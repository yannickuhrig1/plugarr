"""Arborescence de donnees et profils de plateforme.

Le point critique du projet (PROMPT.md sec. 4.2) : un montage UNIQUE `/data` dans
tous les conteneurs. Deux montages separes (/downloads + /media) font echouer les
hardlinks silencieusement, et chaque import recopie le fichier.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import catalog
from .i18n import t
from .models import PlatformProfile


#: Sous-dossiers crees sous DATA_ROOT. Meme structure cote hote et cote conteneur.
@dataclass(frozen=True)
class Bibliotheque:
    """Un genre de contenu, de son telechargement a son rangement."""

    id: str
    nom: str
    #: Application qui la remplit, ou None si personne ne la pilote encore.
    arr: str | None
    #: False pour ce qui ne se range pas dans une mediatheque : un logiciel
    #: telecharge n'a pas sa place a cote des films.
    media: bool = True

    @property
    def torrents(self) -> str:
        return f"/data/torrents/{self.id}"

    @property
    def usenet(self) -> str:
        return f"/data/usenet/{self.id}"

    @property
    def mediatheque(self) -> str:
        return f"/data/media/{self.id}"


#: Les BIBLIOTHEQUES d'une stack media, et tout ce qui en decoule.
#:
#: Une seule table, parce que chaque bibliotheque implique trois choses qui
#: doivent rester d'accord : un dossier de telechargement, un dossier de
#: rangement, et une categorie chez le client torrent qui envoie l'un vers
#: l'autre. Les tenir dans trois listes separees revenait a les desynchroniser
#: a la premiere addition.
#:
#: `arr` designe l'application qui la remplit, ou None : un rangement sans
#: automatisation reste utile pour ce qu'on telecharge a la main, mais plugarr
#: ne doit pas laisser croire qu'il le pilote.
#:
#: Les deux racines vivent sous le MEME point de montage `/data`, condition des
#: liens physiques : sans cela chaque import recopie le fichier.
BIBLIOTHEQUES: tuple[Bibliotheque, ...] = (
    Bibliotheque("movies", "Films", arr="radarr"),
    Bibliotheque("tv", "Series", arr="sonarr"),
    # Sonarr gere l'anime comme un TYPE de serie, avec son propre dossier
    # racine : c'est la disposition recommandee par les TRaSH Guides, et elle
    # evite que les conventions de nommage anime polluent les series.
    Bibliotheque("anime", "Anime", arr="sonarr"),
    Bibliotheque("music", "Musique", arr="lidarr"),
    # Les suivantes n'ont pas encore d'application au catalogue. Elles rangent
    # ce qu'on telecharge a la main, et attendent Audiobookshelf, Shelfarr et
    # les autres.
    Bibliotheque("shows", "Spectacles", arr=None),
    Bibliotheque("books", "Livres", arr=None),
    Bibliotheque("audiobooks", "Livres audio", arr=None),
    Bibliotheque("apps", "Logiciels", arr=None, media=False),
)

#: Sous-dossiers a creer sous DATA_ROOT. Deduit de la table ci-dessus.
#:
#: Torrent et Usenet ont leur propre arborescence. Ce n'est pas une coquetterie :
#: les deux protocoles ont des durees de vie differentes — un torrent doit rester
#: en partage apres l'import, un NZB non — et melanger les deux fait effacer par
#: l'un ce que l'autre partage encore. Les TRaSH Guides recommandent la meme
#: separation. Les deux restent sous `/data`, condition des liens physiques.
DATA_SUBDIRS = (
    "torrents",
    "torrents/.incomplete",
    *(f"torrents/{b.id}" for b in BIBLIOTHEQUES),
    "usenet",
    "usenet/.incomplete",
    *(f"usenet/{b.id}" for b in BIBLIOTHEQUES),
    "media",
    *(f"media/{b.id}" for b in BIBLIOTHEQUES if b.media),
)

#: Chemins tels que les conteneurs les voient.
CONTAINER_PATHS = {
    "torrents_root": "/data/torrents",
    "torrents_incomplete": "/data/torrents/.incomplete",
    **{f"torrents_{b.id}": f"/data/torrents/{b.id}" for b in BIBLIOTHEQUES},
    "usenet_root": "/data/usenet",
    "usenet_incomplete": "/data/usenet/.incomplete",
    **{f"usenet_{b.id}": f"/data/usenet/{b.id}" for b in BIBLIOTHEQUES},
    **{f"media_{b.id}": f"/data/media/{b.id}" for b in BIBLIOTHEQUES if b.media},
}


@dataclass(frozen=True)
class ProfileDefaults:
    config_root: str
    data_root: str
    puid: int
    pgid: int
    #: True quand les identifiants corrects sont ceux de l'utilisateur courant et
    #: doivent etre DETECTES. False quand la plateforme impose une constante.
    prefer_detection: bool
    #: D'ou viennent puid/pgid. Affiche a l'utilisateur : il doit pouvoir juger.
    source: str


def _sous_le_dossier_personnel(*parties: str) -> str:
    """Chemin absolu sous le dossier personnel, resolu MAINTENANT.

    Un `~` laisse tel quel serait ecrit dans `.env` puis dans
    `docker-compose.yml`, ou Docker ne l'etend pas : il creerait un dossier
    litteralement nomme `~`. Le defaut doit donc etre absolu des sa lecture.
    """
    return str(Path.home().joinpath(*parties))


PROFILE_DEFAULTS: dict[PlatformProfile, ProfileDefaults] = {
    PlatformProfile.GENERIC_LINUX: ProfileDefaults(
        config_root="/opt/plugarr/config",
        data_root="/srv/data",
        puid=1000,
        pgid=1000,
        prefer_detection=True,
        source="utilisateur courant",
    ),
    PlatformProfile.WINDOWS: ProfileDefaults(
        # Des chemins Windows, evidemment. Sans ce profil, un utilisateur Windows
        # n'avait AUCUNE option correcte : les trois autres proposent des chemins
        # Linux, que Docker Desktop cree alors a la racine du disque courant
        # (`/mnt/user/data` devient `C:\mnt\user\data`) sans que rien ne le dise.
        config_root="C:/plugarr/config",
        data_root="C:/plugarr/data",
        # Docker Desktop n'applique pas la propriete Unix aux montages venus de
        # Windows : ces valeurs n'ont aucun effet ici. On garde 1000:1000, qui est
        # ce qu'attendent les images LinuxServer, et on le DIT plutot que
        # d'afficher un avertissement inquietant et sans objet.
        puid=1000,
        pgid=1000,
        prefer_detection=False,
        source="sans effet sous Docker Desktop : Windows ne porte pas ces droits",
    ),
    PlatformProfile.MACOS: ProfileDefaults(
        # SOUS LE DOSSIER PERSONNEL, et ce n'est pas un gout. Depuis Catalina la
        # racine de macOS est un volume systeme signe, monte en LECTURE SEULE :
        # `/srv` n'y existe pas et ne peut pas y etre cree. Sans ce profil, un
        # utilisateur Mac heritait de `generic-linux` et de son `/srv/data`, donc
        # de « [Errno 30] Read-only file system: '/srv' » des le premier
        # lancement — signale par un utilisateur, capture a l'appui.
        #
        # `/Users` fait partie des dossiers que Docker Desktop partage par
        # defaut : le montage fonctionne sans rien avoir a regler. `/opt`, lui,
        # est bien inscriptible sur macOS mais n'est PAS partage — le dossier se
        # creerait et le montage echouerait plus tard, ce qui est pire.
        config_root=_sous_le_dossier_personnel("plugarr", "config"),
        data_root=_sous_le_dossier_personnel("plugarr", "data"),
        # Valeurs de repli seulement : le premier compte macOS est 501:20
        # (staff), mais rien ne le garantit. La detection passe devant.
        puid=501,
        pgid=20,
        prefer_detection=True,
        source="utilisateur courant",
    ),
    PlatformProfile.UNRAID: ProfileDefaults(
        config_root="/mnt/user/appdata/plugarr",
        data_root="/mnt/user/data",
        puid=99,
        pgid=100,
        prefer_detection=False,
        source="constante Unraid : nobody:users = 99:100",
    ),
    PlatformProfile.SYNOLOGY: ProfileDefaults(
        config_root="/volume1/docker/plugarr",
        data_root="/volume1/data",
        # Valeurs de repli seulement. Sur DSM, l'UID depend de l'ordre de creation
        # des utilisateurs : 1026 pour le premier, mais on rencontre couramment
        # bien plus haut. Une constante serait fausse par conception, d'ou la
        # detection.
        puid=1026,
        pgid=100,
        prefer_detection=True,
        source="utilisateur courant (les UID DSM varient selon l'utilisateur cree)",
    ),
}


def detect_ids() -> tuple[int, int] | None:
    """UID/GID de l'utilisateur courant, ou None si la plateforme ne les expose pas.

    Renvoie None plutot que 1000:1000 sous Windows : une valeur inventee
    silencieusement est pire qu'une absence de valeur, puisqu'elle empeche de
    prevenir l'utilisateur.
    """
    getuid = getattr(os, "getuid", None)
    getgid = getattr(os, "getgid", None)
    if getuid is None or getgid is None:
        return None
    return getuid(), getgid()


def resolve_ids(profile: PlatformProfile) -> tuple[int, int, str, bool]:
    """Determine PUID/PGID pour un profil.

    Renvoie (uid, gid, explication, sur). `sur` a False signifie "l'utilisateur doit
    regarder cette valeur avant de continuer" : l'explication dit pourquoi.
    """
    defaults = PROFILE_DEFAULTS[profile]
    if not defaults.prefer_detection:
        return defaults.puid, defaults.pgid, defaults.source, True

    detected = detect_ids()
    if detected is None:
        return (
            defaults.puid,
            defaults.pgid,
            "valeur par defaut : detection impossible sur cette plateforme",
            False,
        )
    if detected[0] == 0:
        # Constate lors du premier essai sur Linux natif : `sudo plugarr install`
        # detecte 0:0 et fait tourner TOUTE la stack en root, en silence. Les
        # medias telecharges appartiennent alors a root, et l'utilisateur ne peut
        # plus y toucher sans sudo. On propose la valeur, on ne l'impose pas, mais
        # on ne la laisse pas passer sans le dire.
        return (
            0,
            detected[1],
            "lance en root : conteneurs et medias appartiendront a root",
            False,
        )
    return detected[0], detected[1], t("detecte ({origine})", origine=t(defaults.source)), True


def create_tree(data_root: str | Path, config_root: str | Path, service_ids: list[str]) -> list[Path]:
    """Cree l'arborescence. Idempotent."""
    created: list[Path] = []
    data_root, config_root = Path(data_root), Path(config_root)
    for sub in DATA_SUBDIRS:
        p = data_root / sub
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            created.append(p)
    for sid in service_ids:
        spec = catalog.CATALOG.get(sid)
        # On cree le dossier que le compose MONTE, pas un dossier portant le nom
        # du service. Les deux coincidaient partout jusqu'a Silo, dont les
        # conteneurs d'appoint vivent sous `silo/`. Sans cela, `config/silo-redis`
        # restait vide a cote du `config/silo/redis` que Docker creait lui-meme.
        # Un service sans dossier de configuration — la base de Silo, qui tient
        # dans un volume Docker — n'en cree aucun.
        if spec is not None and not spec.needs_config_volume:
            continue
        p = config_root / (spec.config_dir if spec is not None else sid)
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            created.append(p)
    return created


