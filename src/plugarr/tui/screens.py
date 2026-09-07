"""Ecrans de l'assistant.

Aucune logique metier ici : chaque ecran lit le catalogue et appelle
orchestrator.py. Un service ajoute au catalogue apparait automatiquement dans la
selection, sans toucher a ce fichier.
"""

from __future__ import annotations

from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Footer,
    ProgressBar,
    RadioSet,
    RichLog,
    Rule,
    Select,
    SelectionList,
)

from .. import catalog, i18n, journal, langues, orchestrator, vpnservers
from ..clients import recyclarr as recyclarr_cfg
from ..i18n import t
from ..layout import (
    PROFILE_DEFAULTS,
    default_profile,
    hardlink_supported,
    path_warning,
    resolve_ids,
)
from ..models import VPN_PROVIDERS, Category, PlatformProfile, VpnConfig
from ..orchestrator import InstallAborted, Progress
from ..wiring import StepResult

# Memes widgets que ceux de Textual, mais ils font passer leur libelle par le
# catalogue de traduction. Les ecrans ecrivent leurs phrases en francais, en
# clair, et n'ont rien a envelopper.
from .widgets import (
    Button,
    Checkbox,
    DataTable,
    Input,
    Label,
    RadioButton,
    Static,
)

CATEGORY_TITLES = {
    Category.ARR: "Mediatheque",
    Category.DOWNLOAD: "Telechargement",
    Category.MEDIA: "Serveur media",
    Category.UI: "Interfaces",
}


class WizardHeader(Static):
    """Bandeau de titre maison.

    Le `Header` de Textual monte ses enfants de facon asynchrone et met a jour son
    titre depuis l'application : enchainer deux `push_screen` rapidement le fait
    lever `NoMatches: No nodes match 'HeaderTitle'`. Un simple Static rend la meme
    chose sans course, et sans dependre d'un detail interne du framework.
    """

    def __init__(self, subtitle: str) -> None:
        # La version est affichee sur CHAQUE ecran : c'est la premiere chose a
        # demander quand quelqu'un signale un probleme, et la derniere qu'il
        # pense a donner.
        from .. import __version__

        super().__init__(f"plugarr {__version__}  —  {subtitle}", id="wizard-header")


class WizardScreen(Screen):
    """Socle commun : entete, pied de page, navigation."""

    BINDINGS = [("escape", "app.pop_screen", "Retour"), ("ctrl+q", "app.quit", "Quitter")]

    #: Sous-titre affiche dans le bandeau. C'est une CLE de traduction :
    #: le libelle francais sert d'index, et `compose` le traduit.
    SUB_TITLE = ""

    def __init__(self, *args: object, **kw: object) -> None:
        # Les raccourcis du pied de page sont declares au niveau de la
        # classe, donc lus a l'import, avant que la langue soit connue. On
        # les traduit sur l'INSTANCE, que Textual consulte en priorite.
        self.BINDINGS = [
            (touche, action, t(libelle))
            for touche, action, libelle in type(self).BINDINGS
        ]
        super().__init__(*args, **kw)

    def compose(self) -> ComposeResult:
        yield WizardHeader(t(self.SUB_TITLE))
        yield from self.content()
        yield Footer()

    def content(self) -> ComposeResult:  # pragma: no cover - surcharge
        return iter(())


# --------------------------------------------------------------------- accueil


class WelcomeScreen(WizardScreen):
    SUB_TITLE = "Deploie ET cable une stack media complete"

    def content(self) -> ComposeResult:
        with Vertical(id="welcome"):
            yield Static(
                t(
                    "Cet assistant va deployer les services que vous choisissez, "
                    "puis [b]les cabler entre eux[/b] : cles API echangees, "
                    "indexeurs synchronises, dossiers racine crees, "
                    "bibliotheques scannees.\n\n"
                    "Rien n'est ecrit avant l'ecran de recapitulatif."
                ),
                id="pitch",
            )
            yield Rule()
            # La langue de PlugArr se choisit AVANT tout le reste : c'est la
            # premiere chose que quelqu'un qui ne lit pas le francais doit
            # pouvoir faire. L'enterrer dans un ecran de reglages trois etapes
            # plus loin reviendrait a la reserver a ceux qui lisent deja.
            yield Label("Langue de PlugArr", classes="group-title")
            # `Select` attend (libelle, valeur), dans cet ordre. Passer la
            # paire telle qu'elle est declaree faisait du NOM la valeur, et le
            # code « fr » devenait alors illegal : l'assistant mourait au
            # montage de l'ecran d'accueil.
            yield Select(
                [(nom, code) for code, nom in i18n.DISPONIBLES],
                value=i18n.langue(),
                allow_blank=False,
                id="ui-langue",
            )
            yield Rule()
            yield Static(id="docker-status")
            yield Horizontal(
                Button("Commencer", variant="primary", id="start", disabled=True),
                Button("Sauvegarder", id="sauvegarder", disabled=True),
                Button("Restaurer une sauvegarde", id="restaurer", disabled=True),
                Button("Quitter", id="quit"),
                classes="actions",
            )

    @on(Select.Changed, "#ui-langue")
    def _changer_langue(self, event: Select.Changed) -> None:
        """Rebascule l'assistant sans le redemarrer.

        Textual ne re-compose pas un ecran deja monte : on le remplace par
        un neuf. C'est aussi ce qui fait suivre le bandeau et le pied de
        page, construits au montage.
        """
        if not isinstance(event.value, str) or event.value == i18n.langue():
            return
        i18n.utiliser(event.value)
        self.app.ui_language = event.value
        self.app.pop_screen()
        self.app.push_screen(WelcomeScreen())

    def on_mount(self) -> None:
        self.check_docker()

    @work(thread=True)
    def check_docker(self) -> None:
        from ..runner import check_docker

        try:
            checks = check_docker()
        except Exception as exc:  # noqa: BLE001
            journal.LOGGER.exception("diagnostic docker")
            self.app.call_from_thread(
                self._render_docker,
                f"[red]{t('Diagnostic impossible')} : {exc}[/red]",
                False,
            )
            return
        lines, ok = [], True
        for check in checks:
            mark = "[green]OK[/green]" if check.ok else f"[red]{t('ECHEC')}[/red]"
            lines.append(f"{mark}  {check.name} : {check.detail}")
            ok = ok and check.ok
        self.app.call_from_thread(self._render_docker, "\n".join(lines), ok)

    def _render_docker(self, text: str, ok: bool) -> None:
        self.query_one("#docker-status", Static).update(text)
        self.query_one("#start", Button).disabled = not ok
        self.query_one("#restaurer", Button).disabled = not ok
        self.query_one("#sauvegarder", Button).disabled = not ok

    @on(Button.Pressed, "#start")
    def go(self) -> None:
        self.app.push_screen(ServicesScreen())

    @on(Button.Pressed, "#restaurer")
    def restaurer(self) -> None:
        self.app.push_screen(RestaurationScreen())

    @on(Button.Pressed, "#sauvegarder")
    def sauvegarder(self) -> None:
        self.app.push_screen(SauvegardeScreen())

    @on(Button.Pressed, "#quit")
    def leave(self) -> None:
        self.app.exit(0)


