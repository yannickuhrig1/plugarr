"""Tests de l'ecran de choix des profils de qualite.

Aucun de ces tests ne touche au reseau : le manifeste est simule. C'est la forme
reelle du fichier `templates.json` publie par Recyclarr qui est reproduite.
"""

from __future__ import annotations

import pytest
from textual.widgets import Button, Select, Static

from plugarr.clients import recyclarr
from plugarr.tui.app import PlugArrApp
from plugarr.tui.screens import PathsScreen, RemoteAccessScreen, SummaryScreen, TemplatesScreen

AVAILABLE = {
    "sonarr": ["sonarr-german-hd-bluray-web", "web-1080p", "web-2160p"],
    "radarr": ["french-multi-vf-hd-bluray-web", "hd-bluray-web"],
}


@pytest.fixture
def app(tmp_path):
    return PlugArrApp(project_dir=tmp_path)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """L'assistant ne doit jamais dependre de GitHub pendant les tests."""
    monkeypatch.setattr(recyclarr, "fetch_manifest", lambda **kw: (dict(AVAILABLE), None))


async def _goto_templates(pilot, selection) -> TemplatesScreen:
    pilot.app.selection = selection
    await pilot.app.push_screen(TemplatesScreen())
    # La liste arrive d'un worker en fil separe. Compter les passes d'evenements
    # ne suffit pas : sous charge, deux ne suffisaient pas et un test echouait
    # une fois sur plusieurs dizaines. On attend donc ce que le worker ecrit.
    for _ in range(60):
        await pilot.pause()
        note = pilot.app.screen.query(f"#tpl-choices-{selection[0]}")
        if note and "Chargement" not in str(note.first(Static).content):
            break
    return pilot.app.screen


@pytest.mark.asyncio
async def test_les_defauts_sont_preremplis(app):
    async with app.run_test() as pilot:
        screen = await _goto_templates(pilot, ["sonarr", "radarr", "recyclarr"])

        assert screen.query_one("#tpl-sonarr", Select).value == "web-1080p"
        assert screen.query_one("#tpl-radarr", Select).value == "hd-bluray-web"
        assert screen.choices() == recyclarr.DEFAULT_TEMPLATES


@pytest.mark.asyncio
async def test_seuls_les_services_installes_sont_proposes(app):
    """Sans Radarr, lui demander un profil n'a aucun sens."""
    async with app.run_test() as pilot:
        screen = await _goto_templates(pilot, ["sonarr", "recyclarr"])

        assert screen.query_one("#tpl-sonarr", Select) is not None
        assert not screen.query("#tpl-radarr")
        assert list(screen.choices()) == ["sonarr"]


@pytest.mark.asyncio
async def test_un_nom_inconnu_est_signale_avant_l_installation(app, attendre):
    """Recyclarr ne refuserait le nom qu'a la fin du cablage, stack demarree.

    Le dire ici coute une comparaison ; le decouvrir la-bas coute une
    installation.

    Les attentes sont BORNEES et non un simple `pause` : changer la valeur d'un
    `Select` declenche un message, et sous la charge d'une suite complete le
    bouton n'a pas encore ete rafraichi au tour suivant. Le test tombait alors
    sur un code parfaitement sain.
    """
    async with app.run_test() as pilot:
        screen = await _goto_templates(pilot, ["sonarr", "radarr", "recyclarr"])
        # Une valeur absente de la liste ne peut plus arriver par l'interface :
        # on l'injecte pour verifier que le garde-fou tient quand meme.
        screen._available["sonarr"] = ["web-1080p", "web-2160p"]
        screen.query_one("#tpl-sonarr", Select).set_options([("web-9999p", "web-9999p")])
        screen.query_one("#tpl-sonarr", Select).value = "web-9999p"

        assert await attendre(
            pilot, lambda: screen.query_one("#next", Button).disabled is True
        ), "le bouton est reste actif malgre un nom inconnu"
        assert "inconnu" in str(screen.query_one("#templates-status", Static).content)

        screen.query_one("#tpl-sonarr", Select).set_options([("web-2160p", "web-2160p")])
        screen.query_one("#tpl-sonarr", Select).value = "web-2160p"

        assert await attendre(
            pilot, lambda: screen.query_one("#next", Button).disabled is False
        ), "le bouton est reste bloque alors que le nom est valide"


@pytest.mark.asyncio
async def test_passer_laisse_les_defauts_au_cablage(app):
    """« Passer » ne doit pas signifier « aucun profil »."""
    async with app.run_test() as pilot:
        screen = await _goto_templates(pilot, ["sonarr", "radarr", "recyclarr"])
        screen.query_one("#skip", Button).press()
        await pilot.pause()

        assert pilot.app.recyclarr_templates == {}
        # Le cablage retombe alors sur les defauts du module, pas sur rien.
        cfg = pilot.app.build_config()
        assert cfg.recyclarr_templates == {}
        assert recyclarr.DEFAULT_TEMPLATES["sonarr"] == "web-1080p"


