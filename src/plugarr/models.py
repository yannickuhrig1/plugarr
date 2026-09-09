"""Modele de donnees d'une stack.

`StackConfig` est l'unique source de verite. `docker-compose.yml` et `.env` en sont
des artefacts generes, jamais edites a la main (voir PROMPT.md sec. 6).
"""

from __future__ import annotations

import os
import re
from enum import Enum
from pathlib import PurePosixPath

from pydantic import BaseModel, Field, field_validator

from .i18n import t


class Category(str, Enum):
    ARR = "arr"
    DOWNLOAD = "download"
    MEDIA = "media"
    UI = "ui"


class PlatformProfile(str, Enum):
    GENERIC_LINUX = "generic-linux"
    UNRAID = "unraid"
    SYNOLOGY = "synology"
    WINDOWS = "windows"
    MACOS = "macos"


class ServiceSpec(BaseModel):
    """Definition statique d'un service. Immuable, vit dans catalog.py."""

    id: str
    display_name: str
    category: Category
    image: str
    internal_port: int
    default_host_port: int
    #: Sous-dossier sous CONFIG_ROOT. None = le service n'a pas de config persistante.
    config_dir: str | None = None

    #: Ports PUBLIES en plus du principal, sous la forme (libelle, port interne).
    #: Silo en expose trois : son interface sur 8080, une API compatible Jellyfin
    #: sur 8096 et une API compatible Audiobookshelf sur 13378. Le libelle sert a
    #: l'affichage — « API Jellyfin » dit quelque chose, « port 8096 » non.
    extra_ports: tuple[tuple[str, int], ...] = ()

    #: Conteneur d'appoint : tire comme prerequis, jamais propose au choix.
    #: Une base de donnees n'est pas un service qu'on coche — c'est une piece de
    #: celui qui en depend. Sans ce drapeau, PostgreSQL apparaitrait dans
    #: l'assistant a cote de Sonarr, et sur la page d'acces avec un lien mort.
    internal: bool = False

    #: Ce service exige-t-il une cle de chiffrement au repos ?
    needs_secret_key: bool = False

    #: Avertissement a afficher quand le service n'est pas stable. Vide = stable.
    #: Le texte est repris du projet amont, pas redige par nous : c'est lui qui
    #: sait ou il en est. Un service instable qu'on presente comme les autres est
    #: un mensonge par omission.
    experimental: str = ""

    #: Services qui doivent etre SAINS avant celui-ci, pas seulement demarres.
    #: Silo refuse de demarrer si sa base n'a pas fini son initialisation.
    depends_on_healthy: tuple[str, ...] = ()
    #: Services requis pour que celui-ci ait un sens. Tous obligatoires.
    requires: tuple[str, ...] = ()
    #: Au moins UN de ces services est necessaire. Sert aux interfaces qui
    #: acceptent plusieurs backends, comme Flood.
    requires_one_of: tuple[str, ...] = ()
    #: Volumes DOCKER NOMMES, sous forme (nom, chemin dans le conteneur).
    #:
    #: Reserve a ce qui ne SUPPORTE PAS un montage vers le disque de l'hote.
    #: Deux cas mesures, tous deux des bases de donnees : PostgreSQL, dont les
    #: migrations passent de 2935 s a 5 s, et la base SQLite de DroppedNeedle,
    #: dont la verification apres mise a jour echoue purement et simplement.
    #:
    #: Tout le reste vit sous CONFIG_ROOT, ou l'utilisateur peut le lire, le
    #: sauvegarder et le corriger.
    named_volumes: tuple[tuple[str, str], ...] = ()

    #: Famille d'API, pilote le cablage. Voir wiring.py.
    api_family: str | None = None
    #: Version d'API des *arr : v3 pour Sonarr/Radarr, v1 pour Prowlarr.
    api_version: str = "v3"
    notes: str = ""

    @property
    def needs_config_volume(self) -> bool:
        return self.config_dir is not None


#: Fournisseurs acceptes par Gluetun. Liste obtenue de Gluetun LUI-MEME, en lui
#: passant un nom invalide : il repond avec l'enumeration exacte. Verifie contre
#: la v3.41.3, jamais recopiee d'un article.
VPN_PROVIDERS = (
    "airvpn", "cyberghost", "expressvpn", "fastestvpn", "giganews", "hidemyass",
    "ipvanish", "ivpn", "mullvad", "nordvpn", "perfect privacy", "privado",
    "private internet access", "privatevpn", "protonvpn", "purevpn", "slickvpn",
    "surfshark", "torguard", "vpnsecure", "vpn unlimited", "vyprvpn", "windscribe",
    "custom", "pia",
)