class RestaurationScreen(WizardScreen):
    """Repose une sauvegarde, depuis l'assistant.

    Signale a l'usage : « pourquoi ne pas mettre un bouton restauration avec
    charger le fichier de sauvegarde ? Ce serait pratique pour restaurer apres
    un formatage ou changement de setup. »

    L'objection etait juste et ma premiere reponse mauvaise. La restauration ne
    peut PAS vivre sur la console d'administration : celle-ci commence par lire
    un `stack.yml`, et sur une machine fraichement formatee il n'y en a pas —
    c'est justement ce que l'archive contient. Le bouton aurait ete inutilisable
    dans le seul cas ou il sert.

    L'assistant, lui, demarre sans rien : c'est ici que la restauration
    appartient, et nulle part ailleurs.
    """

    SUB_TITLE = "Restaurer une installation sauvegardee"

    def content(self) -> ComposeResult:
        with Vertical(id="restauration"):
            yield Static(
                "Reposez une archive produite par [b]plugarr backup[/b] ou par le "
                "bouton [b]Sauvegarder la configuration[/b] de la page "
                "d'administration.\n\n"
                "Elle contient vos services, vos identifiants et tout ce que vous "
                "aviez saisi : indexeurs, profils, bibliotheques. "
                "[b]Vos medias ne sont pas dedans[/b] et ne seront pas touches.",
                id="pitch",
            )
            yield Rule()
            yield Label("Fichier de sauvegarde (.zip)", classes="group-title")
            yield Input(placeholder="C:/sauvegardes/plugarr-....zip", id="archive")
            yield Label(
                "Ou reposer la configuration [dim](vide = l'emplacement d'origine)[/dim]",
                classes="group-title",
            )
            yield Input(id="cible")
            yield Rule()
            yield Static(id="restauration-etat")
            yield Horizontal(
                Button("Examiner l'archive", id="examiner"),
                Button("Restaurer", variant="primary", id="poser", disabled=True),
                Button("Retour", id="retour"),
                classes="actions",
            )

    @on(Button.Pressed, "#examiner")
    def examiner(self) -> None:
        """Montre ce que l'archive contient AVANT d'ecraser quoi que ce soit.

        C'est ce qui remplace la confirmation en ligne de commande : on ne
        restaure pas a l'aveugle, et le bouton reste inerte tant que l'archive
        n'a pas ete lue.
        """
        from .. import sauvegarde

        etat = self.query_one("#restauration-etat", Static)
        chemin = Path(self.query_one("#archive", Input).value.strip().strip('"'))
        if not chemin.is_file():
            etat.update(f"[red]{chemin} introuvable.[/red]")
            return
        try:
            manifeste = sauvegarde.lire_manifeste(chemin)
        except (ValueError, OSError) as exc:
            etat.update(f"[red]{exc}[/red]")
            return

        lignes = [
            f"[b]Date[/b] : {manifeste['date']}",
            f"[b]Pile[/b] : {manifeste['project_name']}",
            f"[b]Services[/b] : {', '.join(manifeste['services'])}",
            f"[b]Volumes[/b] : {', '.join(manifeste['volumes']) or 'aucun'}",
            f"[b]Configuration d'origine[/b] : {manifeste['config_root']}",
        ]
        if manifeste.get("a_chaud"):
            lignes.append(
                t(
                    "[yellow]Prise A CHAUD, conteneurs en marche : ses bases "
                    "peuvent etre corrompues.[/yellow]"
                )
            )
        etat.update("\n".join(lignes))
        self.query_one("#poser", Button).disabled = False

    @on(Button.Pressed, "#poser")
    def poser(self) -> None:
        self._restaurer()

    @work(thread=True)
    def _restaurer(self) -> None:
        from .. import sauvegarde

        etat = self.query_one("#restauration-etat", Static)
        chemin = Path(self.query_one("#archive", Input).value.strip().strip('"'))
        ailleurs = self.query_one("#cible", Input).value.strip() or None
        self.app.call_from_thread(etat.update, "Restauration en cours...")
        try:
            manifeste = sauvegarde.restaurer(
                chemin, self.app.project_dir or Path("."), config_root=ailleurs
            )
        except Exception as exc:  # noqa: BLE001
            journal.LOGGER.exception("restauration")
            self.app.call_from_thread(etat.update, f"[red]{type(exc).__name__} : {exc}[/red]")
            return
        self.app.call_from_thread(
            etat.update,
            t(
                "[green]Restauration terminee.[/green]\n\n"
                "{nombre} services reposes. Demarrez la pile, puis "
                "[b]plugarr wire[/b] pour verifier que tout repond.",
                nombre=len(manifeste["services"]),
            ),
        )

    @on(Button.Pressed, "#retour")
    def retour(self) -> None:
        self.app.pop_screen()


