"""Catalogue des services de la Phase 1.

Regle du projet : les tags d'image sont EPINGLES. Un tag flottant `latest` rend le
cablage non reproductible et fait exploser l'outil a chaque release amont.
La version testee est consignee dans docs/COMPATIBILITY.md.
"""

from __future__ import annotations

from .models import Category, ServiceSpec

# Tags epingles. A remonter via une PR dediee + un passage de la CI d'integration.
_TAGS = {
    "sonarr": "4.0.19",
    "radarr": "6.3.0",
    "prowlarr": "2.5.2",
    "transmission": "4.1.3",
    "qbittorrent": "5.2.3",
    "lidarr": "3.1.0",
    "jellyfin": "10.11.11",
    "flood": "4.16.1",
    "autobrr": "v1.85.0",
    "qui": "v1.28.0",
    "recyclarr": "8.7.1",
}

#: VueTorrent, interface de remplacement de qBittorrent, pose par le chargeur de
#: mods des images LinuxServer (`DOCKER_MODS`). Epingle comme Silo : tag lisible
#: ET digest. Mesure le 2026-09-19 sur qBittorrent 5.2.3 : le chargeur accepte
#: `depot:tag@sha256:...` et telecharge exactement cette version.
VUETORRENT_MOD = (
    "ghcr.io/vuetorrent/vuetorrent-lsio-mod:2.35.0"
    "@sha256:f6445ce1eefc597650d4f469ad7b18e35451ce79fc9588f4276a2a0221ca793e"
)

#: Silo s'epingle autrement : il ne publie pas de version au sens habituel, mais
#: un numero de construction monotone. `build-522` porte l'etiquette
#: `org.opencontainers.image.version` de l'image, relevee dans l'image elle-meme.
#:
#: Le DIGEST accompagne le tag. Docker retient le digest, donc le contenu est
#: fige ; le tag reste lisible et comparable pour la detection de mises a jour.
#: C'est la seule forme qui donne les deux a la fois.
#:
#: Ses deux appoints sont epingles de la meme facon : `redis:alpine` et
#: `pgvector:pg18` sont des tags FLOTTANTS, qui designent un nom et non un
#: contenu. Sans digest, deux installations du meme jour peuvent differer.
#: DroppedNeedle, anciennement MusicSeerr.
_DROPPEDNEEDLE = (
    "ghcr.io/droppedneedle/droppedneedle:v2.9.0"
    "@sha256:4687b3913ef07645dfa392cc03002ba0a6f4f07d32801065c533ecd08c5f2a82"
)

#: SABnzbd. Image LinuxServer : nos conventions exactes.
_SABNZBD = (
    "lscr.io/linuxserver/sabnzbd:5.1.2"
    "@sha256:64c4c2b6ed546237451cbfec33aa8bac1396865c1a266dd247c02b36ffe27c62"
)

#: Seerr, successeur commun de Jellyseerr et d'Overseerr.
_SEERR = (
    "ghcr.io/seerr-team/seerr:v3.4.1"
    "@sha256:f4768de5f616248d723e05891f3345a1402123775d03bf0890dbfedc0831bda1"
)

#: Audiobookshelf. 128 versions publiees : il s'epingle sans exception.
_AUDIOBOOKSHELF = (
    "ghcr.io/advplyr/audiobookshelf:2.36.0"
    "@sha256:180acad33d69c99ed208676465d8edcb268fa46967735579a7810859885b1a8e"
)

_SILO = {
    "silo": (
        "ghcr.io/silo-server/silo-server:build-522"
        "@sha256:d3cb4ad9df66c727506c562ea3a9263b8938352d66ac5c247425d654b585b5df"
    ),
    "postgres": (
        "pgvector/pgvector:pg18"
        "@sha256:2ba9ca5f2e7daa0f0e7723cba1ee9167bab54efd3640516a44ac1a928dd67e7a"
    ),
    "redis": (
        "redis:alpine"
        "@sha256:becdda6c7f4b3fb42e42fd7f120bbf5c54c4caaaf16f26da24e4563d2c1f0576"
    ),
}

