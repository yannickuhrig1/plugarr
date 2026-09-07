"""L'assistant sait aussi SAUVEGARDER, pas seulement restaurer.

Demande a l'usage : « ajoute aussi la possibilite de creer une sauvegarde lors
du lancement de l'exe, pas seulement la restauration. »

La dissymetrie coutait cher. `plugarr backup` et la console d'administration
savaient archiver ; l'assistant, non. Or c'est l'assistant, et lui seul, que
voit quelqu'un qui double-clique un executable. Il n'avait donc de sauvegarde
que s'il en avait deja une — exactement au moment ou il n'en a pas.

Le moment compte autant que le bouton : c'est avant de relancer une
installation par-dessus une autre qu'une archive a le plus de valeur.
"""

from __future__ import annotations

import pytest
from textual.widgets import Button, Checkbox, Input, Static

from plugarr import compose, orchestrator
from plugarr.tui.app import PlugArrApp
from plugarr.tui.screens import SauvegardeScreen


def _installation(tmp_path, projet):
    cfg = orchestrator.build_config(
        services=["sonarr", "jellyfin"],
        config_root=str(tmp_path / "config"),
        data_root=str(tmp_path / "data"),
    )
    compose.write_artifacts(cfg, projet)
    return cfg


def _source(app) -> str:
    return str(app.screen.query_one("#sauvegarde-source", Static).content)


def _etat(app) -> str:
    return str(app.screen.query_one("#sauvegarde-etat", Static).content)


@pytest.fixture
def assistant(tmp_path):
    app = PlugArrApp(tmp_path / "projet")
    app.auto_open_page = False
    return app


@pytest.mark.asyncio
async def test_le_premier_ecran_propose_la_sauvegarde(assistant):
    """Le seul ecran qu'un utilisateur voit doit porter les deux sens."""
    async with assistant.run_test(size=(110, 40)) as pilot:
        await pilot.pause()

        boutons = {b.id for b in assistant.screen.query(Button)}
        assert {"sauvegarder", "restaurer"} <= boutons


@pytest.mark.asyncio
async def test_l_installation_du_repertoire_est_trouvee_seule(assistant, tmp_path):
    """Rien a saisir : les champs sont deja remplis quand l'ecran s'ouvre."""
    _installation(tmp_path, tmp_path / "projet")

    async with assistant.run_test(size=(110, 40)) as pilot:
        assistant.push_screen(SauvegardeScreen())
        await pilot.pause()

        assert not assistant.screen.query_one("#lancer", Button).disabled
        assert str(tmp_path / "projet") in assistant.screen.query_one("#source", Input).value
        assert assistant.screen.query_one("#destination", Input).value.endswith(".zip")


@pytest.mark.asyncio
async def test_une_installation_posee_ailleurs_est_retrouvee(assistant, tmp_path):
    """Meme registre que la reprise : l'exe lance ailleurs trouve quand meme.

    Sans cela, le bouton serait inerte pour la personne qui a deplace
    `plugarr.exe` — c'est-a-dire pour celle qui en a le plus besoin.
    """
    _installation(tmp_path, tmp_path / "ailleurs")

    async with assistant.run_test(size=(110, 40)) as pilot:
        assistant.push_screen(SauvegardeScreen())
        await pilot.pause()

        assert not assistant.screen.query_one("#lancer", Button).disabled
        assert "ailleurs" in assistant.screen.query_one("#source", Input).value


@pytest.mark.asyncio
async def test_sans_installation_le_bouton_reste_inerte(assistant, tmp_path):
    """Et l'ecran dit quoi faire, plutot que d'echouer au moment du clic."""
    async with assistant.run_test(size=(110, 40)) as pilot:
        assistant.push_screen(SauvegardeScreen())
        await pilot.pause()

        assert assistant.screen.query_one("#lancer", Button).disabled
        assert "stack.yml" in _source(assistant)


@pytest.mark.asyncio
async def test_l_arret_des_conteneurs_est_le_defaut(assistant, tmp_path):
    """Une base SQLite copiee a chaud est corrompue sans le dire.

    La case existe pour qui accepte ce risque en connaissance de cause ; elle
    ne doit jamais etre cochee a sa place.
    """
    _installation(tmp_path, tmp_path / "projet")

    async with assistant.run_test(size=(110, 40)) as pilot:
        assistant.push_screen(SauvegardeScreen())
        await pilot.pause()

        assert assistant.screen.query_one("#a-chaud", Checkbox).value is False


@pytest.mark.asyncio
async def test_une_archive_est_reellement_ecrite(assistant, tmp_path, attendre, monkeypatch):
    """Le bouton archive pour de vrai. Docker est simule : la copie, non."""
    from plugarr import sauvegarde

    projet = tmp_path / "projet"
    cfg = _installation(tmp_path, projet)
    (tmp_path / "config" / "sonarr").mkdir(parents=True)
    (tmp_path / "config" / "sonarr" / "sonarr.db").write_text("vos profils", encoding="utf-8")

    class _Compose:
        def __init__(self, *a, **kw):
            pass

        def stop(self):
            return True, ""

        def up(self):
            return True, ""

    monkeypatch.setattr(sauvegarde, "Compose", _Compose)
    monkeypatch.setattr(sauvegarde, "volumes_du_projet", lambda _cfg: [])

    destination = tmp_path / "archive.zip"

    async with assistant.run_test(size=(110, 40)) as pilot:
        assistant.push_screen(SauvegardeScreen())
        await pilot.pause()
        assistant.screen.query_one("#destination", Input).value = str(destination)
        assistant.screen.query_one("#lancer", Button).press()

        assert await attendre(pilot, lambda: "terminee" in _etat(assistant))

    assert sauvegarde.lire_manifeste(destination)["services"] == sorted(cfg.services)