class SauvegardeScreen(WizardScreen):
    """Archive une installation existante, depuis l'assistant.

    L'assistant savait RESTAURER et pas sauvegarder. La dissymetrie est
    couteuse : la sauvegarde ne vivait que dans `plugarr backup` et dans la
    console d'administration, c'est-a-dire dans deux endroits qu'un utilisateur
    qui double-clique un executable n'ouvre jamais. Il n'avait donc de
    sauvegarde que s'il en avait deja une — exactement au moment ou il n'en a
    pas.

    Le moment compte aussi. C'est ICI, avant de relancer une installation par
    dessus une autre, qu'une archive a le plus de valeur : elle porte les
    indexeurs, les profils et les mots de passe que l'installation qui va
    suivre pourrait perdre.

    L'installation a archiver est cherchee comme partout ailleurs : le
    repertoire courant d'abord, le registre des installations ensuite. Sur une
    machine ou PlugArr a deja tourne, il n'y a donc rien a saisir.
    """

    SUB_TITLE = "Sauvegarder une installation existante"

    #: L'installation retenue. Poses par `_charger`, declares ici pour qu'un
    #: clic sur « Sauvegarder » avant le montage ne leve pas d'AttributeError.
    _cfg = None
    _project_dir = None

    def content(self) -> ComposeResult:
        # `VerticalScroll` et non `Vertical` : cet ecran porte deux champs, une
        # case a cocher et son avertissement. Sur un terminal de 24 lignes, une
        # colonne fixe couperait le bouton — c'est-a-dire tout l'ecran.
        with VerticalScroll(id="sauvegarde"):
            yield Static(
                "Une archive contient votre [b]stack.yml[/b], la configuration de "
                "chaque service et les volumes Docker : indexeurs, profils, "
                "bibliotheques, mots de passe.\n\n"
                "[b]Vos medias n'y sont pas[/b] : ils pesent des teraoctets et ne "
                "sont pas une configuration.",
                id="pitch",
            )
            yield Rule()
            yield Label("Installation a sauvegarder", classes="group-title")
            yield Input(placeholder="C:/plugarr", id="source")
            yield Static(id="sauvegarde-source")
            yield Label("Fichier d'archive a ecrire (.zip)", classes="group-title")
            yield Input(placeholder="C:/sauvegardes/plugarr-....zip", id="destination")
            yield Checkbox(
                "Sauvegarder a chaud, sans arreter les conteneurs",
                value=False,
                id="a-chaud",
            )
            yield Static(
                "[dim]Une base SQLite copiee pendant qu'on ecrit dedans donne un "
                "fichier valide en apparence et inutilisable en pratique. Sans "
                "cette case, PlugArr arrete les conteneurs le temps de la copie "
                "puis les redemarre.[/dim]",
                id="sauvegarde-avertissement",
            )
            yield Rule()
            yield Static(id="sauvegarde-etat")
            yield Horizontal(
                Button("Sauvegarder", variant="primary", id="lancer"),
                Button("Retour", id="retour"),
                classes="actions",
            )

    def on_mount(self) -> None:
        self._charger(Path(self.app.project_dir or "."))

    def _charger(self, depart: Path) -> None:
        """Trouve l'installation, remplit les champs, ou dit ce qui manque."""
        from .. import reprise, sauvegarde

        etat = self.query_one("#sauvegarde-source", Static)
        self._cfg = None
        self._project_dir = None
        try:
            trouvee = reprise.trouver(depart)
        except Exception as exc:  # noqa: BLE001 - version future, fichier illisible
            etat.update(f"[red]{exc}[/red]")
            self.query_one("#lancer", Button).disabled = True
            return
        if trouvee is None:
            etat.update(
                t(
                    "[yellow]Aucune installation trouvee.[/yellow]\n[dim]Indiquez "
                    "ci-dessus le dossier qui contient stack.yml, puis validez avec "
                    "Entree.[/dim]"
                )
            )
            self.query_one("#lancer", Button).disabled = True
            return

        self._cfg = trouvee.cfg
        self._project_dir = trouvee.project_dir
        self.query_one("#source", Input).value = str(trouvee.project_dir)
        self.query_one("#destination", Input).value = str(
            trouvee.project_dir / sauvegarde.nom_par_defaut(trouvee.cfg)
        )
        etat.update(
            t(
                "[dim]stack.yml : {stack}\nConfigurations : {config}\n"
                "Services : {services}[/dim]",
                stack=trouvee.chemin,
                config=trouvee.cfg.config_root,
                services=", ".join(sorted(trouvee.cfg.services)),
            )
        )
        self.query_one("#lancer", Button).disabled = False

    @on(Input.Submitted, "#source")
    def _changer_source(self, event: Input.Submitted) -> None:
        """Un dossier saisi a la main prime sur celui qui a ete devine."""
        self._charger(Path(event.value.strip().strip('"') or "."))

    @on(Button.Pressed, "#lancer")
    def lancer(self) -> None:
        self._sauvegarder()

    @work(thread=True)
    def _sauvegarder(self) -> None:
        from .. import sauvegarde

        etat = self.query_one("#sauvegarde-etat", Static)
        bouton = self.query_one("#lancer", Button)
        if self._cfg is None or self._project_dir is None:
            return
        destination = Path(self.query_one("#destination", Input).value.strip().strip('"'))
        a_chaud = self.query_one("#a-chaud", Checkbox).value

        self.app.call_from_thread(setattr, bouton, "disabled", True)
        self.app.call_from_thread(
            etat.update,
            t("Sauvegarde en cours. Ne fermez pas cette fenetre."),
        )
        try:
            rapport = sauvegarde.sauvegarder(
                self._cfg,
                self._project_dir,
                destination,
                live=a_chaud,
                on_progress=lambda message: self.app.call_from_thread(
                    etat.update, f"[dim]{message}[/dim]"
                ),
            )
        except Exception as exc:  # noqa: BLE001
            journal.LOGGER.exception("sauvegarde")
            self.app.call_from_thread(
                etat.update, f"[red]{type(exc).__name__} : {exc}[/red]"
            )
            self.app.call_from_thread(setattr, bouton, "disabled", False)
            return

        self.app.call_from_thread(setattr, bouton, "disabled", False)
        self.app.call_from_thread(
            etat.update,
            t(
                "[green]Sauvegarde terminee.[/green]\n\n{archive}\n"
                "{taille} Mo, {fichiers} fichiers, volumes : {volumes}",
                archive=rapport.archive,
                taille=rapport.mega,
                fichiers=rapport.fichiers,
                volumes=", ".join(rapport.volumes) or t("aucun"),
            ),
        )

    @on(Button.Pressed, "#retour")
    def retour(self) -> None:
        self.app.pop_screen()

# ------------------------------------------------------------------- selection


class ServicesScreen(WizardScreen):
    SUB_TITLE = "Etape 1/3 - Quels services installer ?"

    #: Repartition en deux colonnes. La mediatheque, la plus fournie, occupe la
    #: gauche a elle seule.
    COLUMNS = ((Category.ARR,), (Category.DOWNLOAD, Category.MEDIA, Category.UI))

    def content(self) -> ComposeResult:
        with Horizontal(id="services"):
            for index, categories in enumerate(self.COLUMNS):
                with VerticalScroll(classes="service-column", id=f"column-{index}"):
                    for category in categories:
                        specs = [s for s in catalog.selectable() if s.category is category]
                        if not specs:
                            continue
                        yield Label(CATEGORY_TITLES[category], classes="group-title")
                        for spec in sorted(specs, key=lambda s: s.display_name):
                            yield Checkbox(
                                spec.display_name,
                                value=spec.id in catalog.DEFAULT_SELECTION,
                                id=f"svc-{spec.id}",
                                classes="service",
                            )
                            yield Label(spec.notes, classes="service-note")
        yield Static(id="selection-summary")
        yield Horizontal(
            Button("Continuer", variant="primary", id="next"),
            Button("Retour", id="back"),
            classes="actions",
        )

    def on_mount(self) -> None:
        self._refresh_summary()

    @on(Checkbox.Changed)
    def _on_toggle(self) -> None:
        self._refresh_summary()

    def selection(self) -> list[str]:
        return [
            box.id.removeprefix("svc-")
            for box in self.query(Checkbox)
            if box.value and box.id is not None
        ]

    def _refresh_summary(self) -> None:
        chosen = self.selection()
        summary = self.query_one("#selection-summary", Static)
        if not chosen:
            summary.update("[yellow]Selectionnez au moins un service.[/yellow]")
            self.query_one("#next", Button).disabled = True
            return

        resolved = catalog.resolve_dependencies(chosen)
        added = [s for s in resolved if s not in chosen]
        cfg = orchestrator.build_config(services=resolved)
        text = t(
            "[b]{services} services[/b] - [b]{liens} liens[/b] seront cables",
            services=len(resolved),
            liens=orchestrator.planned_links(cfg),
        )
        if added:
            names = ", ".join(catalog.get(s).display_name for s in added)
            text += t(
                "\n[cyan]Ajoute automatiquement (prerequis) : {noms}[/cyan]",
                noms=names,
            )
        summary.update(text)
        self.query_one("#next", Button).disabled = False

    @on(Button.Pressed, "#next")
    def go(self) -> None:
        self.app.selection = catalog.resolve_dependencies(self.selection())
        self.app.push_screen(PathsScreen())

    @on(Button.Pressed, "#back")
    def back(self) -> None:
        self.app.pop_screen()


# ---------------------------------------------------------------------- chemins