#: Repris tel quel du README de Silo. Ce n'est pas notre jugement sur le projet,
#: c'est ce que le projet dit de lui-meme.
_SILO_AVERTISSEMENT = (
    "Silo est en pre-version : son API, sa configuration et ses migrations de "
    "base peuvent changer avant sa premiere version stable. Sauvegardez avant "
    "toute mise a jour."
)

CATALOG: dict[str, ServiceSpec] = {
    "prowlarr": ServiceSpec(
        id="prowlarr",
        display_name="Prowlarr",
        category=Category.ARR,
        image=f"lscr.io/linuxserver/prowlarr:{_TAGS['prowlarr']}",
        internal_port=9696,
        default_host_port=9696,
        config_dir="prowlarr",
        api_family="arr",
        api_version="v1",
        notes="Pivot du cablage : alimente les autres en indexeurs.",
    ),
    "sonarr": ServiceSpec(
        id="sonarr",
        display_name="Sonarr",
        category=Category.ARR,
        image=f"lscr.io/linuxserver/sonarr:{_TAGS['sonarr']}",
        internal_port=8989,
        default_host_port=8989,
        config_dir="sonarr",
        api_family="arr",
        api_version="v3",
        notes="Series TV.",
    ),
    "radarr": ServiceSpec(
        id="radarr",
        display_name="Radarr",
        category=Category.ARR,
        image=f"lscr.io/linuxserver/radarr:{_TAGS['radarr']}",
        internal_port=7878,
        default_host_port=7878,
        config_dir="radarr",
        api_family="arr",
        api_version="v3",
        notes="Films.",
    ),
    "transmission": ServiceSpec(
        id="transmission",
        display_name="Transmission",
        category=Category.DOWNLOAD,
        image=f"lscr.io/linuxserver/transmission:{_TAGS['transmission']}",
        internal_port=9091,
        default_host_port=9091,
        config_dir="transmission",
        api_family="transmission",
        notes="Client torrent par defaut.",
    ),
    "lidarr": ServiceSpec(
        id="lidarr",
        display_name="Lidarr",
        category=Category.ARR,
        image=f"lscr.io/linuxserver/lidarr:{_TAGS['lidarr']}",
        internal_port=8686,
        default_host_port=8686,
        config_dir="lidarr",
        api_family="arr",
        api_version="v1",
        notes="Musique. Son API est en v1, pas en v3.",
    ),
    "qbittorrent": ServiceSpec(
        id="qbittorrent",
        display_name="qBittorrent",
        category=Category.DOWNLOAD,
        image=f"lscr.io/linuxserver/qbittorrent:{_TAGS['qbittorrent']}",
        internal_port=8080,
        default_host_port=8080,
        config_dir="qbittorrent",
        api_family="qbittorrent",
        notes="Categories natives avec chemin dedie.",
    ),
    "jellyfin": ServiceSpec(
        id="jellyfin",
        display_name="Jellyfin",
        category=Category.MEDIA,
        image=f"lscr.io/linuxserver/jellyfin:{_TAGS['jellyfin']}",
        internal_port=8096,
        default_host_port=8096,
        config_dir="jellyfin",
        api_family="jellyfin",
        notes="Serveur media. Bibliotheques creees pour vous.",
    ),
    "seerr": ServiceSpec(
        id="seerr",
        display_name="Seerr",
        category=Category.MEDIA,
        image=_SEERR,
        internal_port=5055,
        default_host_port=5055,
        config_dir="seerr",
        api_family="seerr",
        # Il ne sert a rien seul : il demande des medias A des applications.
        requires=("jellyfin",),
        notes="Demandes de medias. Successeur de Jellyseerr et d'Overseerr.",
    ),
    "sabnzbd": ServiceSpec(
        id="sabnzbd",
        display_name="SABnzbd",
        category=Category.DOWNLOAD,
        image=_SABNZBD,
        # Sous VPN, tous les clients de telechargement partagent la pile reseau
        # de Gluetun. Decaler seulement le port HOTE ne suffit alors pas :
        # `8085:8080` et `8080:8080` aboutissent au meme socket de Gluetun, et
        # qBittorrent repond a la place de SABnzbd. Le port d'ecoute de SABnzbd
        # est donc distinct jusque dans le conteneur.
        internal_port=8085,
        default_host_port=8085,
        config_dir="sabnzbd",
        api_family="sabnzbd",
        notes="Client Usenet. Complete les torrents, il ne les remplace pas.",
    ),
    "droppedneedle": ServiceSpec(
        id="droppedneedle",
        display_name="DroppedNeedle",
        category=Category.MEDIA,
        image=_DROPPEDNEEDLE,
        internal_port=8688,
        default_host_port=8688,
        config_dir="droppedneedle",
        # `/app/cache` porte sa base SQLite, `auth_users` comprise. Sur un
        # montage Windows, sa verification apres mise a jour echoue et le
        # conteneur refuse de demarrer : « The upgraded library database could
        # not be verified after installation ». Meme remede que pour la base de
        # Silo, et meme cause probable — SQLite et la couche de partage de
        # fichiers de Docker Desktop ne s'entendent pas.
        named_volumes=(("droppedneedle-cache", "/app/cache"),),
        api_family="droppedneedle",
        # Il ne telecharge rien sans client. SABnzbd est celui que PlugArr sait
        # lui cabler ; sans lui, l'installer donnerait une interface qui
        # cherche et ne peut rien obtenir.
        requires=("sabnzbd",),
        notes="Musique, de la demande au rangement. REMPLACE Lidarr, ne le complete pas.",
    ),
    "audiobookshelf": ServiceSpec(
        id="audiobookshelf",
        display_name="Audiobookshelf",
        category=Category.MEDIA,
        image=_AUDIOBOOKSHELF,
        internal_port=80,
        # 13378 est le port que son projet documente. Il ne sert a rien dans le
        # conteneur, qui ecoute sur 80 : c'est une convention cote hote.
        default_host_port=13378,
        config_dir="audiobookshelf",
        api_family="audiobookshelf",
        notes="Livres et livres audio. Remplit les bibliotheques books et audiobooks.",
    ),
    "silo-postgres": ServiceSpec(
        id="silo-postgres",
        display_name="PostgreSQL (Silo)",
        category=Category.MEDIA,
        image=_SILO["postgres"],
        # Aucun port publie : la base ne sert qu'a Silo, sur le reseau interne.
        # L'exposer sur l'hote serait une surface d'attaque pour rien.
        internal_port=0,
        default_host_port=0,
        # Aucun dossier sur l'hote : ses donnees vivent dans un VOLUME Docker.
        # Un montage vers le disque Windows rendait ses migrations 590 fois plus
        # lentes — 2935 s contre 5 s, mesure. Voir compose.PG_VOLUME.
        config_dir=None,
        named_volumes=(("silo-pgdata", "/var/lib/postgresql"),),
        internal=True,
        notes="Base de donnees de Silo. Installee avec lui, jamais seule.",
    ),
    "silo-redis": ServiceSpec(
        id="silo-redis",
        display_name="Redis (Silo)",
        category=Category.MEDIA,
        image=_SILO["redis"],
        internal_port=0,
        default_host_port=0,
        config_dir="silo/redis",
        internal=True,
        notes="Cache de Silo. Installe avec lui, jamais seul.",
    ),
    "silo": ServiceSpec(
        id="silo",
        display_name="Silo",
        category=Category.MEDIA,
        image=_SILO["silo"],
        internal_port=8080,
        default_host_port=8090,
        config_dir="silo",
        # Trois portes sur le meme conteneur. Le libelle compte : « API
        # Jellyfin » dit a quoi ca sert, « port 8096 » non.
        extra_ports=(("API Jellyfin", 8096), ("API Audiobookshelf", 13378)),
        requires=("silo-postgres", "silo-redis"),
        # SAINS, pas seulement demarres : Silo refuse de demarrer si sa base n'a
        # pas fini son initialisation.
        depends_on_healthy=("silo-postgres", "silo-redis"),
        api_family="silo",
        needs_secret_key=True,
        experimental=_SILO_AVERTISSEMENT,
        notes="Serveur media, API compatible Jellyfin. Meilisearch est optionnel "
        "et n'est pas installe.",
    ),
    "autobrr": ServiceSpec(
        id="autobrr",
        display_name="autobrr",
        category=Category.ARR,
        image=f"ghcr.io/autobrr/autobrr:{_TAGS['autobrr']}",
        internal_port=7474,
        default_host_port=7474,
        config_dir="autobrr",
        requires_one_of=("sonarr", "radarr", "lidarr"),
        api_family="autobrr",
        notes="Ecoute les annonces IRC. Plus rapide que le sondage RSS.",
    ),
    "qui": ServiceSpec(
        id="qui",
        display_name="qui",
        category=Category.UI,
        image=f"ghcr.io/autobrr/qui:{_TAGS['qui']}",
        internal_port=7476,
        default_host_port=7476,
        config_dir="qui",
        requires=("qbittorrent",),
        api_family="qui",
        notes="UI web pour qBittorrent. N'est pas un client.",
    ),
    "recyclarr": ServiceSpec(
        id="recyclarr",
        display_name="Recyclarr",
        category=Category.ARR,
        image=f"ghcr.io/recyclarr/recyclarr:{_TAGS['recyclarr']}",
        #: Aucune interface web : Recyclarr tourne sur une planification et sort.
        #: Le port 0 signale qu'il n'y a rien a publier.
        internal_port=0,
        default_host_port=0,
        config_dir="recyclarr",
        requires_one_of=("sonarr", "radarr"),
        api_family="recyclarr",
        notes="Profils de qualite TRaSH. Aucune interface web.",
    ),
    "flood": ServiceSpec(
        id="flood",
        display_name="Flood",
        category=Category.UI,
        image=f"jesec/flood:{_TAGS['flood']}",
        internal_port=3000,
        default_host_port=3001,
        config_dir="flood",
        #: Flood pilote qBittorrent OU Transmission. `requires` ne sait exprimer
        #: qu'un ET : l'alternative est verifiee par `missing_requirements`.
        requires=(),
        requires_one_of=("qbittorrent", "transmission"),
        api_family=None,
        notes="UI web pour qBittorrent ou Transmission. N'est pas un client.",
    ),
}

