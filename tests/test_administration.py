"""Tests de l'acces a la page d'administration.

Signale a l'usage : « la page ne me dit pas s'il y a une mise a jour, et ne me
permet pas d'arreter ou relancer une instance ».

C'etait exact et voulu — la page d'acces est un fichier fige — mais personne ne
devine qu'il faut lancer une commande pour obtenir le reste, surtout apres avoir
double-clique un executable qui n'est pas dans le PATH.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from plugarr import dashboard
from plugarr.orchestrator import build_config


def _cfg(tmp_path):
    return build_config(
        services=["sonarr", "qbittorrent"],
        config_root=str(tmp_path / "c"),
        data_root=str(tmp_path / "d"),
    )


def test_le_lanceur_est_ecrit_a_cote_des_artefacts(tmp_path):
    chemin = dashboard.write_admin_launcher(tmp_path)

    assert chemin.parent == tmp_path
    assert chemin.name == dashboard.LAUNCHER_NAME
    assert chemin.exists()


def test_il_vise_le_bon_repertoire(tmp_path):
    """Sans `--project-dir`, `serve` chercherait un stack.yml dans le dossier
    courant — celui d'ou le double-clic a ete fait, pas celui de la stack."""
    contenu = dashboard.write_admin_launcher(tmp_path).read_text(encoding="utf-8")

    assert str(tmp_path.resolve()) in contenu
    assert "serve" in contenu


def test_il_nomme_l_executable_reellement_utilise(tmp_path):
    """« lancez plugarr serve » n'aide pas quelqu'un qui n'a pas plugarr dans
    son PATH. On note le chemin de cette installation-la."""
    contenu = dashboard.write_admin_launcher(tmp_path).read_text(encoding="utf-8")

    assert Path(sys.executable).name in contenu


@pytest.mark.skipif(sys.platform != "win32", reason="lanceur Windows")
def test_le_lanceur_windows_reste_ouvert(tmp_path):
    """Sans `pause`, la fenetre se ferme sur l'erreur avant qu'on la lise."""
    contenu = dashboard.write_admin_launcher(tmp_path).read_text(encoding="utf-8")

    assert contenu.startswith("@echo off")
    assert "pause" in contenu


@pytest.mark.skipif(sys.platform == "win32", reason="lanceur POSIX")
def test_le_lanceur_posix_est_executable(tmp_path):
    chemin = dashboard.write_admin_launcher(tmp_path)

    assert chemin.read_text(encoding="utf-8").startswith("#!/bin/sh")
    assert chemin.stat().st_mode & 0o111


def test_la_page_figee_renvoie_vers_le_lanceur(tmp_path):
    """Elle disait « lancez plugarr serve » : une commande, pas un fichier."""
    page = dashboard.render(_cfg(tmp_path))

    assert dashboard.LAUNCHER_NAME in page
    assert "mises a jour" in page


def test_la_page_vivante_n_affiche_pas_ce_renvoi(tmp_path):
    """Elle EST la page d'administration : l'y renvoyer serait absurde."""
    page = dashboard.render(_cfg(tmp_path), live=True)

    assert dashboard.LAUNCHER_NAME not in page
    # Et elle porte bien les boutons qui manquaient a l'autre.
    assert 'data-action="stop"' in page
    assert 'data-action="restart"' in page


def test_le_lanceur_est_ecrasable(tmp_path):
    """Reinstaller doit le remettre a jour, pas echouer."""
    dashboard.write_admin_launcher(tmp_path)
    chemin = dashboard.write_admin_launcher(tmp_path)

    assert chemin.exists()


def test_avec_console_en_conteneur_le_lanceur_ne_depend_pas_du_python_de_l_installation(tmp_path):
    """VPS reel du 25/09/2026 : « /usr/local/bin/python3.12: not found »."""
    cfg = _cfg(tmp_path)
    cfg.console_enabled = True
    cfg.host = "10.0.0.30"

    contenu = dashboard.write_admin_launcher(tmp_path, cfg).read_text(encoding="utf-8")

    assert f"docker start {cfg.project_name}-console" in contenu
    assert f"http://10.0.0.30:{cfg.console_port}/" in contenu
    assert str(Path(sys.executable).resolve()) not in contenu

