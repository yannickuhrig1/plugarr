"""DroppedNeedle : la musique, de la demande au rangement.

Il REMPLACE Lidarr plutot qu'il ne le complete, et il est reste hors du
catalogue tant qu'aucun client de telechargement ne l'accompagnait. C'est
SABnzbd qui l'a debloque.

Une note de la feuille de route affirmait « son premier compte administrateur
se cree par l'interface web ». **C'etait faux** : `POST /api/v1/auth/setup`
existe, rend 201 avec un jeton, et 409 si l'accueil a deja eu lieu.

Deux defauts trouves en l'integrant, aucun des deux visible autrement.

**Sa base ne survivait pas au conteneur.** La table `auth_users` vit dans
`/app/cache/library.db`, et le compose amont ne monte que `/app/config`.
L'accueil reussissait, puis la connexion avec les identifiants annonces
repondait 401 apres un simple redemarrage.

**Sa base ne supporte pas un montage Windows.** Montee sur le disque de l'hote,
sa verification apres mise a jour echoue et le conteneur refuse de demarrer :
« The upgraded library database could not be verified after installation ». Meme
remede que pour la base de Silo — un volume Docker nomme — et probablement meme
cause : SQLite et la couche de partage de fichiers de Docker Desktop.

Ce second cas a fait generaliser les volumes nommes, jusque-la codes en dur en
cinq endroits pour le seul PostgreSQL de Silo.
"""

from __future__ import annotations

import pytest

from plugarr import catalog, compose, orchestrator
from plugarr.clients.base import WiringError
from plugarr.clients.droppedneedle import DroppedNeedleClient
from plugarr.wiring import Wirer


def _cfg(*services: str):
    return orchestrator.build_config(
        services=list(services or ("droppedneedle",)), config_root="/c", data_root="/d"
    )


# ------------------------------------------------------------------ catalogue


def test_le_service_est_choisissable():
    assert "droppedneedle" in {s.id for s in catalog.selectable()}


def test_l_image_est_epinglee_au_digest():
    assert "@sha256:" in catalog.get("droppedneedle").image


def test_il_tire_un_client_de_telechargement():
    """Sans client, il chercherait sans jamais rien obtenir. C'est ce qui l'a
    tenu hors du catalogue jusqu'a l'arrivee de SABnzbd."""
    assert "sabnzbd" in _cfg("droppedneedle").services


def test_il_recoit_un_compte():
    inst = _cfg().services["droppedneedle"]

    assert inst.username and inst.password


# ------------------------------------------------------------------ volumes


def test_sa_base_vit_dans_un_volume_nomme():
    """Deux raisons, mesurees : elle ne survit pas a la recreation du conteneur
    si elle reste dans /app/cache non monte, et elle refuse de demarrer si on
    la met sur un montage Windows."""
    assert catalog.get("droppedneedle").named_volumes == (
        ("droppedneedle-cache", "/app/cache"),
    )


def test_le_volume_est_declare_et_monte():
    doc = compose.build_compose(_cfg())

    assert "droppedneedle-cache" in doc.get("volumes", {})
    assert "droppedneedle-cache:/app/cache" in doc["services"]["droppedneedle"]["volumes"]


def test_les_volumes_nommes_sont_deduits_du_catalogue():
    """Ils etaient codes en dur en cinq endroits pour le seul PostgreSQL de
    Silo. Le deuxieme cas a rendu la generalisation obligatoire."""
    cfg = _cfg("droppedneedle", "silo")
    cfg.project_name = "essai"

    assert orchestrator.volumes_nommes(cfg, "droppedneedle") == ["essai_droppedneedle-cache"]
    assert orchestrator.volumes_nommes(cfg, "silo-postgres") == ["essai_silo-pgdata"]
    assert orchestrator.volumes_nommes(cfg, "sonarr") == []


def test_un_volume_survivant_rend_la_reprise_impossible(monkeypatch):
    """Son compte administrateur vit dans ce volume. Reinstaller par-dessus
    genererait un mot de passe que l'application refuserait — meme piege que la
    base de Silo."""
    monkeypatch.setattr(orchestrator, "volume_exists", lambda n: True)

    assert "droppedneedle" in orchestrator.unusable_configs(_cfg())


