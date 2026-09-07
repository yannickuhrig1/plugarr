"""macOS : une racine systeme en LECTURE SEULE, et un preflight qui se taisait.

Signale par un utilisateur sur r/FrancePirate, capture a l'appui. Il lance
`plugarr install --dry-run` sur son Mac et recoit :

    hardlinks /data   WARNING   impossible de creer /srv/data/torrents ou
                                /srv/data/media: [Errno 30] Read-only file
                                system: '/srv'

Sa capture porte les trois defauts a la fois, et ils sont independants :

1. le profil `generic-linux` etait le seul qu'on proposait a un Mac, avec son
   `/srv/data`. Depuis Catalina la racine de macOS est un volume systeme signe,
   monte en lecture seule : `/srv` n'y est pas et ne peut pas y etre cree ;
2. le preflight ne verifiait nulle part qu'on peut ECRIRE. Une condition fatale
   sortait en avertissement jaune, sur la ligne des hardlinks — qui parle
   d'autre chose — et l'installation reelle mourait ensuite sur un errno nu ;
3. ce message-la etait le seul de sa fonction a ne pas passer par `t()` : son
   tableau etait en anglais, cette ligne en francais.

Reproduit avant correction sur un tmpfs monte en lecture seule : dry-run
identique a la capture, puis `install --yes` terminant sur
`OSError : [Errno 30] Read-only file system`, sans une piste sur quoi changer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from plugarr import layout, orchestrator
from plugarr.models import PlatformProfile
from plugarr.runner import check_writable

# ------------------------------------------------------- le profil manquant


def test_un_mac_ne_recoit_plus_le_profil_linux(monkeypatch):
    """C'est la racine du probleme : `darwin` tombait dans `generic-linux`."""
    monkeypatch.setattr(sys, "platform", "darwin")

    assert layout.default_profile() is PlatformProfile.MACOS


@pytest.mark.parametrize(
    ("plateforme", "attendu"),
    [("win32", PlatformProfile.WINDOWS), ("linux", PlatformProfile.GENERIC_LINUX)],
)
def test_les_autres_plateformes_ne_bougent_pas(monkeypatch, plateforme, attendu):
    monkeypatch.setattr(sys, "platform", plateforme)

    assert layout.default_profile() is attendu


def test_les_chemins_macos_ne_sont_pas_sur_le_volume_systeme():
    """`/srv` et `/opt` sont les deux pieges, pour deux raisons differentes.

    `/srv` ne peut pas etre cree du tout. `/opt` le peut — Homebrew y vit — mais
    ne fait PAS partie des dossiers que Docker Desktop partage par defaut : le
    dossier se creerait et le montage echouerait plus tard, ce qui est pire
    qu'un refus franc.
    """
    defauts = layout.PROFILE_DEFAULTS[PlatformProfile.MACOS]

    for chemin in (defauts.data_root, defauts.config_root):
        assert not chemin.startswith("/srv")
        assert not chemin.startswith("/opt")
        assert str(Path.home()) in chemin


def test_les_chemins_macos_sont_absolus():
    """Un `~` serait ecrit tel quel dans .env puis dans docker-compose.yml, ou
    Docker ne l'etend pas : il creerait un dossier litteralement nomme `~`."""
    defauts = layout.PROFILE_DEFAULTS[PlatformProfile.MACOS]

    assert "~" not in defauts.data_root
    assert Path(defauts.data_root).is_absolute()
    assert Path(defauts.config_root).is_absolute()


# ------------------------------------------------ le controle qui manquait


def test_un_dossier_inscriptible_passe(tmp_path):
    controle = check_writable(tmp_path, "racine des donnees")

    assert controle.ok


def test_un_dossier_a_creer_passe_si_son_parent_accepte(tmp_path):
    """Le cas courant : DATA_ROOT n'existe pas encore, et c'est normal."""
    controle = check_writable(tmp_path / "pas" / "encore" / "la", "racine des donnees")

    assert controle.ok


def test_le_controle_ne_cree_rien(tmp_path):
    """Un preflight — a plus forte raison sous --dry-run — ne doit pas poser
    l'arborescence qu'il examine."""
    cible = tmp_path / "absent"

    check_writable(cible, "racine des donnees")

    assert not cible.exists()
    assert list(tmp_path.iterdir()) == [], "un fichier temoin a ete laisse derriere"


def test_un_emplacement_impossible_est_BLOQUANT(tmp_path, monkeypatch):
    """Le coeur du correctif. En avertissement, l'installation partait quand
    meme et mourait sur sa premiere ecriture."""

    def refuser(*_a, **_kw):
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr("tempfile.NamedTemporaryFile", refuser)

    controle = check_writable(tmp_path / "data", "racine des donnees")

    assert not controle.ok
    assert controle.blocking, "un chemin impossible doit ARRETER l'installation"


def test_le_refus_dit_quoi_changer(tmp_path, monkeypatch):
    """« [Errno 30] Read-only file system » ne dit pas quoi faire. Le remede
    doit etre dans le message, pas dans la tete du lecteur."""

    def refuser(*_a, **_kw):
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr("tempfile.NamedTemporaryFile", refuser)

    detail = check_writable(tmp_path / "data", "racine des donnees").detail

    assert "--data-root" in detail


def test_le_preflight_controle_les_deux_racines(tmp_path, monkeypatch):
    """Les deux, pas seulement DATA_ROOT : sur macOS c'est bien `/srv` qui
    casse, mais `/opt/plugarr/config` n'aurait pas ete monte pour autant."""
    monkeypatch.setattr(orchestrator, "check_docker", list)
    monkeypatch.setattr(orchestrator, "our_published_ports", lambda cfg, d: set())
    cfg = orchestrator.build_config(
        services=["sonarr"],
        config_root=str(tmp_path / "config"),
        data_root=str(tmp_path / "data"),
    )

    noms = [c.name for c in orchestrator.preflight(cfg, None)]

    assert "racine des donnees" in noms
    assert "racine des configurations" in noms


# ------------------------------------------------------- le t() oublie


def test_le_refus_de_creer_passe_par_le_catalogue(tmp_path, monkeypatch):
    """Sa capture montrait un tableau anglais avec UNE ligne en francais.

    L'audit des traductions ne pouvait pas le voir : il releve les `t("...")`
    presents, jamais un `t()` absent. Ce test le voit.
    """
    from plugarr import i18n

    avant = i18n.langue()
    monkeypatch.setattr(Path, "mkdir", lambda *_a, **_kw: (_ for _ in ()).throw(OSError("nope")))
    try:
        i18n.utiliser("en")
        _ok, detail = layout.hardlink_supported(tmp_path / "data")
    finally:
        i18n.utiliser(avant)

    assert "cannot create" in detail, "le message n'est pas traduit"