class VpnConfig(BaseModel):
    """Reglages Gluetun.

    Deux modes, et ils n'exigent pas les memes champs — constate en lancant
    Gluetun a vide et en lisant ce qu'il reclame :

    - `wireguard` : `WIREGUARD_PRIVATE_KEY` obligatoire, et la cle doit etre une
      vraie cle base64 ; Gluetun refuse toute autre chaine ;
    - `openvpn` : `OPENVPN_USER` et `OPENVPN_PASSWORD`.
    """

    enabled: bool = False
    provider: str = ""
    vpn_type: str = "wireguard"
    openvpn_user: str = ""
    openvpn_password: str = ""
    wireguard_private_key: str = ""
    wireguard_addresses: str = ""
    #: Filtre geographique, facultatif. Ex : "Switzerland,Netherlands".
    #: Le nom du champ dit « pays » par histoire ; la variable Gluetun qu'il
    #: alimente depend du fournisseur — voir `vpnservers.filter_env`.
    countries: str = ""

    @field_validator("provider")
    @classmethod
    def _known_provider(cls, v: str) -> str:
        v = v.strip().lower()
        if v and v not in VPN_PROVIDERS:
            raise ValueError(
                f"fournisseur VPN inconnu de Gluetun: {v!r}. "
                f"Choix possibles : {', '.join(VPN_PROVIDERS)}"
            )
        return v

    @field_validator("vpn_type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("wireguard", "openvpn"):
            raise ValueError(f"type de VPN inconnu: {v!r} (attendu wireguard ou openvpn)")
        return v

    def missing(self) -> list[str]:
        """Ce qui manque pour que Gluetun demarre. Vide = pret."""
        if not self.enabled:
            return []
        gaps: list[str] = []
        if not self.provider:
            gaps.append(t("le fournisseur VPN (--vpn-provider)"))
        if self.vpn_type == "wireguard":
            if not self.wireguard_private_key:
                gaps.append(t("la cle privee WireGuard (--vpn-key)"))
        elif not self.openvpn_user or not self.openvpn_password:
            gaps.append(t("les identifiants OpenVPN (--vpn-user et --vpn-pass)"))
        return gaps

    def environment(self, timezone: str) -> dict[str, str]:
        env = {
            "VPN_SERVICE_PROVIDER": self.provider,
            "VPN_TYPE": self.vpn_type,
            "TZ": timezone,
        }
        # Les secrets passent par le .env, comme tous les autres. Ils etaient
        # ecrits EN CLAIR dans docker-compose.yml : la cle privee WireGuard —
        # celle qui ouvre le compte VPN — etait le seul secret de plugarr a
        # echapper au fichier protege par chmod 600. Constate en relisant le
        # compose d'une installation reelle.
        if self.vpn_type == "wireguard":
            env["WIREGUARD_PRIVATE_KEY"] = "${VPN_WIREGUARD_KEY}"
            if self.wireguard_addresses:
                env["WIREGUARD_ADDRESSES"] = self.wireguard_addresses
        else:
            env["OPENVPN_USER"] = "${VPN_OPENVPN_USER}"
            env["OPENVPN_PASSWORD"] = "${VPN_OPENVPN_PASS}"
        # Un port ENTRANT, quand le fournisseur le permet. Sans lui, le client
        # telecharge tres bien mais ne partage qu'a moitie : seuls les pairs qui
        # acceptent nos connexions sortantes sont joignables. Ce n'est pas une
        # question de protection — les vingt et un autres fournisseurs chiffrent
        # pareil — mais de ratio, et rien ne le signalait.
        #
        # Aucune case a cocher : c'est un gain sans contrepartie, et le controle
        # de `vpncheck` dira si le port est reellement arrive plutot que de le
        # supposer.
        #
        # `PORT_FORWARD_ONLY` n'est deliberement PAS pose : verifie contre l'image
        # v3.41.3, `VPN_PORT_FORWARDING=on` restreint DEJA la selection aux
        # serveurs qui l'offrent. Une sonde ProtonVPN sur Macedonia, pays sans
        # port forwarding, echoue de la meme facon avec ou sans le drapeau :
        #
        #   ERROR [vpn] finding a VPN server: filtering servers: no server found:
        #   ... country macedonia; port forwarding only
        #
        # C'est aussi pourquoi l'assistant ne propose que les lieux qui en ont :
        # Gluetun ne demarre PAS du tout si le lieu choisi n'en offre aucun.
        from .vpnservers import port_forward

        if port_forward(self.provider):
            env["VPN_PORT_FORWARDING"] = "on"
        if self.countries:
            # PAS toujours SERVER_COUNTRIES. Cinq fournisseurs n'exposent aucun
            # pays dans les donnees de Gluetun : Windscribe, VyprVPN, Giganews
            # et Private Internet Access classent par region, Perfect Privacy
            # par ville. Leur poser SERVER_COUNTRIES ne filtrait rien.
            from .vpnservers import filter_env

            env[filter_env(self.provider)] = self.countries
        return env


class ServiceInstance(BaseModel):
    """Un service reellement selectionne, avec ses secrets et son port resolus."""

    spec_id: str
    host_port: int
    #: Cle API pre-semee pour les *arr. None pour les services sans cle.
    api_key: str | None = None
    username: str | None = None
    password: str | None = None

    #: True quand le service existait DEJA et n'est pas gere par plugarr :
    #: aucun conteneur n'est genere pour lui, on se contente de le cabler.
    adopted: bool = False
    #: Nom du conteneur existant, pour un service adopte.
    container: str | None = None
    #: `UrlBase` du service, quand il n'est pas servi a la racine.
    url_base: str = ""

    #: Cle de chiffrement AU REPOS, distincte d'un mot de passe. Elle ne sert
    #: pas a se connecter : elle chiffre les secrets que le service stocke.
    #: La confondre avec un mot de passe serait grave — on peut reinitialiser un
    #: mot de passe, pas celle-ci. Sa PERTE rend les donnees chiffrees
    #: irrecuperables, ce que la page d'acces doit dire.
    secret_key: str = ""

    #: Ports supplementaires REELLEMENT publies, {port interne: port hote}.
    #: Le catalogue donne les valeurs par defaut ; celles-ci peuvent etre
    #: decalees pour eviter un conflit. C'est ainsi que Silo peut exposer son
    #: API compatible Jellyfin ailleurs que sur 8096, la ou Jellyfin ecoute
    #: deja : son conteneur garde 8096 en interne, seul le cote hote bouge.
    extra_ports: dict[int, int] = Field(default_factory=dict)

    #: Image REELLEMENT deployee, tag compris. Le catalogue ne fournit que la
    #: valeur par defaut : sans ce champ, la version serait figee dans le code
    #: de plugarr et personne ne pourrait mettre a jour Sonarr sans attendre une
    #: nouvelle version de l'outil.
    image: str = ""

    @property
    def has_web_ui(self) -> bool:
        """Ce service publie-t-il quelque chose a ouvrir dans un navigateur ?

        Recyclarr n'a pas d'interface : il tourne sur une planification et ne
        publie aucun port. Tout affichage doit le savoir, sans quoi il propose un
        lien vers `http://hote:0` — un lien mort au milieu d'une page de
        raccourcis fait conclure que l'installation a echoue.
        """
        return bool(self.host_port)

    def url(self, host: str = "localhost") -> str:
        base = f"http://{host}:{self.host_port}"
        return f"{base}/{self.url_base}" if self.url_base else base

    def internal_url(
        self, spec: ServiceSpec, host: str = "localhost", *, behind_vpn: bool = False
    ) -> str:
        """URL a utiliser quand un service en appelle un autre.

        Pour une stack geree par plugarr, les conteneurs partagent un reseau
        compose : le nom de SERVICE resout, et c'est le plus robuste.

        Sous VPN, un client de telechargement perd son alias DNS : il partage la
        pile reseau de Gluetun. C'est `behind_vpn` qui l'exprime.

        Pour un service ADOPTE, non plus. Les conteneurs existants vivent sur leurs
        propres reseaux, souvent differents les uns des autres : `http://sonarr:8989`
        ne resout pas d'un reseau a l'autre. Il faut passer par l'adresse de
        l'hote et le port publie, seul chemin garanti entre deux conteneurs
        etrangers l'un a l'autre.
        """
        if self.adopted:
            return self.url(host)
        if behind_vpn:
            # Sous `network_mode: service:gluetun`, le conteneur n'a plus de pile
            # reseau propre : il perd son alias DNS. `http://qbittorrent:8080` ne
            # resout plus, il faut viser gluetun, qui porte desormais sa place
            # dans le reseau ET ses ports.
            return f"http://gluetun:{spec.internal_port}"
        return f"http://{spec.id}:{spec.internal_port}"


#: Forme acceptee pour l'identifiant.
#:
#: La longueur minimale est de UN caractere : verifie contre qBittorrent 5.2.3,
#: qui accepte « ab » sans broncher (HTTP 204 a la connexion). Imposer trois
#: caracteres aurait ete une contrainte inventee.
#:
#: Le jeu de caracteres, lui, est bien une contrainte reelle : ce nom finit dans
#: un XML, un INI, un JSON, un formulaire de connexion et une ligne de commande
#: de conteneur. Espaces, accents et ponctuation exotique y passeraient
#: peut-etre — mais « peut-etre » ne convient pas pour une valeur qu'on ne peut
#: plus changer sans tout reinstaller.
USERNAME_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,32}")


