"""Le filtre geographique du VPN : une liste cliquable, et la bonne variable.

Deux problemes traites ensemble.

**La saisie libre.** Une valeur inventee fait echouer Gluetun au demarrage, et
le client de telechargement — qui partage sa pile reseau — reste alors
injoignable sans que rien ne l'explique. Les valeurs proposees viennent donc de
l'IMAGE epinglee elle-meme.

**Tous les fournisseurs ne se filtrent pas par pays.** Cinq d'entre eux
n'exposent AUCUN pays dans les donnees de Gluetun v3.41.3 : Windscribe,
VyprVPN, Giganews et Private Internet Access classent par region, Perfect
Privacy par ville. Leur poser `SERVER_COUNTRIES` ne filtrait rien du tout.
"""

from __future__ import annotations

import json

import pytest
from textual.widgets import Label, RadioButton, Select, SelectionList

from plugarr import vpnservers
from plugarr.compose import GLUETUN_TAG
from plugarr.models import VPN_PROVIDERS, VpnConfig
from plugarr.tui.app import PlugArrApp
from plugarr.tui.screens import VpnScreen

# ------------------------------------------------------------------ donnees


def test_les_donnees_viennent_de_la_version_epinglee():
    """Le depot amont avance ; une valeur qu'il propose mais que la version
    deployee ignore serait refusee au demarrage."""
    assert vpnservers.gluetun_version() == GLUETUN_TAG


def test_chaque_fournisseur_reel_a_sa_liste():
    """`custom` excepte : l'utilisateur fournit ses propres serveurs."""
    for provider in VPN_PROVIDERS:
        if provider == "custom":
            continue
        assert vpnservers.choices(provider), provider


@pytest.mark.parametrize(
    ("provider", "attendu"),
    [
        ("mullvad", "SERVER_COUNTRIES"),
        ("nordvpn", "SERVER_COUNTRIES"),
        # Les cinq qui ne connaissent pas de pays.
        ("windscribe", "SERVER_REGIONS"),
        ("vyprvpn", "SERVER_REGIONS"),
        ("giganews", "SERVER_REGIONS"),
        ("private internet access", "SERVER_REGIONS"),
        ("perfect privacy", "SERVER_CITIES"),
    ],
)
def test_la_variable_suit_le_fournisseur(provider, attendu):
    assert vpnservers.filter_env(provider) == attendu


def test_pia_partage_la_liste_de_private_internet_access():
    """Gluetun accepte les deux noms : verifie contre l'image, `pia` demarre et
    tente de se connecter."""
    assert vpnservers.choices("pia") == vpnservers.choices("private internet access")
    assert vpnservers.filter_env("pia") == vpnservers.filter_env("private internet access")


def test_un_fournisseur_inconnu_reste_utilisable():
    """Une version plus recente de Gluetun peut en ajouter : la saisie doit
    passer telle quelle plutot que d'etre bloquee."""
    assert vpnservers.choices("nexistepas") == []
    assert vpnservers.filter_env("nexistepas") == "SERVER_COUNTRIES"


def test_le_fichier_est_lisible_et_complet():
    contenu = json.loads(vpnservers.DATA.read_text(encoding="utf-8"))
    for provider, entree in contenu["providers"].items():
        # `port_forward` et `pf_values` ne concernent que les fournisseurs a port
        # entrant, et `pf_values` n'est ecrit que s'il RESTREINT quelque chose :
        # le recopier a l'identique doublerait le fichier sans rien apprendre.
        assert set(entree) <= {"env", "values", "port_forward", "pf_values"}, provider
        assert {"env", "values"} <= set(entree), provider
        assert entree["env"].startswith("SERVER_"), provider
        if "pf_values" in entree:
            assert entree.get("port_forward"), provider
            assert set(entree["pf_values"]) < set(entree["values"]), provider


# ------------------------------------------------------------ configuration


@pytest.mark.parametrize(
    ("provider", "variable"),
    [
        ("mullvad", "SERVER_COUNTRIES"),
        ("windscribe", "SERVER_REGIONS"),
        ("perfect privacy", "SERVER_CITIES"),
    ],
)
def test_la_bonne_variable_atteint_gluetun(provider, variable):
    cfg = VpnConfig(
        enabled=True, provider=provider, wireguard_private_key="x", countries="Berlin"
    )
    env = cfg.environment("Etc/UTC")

    assert env[variable] == "Berlin"
    assert len([k for k in env if k.startswith("SERVER_")]) == 1