def hardlink_supported(data_root: str | Path) -> tuple[bool, str]:
    """Teste REELLEMENT qu'un hardlink est possible entre torrents/ et media/.

    C'est le diagnostic qui distingue une stack qui recopie 40 Go a chaque import
    d'une stack qui fait un lien instantane. On ne suppose rien, on essaie.
    """
    data_root = Path(data_root)
    src_dir, dst_dir = data_root / "torrents", data_root / "media"
    try:
        src_dir.mkdir(parents=True, exist_ok=True)
        dst_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # Le `t()` manquait ici, et lui seul : les deux autres sorties de cette
        # fonction l'avaient. Un utilisateur macOS en interface anglaise voyait
        # donc un tableau anglais avec cette ligne — et elle seule — en francais.
        # L'audit des traductions ne pouvait pas l'attraper : il releve les
        # `t("...")` presents, jamais un `t()` absent.
        return False, t(
            "impossible de creer {source} ou {cible} : {erreur}",
            source=src_dir,
            cible=dst_dir,
            erreur=exc,
        )

    fd, src = tempfile.mkstemp(dir=src_dir, prefix=".plugarr-hardlink-")
    os.close(fd)
    dst = dst_dir / (Path(src).name + ".link")
    try:
        os.link(src, dst)
        return True, t("hardlink OK entre torrents/ et media/")
    except OSError as exc:
        return False, t(
            "hardlink impossible ({erreur}). Les imports recopieront les fichiers "
            "au lieu de les lier. Verifiez que {source} et {cible} sont sur le "
            "MEME systeme de fichiers, et que DATA_ROOT est monte d'un seul bloc.",
            erreur=exc,
            source=src_dir,
            cible=dst_dir,
        )
    finally:
        for p in (dst, Path(src)):
            try:
                p.unlink()
            except OSError:
                pass


