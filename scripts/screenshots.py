"""Genere les captures SVG de l'assistant pour le README.

Tourne sans terminal et sans Docker : le harnais de test de Textual pilote
l'application en memoire et exporte chaque ecran en SVG.

    python scripts/screenshots.py

Deux jeux sont produits, un par langue : le francais dans `docs/screenshots/`,
l'anglais dans `docs/screenshots/en/`. Le site en a besoin des deux, et une
capture francaise sur une page anglaise annulerait le travail de traduction.

Les fichiers sont regeneres a l'identique a chaque execution ET sur n'importe
quelle machine, ce qui permet de les versionner et de voir les regressions
visuelles dans une pull request. La CI le verifie.

Sept sources de variation sont neutralisees ici, et il a fallu les trouver
une par une : le profil de plateforme propose (il suit la machine), les
identifiants Unix detectes, le diagnostic Docker (celui de la machine, absent
sur une CI), les secrets generes (tires au hasard a chaque execution), le
repertoire du projet (le chemin personnel de qui lance le script se retrouvait
dans une capture publiee), la liste des templates Recyclarr (elle vient du
depot amont et bouge sans nous) et les configurations deja presentes sur le
disque (le recapitulatif les lit pour avertir, et avertissait donc de ce qui
trainait sur la machine de l'auteur).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from textual.widgets import (
    Input,
    Label,
    ListItem,
    ListView,
    RadioButton,
    Select,
    SelectionList,
    Static,
)

from plugarr import i18n
from plugarr.clients.prowlarr import IndexerDefinition
from plugarr.i18n import t
from plugarr.tui.app import PlugArrApp
from plugarr.tui.indexers import IndexersScreen
from plugarr.tui.screens import (
    InstallScreen,
    PathsScreen,
    ReportScreen,
    ServicesScreen,
    SummaryScreen,
    TemplatesScreen,
    VpnScreen,
)
from plugarr.wiring import StepResult

OUT = ROOT / "docs" / "screenshots"
SIZE = (104, 34)

#: Ou vont les captures de chaque langue. Le francais reste a la racine : c'est
#: ce que le README cite depuis toujours, et deplacer ces fichiers casserait
#: chaque lien deja publie.
SORTIES = {"fr": OUT, "en": OUT / "en"}

#: Repertoire affiche dans les captures. Surtout PAS celui d'ou l'on lance le
#: script : le chemin personnel de l'auteur finirait dans une image publiee.
SHOWN_PROJECT_DIR = PurePosixPath("/opt/plugarr")

#: Secrets d'illustration. Les vrais sont tires au hasard a chaque execution :
#: sans cela, deux captures ne seraient jamais identiques.
SHOWN_API_KEY = "0123456789abcdef0123456789abcdef"
SHOWN_PASSWORD = "MotDePasseGenere42"

#: Fournisseur montre dans la capture VPN : le premier de la liste par ordre
#: alphabetique, choisi pour cette seule raison. plugarr n'en recommande aucun.
SHOWN_VPN_PROVIDER = "airvpn"
SHOWN_VPN_KEY = "cle-privee-wireguard"
#: Deux lieux coches, pour montrer que la liste se selectionne au clic.
SHOWN_VPN_LIEUX = ("Netherlands", "Switzerland")

#: Templates figes pour l'illustration. La liste reelle vient du depot Recyclarr
#: et change quand il en publie : une capture comparee a l'octet pres ne peut pas
#: en dependre. Les noms sont vrais, seul l'instantane est fige.
SHOWN_TEMPLATES = {
    "sonarr": [
        "french-multi-vf-bluray-web-1080p",
        "french-multi-vf-bluray-web-2160p",
        "french-multi-vo-bluray-web-1080p",
        "sonarr-german-hd-bluray-web",
        "web-1080p",
        "web-2160p",
        "web-simple-1080p",
    ],
    "radarr": [
        "french-multi-vf-hd-bluray-web",
        "french-multi-vf-uhd-bluray-web",
        "french-multi-vo-hd-bluray-web",
        "hd-bluray-web",
        "radarr-german-hd-bluray-web",
        "remux-web-1080p",
        "uhd-bluray-web",
    ],
}


#: Diagnostic Docker d'illustration. L'ecran d'accueil affiche celui de la
#: machine : sans cela, une machine sans Docker (une CI, par exemple) produit une
#: capture rouge, et le chemin du binaire trahit le systeme de l'auteur.
SHOWN_DOCKER = (
    ("docker", "trouve : {chemin}", {"chemin": "/usr/bin/docker"}),
    ("daemon docker", "version serveur {version}", {"version": "27.3.1"}),
    ("docker compose", "v2.29.7", {}),
)


def freeze_environment() -> None:
    """Rend la capture independante de la machine qui la produit."""
    from plugarr import orchestrator, runner, seed
    from plugarr.models import PlatformProfile
    from plugarr.tui import screens

    runner.check_docker = lambda: [  # type: ignore[assignment]
        runner.Check(t(nom), True, t(detail, **valeurs))
        for nom, detail, valeurs in SHOWN_DOCKER
    ]

    # Le NUMERO DE VERSION sort du bandeau des captures — et de la seulement.
    # Il reste affiche sur chaque ecran du produit, ou il a une vraie raison
    # d'etre : c'est la premiere chose a demander quand quelqu'un signale un
    # probleme. Mais dans une capture, il ne documente rien et coute cher : la
    # seule 0.7.2 faisait bouger 18 fichiers et 1609 lignes de SVG, sans qu'un
    # pixel d'interface ait change. La CI comparant les captures a celles du
    # depot, chaque version obligeait a les regenerer et a relire un diff
    # entierement faux.
    #
    # On ne le remplace par aucune valeur : ecrire « 0.0.0 » serait montrer une
    # version qui n'existe pas, et une capture ne doit pas mentir sur le
    # produit. Les captures ne bougent donc plus que lorsque l'INTERFACE bouge,
    # ce qui est exactement ce qu'elles sont censees documenter.
    screens.WizardHeader.__init__ = (  # type: ignore[method-assign]
        lambda self, subtitle: Static.__init__(
            self, f"plugarr  —  {subtitle}", id="wizard-header"
        )
    )

    # Le profil propose suit desormais la machine : sans le figer, la capture de
    # l'ecran des chemins montre « windows » ici et « generic-linux » sur la CI.
    # Le depot documente une installation Linux, c'est donc celle-la qu'on montre.
    screens.default_profile = lambda: PlatformProfile.GENERIC_LINUX  # type: ignore[assignment]

    # La meme phrase que produit `resolve_ids` en vrai sur un Linux : une
    # capture qui montre autre chose que le produit ment sur le produit.
    fixed_ids = (1000, 1000, t("detecte ({origine})", origine=t("utilisateur courant")), True)
    orchestrator.resolve_ids = lambda profile: fixed_ids  # type: ignore[assignment]
    screens.resolve_ids = lambda profile: fixed_ids  # type: ignore[assignment]
    seed.generate_api_key = lambda: SHOWN_API_KEY  # type: ignore[assignment]
    seed.generate_password = lambda *a, **kw: SHOWN_PASSWORD  # type: ignore[assignment]
    screens.recyclarr_cfg.available_templates = (  # type: ignore[assignment]
        lambda config_dir=None, **kw: (dict(SHOWN_TEMPLATES), None)
    )

    # Le recapitulatif LIT LE DISQUE pour avertir d'une configuration heritee.
    # La capture dependait donc du contenu de /opt/plugarr/config sur la machine
    # qui la produit : ici un avertissement qBittorrent laisse par un essai
    # precedent, sur la CI rien du tout. On montre le cas nominal, une machine
    # vierge — c'est celui que decrit le depot.
    screens.orchestrator.unusable_configs = lambda cfg: []  # type: ignore[assignment]

    # L'assistant CHERCHE une installation precedente, dans le repertoire de
    # lancement ET dans le registre de l'utilisateur. La capture dependait donc
    # des piles reellement installees sur la machine qui la produit, et la
    # difference n'etait pas cosmetique :
    #
    # - le recapitulatif affichait « Une installation precedente a ete retrouvee
    #   dans C:\\Users\\...\\Downloads », chemin local parti dans un SVG publie ;
    # - la reprise reprend le FUSEAU HORAIRE de cette installation, ce qui
    #   changeait une deuxieme ligne de la capture pour la meme cause.
    #
    # La CI, elle, tourne sur une machine vierge : les captures ne pouvaient donc
    # PAS coincider, et le controle « les captures sont a jour » echouait sans
    # qu'aucun pixel d'interface ait bouge. On montre le cas nominal, comme pour
    # `unusable_configs` juste au-dessus.
    from plugarr.tui import app as tui_app

    tui_app.reprise.trouver = lambda project_dir, config_root: None  # type: ignore[assignment]


def fake_steps() -> list[StepResult]:
    """Resultats fictifs pour illustrer le rapport sans rien demarrer.

    Construits a l'APPEL et non a l'import : leurs details passent par le
    catalogue, et les figer ici les gelerait dans la langue chargee au
    chargement du module.
    """
    cree = t("cree")
    return [
        StepResult("sonarr: dossier racine /data/media/tv", True, cree, created=True),
        StepResult("radarr: dossier racine /data/media/movies", True, cree, created=True),
        StepResult(
            "qbittorrent: categories avec chemin de sauvegarde",
            True,
            t("creees : {noms}", noms="tv, movies"),
        ),
        StepResult("sonarr: client de telechargement qBittorrent", True, f"{cree} (id=1), test OK"),
        StepResult("radarr: client de telechargement qBittorrent", True, f"{cree} (id=1), test OK"),
        StepResult("prowlarr -> sonarr (Application, fullSync)", True, f"{cree} (id=1), test OK"),
        StepResult("prowlarr -> radarr (Application, fullSync)", True, f"{cree} (id=2), test OK"),
        StepResult(
            "jellyfin: assistant + bibliotheques", True, f"{t('Films')}, {t('Series')}"
        ),
    ]


#: Definition fictive : plugarr ne nomme et ne recommande aucun indexeur reel.
def fake_definition() -> IndexerDefinition:
    return IndexerDefinition(
        name=t("Votre indexeur"),
        implementation="Torznab",
        privacy="private",
        protocol="torrent",
        language="fr-FR",
        description=t(
            "La liste vient de votre Prowlarr. plugarr n'en fournit aucun."
        ),
        raw={
            "indexerUrls": ["https://exemple.invalid/"],
            "fields": [
                {"name": "baseUrl", "type": "select", "label": "Url", "value": None},
                {
                    "name": "apiKey",
                    "type": "textbox",
                    "label": "API Key",
                    "privacy": "apiKey",
                },
            ],
        },
    )


async def capture(langue: str) -> None:
    i18n.utiliser(langue)
    sortie = SORTIES[langue]
    sortie.mkdir(parents=True, exist_ok=True)
    freeze_environment()
    etapes = fake_steps()
    definition = fake_definition()

    async def shot(app: PlugArrApp, pilot, name: str) -> None:
        # Le `Footer` monte ses raccourcis de facon asynchrone. Attendre que ses
        # ENFANTS existent ne suffit pas : le premier apparait avant que le texte
        # ne soit rendu, et la capture partait parfois sans pied de page. On
        # attend donc ce qu'on va reellement ecrire, en cherchant le raccourci
        # « palette » que toutes les fenetres affichent.
        contenu = app.export_screenshot()
        for _ in range(40):
            if "palette" in contenu:
                break
            await pilot.pause()
            contenu = app.export_screenshot()
        path = sortie / f"{name}.svg"
        # newline="" : sans cela Python traduit les sauts de ligne en CRLF sous
        # Windows. Git le rattrape a la normalisation, mais un depot configure
        # autrement verrait le controle de la CI echouer sans rien de reel.
        with path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(contenu)
        print(f"  {path.relative_to(ROOT)}")

    app = PlugArrApp(project_dir=SHOWN_PROJECT_DIR)
    app.auto_open_page = False
    async with app.run_test(size=SIZE) as pilot:
        await pilot.pause()
        await shot(app, pilot, "1-accueil")

        app.push_screen(ServicesScreen())
        await pilot.pause()
        await shot(app, pilot, "2-services")

        app.selection = ["prowlarr", "sonarr", "radarr", "qbittorrent", "jellyfin"]
        app.push_screen(PathsScreen())
        await pilot.pause()
        await shot(app, pilot, "3-chemins")

        app.data_root, app.config_root = "/srv/data", "/opt/plugarr/config"
        app.push_screen(VpnScreen())
        await pilot.pause()
        screen = app.screen
        screen.query_one("#vpn-oui", RadioButton).value = True
        await pilot.pause()
        screen.query_one("#vpn-provider", Select).value = SHOWN_VPN_PROVIDER
        screen.query_one("#vpn-key", Input).value = SHOWN_VPN_KEY
        # La liste des lieux est repeuplee par le changement de fournisseur.
        await pilot.pause()
        liste = screen.query_one("#vpn-lieux", SelectionList)
        for lieu in SHOWN_VPN_LIEUX:
            liste.select(lieu)
        # L'ecran defile : sans cela la capture montrerait la liste coupee a sa
        # premiere ligne, c'est-a-dire une boite vide.
        liste.scroll_visible(animate=False)
        for _ in range(4):
            await pilot.pause()
        await shot(app, pilot, "4-vpn")
        # Ce que fait le bouton « Continuer ». Sans cela le recapitulatif suivant
        # avertirait qu'aucun VPN n'est configure, juste apres une capture qui en
        # montre un rempli.
        app.vpn = screen.config()

        app.selection = [*app.selection, "recyclarr"]
        app.push_screen(TemplatesScreen())
        # La liste des templates arrive d'un worker : capturer trop tot montrerait
        # « Chargement… » au lieu de l'ecran reel.
        for _ in range(40):
            await pilot.pause(0.25)
            if str(app.screen.query_one("#tpl-choices-sonarr", Static).content):
                break
        await shot(app, pilot, "5-profils")

        app.push_screen(SummaryScreen())
        await pilot.pause()
        await shot(app, pilot, "6-recapitulatif")

        # L'ecran d'installation lance un worker : on le rend inerte pour la
        # capture, puis on injecte des lignes representatives.
        InstallScreen.run_install = lambda self: None  # type: ignore[method-assign]
        app.stack_config = app.build_config()
        app.push_screen(InstallScreen())
        await pilot.pause()
        screen = app.screen
        # Une barre sans total s'affiche en mode INDETERMINE, c'est-a-dire animee :
        # deux captures ne coincideraient jamais. Lui donner un total la fige, et
        # montre au passage ce que l'utilisateur voit vraiment.
        screen._set_total(len(etapes))
        for _ in etapes:
            screen._advance()
        screen._phase(
            t(
                "[green]Termine : {faits}/{total} liens etablis[/green]",
                faits=len(etapes),
                total=len(etapes),
            )
        )
        for step in etapes:
            screen._log(f"  [green]OK[/green]  {step.name} - {step.detail}")
        await pilot.pause()
        await shot(app, pilot, "7-installation")

        # Etape indexeurs : rendue hors ligne. Le chargement des definitions est
        # neutralise, on injecte des exemples representatifs de ce que Prowlarr
        # renvoie. Aucun indexeur reel n'est nomme : plugarr n'en recommande aucun.
        IndexersScreen.load_definitions = lambda self: None  # type: ignore[method-assign]
        app.push_screen(IndexersScreen())
        await pilot.pause()
        screen = app.screen
        screen._set_status(
            t("[dim]{nombre} definitions fournies par votre Prowlarr{deja}[/dim]",
              nombre=626, deja="")
        )
        screen._matches = [definition]
        results = screen.query_one("#indexer-results", ListView)
        results.append(
            ListItem(Label(f"{definition.name}  [dim]{t('prive')} - torrent[/dim]"))
        )
        await screen._render_form(definition)
        # mount() est asynchrone : sans ces passes, la capture part avant que les
        # champs du formulaire soient rendus.
        for _ in range(4):
            await pilot.pause()
        await shot(app, pilot, "8-indexeurs")

        app.results = etapes
        app.push_screen(ReportScreen())
        await pilot.pause()
        await shot(app, pilot, "9-rapport")


if __name__ == "__main__":
    for code in SORTIES:
        print(f"Generation des captures ({code}) :")
        asyncio.run(capture(code))
