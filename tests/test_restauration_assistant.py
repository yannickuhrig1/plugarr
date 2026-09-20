"""La restauration vit dans l'assistant, pas sur la console.

Signale a l'usage : « pourquoi ne pas mettre un bouton restauration avec
charger le fichier de sauvegarde ? Ce serait pratique pour restaurer apres un
formatage ou changement de setup. »

L'objection etait juste, et la premiere reponse — « un bouton a un clic d'une
mauvaise archive serait une arme » — etait faible : la ligne de commande a
exactement le meme pouvoir, et une confirmation suffit.

La vraie raison est ailleurs, et elle designe le bon endroit. La console
d'administration commence par lire un `stack.yml` ; sur une machine
fraichement formatee il n'y en a pas, puisque c'est justement ce que l'archive
contient. Un bouton la-bas aurait ete inutilisable dans le seul cas ou il sert.

L'assistant, lui, demarre sans rien.
"""

from __future__ import annotations

import asyncio
import json
import zipfile
from pathlib import Path

import pytest
from textual.widgets import Button, Input, Static

from plugarr import sauvegarde
from plugarr.tui.app import PlugArrApp
from plugarr.tui.screens import RestaurationScreen


def _archive(dossier: Path, *, a_chaud: bool = False) -> Path:
    archive = dossier / "essai.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("projet/stack.yml", "project_name: plugarr\n")
        zf.writestr("projet/.env", "CONFIG_ROOT=C:/origine\n")
        zf.writestr("config/prowlarr/prowlarr.db", "vos indexeurs")
        zf.writestr(
            sauvegarde.MANIFESTE,
            json.dumps(
                {
                    "format": sauvegarde.FORMAT,
                    "date": "2026-09-04T07:00:00+00:00",
                    "project_name": "plugarr",
                    "config_root": "C:/origine",
                    "data_root": "C:/medias",
                    "services": ["prowlarr", "sonarr"],
                    "volumes": [],
                    "a_chaud": a_chaud,
                }
            ),
        )
    return archive


def _etat(app) -> str:
    return str(app.screen.query_one("#restauration-etat", Static).content)


@pytest.fixture
def assistant(tmp_path):
    app = PlugArrApp(tmp_path / "projet")
    app.auto_open_page = False
    return app


@pytest.mark.asyncio
async def test_le_premier_ecran_propose_la_restauration(assistant):
    """C'est le seul ecran qu'un utilisateur voit sur une machine neuve."""
    async with assistant.run_test(size=(110, 40)) as pilot:
        await pilot.pause()
        assert assistant.screen.query_one("#restaurer", Button) is not None


@pytest.mark.asyncio
async def test_le_bouton_reste_inerte_avant_lecture(assistant, tmp_path):
    """On ne restaure pas a l'aveugle : l'examen remplace la confirmation."""
    async with assistant.run_test(size=(110, 40)) as pilot:
        await assistant.push_screen(RestaurationScreen())
        await pilot.pause()

        assert assistant.screen.query_one("#poser", Button).disabled


@pytest.mark.asyncio
async def test_une_archive_introuvable_est_dite(assistant):
    async with assistant.run_test(size=(110, 40)) as pilot:
        await assistant.push_screen(RestaurationScreen())
        await pilot.pause()
        assistant.screen.query_one("#archive", Input).value = "C:/nexiste/pas.zip"
        assistant.screen.query_one("#examiner", Button).press()
        await pilot.pause()

        assert "introuvable" in _etat(assistant)
        assert assistant.screen.query_one("#poser", Button).disabled


@pytest.mark.asyncio
async def test_l_examen_montre_le_contenu(assistant, tmp_path):
    """Ce que l'utilisateur doit voir AVANT d'ecraser sa configuration."""
    archive = _archive(tmp_path)
    async with assistant.run_test(size=(110, 40)) as pilot:
        await assistant.push_screen(RestaurationScreen())
        await pilot.pause()
        assistant.screen.query_one("#archive", Input).value = str(archive)
        assistant.screen.query_one("#examiner", Button).press()
        await pilot.pause()

        etat = _etat(assistant)
        assert "prowlarr" in etat
        assert "C:/origine" in etat
        assert not assistant.screen.query_one("#poser", Button).disabled


@pytest.mark.asyncio
async def test_une_archive_a_chaud_est_signalee(assistant, tmp_path):
    """Ses bases peuvent etre corrompues : le taire serait un piege."""
    archive = _archive(tmp_path, a_chaud=True)
    async with assistant.run_test(size=(110, 40)) as pilot:
        await assistant.push_screen(RestaurationScreen())
        await pilot.pause()
        assistant.screen.query_one("#archive", Input).value = str(archive)
        assistant.screen.query_one("#examiner", Button).press()
        await pilot.pause()

        assert "A CHAUD" in _etat(assistant)


@pytest.mark.asyncio
async def test_la_restauration_repose_reellement_les_fichiers(assistant, tmp_path):
    archive = _archive(tmp_path)
    cible = tmp_path / "restaure"
    async with assistant.run_test(size=(110, 40)) as pilot:
        await assistant.push_screen(RestaurationScreen())
        await pilot.pause()
        assistant.screen.query_one("#archive", Input).value = str(archive)
        assistant.screen.query_one("#cible", Input).value = str(cible)
        assistant.screen.query_one("#examiner", Button).press()
        await pilot.pause()
        assistant.screen.query_one("#poser", Button).press()
        for _ in range(60):
            await pilot.pause()
            if "terminee" in _etat(assistant):
                break
            await asyncio.sleep(0.05)

    assert (cible / "prowlarr" / "prowlarr.db").read_text(encoding="utf-8") == "vos indexeurs"
    assert (tmp_path / "projet" / "stack.yml").is_file()


@pytest.mark.asyncio
async def test_une_archive_etrangere_est_refusee(assistant, tmp_path):
    """Deballer n'importe quel zip sur CONFIG_ROOT serait destructeur."""
    faux = tmp_path / "faux.zip"
    with zipfile.ZipFile(faux, "w") as zf:
        zf.writestr("bonjour.txt", "je ne suis pas une sauvegarde")

    async with assistant.run_test(size=(110, 40)) as pilot:
        await assistant.push_screen(RestaurationScreen())
        await pilot.pause()
        assistant.screen.query_one("#archive", Input).value = str(faux)
        assistant.screen.query_one("#examiner", Button).press()
        await pilot.pause()

        assert "pas une sauvegarde" in _etat(assistant)
        assert assistant.screen.query_one("#poser", Button).disabled