#: Ordre de demarrage et de cablage. Prowlarr en dernier : il a besoin que
#: Sonarr/Radarr repondent deja pour enregistrer ses Applications.
STARTUP_ORDER = (
    "transmission",
    "qbittorrent",
    # SABnzbd avec les autres clients : les *arr le declarent au meme moment.
    "sabnzbd",
    "sonarr",
    "radarr",
    "lidarr",
    "prowlarr",
    # Recyclarr apres les *arr : il ecrit dans leurs profils de qualite.
    "recyclarr",
    # autobrr apres les *arr ET apres les clients : il les declare tous les deux
    # au meme endpoint, et son test de connexion les contacte reellement.
    "autobrr",
    "jellyfin",
    # Les appoints de Silo AVANT lui : `depends_on` exige qu'ils soient sains,
    # et l'ordre de cette liste decide aussi de l'ordre d'affichage.
    "silo-postgres",
    "silo-redis",
    "silo",
    # Audiobookshelf ne depend de personne : il lit des dossiers. Sa place ici
    # est celle de l'affichage, a cote des autres serveurs media.
    "audiobookshelf",
    # DroppedNeedle apres SABnzbd, qu'il declare.
    "droppedneedle",
    # Seerr APRES Jellyfin et les *arr : son accueil s'authentifie contre le
    # serveur media, et il declare les *arr dans la foulee.
    "seerr",
    "flood",
    "qui",
)