def test_il_voit_data_en_entier():
    """`downloads_mount` n'a alors rien a remapper : DroppedNeedle voit les
    telechargements termines la ou SABnzbd les depose, et l'import LIE le
    fichier au lieu de le recopier."""
    volumes = compose.build_compose(_cfg())["services"]["droppedneedle"]["volumes"]

    assert "${DATA_ROOT}:/data" in volumes


# ------------------------------------------------------------------ plan


def test_il_passe_apres_les_categories_de_sabnzbd():
    """Il cite la categorie `music` : elle doit deja porter son repertoire."""
    noms = [e.name for e in Wirer(_cfg()).build_plan()]

    assert noms.index("sabnzbd/categories") < noms.index("droppedneedle/setup")


def test_il_passe_apres_jellyfin_quand_il_est_la():
    """Il reprend la cle API que l'etape Jellyfin vient de creer."""
    noms = [e.name for e in Wirer(_cfg("droppedneedle", "jellyfin")).build_plan()]

    assert noms.index("jellyfin/setup") < noms.index("droppedneedle/setup")


def test_jellyfin_n_est_pas_exige():
    """Il sait tenir une bibliotheque locale seul : forcer un serveur media a
    qui ne veut que de la musique n'aurait pas de sens."""
    assert "jellyfin" not in _cfg("droppedneedle").services


# ------------------------------------------------------------------ client


class _Faux(DroppedNeedleClient):
    """Journalise les corps envoyes au lieu de les emettre."""

    def __init__(self, *, requis=True, sabnzbd=None, jellyfin=None):
        self.name = "faux"
        self._requis = requis
        self._sab = dict(sabnzbd or {})
        self._jf = dict(jellyfin or {})
        self.corps: list[tuple[str, dict]] = []

    def _request(self, method, path, **kw):
        corps = kw.get("json") or {}
        self.corps.append((f"{method} {path}", corps))
        if path == "/auth/setup/status":
            return {"required": self._requis}
        if path == "/auth/setup":
            self._requis = False
            return {"token": "jeton"}
        if path == "/auth/login":
            return {"token": "jeton"}
        if path == "/settings/jellyfin":
            if method == "GET":
                return dict(self._jf)
            self._jf.update(corps)
            return None
        if path == "/download-clients/sabnzbd":
            if method == "GET":
                return dict(self._sab)
            self._sab.update(corps)
            return None
        if path.endswith("/test"):
            return {"valid": True, "message": "ok"}
        return None


def test_l_accueil_ne_se_rejoue_pas():
    """Un second appel rendrait 409 « Setup has already been completed »."""
    assert _Faux(requis=True).setup(username="u", password="p") is True
    assert _Faux(requis=False).setup(username="u", password="p") is False


def test_l_adresse_est_fabriquee_sous_invalid():
    """Elle est obligatoire. `.invalid` est reserve par la RFC 2606 et ne peut
    par construction jamais resoudre."""
    faux = _Faux()

    faux.setup(username="plugarr", password="p")

    assert faux.corps[-1][1]["email"].endswith("@plugarr.invalid")


def test_le_client_de_telechargement_recoit_le_montage_partage():
    """Son schema le dit : « downloads_mount is where DroppedNeedle sees
    SABnzbd's completed dir »."""
    faux = _Faux(sabnzbd={"enabled": False})

    faux.ensure_sabnzbd(
        url="http://sabnzbd:8080", api_key="CLE", categorie="music", montage="/data/usenet"
    )

    envoye = faux.corps[-1][1]
    assert envoye["downloads_mount"] == "/data/usenet"
    assert envoye["category"] == "music"
    assert envoye["enabled"] is True


def test_declarer_deux_fois_ne_change_rien():
    faux = _Faux(sabnzbd={"enabled": False})
    args = {
        "url": "http://sabnzbd:8080",
        "api_key": "CLE",
        "categorie": "music",
        "montage": "/data/usenet",
    }

    assert faux.ensure_sabnzbd(**args) is True
    assert faux.ensure_sabnzbd(**args) is False


