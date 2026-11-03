"""Les artefacts sont remplaces d'un seul coup.

`write_text` vide d'abord le fichier : un arret en pleine ecriture laissait un
`stack.yml` incomplet, seule copie des mots de passe, et un `.env` neuf restait
lisible par tous jusqu'au `chmod` qui suivait.
"""

from __future__ import annotations

import os
import stat

import pytest

from plugarr import compose, orchestrator

posix = pytest.mark.skipif(os.name != "posix", reason="droits POSIX")


def _droits(chemin):
    return stat.S_IMODE(chemin.stat().st_mode)


def _cfg(tmp_path):
    return orchestrator.build_config(
        services=["sonarr"],
        config_root=str(tmp_path / "config"),
        data_root=str(tmp_path / "data"),
    )


def test_un_arret_en_pleine_ecriture_laisse_l_ancien_fichier(tmp_path, monkeypatch):
    cible = tmp_path / "stack.yml"
    cible.write_text("ancien", encoding="utf-8")

    def panne(_fd):
        raise OSError("disque plein")

    monkeypatch.setattr(compose.os, "fsync", panne)

    with pytest.raises(OSError, match="disque plein"):
        compose._ecrire_atomique(cible, "nouveau", secret=True)

    assert cible.read_text(encoding="utf-8") == "ancien"
    assert [p.name for p in tmp_path.iterdir()] == ["stack.yml"], "reliquat temporaire"


@posix
def test_un_secret_nait_en_600(tmp_path, monkeypatch):
    """Ecrit puis restreint, il reste lisible par tous entre les deux. L'umask a 0
    est le pire cas : seul le mode passe a la creation protege alors le fichier."""
    naissances = []
    vrai_open = os.open

    def espion(chemin, *args, **kw):
        descripteur = vrai_open(chemin, *args, **kw)
        naissances.append(stat.S_IMODE(os.fstat(descripteur).st_mode))
        return descripteur

    monkeypatch.setattr(compose.os, "open", espion)
    ancien = os.umask(0)
    try:
        compose._ecrire_atomique(tmp_path / ".env", "CLE=1\n", secret=True)
    finally:
        os.umask(ancien)

    assert naissances == [0o600]
    assert _droits(tmp_path / ".env") == 0o600


@posix
def test_les_secrets_restent_en_600_apres_reecriture(tmp_path):
    projet = tmp_path / "projet"
    compose.write_artifacts(_cfg(tmp_path), projet)
    (projet / ".env").chmod(0o644)

    compose.write_artifacts(_cfg(tmp_path), projet)

    assert _droits(projet / ".env") == 0o600
    assert _droits(projet / "stack.yml") == 0o600


@posix
def test_docker_compose_garde_les_droits_qu_on_lui_a_donnes(tmp_path):
    """Forcer 644 rouvrirait a tous un fichier que quelqu'un a volontairement ferme."""
    projet = tmp_path / "projet"
    compose.write_artifacts(_cfg(tmp_path), projet)
    (projet / "docker-compose.yml").chmod(0o600)

    compose.write_artifacts(_cfg(tmp_path), projet)

    assert _droits(projet / "docker-compose.yml") == 0o600


@posix
def test_un_docker_compose_neuf_suit_l_umask(tmp_path):
    ancien = os.umask(0o077)
    try:
        compose.write_artifacts(_cfg(tmp_path), tmp_path / "projet")
    finally:
        os.umask(ancien)

    assert _droits(tmp_path / "projet" / "docker-compose.yml") == 0o600


@posix
def test_un_lien_symbolique_reste_un_lien(tmp_path):
    """Sinon la copie reelle, celle qu'on sauvegarde, cesse d'etre mise a jour."""
    reel = tmp_path / "ailleurs.yml"
    reel.write_text("ancien", encoding="utf-8")
    lien = tmp_path / "docker-compose.yml"
    lien.symlink_to(reel)

    compose._ecrire_atomique(lien, "nouveau")

    assert lien.is_symlink()
    assert reel.read_text(encoding="utf-8") == "nouveau"


def test_un_temporaire_oublie_est_ignore_par_git():
    """Tue au mauvais moment, le processus laisse un temporaire plein de mots de
    passe, et `stack.yml.*` ne couvre pas un nom qui commence par un point."""
    assert ".*.tmp" in compose._GITIGNORE.splitlines()