#: Applications *arr pilotables par Prowlarr et rattachables a un client de download.
MANAGED_ARRS = ("sonarr", "radarr", "lidarr")

#: Services jouant le role de client de telechargement.
#: Les clients de telechargement. SABnzbd y figure alors qu'il parle Usenet et
#: non BitTorrent : il est declare aux *arr de la meme facon, il est attendu au
#: demarrage de la meme facon, et il passe par le VPN de la meme facon. Ce qui
#: change — protocole, cle API au lieu d'un mot de passe — est isole dans
#: downloadclients.py.
# Les clients BitTorrent et Usenet partagent une categorie d'interface, mais
# pas le meme besoin reseau. Garder les deux listes evite de refaire l'erreur
# « tout telechargement est du torrent » dans les avertissements et le VPN.
TORRENT_CLIENTS = ("transmission", "qbittorrent")
DOWNLOAD_CLIENTS = (*TORRENT_CLIENTS, "sabnzbd")

#: Selection par defaut du profil "Debutant tout-en-un" en Phase 1.
#: Coches par defaut dans l'assistant. Recyclarr en fait partie : il ne coute
#: presque rien (pas de port, pas d'interface, un reveil par jour) et c'est lui
#: qui evite qu'un *arr accepte n'importe quel encodage. Une stack sans profil de
#: qualite telecharge, mais telecharge mal.
DEFAULT_SELECTION = ("prowlarr", "sonarr", "radarr", "transmission", "jellyfin", "recyclarr")


