"""Tests du profil de plateforme et de la coherence des chemins.

Signale a l'usage, sur Windows : l'assistant ne proposait que `generic-linux`,
`unraid` et `synology`. Aucune option ne correspondait a la machine, et les
chemins Linux qui allaient avec passaient sans un mot — Docker Desktop les cree
alors a la racine du disque courant, `/mnt/user/data` devenant
`C:\\mnt\\user\\data`.
"""

from __future__ import annotations

import sys

import pytest

from plugarr.layout import PROFILE_DEFAULTS, default_profile, path_warning, resolve_ids
from plugarr.models import PlatformProfile


def test_chaque_profil_a_ses_valeurs_par_defaut():
    """Un profil sans valeurs ferait planter l'assistant a la selection."""
    for profile in PlatformProfile:
        assert profile in PROFILE_DEFAULTS, profile


def test_windows_propose_des_chemins_windows():
    defaults = PROFILE_DEFAULTS[PlatformProfile.WINDOWS]

    assert defaults.config_root.startswith("C:/")
    assert defaults.data_root.startswith("C:/")


def test_le_profil_par_defaut_suit_la_machine():
    attendu = PlatformProfile.WINDOWS if sys.platform == "win32" else PlatformProfile.GENERIC_LINUX
    assert default_profile() is attendu


def test_windows_n_affiche_pas_d_avertissement_sur_les_identifiants():
    """Sous Docker Desktop, PUID/PGID n'ont aucun effet.

    Afficher « non detectables, valeur de repli » en jaune inquietait pour rien.
    On donne une valeur assumee, et on explique qu'elle est sans objet ici.
    """
    _uid, _gid, source, certain = resolve_ids(PlatformProfile.WINDOWS)

    assert certain is True
    assert "sans effet" in source


# ------------------------------------------------------- coherence des chemins


@pytest.mark.skipif(sys.platform != "win32", reason="comportement propre a Windows")
def test_un_chemin_linux_est_signale_sous_windows():
    avertissement = path_warning("/mnt/user/data")

    assert avertissement is not None
    # Le message doit dire OU le dossier atterrira reellement : c'est ce qui
    # rend le probleme evident.
    assert "C:" in avertissement and "mnt" in avertissement


@pytest.mark.skipif(sys.platform != "win32", reason="comportement propre a Windows")
@pytest.mark.parametrize("chemin", ["C:/plugarr/data", "D:\\medias", "c:/minuscule"])
def test_un_chemin_windows_ne_declenche_rien(chemin):
    assert path_warning(chemin) is None


@pytest.mark.skipif(sys.platform == "win32", reason="comportement propre a Linux")
def test_un_chemin_windows_est_signale_ailleurs():
    assert path_warning("C:/plugarr/data") is not None
    assert path_warning("/srv/data") is None


def test_un_chemin_vide_ne_declenche_rien():
    """Le champ est vide au demarrage : ce n'est pas une erreur a signaler."""
    assert path_warning("") is None
    assert path_warning("   ") is None


# ----------------------------------------------------------------- assistant


@pytest.mark.asyncio
async def test_l_assistant_preselectionne_le_profil_de_la_machine(tmp_path):
    from textual.widgets import Input, RadioSet

    from plugarr.tui.app import PlugArrApp
    from plugarr.tui.screens import PathsScreen

    app = PlugArrApp(project_dir=tmp_path)
    async with app.run_test() as pilot:
        await app.push_screen(PathsScreen())
        await pilot.pause()
        screen = app.screen

        coche = screen.query_one("#platform", RadioSet).pressed_button
        assert str(coche.label) == default_profile().value
        assert (
            screen.query_one("#data-root", Input).value
            == PROFILE_DEFAULTS[default_profile()].data_root
        )


@pytest.mark.asyncio
async def test_la_verification_dit_ou_le_dossier_atterrit(tmp_path):
    """« hardlink OK » seul ne prouvait rien : le controle validait
    `/mnt/user/data` sous Windows sans signaler qu'il creait `C:\\mnt\\user\\data`."""
    from textual.widgets import Button, Input, Static

    from plugarr.tui.app import PlugArrApp
    from plugarr.tui.screens import PathsScreen

    app = PlugArrApp(project_dir=tmp_path)
    async with app.run_test() as pilot:
        await app.push_screen(PathsScreen())
        await pilot.pause()
        screen = app.screen
        screen.query_one("#data-root", Input).value = str(tmp_path / "media")
        await pilot.pause()
        screen.query_one("#check", Button).press()
        for _ in range(10):
            await pilot.pause()

        texte = str(screen.query_one("#paths-check", Static).content)

    assert "Dossier vise" in texte
    assert str(tmp_path.resolve()) in texte
    assert "hardlink" in texte


@pytest.mark.asyncio
async def test_la_note_explique_ce_que_sont_puid_et_pgid(tmp_path):
    """« 1000:1000 » ne dit rien a qui n'a jamais administre un systeme Unix."""
    from textual.widgets import Static

    from plugarr.tui.app import PlugArrApp
    from plugarr.tui.screens import PathsScreen

    app = PlugArrApp(project_dir=tmp_path)
    async with app.run_test() as pilot:
        await app.push_screen(PathsScreen())
        await pilot.pause()
        note = str(app.screen.query_one("#platform-note", Static).content)

    assert "utilisateur Linux" in note
    assert "possedera vos fichiers" in note
