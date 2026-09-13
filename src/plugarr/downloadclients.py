"""Profils de clients de telechargement.

Chaque client expose des champs differents dans les *arr, et surtout une facon
differente de router les telechargements :

- Transmission n'a pas de vraies categories : on lui donne un REPERTOIRE.
- qBittorrent a des categories natives, avec chemin de sauvegarde par categorie :
  on lui donne une CATEGORIE, et on cree cette categorie cote qBittorrent avec le
  bon chemin.

Poser les deux fait echouer la validation ("Cannot use Category and Directory"),
et le gabarit /schema arrive avec une categorie par defaut deja remplie. Chaque
profil doit donc explicitement vider celui des deux qu'il n'utilise pas.
"""

from __future__ import annotations

from dataclasses import dataclass

from .i18n import t
from .layout import CONTAINER_PATHS

#: Prefixe des champs de categorie/repertoire selon l'application.
#: Sonarr expose tvCategory/tvDirectory, Radarr movieCategory/movieDirectory, etc.
ARR_FIELD_PREFIX = {"sonarr": "tv", "radarr": "movie", "lidarr": "music"}

#: Nom de la categorie et chemin de telechargement associes a chaque application.
ARR_ROUTING = {
    "sonarr": ("tv", CONTAINER_PATHS["torrents_tv"]),
    "radarr": ("movies", CONTAINER_PATHS["torrents_movies"]),
    "lidarr": ("music", CONTAINER_PATHS["torrents_music"]),
}


@dataclass(frozen=True)
class DownloadClientProfile:
    service_id: str
    #: Nom technique de l'implementation dans les *arr, pas le libelle affiche.
    implementation: str
    protocol: str
    #: True = router par categorie native, False = router par repertoire explicite.
    routes_by_category: bool

    def arr_values(self, *, host: str, port: int, username: str, password: str, arr_id: str) -> dict:
        """Valeurs a poser dans le gabarit du *arr `arr_id`.

        On ne pousse que le prefixe pertinent : envoyer `movieDirectory` a Sonarr
        genererait un avertissement de champ inconnu a chaque passage.
        """
        prefix = ARR_FIELD_PREFIX[arr_id]
        category, directory = ARR_ROUTING[arr_id]
        values: dict[str, object] = {
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "useSsl": False,
        }
        if self.service_id == "transmission":
            values["urlBase"] = "/transmission/"
        if self.service_id == "sabnzbd":
            # SABnzbd s'authentifie par CLE API. Son identifiant et son mot de
            # passe restent vides : les poser ferait echouer le test de
            # connexion, l'interface n'en demandant pas.
            values["apiKey"] = password
            values["username"] = ""
            values["password"] = ""
        if self.routes_by_category:
            values[f"{prefix}Category"] = category
            values[f"{prefix}Directory"] = ""
        else:
            values[f"{prefix}Directory"] = directory
            values[f"{prefix}Category"] = ""
        return values

    def prowlarr_values(self, *, host: str, port: int, username: str, password: str) -> dict:
        """Prowlarr n'a pas de notion de categorie par media : pas de prefixe."""
        values: dict[str, object] = {
            "host": host,
            "port": port,
            "username": username,
            "password": password,
            "useSsl": False,
        }
        if self.service_id == "transmission":
            values["urlBase"] = "/transmission/"
        if self.service_id == "sabnzbd":
            values["apiKey"] = password
            values["username"] = ""
            values["password"] = ""
        return values


PROFILES: dict[str, DownloadClientProfile] = {
    "transmission": DownloadClientProfile(
        service_id="transmission",
        implementation="Transmission",
        protocol="torrent",
        routes_by_category=False,
    ),
    "qbittorrent": DownloadClientProfile(
        service_id="qbittorrent",
        implementation="QBittorrent",
        protocol="torrent",
        routes_by_category=True,
    ),
    "sabnzbd": DownloadClientProfile(
        service_id="sabnzbd",
        implementation="Sabnzbd",
        # USENET, pas torrent. Ce n'est pas un detail d'etiquette : les *arr
        # rangent leurs clients par protocole et ne proposent un client Usenet
        # que pour les publications Usenet.
        protocol="usenet",
        routes_by_category=True,
    ),
}


def profile_for(service_id: str) -> DownloadClientProfile:
    try:
        return PROFILES[service_id]
    except KeyError:
        known = ", ".join(sorted(PROFILES))
        raise KeyError(
            t(
                "pas de profil de client de telechargement pour {service}. "
                "Connus : {liste}",
                service=repr(service_id),
                liste=known,
            )
        ) from None


#: Ordre retenu quand plusieurs clients du MEME protocole sont installes et que
#: personne n'a choisi. qBittorrent d'abord : c'est deja la regle du port
#: entrant (`compose.port_sync_clients`) et celle de Flood.
ORDRE_AUTO = ("qbittorrent", "transmission", "sabnzbd")


def _par_protocole(presents) -> dict[str, list[str]]:
    groupes: dict[str, list[str]] = {}
    for sid in ORDRE_AUTO:
        if sid in presents:
            groupes.setdefault(PROFILES[sid].protocol, []).append(sid)
    return groupes


def concurrents(services) -> list[str]:
    """Clients qui partagent leur protocole avec au moins un autre de la selection.

    C'est la seule situation ou demander un client prefere a un sens : SABnzbd a
    cote de qBittorrent ne se dispute rien, les *arr choisissent d'abord par
    protocole.
    """
    groupes = _par_protocole(set(services))
    return [sid for groupe in groupes.values() if len(groupe) > 1 for sid in groupe]


def priorites(cfg) -> dict[str, int]:
    """Priorite a poser, dans les *arr et Prowlarr, pour chaque client installe.

    Tous etaient declares a `priority: 1`. Or la documentation de Sonarr est
    explicite : « Round-Robin is used for clients of the same type
    (torrent/usenet) that have the same priority ». Deux clients torrent
    installes, et les episodes partaient ALTERNATIVEMENT dans l'un et dans
    l'autre, sans que personne l'ait demande ni que rien ne le dise.

    Le client prefere passe a 1, les autres descendent. Ils restent declares et
    fonctionnels : le secours est preserve, rien n'est efface.
    """
    presents = {sid for sid in ORDRE_AUTO if cfg.enabled(sid)}
    rangs: dict[str, int] = {}
    for groupe in _par_protocole(presents).values():
        if cfg.client_prefere in groupe:
            groupe = [cfg.client_prefere, *(s for s in groupe if s != cfg.client_prefere)]
        for rang, sid in enumerate(groupe, start=1):
            rangs[sid] = rang
    return rangs
