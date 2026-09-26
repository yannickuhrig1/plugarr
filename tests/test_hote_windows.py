"""Ce qu'une installation locale ne peut pas faire sous Windows. Bloque AVANT d'ecrire.

Essai reel du 26/09/2026 sous Windows, pile en `generic-linux` :

- `/opt/plugarr/config` : PlugArr y ecrivait dans `C:\\opt\\plugarr\\config`,
  Docker Desktop montait un autre dossier dans sa machine virtuelle. Sonarr
  s'est donne sa propre cle, et l'installation est morte sur un 401 ;
- console en conteneur : Docker Desktop refuse un chemin `C:\\...` comme cible
  de montage (« too many colons »), et `docker compose up` echouait pour toute
  la pile.
"""

from __future__ import annotations

import pytest

from plugarr import orchestrator
from plugarr.orchestrator import InstallAborted


def _cfg(config_root: str, data_root: str, *, console: bool = False):
    cfg = orchestrator.build_config(services=["sonarr"], config_root=config_root, data_root=data_root)
    cfg.console_enabled = console
    return cfg


@pytest.fixture
def windows(monkeypatch):
    monkeypatch.setattr(orchestrator.sys, "platform", "win32")


def test_un_chemin_linux_est_refuse_sous_windows(windows):
    controles = orchestrator.controles_hote(_cfg("/opt/plugarr/config", "/srv/data"))

    assert len(controles) == 2
    assert all(not c.ok and c.blocking for c in controles)
    assert "/opt/plugarr/config" in controles[0].detail


def test_la_console_en_conteneur_est_refusee_sous_windows(windows):
    (controle,) = orchestrator.controles_hote(_cfg("C:/plugarr/config", "C:/plugarr/data", console=True))

    assert not controle.ok and controle.blocking


def test_des_chemins_windows_passent(windows):
    assert orchestrator.controles_hote(_cfg("C:/plugarr/config", "D:\\medias")) == []


def test_rien_n_est_controle_hors_de_windows(monkeypatch):
    """L'installation distante tourne sous Linux : `/opt` y est le bon chemin,
    et la console en conteneur y est prevue."""
    monkeypatch.setattr(orchestrator.sys, "platform", "linux")

    assert orchestrator.controles_hote(_cfg("/opt/plugarr/config", "/srv/data", console=True)) == []


def test_l_installation_s_arrete_avant_d_ecrire(windows, tmp_path):
    """Le TUI ne passe pas par le preflight : `install` doit refuser lui-meme."""
    projet = tmp_path / "projet"
    projet.mkdir()

    with pytest.raises(InstallAborted, match="chemin Linux"):
        orchestrator.install(_cfg("/opt/plugarr/config", "/srv/data"), projet)

    assert list(projet.iterdir()) == []
