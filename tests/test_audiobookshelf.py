"""Audiobookshelf : les deux bibliotheques que rien ne pilotait.

`books` et `audiobooks` existent depuis la 0.1.12 mais aucune application ne
les remplissait — PlugArr rangeait sans lire. C'est le premier des cinq
services demandes a entrer au catalogue.

Trois pieges releves contre une instance reelle en 2.36.0, et chacun a coute
une fausse piste avant d'etre compris.

**Il met quarante secondes a demarrer.** Migrations, declencheurs SQLite,
ANALYZE, puis seulement il ecoute. Sonde plus tot, `/` repond 404 et on conclut
que l'image est cassee. Elle ne l'est pas.

**Sa base SQLite se lit avec son journal `-wal`, ou pas du tout.** Copier
`absdatabase.sqlite` seul montre une table `users` vide pendant que `/status`
annonce `isInit: true`. L'incoherence est dans la lecture, pas dans le serveur.

**`POST /init` ne rend AUCUN jeton.** Il repond 200 avec un corps vide, la ou
Silo en renvoie deux. Sans connexion explicite ensuite, l'appel suivant repond
401 — et le message d'aide envoie chercher un accueil deja fait qui n'existe
pas. Constate au premier essai reel : 0 liaison sur 1.
"""

from __future__ import annotations

import pytest

from plugarr import catalog, compose, orchestrator
from plugarr.clients.audiobookshelf import PROVIDERS, AudiobookshelfClient
from plugarr.wiring import Wirer


def _cfg(*services: str):
    return orchestrator.build_config(
        services=list(services or ("audiobookshelf",)), config_root="/c", data_root="/d"
    )


# ------------------------------------------------------------------ catalogue


def test_le_service_est_choisissable():
    assert "audiobookshelf" in {s.id for s in catalog.selectable()}


def test_l_image_est_epinglee_au_digest():
    """Regle du projet : aucun tag flottant au catalogue."""
    image = catalog.get("audiobookshelf").image

    assert "@sha256:" in image
    assert ":latest" not in image


def test_il_recoit_un_compte():
    """Sans mot de passe genere, l'accueil ne peut pas se faire seul."""
    cfg = _cfg()

    assert cfg.services["audiobookshelf"].password


# -------------------------------------------------------------------- compose


def test_les_deux_bibliotheques_sont_montees():
    """C'est toute la raison de l'inscrire : `books` et `audiobooks`
    existaient sans personne pour les lire."""
    volumes = compose.build_compose(_cfg())["services"]["audiobookshelf"]["volumes"]

    assert any(v.startswith("${DATA_ROOT}/media/books:") for v in volumes)
    assert any(v.startswith("${DATA_ROOT}/media/audiobooks:") for v in volumes)


def test_les_medias_sont_montes_en_lecture_seule():
    """Audiobookshelf lit, il n'organise pas. Le montage rend la cohabitation
    sure plutot que simplement probable."""
    volumes = compose.build_compose(_cfg())["services"]["audiobookshelf"]["volumes"]

    for v in volumes:
        if v.startswith("${DATA_ROOT}"):
            assert v.endswith(":ro"), v


def test_la_configuration_et_les_metadonnees_sont_separees():
    """`/metadata` porte les couvertures et les donnees extraites. Le confondre
    avec `/config` gonfle les sauvegardes de centaines de Mo pour rien."""
    volumes = compose.build_compose(_cfg())["services"]["audiobookshelf"]["volumes"]

    assert any(v.endswith(":/config") for v in volumes)
    assert any(v.endswith(":/metadata") for v in volumes)


def test_le_port_publie_n_est_pas_celui_du_conteneur():
    """Il ecoute sur 80 ; 13378 est la convention cote hote de son projet."""
    spec = catalog.get("audiobookshelf")

    assert spec.internal_port == 80
    assert spec.default_host_port == 13378


# --------------------------------------------------------------------- plan


def test_l_etape_est_au_plan():
    assert "audiobookshelf/setup" in [e.name for e in Wirer(_cfg()).build_plan()]


def test_aucune_etape_s_il_n_est_pas_installe():
    assert "audiobookshelf/setup" not in [
        e.name for e in Wirer(_cfg("sonarr")).build_plan()
    ]


def test_le_cablage_se_connecte_TOUJOURS_apres_l_accueil():
    """Le defaut qui a donne 0 liaison sur 1 au premier essai reel.

    `POST /init` repond 200 avec un corps VIDE et ne rend aucun jeton — la ou
    l'accueil de Silo en renvoie deux. Ne se connecter que lorsque l'accueil
    avait DEJA ete fait laissait le client sans jeton juste apres l'avoir
    fait, et l'appel suivant repondait 401.
    """
    import inspect

    source = inspect.getsource(Wirer.step_audiobookshelf_setup)
    avant = source.index("setup(")
    apres = source.index("login(")

    assert apres > avant, "la connexion doit suivre l'accueil"
    assert "if not cree" not in source, "la connexion est redevenue conditionnelle"