class PathsScreen(WizardScreen):
    SUB_TITLE = "Etape 2/3 - Chemins et plateforme"

    def content(self) -> ComposeResult:
        # Le profil propose est celui de la machine. Proposer generic-linux a un
        # utilisateur Windows le menait droit dans le piege : il gardait des
        # chemins Linux, crees ensuite a la racine du disque courant.
        courant = default_profile()
        defaults = PROFILE_DEFAULTS[courant]
        # `VerticalScroll` et non `Vertical` : l'ecran a grossi (identifiant,
        # adresse de la machine) et depassait la fenetre. Sans defilement, les
        # derniers champs etaient simplement INACCESSIBLES — il fallait
        # agrandir la fenetre a la main pour les voir. Signale a l'usage.
        with VerticalScroll(id="paths"):
            yield Label("Profil de plateforme", classes="group-title")
            with RadioSet(id="platform"):
                for profile in PlatformProfile:
                    yield RadioButton(
                        profile.value,
                        value=profile is courant,
                        id=f"plat-{profile.value}",
                    )
            yield Static(id="platform-note")

            yield Label("Racine des configurations", classes="group-title")
            yield Input(value=defaults.config_root, id="config-root")

            yield Label(
                "Racine des donnees [dim](montee sur /data dans TOUS les conteneurs)[/dim]",
                classes="group-title",
            )
            yield Input(value=defaults.data_root, id="data-root")

            yield Label(
                "Identifiant [dim](le meme pour tous les services installes)[/dim]",
                classes="group-title",
            )
            yield Input(value="plugarr", id="username")

            # La langue des SERVICES, pas celle de PlugArr : elle decide de ce
            # que Sonarr, Jellyfin et les autres afficheront dans leur propre
            # interface. Elle part de celle de PlugArr, qui est le cas courant,
            # mais rien n'oblige a les garder ensemble : on peut vouloir
            # l'assistant en anglais et sa mediatheque en francais.
            yield Label(
                "Langue des services installes "
                "[dim](Sonarr, Jellyfin... ; celle de PlugArr se choisit "
                "sur l'ecran d'accueil)[/dim]",
                classes="group-title",
            )
            yield Select(
                [(lang.nom, lang.code) for lang in langues.PROPOSEES],
                value=self._langue_par_defaut(),
                allow_blank=False,
                id="langue",
            )

            yield Label(
                "Nom de la pile Docker "
                "[dim](a changer pour en installer une SECONDE a cote)[/dim]",
                classes="group-title",
            )
            yield Input(value="plugarr", id="project-name")

            yield Label("Fuseau horaire", classes="group-title")
            yield Input(value="Europe/Paris", id="tz")

            yield Label(
                "Adresse de cette machine "
                "[dim](a changer si vous naviguerez depuis un autre poste)[/dim]",
                classes="group-title",
            )
            yield Input(value="localhost", id="host")

            yield Rule()
            yield Static(id="paths-check")
        yield Horizontal(
            Button("Verifier les chemins", id="check"),
            Button("Continuer", variant="primary", id="next"),
            Button("Retour", id="back"),
            classes="actions",
        )

    @staticmethod
    def _langue_par_defaut() -> str:
        """Celle de PlugArr, si les services savent la recevoir.

        `langues.PROPOSEES` est volontairement plus courte que ce que les *arr
        acceptent : si la langue de PlugArr n'y figure pas, la liste refuserait
        la valeur et l'ecran ne se monterait pas.
        """
        courante = i18n.langue()
        return courante if any(lang.code == courante for lang in langues.PROPOSEES) else "en"

    def on_mount(self) -> None:
        self._update_note(default_profile())

    @on(RadioSet.Changed, "#platform")
    def _on_platform(self, event: RadioSet.Changed) -> None:
        profile = PlatformProfile(str(event.pressed.label))
        defaults = PROFILE_DEFAULTS[profile]
        self.query_one("#config-root", Input).value = defaults.config_root
        self.query_one("#data-root", Input).value = defaults.data_root
        self._update_note(profile)

    #: « 1000:1000 » ne dit rien a qui n'a jamais administre un systeme Unix, et
    #: cette valeur decide pourtant de qui possedera les fichiers telecharges.
    IDS_EXPLICATION = (
        "[dim]PUID/PGID = l'utilisateur Linux, a l'interieur des conteneurs, "
        "qui possedera vos fichiers.[/dim]"
    )

    def _update_note(self, profile: PlatformProfile) -> None:
        uid, gid, source, certain = resolve_ids(profile)
        note = self.query_one("#platform-note", Static)
        entete = f"[dim]PUID/PGID[/dim] [b]{uid}:{gid}[/b]"
        if certain:
            note.update(f"{entete} [dim]- {t(source)}[/dim]\n{t(self.IDS_EXPLICATION)}")
        else:
            note.update(
                entete
                + t(
                    " [yellow]- non detectables ici, valeur de repli.[/yellow]\n"
                )
                + t(self.IDS_EXPLICATION)
                + t(
                    "\n[dim]Sur un NAS, lancez `id` et corrigez ces valeurs.[/dim]"
                )
            )

    def platform(self) -> PlatformProfile:
        pressed = self.query_one("#platform", RadioSet).pressed_button
        return PlatformProfile(str(pressed.label)) if pressed else PlatformProfile.GENERIC_LINUX

    @on(Button.Pressed, "#check")
    def check(self) -> None:
        data_root = self.query_one("#data-root", Input).value.strip()
        target = self.query_one("#paths-check", Static)
        if not data_root:
            target.update("[red]La racine des donnees ne peut pas etre vide.[/red]")
            return

        lignes: list[str] = []
        # D'abord OU le dossier va reellement atterrir. Sans cette ligne, le
        # controle repondait « hardlink OK » pour `/mnt/user/data` saisi sous
        # Windows — vrai, mais dans `C:\mnt\user\data`, que personne ne voulait.
        avertissement = path_warning(data_root)
        if avertissement:
            lignes.append(f"[yellow]{avertissement}[/yellow]")
        else:
            lignes.append(
                t("[dim]Dossier vise : {chemin}[/dim]", chemin=Path(data_root).resolve())
            )

        try:
            Path(data_root).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            lignes.append(t("[red]Impossible de le creer : {erreur}[/red]", erreur=exc))
            target.update("\n".join(lignes))
            return

        ok, detail = hardlink_supported(data_root)
        colour = "green" if ok else "yellow"
        lignes.append(f"[{colour}]{detail}[/{colour}]")
        lignes.append(
            "[dim]Un hardlink reel a ete cree puis supprime entre torrents/ et media/.[/dim]"
        )
        target.update("\n".join(lignes))

    @on(Button.Pressed, "#next")
    def go(self) -> None:
        self.app.config_root = self.query_one("#config-root", Input).value.strip()
        self.app.data_root = self.query_one("#data-root", Input).value.strip()
        self.app.timezone = self.query_one("#tz", Input).value.strip() or "Etc/UTC"
        self.app.username = self.query_one("#username", Input).value.strip() or "plugarr"
        self.app.project_name = (
            self.query_one("#project-name", Input).value.strip() or "plugarr"
        )
        choisie = self.query_one("#langue", Select).value
        self.app.language = choisie if isinstance(choisie, str) else "en"
        self.app.host = self.query_one("#host", Input).value.strip() or "localhost"
        self.app.platform = self.platform()
        # Le VPN d'abord, s'il y a un trafic a proteger. Puis les profils de
        # qualite, s'ils ont un sens. Chaque ecran facultatif sait s'effacer.
        if any(sid in self.app.selection for sid in catalog.DOWNLOAD_CLIENTS):
            self.app.push_screen(VpnScreen())
        else:
            _suite_apres_vpn(self.app)

    @on(Button.Pressed, "#back")
    def back(self) -> None:
        self.app.pop_screen()


# ------------------------------------------------------------ profils qualite


