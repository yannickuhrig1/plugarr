"""Seerr : les demandes de medias, et une specification qui ment par omission.

Seerr est le successeur commun de Jellyseerr et d'Overseerr, confirme par le
projet. Son image embarque sa propre specification OpenAPI, `/app/seerr-api.yml`,
contre laquelle le serveur valide chaque corps. C'est confortable — un champ
manquant est nomme dans la reponse — mais **elle est incomplete la ou ca
compte**, et trois essais reels l'ont montre.

**`hostname` est l'HOTE SEUL, et la specification ne declare ni `port`, ni
`useSsl`, ni `urlBase`.** L'implementation les lit pourtant, et recompose
l'adresse elle-meme (`dist/utils/getHostname.js`) :

    `${useSsl ? 'https' : 'http'}://${ip}:${port}${urlBase}`

Passer `http://jellyfin:8096` rend `HTTP 404 INVALID_URL`, message qui ne dit
pas quel champ est en cause.

**`serverType` est obligatoire alors qu'elle le donne pour facultatif.** Sans
lui : `NO_ADMIN_USER`, ce qui envoie chercher un probleme de droits cote
Jellyfin qui n'existe pas.

**L'adresse du serveur media n'est acceptee qu'UNE FOIS.** La renvoyer ensuite
rend « Jellyfin hostname already configured » ; l'omettre au premier appel rend
« No hostname provided ». Les deux erreurs sont symetriques et aucune
documentation ne les mentionne.

**`minimumAvailability` est obligatoire pour Radarr et absent du schema de
Sonarr.** Seerr le transmet tel quel a Radarr.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from plugarr import catalog, compose, orchestrator
from plugarr.clients.base import WiringError
from plugarr.clients.seerr import MINIMUM_DISPONIBILITE, SERVEUR_JELLYFIN, SeerrClient
from plugarr.wiring import Wirer


def _cfg(*services: str):
    return orchestrator.build_config(
        services=list(services or ("seerr",)), config_root="/c", data_root="/d"
    )


# ------------------------------------------------------------------ catalogue


def test_le_service_est_choisissable():
    assert "seerr" in {s.id for s in catalog.selectable()}


def test_l_image_est_epinglee_au_digest():
    assert "@sha256:" in catalog.get("seerr").image


def test_il_tire_jellyfin():
    """Il ne sert a rien seul : son compte administrateur EST un compte
    Jellyfin, et il demande des medias A des applications."""
    assert "jellyfin" in _cfg("seerr").services


def test_il_ne_recoit_aucun_mot_de_passe():
    """Consequence de structure, pas oubli : son administrateur est le compte
    Jellyfin. Lui en annoncer un serait mentir."""
    inst = _cfg("seerr").services["seerr"]

    assert not inst.password


def test_il_ne_touche_aucun_fichier():
    """Il transmet des demandes ; ce sont les *arr qui telechargent."""
    volumes = compose.build_compose(_cfg())["services"]["seerr"]["volumes"]

    assert all(not v.startswith("${DATA_ROOT}") for v in volumes), volumes


def test_il_passe_en_dernier():
    """Il s'authentifie contre Jellyfin et declare les *arr : les deux doivent
    etre cables avant lui."""
    noms = [e.name for e in Wirer(_cfg("seerr", "sonarr", "radarr")).build_plan()]

    assert noms[-1] == "seerr/setup"
    assert noms.index("jellyfin/setup") < noms.index("seerr/setup")


# --------------------------------------------------------------------- client


class _Faux(SeerrClient):
    """Journalise les corps envoyes au lieu de les emettre."""

    def __init__(self, *, hote_deja_pose=False, servarrs=None):
        self.name = "faux"
        self._hote_pose = hote_deja_pose
        self._servarrs = dict(servarrs or {})
        self.corps: list[tuple[str, dict]] = []

    def _request(self, method, path, **kw):
        corps = kw.get("json") or {}
        self.corps.append((path, corps))
        if path == "/auth/jellyfin":
            if self._hote_pose and "hostname" in corps:
                raise WiringError("faux", "HTTP 500 - Jellyfin hostname already configured", "")
            self._hote_pose = True
            return {"id": 1}
        if path.startswith("/settings/") and method == "GET":
            return self._servarrs.get(path.rsplit("/", 1)[1], [])
        return None


def test_l_accueil_pose_le_type_de_serveur():
    """Sans lui : NO_ADMIN_USER, message trompeur."""
    faux = _Faux()

    faux.login_jellyfin(username="u", password="p", hostname="jellyfin", port=8096)

    assert faux.corps[0][1]["serverType"] == SERVEUR_JELLYFIN


def test_l_hote_et_le_port_partent_separement():
    """Seerr recompose l'URL lui-meme ; lui en passer une rend INVALID_URL."""
    faux = _Faux()

    faux.login_jellyfin(username="u", password="p", hostname="jellyfin", port=8096)

    envoye = faux.corps[0][1]
    assert envoye["hostname"] == "jellyfin"
    assert envoye["port"] == 8096
    assert "://" not in envoye["hostname"]


def test_l_etape_se_rejoue_quand_l_hote_est_deja_pose():
    """« Jellyfin hostname already configured » n'est pas une panne : c'est le
    second passage. On retire l'adresse et on recommence."""
    faux = _Faux(hote_deja_pose=True)

    faux.login_jellyfin(username="u", password="p", hostname="jellyfin", port=8096)

    assert len(faux.corps) == 2, "le repli sans adresse n'a pas eu lieu"
    assert "hostname" not in faux.corps[1][1]
    assert faux.corps[1][1]["username"] == "u"


