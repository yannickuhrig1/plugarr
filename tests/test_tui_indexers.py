"""Tests de l'ecran indexeurs. Aucun reseau : le chargement est neutralise."""

from __future__ import annotations

import pytest
from textual.widgets import Button, Input, Label, Static

from plugarr.clients.prowlarr import IndexerDefinition
from plugarr.tui.app import PlugArrApp
from plugarr.tui.indexers import IndexersScreen
from plugarr.tui.screens import ReportScreen

DEFINITION = IndexerDefinition(
    name="Exemple",
    implementation="Torznab",
    privacy="private",
    protocol="torrent",
    language="fr-FR",
    description="Definition fictive.",
    raw={
        "indexerUrls": ["https://un.invalid/", "https://deux.invalid/"],
        "fields": [
            {"name": "baseUrl", "type": "select", "label": "Url", "value": None},
            {"name": "apiKey", "type": "textbox", "label": "API Key", "privacy": "apiKey"},
            {"name": "baseSettings.queryLimit", "type": "number", "label": "Limite"},
            {"name": "info_help", "type": "info", "label": "Aide"},
        ],
    },
)


@pytest.fixture(autouse=True)
def _sans_registres(monkeypatch):
    """Le rapport cherche les mises a jour dans les registres : jamais en test."""
    from plugarr import updates

    monkeypatch.setattr(updates, "disponibles", lambda _cfg: {"updates": [], "unchecked": []})


@pytest.fixture
def screen_app(tmp_path, monkeypatch):
    monkeypatch.setattr(IndexersScreen, "load_definitions", lambda self: None)
    app = PlugArrApp(project_dir=tmp_path)
    app.selection = ["prowlarr"]
    app.stack_config = app.build_config()
    return app


@pytest.mark.asyncio
async def test_intro_states_that_plugarr_provides_no_indexer(screen_app):
    """La position juridique du projet doit etre lisible a l'ecran, pas seulement
    dans le README."""
    async with screen_app.run_test() as pilot:
        await pilot.app.push_screen(IndexersScreen())
        await pilot.pause()
        intro = str(pilot.app.screen.query_one("#indexers-intro", Static).content)
        assert "aucun" in intro.lower()
        assert "votre propre Prowlarr" in intro


@pytest.mark.asyncio
async def test_intro_warns_that_adding_contacts_the_indexer(screen_app):
    """Prowlarr contacte l'indexeur pour valider : l'utilisateur doit le savoir
    avant de cliquer."""
    async with screen_app.run_test() as pilot:
        await pilot.app.push_screen(IndexersScreen())
        await pilot.pause()
        intro = str(pilot.app.screen.query_one("#indexers-intro", Static).content)
        assert "contacte" in intro


@pytest.mark.asyncio
async def test_the_step_can_be_skipped(screen_app, appuyer):
    async with screen_app.run_test() as pilot:
        await pilot.app.push_screen(IndexersScreen())
        await pilot.pause()
        pilot.app.results = []
        assert await appuyer(
            pilot, "#skip", lambda: isinstance(pilot.app.screen, ReportScreen)
        )


@pytest.mark.asyncio
async def test_add_is_disabled_until_an_indexer_is_chosen(screen_app):
    async with screen_app.run_test() as pilot:
        await pilot.app.push_screen(IndexersScreen())
        await pilot.pause()
        assert pilot.app.screen.query_one("#add", Button).disabled is True


@pytest.mark.asyncio
async def test_form_shows_credentials_and_hides_tuning_fields(screen_app):
    async with screen_app.run_test() as pilot:
        await pilot.app.push_screen(IndexersScreen())
        await pilot.pause()
        screen = pilot.app.screen
        await screen._render_form(DEFINITION)
        await pilot.pause()

        names = {inp.id for inp in screen.query(".indexer-field").results(Input)}
        assert names == {"fld-baseUrl", "fld-apiKey"}
        assert screen.query_one("#add", Button).disabled is False


@pytest.mark.asyncio
async def test_secret_fields_are_masked_on_screen(screen_app):
    async with screen_app.run_test() as pilot:
        await pilot.app.push_screen(IndexersScreen())
        await pilot.pause()
        screen = pilot.app.screen
        await screen._render_form(DEFINITION)
        await pilot.pause()
        masked = {inp.id: inp.password for inp in screen.query(".indexer-field").results(Input)}
        assert masked == {"fld-baseUrl": False, "fld-apiKey": True}


@pytest.mark.asyncio
async def test_base_url_is_prefilled_from_the_definition(screen_app):
    """Sans cela l'utilisateur devrait deviner l'adresse du tracker."""
    async with screen_app.run_test() as pilot:
        await pilot.app.push_screen(IndexersScreen())
        await pilot.pause()
        screen = pilot.app.screen
        await screen._render_form(DEFINITION)
        await pilot.pause()
        url = screen.query_one("#fld-baseUrl", Input)
        assert url.value == "https://un.invalid/"