class TemplatesScreen(WizardScreen):
    """Choix du profil de qualite TRaSH, service par service.

    Etape facultative : les defauts conviennent a la plupart des installations,
    et le bouton « Passer » est la pour le dire. Elle n'apparait que si Recyclarr
    est selectionne avec au moins un *arr a configurer.

    La liste vient du manifeste officiel, pas d'une copie embarquee dans le code.
    Elle est chargee dans un thread : l'ecran doit s'afficher tout de suite, meme
    si le reseau traine.
    """

    SUB_TITLE = "Etape optionnelle - profils de qualite"

    #: Services que Recyclarr sait configurer, dans l'ordre d'affichage.
    SERVICES = ("sonarr", "radarr")

    def __init__(self) -> None:
        super().__init__()
        self._available: dict[str, list[str]] = {}

    def _targets(self) -> list[str]:
        return [sid for sid in self.SERVICES if sid in self.app.selection]

    def content(self) -> ComposeResult:
        yield Static(
            "Sans profil de qualite, un *arr accepte [b]n'importe quel[/b] encodage : "
            "le premier resultat venu, pas le meilleur.\n"
            "[dim]Les profils viennent des TRaSH Guides. plugarr ne fait que poser "
            "l'adresse et la cle API dans le template que vous choisissez ici.[/dim]",
            id="templates-intro",
        )
        with VerticalScroll(id="templates"):
            for sid in self._targets():
                spec = catalog.get(sid)
                default = recyclarr_cfg.DEFAULT_TEMPLATES.get(sid, "")
                yield Label(spec.display_name, classes="group-title")
                # Une LISTE, pas un champ libre. Il y a 22 profils pour Sonarr et
                # 35 pour Radarr : demander de taper un nom obligeait a le
                # connaitre par coeur, et l'ecran n'en montrait que six.
                yield Select(
                    [(default, default)] if default else [],
                    value=default or Select.BLANK,
                    allow_blank=not default,
                    id=f"tpl-{sid}",
                )
                yield Static(id=f"tpl-choices-{sid}", classes="service-note")
        yield Static(id="templates-status")
        yield Horizontal(
            Button("Continuer", variant="primary", id="next"),
            Button("Passer", id="skip"),
            Button("Retour", id="back"),
            classes="actions",
        )

    def on_mount(self) -> None:
        self.query_one("#templates-status", Static).update(
            "[dim]Chargement de la liste officielle…[/dim]"
        )
        self._load()

    @work(thread=True)
    def _load(self) -> None:
        config_dir = Path(self.app.config_root) / "recyclarr" if self.app.config_root else None
        try:
            names, problem = recyclarr_cfg.available_templates(config_dir)
        except Exception as exc:  # noqa: BLE001
            journal.LOGGER.exception("liste des templates Recyclarr")
            names, problem = {}, t("liste indisponible : {erreur}", erreur=exc)
        self.app.call_from_thread(self._loaded, names, problem)

    def _loaded(self, names: dict[str, list[str]], problem: str | None) -> None:
        self._available = names
        status = self.query_one("#templates-status", Static)
        if problem:
            # Le nom reste saisissable : ne pas pouvoir lister n'est pas une raison
            # d'empecher quelqu'un qui sait ce qu'il veut.
            status.update(
                f"[yellow]{problem}[/yellow]\n"
                + t(
                    "[dim]Les noms ne seront pas verifies ici. Les defauts "
                    "restent valables.[/dim]"
                )
            )
            return
        status.update("")
        for sid in self._targets():
            available = names.get(sid, [])
            defaut = recyclarr_cfg.DEFAULT_TEMPLATES.get(sid, "")
            liste = self.query_one(f"#tpl-{sid}", Select)
            liste.set_options((nom, nom) for nom in available)
            if defaut in available:
                liste.value = defaut
            self.query_one(f"#tpl-choices-{sid}", Static).update(
                t(
                    "[dim]{nombre} profils proposes par les TRaSH Guides. "
                    "Cliquez pour derouler la liste.[/dim]",
                    nombre=len(available),
                )
            )
        self._validate()

    @on(Select.Changed)
    def _on_change(self) -> None:
        self._validate()

    def choices(self) -> dict[str, str]:
        retenus = {}
        for sid in self._targets():
            valeur = self.query_one(f"#tpl-{sid}", Select).value
            if isinstance(valeur, str) and valeur:
                retenus[sid] = valeur
        return retenus

    def _validate(self) -> bool:
        """Un nom inconnu n'echoue qu'a la toute fin du cablage. On le dit ici."""
        if not self._available:
            return True
        unknown = [
            f"{sid} : {name}"
            for sid, name in self.choices().items()
            if name not in self._available.get(sid, [])
        ]
        status = self.query_one("#templates-status", Static)
        button = self.query_one("#next", Button)
        if unknown:
            status.update(
                t(
                    "[red]Template inconnu — {noms}[/red]\n"
                    "[dim]Recyclarr refuserait de generer la configuration.[/dim]",
                    noms=", ".join(unknown),
                )
            )
            button.disabled = True
            return False
        status.update("")
        button.disabled = False
        return True

    @on(Button.Pressed, "#next")
    def go(self) -> None:
        if not self._validate():
            return
        self.app.recyclarr_templates = self.choices()
        self.app.push_screen(SummaryScreen())

    @on(Button.Pressed, "#skip")
    def skip(self) -> None:
        self.app.recyclarr_templates = {}
        self.app.push_screen(SummaryScreen())

    @on(Button.Pressed, "#back")
    def back(self) -> None:
        self.app.pop_screen()


# ------------------------------------------------------------------------ vpn


