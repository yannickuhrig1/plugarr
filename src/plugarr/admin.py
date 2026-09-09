"""Serveur d'administration local : etat des services, demarrer / arreter / redemarrer.

La page d'acces statique ne peut pas piloter Docker : un fichier HTML n'execute
rien. Il faut un serveur. Celui-ci est volontairement minuscule et repose
uniquement sur la bibliotheque standard.

Modele de securite, parce qu'une page capable d'arreter des conteneurs n'est pas
anodine :

- **ecoute sur 127.0.0.1 par defaut.** Exposer sur le reseau demande `--host`,
  et l'avertissement est explicite ;
- **jeton obligatoire**, tire au hasard a chaque demarrage, jamais ecrit sur
  disque. Il arrive par l'URL puis est stocke en cookie `HttpOnly` ;
- **mot de passe optionnel**, pour une console qui tourne en permanence : le
  jeton ne convient que si quelqu'un lit le terminal au demarrage. Empreinte
  seule dans `stack.yml`, sessions en memoire, tentatives limitees. Voir
  `adminauth` ;
- **comparaison a temps constant**, pour ne pas fuiter le jeton octet par octet ;
- **listes fermees** : le nom de service est valide contre la configuration et
  l'action contre trois valeurs, avant de rejoindre une ligne de commande.
"""

from __future__ import annotations

import hmac
import json
import secrets
import sys
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import (
    adminauth,
    autoupdate,
    catalog,
    compose,
    dashboard,
    imageref,
    journal,
    orchestrator,
    sauvegarde,
    updates,
    vpncheck,
)
from .clients.arr import ArrClient
from .i18n import t
from .models import StackConfig
from .runner import Compose

ACTIONS = ("start", "stop", "restart")

#: Le controle interroge les registres : quelques secondes. On garde le resultat
#: brievement pour que l'ouverture de la page ne le relance pas a chaque fois.
UPDATE_CACHE_SECONDS = 300
COOKIE = "plugarr_token"


@dataclass
class ServiceState:
    service: str
    state: str  # running, exited, created, paused...
    status: str  # libelle lisible ("Up 3 minutes")
    health: str = ""

    @property
    def up(self) -> bool:
        return self.state == "running"


def read_states(compose: Compose) -> dict[str, ServiceState]:
    """Etat par service, indexe par nom de service compose."""
    states: dict[str, ServiceState] = {}
    for entry in compose.ps_json():
        name = entry.get("Service")
        if not name:
            continue
        states[name] = ServiceState(
            service=name,
            state=str(entry.get("State", "")),
            status=str(entry.get("Status", "")),
            health=str(entry.get("Health", "") or ""),
        )
    return states


def status_payload(cfg: StackConfig, compose: Compose) -> dict:
    """Etat de chaque service SELECTIONNE, meme absent de docker : un service
    installe mais jamais demarre doit apparaitre, pas disparaitre."""
    states = read_states(compose)
    services = []
    for sid in catalog.STARTUP_ORDER:
        if not cfg.enabled(sid):
            continue
        found = states.get(sid)
        services.append(
            {
                "id": sid,
                "name": catalog.get(sid).display_name,
                "state": found.state if found else "absent",
                "status": found.status if found else "conteneur absent",
                "health": found.health if found else "",
                "up": bool(found and found.up),
            }
        )
    return {"services": services}


def updates_payload(cfg: StackConfig) -> dict:
    """Etat des mises a jour, service par service."""
    entries = []
    for info in updates.check(cfg):
        entries.append(
            {
                "id": info.service,
                "name": catalog.get(info.service).display_name,
                "current": info.current_tag,
                "latest": info.latest_tag,
                "rebuilt": info.rebuilt,
                "available": info.has_update,
                "problems": info.problems,
            }
        )
    # PlugArr lui-meme : le bouton « chercher les mises a jour » ne regardait
    # que les images des services. Quelqu'un pouvait donc tout avoir a jour
    # sauf l'outil qui lui dit que tout est a jour.
    sortie = autoupdate.derniere()
    return {
        "services": entries,
        "plugarr": {
            "current": sortie.courante,
            "latest": sortie.disponible,
            "available": bool(sortie.disponible),
            "url": sortie.url,
            "problem": sortie.probleme,
        },
    }