def test_sans_selection_aucune_variable_n_est_posee():
    """Sans filtre, le VPN choisit son serveur : c'est le comportement voulu."""
    cfg = VpnConfig(enabled=True, provider="mullvad", wireguard_private_key="x")

    assert not [k for k in cfg.environment("Etc/UTC") if k.startswith("SERVER_")]


# ------------------------------------------------------------------- ecran


async def _ecran(pilot) -> VpnScreen:
    pilot.app.selection = ["sonarr", "qbittorrent"]
    pilot.app.push_screen(VpnScreen())
    await pilot.pause()
    screen = pilot.app.screen
    screen.query_one("#vpn-oui", RadioButton).value = True
    await pilot.pause()
    return screen


@pytest.fixture
def app(tmp_path):
    application = PlugArrApp(project_dir=tmp_path)
    application.auto_open_page = False
    return application


@pytest.mark.asyncio
async def test_la_liste_suit_le_fournisseur_choisi(app):
    async with app.run_test(size=(110, 30)) as pilot:
        screen = await _ecran(pilot)
        liste = screen.query_one("#vpn-lieux", SelectionList)

        screen.query_one("#vpn-provider", Select).value = "mullvad"
        await pilot.pause()
        mullvad = [o.value for o in liste._options]

        screen.query_one("#vpn-provider", Select).value = "windscribe"
        await pilot.pause()
        windscribe = [o.value for o in liste._options]

        assert mullvad == vpnservers.choices("mullvad")
        assert windscribe == vpnservers.choices("windscribe")
        assert mullvad != windscribe


@pytest.mark.asyncio
async def test_le_libelle_dit_ce_qu_on_choisit(app):
    """Proposer « pays » a un fournisseur qui n'en connait aucun serait un
    filtre qui ne filtre rien."""
    async with app.run_test(size=(110, 30)) as pilot:
        screen = await _ecran(pilot)
        titre = screen.query_one("#vpn-lieux-titre", Label)

        for provider, mot in (
            ("mullvad", "Pays"),
            ("windscribe", "Regions"),
            ("perfect privacy", "Villes"),
        ):
            screen.query_one("#vpn-provider", Select).value = provider
            await pilot.pause()
            assert mot in str(titre.content), provider


@pytest.mark.asyncio
async def test_un_fournisseur_sans_liste_masque_le_choix(app):
    async with app.run_test(size=(110, 30)) as pilot:
        screen = await _ecran(pilot)
        screen.query_one("#vpn-provider", Select).value = "custom"
        await pilot.pause()

        assert screen.query_one("#vpn-lieux", SelectionList).display is False
        assert "propre configuration" in str(screen.query_one("#vpn-lieux-note").content)


@pytest.mark.asyncio
async def test_les_choix_cliques_atteignent_la_configuration(app):
    async with app.run_test(size=(110, 30)) as pilot:
        screen = await _ecran(pilot)
        screen.query_one("#vpn-provider", Select).value = "mullvad"
        await pilot.pause()
        liste = screen.query_one("#vpn-lieux", SelectionList)
        liste.select(liste._options[0].value)
        liste.select(liste._options[2].value)
        await pilot.pause()

        attendu = [vpnservers.choices("mullvad")[0], vpnservers.choices("mullvad")[2]]
        assert screen.config().countries == ",".join(attendu)


@pytest.mark.parametrize("hauteur", [24, 30, 40])
@pytest.mark.asyncio
async def test_la_liste_ne_chasse_pas_le_bouton(app, hauteur):
    """Deux cents entrees sans hauteur bornee feraient disparaitre Continuer."""
    async with app.run_test(size=(110, hauteur)) as pilot:
        screen = await _ecran(pilot)
        screen.query_one("#vpn-provider", Select).value = "hidemyass"  # 217 choix
        await pilot.pause()

        assert screen.query_one("#vpn-lieux", SelectionList).region.height <= 10
        assert screen.query_one("#next").region.height == 3