@pytest.mark.asyncio
async def test_rendering_a_second_indexer_replaces_the_first_form(screen_app):
    """Sinon les champs du precedent resteraient a l'ecran et seraient envoyes."""
    other = IndexerDefinition(
        name="Autre",
        implementation="X",
        privacy="public",
        protocol="usenet",
        language="en",
        description="",
        raw={"indexerUrls": [], "fields": [{"name": "cookie", "type": "textbox"}]},
    )
    async with screen_app.run_test() as pilot:
        await pilot.app.push_screen(IndexersScreen())
        await pilot.pause()
        screen = pilot.app.screen
        await screen._render_form(DEFINITION)
        await pilot.pause()
        await screen._render_form(other)
        await pilot.pause()
        names = {inp.id for inp in screen.query(".indexer-field").results(Input)}
        assert names == {"fld-cookie"}


# ------------------------------------------------- le plantage de la 0.1.5


#: Deux definitions qui PARTAGENT un nom de champ. C'est le cas courant :
#: `baseUrl` existe dans presque toutes les definitions de Prowlarr. Le test
#: precedent en comparait deux aux champs disjoints, et passait donc au vert
#: pendant que l'assistant se fermait chez l'utilisateur.
JUMELLE_A = IndexerDefinition(
    name="Tr4cker",
    implementation="Torznab",
    privacy="private",
    protocol="torrent",
    language="fr-FR",
    description="",
    raw={
        "indexerUrls": ["https://a.invalid/"],
        "fields": [
            {"name": "baseUrl", "type": "select", "label": "Url", "value": None},
            {"name": "apiKey", "type": "textbox", "label": "API Key", "privacy": "apiKey"},
        ],
    },
)
JUMELLE_B = IndexerDefinition(
    name="Torrent[CORE]",
    implementation="Torznab",
    privacy="private",
    protocol="torrent",
    language="fr-FR",
    description="",
    raw={
        "indexerUrls": ["https://b.invalid/"],
        "fields": [
            {"name": "baseUrl", "type": "select", "label": "Url", "value": None},
            {"name": "apiKey", "type": "textbox", "label": "API Key", "privacy": "apiKey"},
        ],
    },
)


@pytest.mark.asyncio
async def test_deux_indexeurs_aux_memes_champs_ne_tuent_pas_l_assistant(screen_app):
    """Le plantage signale : chercher, cliquer un indexeur, puis un autre, et
    l'application se fermait net.

    `remove_children()` rend la main AVANT que le DOM ait bouge. Le second
    formulaire montait donc un `#fld-baseUrl` alors que le premier existait
    encore, et Textual levait `DuplicateIds` depuis un gestionnaire d'evenement
    — ce qui arrete l'application. Reproduit sur un Prowlarr reel : 39 des 40
    correspondances de « tr » plantaient a la seconde selection.
    """
    async with screen_app.run_test() as pilot:
        await pilot.app.push_screen(IndexersScreen())
        await pilot.pause()
        screen = pilot.app.screen

        await screen._render_form(JUMELLE_A)
        await screen._render_form(JUMELLE_B)
        await pilot.pause()

        assert screen.query_one("#fld-baseUrl", Input).value == "https://b.invalid/"
        assert len(screen.query("#fld-baseUrl")) == 1


@pytest.mark.asyncio
async def test_dix_allers_retours_de_suite(screen_app):
    """Un utilisateur compare plusieurs indexeurs avant de choisir."""
    async with screen_app.run_test() as pilot:
        await pilot.app.push_screen(IndexersScreen())
        await pilot.pause()
        screen = pilot.app.screen

        for i in range(10):
            await screen._render_form(JUMELLE_A if i % 2 else JUMELLE_B)

        assert len(screen.query(".indexer-field")) == 2


@pytest.mark.asyncio
async def test_un_nom_a_crochets_reste_lisible(screen_app):
    """`Torrent[CORE]` existe vraiment dans Prowlarr. Le nom traverse notre
    balisage : mal echappe, une balise fermante isolee ferait lever MarkupError
    en plein rendu de la liste."""
    async with screen_app.run_test() as pilot:
        await pilot.app.push_screen(IndexersScreen())
        await pilot.pause()
        screen = pilot.app.screen
        screen._indexers = _FauxCatalogue([JUMELLE_B, JUMELLE_A])

        screen.query_one("#indexer-search", Input).value = "to"
        await pilot.pause()

        libelles = [str(w.content) for w in screen.query_one("#indexer-results").query(Label)]
        assert any("Torrent[CORE]" in libelle for libelle in libelles)


class _FauxCatalogue:
    def __init__(self, definitions):
        self._definitions = definitions

    def search(self, terme, limite):
        besoin = terme.strip().lower()
        return [d for d in self._definitions if besoin in d.name.lower()][:limite]


