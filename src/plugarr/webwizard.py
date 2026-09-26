"""Assistant web local : saisie, preflight et progression du moteur existant.

Le jeton reste dans le fragment de l'URL puis en memoire de session du navigateur.
Aucune route ne lance une commande arbitraire. Le mode demo n'appelle ni Docker,
ni le moteur d'installation, ni les lecteurs de configuration de l'utilisateur.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import ntpath
import posixpath
import re
import secrets
import shutil
import sys
import tempfile
import threading
import time
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import (
    __version__,
    admin,
    adminauth,
    catalog,
    compose,
    dashboard,
    downloadclients,
    i18n,
    imageref,
    import_prowlarr,
    journal,
    migrations,
    orchestrator,
    remote_access,
    remote_install,
    reprise,
    sauvegarde,
    updates,
    vpnessai,
    vpnservers,
    wizard_graph,
)
from .admin import vider_corps_requete
from .clients import recyclarr
from .clients.arr import ArrClient
from .clients.prowlarr import IndexerDefinition, ProwlarrIndexers
from .compose import GLUETUN_TAG
from .interface import Interface, save_preference
from .layout import (
    PROFILE_DEFAULTS,
    default_profile,
    hardlink_supported,
    path_warning,
    resolve_ids,
)
from .models import INTERFACES_QBITTORRENT, VPN_PROVIDERS, PlatformProfile, VpnConfig
from .phone_share import TAILLE_MAX as MAX_PHONE_SHARE
from .phone_share import PartageTelephone
from .remote_models import RemoteAccessConfig
from .runner import Check, check_docker
from .wiring import StepResult

ASSETS = Path(__file__).parent / "web"
MAX_INDEXER_RESULTS = 40
#: Une archive PlugArr complete pese une centaine de Mo ; une sauvegarde
#: Prowlarr seule, un ou deux.
MAX_BACKUP_UPLOAD = 2 * 1024 * 1024 * 1024
DEFAULT_VPN = "protonvpn"
VPN_ALIASES = {"pia": "private internet access"}


class WizardInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    services: list[str] = Field(min_length=1, max_length=40)
    platform: str
    config_root: str = Field(min_length=1, max_length=1024)
    data_root: str = Field(min_length=1, max_length=1024)
    project_name: str = Field(min_length=1, max_length=63)
    username: str = Field(min_length=1, max_length=32)
    host: str = Field(default="localhost", min_length=1, max_length=255)
    timezone: str = "Etc/UTC"
    language: str = "fr"
    ui_language: str = "fr"
    vpn: dict = Field(default_factory=dict)
    recyclarr_templates: dict[str, str] = Field(default_factory=dict)
    reprendre: bool = True
    reset_config: bool = False
    client_prefere: str = ""
    qbittorrent_ui: str = ""
    veille_enabled: bool = False
    veille_port: int = 7374
    veille_socket: bool = False
    console_enabled: bool = False
    console_port: int = 7373
    remote_access: RemoteAccessConfig = Field(default_factory=RemoteAccessConfig)
    install_target: str = "local"
    remote_connection_id: str = Field(default="", max_length=128)
    remote_fingerprint: str = Field(default="", max_length=256)
    remote_project_dir: str = Field(default="", max_length=1024)
    remote_replace: bool = False
    #: Reprise seulement : prendre la version testee du catalogue quand elle
    #: est plus recente que celle installee. Sans cela, chaque application garde
    #: la sienne, ce qui reste le comportement par defaut.
    upgrade_images: bool = False
    #: Reprise seulement : remplacer le mot de passe de la console, qui n'est
    #: affiche qu'une fois, dans le rapport de l'installation qui l'a cree.
    new_console_password: bool = False


class RemoteSSHInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(default="", max_length=4096)
    private_key: str = Field(default="", max_length=32768)
    passphrase: str = Field(default="", max_length=4096)
    sudo_password: str = Field(default="", max_length=4096)


def version_plus_recente(testee: str, installee: str) -> bool:
    """La version testee du catalogue est-elle plus recente que l'installee ?

    Une version illisible des deux cotes n'est jamais une raison de changer.
    """
    a = updates.parse_version(imageref.parse(testee).tag) if testee else None
    b = updates.parse_version(imageref.parse(installee).tag) if installee else None
    return a is not None and b is not None and a > b


def changements_de_version(previous) -> list[dict]:
    """Ce que « passer aux versions testees » changerait, application par application.

    Demande du 26/09/2026 : reprendre une installation ne doit pas obliger a
    tout reparametrer pour obtenir les versions que PlugArr vient de tester.
    """
    changements = []
    for sid, inst in previous.services.items():
        if sid not in catalog.CATALOG or inst.adopted or not inst.image:
            continue
        testee = catalog.get(sid).image
        if not version_plus_recente(testee, inst.image):
            continue
        avant = updates.parse_version(imageref.parse(inst.image).tag)
        apres = updates.parse_version(imageref.parse(testee).tag)
        changements.append(
            {
                "id": sid,
                "name": catalog.get(sid).display_name,
                "installed": imageref.parse(inst.image).tag,
                "tested": imageref.parse(testee).tag,
                "major": bool(avant and apres and avant[0] != apres[0]),
            }
        )
    return changements


class WizardState:
    def __init__(self, project_dir: Path, *, demo: bool = False):
        self.launch_project_dir = project_dir.resolve()
        self.project_dir = self.launch_project_dir
        self.demo = demo
        self.remote_result = None
        self.remote_worker = None
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.revision = 0
        self.graph = None
        self.graph_results = {}
        self.active_step = None
        self.deployed = False
        self.previous = None
        self.previous_project_dir: Path | None = None
        self.watched_stack: Path | None = None
        self.initial_hash = None
        if not demo:
            self.reload_previous()
        self.cfg = None
        self.reprise = None
        self.reset_candidates: list[str] = []
        self.reset_requested = False
        self.reset_cfg = None
        self.reset_project_dir: Path | None = None
        self.reset_existing_stack = False
        self.results = []
        self.plan_id = None
        self.validated_at = 0.0
        self.events: list[dict] = []
        self.status = "idle"
        self.worker = None
        self.admin_server = None
        self.admin_url = None
        self.console_password = ""
        #: Lien a usage unique vers le telephone (QR code), ouvert a la demande.
        self.phone_share: PartageTelephone | None = None
        self.restore_inspections: dict[str, dict] = {}
        self.indexer_client: ArrClient | None = None
        self.indexers: ProwlarrIndexers | None = None
        self.indexer_matches: dict[str, IndexerDefinition] = {}
        #: Indexeurs lus dans une sauvegarde, avec leurs identifiants. Ils ne
        #: quittent jamais le serveur : le navigateur ne voit que la cle.
        self.backup_indexers: dict[str, import_prowlarr.IndexeurSauvegarde] = {}
        #: Connexions SSH sondees. Les secrets restent uniquement dans ce
        #: processus et disparaissent a la fermeture de l'assistant.
        self.remote_connections: dict[str, dict[str, object]] = {}
        self.install_target = "local"
        self.remote_connection_id = ""
        self.remote_project_dir = ""
        self.remote_existing_sha = ""
        self.remote_replace_confirmed = False
        self.result = 0

    def stack_hash(self, path: Path | None = None):
        path = path or self.watched_stack or (self.launch_project_dir / "stack.yml")
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

    def reload_previous(self):
        """Retrouve la pile comme le TUI, sans avaler un stack local invalide."""
        self.project_dir = self.launch_project_dir
        here = self.launch_project_dir / "stack.yml"
        found = None
        if here.exists():
            # Une configuration locale illisible ou future doit bloquer, jamais
            # etre traitee comme une installation neuve.
            cfg, _ = migrations.lire(here)
            found = reprise.Trouvee(cfg, here)
        else:
            found = reprise.trouver(self.launch_project_dir)
        self.previous = found.cfg if found else None
        self.previous_project_dir = found.project_dir if found else None
        self.watched_stack = found.chemin if found else here
        self.initial_hash = self.stack_hash(self.watched_stack)

    def bootstrap(self):
        cfg = self.previous
        platform = cfg.platform if cfg else default_profile()
        defaults = PROFILE_DEFAULTS[platform]
        icons = json.loads((ASSETS.parent / "data/connection_icons.json").read_text("utf-8"))
        vpn = cfg.vpn.model_dump() if cfg else VpnConfig().model_dump()
        for key in ("wireguard_private_key", "openvpn_password", "openvpn_user"):
            vpn[key] = ""  # Les champs vides conservent les identifiants existants.
        vpn["provider"] = VPN_ALIASES.get(vpn.get("provider"), vpn.get("provider"))
        if not vpn.get("provider"):
            vpn["provider"] = DEFAULT_VPN
        providers = [p for p in VPN_PROVIDERS if p not in VPN_ALIASES]
        providers.sort(key=lambda p: (not vpnservers.port_forward(p), p.casefold()))
        profiles = {}
        for profile, profile_defaults in PROFILE_DEFAULTS.items():
            uid, gid, source, certain = resolve_ids(profile)
            profiles[profile.value] = {
                "config_root": profile_defaults.config_root,
                "data_root": profile_defaults.data_root,
                "puid": uid,
                "pgid": gid,
                "ids_source": i18n.t(source),
                "ids_certain": certain,
                # Ce que le profil ne peut pas deviner : une contrainte du
                # systeme, ou le fait qu'il n'ait pas encore ete eprouve.
                "note": i18n.t(profile_defaults.note) if profile_defaults.note else "",
            }
        backup = {"available": False, "source": "", "destination": ""}
        if cfg is not None and self.previous_project_dir is not None:
            backup = {
                "available": True,
                "source": str(self.previous_project_dir),
                "destination": str(self.previous_project_dir / sauvegarde.nom_par_defaut(cfg)),
                "services": sorted(cfg.services),
                "config_root": cfg.config_root,
            }
        return {
            "version": __version__,
            "demo": self.demo,
            "existing": cfg is not None,
            "existing_project_dir": str(self.previous_project_dir) if self.previous_project_dir else "",
            "download_clients": list(catalog.DOWNLOAD_CLIENTS),
            "torrent_clients": list(catalog.TORRENT_CLIENTS),
            "download_order": list(downloadclients.ORDRE_AUTO),
            "client_protocols": {
                sid: downloadclients.profile_for(sid).protocol
                for sid in catalog.DOWNLOAD_CLIENTS
            },
            "project_dir": str(self.launch_project_dir),
            "icons": icons,
            "can_tui": not self.demo and sys.stdin.isatty() and sys.stdout.isatty(),
            "catalog": [
                {
                    "id": s.id,
                    "name": s.display_name,
                    "category": s.category.value,
                    "notes": i18n.t(s.notes),
                    "experimental": i18n.t(s.experimental),
                    "requires": list(s.requires),
                    "requires_one_of": list(s.requires_one_of),
                }
                for s in catalog.CATALOG.values()
                if not s.internal
            ],
            "profiles": profiles,
            "providers": {
                p: {
                    "choices": vpnservers.pf_choices(p)
                    if vpnservers.port_forward(p)
                    else vpnservers.choices(p),
                    "total": len(vpnservers.choices(p)),
                    "label": i18n.t(vpnservers.label(p)),
                    "port_forward": vpnservers.port_forward(p),
                    "version": vpnservers.gluetun_version(),
                }
                for p in providers
            },
            "backup": backup,
            "form": self._form_for(cfg, platform, defaults, vpn),
        }

    def _form_for(self, cfg, platform, defaults, vpn):
        """Formulaire initial, depuis une configuration existante ou les defauts."""
        return {
                "services": [s for s in cfg.services if not catalog.get(s).internal]
                if cfg
                else list(catalog.DEFAULT_SELECTION),
                "platform": platform.value,
                "config_root": cfg.config_root if cfg else defaults.config_root,
                "data_root": cfg.data_root if cfg else defaults.data_root,
                "project_name": cfg.project_name if cfg else "plugarr",
                "username": cfg.username if cfg else "plugarr",
                "host": cfg.host if cfg else "localhost",
                "timezone": cfg.timezone if cfg else "Etc/UTC",
                "language": cfg.language if cfg else i18n.langue(),
                "ui_language": cfg.ui_language if cfg else i18n.langue(),
                "vpn": vpn,
                "recyclarr_templates": cfg.recyclarr_templates if cfg else {},
                "client_prefere": cfg.client_prefere if cfg else "",
                "qbittorrent_ui": cfg.qbittorrent_ui if cfg else "",
                "veille_enabled": cfg.veille_enabled if cfg else False,
                "veille_port": cfg.veille_port if cfg else 7374,
                "veille_socket": cfg.veille_socket if cfg else False,
                "console_enabled": cfg.console_enabled if cfg else False,
                "console_port": cfg.console_port if cfg else 7373,
                "remote_access": cfg.remote_access.model_dump() if cfg else {"mode": "local", "domain": "", "services": []},
                "install_target": "local",
                "remote_connection_id": "",
                "remote_fingerprint": "",
                "remote_project_dir": "",
                "remote_replace": False,
                "reprendre": cfg is not None,
                "reset_config": False,
        }

    def _remote_previous(self, target, credentials, probe_result, project_dir):
        """Pile PlugArr deja presente sur la cible, pour la reprendre.

        Second passage reel du 25/09/2026 sur un VPS : sans reprise, l'assistant
        repartait des defauts, regenerait les mots de passe et perdait le VPN.
        """
        state = remote_install.inspect_project(
            remote_install.RemoteTarget(
                host=target.host,
                port=target.port,
                username=target.username,
                expected_fingerprint=probe_result.fingerprint,
            ),
            credentials,
            project_dir,
            connect=remote_install.connect_paramiko,
        )
        if not (state.managed and state.stack_yaml):
            return None
        try:
            cfg, _notes = migrations.lire_texte(state.stack_yaml)
        except (ValueError, ValidationError):
            return None
        return cfg

    def _default_form(self):
        """Reglages par defaut, sans rien d'une installation precedente."""
        platform = default_profile()
        vpn = VpnConfig().model_dump()
        vpn["provider"] = VPN_ALIASES.get(vpn.get("provider"), vpn.get("provider")) or DEFAULT_VPN
        return self._form_for(None, platform, PROFILE_DEFAULTS[platform], vpn)

    def _remote_form(self, cfg):
        platform = cfg.platform
        vpn = cfg.vpn.model_dump()
        for key in ("wireguard_private_key", "openvpn_password", "openvpn_user"):
            vpn[key] = ""  # Les champs vides conservent les identifiants existants.
        vpn["provider"] = VPN_ALIASES.get(vpn.get("provider"), vpn.get("provider"))
        return self._form_for(cfg, platform, PROFILE_DEFAULTS[platform], vpn)

    def _remote_connection_for(self, form: WizardInput):
        if form.install_target == "local":
            self.install_target = "local"
            self.remote_connection_id = ""
            self.remote_project_dir = ""
            return None
        if form.install_target != "ssh":
            raise ValueError("Destination d'installation inconnue.")
        connection = self.remote_connections.get(form.remote_connection_id)
        if connection is None:
            raise ValueError("Connexion SSH absente ou expiree. Testez-la a nouveau.")
        if form.reprendre and connection.get("previous") is None:
            raise ValueError(
                "Aucune pile PlugArr a reprendre sur ce serveur; "
                "la reprise locale ne s'applique pas a une installation distante."
            )
        if time.monotonic() - float(connection["created_at"]) > 900:
            self.remote_connections.pop(form.remote_connection_id, None)
            raise ValueError("Le test SSH a expire. Testez la connexion a nouveau.")
        probe_result = connection["probe"]
        if not isinstance(probe_result, remote_install.RemoteProbe) or not probe_result.ready:
            raise ValueError("La cible SSH doit etre Linux avec Docker operationnel.")
        if not hmac.compare_digest(form.remote_fingerprint, probe_result.fingerprint):
            raise ValueError("Confirmez exactement l'empreinte SSH affichee.")
        project = posixpath.normpath(form.remote_project_dir)
        if (
            not project.startswith("/")
            or project == "/"
            or any(char in form.remote_project_dir for char in ("\n", "\r", "\x00"))
        ):
            raise ValueError("Le dossier du projet distant doit etre un chemin Linux absolu.")
        self.install_target = "ssh"
        self.remote_connection_id = form.remote_connection_id
        self.remote_project_dir = project
        cible = connection["target"]
        self.remote_ssh = (cible.username, cible.host, cible.port)
        return connection

    def build_config(self, payload):
        form = payload if isinstance(payload, WizardInput) else WizardInput.model_validate(payload)
        platform = PlatformProfile(form.platform)
        connection = self._remote_connection_for(form)
        if connection is not None and platform == PlatformProfile.WINDOWS:
            raise ValueError("L'installation SSH prend en charge les cibles Linux et NAS.")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", form.project_name):
            raise ValueError("Nom de pile : lettres minuscules, chiffres, tirets et underscores.")
        if any(s not in catalog.CATALOG or catalog.get(s).internal for s in form.services):
            raise ValueError("Service inconnu ou reserve aux dependances internes.")
        for path in (form.config_root, form.data_root):
            absolute = (
                bool(re.match(r"^[A-Za-z]:[/\\]", path))
                if platform == PlatformProfile.WINDOWS
                else path.startswith("/")
            )
            if not absolute or any(c in path for c in ("\n", "\r", "\x00", "$", '"')):
                raise ValueError(
                    "Utilisez des chemins absolus, sans variable ni retour a la ligne."
                )
        path_module = ntpath if platform == PlatformProfile.WINDOWS else posixpath

        def comparable(path):
            path = path_module.normpath(path).replace("\\", "/").rstrip("/")
            return path.casefold() if platform == PlatformProfile.WINDOWS else path

        config_path = comparable(form.config_root)
        data_path = comparable(form.data_root)
        if (
            not config_path
            or not data_path
            or config_path == data_path
            or config_path.startswith(data_path + "/")
            or data_path.startswith(config_path + "/")
        ):
            raise ValueError(
                "Les dossiers de configuration et de medias doivent etre distincts, sans imbrication."
            )
        try:
            ZoneInfo(form.timezone)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Fuseau horaire inconnu.") from exc
        if form.ui_language not in ("fr", "en") or form.language not in (
            "fr",
            "en",
            "de",
            "es",
            "it",
            "pt",
            "nl",
        ):
            raise ValueError("Langue non prise en charge par cet assistant.")
        host = form.host.strip()
        if not re.fullmatch(r"[A-Za-z0-9._:\-\[\]]+", host):
            raise ValueError("Adresse de la machine invalide : indiquez un nom ou une adresse IP.")
        cfg = orchestrator.build_config(
            services=form.services,
            platform=platform,
            config_root=form.config_root,
            data_root=form.data_root,
            project_name=form.project_name,
            username=form.username,
            host=host,
            timezone=form.timezone,
            language=form.language,
        )
        if connection is not None:
            probe_result = connection["probe"]
            cfg.puid = probe_result.uid
            cfg.pgid = probe_result.gid
            cfg.ids_source = "utilisateur SSH distant"
            cfg.ids_certain = True
        # En SSH, la configuration a reprendre est celle du serveur, jamais celle
        # du poste qui lance l'assistant.
        previous = connection.get("previous") if connection is not None else self.previous
        vpn = dict(form.vpn)
        if set(vpn) - set(VpnConfig.model_fields):
            raise ValueError("Champ VPN inconnu.")
        if form.reprendre and previous and previous.vpn.enabled:
            old_vpn = previous.vpn
            old_provider = VPN_ALIASES.get(old_vpn.provider, old_vpn.provider)
            if vpn.get("provider") == old_provider and vpn.get("vpn_type") == old_vpn.vpn_type:
                for key in ("wireguard_private_key", "openvpn_password", "openvpn_user"):
                    if not vpn.get(key):
                        vpn[key] = getattr(old_vpn, key)
        cfg.vpn = VpnConfig.model_validate(vpn)
        if any(
            any(c in value for c in ("\n", "\r", "\x00"))
            for value in cfg.vpn.model_dump().values()
            if isinstance(value, str)
        ):
            raise ValueError("Les champs VPN ne doivent pas contenir de retour a la ligne.")
        if cfg.vpn.enabled:
            if not any(
                cfg.enabled(s) and cfg.vpn.protects(s) for s in catalog.DOWNLOAD_CLIENTS
            ):
                raise ValueError("Le VPN demande au moins un client selectionne a proteger.")
            if cfg.vpn.missing():
                raise ValueError("Configuration VPN incomplete : " + ", ".join(cfg.vpn.missing()))
            if cfg.vpn.vpn_type == "wireguard":
                try:
                    if len(base64.b64decode(cfg.vpn.wireguard_private_key, validate=True)) != 32:
                        raise ValueError()
                except ValueError as exc:
                    raise ValueError(
                        "La cle WireGuard doit contenir 32 octets encodes en base64."
                    ) from exc
            places = (
                vpnservers.pf_choices(cfg.vpn.provider)
                if vpnservers.port_forward(cfg.vpn.provider)
                else vpnservers.choices(cfg.vpn.provider)
            )
            if places and any(
                p.strip() not in places for p in cfg.vpn.countries.split(",") if p.strip()
            ):
                raise ValueError("Localisation VPN absente de la liste de Gluetun.")
        elif cfg.vpn.protect_sabnzbd:
            raise ValueError("SABnzbd ne peut pas passer par un VPN desactive.")
        if cfg.vpn.protect_sabnzbd and not cfg.enabled("sabnzbd"):
            raise ValueError("Le trajet VPN de SABnzbd demande que SABnzbd soit selectionne.")
        cfg.ui_language = form.ui_language
        if form.client_prefere:
            if form.client_prefere not in downloadclients.concurrents(cfg.services):
                raise ValueError(
                    "Client de telechargement prefere invalide pour la selection."
                )
            cfg.client_prefere = form.client_prefere
        if form.qbittorrent_ui not in INTERFACES_QBITTORRENT:
            raise ValueError("Interface de qBittorrent inconnue.")
        if form.qbittorrent_ui and not cfg.enabled("qbittorrent"):
            raise ValueError("VueTorrent demande que qBittorrent soit selectionne.")
        cfg.qbittorrent_ui = form.qbittorrent_ui
        if not 1 <= form.veille_port <= 65535:
            raise ValueError("Port de la veille invalide.")
        cfg.veille_enabled = form.veille_enabled
        cfg.veille_port = form.veille_port
        cfg.veille_socket = form.veille_socket
        if not 1 <= form.console_port <= 65535:
            raise ValueError("Port de la console invalide.")
        if form.console_enabled and form.console_port == form.veille_port:
            raise ValueError("La console et la veille ne peuvent pas partager un port.")
        cfg.console_enabled = form.console_enabled
        cfg.console_port = form.console_port
        cfg.recyclarr_templates = form.recyclarr_templates
        if form.recyclarr_templates:
            if self.demo:
                names = recyclarr.bundled_manifest()
            else:
                names, problem = recyclarr.available_templates(Path(cfg.config_root) / "recyclarr")
                if problem:
                    raise ValueError(
                        "Impossible de verifier les profils de qualite. Reessayez ou gardez les profils par defaut."
                    )
            for service, name in form.recyclarr_templates.items():
                if (
                    not cfg.enabled("recyclarr")
                    or not cfg.enabled(service)
                    or name not in names.get(service, [])
                ):
                    raise ValueError("Profil de qualite invalide pour la selection.")
        self.reprise = None
        self.project_dir = self.launch_project_dir
        if form.reprendre and previous is not None:
            self.reprise = reprise.appliquer(
                cfg,
                previous,
                imposes={
                    "language",
                    "ui_language",
                    "recyclarr_templates",
                    # Toujours impose : le formulaire part du choix precedent,
                    # et « interface d'origine » est un choix, pas un oubli.
                    "qbittorrent_ui",
                    # Meme raison : « pas de veille » est un choix du
                    # formulaire, pas un oubli a completer par l'ancienne.
                    "veille_enabled",
                    "veille_port",
                    "veille_socket",
                    "console_enabled",
                    "console_port",
                    *(("client_prefere",) if form.client_prefere else ()),
                    *(("vpn",) if cfg.vpn.enabled else ()),
                },
            )
            # Les images et ports secondaires choisis lors d'une mise a jour
            # appartiennent aussi a l'installation precedente. `appliquer`
            # couvre les identifiants et le port principal ; on complete ici
            # sans reprendre les services que l'utilisateur a decoches.
            for sid in cfg.services.keys() & previous.services.keys():
                old = previous.services[sid]
                current = cfg.services[sid]
                garder = old.image and not (
                    form.upgrade_images and version_plus_recente(current.image, old.image)
                )
                current.image = old.image if garder else current.image
                current.extra_ports = dict(old.extra_ports)
                current.secret_key = old.secret_key or current.secret_key
            # Les ports repris valaient pour l'ANCIENNE selection.
            # `build_config` avait deja resolu les conflits ; on vient d'ecrire
            # par-dessus. Sans cette seconde passe, ajouter Jellyfin a une pile
            # Silo restaurait le 8096 de Silo et le compose publiait deux fois
            # le meme port, pour toute la pile.
            orchestrator.resolve_port_conflicts(cfg)
            if connection is None and self.previous_project_dir is not None:
                self.project_dir = self.previous_project_dir
        cfg.remote_access = form.remote_access.model_copy(deep=True)
        if any(not cfg.enabled(sid) for sid in cfg.remote_access.services):
            raise ValueError("L’accès distant doit concerner des applications sélectionnées.")
        cfg.project_dir = self.remote_project_dir if connection is not None else self.project_dir
        return cfg

    def startup_checks(self):
        if self.demo:
            checks = [Check("Docker", True, "Demonstration : controle simule.")]
        else:
            try:
                checks = check_docker()
            except Exception as exc:  # noqa: BLE001
                journal.LOGGER.exception("diagnostic docker depuis l'assistant web")
                checks = [Check("Docker", False, str(exc))]
        return {"ok": all(check.ok for check in checks), "checks": [asdict(c) for c in checks]}

    def check_paths(self, payload):
        platform = PlatformProfile(str(payload.get("platform", "")))
        data_root = str(payload.get("data_root", "")).strip()
        if not data_root:
            raise ValueError("La racine des donnees ne peut pas etre vide.")
        warning = path_warning(data_root)
        uid, gid, source, certain = resolve_ids(platform)
        if self.demo:
            return {
                "ok": True,
                "detail": "Demonstration : creation et hardlink simules.",
                "target": data_root,
                "warning": warning,
                "puid": uid,
                "pgid": gid,
                "ids_source": i18n.t(source),
                "ids_certain": certain,
                "demo": True,
            }
        try:
            Path(data_root).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ValueError(f"Impossible de creer le dossier : {exc}") from exc
        ok, detail = hardlink_supported(data_root)
        return {
            "ok": ok,
            "detail": detail,
            "target": str(Path(data_root).resolve()),
            "warning": warning,
            "puid": uid,
            "pgid": gid,
            "ids_source": i18n.t(source),
            "ids_certain": certain,
            "demo": False,
        }

    def create_backup(self, payload):
        if self.status == "running":
            raise ValueError("Une installation est en cours.")
        source_value = str(payload.get("source", "")).strip().strip('"')
        destination_value = str(payload.get("destination", "")).strip().strip('"')
        live = payload.get("live", False)
        if not isinstance(live, bool) or not source_value or not destination_value:
            raise ValueError("Source, destination et mode de sauvegarde invalides.")
        source = Path(source_value)
        destination = Path(destination_value)
        if self.demo:
            return {
                "ok": True,
                "demo": True,
                "archive": str(destination),
                "size_mb": 12.4,
                "files": 128,
                "volumes": ["plugarr_silo-data"],
                "stopped": not live,
                "progress": ["Demonstration : aucune archive n'a ete ecrite."],
            }
        found = reprise.trouver(source)
        if found is None:
            raise ValueError("Aucune installation PlugArr trouvee dans ce dossier.")
        progress = []
        report = sauvegarde.sauvegarder(
            found.cfg,
            found.project_dir,
            destination,
            live=live,
            on_progress=lambda message: progress.append(str(message)[:500]),
        )
        return {
            "ok": True,
            "demo": False,
            "archive": str(report.archive),
            "size_mb": report.mega,
            "files": report.fichiers,
            "volumes": report.volumes,
            "stopped": report.arret,
            "progress": progress[-30:],
        }

    def inspect_restore(self, payload):
        archive_value = str(payload.get("archive", "")).strip().strip('"')
        if not archive_value:
            raise ValueError("Indiquez une archive de sauvegarde.")
        archive = Path(archive_value)
        if self.demo:
            manifest = {
                "date": "2026-09-10T00:00:00+00:00",
                "project_name": "plugarr",
                "services": ["prowlarr", "sonarr", "radarr", "qbittorrent"],
                "volumes": ["plugarr_silo-data"],
                "config_root": "C:/PlugArr/config",
                "a_chaud": False,
            }
            signature = {"archive": str(archive), "size": 0, "mtime_ns": 0}
        else:
            if not archive.is_file():
                raise ValueError(f"{archive} introuvable.")
            manifest = sauvegarde.lire_manifeste(archive)
            stat = archive.stat()
            signature = {
                "archive": str(archive.resolve()),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
        inspection_id = secrets.token_urlsafe(24)
        self.restore_inspections = {inspection_id: signature}
        return {"inspection_id": inspection_id, "manifest": manifest, "demo": self.demo}

    def restore(self, payload):
        if self.status == "running":
            raise ValueError("Une installation est en cours.")
        if payload.get("confirm") is not True:
            raise ValueError("Confirmez la restauration apres avoir examine l'archive.")
        inspection_id = payload.get("inspection_id")
        signature = self.restore_inspections.pop(str(inspection_id), None)
        if signature is None:
            raise ValueError("Examinez de nouveau l'archive avant de restaurer.")
        archive = Path(str(payload.get("archive", "")).strip().strip('"'))
        target = str(payload.get("target", "")).strip() or None
        if target and any(char in target for char in ("\n", "\r", "\x00", '"')):
            raise ValueError("Le dossier de restauration contient un caractere interdit.")
        if target and not self.demo and not Path(target).is_absolute():
            raise ValueError("Le dossier de restauration doit etre absolu.")
        if self.demo:
            return {
                "ok": True,
                "demo": True,
                "services": 4,
                "project_dir": str(self.launch_project_dir),
                "config_root": target or "C:/PlugArr/config",
                "progress": ["Demonstration : aucun fichier n'a ete restaure."],
            }
        stat = archive.stat()
        if (
            str(archive.resolve()) != signature["archive"]
            or stat.st_size != signature["size"]
            or stat.st_mtime_ns != signature["mtime_ns"]
        ):
            raise ValueError("L'archive a change depuis son examen. Examinez-la de nouveau.")
        progress = []
        manifest = sauvegarde.restaurer(
            archive,
            self.launch_project_dir,
            config_root=target,
            on_progress=lambda message: progress.append(str(message)[:500]),
        )
        self.reload_previous()
        return {
            "ok": True,
            "demo": False,
            "services": len(manifest.get("services", [])),
            "project_dir": str(self.launch_project_dir),
            "config_root": target or manifest["config_root"],
            "progress": progress[-30:],
        }

    @staticmethod
    def _vpn_config(payload):
        if not isinstance(payload, dict) or set(payload) - set(VpnConfig.model_fields):
            raise ValueError("Configuration VPN invalide.")
        config = VpnConfig.model_validate(payload)
        if not config.enabled:
            raise ValueError("Activez le VPN avant de lancer l'essai.")
        if config.missing():
            raise ValueError("Configuration VPN incomplete : " + ", ".join(config.missing()))
        if any(
            any(c in value for c in ("\n", "\r", "\x00"))
            for value in config.model_dump().values()
            if isinstance(value, str)
        ):
            raise ValueError("Les champs VPN ne doivent pas contenir de retour a la ligne.")
        if config.provider not in VPN_PROVIDERS or config.provider in VPN_ALIASES:
            raise ValueError("Fournisseur VPN inconnu.")
        if config.vpn_type == "wireguard":
            try:
                if len(base64.b64decode(config.wireguard_private_key, validate=True)) != 32:
                    raise ValueError()
            except ValueError as exc:
                raise ValueError(
                    "La cle WireGuard doit contenir 32 octets encodes en base64."
                ) from exc
        places = (
            vpnservers.pf_choices(config.provider)
            if vpnservers.port_forward(config.provider)
            else vpnservers.choices(config.provider)
        )
        if places and any(
            place.strip() not in places
            for place in config.countries.split(",")
            if place.strip()
        ):
            raise ValueError("Localisation VPN absente de la liste de Gluetun.")
        return config

    def test_vpn(self, payload):
        values = payload.get("vpn")
        if not isinstance(values, dict):
            raise TypeError("Configuration VPN invalide.")
        values = dict(values)
        remote_target = payload.get("install_target") == "ssh"
        previous = (
            (self.remote_connections.get(str(payload.get("remote_connection_id") or "")) or {}).get(
                "previous"
            )
            if remote_target
            else self.previous
        )
        if previous and previous.vpn.enabled:
            old = previous.vpn
            old_provider = VPN_ALIASES.get(old.provider, old.provider)
            if values.get("provider") == old_provider and values.get("vpn_type") == old.vpn_type:
                for key in ("wireguard_private_key", "openvpn_password", "openvpn_user"):
                    if not values.get(key):
                        values[key] = getattr(old, key)
        config = self._vpn_config(values)
        if self.demo:
            check = Check(
                "Essai VPN",
                True,
                "Demonstration : tunnel, adresse publique et port entrant simules.",
                blocking=False,
            )
        elif remote_target:
            connection_id = payload.get("remote_connection_id")
            fingerprint = payload.get("remote_fingerprint")
            if not isinstance(connection_id, str) or not isinstance(fingerprint, str):
                raise ValueError("Connexion SSH invalide. Testez-la a nouveau.")
            connection = self.remote_connections.get(connection_id)
            if connection is None:
                raise ValueError("Connexion SSH absente ou expiree. Testez-la a nouveau.")
            if time.monotonic() - float(connection["created_at"]) > 900:
                self.remote_connections.pop(connection_id, None)
                raise ValueError("Le test SSH a expire. Testez la connexion a nouveau.")
            probe_result = connection["probe"]
            if not isinstance(probe_result, remote_install.RemoteProbe):
                raise ValueError("Diagnostic SSH invalide. Testez la connexion a nouveau.")
            if not hmac.compare_digest(fingerprint, probe_result.fingerprint):
                raise ValueError("Confirmez exactement l'empreinte SSH affichee.")
            original_target = connection["target"]
            target = remote_install.RemoteTarget(
                host=original_target.host,
                port=original_target.port,
                username=original_target.username,
                expected_fingerprint=probe_result.fingerprint,
            )
            result = remote_install.test_vpn(
                target,
                connection["credentials"],
                config.model_dump(mode="json"),
                uid=probe_result.uid,
                gid=probe_result.gid,
                admin_image=catalog.CONSOLE_IMAGE,
                gluetun_image=f"qmcgaw/gluetun:{GLUETUN_TAG}",
                connect=remote_install.connect_paramiko,
            )
            check = Check(
                str(result.get("name", "Essai VPN")),
                bool(result.get("ok")),
                str(result.get("detail", "Essai VPN distant termine.")),
                blocking=False,
            )
        else:
            try:
                check = vpnessai.essayer(config, f"qmcgaw/gluetun:{GLUETUN_TAG}")
            except Exception as exc:  # noqa: BLE001
                journal.LOGGER.exception("essai VPN depuis l'assistant web")
                check = Check("Essai VPN", False, str(exc), blocking=False)
        return asdict(check)

    def _require_completed(self):
        if self.status not in ("done", "partial") or self.cfg is None:
            raise ValueError("Cette fonction est disponible apres la fin de l'installation.")

    def _ensure_indexers(self):
        self._require_completed()
        if not self.cfg.enabled("prowlarr"):
            raise ValueError("Prowlarr n'est pas installe dans cette selection.")
        if self.indexers is None:
            spec = catalog.get("prowlarr")
            inst = self.cfg.services["prowlarr"]
            self.indexer_client = ArrClient(
                inst.url(self.cfg.host),
                inst.api_key or "",
                api_version=spec.api_version,
                name="prowlarr",
            )
            self.indexers = ProwlarrIndexers(self.indexer_client)
        return self.indexers

    @staticmethod
    def _demo_indexer_definitions():
        return [
            IndexerDefinition(
                "Exemple public",
                "Cardigann",
                "public",
                "torrent",
                "fr-FR",
                "Definition fictive pour parcourir l'assistant sans contacter Prowlarr.",
                {"fields": [], "indexerUrls": ["https://example.invalid/"]},
            ),
            IndexerDefinition(
                "Exemple prive",
                "Cardigann",
                "private",
                "torrent",
                "fr-FR",
                "Definition fictive avec identifiants.",
                {
                    "indexerUrls": ["https://tracker.example.invalid/"],
                    "fields": [
                        {"name": "baseUrl", "label": "Adresse", "value": ""},
                        {"name": "username", "label": "Identifiant", "value": ""},
                        {
                            "name": "password",
                            "label": "Mot de passe",
                            "value": "",
                            "type": "password",
                        },
                    ],
                },
            ),
        ]

    def indexer_overview(self):
        self._require_completed()
        # Installation distante reelle du 25/09/2026 : ce panneau interrogeait
        # Prowlarr depuis CE poste, a l'adresse privee du VPS, et expirait.
        # Les indexeurs s'ajoutent alors depuis la console du serveur.
        if not self.cfg.enabled("prowlarr") or self.install_target == "ssh":
            return {"available": False, "count": 0, "configured": [], "demo": self.demo}
        if self.demo:
            definitions = self._demo_indexer_definitions()
            configured = []
        else:
            indexers = self._ensure_indexers()
            definitions = indexers.definitions()
            configured = [str(i.get("name", "?")) for i in indexers.configured()]
        return {
            "available": True,
            "count": len(definitions),
            "configured": configured,
            "demo": self.demo,
        }

    def search_indexers(self, payload):
        self._require_completed()
        query = str(payload.get("query", "")).strip()
        if len(query) < 2 or len(query) > 100:
            raise ValueError("Saisissez au moins deux caracteres.")
        if self.demo:
            definitions = [
                definition
                for definition in self._demo_indexer_definitions()
                if query.casefold() in definition.name.casefold()
            ][:MAX_INDEXER_RESULTS]
        else:
            definitions = self._ensure_indexers().search(query, MAX_INDEXER_RESULTS)
        self.indexer_matches = {}
        results = []
        for definition in definitions:
            key = secrets.token_urlsafe(12)
            self.indexer_matches[key] = definition
            results.append(
                {
                    "key": key,
                    "name": definition.name,
                    "privacy": definition.privacy,
                    "private": definition.is_private,
                    "protocol": definition.protocol,
                    "description": definition.description[:300],
                    "mirrors": definition.urls[:4],
                    "fields": [
                        {
                            "name": field.name,
                            "label": field.label,
                            "secret": field.secret,
                            "prefill": field.prefill,
                        }
                        for field in definition.editable_fields()
                    ],
                }
            )
        return {"results": results}

    def add_indexer(self, payload):
        self._require_completed()
        definition = self.indexer_matches.get(str(payload.get("key", "")))
        values = payload.get("values")
        if definition is None or not isinstance(values, dict):
            raise ValueError("Selection d'indexeur invalide ou expiree.")
        allowed = {field.name for field in definition.editable_fields()}
        if (
            set(values) - allowed
            or len(values) > 30
            or not all(
                isinstance(key, str) and isinstance(value, str) and len(value) <= 4096
                for key, value in values.items()
            )
        ):
            raise ValueError("Champs d'indexeur invalides.")
        if self.demo:
            ok, message, configured = True, "Ajout simule : aucun indexeur contacte.", [definition.name]
        else:
            indexers = self._ensure_indexers()
            ok, message = indexers.add(definition, values)
            configured = [str(i.get("name", "?")) for i in indexers.configured()]
        return {"ok": ok, "message": self.redact(message), "configured": configured}

    def prepare_indexer_backup(self):
        """Refuse AVANT de recevoir le fichier, pas apres l'avoir lu."""
        self._require_completed()
        if not self.cfg.enabled("prowlarr"):
            raise ValueError("Prowlarr n'est pas installe dans cette selection.")

    def inspect_indexer_backup(self, path: Path):
        self.prepare_indexer_backup()
        sauvegarde = import_prowlarr.lire(path)
        if self.demo:
            statuts = [(entree, import_prowlarr.IMPORTABLE) for entree in sauvegarde.indexeurs]
        else:
            statuts = import_prowlarr.examiner(sauvegarde, self._ensure_indexers())
        self.backup_indexers = {}
        rows = []
        for entree, statut in statuts:
            key = None
            if statut == import_prowlarr.IMPORTABLE:
                key = secrets.token_urlsafe(12)
                self.backup_indexers[key] = entree
            rows.append(
                {
                    "key": key,
                    "name": entree.name,
                    "definition": entree.definition_file or entree.implementation,
                    "enabled": entree.enable,
                    "status": statut,
                }
            )
        return {"source": sauvegarde.source, "indexers": rows, "ignored": sauvegarde.ignores}

    def import_indexer_backup(self, payload):
        self.prepare_indexer_backup()
        key = str(payload.get("key", ""))
        entree = self.backup_indexers.get(key)
        if entree is None:
            raise ValueError("Indexeur de sauvegarde invalide, expire ou deja importe.")
        if self.demo:
            ok, message, warnings = True, "Import simule : aucun indexeur contacte.", []
            configured = [entree.name]
        else:
            indexers = self._ensure_indexers()
            ok, message, warnings = import_prowlarr.importer(entree, indexers)
            configured = [str(i.get("name", "?")) for i in indexers.configured()]
        if ok:
            self.backup_indexers.pop(key, None)
        return {
            "ok": ok,
            "name": entree.name,
            "message": self.redact(message),
            "warnings": [self.redact(w) for w in warnings],
            "configured": configured,
        }

    def share_to_phone(self, contenu: bytes, nom: str) -> dict:
        """Publie un fichier du telephone derriere un lien a usage unique.

        Seulement une fois l'installation terminee : c'est la page d'acces qui
        produit ces fichiers. En demonstration, aucun serveur n'est ouvert.
        """
        self._require_completed()
        if self.demo:
            return {"url": "http://192.0.2.50:49152/t/demonstration", "expires_in": 600, "demo": True}
        with self.lock:
            hote = dashboard.resolve_host(self.cfg)[0]
            if self.phone_share is None or self.phone_share.hote != hote:
                if self.phone_share is not None:
                    self.phone_share.arreter()
                self.phone_share = PartageTelephone(hote)
            return self.phone_share.publier(contenu, nom)

    def available_updates(self):
        """Versions plus recentes que celles installees, pour le rapport de fin.

        Demande du 26/09/2026 : PlugArr installe les versions qu'il a testees,
        et dit ensuite ce qui existe de plus recent. Rien n'est change ici.
        Route separee du rapport : une vingtaine de registres a interroger ne
        doit pas retarder l'affichage des acces.
        """
        self._require_completed()
        if self.demo:
            return {"demo": True, "updates": [], "unchecked": []}
        cibles = [
            (sid, catalog.get(sid).display_name, inst.image or catalog.get(sid).image)
            for sid, inst in orchestrator.iter_selected(self.cfg)
            if (inst.image or catalog.get(sid).image) and not inst.adopted
        ]

        def verifier(cible):
            sid, nom, image = cible
            try:
                recentes, probleme = updates.newer_tags(image, timeout=10.0)
            except Exception as exc:  # noqa: BLE001 - un registre ne doit pas casser le rapport
                recentes, probleme = [], str(exc)
            return sid, nom, image, recentes, probleme

        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=8) as pool:
            resultats = list(pool.map(verifier, cibles))
        return {
            "demo": False,
            "updates": [
                {
                    "id": sid,
                    "name": nom,
                    "current": imageref.parse(image).tag,
                    "latest": recentes[-1],
                }
                for sid, nom, image, recentes, probleme in resultats
                if recentes and not probleme
            ],
            "unchecked": [nom for _sid, nom, _image, _recentes, probleme in resultats if probleme],
        }

    def report(self):
        self._require_completed()
        failed = [result for result in self.results if not result.ok]
        next_steps = (
            [
                f"Liens en echec : {result.name} : "
                f"{next(iter(result.detail.splitlines()), 'aucun detail')}"
                for result in failed
            ]
            if failed
            else orchestrator.prochaine_etape(self.cfg)
        )
        return {
            "services": [
                {
                    "id": sid,
                    "name": catalog.get(sid).display_name,
                    "url": inst.url(self.cfg.host) if inst.has_web_ui else "",
                    "remote_url": (self.remote_result or {}).get("urls", {}).get(sid, ""),
                    "local_url": inst.url("192.0.2.50" if self.demo else dashboard.resolve_host(self.cfg)[0]) if inst.has_web_ui else "",
                    "username": inst.username or "-",
                    "password": inst.password or "-",
                    "api_key": inst.api_key or "-",
                }
                for sid, inst in orchestrator.iter_selected(self.cfg)
            ],
            "next_steps": next_steps,
            "env_path": (
                posixpath.join(self.remote_project_dir, ".env")
                if self.install_target == "ssh"
                else str(self.project_dir / ".env")
            ),
            "remote_install": self.install_target == "ssh",
            "console_url": (
                f"http://{self.cfg.host}:{self.cfg.console_port}/"
                if self.cfg.console_enabled and self.install_target == "ssh"
                else ""
            ),
            "console_password": self.console_password if self.install_target == "ssh" else "",
            "console_password_kept": bool(
                self.install_target == "ssh"
                and self.cfg.console_enabled
                and not self.console_password
            ),
            "access_help": self.acces_depuis_ce_poste(),
            "can_indexers": self.cfg.enabled("prowlarr") and self.install_target != "ssh",
            "demo": self.demo,
            "remote": self.remote_result or remote_access.summary(self.cfg, demo=self.demo),
            "remote_managed": bool(self.remote_result)
            if self.install_target == "ssh"
            else False
            if self.demo
            else (self.project_dir / ".plugarr-remote" / "compose.yml").is_file(),
        }

    def remote_action(self, payload):
        self._require_completed()
        if payload.get("action") not in ("activate", "inspect", "deactivate"):
            raise ValueError("Action distante inconnue.")
        if self.install_target == "ssh":
            return self._remote_gateway_action(payload)
        with self.lock:
            if self.remote_worker and self.remote_worker.is_alive():
                raise ValueError("Une opération d’accès distant est déjà en cours.")
            if payload["action"] in ("activate", "deactivate") and payload.get("confirm") is not True:
                raise ValueError("Confirmez l’activation de l’accès distant.")
            self.remote_result = {**remote_access.summary(self.cfg, demo=self.demo), "status": "running", "message": "Configuration de l’accès distant en cours…"}
            def work():
                try:
                    operation = {"activate": remote_access.activate, "inspect": remote_access.inspect, "deactivate": remote_access.deactivate}[payload["action"]]
                    result = operation(self.cfg, self.project_dir, demo=self.demo)
                    if not self.demo:
                        path = self.project_dir / dashboard.FILENAME
                        path.write_text(dashboard.render(self.cfg, remote_report=result), encoding="utf-8")
                        path.chmod(0o600)
                except Exception as exc:  # noqa: BLE001
                    # Exception details can contain a sensitive authorization URL.
                    message = str(exc) if isinstance(exc, ValueError) else "Vérification distante impossible. Vérifiez Docker, le réseau et les identifiants des applications."
                    result = {**remote_access.summary(self.cfg, demo=self.demo), "status": "error", "message": self.redact(message)}
                with self.lock:
                    self.remote_result = result
            self.remote_worker = threading.Thread(target=work, daemon=False)
            self.remote_worker.start()
        return {"status": "running"}

    def _remote_gateway_action(self, payload):
        with self.lock:
            if self.remote_worker and self.remote_worker.is_alive():
                raise ValueError("Une opération d’accès distant est déjà en cours.")
            if payload["action"] in ("activate", "deactivate") and payload.get("confirm") is not True:
                raise ValueError("Confirmez l’activation de l’accès distant.")
            connection = self.remote_connections.get(self.remote_connection_id)
            if connection is None:
                raise ValueError("La session SSH a expiré. Relancez l’assistant.")
            self.remote_result = {
                **remote_access.summary(self.cfg),
                "status": "running",
                "message": "Opération distante en cours sur le serveur…",
            }

            def work():
                try:
                    original_target = connection["target"]
                    target = remote_install.RemoteTarget(
                        host=original_target.host,
                        port=original_target.port,
                        username=original_target.username,
                        expected_fingerprint=connection["probe"].fingerprint,
                    )
                    deployment = remote_install.RemoteDeployment(
                        project_dir=self.remote_project_dir,
                        config_root=self.cfg.config_root,
                        data_root=self.cfg.data_root,
                        uid=self.cfg.puid,
                        gid=self.cfg.pgid,
                        stack_yaml=compose.render_stack(self.cfg),
                        image=catalog.CONSOLE_IMAGE,
                        veille_image=catalog.VEILLE_IMAGE,
                    )

                    def receive(event):
                        if event.get("kind") == "remote_access" and isinstance(
                            event.get("result"), dict
                        ):
                            self.remote_result = event["result"]

                    remote_install.deploy(
                        target,
                        connection["credentials"],
                        deployment,
                        connect=remote_install.connect_paramiko,
                        on_event=receive,
                        operation=payload["action"],
                    )
                except Exception as exc:  # noqa: BLE001
                    self.remote_result = {
                        **remote_access.summary(self.cfg),
                        "status": "error",
                        "message": self.redact(exc),
                    }

            self.remote_worker = threading.Thread(target=work, daemon=False)
            self.remote_worker.start()
        return {"status": "running"}

    def acces_depuis_ce_poste(self) -> dict | None:
        """Comment joindre les applications depuis ce poste, quand elles n'y sont pas.

        Validation reelle du 26/09/2026 : sur un VPS ou seul SSH est ouvert, les
        liens pointaient vers l'adresse privee du serveur (10.0.0.30), que le
        poste ne peut pas joindre, et rien ne disait comment faire. Un proxy
        SOCKS par SSH les rend joignables tels quels, sans rien ouvrir.
        """
        if self.install_target != "ssh" or self.cfg is None or not getattr(self, "remote_ssh", None):
            return None
        try:
            adresse = ipaddress.ip_address(self.cfg.host)
        except ValueError:
            return None
        utilisateur, hote, port = self.remote_ssh
        if not adresse.is_private or hote == self.cfg.host:
            return None
        commande = f"ssh -N -D 1080 {utilisateur}@{hote}" + (f" -p {port}" if port != 22 else "")
        return {"host": self.cfg.host, "ssh": commande, "proxy": "socks5://127.0.0.1:1080"}

    def access_page(self):
        self._require_completed()
        cfg = self.cfg.model_copy(deep=True)
        if self.demo and cfg.host == "localhost":
            cfg.host = "192.0.2.10"
        return dashboard.render(
            cfg,
            live=False,
            remote_report=self.remote_result,
            demo=self.demo,
            console_password=self.console_password if self.install_target == "ssh" else "",
            aide_acces=self.acces_depuis_ce_poste(),
        ).encode("utf-8")

    def close_resources(self):
        self.backup_indexers = {}
        self.remote_connections = {}
        if self.phone_share is not None:
            self.phone_share.arreter()
            self.phone_share = None
        if self.indexer_client is not None:
            self.indexer_client.close()
            self.indexer_client = None
            self.indexers = None

    def probe_remote_install(self, payload):
        """Sonde une cible SSH et conserve ses secrets seulement en memoire."""
        form = RemoteSSHInput.model_validate(payload)
        credentials = remote_install.RemoteCredentials(
            password=form.password,
            private_key=form.private_key,
            passphrase=form.passphrase,
            sudo_password=form.sudo_password,
        )
        target = remote_install.RemoteTarget(
            host=form.host.strip(),
            port=form.port,
            username=form.username.strip(),
        )
        result = remote_install.probe(
            target,
            credentials,
            connect=remote_install.connect_paramiko,
        )
        connection_id = secrets.token_urlsafe(24)
        project_dir = posixpath.join(result.home, "plugarr")
        previous = (
            self._remote_previous(target, credentials, result, project_dir)
            if result.ready
            else None
        )
        self.remote_connections = {
            connection_id: {
                "target": target,
                "credentials": credentials,
                "probe": result,
                "previous": previous,
                "created_at": time.monotonic(),
            }
        }
        return {
            "existing": previous is not None,
            "existing_form": self._remote_form(previous) if previous is not None else None,
            "version_changes": changements_de_version(previous) if previous is not None else [],
            "fresh_form": self._default_form() if previous is not None else None,
            "connection_id": connection_id,
            "fingerprint": result.fingerprint,
            "system": result.system,
            "machine": result.machine,
            "uid": result.uid,
            "gid": result.gid,
            "docker_version": result.docker_version,
            "ready": result.ready,
            "suggested_host": result.suggested_host(target.host),
            "project_dir": project_dir,
            "config_root": posixpath.join(project_dir, "config"),
            "data_root": posixpath.join(result.home, "data"),
        }

    def graph_preview(self, payload):
        selected = payload.get("services", [])
        if (
            not isinstance(selected, list)
            or len(selected) > 40
            or not all(isinstance(s, str) and s in catalog.CATALOG for s in selected)
        ):
            raise ValueError("Selection de services invalide.")
        language = payload.get("language", "fr")
        if not isinstance(language, str) or len(language) > 10:
            raise ValueError("Langue invalide.")
        vpn = payload.get("vpn_enabled", False)
        if not isinstance(vpn, bool):
            raise TypeError("Choix VPN invalide.")
        protect_sabnzbd = payload.get("protect_sabnzbd", False)
        if not isinstance(protect_sabnzbd, bool):
            raise TypeError("Choix de trajet SABnzbd invalide.")
        cfg = orchestrator.build_config(services=selected, language=language)
        cfg.vpn.protect_sabnzbd = protect_sabnzbd and cfg.enabled("sabnzbd")
        cfg.vpn.enabled = vpn and any(
            cfg.enabled(s) and (s in catalog.TORRENT_CLIENTS or cfg.vpn.protect_sabnzbd)
            for s in catalog.DOWNLOAD_CLIENTS
        )
        return {
            "graph": wizard_graph.build(cfg),
            "graph_results": {},
            "deployed": False,
            "active_step": None,
            "status": "idle",
            "demo": self.demo,
        }

    def validate(self, payload):
        with self.lock:
            if self.status in ("running", "done", "partial"):
                raise ValueError(
                    "Une installation est deja lancee. Ouvrez la console ou relancez l'assistant."
                )
            self.plan_id = None
            form = WizardInput.model_validate(payload)
            cfg = self.build_config(form)
            self.console_password = ""
            # Validation reelle du 26/09/2026 : en reprise, l'ancien mot de passe
            # etait garde en silence ; perdu avec le rapport qui l'avait montre,
            # la console restait fermee. Il se remplace desormais sur demande.
            if (
                self.install_target == "ssh"
                and cfg.console_enabled
                and (not cfg.admin_password_hash or form.new_console_password)
            ):
                self.console_password = secrets.token_urlsafe(24)
                cfg.admin_password_hash = adminauth.hash_password(self.console_password)
            remote_connection = (
                self.remote_connections.get(self.remote_connection_id)
                if self.install_target == "ssh"
                else None
            )
            if self.install_target == "local" and not self.demo and self.stack_hash() != self.initial_hash:
                raise ValueError(
                    "stack.yml a change. Relancez l'assistant pour reprendre la configuration actuelle."
                )
            if remote_connection is not None:
                remote_probe = remote_connection["probe"]
                original_target = remote_connection["target"]
                remote_target = remote_install.RemoteTarget(
                    host=original_target.host,
                    port=original_target.port,
                    username=original_target.username,
                    expected_fingerprint=remote_probe.fingerprint,
                )
                remote_project = remote_install.inspect_project(
                    remote_target,
                    remote_connection["credentials"],
                    self.remote_project_dir,
                    connect=remote_install.connect_paramiko,
                )
                expected_remote_sha = hashlib.sha256(
                    compose.render_stack(cfg).encode("utf-8")
                ).hexdigest()
                remote_replace_required = bool(
                    remote_project.exists
                    and not hmac.compare_digest(remote_project.stack_sha, expected_remote_sha)
                )
                remote_replace_ok = bool(
                    remote_replace_required and remote_project.managed and form.remote_replace
                )
                remote_reset_ok = bool(
                    remote_project.exists
                    and remote_project.managed
                    and remote_project.stack_sha
                    and remote_project.services
                    and remote_project.project_name == cfg.project_name
                    and remote_project.config_root == cfg.config_root
                    and remote_project.data_root == cfg.data_root
                    and set(remote_project.services) <= set(catalog.STARTUP_ORDER)
                )
                self.remote_existing_sha = remote_project.stack_sha
                self.remote_replace_confirmed = remote_replace_ok
                checks = [
                    asdict(Check("SSH", True, "Connexion et empreinte confirmees.")),
                    asdict(
                        Check(
                            "Linux",
                            remote_probe.system == "Linux",
                            f"{remote_probe.system} {remote_probe.machine}".strip(),
                        )
                    ),
                    asdict(
                        Check(
                            "Docker distant",
                            bool(remote_probe.docker_version),
                            remote_probe.docker_version or "Docker indisponible",
                        )
                    ),
                    asdict(
                        Check(
                            "Pile PlugArr distante",
                            not remote_replace_required or remote_replace_ok,
                            (
                                "Aucune pile existante a remplacer."
                                if not remote_replace_required
                                else "Mise a jour explicitement confirmee; configurations et medias conserves."
                                if remote_replace_ok
                                else "Pile PlugArr existante detectee. Confirmez sa mise a jour."
                                if remote_project.managed
                                else "Le dossier contient une pile qui n'est pas reconnue comme geree par PlugArr."
                            ),
                        )
                    ),
                ]
                if form.reset_config:
                    checks.append(
                        asdict(
                            Check(
                                "Remise a zero distante",
                                remote_reset_ok,
                                "Ancienne pile reconnue, chemins inchanges et medias exclus."
                                if remote_reset_ok
                                else "Pile distante non reconnue ou chemins modifies : suppression refusee.",
                            )
                        )
                    )
            else:
                remote_project = None
                remote_replace_required = False
                remote_reset_ok = False
                self.remote_existing_sha = ""
                self.remote_replace_confirmed = False
                checks = (
                    []
                    if self.demo
                    else [asdict(c) for c in orchestrator.preflight(cfg, self.project_dir)]
                )
            blocked = any(not c["ok"] and c["blocking"] for c in checks)
            self.cfg = cfg
            resumed = set(getattr(self.reprise, "services", ()) or ())
            self.reset_cfg = cfg
            self.reset_project_dir = self.project_dir
            self.reset_existing_stack = False
            if self.install_target == "local" and self.previous is not None and not form.reprendre:
                # « Repartir de zero » doit proposer TOUT l'etat de l'ancienne
                # installation, y compris les applications decochees et les
                # volumes Docker. Le choix reste desactive par defaut et les
                # medias ne font jamais partie des candidats.
                self.reset_cfg = self.previous
                self.reset_project_dir = self.previous_project_dir or self.launch_project_dir
                self.reset_existing_stack = self.previous_project_dir is not None
                self.reset_candidates = orchestrator.existing_configs(self.previous)
            elif self.install_target == "local":
                self.reset_candidates = [
                    service
                    for service in orchestrator.unusable_configs(cfg)
                    if service not in resumed
                ]
            else:
                self.reset_candidates = (
                    list(remote_project.services) if remote_reset_ok and remote_project else []
                )
            self.reset_requested = bool(form.reset_config and self.reset_candidates)
            self.graph = wizard_graph.build(cfg)
            self.plan_id = secrets.token_urlsafe(24) if not blocked else None
            self.validated_at = time.monotonic()
            warnings = []
            if any(cfg.enabled(s) for s in catalog.TORRENT_CLIENTS) and not cfg.vpn.enabled:
                warnings.append(
                    "Aucun VPN : les telechargements utiliseront l'adresse IP publique de cette machine."
                )
            if form.reprendre and (self.previous or self.install_target == "ssh"):
                warnings.append(
                    "Reinstallation : les conteneurs existants seront arretes puis relances. Identifiants et versions sont conserves."
                )
            if self.remote_replace_confirmed:
                warnings.append(
                    "La pile PlugArr distante sera mise a jour. Ses configurations et ses medias seront conserves."
                )
            if self.install_target == "ssh" and self.reset_requested:
                warnings.append(
                    "Les configurations et volumes des applications de l'ancienne pile "
                    "seront supprimes sur le serveur. Les medias resteront intacts."
                )
            warnings.extend(
                i18n.t(catalog.get(s).experimental)
                for s in cfg.services
                if catalog.get(s).experimental
            )
            return {
                "plan_id": self.plan_id,
                "blocked": blocked,
                "checks": checks,
                "demo": self.demo,
                "warnings": warnings,
                "services": [
                    {
                        "id": s,
                        "name": catalog.get(s).display_name,
                        "port": inst.host_port,
                        "image": inst.image,
                        "url": inst.url(cfg.host) if inst.has_web_ui else "",
                    }
                    for s, inst in cfg.services.items()
                ],
                "config_root": cfg.config_root,
                "data_root": cfg.data_root,
                "project_name": cfg.project_name,
                "project_dir": self.remote_project_dir
                if self.install_target == "ssh"
                else str(self.project_dir),
                "install_target": self.install_target,
                "remote_replace_required": remote_replace_required,
                "remote_replace_managed": bool(remote_project and remote_project.managed),
                "remote_replace_confirmed": self.remote_replace_confirmed,
                "host": cfg.host,
                "remote_access": cfg.remote_access.model_dump(),
                "puid": cfg.puid,
                "pgid": cfg.pgid,
                "ids_source": i18n.t(cfg.ids_source),
                "ids_certain": cfg.ids_certain,
                "umask": cfg.umask,
                "timezone": cfg.timezone,
                "planned_links": orchestrator.planned_links(cfg),
                "vpn": cfg.vpn.enabled,
                "sabnzbd_route": (
                    "vpn" if cfg.vpn.protects("sabnzbd") else "direct"
                ) if cfg.enabled("sabnzbd") else None,
                "recyclarr_templates": cfg.recyclarr_templates,
                "qbittorrent_ui": cfg.qbittorrent_ui,
                "veille_enabled": cfg.veille_enabled,
                "veille_port": cfg.veille_port,
                "veille_socket": cfg.veille_socket,
                "console_enabled": cfg.console_enabled,
                "console_port": cfg.console_port,
                "client_prefere": next(
                    (
                        sid
                        for sid in downloadclients.concurrents(cfg.services)
                        if downloadclients.priorites(cfg)[sid] == 1
                    ),
                    "",
                ),
                "resume": {
                    "enabled": bool(self.reprise),
                    "settings": list(getattr(self.reprise, "reglages", [])),
                    "services": list(getattr(self.reprise, "services", [])),
                    "from": str(self.previous_project_dir) if self.previous_project_dir else "",
                },
                "reset_candidates": list(self.reset_candidates),
                "reset_locations": [
                    orchestrator.emplacement_etat(self.reset_cfg, service)
                    for service in self.reset_candidates
                ] if self.install_target == "local" else [],
                "reset_requested": self.reset_requested,
                "graph": self.graph,
            }

    def redact(self, message):
        message = str(message)
        remote_values = [self.console_password]
        for connection in self.remote_connections.values():
            credentials = connection.get("credentials")
            if isinstance(credentials, remote_install.RemoteCredentials):
                remote_values.extend(
                    (
                        credentials.password,
                        credentials.private_key,
                        credentials.passphrase,
                        credentials.sudo_password,
                    )
                )
        for value in sorted(filter(None, remote_values), key=len, reverse=True):
            message = message.replace(value, "<masque>")
        if self.cfg:
            values = []
            for inst in self.cfg.services.values():
                values.extend(getattr(inst, k, "") for k in ("password", "api_key", "secret_key"))
            values.extend(
                getattr(self.cfg.vpn, k)
                for k in ("wireguard_private_key", "openvpn_password", "openvpn_user")
            )
            for value in sorted(filter(None, values), key=len, reverse=True):
                message = message.replace(value, "<masque>")
        return re.sub(r"(?i)((?:api_?key|token|password|passkey)=)[^&\s]+", r"\1<masque>", message)[
            :4000
        ]

    def event(self, phase, message, ok=True, *, step_id=None, warnings=None, started=False):
        with self.changed:
            event = {
                "phase": str(phase),
                "message": self.redact(message),
                "ok": ok,
                "step_id": step_id,
                "started": started,
                "warnings": [self.redact(w) for w in (warnings or [])],
            }
            self.events.append(event)
            self.events = self.events[-1000:]
            if step_id:
                if started:
                    self.active_step = step_id
                else:
                    self.graph_results[step_id] = event
                    self.active_step = None
            if phase == "demarrage-termine" and ok:
                self.deployed = True
            self.revision += 1
            self.changed.notify_all()

    def set_status(self, status):
        with self.changed:
            self.status = status
            if status != "running":
                self.active_step = None
            self.revision += 1
            self.changed.notify_all()

    def start(self, payload):
        with self.lock:
            if (
                payload.get("confirm") is not True
                or not self.plan_id
                or payload.get("plan_id") != self.plan_id
            ):
                raise ValueError("Validez le recapitulatif avant de lancer l'installation.")
            if self.status == "running":
                raise ValueError("Une installation est deja en cours.")
            if time.monotonic() - self.validated_at > 300:
                self.plan_id = None
                raise ValueError("Les controles ont expire. Verifiez a nouveau la configuration.")
            if (
                self.install_target == "local"
                and not self.demo
                and self.stack_hash() != self.initial_hash
            ):
                self.plan_id = None
                raise ValueError("stack.yml a change depuis la verification. Relancez l'assistant.")
            if self.install_target == "ssh":
                connection = self.remote_connections.get(self.remote_connection_id)
                if connection is None or time.monotonic() - float(connection["created_at"]) > 900:
                    self.plan_id = None
                    raise ValueError("Le test SSH a expire. Testez la connexion a nouveau.")
            self.plan_id = None
            self.status = "running"
            self.graph_results = {}
            self.active_step = None
            self.deployed = False
            self.events = []
            self.revision += 1
            self.changed.notify_all()
            self.worker = threading.Thread(target=self.install, daemon=False)
            self.worker.start()
            return {"status": self.status}

    def install(self):
        try:
            if self.demo:
                self.results = []
                for phase in (
                    "Verification simulee",
                    "Dossiers simules",
                    "Demarrage simule",
                    "Cablage simule",
                ):
                    self.event(phase, "Demonstration : aucune operation reelle.")
                    time.sleep(0.35)
                self.event("demarrage-termine", "Demonstration : conteneurs simules.")
                for step_id in self.graph["etapes"]:
                    self.event(
                        step_id,
                        "Demonstration : etape simulee en cours.",
                        step_id=step_id,
                        started=True,
                    )
                    time.sleep(0.18)
                    self.event(
                        step_id,
                        "Demonstration : resultat simule, aucun test reel.",
                        step_id=step_id,
                    )
                self.set_status("done")
                return
            if self.install_target == "ssh":
                connection = self.remote_connections.get(self.remote_connection_id)
                if connection is None:
                    raise ValueError("Connexion SSH expiree. Relancez l'assistant.")
                original_target = connection["target"]
                target = remote_install.RemoteTarget(
                    host=original_target.host,
                    port=original_target.port,
                    username=original_target.username,
                    expected_fingerprint=connection["probe"].fingerprint,
                )
                deployment = remote_install.RemoteDeployment(
                    project_dir=self.remote_project_dir,
                    config_root=self.cfg.config_root,
                    data_root=self.cfg.data_root,
                    uid=self.cfg.puid,
                    gid=self.cfg.pgid,
                    stack_yaml=compose.render_stack(self.cfg),
                    image=catalog.CONSOLE_IMAGE,
                    veille_image=catalog.VEILLE_IMAGE,
                    replace_existing=self.remote_replace_confirmed,
                    reset_existing=self.reset_requested,
                    expected_existing_sha=self.remote_existing_sha,
                )

                def remote_event(event):
                    kind = event.get("kind")
                    if kind == "progress":
                        self.event(
                            event.get("phase", "Installation distante"),
                            event.get("message", ""),
                            event.get("ok", True),
                            started=event.get("started", False),
                        )
                    elif kind == "check":
                        self.event(
                            event.get("name", "Verification distante"),
                            event.get("detail", ""),
                            event.get("ok", False),
                        )
                    elif kind == "step":
                        self.results.append(
                            StepResult(
                                name=str(event.get("name", "Cablage distant")),
                                ok=bool(event.get("ok")),
                                detail=str(event.get("detail", "")),
                                created=bool(event.get("created")),
                                warnings=list(event.get("warnings") or []),
                                step_id=str(event.get("step_id") or ""),
                            )
                        )
                        self.event(
                            event.get("name", "Cablage distant"),
                            event.get("detail", ""),
                            event.get("ok", False),
                            step_id=event.get("step_id") or None,
                            warnings=event.get("warnings", []),
                        )
                    elif kind == "log" and event.get("message"):
                        self.event("SSH", event["message"])
                    elif kind == "remote_access" and isinstance(event.get("result"), dict):
                        self.remote_result = event["result"]
                        self.event(
                            "Acces distant",
                            self.remote_result.get("message", "Configuration terminee."),
                            self.remote_result.get("status") not in ("error", "failed"),
                        )
                    elif kind == "credentials" and isinstance(event.get("services"), dict):
                        # Evenement prive sur le canal SSH : ne jamais le
                        # copier dans le journal de progression du navigateur.
                        for service_id, values in event["services"].items():
                            instance = self.cfg.services.get(service_id)
                            if instance is None or not isinstance(values, dict):
                                continue
                            for field_name in ("username", "password", "api_key"):
                                value = values.get(field_name)
                                if isinstance(value, str):
                                    setattr(instance, field_name, value)

                result = remote_install.deploy(
                    target,
                    connection["credentials"],
                    deployment,
                    connect=remote_install.connect_paramiko,
                    on_event=remote_event,
                )
                self.deployed = result.status in ("done", "partial")
                self.set_status(result.status)
                return
            journal.start(self.project_dir, "web")
            journal.config(self.cfg)

            if self.reset_requested:
                self.event(
                    "Remise a zero",
                    "Retrait de l'ancienne pile et nettoyage des configurations en cours.",
                    started=True,
                )
                if self.reset_existing_stack:
                    removed = orchestrator.reset_installation_configs(
                        self.reset_cfg, self.reset_project_dir, self.reset_candidates
                    )
                else:
                    removed = orchestrator.reset_configs(
                        self.reset_cfg, self.reset_candidates
                    )
                self.event(
                    "Remise a zero",
                    f"{len(removed)} emplacement(s) de configuration reinitialise(s).",
                )

            def progress(p):
                journal.progress(p.phase, p.message, p.ok)
                self.event(p.phase, p.message, p.ok, started=p.started)

            def step(s):
                journal.step(s)
                self.event(s.name, s.detail, s.ok, step_id=s.step_id or None, warnings=s.warnings)

            self.results = orchestrator.install(
                self.cfg,
                self.project_dir,
                on_progress=progress,
                on_step=step,
                on_step_start=lambda sid: self.event(
                    sid, "Etape en cours", step_id=sid, started=True
                ),
            )
            self.set_status("done" if all(s.ok for s in self.results) else "partial")
            journal.finish(self.status)
        except Exception as exc:  # noqa: BLE001
            self.event("Erreur", self.redact(exc), False)
            self.set_status("error")

    def progress(self):
        with self.lock:
            return {
                "status": self.status,
                "events": list(self.events),
                "demo": self.demo,
                "graph": self.graph,
                "graph_results": dict(self.graph_results),
                "active_step": self.active_step,
                "deployed": self.deployed,
                "revision": self.revision,
            }

    def open_admin(self):
        with self.lock:
            if self.status not in ("done", "partial"):
                raise ValueError("La console est disponible apres la fin de l'installation.")
            if self.install_target == "ssh":
                raise ValueError(
                    "La console locale ne pilote pas le Docker distant. "
                    "Utilisez les liens des applications ou la console en conteneur."
                )
            if self.admin_server is None:
                token = admin.generate_token()
                if self.demo:
                    from .demo_admin import DemoServer

                    self.admin_server = DemoServer(self.cfg, token)
                else:
                    self.admin_server = admin.build_server(
                        self.cfg, self.project_dir, host="127.0.0.1", port=0, token=token
                    )
                port = self.admin_server.server_address[1]
                self.admin_url = f"http://127.0.0.1:{port}/?t={token}"
                threading.Thread(target=self.admin_server.serve_forever, daemon=True).start()
            return {"url": self.admin_url}


class WizardServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = False

    def __init__(self, project_dir, *, port=0, demo=False):
        self.state = WizardState(project_dir, demo=demo)
        self.token = secrets.token_urlsafe(32)
        self.stopping = threading.Event()
        self.access_previews = {}
        self.access_previews_lock = threading.Lock()
        super().__init__(("127.0.0.1", port), WizardHandler)
        self.origin = f"http://127.0.0.1:{self.server_address[1]}"

    def issue_access_preview(self):
        # Une navigation ne peut pas fournir le Bearer du fetch authentifie.
        # Un ticket court, a usage unique, evite de mettre ce Bearer dans l'URL.
        html = self.state.access_page()
        ticket = secrets.token_urlsafe(32)
        with self.access_previews_lock:
            now = time.monotonic()
            self.access_previews = {
                key: value for key, value in self.access_previews.items() if value[0] > now
            }
            if len(self.access_previews) >= 8:
                oldest = min(self.access_previews, key=lambda key: self.access_previews[key][0])
                del self.access_previews[oldest]
            self.access_previews[ticket] = (now + 60, html)
        return {"url": f"/access-preview/{ticket}"}

    def consume_access_preview(self, ticket):
        with self.access_previews_lock:
            item = self.access_previews.pop(ticket, None)
        if item is None or item[0] <= time.monotonic():
            return None
        return item[1]


class WizardHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *args):
        pass  # Ne jamais journaliser les requetes ni le jeton.

    def respond(self, body, status=200, content_type="application/json; charset=utf-8", *, csp=None):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            csp or "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
        )
        self.end_headers()
        self.wfile.write(data)

    def allowed(self, *, authenticated=True):
        origin = self.server.origin
        if self.headers.get("Host") != origin.removeprefix("http://"):
            self.respond({"error": "Hote refuse."}, 403)
            return False
        if self.headers.get("Origin") not in (None, origin):
            self.respond({"error": "Origine refusee."}, 403)
            return False
        supplied = self.headers.get("Authorization", "")
        if authenticated and not hmac.compare_digest(supplied, "Bearer " + self.server.token):
            self.respond(
                {"error": "Session absente ou expiree. Rouvrez le lien affiche dans le terminal."},
                401,
            )
            return False
        return True

    def do_GET(self):
        route = urlsplit(self.path).path
        assets = {
            "/": ("wizard.html", "text/html; charset=utf-8"),
            "/wizard.css": ("wizard.css", "text/css; charset=utf-8"),
            "/wizard-profile.css": ("wizard-profile.css", "text/css; charset=utf-8"),
            "/wizard-parity.css": ("wizard-parity.css", "text/css; charset=utf-8"),
            "/wizard.js": ("wizard.js", "text/javascript; charset=utf-8"),
            "/graph.js": ("graph.js", "text/javascript; charset=utf-8"),
            "/remote.js": ("remote.js", "text/javascript; charset=utf-8"),
            "/graph.css": ("graph.css", "text/css; charset=utf-8"),
        }
        preview_route = route.startswith("/access-preview/")
        if not self.allowed(authenticated=route not in assets and not preview_route):
            return
        if route in assets:
            name, mime = assets[route]
            self.respond((ASSETS / name).read_bytes(), content_type=mime)
        elif preview_route:
            ticket = route.removeprefix("/access-preview/")
            html = self.server.consume_access_preview(ticket)
            if html is None:
                self.respond({"error": "Apercu expire. Rouvrez-le depuis PlugArr."}, 404)
                return
            hashes = [
                "'sha256-" + base64.b64encode(hashlib.sha256(match.group(1)).digest()).decode() + "'"
                for match in re.finditer(
                    rb"<script(?:\s[^>]*)?>(.*?)</script>", html, re.IGNORECASE | re.DOTALL
                )
            ]
            csp = (
                "default-src 'none'; script-src " + (" ".join(hashes) or "'none'")
                + "; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; "
                "base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'none'"
            )
            self.respond(html, content_type="text/html; charset=utf-8", csp=csp)
        elif route == "/api/bootstrap":
            self.respond(self.server.state.bootstrap())
        elif route == "/api/startup":
            self.respond(self.server.state.startup_checks())
        elif route == "/api/events":
            self.stream_events()
        elif route == "/api/progress":
            self.respond(self.server.state.progress())
        elif route == "/api/report":
            self.respond(self.server.state.report())
        elif route == "/api/updates":
            self.respond(self.server.state.available_updates())
        elif route == "/api/indexers":
            self.respond(self.server.state.indexer_overview())
        elif route == "/api/access":
            self.respond(
                self.server.state.access_page(),
                content_type="text/html; charset=utf-8",
            )
        elif route == "/api/templates":
            state = self.server.state
            if state.demo:
                names, problem = recyclarr.bundled_manifest(), None
            else:
                path = Path(state.previous.config_root) / "recyclarr" if state.previous else None
                names, problem = recyclarr.available_templates(path)
            self.respond({"names": names, "problem": problem, "bundled": state.demo})
        else:
            self.respond({"error": "Route inconnue."}, 404)

    def receive_indexer_backup(self):
        """Recoit le fichier brut, l'ecrit dans un dossier temporaire le temps
        de le lire, puis l'efface : la sauvegarde contient les cles des
        indexeurs et n'a pas a rester sur le disque."""
        try:
            if self.headers.get("Content-Type", "").split(";")[
                0
            ] != "application/octet-stream" or self.headers.get("Transfer-Encoding"):
                raise ValueError("Fichier de sauvegarde attendu.")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BACKUP_UPLOAD:
                raise ValueError("Taille de fichier refusee (2 Go au plus).")
            self.server.state.prepare_indexer_backup()
        except (ValueError, TypeError):
            vider_corps_requete(self)
            raise
        dossier = Path(tempfile.mkdtemp(prefix="plugarr-televersement-"))
        try:
            chemin = dossier / "sauvegarde"
            with open(chemin, "wb") as fichier:
                reste = length
                while reste > 0:
                    morceau = self.rfile.read(min(reste, 1024 * 1024))
                    if not morceau:
                        raise ValueError("Televersement interrompu.")
                    fichier.write(morceau)
                    reste -= len(morceau)
            return self.server.state.inspect_indexer_backup(chemin)
        finally:
            shutil.rmtree(dossier, ignore_errors=True)

    def receive_phone_share(self):
        """Recoit le fichier prepare par le navigateur pour le telephone. Il
        reste en memoire, jamais sur le disque, le temps d'un telechargement."""
        try:
            if self.headers.get("Content-Type", "").split(";")[
                0
            ] != "application/octet-stream" or self.headers.get("Transfer-Encoding"):
                raise ValueError("Fichier attendu.")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_PHONE_SHARE:
                raise ValueError("Taille de fichier refusee (1 Mo au plus).")
        except (ValueError, TypeError):
            vider_corps_requete(self)
            raise
        contenu = self.rfile.read(length)
        if len(contenu) != length:
            raise ValueError("Envoi interrompu.")
        nom = parse_qs(urlsplit(self.path).query).get("name", [""])[0]
        return self.server.state.share_to_phone(contenu, nom)

    def stream_events(self):
        """Instantane initial puis mises a jour poussees, avec reprise sans perte.

        fetch() porte l'Authorization : aucun jeton dans l'URL de l'API.
        Un flux court est reconnecte par le navigateur, limitant sa duree de vie.
        """
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        state = self.server.state
        last_revision = -1
        deadline = time.monotonic() + 25
        try:
            while time.monotonic() < deadline and not self.server.stopping.is_set():
                with state.changed:
                    if state.revision == last_revision:
                        state.changed.wait(timeout=1)
                    snapshot = state.progress()
                if snapshot["revision"] != last_revision:
                    data = json.dumps(snapshot, ensure_ascii=False)
                    self.wfile.write(("data: " + data + "\n\n").encode("utf-8"))
                    self.wfile.flush()
                    last_revision = snapshot["revision"]
                if snapshot["status"] != "running":
                    break
        except (OSError, TimeoutError):
            pass  # Fermer un onglet ne doit jamais interrompre l'installation.
        self.close_connection = True

    def do_POST(self):
        if not self.allowed():
            # Vider le corps avant de fermer : sinon la pile TCP repond un RST
            # et le client perd le 401 ou le 403 qu'on vient d'ecrire.
            vider_corps_requete(self)
            return
        try:
            state = self.server.state
            route = urlsplit(self.path).path
            if route == "/api/indexers/backup":
                self.respond(self.receive_indexer_backup())
                return
            if route == "/api/phone-share":
                self.respond(self.receive_phone_share())
                return
            if self.headers.get("Content-Type", "").split(";")[
                0
            ] != "application/json" or self.headers.get("Transfer-Encoding"):
                vider_corps_requete(self)
                raise ValueError("Corps JSON requis.")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                vider_corps_requete(self)
                raise ValueError("Taille de requete refusee.")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise TypeError("Objet JSON requis.")
            if route == "/api/selection":
                selected = body.get("services")
                if (
                    not isinstance(selected, list)
                    or len(selected) > 40
                    or not all(
                        isinstance(s, str)
                        and s in catalog.CATALOG
                        and not catalog.get(s).internal
                        for s in selected
                    )
                ):
                    raise ValueError("Selection de services invalide.")
                resolved = catalog.resolve_dependencies(selected)
                preview = orchestrator.build_config(services=selected)
                result = {
                    "services": resolved,
                    "selected_count": len(set(selected)),
                    "effective_count": len(resolved),
                    "planned_links": orchestrator.planned_links(preview),
                }
            elif route == "/api/remote-install/probe":
                result = state.probe_remote_install(body)
            elif route == "/api/path-check":
                result = state.check_paths(body)
            elif route == "/api/vpn-test":
                result = state.test_vpn(body)
            elif route == "/api/backup":
                result = state.create_backup(body)
            elif route == "/api/restore/inspect":
                result = state.inspect_restore(body)
            elif route == "/api/restore":
                result = state.restore(body)
            elif route == "/api/indexers/search":
                result = state.search_indexers(body)
            elif route == "/api/indexers/add":
                result = state.add_indexer(body)
            elif route == "/api/indexers/backup/import":
                result = state.import_indexer_backup(body)
            elif route == "/api/graph":
                result = state.graph_preview(body)
            elif route == "/api/validate":
                result = state.validate(body)
            elif route == "/api/install":
                result = state.start(body)
            elif route == "/api/remote":
                result = state.remote_action(body)
            elif route == "/api/preference":
                if state.demo:
                    raise ValueError("Les preferences ne sont pas modifiees en demonstration.")
                save_preference(Interface(body.get("interface")))
                result = {"ok": True}
            elif route == "/api/reload":
                with state.lock:
                    if state.status != "error" or (state.worker and state.worker.is_alive()):
                        raise ValueError("Attendez la fin des operations avant de recharger.")
                    state.close_resources()
                    if not state.demo:
                        state.reload_previous()
                    else:
                        state.previous = None
                        state.previous_project_dir = None
                        state.project_dir = state.launch_project_dir
                        state.initial_hash = None
                    state.status = "idle"
                    state.plan_id = None
                    state.events = []
                    state.graph = None
                    state.graph_results = {}
                    state.active_step = None
                    state.deployed = False
                    state.cfg = None
                    state.console_password = ""
                    state.remote_result = None
                    state.reprise = None
                    state.reset_candidates = []
                    state.reset_requested = False
                    state.reset_cfg = None
                    state.reset_project_dir = None
                    state.reset_existing_stack = False
                    state.results = []
                result = {"ok": True}
            elif route == "/api/admin":
                result = state.open_admin()
            elif route == "/api/access-preview":
                result = self.server.issue_access_preview()
            elif route == "/api/close":
                with state.lock:
                    if state.status == "running" or (state.remote_worker and state.remote_worker.is_alive()):
                        raise ValueError("Attendez la fin de l'installation avant de fermer.")
                    state.result = 0
                self.respond({"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            elif route == "/api/tui":
                with state.lock:
                    if (
                        state.status != "idle"
                        or state.demo
                        or not sys.stdin.isatty()
                        or not sys.stdout.isatty()
                    ):
                        raise ValueError(
                            "Retour au TUI indisponible pendant ou apres une installation."
                        )
                    state.result = "tui"
                self.respond({"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            else:
                self.respond({"error": "Route inconnue."}, 404)
                return
            self.respond(result)
        except ValidationError as exc:
            # Pydantic inclut normalement les valeurs d'entree, dont les secrets.
            fields = [".".join(map(str, e["loc"])) for e in exc.errors(include_input=False)]
            self.respond({"error": "Champs invalides : " + ", ".join(fields)}, 400)
        except (ValueError, TypeError, KeyError) as exc:
            self.respond({"error": self.server.state.redact(exc)}, 400)
        except OSError:
            self.respond(
                {
                    "error": "Impossible de lire ou ecrire la configuration locale. Verifiez les permissions."
                },
                400,
            )
        except Exception:  # noqa: BLE001
            self.respond(
                {"error": "Operation impossible. Consultez le terminal puis reessayez."}, 500
            )


def run_web(project_dir: Path, *, port=0, open_page=True, demo=False):
    import typer

    try:
        server = WizardServer(project_dir, port=port, demo=demo)
    except (OSError, ValueError) as exc:
        typer.echo(f"Assistant web indisponible : {exc}")
        return 2
    url = server.origin + "/#token=" + server.token
    typer.echo(f"PlugArr {'DEMO' if demo else 'WEB'} : {url}")
    typer.echo("Gardez ce terminal ouvert. Ctrl+C pour fermer apres l'installation.")
    if open_page:
        try:
            opened = webbrowser.open(url)
        except webbrowser.Error:
            opened = False
        if not opened:
            typer.echo("Navigateur non ouvert. Copiez l'adresse ci-dessus dans votre navigateur.")
            if not demo and sys.stdin.isatty() and typer.confirm("Revenir au TUI ?", default=False):
                server.server_close()
                return "tui"
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        typer.echo("Fermeture : attente de la fin des operations en cours.")
    finally:
        server.stopping.set()
        with server.state.changed:
            server.state.changed.notify_all()
        if server.state.worker:
            server.state.worker.join()
        if server.state.remote_worker:
            server.state.remote_worker.join()
        if server.state.admin_server:
            server.state.admin_server.shutdown()
            server.state.admin_server.server_close()
        server.state.close_resources()
        server.server_close()
    return server.state.result
