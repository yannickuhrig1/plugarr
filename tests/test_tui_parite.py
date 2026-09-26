"""Parite du TUI avec l'assistant web.

Demande du 26/09/2026 : « l'installateur TUI doit avoir les memes fonctions que
la page HTML ». Chaque test ici porte une fonction que le web avait et que le
TUI n'avait pas.
"""

from __future__ import annotations

import pytest
from textual.widgets import Button, Static

from plugarr import compose, orchestrator, updates
from plugarr.orchestrator import InstallAborted
from plugarr.tui.app import PlugArrApp
from plugarr.tui.screens import InstallScreen, ReportScreen, ServicesScreen, SummaryScreen


@pytest.fixture(autouse=True)
def _sans_registres(monkeypatch):
    monkeypatch.setattr(updates, "disponibles", lambda _cfg: {"updates": [], "unchecked": []})


@pytest.fixture
def app(tmp_path):
    return PlugArrApp(project_dir=tmp_path)


# ------------------------------------------------------ 1. relance apres echec


@pytest.mark.asyncio
async def test_un_echec_propose_de_revoir_les_reglages_et_reessayer(app, monkeypatch, attendre):
    def interrompue(*_a, **_k):
        raise InstallAborted("sonarr n'a pas repondu")

    monkeypatch.setattr(orchestrator, "install", interrompue)

    async with app.run_test() as pilot:
        pilot.app.stack_config = pilot.app.build_config()
        await pilot.app.push_screen(SummaryScreen())
        await pilot.app.push_screen(InstallScreen())
        await pilot.pause()
        relance = pilot.app.screen.query_one("#retry", Button)
        assert await attendre(pilot, lambda: "hidden" not in relance.classes)

        relance.press()
        assert await attendre(pilot, lambda: isinstance(pilot.app.screen, SummaryScreen))


@pytest.mark.asyncio
async def test_une_installation_reussie_ne_propose_pas_de_relance(app, monkeypatch, attendre):
    monkeypatch.setattr(orchestrator, "install", lambda *_a, **_k: [])

    async with app.run_test() as pilot:
        pilot.app.stack_config = pilot.app.build_config()
        await pilot.app.push_screen(SummaryScreen())
        await pilot.app.push_screen(InstallScreen())
        termine = pilot.app.screen.query_one("#done", Button)
        assert await attendre(pilot, lambda: not termine.disabled)

        assert "hidden" in pilot.app.screen.query_one("#retry", Button).classes


# ------------------------------------------------- 2. reprise : pages sautees


@pytest.mark.asyncio
async def test_en_reprise_les_applications_menent_au_recapitulatif(tmp_path, attendre):
    precedente = orchestrator.build_config(
        services=["sonarr", "qbittorrent"],
        config_root=str(tmp_path / "config"),
        data_root=str(tmp_path / "data"),
    )
    compose.write_artifacts(precedente, tmp_path)
    app = PlugArrApp(project_dir=tmp_path)

    async with app.run_test() as pilot:
        await pilot.app.push_screen(ServicesScreen())
        await pilot.pause()
        pilot.app.screen.query_one("#next", Button).press()
        assert await attendre(pilot, lambda: isinstance(pilot.app.screen, SummaryScreen))

        ecran = pilot.app.screen
        assert ecran.saute is True
        assert "hidden" not in ecran.query_one("#saute", Static).classes
        assert "hidden" not in ecran.query_one("#modifier", Button).classes


@pytest.mark.asyncio
async def test_une_premiere_installation_passe_par_tous_les_ecrans(app, attendre):
    from plugarr.tui.screens import PathsScreen

    async with app.run_test() as pilot:
        await pilot.app.push_screen(ServicesScreen())
        await pilot.pause()
        pilot.app.screen.query_one("#next", Button).press()
        assert await attendre(pilot, lambda: isinstance(pilot.app.screen, PathsScreen))


# ----------------------------------- 3. rapport : mises a jour et administration


@pytest.mark.asyncio
async def test_le_rapport_liste_les_mises_a_jour(app, monkeypatch, attendre):
    monkeypatch.setattr(
        updates,
        "disponibles",
        lambda _cfg: {
            "updates": [{"id": "sonarr", "name": "Sonarr", "current": "4.0.20", "latest": "4.0.21"}],
            "unchecked": ["Flood"],
        },
    )

    async with app.run_test() as pilot:
        pilot.app.stack_config = pilot.app.build_config()
        pilot.app.results = []
        await pilot.app.push_screen(ReportScreen())
        zone = pilot.app.screen.query_one("#report-updates", Static)

        assert await attendre(pilot, lambda: "4.0.21" in str(zone.render()))
        assert "Flood" in str(zone.render())


@pytest.mark.asyncio
async def test_le_rapport_ouvre_l_administration(app, monkeypatch, attendre):
    import webbrowser

    from plugarr import admin

    class FauxServeur:
        server_address = ("127.0.0.1", 45678)

        def serve_forever(self):
            pass

    ouvertes = []
    monkeypatch.setattr(admin, "build_server", lambda *_a, **_k: FauxServeur())
    monkeypatch.setattr(admin, "generate_token", lambda: "jeton-essai")
    monkeypatch.setattr(webbrowser, "open", lambda url: ouvertes.append(url) or True)

    async with app.run_test() as pilot:
        pilot.app.stack_config = pilot.app.build_config()
        pilot.app.results = []
        await pilot.app.push_screen(ReportScreen())
        await pilot.pause()
        pilot.app.screen.query_one("#open-admin", Button).press()
        zone = pilot.app.screen.query_one("#report-admin", Static)
        assert await attendre(pilot, lambda: "45678" in str(zone.render()))

    assert ouvertes == ["http://127.0.0.1:45678/?t=jeton-essai"]