@pytest.mark.asyncio
async def test_un_message_de_prowlarr_a_balise_ne_ferme_pas_l_assistant(screen_app):
    """Les messages viennent de Prowlarr et de l'indexeur contacte.

    Ils atterrissaient dans NOTRE balisage. Le message reel de C411 le montre :

        Unable to connect: ... [401:Unauthorized] [GET] at [https://c411.org
        /api/torznab?apikey=...&t=search&l

    tronque en pleine URL, il laisse un `[` ouvert et Textual leve « Expected
    markup value ». Ni `rich.markup.escape` ni `textual.markup.escape` n'y
    changent rien — tous deux rendent cette chaine INCHANGEE. Le contenu est
    donc assemble, jamais analyse.
    """
    reel = (
        "Unable to connect: to indexer. HTTP request failed: [401:Unauthorized] [GET] at "
        "[https://c411.org/api/torznab?apikey=...&t=search&l"
    )
    async with screen_app.run_test() as pilot:
        await pilot.app.push_screen(IndexersScreen())
        await pilot.pause()
        screen = pilot.app.screen

        screen._added("C411", False, reel, ["Torrent[CORE]"])
        await pilot.pause()

        affiche = screen.query_one("#indexer-status", Static).content.plain

        # Tout doit survivre a l'affichage : un diagnostic ampute ne sert a rien.
        assert "C411" in affiche
        assert "[401:Unauthorized]" in affiche
        assert "[GET]" in affiche, "l'analyseur de balisage mangeait ce jeton"
        assert "Torrent[CORE]" in affiche, "l'analyseur amputait ce nom de moitie"


@pytest.mark.asyncio
async def test_une_erreur_d_affichage_ne_remonte_pas_dans_le_worker(screen_app, monkeypatch):
    """`call_from_thread` RENVOIE au fil appelant ce que le rappel a leve.

    L'appel etait hors de la garde : une erreur d'affichage remontait donc dans
    le worker, hors de tout `try`, et Textual arretait l'application.
    """
    async with screen_app.run_test() as pilot:
        await pilot.app.push_screen(IndexersScreen())
        await pilot.pause()
        screen = pilot.app.screen
        screen._indexers = _FauxCatalogue([JUMELLE_A])
        monkeypatch.setattr(
            type(screen), "_added", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boum"))
        )
        monkeypatch.setattr(
            _FauxCatalogue, "add", lambda self, d, v: (True, "ok"), raising=False
        )
        monkeypatch.setattr(
            _FauxCatalogue, "configured", lambda self: [], raising=False
        )

        # Le worker tourne dans un fil : on appelle le corps directement, ce qui
        # exerce exactement le chemin qui tuait l'application.
        screen.submit.__wrapped__(screen, JUMELLE_A, {})

        assert pilot.app._exception is None


@pytest.mark.asyncio
async def test_une_sauvegarde_prowlarr_se_reprend_dans_le_tui(screen_app, monkeypatch, attendre, tmp_path):
    """Parite avec l'assistant web : reprendre les indexeurs d'une sauvegarde
    Prowlarr au lieu de tout ressaisir. Seuls les importables sont coches."""
    from textual.widgets import SelectionList

    from plugarr import import_prowlarr

    class Entree:
        def __init__(self, name):
            self.name = name

    a_importer, deja = Entree("Tracker A"), Entree("Tracker B")
    sauvegarde = object()
    monkeypatch.setattr(import_prowlarr, "lire", lambda chemin: sauvegarde)
    monkeypatch.setattr(
        import_prowlarr,
        "examiner",
        lambda s, idx: [(a_importer, import_prowlarr.IMPORTABLE), (deja, import_prowlarr.CONFIGURE)],
    )
    importes = []
    monkeypatch.setattr(
        import_prowlarr,
        "importer",
        lambda entree, idx: importes.append(entree.name) or (True, "ajoute", []),
    )
    fichier = tmp_path / "prowlarr_backup.zip"
    fichier.write_bytes(b"x")

    async with screen_app.run_test() as pilot:
        await pilot.app.push_screen(IndexersScreen())
        await pilot.pause()
        ecran = pilot.app.screen
        ecran._indexers = object()
        ecran.query_one("#backup-path", Input).value = str(fichier)
        ecran.query_one("#backup-inspect", Button).press()
        liste = ecran.query_one("#backup-list", SelectionList)
        assert await attendre(pilot, lambda: liste.option_count == 2)

        assert liste.selected == ["i0"]
        ecran.query_one("#backup-import", Button).press()
        statut = ecran.query_one("#indexer-status", Static)
        # Le compte rendu survit au nouvel examen qui suit l'import.
        assert await attendre(
            pilot,
            lambda: "Tracker A" in str(statut.render()) and "a importer sur" in str(statut.render()),
        )

    assert importes == ["Tracker A"]
