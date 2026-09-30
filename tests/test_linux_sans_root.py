"""Linux sans root : `/srv` et `/opt` refuses, et l'installation qui butait dessus.

Constate en installant a partir des paquets sur un Linux natif, avec un compte
ordinaire : « impossible d'ecrire dans /srv ». Les defauts de `generic-linux`
etaient les seuls proposes, et il fallait tout refaire a la main sous un dossier
de test. Le profil doit maintenant proposer, de lui-meme, des dossiers que le
compte peut ecrire.
"""

from __future__ import annotations

import sys
from pathlib import Path

from plugarr import layout, orchestrator
from plugarr.models import PlatformProfile

LINUX = PlatformProfile.GENERIC_LINUX


def _machine_linux(monkeypatch, *, inscriptible: bool) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(layout, "_peut_creer_sous", lambda chemin: inscriptible)


def test_sans_droit_sur_srv_les_defauts_passent_sous_le_dossier_personnel(monkeypatch):
    _machine_linux(monkeypatch, inscriptible=False)

    defauts = layout.profile_defaults(LINUX)

    for chemin in (defauts.config_root, defauts.data_root):
        assert Path(chemin).is_absolute()
        assert "~" not in chemin
        assert chemin.startswith(str(Path.home()))
    assert defauts.note, "l'utilisateur doit savoir pourquoi les chemins different"


def test_avec_les_droits_les_defauts_ne_bougent_pas(monkeypatch):
    _machine_linux(monkeypatch, inscriptible=True)

    assert layout.profile_defaults(LINUX) is layout.PROFILE_DEFAULTS[LINUX]


def test_seul_generic_linux_est_adapte(monkeypatch):
    _machine_linux(monkeypatch, inscriptible=False)

    for profil in PlatformProfile:
        if profil is not LINUX:
            assert layout.profile_defaults(profil) is layout.PROFILE_DEFAULTS[profil]


def test_la_table_statique_n_est_pas_modifiee(monkeypatch):
    _machine_linux(monkeypatch, inscriptible=False)

    layout.profile_defaults(LINUX)

    assert layout.PROFILE_DEFAULTS[LINUX].data_root == "/srv/data"


def test_build_config_utilise_le_repli(monkeypatch):
    _machine_linux(monkeypatch, inscriptible=False)

    cfg = orchestrator.build_config(services=["sonarr"], platform=LINUX)

    assert cfg.data_root.startswith(str(Path.home()))
    assert cfg.config_root.startswith(str(Path.home()))


def test_un_chemin_saisi_l_emporte_sur_le_repli(monkeypatch):
    _machine_linux(monkeypatch, inscriptible=False)

    cfg = orchestrator.build_config(
        services=["sonarr"], platform=LINUX, data_root="/mnt/x", config_root="/mnt/y"
    )

    assert (cfg.data_root, cfg.config_root) == ("/mnt/x", "/mnt/y")


def test_peut_creer_sous_juge_le_premier_ancetre_existant(tmp_path):
    assert layout._peut_creer_sous(str(tmp_path / "a" / "b"))
