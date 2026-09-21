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
    #: Ce que le profil ne peut PAS deviner, et que l'utilisateur doit savoir
    #: avant de choisir : une contrainte du systeme, ou le fait que le profil
    #: lui-meme n'a pas encore ete eprouve. Vide quand il n'y a rien a dire.
    note: str = ""


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
    PlatformProfile.UGREEN: ProfileDefaults(
        # UGOS range les volumes comme DSM : /volume1, /volume2... crees dans
        # l'interface. `/srv` et `/opt` sont refuses, comme sur tout NAS.
        # Chemins etablis avec un utilisateur sur son propre NAS, le 2026-09-18.
        config_root="/volume1/docker/plugarr",
        data_root="/volume1/data",
        # Valeurs de repli seulement, et tirees d'UN SEUL NAS : `id` y rendait
        # `uid=1000 gid=10(admin)`. Que ce soit vrai de tous les UGOS n'est pas
        # etabli, d'ou la detection, qui passe devant.
        puid=1000,
        pgid=10,
        prefer_detection=True,
        source="utilisateur courant (UGOS : premier compte vu a 1000:10, groupe admin)",
        note=(
            "Profil EXPERIMENTAL : il vient d'une seule installation reelle, et "
            "les retours sont attendus sur le Discord de PlugArr. Deux choses "
            "qu'UGOS impose et qu'aucun profil ne peut contourner : les volumes "
            "appartiennent a root, donc l'installation demande `sudo` ; et les "
            "tunnels SSH sont interdits par defaut, donc l'assistant web ne "
            "s'ouvre pas a travers SSH — utilisez le mode terminal, ou servez-le "
            "sur le reseau local."
        ),
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


def _ids_sudo() -> tuple[int, int] | None:
    """UID/GID du compte qui a lance `sudo`, s'il y en a un.

    sudo pose `SUDO_UID` et `SUDO_GID` dans l'environnement de la commande
    elevee. Les deux doivent etre des entiers, et l'uid non nul : `sudo` lance
    depuis root donne SUDO_UID=0, qui n'apprend rien et ne doit pas faire croire
    qu'un vrai utilisateur a ete retrouve.

    Le gid manquant ne disqualifie pas l'uid : on retombe alors sur le gid du
    processus, ce qui vaut mieux que de renoncer au bon uid.
    """
    brut_uid, brut_gid = os.environ.get("SUDO_UID", ""), os.environ.get("SUDO_GID", "")
    if not brut_uid.strip().isdigit():
        return None
    uid = int(brut_uid.strip())
    if uid == 0:
        return None
    gid = int(brut_gid.strip()) if brut_gid.strip().isdigit() else None
    if gid is None:
        courant = detect_ids()
        gid = courant[1] if courant else uid
    return uid, gid


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
        # plus y toucher sans sudo.
        #
        # Sous `sudo`, le vrai utilisateur n'est pourtant pas perdu : sudo pose
        # SUDO_UID et SUDO_GID. C'est LUI qu'il faut retenir, pas le 0 de
        # l'elevation. Remonte le 2026-09-20 par un membre sur Synology : son
        # installation en sudo avait cree les dossiers en root, et Recyclarr,
        # dont l'image tourne en 1000:1000 et ignore PUID, se faisait jeter a
        # l'ecriture. Un `sudo` est souvent NECESSAIRE — /volume1 appartient a
        # root, personne d'autre ne peut y creer un dossier — donc refuser sudo
        # ne reglerait rien ; garder le bon identifiant, si.
        sous_sudo = _ids_sudo()
        if sous_sudo is not None:
            return (
                sous_sudo[0],
                sous_sudo[1],
                t("detecte sous sudo : votre compte, pas root"),
                True,
            )
        # Root sans sudo : la valeur reste proposee, jamais imposee, mais jamais
        # passee sous silence non plus.
        return (
            0,
            detected[1],
            "lance en root : conteneurs et medias appartiendront a root",
            False,
        )
    return detected[0], detected[1], t("detecte ({origine})", origine=t(defaults.source)), True


#: Images qui ignorent PUID/PGID et tournent sous l'utilisateur que leur donne
#: le compose (`user:`). Seerr tourne sinon en `node` (UID 1000) et plante sur
#: « EACCES: mkdir '/app/config/logs/' » dans un dossier qui n'est pas a lui
#: (constate sur le banc le 2026-09-19 ; sa documentation Docker demande un
#: `chown` ou `--user`).
#:
#: Recyclarr est dans le meme cas, remonte le 2026-09-20 par un membre sur
#: Synology : son image tourne en 1000:1000 en dur et ne lit pas PUID. Tant que
#: l'installation se faisait sous un compte a 1000, la coincidence tenait ; une
#: installation en `sudo` — obligatoire sous `/volume1`, qui appartient a root —
#: creait le dossier en root et Recyclarr se faisait jeter a l'ecriture. Il
#: n'avait alors aucune interface pour le dire : seule une synchronisation en
#: echec, sans cause lisible.
SANS_PUID = frozenset({"seerr", "recyclarr"})


def create_tree(
    data_root: str | Path,
    config_root: str | Path,
    service_ids: list[str],
    *,
    owner: tuple[int, int] | None = None,
) -> list[Path]:
    """Cree l'arborescence. Idempotent.

    `owner` (PUID, PGID) : lance en root, PlugArr donne ces identifiants aux
    dossiers de DONNEES qu'il cree, et au dossier de configuration des images de
    `SANS_PUID`. Le partage n'est pas arbitraire, il est mesure sur le banc le
    2026-09-20, image `linuxserver/sonarr:4.0.19`, avec les deux montages
    appartenant a root et PUID=1000, PGID=10 :

        /config  root:root  ->  1000:10 au demarrage  (l'image s'en charge)
        /data    root:root  ->  root:root             (personne ne s'en charge)
        touch /data/torrents/x  sous 1000:10  ->  Permission denied

    Autrement dit une installation en `sudo` — obligatoire sous `/volume1`, qui
    appartient a root — donnait une pile qui demarre et qui ne telecharge rien.
    Les images reprennent leur configuration, jamais les donnees.

    Les dossiers DEJA presents ne sont pas repris : un `chown -R` sur une
    mediatheque de plusieurs tera serait long, et ce n'est pas a une
    installation de redistribuer ce qu'elle n'a pas cree.
    """
    created: list[Path] = []
    data_root, config_root = Path(data_root), Path(config_root)
    for sub in DATA_SUBDIRS:
        p = data_root / sub
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            created.append(p)
            if owner is not None:
                # Tout juste cree, donc vide : le parcours de `_donner` ne coute
                # rien et n'atteint aucun fichier de l'utilisateur.
                _donner(p, owner)
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
        if sid in SANS_PUID and owner is not None:
            _donner(p, owner)
    return created


def _est_root() -> bool:
    import os

    return os.name == "posix" and os.geteuid() == 0


def _donner(dossier: Path, owner: tuple[int, int]) -> None:
    """Attribue le dossier et son contenu. Seul root le peut ; hors root, le
    dossier appartient deja a l'utilisateur qui lance PlugArr."""
    import os

    if not _est_root():
        return
    for chemin in (dossier, *dossier.rglob("*")):
        os.chown(chemin, *owner, follow_symlinks=False)


def _inscriptible_par(dossier: Path, owner: tuple[int, int]) -> bool:
    """Le compte (uid, gid) des conteneurs peut-il ECRIRE dans ce dossier ?

    On lit les droits du dossier, on ne les essaie pas : le seul essai qui
    vaudrait serait fait SOUS cet utilisateur, et plugarr ne peut pas devenir
    quelqu'un d'autre. La lecture suffit pour le cas qui nous occupe, un dossier
    laisse a root.

    Hors POSIX, la question n'a pas de sens : Docker Desktop ne reporte pas la
    propriete Unix sur un montage venu de Windows, et les bits de mode qu'y
    rend `stat` sont decoratifs. On repond oui plutot que d'inventer un
    probleme.
    """
    import stat as _stat

    if os.name != "posix":
        return True
    uid, gid = owner
    if uid == 0:
        return True
    try:
        infos = dossier.stat()
    except OSError:
        # Un dossier qu'on n'arrive meme pas a interroger n'est pas un dossier
        # dont on a quelque chose a dire ici.
        return True
    if infos.st_uid == uid:
        return bool(infos.st_mode & _stat.S_IWUSR)
    if infos.st_gid == gid:
        return bool(infos.st_mode & _stat.S_IWGRP)
    return bool(infos.st_mode & _stat.S_IWOTH)


def donnees_inaccessibles(data_root: str | Path, owner: tuple[int, int]) -> list[Path]:
    """Dossiers de donnees DEJA presents ou l'utilisateur des conteneurs ne
    peut pas ecrire.

    Constate le 2026-09-21 sur UGOS, journal a l'appui : une premiere
    installation avait cree `/volume2/data` en root, la suivante n'y touchait
    plus — `create_tree` ne reprend que ce qu'il cree — et Sonarr comme Radarr
    refusaient leurs dossiers racines sur « Folder '/data/media/tv' is not
    writable by user 'abc' ». Rien, dans l'installation, n'avait vu venir cette
    panne : l'arborescence etait complete, seuls les droits ne l'etaient pas.
    """
    racine = Path(data_root)
    presents = (racine / sous for sous in DATA_SUBDIRS)
    return [p for p in presents if p.is_dir() and not _inscriptible_par(p, owner)]


def ouvrir_donnees(data_root: str | Path, owner: tuple[int, int]) -> tuple[list[Path], list[Path]]:
    """Rend aux conteneurs les dossiers de donnees qu'ils ne peuvent pas ecrire.

    Renvoie (repares, restants) : ce qui a ete rendu, et ce qui resiste encore
    et doit donc etre dit a l'utilisateur.

    Le `chown` porte sur le DOSSIER SEUL, jamais sur son contenu. La distinction
    est tout le sujet : donner le dossier suffit a ce que les conteneurs y
    ecrivent, alors qu'un `chown -R` sur une mediatheque de plusieurs tera
    prendrait des heures et redistribuerait des fichiers que plugarr n'a pas
    crees. On repare le point de montage, on ne touche pas aux medias.

    Et on ne repare QUE ce qui est casse : un dossier deja inscriptible n'est
    pas repris, pour ne pas defaire un partage voulu (un dossier de groupe en
    2775, par exemple).
    """
    repares: list[Path] = []
    restants: list[Path] = []
    for dossier in donnees_inaccessibles(data_root, owner):
        if not _est_root():
            # Sans elevation, il n'y a rien a tenter : `chown` est refuse a tout
            # le monde sauf root, meme sur ses propres dossiers.
            restants.append(dossier)
            continue
        try:
            os.chown(dossier, *owner, follow_symlinks=False)
        except OSError:
            restants.append(dossier)
        else:
            repares.append(dossier)
    return repares, restants


def _dossiers_absents(chemin: Path) -> list[Path]:
    """Les dossiers de cette chaine qui n'existent pas encore, du plus profond
    au plus haut. C'est exactement ce qu'un `mkdir(parents=True)` va creer."""
    manquants: list[Path] = []
    courant = chemin
    while not courant.exists() and courant != courant.parent:
        manquants.append(courant)
        courant = courant.parent
    return manquants


def hardlink_supported(data_root: str | Path) -> tuple[bool, str]:
    """Teste REELLEMENT qu'un hardlink est possible entre torrents/ et media/.

    C'est le diagnostic qui distingue une stack qui recopie 40 Go a chaque import
    d'une stack qui fait un lien instantane. On ne suppose rien, on essaie.

    Et on remet en etat. Essayer demande deux VRAIS dossiers ; les laisser
    derriere soi faisait mentir `--dry-run`, dont l'ecran annonce « rien n'a
    encore ete ecrit » pendant que `DATA_ROOT/torrents` et `DATA_ROOT/media`
    apparaissaient sur le disque — avec toute leur chaine de parents, `mkdir`
    etant appele avec `parents=True`. Or `--dry-run` est precisement la commande
    qu'on lance pour regarder sans s'engager : quelqu'un qui compare trois
    emplacements en laissait trois, et celui qui se trompait de chemin creait
    une arborescence la ou il s'etait trompe.

    Le menage ne retire QUE ce que ce test a cree, et seulement si c'est reste
    vide : `rmdir` refuse un dossier non vide, ce qui est la garantie qu'on
    cherche. Une installation existante n'est donc jamais touchee.
    """
    data_root = Path(data_root)
    src_dir, dst_dir = data_root / "torrents", data_root / "media"

    # Releve AVANT toute creation, et pour les deux chaines : elles partagent
    # leurs parents, qu'un seul des deux releves suffirait a manquer.
    a_retirer = set(_dossiers_absents(src_dir)) | set(_dossiers_absents(dst_dir))
    try:
        try:
            src_dir.mkdir(parents=True, exist_ok=True)
            dst_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            # Le `t()` manquait ici, et lui seul : les deux autres sorties de
            # cette fonction l'avaient. Un utilisateur macOS en interface
            # anglaise voyait donc un tableau anglais avec cette ligne — et elle
            # seule — en francais. L'audit des traductions ne pouvait pas
            # l'attraper : il releve les `t("...")` presents, jamais un absent.
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
                "hardlink impossible ({erreur}). Les imports recopieront les "
                "fichiers au lieu de les lier. Verifiez que {source} et {cible} "
                "sont sur le MEME systeme de fichiers, et que DATA_ROOT est "
                "monte d'un seul bloc.",
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
    finally:
        # Du PLUS PROFOND au plus haut : `torrents` et `media` d'abord, leurs
        # parents ensuite, sinon `rmdir` bute sur un dossier encore occupe par
        # son propre enfant. Ce `finally` couvre aussi l'echec de `mkdir` a
        # mi-chemin, ou une partie de la chaine a pu etre creee malgre tout.
        for dossier in sorted(a_retirer, key=lambda p: len(p.parts), reverse=True):
            try:
                dossier.rmdir()
            except OSError:
                # Non vide, ou jamais cree. Dans les deux cas il ne nous
                # appartient pas : on n'insiste pas.
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