def test_le_serveur_media_ne_perd_pas_ses_autres_reglages():
    """N'ecrire que deux champs effacerait `user_id`."""
    faux = _Faux(jellyfin={"jellyfin_url": "", "user_id": "abc", "login_enabled": True})

    faux.ensure_jellyfin(url="http://jellyfin:8096", api_key="CLE")

    envoye = faux.corps[-1][1]
    assert envoye["user_id"] == "abc"
    assert envoye["login_enabled"] is True
    assert envoye["enabled"] is True


def test_le_verdict_du_test_se_lit_dans_valid():
    """Le champ s'appelle `valid`, pas `success`. Le lire au mauvais nom
    faisait passer chaque test pour un echec."""
    ok, _message = _Faux(sabnzbd={"url": "x"}).test_sabnzbd()

    assert ok is True


def test_une_erreur_de_test_ne_leve_pas():
    """Un test qui echoue est un resultat, pas une panne du cablage."""

    class _Casse(_Faux):
        def _request(self, method, path, **kw):
            if path.endswith("/test"):
                raise WiringError("faux", "SABnzbd injoignable", "")
            return super()._request(method, path, **kw)

    ok, message = _Casse(sabnzbd={"url": "x"}).test_sabnzbd()

    assert ok is False
    assert "injoignable" in message


def test_le_cablage_utilise_la_cle_reellement_pre_semee_dans_sabnzbd(monkeypatch):
    """Le champ ``password`` alimente sabnzbd.ini et tous les autres clients.

    Une reprise peut laisser son ancienne copie ``api_key`` en decalage. Dans
    ce cas DroppedNeedle doit recevoir la valeur que SABnzbd utilise vraiment,
    puis PlugArr realigne les deux copies avant de repersister la pile.
    """
    from plugarr.clients import droppedneedle

    cfg = _cfg("droppedneedle")
    sab = cfg.services["sabnzbd"]
    sab.api_key = "ancienne-copie"
    sab.password = "cle-pre-semee"
    recu = {}

    class FauxClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return None

        def wait_ready(self):
            return None

        def setup(self, **_kwargs):
            return False

        def login(self, *_args):
            return None

        def ensure_sabnzbd(self, **kwargs):
            recu.update(kwargs)
            return True

        def test_sabnzbd(self):
            return True, "ok"

    monkeypatch.setattr(droppedneedle, "DroppedNeedleClient", FauxClient)

    resultat = Wirer(cfg).step_droppedneedle_setup()

    assert resultat.ok is True
    assert recu["api_key"] == "cle-pre-semee"
    assert sab.api_key == "cle-pre-semee"


@pytest.mark.parametrize("methode", ["authenticate", "ensure_api_key"])
def test_les_methodes_du_client_jellyfin_existent(methode):
    """`step_droppedneedle_setup` a d'abord appele `JellyfinClient.login`, qui
    n'existe pas. Python ne dit rien avant le jour ou l'etape tourne."""
    from plugarr.clients.jellyfin import JellyfinClient

    assert hasattr(JellyfinClient, methode)


def test_une_cle_perimee_est_remplacee_meme_si_le_reste_est_identique():
    """Installation reelle du 26/09/2026 : « SABnzbd returned HTTP 403: API Key
    Incorrect ». La cle est masquee a la lecture ; seul le test la juge."""

    class Perimee(_Faux):
        def _request(self, method, path, **kw):
            if path.endswith("/test"):
                self.corps.append((method, kw.get("json")))
                cle = self._sab.get("api_key")
                return {"valid": cle == "NOUVELLE", "message": "API Key Incorrect"}
            return super()._request(method, path, **kw)

    faux = Perimee(sabnzbd={
        "enabled": True, "client_type": "sabnzbd", "url": "http://sabnzbd:8080",
        "api_key": "ANCIENNE", "category": "music", "priority": 0,
        "post_processing": 3, "downloads_mount": "/data/usenet",
    })
    from plugarr.clients.droppedneedle import POST_TRAITEMENT_COMPLET
    faux._sab["post_processing"] = POST_TRAITEMENT_COMPLET
    args = {"url": "http://sabnzbd:8080", "api_key": "NOUVELLE", "categorie": "music", "montage": "/data/usenet"}

    assert faux.ensure_sabnzbd(**args) is True
    assert faux._sab["api_key"] == "NOUVELLE"
    assert faux.ensure_sabnzbd(**args) is False