@pytest.mark.asyncio
async def test_un_choix_atteint_la_configuration(app):
    async with app.run_test() as pilot:
        screen = await _goto_templates(pilot, ["sonarr", "radarr", "recyclarr"])
        screen.query_one("#tpl-radarr", Select).value = "french-multi-vf-hd-bluray-web"
        await pilot.pause()
        screen.query_one("#next", Button).press()
        # `press()` poste un message : compter les passes d'evenements suffit
        # d'ordinaire, mais pas sous charge. Troisieme test de la suite a
        # echouer ainsi une fois sur plusieurs dizaines. On attend le resultat.
        for _ in range(60):
            await pilot.pause()
            if pilot.app.recyclarr_templates:
                break

        cfg = pilot.app.build_config()
        assert cfg.recyclarr_templates["radarr"] == "french-multi-vf-hd-bluray-web"


@pytest.mark.asyncio
async def test_un_manifeste_injoignable_n_empeche_pas_de_continuer(app, monkeypatch):
    """Sans reseau, on ne peut pas verifier les noms. Ce n'est pas une raison
    pour bloquer quelqu'un qui sait ce qu'il veut."""
    monkeypatch.setattr(recyclarr, "fetch_manifest", lambda **kw: ({}, "depot injoignable"))

    async with app.run_test() as pilot:
        screen = await _goto_templates(pilot, ["sonarr", "recyclarr"])

        assert screen.query_one("#next", Button).disabled is False
        assert "injoignable" in str(screen.query_one("#templates-status", Static).content)


@pytest.mark.asyncio
async def test_l_ecran_est_saute_sans_recyclarr(app, appuyer):
    """L'etape ne doit pas apparaitre pour une stack qui n'en a pas l'usage."""
    async with app.run_test() as pilot:
        pilot.app.selection = ["sonarr", "radarr"]
        await pilot.app.push_screen(PathsScreen())
        await pilot.pause()
        # L'ecran suivant est l'acces distant (Sonarr est choisi), puis le
        # recapitulatif : l'essentiel est que cet ecran-ci soit saute.
        assert await appuyer(
            pilot, "#next", lambda: isinstance(pilot.app.screen, RemoteAccessScreen)
        )


@pytest.mark.asyncio
async def test_l_ecran_apparait_avec_recyclarr(app, appuyer):
    async with app.run_test() as pilot:
        pilot.app.selection = ["sonarr", "recyclarr"]
        await pilot.app.push_screen(PathsScreen())
        await pilot.pause()
        assert await appuyer(
            pilot, "#next", lambda: isinstance(pilot.app.screen, TemplatesScreen)
        )


@pytest.mark.asyncio
async def test_recyclarr_seul_ne_declenche_pas_l_ecran(app, appuyer):
    """Sans Sonarr ni Radarr, Recyclarr n'a rien a configurer."""
    async with app.run_test() as pilot:
        pilot.app.selection = ["recyclarr", "jellyfin"]
        await pilot.app.push_screen(PathsScreen())
        await pilot.pause()
        assert await appuyer(
            pilot, "#next", lambda: isinstance(pilot.app.screen, SummaryScreen)
        )


@pytest.mark.asyncio
async def test_la_liste_complete_est_proposee_au_clic(app):
    """Le champ libre obligeait a connaitre le nom par coeur.

    Signale a l'usage : l'ecran affichait six noms sur vingt-deux, et il fallait
    taper le sien. La liste deroulante contient desormais tout le manifeste.
    """
    async with app.run_test() as pilot:
        screen = await _goto_templates(pilot, ["sonarr", "radarr", "recyclarr"])

        for sid, attendus in AVAILABLE.items():
            liste = screen.query_one(f"#tpl-{sid}", Select)
            proposes = [valeur for _libelle, valeur in liste._options]
            assert proposes == attendus, sid


@pytest.mark.asyncio
async def test_un_choix_se_fait_sans_clavier(app):
    """Tout doit etre atteignable a la souris : c'est la demande d'origine."""
    async with app.run_test() as pilot:
        screen = await _goto_templates(pilot, ["sonarr", "recyclarr"])
        liste = screen.query_one("#tpl-sonarr", Select)

        # Derouler puis choisir, comme un clic le ferait.
        liste.expanded = True
        await pilot.pause()
        liste.value = "web-2160p"
        await pilot.pause()

        assert screen.choices() == {"sonarr": "web-2160p"}
        assert screen.query_one("#next", Button).disabled is False