def get(service_id: str) -> ServiceSpec:
    try:
        return CATALOG[service_id]
    except KeyError:
        known = ", ".join(sorted(CATALOG))
        raise KeyError(f"service inconnu: {service_id!r}. Connus: {known}") from None


def resolve_dependencies(selection: list[str]) -> list[str]:
    """Ajoute les prerequis manquants et renvoie la selection dans l'ordre de demarrage.

    Pour un service qui accepte plusieurs backends (`requires_one_of`), on n'ajoute
    le premier de la liste que si AUCUN n'est deja selectionne : cocher Flood a cote
    de qBittorrent ne doit pas tirer Transmission en plus.
    """
    wanted = set(selection)
    changed = True
    while changed:
        changed = False
        for sid in list(wanted):
            spec = get(sid)
            for dep in spec.requires:
                if dep not in wanted:
                    wanted.add(dep)
                    changed = True
            if spec.requires_one_of and not (set(spec.requires_one_of) & wanted):
                wanted.add(spec.requires_one_of[0])
                changed = True
    return [sid for sid in STARTUP_ORDER if sid in wanted]


def selectable() -> list[ServiceSpec]:
    """Services qu'un utilisateur peut cocher.

    Les conteneurs d'appoint en sont exclus : une base de donnees n'est pas un
    service qu'on choisit, c'est une piece de celui qui en depend. La proposer a
    cote de Sonarr n'aurait aucun sens, et l'installer seule non plus.
    """
    return [spec for spec in CATALOG.values() if not spec.internal]


#: Familles dont le mot de passe peut etre change sans reinstaller. Liste fermee :
#: chaque entree correspond a un chemin VERIFIE contre le service, pas a une
#: supposition. Elle vit ici parce que deux modules en ont besoin — la page
#: d'administration pour afficher le bouton, l'orchestrateur pour agir — et que
#: la page ne peut pas importer l'orchestrateur, qui l'importe deja.
ROTATABLE_FAMILIES = ("arr", "qbittorrent", "transmission")