def test_une_autre_erreur_n_est_pas_avalee():
    """Le repli ne doit masquer que CE cas-la."""

    class _Casse(_Faux):
        def _request(self, method, path, **kw):
            raise WiringError("faux", "HTTP 401 - identifiants refuses", "")

    with pytest.raises(WiringError, match="identifiants refuses"):
        _Casse().login_jellyfin(username="u", password="p", hostname="j", port=1)


def test_radarr_recoit_sa_disponibilite_minimale():
    """Obligatoire pour Radarr, absent du schema de Sonarr."""
    faux = _Faux(servarrs={"radarr": []})

    faux.ensure_servarr(
        "radarr", name="Radarr", hostname="radarr", port=7878, api_key="k",
        profile_id=1, profile_name="Any", directory="/data/media/movies",
    )

    assert faux.corps[-1][1]["minimumAvailability"] == MINIMUM_DISPONIBILITE


def test_sonarr_recoit_ses_dossiers_de_saison_et_son_anime():
    faux = _Faux(servarrs={"sonarr": []})

    faux.ensure_servarr(
        "sonarr", name="Sonarr", hostname="sonarr", port=8989, api_key="k",
        profile_id=1, profile_name="Any", directory="/data/media/tv",
        anime_directory="/data/media/anime",
    )

    envoye = faux.corps[-1][1]
    assert envoye["enableSeasonFolders"] is True
    assert envoye["activeAnimeDirectory"] == "/data/media/anime"
    assert "minimumAvailability" not in envoye


def test_le_doublon_se_juge_sur_l_hote_et_le_port():
    """Deux entrees vers le meme service feraient partir chaque demande en
    double."""
    faux = _Faux(servarrs={"sonarr": [{"hostname": "sonarr", "port": 8989}]})

    ajoute = faux.ensure_servarr(
        "sonarr", name="Autre nom", hostname="sonarr", port=8989, api_key="k",
        profile_id=1, profile_name="Any", directory="/data/media/tv",
    )

    assert ajoute is False


def test_l_accueil_se_ferme_apres_les_applications():
    """`settings/initialize` avant les *arr laisserait une instance qui se
    croit prete et ne peut rien demander."""
    import inspect

    source = inspect.getsource(Wirer.step_seerr_setup)

    assert source.index("ensure_servarr") < source.index("seerr.initialize()")


def test_la_cle_api_est_lue_dans_les_reglages_principaux():
    """Seerr cree sa cle lui-meme. `settings/main` ne la montre qu'a un
    administrateur : sans elle, nzb360 et Arr Control ne s'y connectent pas."""
    faux = _Faux(servarrs={"main": {"apiKey": "CLE-SEERR", "applicationTitle": "Seerr"}})

    assert faux.api_key() == "CLE-SEERR"
    assert faux.corps[-1][0] == "/settings/main"


def test_sans_cle_la_lecture_rend_vide():
    """Un compte sans droits recoit les reglages SANS apiKey."""
    assert _Faux(servarrs={"main": {"applicationTitle": "Seerr"}}).api_key() == ""


def test_l_etape_garde_la_cle_apres_la_session():
    """La cle se lit une fois la session administrateur ouverte, et ne remplace
    une cle connue que si Seerr en rend une."""
    import inspect

    source = inspect.getsource(Wirer.step_seerr_setup)

    assert source.index("login_jellyfin") < source.index("seerr.api_key()")
    assert "seerr.api_key() or inst.api_key" in source


def test_les_identifiants_arr_survivent_a_un_redemarrage():
    """`PUT config/host` repond 202 et n'applique le compte qu'au REDEMARRAGE.

    Verifie sur Sonarr 4.0.19 : methode d'authentification relue a « forms »,
    mot de passe pose, et pourtant le formulaire refusait — y compris avec un
    mot de passe purement alphanumerique, ce qui ecarte la piste des caracteres
    speciaux. Un redemarrage, et la connexion passe.

    C'est le meme piege que pour la cle API, ou seule la reecriture du
    config.xml suivie d'un redemarrage fonctionnait : l'application accepte,
    accuse reception, et ne change rien avant de repartir.
    """
    import inspect

    from plugarr.wiring import Wirer

    source = inspect.getsource(Wirer.step_web_login)

    assert "_redemarrer" in source, "l'etape abandonne au lieu de redemarrer"
    assert source.index("ensure_web_user") < source.index("_redemarrer")
    assert "wait_ready" in source, "on ne reverifie pas apres le redemarrage"


def test_il_tourne_sous_puid_pgid():
    """L'image ignore PUID/PGID et tourne en `node` (UID 1000) : sans `user`,
    « EACCES: mkdir '/app/config/logs/' » dans un dossier qui n'est pas a elle.
    Constate sur le banc (PUID 0), Seerr redemarrait en boucle."""
    cfg = _cfg()
    bloc = compose.build_compose(cfg)["services"]["seerr"]

    assert bloc["user"] == f"{cfg.puid}:{cfg.pgid}"


def test_lance_en_root_plugarr_lui_donne_son_dossier(tmp_path, monkeypatch):
    """`sudo plugarr` avec PUID 1000 : le dossier cree par root doit passer a
    1000, sinon le conteneur lance en 1000 ne peut pas y ecrire."""
    import os

    from plugarr import layout

    donnes = []
    monkeypatch.setattr(layout, "_est_root", lambda: True)
    monkeypatch.setattr(os, "chown", lambda p, u, g, **kw: donnes.append((Path(p).name, u, g)), raising=False)
    config = tmp_path / "config"
    (config / "seerr" / "logs").mkdir(parents=True)

    layout.create_tree(tmp_path / "data", config, ["seerr", "sonarr"], owner=(1000, 1001))

    assert ("seerr", 1000, 1001) in donnes and ("logs", 1000, 1001) in donnes
    assert all(nom != "sonarr" for nom, *_ in donnes), "les images LinuxServer s'en chargent"