# -------------------------------------------------------------------- client


class _Faux(AudiobookshelfClient):
    """Journalise les appels au lieu de les emettre."""

    def __init__(self, *, init=False, libs=None):
        self.name = "faux"
        self._token = None
        self._init = init
        self._libs = list(libs or [])
        self.appels: list[tuple[str, str]] = []

    def _request(self, method, path, **kw):
        self.appels.append((method, path))
        if path == "/status":
            return {"isInit": self._init, "serverVersion": "2.36.0"}
        if path == "/init":
            self._init = True
            return None  # corps VIDE : c'est le piege
        if path == "/login":
            return {"user": {"accessToken": "jeton"}}
        if path == "/api/libraries" and method == "GET":
            return {"libraries": self._libs}
        if path == "/api/libraries" and method == "POST":
            self._libs.append({"id": "x", "name": kw["json"]["name"], "folders": kw["json"]["folders"]})
        return None


def test_l_accueil_ne_se_rejoue_pas():
    """`POST /init` repond 500 si un compte racine existe : on relit l'etat
    plutot que d'interpreter un code d'erreur."""
    assert _Faux(init=True).setup(username="u", password="p") is False
    assert _Faux(init=False).setup(username="u", password="p") is True


def test_un_mot_de_passe_vide_est_refuse():
    """Audiobookshelf l'accepterait avec un simple avertissement dans son
    journal. Un serveur media sans mot de passe est une porte ouverte."""
    from plugarr.clients.base import WiringError

    with pytest.raises(WiringError, match="mot de passe vide"):
        _Faux().setup(username="u", password="")


def test_les_bibliotheques_se_lisent_dans_un_objet():
    """La reponse est `{"libraries": [...]}`, pas un tableau."""
    assert _Faux(libs=[{"id": "1", "name": "Livres"}]).libraries()[0]["name"] == "Livres"


def test_le_doublon_se_juge_sur_le_chemin():
    """Deux bibliotheques sur le meme dossier scanneraient tout deux fois, et
    se fier au nom ferait echouer un second passage apres un renommage."""
    faux = _Faux(libs=[{"id": "1", "name": "Ancien nom", "folders": [{"fullPath": "/books"}]}])

    assert faux.ensure_library("Nouveau nom", "/books") is False
    assert faux.ensure_library("Livres audio", "/audiobooks") is True


def test_chaque_bibliotheque_a_son_fournisseur():
    """`audible` pour ce qui s'ecoute, `google` pour ce qui se lit."""
    assert PROVIDERS["audiobooks"] == "audible"
    assert PROVIDERS["books"] == "google"


def test_un_compte_existant_retrouve_le_mot_de_passe_d_une_installation_precedente(monkeypatch):
    """Reinstallation reelle du 25/09/2026 : HTTP 401, alors que le mot de passe
    accepte etait dans un stack.yml precedent (stack.yml.5)."""
    from plugarr import reprise
    from plugarr.clients import audiobookshelf as module_abs
    from plugarr.clients.base import WiringError

    cfg = _cfg("audiobookshelf")
    cfg.services["audiobookshelf"].password = "genere-ce-passage"
    essais = []

    class Faux:
        def __init__(self, *_a, **_k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def wait_ready(self):
            pass

        def setup(self, **_kw):
            return False

        def login(self, _user, mot):
            essais.append(mot)
            if mot != "celui-du-premier-passage":
                raise WiringError("audiobookshelf: POST /login a echoue", "HTTP 401", "")

        def ensure_library(self, *_a, **_k):
            return False

        def libraries(self):
            return [{"id": "a"}, {"id": "b"}]

        def scan(self, _id):
            return True

    monkeypatch.setattr(module_abs, "AudiobookshelfClient", Faux)
    monkeypatch.setattr(
        reprise, "mots_de_passe_connus", lambda *_a, **_k: ["celui-du-premier-passage"]
    )
    wirer = Wirer(cfg)

    resultat = wirer.step_audiobookshelf_setup()

    assert essais == ["genere-ce-passage", "celui-du-premier-passage"]
    assert cfg.services["audiobookshelf"].password == "celui-du-premier-passage"
    assert "audiobookshelf" in wirer.recuperations
    assert resultat.ok


def test_sa_configuration_existante_est_signalee_comme_non_relisible(tmp_path):
    cfg = orchestrator.build_config(
        services=["audiobookshelf"], config_root=str(tmp_path / "c"), data_root=str(tmp_path / "d")
    )
    dossier = tmp_path / "c" / "audiobookshelf"
    dossier.mkdir(parents=True)
    (dossier / "absdatabase.sqlite").write_bytes(b"x")

    assert "audiobookshelf" in orchestrator.unusable_configs(cfg)
