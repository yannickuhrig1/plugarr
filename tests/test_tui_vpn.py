"""Tests de l'ecran VPN de l'assistant.

Signale a l'usage : « pourquoi tout n'est pas dans l'assistant ? ». Les sept
options `--vpn*` n'existaient qu'en ligne de commande, et le recapitulatif se
contentait d'AVERTIR qu'aucun VPN n'etait configure — sans offrir le moindre
moyen d'en mettre un.
"""

from __future__ import annotations

import pytest
from textual.widgets import Button, Input, RadioButton, Select, SelectionList, Static

from plugarr import vpnservers
from plugarr.models import VPN_PROVIDERS, VpnConfig
from plugarr.tui.app import PlugArrApp
from plugarr.tui.screens import PathsScreen, SummaryScreen, TemplatesScreen, VpnScreen


@pytest.fixture
def app(tmp_path):
    return PlugArrApp(project_dir=tmp_path)


async def _vpn(pilot, selection=("sonarr", "qbittorrent")) -> VpnScreen:
    pilot.app.selection = list(selection)
    pilot.app.push_screen(VpnScreen())
    await pilot.pause()
    return pilot.app.screen


# --------------------------------------------------------------- apparition


@pytest.mark.asyncio
async def test_l_ecran_apparait_avec_un_client_de_telechargement(app, appuyer):
    async with app.run_test() as pilot:
        pilot.app.selection = ["sonarr", "transmission"]
        pilot.app.push_screen(PathsScreen())
        await pilot.pause()
        assert await appuyer(pilot, "#next", lambda: isinstance(pilot.app.screen, VpnScreen))


@pytest.mark.asyncio
async def test_il_est_saute_sans_client_de_telechargement(app, appuyer):
    """Sans trafic BitTorrent, Gluetun ne protegerait rien."""
    async with app.run_test() as pilot:
        pilot.app.selection = ["sonarr", "jellyfin"]
        pilot.app.push_screen(PathsScreen())
        await pilot.pause()
        assert await appuyer(
            pilot, "#next", lambda: isinstance(pilot.app.screen, SummaryScreen)
        )


@pytest.mark.asyncio
async def test_les_profils_suivent_toujours_le_vpn(app, appuyer):
    async with app.run_test() as pilot:
        await _vpn(pilot, ("sonarr", "qbittorrent", "recyclarr"))
        assert await appuyer(
            pilot, "#next", lambda: isinstance(pilot.app.screen, TemplatesScreen)
        )


# ------------------------------------------------------------------- saisie


@pytest.mark.asyncio
async def test_sans_vpn_par_defaut(app):
    """Le VPN reste un choix : on ne l'impose pas, on le propose."""
    async with app.run_test() as pilot:
        screen = await _vpn(pilot)

        assert screen.vpn_voulu() is False
        assert screen.config().enabled is False
        assert screen.query_one("#next", Button).disabled is False


@pytest.mark.asyncio
async def test_tous_les_fournisseurs_sont_proposes(app):
    """Ils viennent de Gluetun lui-meme, pas d'une liste recopiee.

    `pia` est le seul absent : c'est l'alias de `private internet access`, et le
    proposer deux fois se lirait comme un bug. Il reste accepte en ligne de
    commande et dans un `stack.yml` ecrit a la main."""
    async with app.run_test() as pilot:
        screen = await _vpn(pilot)
        liste = screen.query_one("#vpn-provider", Select)

        proposes = [v for _l, v in liste._options]
        assert set(proposes) == set(VPN_PROVIDERS) - {"pia"}
        assert len(proposes) == len(set(proposes)), "un fournisseur apparait deux fois"


