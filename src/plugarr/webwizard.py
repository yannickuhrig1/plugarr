"""Assistant web local : saisie, preflight et progression du moteur existant.

Le jeton reste dans le fragment de l'URL puis en memoire de session du navigateur.
Aucune route ne lance une commande arbitraire. Le mode demo n'appelle ni Docker,
ni le moteur d'installation, ni les lecteurs de configuration de l'utilisateur.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import ntpath
import posixpath
import re
import secrets
import sys
import threading
import time
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import admin, catalog, i18n, journal, migrations, orchestrator, vpnservers, wizard_graph
from .clients import recyclarr
from .interface import Interface, save_preference
from .layout import PROFILE_DEFAULTS, default_profile
from .models import VPN_PROVIDERS, PlatformProfile, VpnConfig

ASSETS = Path(__file__).parent / "web"


class WizardInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    services: list[str] = Field(min_length=1, max_length=40)
    platform: str
    config_root: str = Field(min_length=1, max_length=1024)
    data_root: str = Field(min_length=1, max_length=1024)
    project_name: str = Field(min_length=1, max_length=63)
    username: str = Field(min_length=1, max_length=100)
    timezone: str = "Etc/UTC"
    language: str = "fr"
    ui_language: str = "fr"
    vpn: dict = Field(default_factory=dict)
    recyclarr_templates: dict[str, str] = Field(default_factory=dict)


class WizardState:
    def __init__(self, project_dir: Path, *, demo: bool = False):
        self.project_dir = project_dir.resolve()
        self.demo = demo
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.revision = 0
        self.graph = None
        self.graph_results = {}
        self.active_step = None
        self.deployed = False
        self.previous = None
        self.initial_hash = self.stack_hash() if not demo else None
        if not demo and (self.project_dir / "stack.yml").exists():
            # Une configuration illisible ou future doit bloquer, jamais etre ecrasee.
            self.previous, _ = migrations.lire(self.project_dir / "stack.yml")
        self.cfg = None
        self.plan_id = None
        self.validated_at = 0.0
        self.events: list[dict] = []
        self.status = "idle"
        self.worker = None
        self.admin_server = None
        self.admin_url = None
        self.result = 0

    def stack_hash(self):
        path = self.project_dir / "stack.yml"
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None

    def bootstrap(self):
        cfg = self.previous
        platform = cfg.platform if cfg else default_profile()
        defaults = PROFILE_DEFAULTS[platform]
        icons = json.loads((ASSETS.parent / "data/connection_icons.json").read_text("utf-8"))
        vpn = cfg.vpn.model_dump() if cfg else VpnConfig().model_dump()
        for key in ("wireguard_private_key", "openvpn_password", "openvpn_user"):
            vpn[key] = ""  # Les champs vides conservent les identifiants existants.
        return {
            "demo": self.demo,
            "existing": cfg is not None,
            "download_clients": list(catalog.DOWNLOAD_CLIENTS),
            "project_dir": str(self.project_dir),
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
            "profiles": {
                p.value: {"config_root": d.config_root, "data_root": d.data_root}
                for p, d in PROFILE_DEFAULTS.items()
            },
            "providers": {
                p: {"choices": vpnservers.choices(p), "label": i18n.t(vpnservers.label(p))}
                for p in VPN_PROVIDERS
            },
            "form": {
                "services": [s for s in cfg.services if not catalog.get(s).internal]
                if cfg
                else list(catalog.DEFAULT_SELECTION),
                "platform": platform.value,
                "config_root": cfg.config_root if cfg else defaults.config_root,
                "data_root": cfg.data_root if cfg else defaults.data_root,
                "project_name": cfg.project_name if cfg else "plugarr",
                "username": cfg.username if cfg else "plugarr",
                "timezone": cfg.timezone if cfg else "Etc/UTC",
                "language": cfg.language if cfg else i18n.langue(),
                "ui_language": cfg.ui_language if cfg else i18n.langue(),
                "vpn": vpn,
                "recyclarr_templates": cfg.recyclarr_templates if cfg else {},
            },
        }

    def build_config(self, payload):
        form = WizardInput.model_validate(payload)
        platform = PlatformProfile(form.platform)
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
        cfg = orchestrator.build_config(
            services=form.services,
            platform=platform,
            config_root=form.config_root,
            data_root=form.data_root,
            project_name=form.project_name,
            username=form.username,
            timezone=form.timezone,
            language=form.language,
        )
        if self.previous:
            old = self.previous
            for key in ("platform", "config_root", "data_root", "project_name", "username"):
                if getattr(cfg, key) != getattr(old, key):
                    raise ValueError(
                        "Cette premiere version conserve les chemins, la plateforme, le nom et l'identifiant de la pile existante."
                    )
            # Conserver aussi les images, ports secondaires, cle de chiffrement et droits.
            for sid in cfg.services.keys() & old.services.keys():
                cfg.services[sid] = old.services[sid].model_copy(deep=True)
            for key in (
                "host",
                "puid",
                "pgid",
                "umask",
                "ids_source",
                "ids_certain",
                "admin_password_hash",
            ):
                setattr(cfg, key, getattr(old, key))
            if set(old.services) - set(cfg.services):
                raise ValueError(
                    "La suppression de services existants reste dans la console d'administration."
                )
        vpn = dict(form.vpn)
        if set(vpn) - set(VpnConfig.model_fields):
            raise ValueError("Champ VPN inconnu.")
        if self.previous and self.previous.vpn.enabled:
            old_vpn = self.previous.vpn
            if vpn.get("provider") == old_vpn.provider and vpn.get("vpn_type") == old_vpn.vpn_type:
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
            if not any(cfg.enabled(s) for s in catalog.DOWNLOAD_CLIENTS):
                raise ValueError("Le VPN demande un client de telechargement selectionne.")
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
            places = vpnservers.choices(cfg.vpn.provider)
            if places and any(
                p.strip() not in places for p in cfg.vpn.countries.split(",") if p.strip()
            ):
                raise ValueError("Localisation VPN absente de la liste de Gluetun.")
        cfg.ui_language = form.ui_language
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
        cfg.project_dir = self.project_dir
        return cfg

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
        cfg = orchestrator.build_config(services=selected, language=language)
        cfg.vpn.enabled = vpn and any(cfg.enabled(s) for s in catalog.DOWNLOAD_CLIENTS)
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
            cfg = self.build_config(payload)
            if not self.demo and self.stack_hash() != self.initial_hash:
                raise ValueError(
                    "stack.yml a change. Relancez l'assistant pour reprendre la configuration actuelle."
                )
            checks = (
                []
                if self.demo
                else [asdict(c) for c in orchestrator.preflight(cfg, self.project_dir)]
            )
            blocked = any(not c["ok"] and c["blocking"] for c in checks)
            self.cfg = cfg
            self.graph = wizard_graph.build(cfg)
            self.plan_id = secrets.token_urlsafe(24) if not blocked else None
            self.validated_at = time.monotonic()
            warnings = []
            if any(cfg.enabled(s) for s in catalog.DOWNLOAD_CLIENTS) and not cfg.vpn.enabled:
                warnings.append(
                    "Aucun VPN : les telechargements utiliseront l'adresse IP publique de cette machine."
                )
            if self.previous:
                warnings.append(
                    "Reinstallation : les conteneurs existants seront arretes puis relances. Identifiants et versions sont conserves."
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
                    }
                    for s, inst in cfg.services.items()
                ],
                "config_root": cfg.config_root,
                "data_root": cfg.data_root,
                "project_name": cfg.project_name,
                "vpn": cfg.vpn.enabled,
                "recyclarr_templates": cfg.recyclarr_templates,
                "graph": self.graph,
            }

    def redact(self, message):
        message = str(message)
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
            if not self.demo and self.stack_hash() != self.initial_hash:
                self.plan_id = None
                raise ValueError("stack.yml a change depuis la verification. Relancez l'assistant.")
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
            journal.start(self.project_dir, "web")
            journal.config(self.cfg)

            def progress(p):
                journal.progress(p.phase, p.message, p.ok)
                self.event(p.phase, p.message, p.ok)

            def step(s):
                journal.step(s)
                self.event(s.name, s.detail, s.ok, step_id=s.step_id or None, warnings=s.warnings)

            results = orchestrator.install(
                self.cfg,
                self.project_dir,
                on_progress=progress,
                on_step=step,
                on_step_start=lambda sid: self.event(
                    sid, "Etape en cours", step_id=sid, started=True
                ),
            )
            self.set_status("done" if all(s.ok for s in results) else "partial")
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
        super().__init__(("127.0.0.1", port), WizardHandler)
        self.origin = f"http://127.0.0.1:{self.server_address[1]}"


class WizardHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *args):
        pass  # Ne jamais journaliser les requetes ni le jeton.

    def respond(self, body, status=200, content_type="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
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
            "/wizard.js": ("wizard.js", "text/javascript; charset=utf-8"),
            "/graph.js": ("graph.js", "text/javascript; charset=utf-8"),
            "/graph.css": ("graph.css", "text/css; charset=utf-8"),
        }
        if not self.allowed(authenticated=route not in assets):
            return
        if route in assets:
            name, mime = assets[route]
            self.respond((ASSETS / name).read_bytes(), content_type=mime)
        elif route == "/api/bootstrap":
            self.respond(self.server.state.bootstrap())
        elif route == "/api/events":
            self.stream_events()
        elif route == "/api/progress":
            self.respond(self.server.state.progress())
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
            return
        try:
            if self.headers.get("Content-Type", "").split(";")[
                0
            ] != "application/json" or self.headers.get("Transfer-Encoding"):
                raise ValueError("Corps JSON requis.")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536:
                raise ValueError("Taille de requete refusee.")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise TypeError("Objet JSON requis.")
            state = self.server.state
            route = urlsplit(self.path).path
            if route == "/api/selection":
                selected = body.get("services")
                if not isinstance(selected, list) or not all(
                    isinstance(s, str) and s in catalog.CATALOG for s in selected
                ):
                    raise ValueError("Selection de services invalide.")
                result = {"services": catalog.resolve_dependencies(selected)}
            elif route == "/api/graph":
                result = state.graph_preview(body)
            elif route == "/api/validate":
                result = state.validate(body)
            elif route == "/api/install":
                result = state.start(body)
            elif route == "/api/preference":
                if state.demo:
                    raise ValueError("Les preferences ne sont pas modifiees en demonstration.")
                save_preference(Interface(body.get("interface")))
                result = {"ok": True}
            elif route == "/api/reload":
                with state.lock:
                    if state.status != "error" or (state.worker and state.worker.is_alive()):
                        raise ValueError("Attendez la fin des operations avant de recharger.")
                    previous = None
                    if not state.demo and (state.project_dir / "stack.yml").exists():
                        previous, _ = migrations.lire(state.project_dir / "stack.yml")
                    state.previous = previous
                    state.initial_hash = state.stack_hash() if not state.demo else None
                    state.status = "idle"
                    state.plan_id = None
                    state.events = []
                    state.graph = None
                    state.graph_results = {}
                    state.active_step = None
                    state.deployed = False
                result = {"ok": True}
            elif route == "/api/admin":
                result = state.open_admin()
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
        if server.state.admin_server:
            server.state.admin_server.shutdown()
            server.state.admin_server.server_close()
        server.server_close()
    return server.state.result