class VpnScreen(WizardScreen):
    """Choix du VPN pour le client de telechargement.

    Etape facultative, mais elle manquait completement : les sept options
    `--vpn*` n'existaient qu'en ligne de commande, et le recapitulatif se
    contentait d'AVERTIR qu'aucun VPN n'etait configure — sans offrir le moindre
    moyen d'en mettre un. Signale a l'usage.

    L'ecran n'apparait que si un client de telechargement est installe : sans
    trafic BitTorrent, Gluetun ne protegerait rien.
    """

    SUB_TITLE = "Etape optionnelle - VPN du client de telechargement"

    def content(self) -> ComposeResult:
        yield Static(
            "Sans VPN, le trafic BitTorrent sort sur [b]l'adresse IP publique de cette "
            "machine[/b], visible par tous les autres pairs.\n"
            "[dim]Avec Gluetun, le client de telechargement perd son propre reseau : il "
            "ne demarre pas tant que le tunnel n'est pas etabli, donc aucun paquet ne "
            "peut sortir en clair.[/dim]",
            id="vpn-intro",
        )
        with VerticalScroll(id="vpn"):
            with RadioSet(id="vpn-choix"):
                yield RadioButton("Sans VPN", value=True, id="vpn-non")
                yield RadioButton("Faire passer le client par un VPN", id="vpn-oui")

            with Vertical(id="vpn-details", classes="hidden"):
                yield Label("Fournisseur", classes="group-title")
                yield Select(
                    [(nom, nom) for nom in VPN_PROVIDERS],
                    value="mullvad",
                    allow_blank=False,
                    id="vpn-provider",
                )

                yield Label("Protocole", classes="group-title")
                yield Select(
                    [("wireguard", "wireguard"), ("openvpn", "openvpn")],
                    value="wireguard",
                    allow_blank=False,
                    id="vpn-type",
                )

                with Vertical(id="vpn-wireguard"):
                    yield Label("Cle privee WireGuard", classes="group-title")
                    yield Input(password=True, id="vpn-key")

                with Vertical(id="vpn-openvpn", classes="hidden"):
                    yield Label("Identifiant OpenVPN", classes="group-title")
                    yield Input(id="vpn-user")
                    yield Label("Mot de passe OpenVPN", classes="group-title")
                    yield Input(password=True, id="vpn-pass")

                yield Label("", id="vpn-lieux-titre", classes="group-title")
                # Liste cliquable plutot que saisie libre : une valeur inventee
                # fait echouer Gluetun au demarrage, et le client de
                # telechargement reste alors injoignable sans explication. Les
                # valeurs viennent de l'image epinglee elle-meme.
                yield SelectionList[str](id="vpn-lieux")
                yield Static(id="vpn-lieux-note", classes="service-note")

        yield Static(id="vpn-status")
        yield Horizontal(
            Button("Continuer", variant="primary", id="next"),
            Button("Retour", id="back"),
            classes="actions",
        )

    def on_mount(self) -> None:
        self._peupler_lieux()

    @on(RadioSet.Changed, "#vpn-choix")
    def _on_choice(self) -> None:
        self.query_one("#vpn-details", Vertical).set_class(not self.vpn_voulu(), "hidden")
        self._validate()

    @on(Select.Changed, "#vpn-provider")
    def _on_provider(self) -> None:
        """Chaque fournisseur a SA liste, et pas toujours des pays.

        Windscribe, VyprVPN, Giganews et Private Internet Access classent leurs
        serveurs par region ; Perfect Privacy par ville. Proposer « pays » a
        tout le monde offrirait un filtre qui ne filtre rien.
        """
        self._peupler_lieux()
        self._validate()

    def _peupler_lieux(self) -> None:
        fournisseur = self.query_one("#vpn-provider", Select).value
        fournisseur = fournisseur if isinstance(fournisseur, str) else ""
        liste = self.query_one("#vpn-lieux", SelectionList)
        liste.clear_options()
        choix = vpnservers.choices(fournisseur)
        titre = self.query_one("#vpn-lieux-titre", Label)
        note = self.query_one("#vpn-lieux-note", Static)
        if choix:
            liste.add_options([(lieu, lieu) for lieu in choix])
            liste.display = True
            titre.update(
                f"{vpnservers.label(fournisseur)} " + t("[dim](facultatif)[/dim]")
            )
            note.update(
                t(
                    "[dim]{nombre} choix proposes par Gluetun {version}. "
                    "Sans selection, le VPN choisit pour vous.[/dim]",
                    nombre=len(choix),
                    version=vpnservers.gluetun_version(),
                )
            )
        else:
            # `custom` n'a par construction aucune liste : l'utilisateur fournit
            # sa propre configuration, Gluetun ne connait aucun serveur pour lui.
            liste.display = False
            titre.update("")
            note.update(
                "[dim]Ce fournisseur ne propose pas de filtre geographique : "
                "les serveurs viennent de votre propre configuration.[/dim]"
            )

    @on(Select.Changed, "#vpn-type")
    def _on_type(self) -> None:
        wireguard = self.query_one("#vpn-type", Select).value == "wireguard"
        self.query_one("#vpn-wireguard", Vertical).set_class(not wireguard, "hidden")
        self.query_one("#vpn-openvpn", Vertical).set_class(wireguard, "hidden")
        self._validate()

    @on(Input.Changed)
    def _on_change(self) -> None:
        self._validate()

    def vpn_voulu(self) -> bool:
        coche = self.query_one("#vpn-choix", RadioSet).pressed_button
        return coche is not None and coche.id == "vpn-oui"

    def config(self) -> VpnConfig:
        """Traduit la saisie. Une valeur invalide est ecartee ici, pas plus tard."""
        if not self.vpn_voulu():
            return VpnConfig()
        fournisseur = self.query_one("#vpn-provider", Select).value
        try:
            return VpnConfig(
                enabled=True,
                provider=fournisseur if isinstance(fournisseur, str) else "",
                vpn_type=str(self.query_one("#vpn-type", Select).value),
                wireguard_private_key=self.query_one("#vpn-key", Input).value.strip(),
                openvpn_user=self.query_one("#vpn-user", Input).value.strip(),
                openvpn_password=self.query_one("#vpn-pass", Input).value.strip(),
                countries=",".join(self.query_one("#vpn-lieux", SelectionList).selected),
            )
        except ValueError:
            return VpnConfig()

    def _validate(self) -> bool:
        """Gluetun refuse de demarrer s'il manque un champ, et le client de
        telechargement reste alors injoignable. Autant le dire ici."""
        bouton = self.query_one("#next", Button)
        status = self.query_one("#vpn-status", Static)
        if not self.vpn_voulu():
            status.update("")
            bouton.disabled = False
            return True

        manques = self.config().missing()
        if manques:
            status.update(
                t(
                    "[yellow]Il manque {champs}.[/yellow]\n"
                    "[dim]Sans cela Gluetun refuse de demarrer, et le client de "
                    "telechargement reste injoignable.[/dim]",
                    champs=", ".join(manques),
                )
            )
            bouton.disabled = True
            return False
        status.update("[green]Configuration complete.[/green]")
        bouton.disabled = False
        return True

    @on(Button.Pressed, "#next")
    def go(self) -> None:
        if not self._validate():
            return
        self.app.vpn = self.config()
        _suite_apres_vpn(self.app)

    @on(Button.Pressed, "#back")
    def back(self) -> None:
        self.app.pop_screen()


def _suite_apres_vpn(app) -> None:
    """Ecran suivant : les profils de qualite s'ils ont un sens, sinon la fin."""
    if "recyclarr" in app.selection and any(
        sid in app.selection for sid in TemplatesScreen.SERVICES
    ):
        app.push_screen(TemplatesScreen())
    else:
        app.push_screen(SummaryScreen())


# ----------------------------------------------------------------- recapitulatif