@pytest.mark.asyncio
async def test_les_fournisseurs_a_port_entrant_viennent_en_tete(app):
    """L'ordre EST une recommandation : le premier de la liste est celui qu'on
    choisit sans lire."""
    async with app.run_test() as pilot:
        screen = await _vpn(pilot)
        liste = screen.query_one("#vpn-provider", Select)

        valeurs = [v for _l, v in liste._options]
        avec_pf = [v for v in valeurs if vpnservers.port_forward(v)]
        assert valeurs[: len(avec_pf)] == avec_pf, "un fournisseur sans port entrant s'est glisse en tete"
        assert len(avec_pf) == 4, avec_pf


@pytest.mark.asyncio
async def test_le_libelle_dit_ce_qu_ils_apportent_en_plus(app):
    """Surtout pas « recommandes » : les autres protegent exactement autant, ils
    rendent seulement moins joignable."""
    async with app.run_test() as pilot:
        screen = await _vpn(pilot)
        libelles = {
            v: str(lib) for lib, v in screen.query_one("#vpn-provider", Select)._options
        }

        assert "connexions entrantes" in libelles["protonvpn"]
        assert "recommand" not in libelles["protonvpn"].lower()
        assert libelles["mullvad"] == "mullvad", "un fournisseur sans PF ne doit rien porter"


@pytest.mark.asyncio
async def test_le_defaut_accepte_les_connexions_entrantes(app):
    """Un defaut qui n'en accepterait pas priverait de port entrant la moitie des
    installations, sans que personne ne s'en apercoive."""
    async with app.run_test() as pilot:
        screen = await _vpn(pilot)

        defaut = screen.query_one("#vpn-provider", Select).value
        assert defaut == "protonvpn"
        assert vpnservers.port_forward(defaut)


@pytest.mark.asyncio
async def test_une_configuration_incomplete_bloque(app):
    """Gluetun refuse de demarrer s'il manque la cle, et le client de
    telechargement reste alors injoignable."""
    async with app.run_test() as pilot:
        screen = await _vpn(pilot)
        screen.query_one("#vpn-oui", RadioButton).value = True
        await pilot.pause()

        assert screen.query_one("#next", Button).disabled is True
        assert "manque" in str(screen.query_one("#vpn-status", Static).content)


@pytest.mark.asyncio
async def test_une_configuration_wireguard_complete_passe(app):
    async with app.run_test() as pilot:
        screen = await _vpn(pilot)
        screen.query_one("#vpn-oui", RadioButton).value = True
        await pilot.pause()
        screen.query_one("#vpn-provider", Select).value = "mullvad"
        screen.query_one("#vpn-key", Input).value = "cle-privee-wireguard"
        await pilot.pause()

        assert screen.query_one("#next", Button).disabled is False
        screen.query_one("#next", Button).press()
        await pilot.pause()

        vpn = pilot.app.vpn
        assert vpn.enabled and vpn.provider == "mullvad"
        assert vpn.wireguard_private_key == "cle-privee-wireguard"


@pytest.mark.asyncio
async def test_openvpn_demande_deux_champs_differents(app):
    """WireGuard veut une cle, OpenVPN un couple : les champs affiches changent."""
    async with app.run_test() as pilot:
        screen = await _vpn(pilot)
        screen.query_one("#vpn-oui", RadioButton).value = True
        await pilot.pause()
        screen.query_one("#vpn-type", Select).value = "openvpn"
        await pilot.pause()

        assert screen.query_one("#vpn-openvpn").has_class("hidden") is False
        assert screen.query_one("#vpn-wireguard").has_class("hidden") is True
        assert screen.query_one("#next", Button).disabled is True

        screen.query_one("#vpn-user", Input).value = "moi"
        screen.query_one("#vpn-pass", Input).value = "secret"
        await pilot.pause()

        assert screen.query_one("#next", Button).disabled is False