def default_profile() -> PlatformProfile:
    """Profil correspondant a la machine qui execute plugarr.

    Proposer `generic-linux` a un utilisateur Windows le conduisait droit dans le
    piege : il gardait des chemins Linux, et Docker Desktop les creait a la racine
    du disque courant sans que rien ne le signale.

    macOS avait exactement le meme angle mort, en pire : `generic-linux` propose
    `/srv/data`, que la racine en lecture seule de macOS REFUSE de creer. Le
    piege Windows produit un dossier au mauvais endroit ; celui-ci produit un
    « [Errno 30] Read-only file system » et une installation morte.
    """
    if sys.platform == "win32":
        return PlatformProfile.WINDOWS
    if sys.platform == "darwin":
        return PlatformProfile.MACOS
    return PlatformProfile.GENERIC_LINUX


def path_warning(path: str) -> str | None:
    r"""Avertissement quand un chemin ne correspond pas a cette machine.

    Renvoie None si le chemin est coherent. C'est le controle qui manquait :
    `/mnt/user/data` saisi sous Windows passait sans un mot, et l'installation
    partait vers `C:\mnt\user\data`.
    """
    texte = path.strip()
    if not texte:
        return None
    # `[\\/]` et non `[\/]` : dans une classe, `\/` ne vaut que la barre oblique.
    # La forme fautive ne reconnaissait AUCUN chemin a antislash, donc pas meme
    # `C:\Users\...`, et les signalait tous comme « pas un chemin Windows ».
    ressemble_windows = bool(re.match(r"^[A-Za-z]:[\\/]", texte))
    if sys.platform == "win32" and not ressemble_windows:
        return t(
            "« {chemin} » n'est pas un chemin Windows. Il sera cree dans "
            "{resolu}, ce qui n'est probablement pas voulu.",
            chemin=texte,
            resolu=Path(texte).resolve(),
        )
    if sys.platform != "win32" and ressemble_windows:
        return t(
            "« {chemin} » est un chemin Windows, sur une machine qui ne l'est pas.",
            chemin=texte,
        )
    return None