class SummaryScreen(WizardScreen):
    SUB_TITLE = "Etape 3/3 - Recapitulatif (rien n'est encore ecrit)"

    def content(self) -> ComposeResult:
        with VerticalScroll(id="summary"):
            yield DataTable(id="summary-table", cursor_type="row")
            yield Static(id="summary-paths")
            yield Static(id="summary-warnings")
            # Choix propose UNIQUEMENT si une configuration inutilisable existe.
            # Il n'apparait donc jamais lors d'une premiere installation.
            yield Static(id="reprise", classes="hidden")
            with RadioSet(id="reprise-choix", classes="hidden"):
                yield RadioButton(
                    "Reprendre ces reglages", value=True, id="reprise-oui"
                )
                yield RadioButton("Repartir de zero", id="reprise-non")
            yield Static(id="config-existante", classes="hidden")
            with RadioSet(id="config-choix", classes="hidden"):
                yield RadioButton("Conserver ces configurations", value=True, id="cfg-garder")
                yield RadioButton("Supprimer et repartir de zero", id="cfg-supprimer")
        yield Horizontal(
            Button("Installer et cabler", variant="success", id="install"),
            Button("Retour", id="back"),
            classes="actions",
        )

    def on_mount(self) -> None:
        cfg = self.app.build_config()
        table = self.query_one("#summary-table", DataTable)
        table.add_columns("Service", "Image", "URL")
        for sid, inst in orchestrator.iter_selected(cfg):
            spec = catalog.get(sid)
            table.add_row(
                spec.display_name,
                spec.image,
                inst.url(cfg.host) if inst.has_web_ui else t("tache de fond"),
            )

        lignes = [
            t("[b]Configurations[/b]  {chemin}", chemin=cfg.config_root),
            t(
                "[b]Donnees[/b]        {chemin}  -> /data dans tous les conteneurs",
                chemin=cfg.data_root,
            ),
            f"[b]PUID:PGID[/b]      {cfg.puid}:{cfg.pgid} [dim]({t(cfg.ids_source)})[/dim]",
            f"[b]UMASK / TZ[/b]     {cfg.umask}   {cfg.timezone}",
        ]
        # Un VPN configure ajoute un conteneur que le tableau ci-dessus ne montre
        # pas : Gluetun n'est pas un service du catalogue. Sans cette ligne, le
        # recapitulatif ne dirait RIEN du choix qui vient d'etre fait, et la
        # disparition de l'avertissement serait le seul indice qu'il a ete pris.
        if cfg.vpn_enabled:
            lignes.append(
                t(
                    "[b]VPN[/b]            gluetun - {fournisseur} "
                    "[dim]({protocole}) ; le client de telechargement ne "
                    "demarrera pas sans le tunnel[/dim]",
                    fournisseur=cfg.vpn.provider,
                    protocole=cfg.vpn.vpn_type,
                )
            )
        lignes.append(
            t("[b]Liens a cabler[/b] {nombre}", nombre=orchestrator.planned_links(cfg))
        )
        self.query_one("#summary-paths", Static).update("\n".join(lignes))

        vpn_warning = t(
            "[yellow]Aucun VPN n'est configure pour le client torrent.[/yellow]\n"
            "[dim]Le trafic BitTorrent sortira sur l'adresse IP publique de "
            "cette machine, visible par les autres pairs.[/dim]"
        )
        # L'avertissement ne vaut que si le VPN n'a PAS ete configure. Tant
        # qu'il n'existait qu'en ligne de commande la question ne se posait
        # pas ; avec l'ecran VPN, avertir sans regarder revenait a annoncer
        # « aucun VPN » a quelqu'un qui venait d'en saisir un.
        warnings = []
        if orchestrator.has_download_client(cfg) and not cfg.vpn_enabled:
            warnings.append(vpn_warning)
        if not cfg.ids_certain:
            warnings.append(
                t(
                    "[yellow]PUID/PGID non detectables ici : repli sur "
                    "{uid}:{gid}.[/yellow]\n"
                    "[dim]Des identifiants faux font ecrire toute la stack avec "
                    "de mauvaises permissions. Sur un NAS, lancez `id`.[/dim]",
                    uid=cfg.puid,
                    gid=cfg.pgid,
                )
            )
        self.query_one("#summary-warnings", Static).update("\n\n".join(warnings))
        self._montrer_reprise()
        self._proposer_reset(cfg)

    def _montrer_reprise(self) -> None:
        """Dit ce qui a ete repris d'une installation precedente.

        Une reprise silencieuse serait pire que pas de reprise : l'utilisateur
        doit voir ce que PlugArr a decide de garder a sa place, et pouvoir le
        refuser.
        """
        reprise = getattr(self.app, "reprise", None)
        if not reprise:
            return
        ailleurs = getattr(self.app, "reprise_depuis", None)
        lignes = [
            t("[cyan]Une installation existe deja ici : ses reglages sont repris.[/cyan]")
            if ailleurs is None
            else t(
                "[cyan]Une installation precedente a ete retrouvee dans "
                "{dossier}[/cyan]\n[dim]Ses reglages sont repris, et c'est la que "
                "PlugArr ecrira ses fichiers : une pile Docker ne peut pas vivre "
                "dans deux repertoires a la fois.[/dim]",
                dossier=ailleurs,
            )
        ]
        if reprise.reglages:
            lignes.append(f"[dim]{t('Reglages')} : {', '.join(reprise.reglages)}[/dim]")
        if reprise.services:
            lignes.append(
                f"[dim]{t('Identifiants conserves')} : "
                f"{', '.join(sorted(reprise.services))}[/dim]"
            )
        bandeau = self.query_one("#reprise", Static)
        bandeau.update("\n".join(lignes))
        bandeau.remove_class("hidden")
        self.query_one("#reprise-choix", RadioSet).remove_class("hidden")

    @on(RadioSet.Changed, "#reprise-choix")
    def _changer_reprise(self, event: RadioSet.Changed) -> None:
        """Refuser la reprise rebatit la configuration : les identifiants
        repris doivent disparaitre du recapitulatif, pas seulement de l'ecran."""
        self.app.reprendre = event.pressed.id == "reprise-oui"
        self.app.stack_config = None
        self.on_mount()

    def _proposer_reset(self, cfg) -> None:
        """Affiche le choix garder / repartir de zero, s'il a lieu d'etre.

        Le cas : qBittorrent, Transmission, Jellyfin, autobrr et qui ne stockent
        leur mot de passe que hache. Une configuration heritee d'une installation
        precedente ne peut donc pas etre reprise — les identifiants annonces
        seront refuses, avec des messages incomprehensibles.

        Le choix par defaut reste « conserver » : effacer la configuration de
        quelqu'un sans qu'il l'ait demande serait inacceptable.
        """
        concernes = orchestrator.unusable_configs(cfg)
        if not concernes:
            return

        chemins = "\n".join(f"  {cfg.config_path(sid)}" for sid in concernes)
        bandeau = self.query_one("#config-existante", Static)
        bandeau.update(
            t(
                "[yellow]Une configuration existe deja pour {services}.[/yellow]\n"
                "[dim]Leurs mots de passe n'y sont stockes que haches. PlugArr "
                "essaiera ceux de ses installations precedentes avant d'en annoncer "
                "un neuf ; si aucun ne convient, il faudra repartir de zero.[/dim]\n",
                services=", ".join(concernes),
            )
            + f"[dim]{chemins}[/dim]\n"
            + t("[dim]Vos medias ne sont jamais touches.[/dim]")
        )
        bandeau.remove_class("hidden")
        self.query_one("#config-choix", RadioSet).remove_class("hidden")

    def reset_demande(self) -> bool:
        choix = self.query_one("#config-choix", RadioSet).pressed_button
        return choix is not None and choix.id == "cfg-supprimer"

    @on(Button.Pressed, "#install")
    def go(self) -> None:
        cfg = self.app.stack_config or self.app.build_config()
        self.app.stack_config = cfg
        if self.reset_demande():
            # Suppression demandee explicitement : elle a lieu ICI, avant que
            # l'installation ne commence, pour que le pre-semis reparte d'un
            # dossier vide.
            efface = orchestrator.reset_configs(cfg, orchestrator.unusable_configs(cfg))
            journal.finish(f"configurations supprimees : {len(efface)}")
        self.app.push_screen(InstallScreen())

    @on(Button.Pressed, "#back")
    def back(self) -> None:
        self.app.pop_screen()


# ------------------------------------------------------------------ installation