class StackConfig(BaseModel):
    """Etat canonique versionnable (stack.yml)."""

    version: int = 1
    project_name: str = "plugarr"
    platform: PlatformProfile = PlatformProfile.GENERIC_LINUX

    config_root: str
    data_root: str

    puid: int = 1000
    pgid: int = 1000
    umask: str = "002"
    timezone: str = "Etc/UTC"

    #: Hote joignable depuis le navigateur de l'utilisateur, pour le rapport final.
    host: str = "localhost"

    #: Langue des SERVICES, code ISO 639-1. Appliquee partout ou le service
    #: sait la recevoir. Avant, plugarr imposait le francais a Jellyfin — en
    #: dur, dans la signature du client — et laissait tout le reste en anglais :
    #: une incoherence que personne n'avait choisie.
    language: str = "en"

    #: Langue de PLUGARR lui-meme : assistant, ligne de commande, rapport,
    #: page d'acces. Distincte de `language` juste au-dessus, qui vise les
    #: services : on peut vouloir l'outil en anglais et sa mediatheque en
    #: francais. Conservee ici pour que `serve`, `doctor` et la page
    #: d'administration retrouvent le choix fait a l'installation, plutot que
    #: de redemander ou de retomber sur le systeme d'une autre machine.
    ui_language: str = "fr"

    #: Identifiant commun a tous les services. « plugarr » n'est qu'un defaut :
    #: demande a l'usage, tout le monde ne veut pas ce nom-la.
    username: str = "plugarr"

    #: Empreinte du mot de passe de la console d'administration. Vide = la
    #: console n'accepte que le jeton tire a chaque demarrage, ce qui suffit
    #: quand on la lance a la main. Voir `adminauth`. JAMAIS le mot de passe en
    #: clair : ce fichier est celui qu'on ouvre pour retrouver un port.
    admin_password_hash: str = ""

    #: D'ou viennent puid/pgid. Affiche a l'utilisateur : des identifiants faux
    #: cassent les permissions de toute la stack, il doit pouvoir les juger.
    ids_source: str = "non renseigne"
    #: False quand on s'est rabattu sur une valeur par defaut faute de detection.
    ids_certain: bool = True

    services: dict[str, ServiceInstance] = Field(default_factory=dict)

    vpn: VpnConfig = Field(default_factory=VpnConfig)

    #: Template TRaSH choisi par service. Vide = celui par defaut de Recyclarr.
    recyclarr_templates: dict[str, str] = Field(default_factory=dict)
    #: Repertoire des artefacts, necessaire pour lancer une commande ponctuelle.
    #: Renseigne a l'execution, pas persiste : il depend d'ou l'on se trouve.
    project_dir: object | None = Field(default=None, exclude=True)

    @property
    def vpn_enabled(self) -> bool:
        """Raccourci de lecture. Desactive = avertissement au recapitulatif."""
        return self.vpn.enabled

    @field_validator("config_root", "data_root")
    @classmethod
    def _no_trailing_sep(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError(t("le chemin ne peut pas etre vide"))
        return v.rstrip("/\\") or v

    @field_validator("username")
    @classmethod
    def _username_utilisable(cls, v: str) -> str:
        """Un identifiant qui traverse cinq applications differentes.

        Les caracteres acceptes sont volontairement restreints : ce nom finit
        dans un XML, un INI, un JSON, un formulaire de connexion et une ligne de
        commande de conteneur. Une espace ou un accent y passeraient peut-etre,
        mais « peut-etre » ne convient pas pour une valeur qu'on ne peut plus
        changer sans tout reinstaller.
        """
        v = v.strip()
        if not USERNAME_PATTERN.fullmatch(v):
            raise ValueError(
                t(
                    "identifiant invalide : {valeur}. Attendu 1 a 32 caracteres "
                    "parmi lettres, chiffres, point, tiret et souligne, sans "
                    "espace.",
                    valeur=repr(v),
                )
            )
        return v

    @field_validator("umask")
    @classmethod
    def _umask_form(cls, v: str) -> str:
        if not (len(v) in (3, 4) and all(c in "01234567" for c in v)):
            raise ValueError(f"umask invalide: {v!r} (attendu 3 ou 4 chiffres octaux)")
        return v

    # -- chemins -------------------------------------------------------------

    def config_path(self, service_id: str) -> str:
        # Separateurs normalises : ces chemins finissent dans un .env lu par Docker,
        # qui n'aime pas les antislashs melanges aux slashs.
        return f"{self.config_root.replace(os.sep, '/')}/{service_id}"

    @staticmethod
    def container_data_root() -> PurePosixPath:
        """Montage unique dans TOUS les conteneurs. C'est ce qui rend les
        hardlinks possibles entre /data/torrents et /data/media."""
        return PurePosixPath("/data")

    def enabled(self, service_id: str) -> bool:
        return service_id in self.services
