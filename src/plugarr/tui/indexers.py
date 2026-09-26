"""Ecran optionnel : saisie des indexeurs de l'utilisateur.

plugarr ne fournit aucun indexeur. La liste presentee ici est celle que le
Prowlarr de l'utilisateur embarque : cet ecran n'est qu'un formulaire de saisie
par-dessus les donnees de Prowlarr. Rien n'est preselectionne, et l'etape se
passe d'un bouton.
"""

from __future__ import annotations

from rich.markup import escape
from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.widgets import ListItem, ListView, SelectionList
from textual.widgets.selection_list import Selection

from .. import catalog, import_prowlarr, journal
from ..clients.arr import ArrClient
from ..clients.prowlarr import IndexerDefinition, ProwlarrIndexers
from ..i18n import t
from .screens import WizardScreen

# Widgets traduisants : voir tui/widgets.py.
from .widgets import Button, Input, Label, Static

MAX_RESULTS = 40


class IndexersScreen(WizardScreen):
    SUB_TITLE = "Etape optionnelle - vos indexeurs"

    def __init__(self) -> None:
        super().__init__()
        self._indexers: ProwlarrIndexers | None = None
        self._client: ArrClient | None = None
        self._matches: list[IndexerDefinition] = []
        self._current: IndexerDefinition | None = None
        #: Indexeurs importables de la sauvegarde examinee, par cle de selection.
        self._sauvegarde: dict[str, import_prowlarr.IndexeurSauvegarde] = {}
        #: Compte rendu du dernier import, garde au-dessus du nouvel examen.
        self._dernier_import: list[str] = []

    def content(self) -> ComposeResult:
        yield Static(
            "plugarr ne fournit et ne recommande [b]aucun[/b] indexeur. La liste "
            "ci-dessous est celle que votre propre Prowlarr embarque.\n"
            "[dim]Ajouter un indexeur le contacte pour valider vos identifiants : "
            "c'est Prowlarr qui l'impose, il n'existe pas d'enregistrement hors ligne.[/dim]",
            id="indexers-intro",
        )
        # Parite avec l'assistant web : reprendre les indexeurs d'une sauvegarde
        # Prowlarr, au lieu de tout ressaisir.
        with Horizontal(id="indexer-backup"):
            yield Input(
                placeholder="Sauvegarde Prowlarr a reprendre (.zip ou prowlarr.db)",
                id="backup-path",
            )
            yield Button("Examiner la sauvegarde", id="backup-inspect")
        yield SelectionList(id="backup-list", classes="hidden")
        yield Button("Importer la selection", id="backup-import", classes="hidden")
        with Horizontal(id="indexers-body"):
            with Vertical(classes="indexers-pane"):
                yield Input(placeholder="Rechercher un indexeur...", id="indexer-search")
                yield ListView(id="indexer-results")
            with VerticalScroll(classes="indexers-pane", id="indexer-form"):
                yield Static("Choisissez un indexeur a gauche.", id="indexer-detail")
        yield Static(id="indexer-status")
        yield Horizontal(
            Button("Ajouter cet indexeur", variant="primary", id="add", disabled=True),
            Button("Passer cette etape", id="skip"),
            classes="actions",
        )

    def on_mount(self) -> None:
        self.load_definitions()

    # -- chargement ----------------------------------------------------------

    @work(thread=True)
    def load_definitions(self) -> None:
        """5,7 Mo de definitions : chargement hors du fil d'affichage."""
        cfg = self.app.stack_config
        spec = catalog.get("prowlarr")
        inst = cfg.services["prowlarr"]
        client = ArrClient(
            inst.url(cfg.host), inst.api_key or "", api_version=spec.api_version, name="prowlarr"
        )
        indexers = ProwlarrIndexers(client)
        try:
            count = len(indexers.definitions())
            already = [i.get("name", "?") for i in indexers.configured()]
        except Exception as exc:  # noqa: BLE001
            journal.LOGGER.exception("chargement des definitions Prowlarr")
            self.app.call_from_thread(
                self._set_status,
                t("[red]Prowlarr injoignable : {erreur}[/red]", erreur=exc),
            )
            client.close()
            return
        self._client, self._indexers = client, indexers
        self.app.call_from_thread(self._ready, count, already)

    def _ready(self, count: int, already: list[str]) -> None:
        configured = (
            t(" - deja configures : {noms}", noms=", ".join(already)) if already else ""
        )
        self._set_status(
            t(
                "[dim]{nombre} definitions fournies par votre Prowlarr{deja}[/dim]",
                nombre=count,
                deja=configured,
            )
        )

    def _set_status(self, text: str) -> None:
        self.query_one("#indexer-status", Static).update(text)

    # -- recherche -----------------------------------------------------------

    @on(Input.Changed, "#indexer-search")
    def _search(self, event: Input.Changed) -> None:
        results = self.query_one("#indexer-results", ListView)
        results.clear()
        self._matches = []
        if self._indexers is None or len(event.value.strip()) < 2:
            return
        self._matches = self._indexers.search(event.value, MAX_RESULTS)
        for definition in self._matches:
            marker = "prive" if definition.is_private else "public"
            # Le nom vient de Prowlarr et se retrouve dans NOTRE balisage : il
            # faut l'echapper, sinon une balise fermante isolee ferait lever
            # `MarkupError` en plein rendu de la liste.
            results.append(
                ListItem(
                    Label(f"{escape(definition.name)}  [dim]{marker} - {definition.protocol}[/dim]")
                )
            )

    @on(ListView.Selected, "#indexer-results")
    async def _select(self, event: ListView.Selected) -> None:
        index = event.list_view.index
        if index is None or index >= len(self._matches):
            return
        self._current = self._matches[index]
        await self._render_form(self._current)

    async def _render_form(self, definition: IndexerDefinition) -> None:
        """Peuple le formulaire pour la definition choisie.

        `remove_children()` et `mount()` sont ASYNCHRONES : ils rendent la main
        avant que le DOM ait bouge. Sans les attendre, le second indexeur
        selectionne montait un `Input` dont l'ancien existait encore, et Textual
        levait `DuplicateIds` — depuis un gestionnaire d'evenement, donc
        l'assistant se fermait net. Constate a l'usage : le premier choix
        s'affichait, le suivant tuait l'application. Reproduit ensuite sur les
        625 definitions d'un Prowlarr reel, ou 39 des 40 correspondances de
        « tr » plantaient a la seconde selection.
        """
        form = self.query_one("#indexer-form", VerticalScroll)
        await form.remove_children()
        # `markup=False` : ces textes viennent de Prowlarr, pas de nous. Verifie
        # sur les 625 definitions du moment : aucune ne casse aujourd'hui, et
        # `Torrent[CORE]` s'affiche tel quel. Mais une balise fermante isolee
        # comme `[/dim]` leverait `MarkupError`, et un `[bold]` disparaitrait
        # sans bruit. La liste bouge a chaque version de Prowlarr ; on ne parie
        # pas dessus.
        await form.mount(
            Static(
                f"{definition.name}  ({definition.privacy} - {definition.protocol})\n"
                f"{definition.description[:160]}",
                classes="indexer-title",
                markup=False,
            )
        )
        fields = definition.editable_fields()
        if not fields:
            await form.mount(Static("[dim]Aucun identifiant requis.[/dim]"))
        for field in fields:
            await form.mount(Label(field.label, classes="group-title", markup=False))
            await form.mount(
                Input(
                    value=field.prefill,
                    password=field.secret,
                    id=f"fld-{field.name}",
                    classes="indexer-field",
                )
            )
        if len(definition.urls) > 1:
            await form.mount(
                Static(
                    "Autres miroirs connus : " + ", ".join(definition.urls[1:4]),
                    classes="indexer-mirrors",
                    markup=False,
                )
            )
        self.query_one("#add", Button).disabled = False

    # -- ajout ---------------------------------------------------------------

    @on(Button.Pressed, "#add")
    def _add(self) -> None:
        if self._current is None or self._indexers is None:
            return
        values = {
            inp.id.removeprefix("fld-"): inp.value
            for inp in self.query(".indexer-field").results(Input)
            if inp.id
        }
        self._set_status(
            t("[dim]Validation de {nom} par Prowlarr...[/dim]", nom=self._current.name)
        )
        self.query_one("#add", Button).disabled = True
        self.submit(self._current, values)

    @work(thread=True)
    def submit(self, definition: IndexerDefinition, values: dict[str, str]) -> None:
        """Ajoute l'indexeur, et ne laisse RIEN s'echapper.

        Une exception levee dans un worker Textual arrete l'application : le
        terminal se ferme, et l'utilisateur perd tout ce qu'il venait de saisir.
        `add` protege son propre appel HTTP, mais pas `configured()` ni
        `app_profile_id()`, qui interrogent Prowlarr eux aussi. Constate a
        l'usage : saisie d'un tracker, clic sur Ajouter, fenetre disparue.
        """
        if self._indexers is None:
            return
        try:
            ok, message = self._indexers.add(definition, values)
            already = [i.get("name", "?") for i in self._indexers.configured()]
        except Exception as exc:  # noqa: BLE001 - aucune ne doit tuer l'assistant
            journal.LOGGER.exception("ajout de l'indexeur %s", definition.name)
            ok, message = False, f"{type(exc).__name__} : {exc}"
            already = []
        try:
            # `call_from_thread` RENVOIE au fil appelant ce que le rappel a leve.
            # L'appel etait hors du `try`, donc une erreur d'affichage remontait
            # dans le worker, hors de toute garde, et Textual arretait
            # l'application. Le `assert` qui precedait avait le meme defaut.
            self.app.call_from_thread(self._added, definition.name, ok, message, already)
        except Exception:  # noqa: BLE001
            journal.LOGGER.exception("affichage du resultat pour %s", definition.name)

    def _added(self, name: str, ok: bool, message: str, already: list[str]) -> None:
        # On ASSEMBLE le contenu au lieu de l'ecrire en balisage. Ces trois
        # textes viennent de Prowlarr et de l'indexeur contacte : les faire
        # passer par l'analyseur de balisage revient a lui donner du texte
        # arbitraire. Le message reel de C411 le montre bien :
        #
        #   Unable to connect: ... [401:Unauthorized] [GET] at [https://c411.org
        #   /api/torznab?apikey=...&t=search&l
        #
        # tronque en pleine URL, il laisse un `[` ouvert et Textual leve
        # « Expected markup value ». L'assistant se fermait la, sans une ligne
        # de journal. Ni `rich.markup.escape` ni `textual.markup.escape` n'y
        # changent quoi que ce soit : verifie, tous deux rendent cette chaine
        # INCHANGEE. Seul un `Content` construit a la main est sur — et il
        # preserve au passage les noms comme `Torrent[CORE]`, que l'analyseur
        # amputait de la moitie.
        couleur = "green" if ok else "red"
        noms = ", ".join(already) or "aucun"
        self.query_one("#indexer-status", Static).update(
            Content(f"{name} : {message}").stylize(couleur)
            + Content("\n")
            + Content(f"Configures : {noms}").stylize("dim")
        )
        self.query_one("#add", Button).disabled = False
        self.query_one("#skip", Button).label = "Continuer"

    # -- sortie --------------------------------------------------------------

    # -- sauvegarde Prowlarr -----------------------------------------------

    @on(Button.Pressed, "#backup-inspect")
    def _inspect_backup(self) -> None:
        chemin = self.query_one("#backup-path", Input).value.strip().strip('"')
        if not chemin:
            self._set_status(t("[yellow]Indiquez le chemin de la sauvegarde Prowlarr.[/yellow]"))
            return
        if self._indexers is None:
            self._set_status(t("[yellow]Prowlarr n'est pas encore pret.[/yellow]"))
            return
        self.query_one("#backup-inspect", Button).disabled = True
        self.inspect_backup(chemin)

    @work(thread=True)
    def inspect_backup(self, chemin: str) -> None:
        from pathlib import Path

        try:
            sauvegarde = import_prowlarr.lire(Path(chemin))
            statuts = import_prowlarr.examiner(sauvegarde, self._indexers)
        except Exception as exc:  # noqa: BLE001 - un fichier illisible se dit, sans planter
            self.app.call_from_thread(
                self._set_status, t("[red]Sauvegarde illisible : {erreur}[/red]", erreur=escape(str(exc)))
            )
            self.app.call_from_thread(self._inspect_done, [])
            return
        self.app.call_from_thread(self._inspect_done, statuts)

    def _inspect_done(self, statuts: list) -> None:
        self.query_one("#backup-inspect", Button).disabled = False
        liste = self.query_one("#backup-list", SelectionList)
        liste.clear_options()
        self._sauvegarde = {}
        libelles = {
            import_prowlarr.IMPORTABLE: t("a importer"),
            import_prowlarr.CONFIGURE: t("deja configure"),
            import_prowlarr.INCONNU: t("inconnu de ce Prowlarr"),
        }
        for rang, (entree, statut) in enumerate(statuts):
            cle = f"i{rang}"
            importable = statut == import_prowlarr.IMPORTABLE
            if importable:
                self._sauvegarde[cle] = entree
            liste.add_option(
                Selection(
                    f"{escape(entree.name)}  [dim]{escape(libelles.get(statut, statut))}[/dim]",
                    cle,
                    importable,
                    disabled=not importable,
                )
            )
        liste.set_class(not statuts, "hidden")
        self.query_one("#backup-import", Button).set_class(not self._sauvegarde, "hidden")
        if statuts:
            decompte = t(
                "[dim]{importables} indexeur(s) a importer sur {total} dans la sauvegarde.[/dim]",
                importables=len(self._sauvegarde),
                total=len(statuts),
            )
            # Le compte rendu d'un import vient d'etre affiche : il reste au-dessus.
            self._set_status("\n".join([*self._dernier_import, decompte]))
        self._dernier_import = []

    @on(Button.Pressed, "#backup-import")
    def _import_backup(self) -> None:
        choisis = [
            self._sauvegarde[cle]
            for cle in self.query_one("#backup-list", SelectionList).selected
            if cle in self._sauvegarde
        ]
        if not choisis or self._indexers is None:
            return
        self.query_one("#backup-import", Button).disabled = True
        self.import_backup(choisis)

    @work(thread=True)
    def import_backup(self, choisis: list) -> None:
        lignes = []
        for entree in choisis:
            try:
                ok, message, avertissements = import_prowlarr.importer(entree, self._indexers)
            except Exception as exc:  # noqa: BLE001 - un indexeur en echec n'arrete pas les suivants
                ok, message, avertissements = False, str(exc), []
            marque = "[green]OK[/green]" if ok else "[red]ECHEC[/red]"
            lignes.append(f"{marque} {escape(entree.name)} : {escape(message)}")
            lignes.extend(f"   [yellow]{escape(a)}[/yellow]" for a in avertissements)
        self.app.call_from_thread(self._import_done, lignes)

    def _import_done(self, lignes: list[str]) -> None:
        self._set_status("\n".join(lignes))
        self._dernier_import = lignes
        self.query_one("#backup-import", Button).disabled = False
        self.query_one("#skip", Button).label = "Continuer"
        # La liste reflete ce qui reste : on reexamine.
        self._inspect_backup()

    @on(Button.Pressed, "#skip")
    def _skip(self) -> None:
        if self._client is not None:
            self._client.close()
        from .screens import ReportScreen

        self.app.push_screen(ReportScreen())