class InstallScreen(WizardScreen):
    SUB_TITLE = "Installation et cablage"
    BINDINGS = [("ctrl+q", "app.quit", "Quitter")]

    def content(self) -> ComposeResult:
        yield Static("Preparation...", id="install-phase")
        # Le telechargement des images est muet et peut durer plusieurs minutes :
        # sans barre, rien ne distingue « ca travaille » de « c'est bloque ».
        yield ProgressBar(id="install-progress", show_eta=False)
        yield RichLog(id="install-log", markup=True, wrap=True)
        yield Horizontal(
            Button("Terminer", variant="primary", id="done", disabled=True),
            classes="actions",
        )

    def on_mount(self) -> None:
        self.run_install()

    def _log(self, text: str) -> None:
        self.query_one("#install-log", RichLog).write(text)

    def _phase(self, text: str) -> None:
        self.query_one("#install-phase", Static).update(text)

    def _advance(self) -> None:
        bar = self.query_one("#install-progress", ProgressBar)
        # Le total est une estimation : on borne plutot que de depasser 100 %.
        if bar.total is not None and bar.progress < bar.total:
            bar.advance(1)

    def _complete(self) -> None:
        bar = self.query_one("#install-progress", ProgressBar)
        if bar.total is not None:
            bar.progress = bar.total

    @work(thread=True)
    def run_install(self) -> None:
        app = self.app
        cfg = app.stack_config or app.build_config()
        app.stack_config = cfg
        chemin = journal.start(Path(app.project_dir), "assistant : installation")
        journal.config(cfg)
        app.call_from_thread(
            self._log, t("[dim]Journal detaille : {chemin}[/dim]", chemin=chemin)
        )
        app.call_from_thread(self._set_total, orchestrator.expected_events(cfg))

        def on_progress(progress: Progress) -> None:
            mark = "[green]OK[/green]" if progress.ok else "[red]ECHEC[/red]"
            journal.progress(progress.phase, progress.message, progress.ok)
            app.call_from_thread(self._phase, f"{progress.phase} : {progress.message}")
            app.call_from_thread(self._log, f"  {mark}  {progress.phase} : {progress.message}")
            app.call_from_thread(self._advance)

        def on_step(result: StepResult) -> None:
            journal.step(result)
            mark = "[green]OK[/green]" if result.ok else "[red]ECHEC[/red]"
            app.call_from_thread(self._log, f"  {mark}  {result.name} - {result.detail}")
            for warning in result.warnings:
                app.call_from_thread(self._log, f"        [yellow]{warning}[/yellow]")
            app.call_from_thread(self._advance)

        try:
            results = orchestrator.install(
                cfg, app.project_dir, on_progress=on_progress, on_step=on_step
            )
        except InstallAborted as exc:
            journal.failure(str(exc))
            app.call_from_thread(self._log, f"[red]{exc}[/red]")
            app.call_from_thread(self._phase, "[red]Installation interrompue[/red]")
            app.call_from_thread(self._enable_done, [])
            return
        except Exception as exc:  # noqa: BLE001 - rien ne doit tuer l'assistant
            # Sans ce filet, une erreur imprevue fait disparaitre la fenetre en
            # plein cablage : l'utilisateur perd l'ecran ET l'explication.
            journal.LOGGER.exception("installation")
            app.call_from_thread(self._log, f"[red]{type(exc).__name__} : {exc}[/red]")
            app.call_from_thread(
                self._log,
                t(
                    "[dim]Detail complet dans {chemin}[/dim]",
                    chemin=app.project_dir / journal.FILENAME,
                ),
            )
            app.call_from_thread(self._phase, "[red]Installation interrompue[/red]")
            app.call_from_thread(self._enable_done, [])
            return
        app.call_from_thread(self._enable_done, results)

    def _set_total(self, total: int) -> None:
        self.query_one("#install-progress", ProgressBar).update(total=total, progress=0)

    def _enable_done(self, results: list[StepResult]) -> None:
        self.app.results = results
        # Une barre figee a 94 % apres un succes se lit comme un echec.
        self._complete()
        ok = sum(1 for r in results if r.ok)
        self._phase(
            t(
                "[green]Termine : {faits}/{total} liens etablis[/green]",
                faits=ok,
                total=len(results),
            )
            if results and ok == len(results)
            else t(
                "[yellow]Termine : {faits}/{total} liens etablis[/yellow]",
                faits=ok,
                total=len(results),
            )
        )
        self.query_one("#done", Button).disabled = False

    @on(Button.Pressed, "#done")
    def go(self) -> None:
        # L'etape indexeurs n'a de sens que si Prowlarr tourne : c'est lui qui
        # fournit les definitions et qui recevra les identifiants.
        if self.app.stack_config and self.app.stack_config.enabled("prowlarr"):
            from .indexers import IndexersScreen

            self.app.push_screen(IndexersScreen())
        else:
            self.app.push_screen(ReportScreen())


# ------------------------------------------------------------------- rapport


class ReportScreen(WizardScreen):
    SUB_TITLE = "Acces"
    BINDINGS = [("ctrl+q", "app.quit", "Quitter")]

    def content(self) -> ComposeResult:
        with VerticalScroll(id="report"):
            yield DataTable(id="report-table", cursor_type="row")
            yield Static(id="report-next")
        yield Horizontal(
            Button("Ouvrir la page d'acces", variant="success", id="open-page"),
            Button("Fermer", variant="primary", id="close"),
            classes="actions",
        )

    def on_mount(self) -> None:
        cfg = self.app.stack_config
        table = self.query_one("#report-table", DataTable)
        table.add_columns("Service", "URL", "Identifiant", "Mot de passe", "Cle API")
        for sid, inst in orchestrator.iter_selected(cfg):
            table.add_row(
                catalog.get(sid).display_name,
                inst.url(cfg.host),
                inst.username or "-",
                inst.password or "-",
                inst.api_key or "-",
            )
        failed = [r for r in self.app.results if not r.ok]
        if failed:
            body = t("[red]Liens en echec :[/red]\n") + "\n".join(
                f"  - {r.name} : {r.detail.splitlines()[0]}" for r in failed
            )
            body += t("\n\n[dim]Diagnostic : plugarr doctor[/dim]")
        else:
            # `stack_config` est pose par l'installation. S'il manque, le
            # rapport reste affichable : on retombe sur la formule generale.
            cfg = self.app.stack_config
            lignes = (
                orchestrator.prochaine_etape(cfg)
                if cfg is not None
                else [t("Prochaine etape : ouvrez chaque service depuis la page d'acces.")]
            )
            # La derniere ligne est un aparte : elle passe en retrait.
            body = "[b]" + lignes[0] + "[/b]"
            if len(lignes) > 2:
                body += "\n" + "\n".join(lignes[1:-1])
            if len(lignes) > 1:
                body += "\n\n[dim]" + lignes[-1] + "[/dim]"
        body += t(
            "\n\n[dim]Ces identifiants sont aussi dans {chemin} "
            "(chmod 600).[/dim]",
            chemin=self.app.project_dir / ".env",
        )
        self.query_one("#report-next", Static).update(body)
        self._ouvrir_automatiquement()

    def _ouvrir_automatiquement(self) -> None:
        """Ouvre la page d'acces sans attendre un clic.

        La ligne de commande le faisait deja ; l'assistant, lui, se contentait
        d'un bouton. Or c'est precisement la que l'utilisateur a besoin de la
        page : elle porte les adresses et les identifiants qu'il vient de se voir
        annoncer.

        Le bouton reste, comme second essai : sur un NAS sans environnement
        graphique, aucun navigateur ne repond.
        """
        from .. import dashboard

        if not self.app.auto_open_page:
            return
        chemin = Path(self.app.project_dir) / dashboard.FILENAME
        if chemin.exists() and dashboard.open_in_browser(chemin):
            self.query_one("#open-page", Button).label = t("Rouvrir la page d'acces")

    @on(Button.Pressed, "#open-page")
    def open_page(self) -> None:
        from .. import dashboard

        path = self.app.project_dir / dashboard.FILENAME
        target = self.query_one("#report-next", Static)
        if not path.exists():
            target.update(t("[yellow]Page introuvable : {chemin}[/yellow]", chemin=path))
            return
        if dashboard.open_in_browser(path):
            target.update(
                t("[green]Page ouverte dans votre navigateur.[/green]\n")
                + f"[dim]{path}[/dim]"
            )
        else:
            # Cas normal sur un NAS sans environnement graphique.
            target.update(
                t(
                    "[yellow]Aucun navigateur disponible ici.[/yellow]\n"
                    "[dim]Ouvrez ce fichier depuis un autre appareil : {chemin}[/dim]",
                    chemin=path,
                )
            )

    @on(Button.Pressed, "#close")
    def close(self) -> None:
        self.app.exit(0 if all(r.ok for r in self.app.results) else 2)
