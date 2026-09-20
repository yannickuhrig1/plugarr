"""Les champs doivent rester atteignables sur une fenetre normale.

Deux pannes signalees a l'usage, meme cause : du contenu plus haut que la
fenetre, et rien pour y acceder.

- l'ecran VPN reclamait la cle privee WireGuard alors que le champ pour la
  saisir etait ecrase hors de vue ;
- l'ecran des chemins coupait l'identifiant, le fuseau et l'adresse de la
  machine, sans defilement : il fallait agrandir la fenetre a la main.

Un `Vertical` vaut `height: 1fr` par defaut : sa hauteur vient de la place
disponible, pas de son contenu. Ces tests mesurent a des tailles reelles, pas
sur un terminal confortable.
"""

from __future__ import annotations

import pytest
from textual.widgets import Input, RadioButton, Select

from plugarr.tui.app import PlugArrApp
from plugarr.tui.screens import PathsScreen, VpnScreen

#: Hauteurs plausibles. 24 lignes est le minimum historique d'un terminal ;
#: la fenetre par defaut de Windows Terminal en fait 30.
HAUTEURS = [24, 30, 40]


def _app(tmp_path):
    app = PlugArrApp(project_dir=tmp_path)
    app.auto_open_page = False
    return app


@pytest.mark.parametrize("hauteur", HAUTEURS)
@pytest.mark.asyncio
async def test_le_champ_de_cle_vpn_a_une_hauteur_utilisable(tmp_path, hauteur):
    async with _app(tmp_path).run_test(size=(110, hauteur)) as pilot:
        pilot.app.selection = ["sonarr", "qbittorrent"]
        await pilot.app.push_screen(VpnScreen())
        await pilot.pause()
        screen = pilot.app.screen
        screen.query_one("#vpn-oui", RadioButton).value = True
        await pilot.pause()

        # 3 lignes : c'est la hauteur d'un Input avec sa bordure. En dessous,
        # le champ est ecrase et l'utilisateur ne peut pas le remplir.
        assert screen.query_one("#vpn-key", Input).region.height == 3
        assert screen.query_one("#vpn-wireguard").region.height >= 4


@pytest.mark.parametrize("hauteur", HAUTEURS)
@pytest.mark.asyncio
async def test_le_couple_openvpn_a_une_hauteur_utilisable(tmp_path, hauteur):
    async with _app(tmp_path).run_test(size=(110, hauteur)) as pilot:
        pilot.app.selection = ["sonarr", "qbittorrent"]
        await pilot.app.push_screen(VpnScreen())
        await pilot.pause()
        screen = pilot.app.screen
        screen.query_one("#vpn-oui", RadioButton).value = True
        await pilot.pause()
        screen.query_one("#vpn-type", Select).value = "openvpn"
        await pilot.pause()

        assert screen.query_one("#vpn-user", Input).region.height == 3
        assert screen.query_one("#vpn-pass", Input).region.height == 3


@pytest.mark.parametrize("hauteur", HAUTEURS)
@pytest.mark.asyncio
async def test_tous_les_champs_des_chemins_restent_atteignables(tmp_path, hauteur):
    """Le dernier champ ajoute est le plus expose : c'est celui qui sort."""
    async with _app(tmp_path).run_test(size=(110, hauteur)) as pilot:
        await pilot.app.push_screen(PathsScreen())
        await pilot.pause()
        screen = pilot.app.screen

        for ident in ("#config-root", "#data-root", "#username", "#tz", "#host"):
            assert screen.query_one(ident, Input).region.height == 3, ident


@pytest.mark.parametrize("hauteur", [24, 30])
@pytest.mark.asyncio
async def test_l_ecran_des_chemins_defile(tmp_path, hauteur):
    """Sans defilement, les champs du bas etaient simplement inaccessibles."""
    async with _app(tmp_path).run_test(size=(110, hauteur)) as pilot:
        await pilot.app.push_screen(PathsScreen())
        await pilot.pause()
        zone = pilot.app.screen.query_one("#paths")

        assert zone.allow_vertical_scroll
        assert zone.max_scroll_y > 0, "le contenu tiendrait dans la fenetre"
