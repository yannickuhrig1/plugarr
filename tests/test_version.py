"""Tests de l'affichage de la version.

Demande a l'usage : « ce sera plus simple en cas de souci avec un utilisateur ».
C'est la premiere chose a demander quand quelqu'un signale un probleme, et la
derniere qu'il pense a donner.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from plugarr import __version__

RACINE = Path(__file__).resolve().parent.parent


def test_la_version_ressemble_a_une_version():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), __version__


def test_le_paquet_et_le_module_ne_peuvent_plus_diverger():
    """Ils avaient deja diverge : 0.1.0 dans le module, 0.1.1 dans pyproject.

    `pyproject.toml` lit desormais la version dans `__init__.py` : une seule
    source, et l'utilisateur voit la meme partout.
    """
    projet = tomllib.loads((RACINE / "pyproject.toml").read_text(encoding="utf-8"))

    assert "version" in projet["project"].get("dynamic", []), (
        "la version doit rester dynamique, sinon les deux valeurs redivergeront"
    )
    assert projet["tool"]["hatch"]["version"]["path"] == "src/plugarr/__init__.py"


def test_le_journal_commence_par_la_version(tmp_path):
    from plugarr import journal

    chemin = journal.start(tmp_path, "test")
    journal.finish("fin")

    contenu = chemin.read_text(encoding="utf-8")
    assert f"plugarr {__version__}" in contenu
    # Et de quoi situer la machine, sans quoi un rapport reste inexploitable.
    assert "plateforme :" in contenu
    assert "python     :" in contenu


@pytest.mark.asyncio
async def test_l_assistant_affiche_la_version(tmp_path):
    from plugarr.tui.app import PlugArrApp
    from plugarr.tui.screens import ServicesScreen

    app = PlugArrApp(project_dir=tmp_path)
    async with app.run_test() as pilot:
        await app.push_screen(ServicesScreen())
        await pilot.pause()
        bandeau = str(app.screen.query_one("#wizard-header").content)

    assert __version__ in bandeau


def test_la_page_d_acces_porte_la_version(tmp_path):
    from plugarr import dashboard
    from plugarr.orchestrator import build_config

    cfg = build_config(
        services=["sonarr"], config_root=str(tmp_path / "c"), data_root=str(tmp_path / "d")
    )

    assert f"plugarr {__version__}" in dashboard.render(cfg)