#: Controles qui n'ont de sens qu'AVANT d'installer, et qu'un diagnostic ne
#: doit donc pas rapporter. « Une configuration existe deja » est un
#: avertissement utile a qui s'apprete a en generer une nouvelle ; sur une
#: installation en marche c'est la situation normale, et l'annoncer en ECHEC
#: envoie chercher une panne qui n'existe pas.
_AVANT_INSTALLATION = ("configuration existante", "nom de projet")


def doctor_payload(cfg: StackConfig, project_dir: Path) -> dict:
    """Le meme diagnostic que `plugarr doctor`, rendu depuis la console.

    Demande a l'usage : « un bouton pour lancer plugarr doctor ». Il n'existait
    qu'en ligne de commande, ce qui allait contre la regle du projet — tout ce
    que plugarr sait faire doit etre atteignable sans ouvrir un terminal.

    On reutilise `preflight` plutot que d'ecrire un second diagnostic : deux
    verifications du meme systeme finiraient par ne plus dire la meme chose.
    """
    controles = [
        {"name": c.name, "ok": c.ok, "detail": c.detail, "blocking": c.blocking, "partage": False}
        for c in orchestrator.preflight(cfg, project_dir)
        if c.name not in _AVANT_INSTALLATION
    ]

    # La joignabilite reelle des API : un conteneur qui tourne n'est pas un
    # service qui repond, et c'est la distinction que `doctor` apporte.
    for sid, inst in orchestrator.iter_selected(cfg):
        spec = catalog.get(sid)
        if spec.api_family != "arr":
            continue
        try:
            with ArrClient(
                inst.url(cfg.host), inst.api_key or "", api_version=spec.api_version, name=sid
            ) as client:
                controles.append(
                    {
                        "name": f"API {spec.display_name}",
                        "ok": True,
                        "detail": f"repond, version {client.version}",
                        "blocking": False,
                        "partage": False,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            controles.append(
                {
                    "name": f"API {spec.display_name}",
                    "ok": False,
                    "detail": str(exc).splitlines()[0],
                    "blocking": False,
                    "partage": False,
                }
            )
    # La fuite VPN en DERNIER, pour qu'elle se lise en bas du rapport, la ou
    # l'oeil s'arrete. C'est le controle dont la reponse compte le plus.
    #
    # `partage` separe les controles de PORT ENTRANT des autres, exactement
    # comme l'installation separe ses deux verdicts. Les confondre serait
    # trompeur : un port desynchronise coute du partage, pas de l'exposition, et
    # l'annoncer comme « controle en echec » a cote d'un tunnel tombe ferait
    # craindre une fuite la ou il n'y en a aucune. L'installation faisait deja
    # cette distinction, la console non — meme systeme, deux verdicts differents.
    controles += [
        {
            "name": c.name,
            "ok": c.ok,
            "detail": c.detail,
            "blocking": c.blocking,
            "partage": c.name.startswith(vpncheck.PREFIXE_PORT),
        }
        for c in vpncheck.verifier(cfg)
    ]
    echecs = sum(1 for c in controles if not c["ok"] and not c["partage"])
    partage = sum(1 for c in controles if not c["ok"] and c["partage"])
    return {"checks": controles, "failed": echecs, "partage": partage}


def apply_update(
    cfg: StackConfig, runner: Compose, project_dir: Path, service: str, target: str | None
) -> tuple[bool, str]:
    """Met a jour UN service.

    Sans `target`, on retire la meme image reconstruite. Avec, on change le tag
    deploye : `stack.yml` et le compose sont reecrits AVANT le pull, sinon Docker
    retirerait l'ancienne version.
    """
    inst = cfg.services[service]
    previous = inst.image or catalog.get(service).image

    if target:
        # `with_tag` laisse tomber un eventuel digest : garder l'ancien
        # condensat avec un nouveau tag donnerait une reference qui ment, Docker
        # retenant le digest.
        inst.image = imageref.with_tag(previous, target)
        compose.write_artifacts(cfg, project_dir)

    ok, message = runner.pull(service)
    if not ok:
        if target:
            inst.image = previous
            compose.write_artifacts(cfg, project_dir)
        return False, f"telechargement echoue, version inchangee : {message[:300]}"

    ok, message = runner.recreate(service)
    if not ok:
        return False, f"image a jour mais recreation echouee : {message[:300]}"
    return True, f"{previous.rpartition(':')[2]} -> {inst.image.rpartition(':')[2]}"


_CONNEXION = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>plugarr — connexion</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #f6f7f9; color: #111827;
         display: grid; place-items: center; min-height: 100vh; margin: 0; }}
  form {{ background: #fff; padding: 2rem; border-radius: 12px; min-width: 20rem;
          box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
  h1 {{ font-size: 1.1rem; margin: 0 0 1.2rem; }}
  input {{ width: 100%; padding: .6rem; font-size: 1rem; box-sizing: border-box;
           border: 1px solid #d1d5db; border-radius: 6px; }}
  button {{ margin-top: 1rem; width: 100%; padding: .6rem; font-size: 1rem; cursor: pointer;
            background: #2563eb; color: #fff; border: 0; border-radius: 6px; }}
  .erreur {{ color: #dc2626; font-size: .9rem; margin-top: .8rem; }}
</style></head><body>
<form method="post" action="/login">
  <h1>Administration plugarr</h1>
  <input type="password" name="password" placeholder="Mot de passe" autofocus
         autocomplete="current-password">
  <button type="submit">Entrer</button>
  <p class="erreur">{erreur}</p>
</form></body></html>
"""


def _page_connexion(erreur: str = "") -> str:
    return _CONNEXION.format(erreur=erreur)


class _Handler(BaseHTTPRequestHandler):
    # Renseignes par serve()
    cfg: StackConfig
    compose: Compose
    token: str
    project_dir: Path
    sessions: adminauth.Sessions

    server_version = "plugarr"
    sys_version = ""

    def log_message(self, fmt: str, *args: object) -> None:
        """Silence : le serveur tourne au premier plan dans le terminal de
        l'utilisateur, un journal d'acces n'y apporterait rien."""

    # -- authentification ---------------------------------------------------

    def _presented_token(self) -> str:
        query = parse_qs(urlparse(self.path).query)
        if query.get("t"):
            return query["t"][0]
        for part in (self.headers.get("Cookie") or "").split(";"):
            key, _, value = part.strip().partition("=")
            if key == COOKIE:
                return value
        return ""

    def _authorised(self) -> bool:
        """Deux voies, et la seconde n'existe que si un mot de passe est pose.

        Le jeton sert au lancement a la main : il s'affiche dans le terminal,
        juste au-dessus de l'URL. La session sert a une console qui tourne en
        permanence, ou personne n'ira lire un journal de conteneur pour
        retrouver un jeton a chaque redemarrage.
        """
        presente = self._presented_token()
        # Comparaison sur des OCTETS, pas sur des chaines. `compare_digest`
        # refuse les `str` non-ASCII et leve `TypeError` : un cookie contenant
        # un caractere accentue suffisait donc a tuer le fil de traitement,
        # sans la moindre authentification. Trouve en essayant un faux jeton
        # accentue.
        if hmac.compare_digest(presente.encode("utf-8"), self.token.encode("utf-8")):
            return True
        return bool(self.cfg.admin_password_hash) and self.sessions.valid(presente)

    def _deny(self) -> None:
        """Formulaire si un mot de passe existe, message sec sinon.

        Renvoyer un formulaire sans mot de passe configure serait cruel : il n'y
        aurait rien a y taper.
        """
        if self.cfg.admin_password_hash:
            page = _page_connexion().encode("utf-8")
            self._send(HTTPStatus.UNAUTHORIZED, page, "text/html; charset=utf-8")
            return
        body = b"Jeton absent ou invalide. Utilisez l'URL affichee par `plugarr serve`."
        self.send_response(HTTPStatus.UNAUTHORIZED)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _connexion(self) -> None:
        """Verifie le mot de passe et ouvre une session.

        La limitation des tentatives est indispensable des que la console sort
        de 127.0.0.1 : sans elle, un mot de passe se devine en quelques heures.
        """
        if not self.cfg.admin_password_hash:
            self._deny()
            return
        if self.sessions.locked_out:
            attente = self.sessions.retry_in()
            page = _page_connexion(
                t("Trop de tentatives. Reessayez dans {secondes} s.", secondes=attente)
            )
            self._send(HTTPStatus.TOO_MANY_REQUESTS, page.encode("utf-8"),
                       "text/html; charset=utf-8")
            return

        longueur = int(self.headers.get("Content-Length") or 0)
        # 4 Ko : un formulaire de connexion n'a aucune raison d'etre plus gros,
        # et lire ce qu'on nous annonce sans borne est une invitation.
        champs = parse_qs(self.rfile.read(min(longueur, 4096)).decode("utf-8", "replace"))
        propose = (champs.get("password") or [""])[0]

        if not adminauth.verify_password(propose, self.cfg.admin_password_hash):
            self.sessions.record_failure()
            page = _page_connexion("Mot de passe refuse.")
            self._send(HTTPStatus.UNAUTHORIZED, page.encode("utf-8"), "text/html; charset=utf-8")
            return

        self.sessions.clear_failures()
        jeton = self.sessions.open()
        page = dashboard.render(self.cfg, live=True).encode("utf-8")
        self._send(HTTPStatus.OK, page, "text/html; charset=utf-8", cookie=True, cookie_value=jeton)

    def _send(
        self,
        status: HTTPStatus,
        body: bytes,
        content_type: str,
        cookie: bool = False,
        cookie_value: str | None = None,
    ):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        # Une console qui affiche des mots de passe n'a rien a faire dans un
        # cadre : `frame-ancestors none` interdit le detournement de clic.
        self.send_header(
            "Content-Security-Policy", "default-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
        )
        self.send_header("Referrer-Policy", "no-referrer")
        if cookie:
            valeur = cookie_value if cookie_value is not None else self.token
            self.send_header(
                "Set-Cookie", f"{COOKIE}={valeur}; Path=/; HttpOnly; SameSite=Strict"
            )
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    # -- routes -------------------------------------------------------------

    def do_GET(self) -> None:
        if not self._authorised():
            self._deny()
            return
        route = urlparse(self.path).path
        if route == "/":
            page = dashboard.render(self.cfg, live=True).encode("utf-8")
            self._send(HTTPStatus.OK, page, "text/html; charset=utf-8", cookie=True)
        elif route == "/api/status":
            self._json(status_payload(self.cfg, self.compose))
        elif route == "/api/updates":
            self._json(updates_payload(self.cfg))
        elif route == "/api/doctor":
            self._json(doctor_payload(self.cfg, self.project_dir))
        else:
            self._json({"error": "route inconnue"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        route_brute = urlparse(self.path).path
        if route_brute == "/login":
            self._connexion()
            return
        if route_brute == "/logout":
            self.sessions.close(self._presented_token())
            self._send(HTTPStatus.OK, _page_connexion("Deconnecte.").encode("utf-8"),
                       "text/html; charset=utf-8", cookie=True, cookie_value="")
            return
        if not self._authorised():
            self._deny()
            return
        route = urlparse(self.path).path
        if route not in ("/api/action", "/api/update", "/api/rotate", "/api/add"):
            self._json({"error": "route inconnue"}, HTTPStatus.NOT_FOUND)
            return

        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json({"error": "corps JSON invalide"}, HTTPStatus.BAD_REQUEST)
            return

        service = str(payload.get("service", ""))
        if route == "/api/add":
            # Liste fermee : seuls les services ABSENTS sont installables, et le
            # nom finit dans une ligne de commande docker compose.
            if service not in orchestrator.installable(self.cfg):
                self._json(
                    {
                        "error": t(
                            "service inconnu ou deja installe : {service}",
                            service=service,
                        )
                    },
                    HTTPStatus.BAD_REQUEST,
                )
                return
            ok, message, ajoutes = orchestrator.add_service(self.cfg, self.project_dir, service)
            self._json(
                {"ok": ok, "service": service, "message": message, "added": ajoutes},
                HTTPStatus.OK if ok else HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        if route == "/api/backup":
            chemin = self.project_dir / sauvegarde.nom_par_defaut(self.cfg)
            try:
                rapport = sauvegarde.sauvegarder(self.cfg, self.project_dir, chemin)
            except Exception as exc:  # noqa: BLE001
                journal.LOGGER.exception("sauvegarde")
                self._json({"ok": False, "error": str(exc)[:200]})
                return
            self._json(
                {
                    "ok": True,
                    "archive": str(rapport.archive),
                    "mega": round(rapport.archive.stat().st_size / 1_048_576, 1),
                    "fichiers": rapport.fichiers,
                    "volumes": rapport.volumes,
                }
            )
            return

        if route == "/api/rotate":
            if not self.cfg.enabled(service):
                self._json({"error": f"service inconnu: {service}"}, HTTPStatus.BAD_REQUEST)
                return
            quoi = str(payload.get("what", "password"))
            # Liste fermee : ce choix designe une fonction, pas une chaine libre.
            if quoi not in ("password", "api_key"):
                self._json({"error": f"secret inconnu: {quoi}"}, HTTPStatus.BAD_REQUEST)
                return
            rotation = (
                orchestrator.rotate_password if quoi == "password" else orchestrator.rotate_api_key
            )
            ok, message, secret = rotation(self.cfg, self.project_dir, service)
            # Le secret part vers la page qui vient de le demander, et nulle part
            # ailleurs : ni journal, ni sortie terminal.
            self._json(
                {"ok": ok, "service": service, "what": quoi, "message": message, "secret": secret},
                HTTPStatus.OK if ok else HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        if route == "/api/update":
            if not self.cfg.enabled(service):
                self._json({"error": f"service inconnu: {service}"}, HTTPStatus.BAD_REQUEST)
                return
            target = payload.get("target")
            if target is not None and updates.parse_version(str(target)) is None:
                # Le tag finit dans une image Docker : il doit ressembler a une
                # version, jamais a ce que le client veut bien envoyer.
                self._json(
                    {"error": f"tag refuse: {target}"}, HTTPStatus.BAD_REQUEST
                )
                return
            ok, message = apply_update(
                self.cfg, self.compose, self.project_dir, service,
                str(target) if target else None,
            )
            self._json(
                {"ok": ok, "service": service, "message": message},
                HTTPStatus.OK if ok else HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        action = str(payload.get("action", ""))

        # Listes fermees : ces deux valeurs finissent dans une ligne de commande.
        if action not in ACTIONS:
            self._json({"error": f"action refusee: {action}"}, HTTPStatus.BAD_REQUEST)
            return
        if not self.cfg.enabled(service):
            self._json({"error": f"service inconnu: {service}"}, HTTPStatus.BAD_REQUEST)
            return

        ok, message = self.compose.control(action, service)
        self._json(
            {"ok": ok, "service": service, "action": action, "message": message[:400]},
            HTTPStatus.OK if ok else HTTPStatus.INTERNAL_SERVER_ERROR,
        )


class _Server(ThreadingHTTPServer):
    """Serveur qui refuse de partager son port.

    `HTTPServer` active `allow_reuse_address`. Sous Linux, SO_REUSEADDR n'autorise
    pas deux ecoutes simultanees. Sous Windows, SI : un second `bind` reussit en
    silence et les requetes partent au hasard vers l'un ou l'autre processus.

    Constate en conditions reelles — deux `plugarr serve` lances de suite, et la
    page renvoyait « jeton invalide » une fois sur deux, chaque processus ayant
    tire son propre jeton. Mieux vaut un echec net au demarrage, que la CLI sait
    deja rapporter.
    """

    allow_reuse_address = sys.platform != "win32"


def build_server(
    cfg: StackConfig, project_dir: Path, *, host: str, port: int, token: str
) -> ThreadingHTTPServer:
    handler = type(
        "BoundHandler",
        (_Handler,),
        {
            "cfg": cfg,
            "compose": Compose(project_dir, cfg.project_name),
            "token": token,
            "project_dir": project_dir,
            # UNE instance partagee par toutes les requetes : les sessions et le
            # compteur de tentatives n'ont aucun sens s'ils sont par connexion.
            "sessions": adminauth.Sessions(),
        },
    )
    server = _Server((host, port), handler)
    server.daemon_threads = True
    return server


def generate_token() -> str:
    return secrets.token_urlsafe(24)


def serve(
    cfg: StackConfig,
    project_dir: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 7373,
    token: str | None = None,
    on_ready=None,
) -> None:
    """Sert la page d'administration jusqu'a interruption."""
    token = token or generate_token()
    server = build_server(cfg, project_dir, host=host, port=port, token=token)
    url = f"http://{host if host != '0.0.0.0' else '127.0.0.1'}:{port}/?t={token}"
    if on_ready:
        on_ready(url, token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