@pytest.mark.asyncio
async def test_le_choix_atteint_la_configuration(app):
    async with app.run_test() as pilot:
        screen = await _vpn(pilot)
        screen.query_one("#vpn-oui", RadioButton).value = True
        await pilot.pause()
        screen.query_one("#vpn-provider", Select).value = "protonvpn"
        screen.query_one("#vpn-key", Input).value = "ma-cle"
        # La liste est repeuplee par le changement de fournisseur : il faut
        # laisser passer l'evenement avant de pouvoir y choisir quoi que ce soit.
        await pilot.pause()
        screen.query_one("#vpn-lieux", SelectionList).select("Switzerland")
        await pilot.pause()
        screen.query_one("#next", Button).press()
        await pilot.pause()

        cfg = pilot.app.build_config()
        assert cfg.vpn.enabled and cfg.vpn.provider == "protonvpn"
        assert cfg.vpn.countries == "Switzerland"


# ------------------------------------------------- les lieux reellement offerts


@pytest.mark.asyncio
async def test_les_lieux_sans_port_entrant_ne_sont_pas_proposes(app):
    """Ce n'est pas du confort d'affichage : `VPN_PORT_FORWARDING=on` restreint
    la selection de Gluetun, qui refuse alors de DEMARRER s'il ne trouve aucun
    serveur — « no server found ... port forwarding only ». Chez PIA les 55
    regions ecartees sont les 55 regions des Etats-Unis : un utilisateur
    americain qui choisit son propre pays obtiendrait une pile morte."""
    async with app.run_test() as pilot:
        screen = await _vpn(pilot)
        screen.query_one("#vpn-oui", RadioButton).value = True
        await pilot.pause()
        screen.query_one("#vpn-provider", Select).value = "private internet access"
        await pilot.pause()

        proposes = {
            str(o.prompt) for o in screen.query_one("#vpn-lieux", SelectionList).options
        }

    offerts = set(vpnservers.pf_choices("private internet access"))
    tous = set(vpnservers.choices("private internet access"))
    assert offerts < tous, "le fournisseur d'essai doit reellement ecarter des lieux"
    assert proposes == offerts
    assert not (proposes & (tous - offerts)), "un lieu sans port entrant est propose"


@pytest.mark.asyncio
async def test_un_fournisseur_sans_port_entrant_garde_toute_sa_liste(app):
    """Le filtrage ne doit pas mordre ailleurs : sans `VPN_PORT_FORWARDING`,
    Gluetun accepte tous ses lieux et en masquer serait une perte seche."""
    async with app.run_test() as pilot:
        screen = await _vpn(pilot)
        screen.query_one("#vpn-oui", RadioButton).value = True
        await pilot.pause()
        screen.query_one("#vpn-provider", Select).value = "mullvad"
        await pilot.pause()

        proposes = {
            str(o.prompt) for o in screen.query_one("#vpn-lieux", SelectionList).options
        }

    assert vpnservers.port_forward("mullvad") is False
    assert proposes == set(vpnservers.choices("mullvad"))


# -------------------------------------------------------------------- l'hote


@pytest.mark.asyncio
async def test_l_hote_du_rapport_se_saisit_dans_l_assistant(app, appuyer):
    """Derniere option qui n'existait qu'en ligne de commande (`--host`).

    Sur un NAS pilote en SSH, `localhost` designe le NAS et non le poste qui
    lit le rapport : toutes les URL de la page finale seraient mortes.
    """
    async with app.run_test() as pilot:
        pilot.app.selection = ["sonarr"]
        pilot.app.push_screen(PathsScreen())
        await pilot.pause()
        screen = pilot.app.screen

        assert screen.query_one("#host", Input).value == "localhost"
        screen.query_one("#host", Input).value = "192.168.1.42"
        assert await appuyer(pilot, "#next", lambda: pilot.app.host == "192.168.1.42")

        assert pilot.app.build_config().host == "192.168.1.42"


@pytest.mark.asyncio
async def test_un_hote_vide_retombe_sur_localhost(app, appuyer):
    async with app.run_test() as pilot:
        pilot.app.selection = ["sonarr"]
        pilot.app.push_screen(PathsScreen())
        await pilot.pause()
        screen = pilot.app.screen
        screen.query_one("#host", Input).value = "   "
        assert await appuyer(pilot, "#next", lambda: pilot.app.host == "localhost")

        assert pilot.app.build_config().host == "localhost"


# ------------------------------------------------------------ recapitulatif


async def _recap(pilot, vpn: VpnConfig) -> SummaryScreen:
    pilot.app.selection = ["sonarr", "qbittorrent"]
    pilot.app.config_root, pilot.app.data_root = "/c", "/d"
    pilot.app.vpn = vpn
    pilot.app.push_screen(SummaryScreen())
    await pilot.pause()
    return pilot.app.screen


def _texte(screen: SummaryScreen) -> str:
    return " ".join(str(w.content) for w in screen.query(Static))


@pytest.mark.asyncio
async def test_sans_vpn_le_recapitulatif_avertit(app):
    async with app.run_test() as pilot:
        screen = await _recap(pilot, VpnConfig())

        assert "Aucun VPN" in _texte(screen)


@pytest.mark.asyncio
async def test_avec_un_vpn_le_recapitulatif_se_tait(app):
    """Il annoncait « aucun VPN » a qui venait d'en saisir un : l'avertissement
    ne regardait que la presence d'un client de telechargement."""
    async with app.run_test() as pilot:
        screen = await _recap(
            pilot,
            VpnConfig(enabled=True, provider="mullvad", wireguard_private_key="cle"),
        )

        assert "Aucun VPN" not in _texte(screen)


@pytest.mark.asyncio
async def test_le_recapitulatif_annonce_gluetun(app):
    """Gluetun n'est pas un service du catalogue : il n'apparait pas dans le
    tableau. Sans cette ligne, rien ne confirmerait le choix qui vient d'etre
    fait."""
    async with app.run_test() as pilot:
        screen = await _recap(
            pilot,
            VpnConfig(enabled=True, provider="mullvad", wireguard_private_key="cle"),
        )
        texte = _texte(screen)

        assert "gluetun" in texte and "mullvad" in texte
        assert "wireguard" in texte


@pytest.mark.asyncio
async def test_sans_vpn_le_recapitulatif_ne_parle_pas_de_gluetun(app):
    async with app.run_test() as pilot:
        screen = await _recap(pilot, VpnConfig())

        assert "gluetun" not in _texte(screen)


# ------------------------------------------------------- essai a la saisie


@pytest.mark.asyncio
async def test_l_essai_reclame_les_champs_manquants(app):
    async with app.run_test() as pilot:
        screen = await _vpn(pilot)
        screen.query_one("#vpn-oui", RadioButton).value = True
        await pilot.pause()

        screen.query_one("#vpn-essai", Button).press()
        await pilot.pause()

        assert "Completez" in str(screen.query_one("#vpn-status", Static).content)


@pytest.mark.asyncio
async def test_un_essai_rate_ne_bloque_pas_l_installation(app):
    """Une panne passagere chez le fournisseur ne doit pas empecher d'installer
    avec une configuration valide."""
    from plugarr.runner import Check

    async with app.run_test() as pilot:
        screen = await _vpn(pilot)
        screen.query_one("#vpn-oui", RadioButton).value = True
        screen.query_one("#vpn-key", Input).value = "une-cle"
        await pilot.pause()

        screen._essai_termine(Check("Essai VPN", False, "aucun tunnel etabli", blocking=False))
        await pilot.pause()

        assert screen.query_one("#next", Button).disabled is False
        assert "aucun tunnel" in str(screen.query_one("#vpn-status", Static).content)
        assert screen.query_one("#vpn-essai", Button).disabled is False


@pytest.mark.asyncio
async def test_un_essai_reussi_annonce_la_sortie(app):
    from plugarr.runner import Check

    async with app.run_test() as pilot:
        screen = await _vpn(pilot)
        screen._essai_termine(Check("Essai VPN", True, "tunnel etabli, sortie par Italy"))
        await pilot.pause()

        assert "Italy" in str(screen.query_one("#vpn-status", Static).content)
