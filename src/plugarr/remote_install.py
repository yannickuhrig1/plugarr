"""Installation d'une machine Linux pilotee par SSH.

L'interface publique reste volontairement petite : ``probe`` decrit la cible
sans rien y ecrire, puis ``deploy`` y lance l'installation. Les details du
transport SSH restent derriere la couture ``connect``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import ipaddress
import json
import secrets
import shlex
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Protocol

import yaml

PROBE_SCRIPT = r"""set -u
printf 'system=%s\n' "$(uname -s 2>/dev/null || true)"
printf 'machine=%s\n' "$(uname -m 2>/dev/null || true)"
printf 'uid=%s\n' "$(id -u 2>/dev/null || true)"
printf 'gid=%s\n' "$(id -g 2>/dev/null || true)"
printf 'home=%s\n' "${HOME:-}"
printf 'docker=%s\n' "$(docker version --format '{{.Server.Version}}' 2>/dev/null || true)"
printf 'addresses=%s\n' "$(hostname -I 2>/dev/null || true)"
printf 'route_address=%s\n' "$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' | head -n 1)"
"""


REMOTE_ENTRYPOINT = r'''"""Point d'entree ephemere de l'installation distante PlugArr."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from plugarr import migrations, orchestrator, remote_access

# Essai reel du 25/09/2026 : le catalogue d'une image epingle forcement l'image
# PRECEDENTE (une image ne connait pas sa propre empreinte). La console deployee
# ignorait donc Shelfarr et plantait a chaque connexion. L'image qui execute ce
# script connait, elle, tous les services qu'elle installe.
for _nom in ("CONSOLE_IMAGE", "VEILLE_IMAGE"):
    if os.environ.get("PLUGARR_" + _nom):
        setattr(orchestrator.catalog, _nom, os.environ["PLUGARR_" + _nom])


def emit(**event):
    print(json.dumps(event, ensure_ascii=False), flush=True)


def reuse_sabnzbd_key(cfg):
    """Le fichier existant fait autorite, pas la cle generee pour ce passage."""
    instance = cfg.services.get("sabnzbd")
    if instance is None:
        return
    ini = Path(cfg.config_path("sabnzbd")) / "sabnzbd.ini"
    try:
        if ini.stat().st_size > 1024 * 1024:
            return
        lines = ini.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    section = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip().lower()
        if section != "misc" or not re.match(r"^api_key\s*=", stripped, re.I):
            continue
        key = stripped.split("=", 1)[1].strip().strip('"\'')
        if re.fullmatch(r"[A-Za-z0-9]{16,128}", key):
            instance.api_key = key
            instance.password = key
            emit(kind="progress", phase="reprise", message="Cle API SABnzbd existante reprise.")
        return


def align_sabnzbd_key(cfg):
    """Aligne la copie d'affichage sur la cle vraiment pre-semee.

    L'image d'administration preview.2 lit encore ``api_key`` en premier pour
    DroppedNeedle, alors que SABnzbd et tous les autres clients utilisent
    ``password``. Garder les deux identiques permet au nouvel executable de
    corriger une installation distante sans attendre une nouvelle image.
    """
    instance = cfg.services.get("sabnzbd")
    if instance is None:
        return
    key = instance.password or instance.api_key or ""
    instance.password = key
    instance.api_key = key


def saved_account_candidates(cfg, project_dir, service_id):
    """Anciens comptes PlugArr, au plus quatre essais et sans divulguer de secret."""
    instance = cfg.services[service_id]
    candidates = [(instance.username or cfg.username, instance.password or "")]
    backups = []
    for path in project_dir.glob(".stack-before-remote-*.yml"):
        try:
            if path.is_symlink():
                continue
            info = path.stat()
        except OSError:
            continue
        if info.st_size <= 1024 * 1024:
            backups.append((info.st_mtime, path))
    for _mtime, path in sorted(backups):
        if len(candidates) >= 4:
            break
        try:
            previous, _ = migrations.lire(path)
        except (OSError, ValueError):
            continue
        old = previous.services.get(service_id)
        if old is None or not old.password:
            continue
        candidate = (old.username or previous.username, old.password)
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def reuse_existing_account(cfg, project_dir, service_id, client_type):
    """Ne reprend un compte qu'apres un login confirme, avant l'arret."""
    instance = cfg.services.get(service_id)
    if instance is None:
        return
    from plugarr.clients.base import WiringError

    try:
        with client_type(instance.url(cfg.host)) as client:
            if client.needs_setup:
                return
            for username, password in saved_account_candidates(cfg, project_dir, service_id):
                if not password:
                    continue
                try:
                    client.login(username, password)
                except WiringError as exc:
                    if "HTTP 401" in str(exc):
                        continue
                    return
                instance.username = username
                instance.password = password
                emit(
                    kind="progress",
                    phase="reprise",
                    message=f"Compte {service_id} existant confirme.",
                )
                return
    except (OSError, WiringError):
        # L'installation peut continuer si le service n'est pas disponible ;
        # le cablage signalera alors son echec sans effacer sa base.
        return


def reuse_droppedneedle_account(cfg, project_dir):
    if "droppedneedle" in cfg.services:
        from plugarr.clients.droppedneedle import DroppedNeedleClient
        reuse_existing_account(cfg, project_dir, "droppedneedle", DroppedNeedleClient)


def reuse_audiobookshelf_account(cfg, project_dir):
    if "audiobookshelf" in cfg.services:
        from plugarr.clients.audiobookshelf import AudiobookshelfClient
        reuse_existing_account(cfg, project_dir, "audiobookshelf", AudiobookshelfClient)


def remove_root_owned_config(dossier, image):
    """Termine un effacement autorise quand une image a cree un sous-dossier root.

    Le conteneur temporaire ne monte que le dossier du service concerne. Il ne
    recoit ni les medias, ni le projet, ni le socket Docker. Le conteneur
    d'installation, lui, reprend ensuite sous l'UID normal.
    """
    if any(char in str(dossier) for char in (",", "\n", "\r")):
        raise ValueError("Chemin de configuration incompatible avec le nettoyage Docker")
    script = (
        "from pathlib import Path\n"
        "import shutil\n"
        "root = Path('/plugarr-reset')\n"
        "for child in root.iterdir():\n"
        "    if child.is_dir() and not child.is_symlink():\n"
        "        shutil.rmtree(child)\n"
        "    else:\n"
        "        child.unlink()\n"
    )
    result = subprocess.run(
        [
            "docker", "run", "--rm", "--user", "0:0",
            "--mount", f"type=bind,src={dossier},dst=/plugarr-reset",
            "--entrypoint", "python", image, "-c", script,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise OSError(
            "Nettoyage de la configuration par Docker impossible : "
            + (result.stderr.strip()[-300:] or f"code {result.returncode}")
        )
    dossier.rmdir()


def reset_existing_configs(previous, project_dir, candidates, image):
    """Reste compatible avec l'API de l'image admin deja publiee.

    Cette image ne connait pas `permission_fallback`. Si elle rencontre un
    dossier cree par root, seul le service qui contient le chemin refuse est
    nettoye par le conteneur temporaire, puis le reset reprend.
    """
    from plugarr import catalog

    pending = list(candidates)
    config_root = Path(previous.config_root).resolve()
    for _attempt in range(len(candidates) + 1):
        try:
            orchestrator.reset_installation_configs(previous, project_dir, pending)
            return
        except PermissionError as exc:
            if not exc.filename:
                raise
            blocked_path = Path(exc.filename).resolve()
            matched = None
            for sid in pending:
                if catalog.get(sid).named_volumes:
                    continue
                raw_dossier = Path(previous.config_path(sid))
                dossier = raw_dossier.resolve()
                if config_root not in dossier.parents:
                    continue
                parent = raw_dossier
                while parent != Path(previous.config_root) and parent != parent.parent:
                    if parent.is_symlink():
                        raise ValueError("Lien symbolique dans la configuration a nettoyer")
                    parent = parent.parent
                if blocked_path == dossier or dossier in blocked_path.parents:
                    matched = (sid, dossier)
                    break
            if matched is None:
                raise
            sid, dossier = matched
            remove_root_owned_config(dossier, image)
            pending.remove(sid)
            emit(
                kind="progress", phase="Remise a zero",
                message=f"{sid}: configuration root nettoyee de facon isolee.",
            )
    raise RuntimeError("Nettoyage distant incomplet apres plusieurs refus de permission")


def main():
    project_dir = Path(sys.argv[1])
    operation = sys.argv[2] if len(sys.argv) > 2 else "install"
    try:
        cfg, notes = migrations.lire(project_dir / "stack.yml")
        for note in notes:
            emit(kind="progress", phase="migration", message=note)

        if operation not in ("install", "reset-install"):
            actions = {
                "activate": remote_access.activate,
                "inspect": remote_access.inspect,
                "deactivate": remote_access.deactivate,
            }
            if operation not in actions:
                raise ValueError("Operation distante inconnue")
            remote_result = actions[operation](cfg, project_dir)
            emit(kind="remote_access", result=remote_result)
            emit(kind="done", status="done")
            return 0

        checks = orchestrator.preflight(cfg, project_dir)
        for check in checks:
            emit(
                kind="check",
                name=check.name,
                ok=check.ok,
                detail=check.detail,
                blocking=check.blocking,
            )
        if any(not check.ok and check.blocking for check in checks):
            emit(kind="done", status="failed", message="Prerequis distants non satisfaits")
            return 2

        if operation == "reset-install":
            import hashlib
            from plugarr import catalog

            expected_sha = sys.argv[3] if len(sys.argv) > 3 else ""
            if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
                raise ValueError("Empreinte de la pile a nettoyer invalide")
            reset_image = sys.argv[4] if len(sys.argv) > 4 else ""
            if not reset_image:
                raise ValueError("Image du nettoyage distant absente")
            old_path = project_dir / (".stack-before-remote-" + expected_sha[:16] + ".yml")
            if old_path.is_symlink() or not old_path.is_file():
                raise ValueError("Sauvegarde de l'ancienne pile absente ou non sure")
            if hashlib.sha256(old_path.read_bytes()).hexdigest() != expected_sha:
                raise ValueError("La sauvegarde de l'ancienne pile ne correspond pas a la verification")
            previous, _ = migrations.lire(old_path)
            old_config = Path(previous.config_root).resolve()
            old_data = Path(previous.data_root).resolve()
            if (
                previous.project_name != cfg.project_name
                or previous.config_root != cfg.config_root
                or previous.data_root != cfg.data_root
                or old_config == old_data
                or old_config in old_data.parents
            ):
                raise ValueError("Les chemins ou le nom de la pile ont change : remise a zero refusee")
            unknown = set(previous.services) - set(catalog.STARTUP_ORDER)
            if unknown:
                raise ValueError("Services inconnus dans l'ancienne pile : remise a zero refusee")
            candidates = orchestrator.existing_configs(previous)
            reset_existing_configs(previous, project_dir, candidates, reset_image)
            emit(kind="progress", phase="Remise a zero", message=f"{len(candidates)} configurations retirees ; medias conserves.")

        reuse_sabnzbd_key(cfg)
        align_sabnzbd_key(cfg)
        reuse_droppedneedle_account(cfg, project_dir)
        reuse_audiobookshelf_account(cfg, project_dir)

        def on_progress(progress):
            emit(
                kind="progress",
                phase=progress.phase,
                message=progress.message,
                ok=progress.ok,
                done=progress.done,
                started=progress.started,
            )

        def on_step(step):
            emit(
                kind="step",
                name=step.name,
                ok=step.ok,
                detail=step.detail,
                created=step.created,
                warnings=step.warnings,
                step_id=step.step_id,
            )

        # L'image admin epinglee peut predater la prise en charge des
        # conteneurs techniques dans la ligne de progression des images.
        # Elle connait deja ces services dans Compose, mais catalog.get()
        # leve une erreur quand elle veut seulement afficher leur nom.
        old_catalog_get = orchestrator.catalog.get
        legacy_image = not hasattr(orchestrator, "_compose_service_name")

        def catalog_get_for_legacy_image(service_id):
            if service_id in ("docker-proxy", "veille", "console"):
                return SimpleNamespace(display_name=service_id)
            return old_catalog_get(service_id)

        if legacy_image:
            orchestrator.catalog.get = catalog_get_for_legacy_image
        try:
            results = orchestrator.install(
                cfg,
                project_dir,
                on_progress=on_progress,
                on_step=on_step,
            )
        finally:
            if legacy_image:
                orchestrator.catalog.get = old_catalog_get
        # Le pre-semis et la reprise de comptes peuvent avoir adopte des
        # identifiants existants. Le poste qui pilote l'installation doit
        # recevoir les valeurs finales, jamais ses valeurs generees avant SSH.
        emit(
            kind="credentials",
            services={
                service_id: {
                    "username": instance.username,
                    "password": instance.password,
                    "api_key": instance.api_key,
                }
                for service_id, instance in cfg.services.items()
            },
        )
        if cfg.remote_access.mode != "local":
            try:
                remote_result = remote_access.activate(cfg, project_dir)
            except Exception as exc:
                remote_result = remote_access.summary(cfg)
                remote_result.update(status="error", message=str(exc))
            emit(kind="remote_access", result=remote_result)
        emit(kind="done", status="partial" if any(not item.ok for item in (results or [])) else "done")
        return 0
    except Exception as exc:
        emit(kind="done", status="failed", message=str(exc))
        return 1


raise SystemExit(main())
'''


VPN_TEST_ENTRYPOINT = r'''"""Essai VPN jetable execute sur le Docker de la cible SSH."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from plugarr import vpnessai
from plugarr.models import VpnConfig


def main():
    try:
        vpn = VpnConfig.model_validate_json(Path(sys.argv[1]).read_text(encoding="utf-8"))
        check = vpnessai.essayer(vpn, sys.argv[2])
        print(json.dumps(asdict(check), ensure_ascii=False), flush=True)
        return 0
    except Exception:
        print(
            json.dumps(
                {
                    "name": "Essai VPN",
                    "ok": False,
                    "detail": "Essai VPN distant impossible. Verifiez Docker et les journaux du serveur.",
                    "blocking": False,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 1


raise SystemExit(main())
'''


@dataclass(frozen=True)
class RemoteTarget:
    host: str
    port: int = 22
    username: str = ""
    expected_fingerprint: str = ""


@dataclass(frozen=True)
class RemoteCredentials:
    password: str = field(default="", repr=False)
    private_key: str = field(default="", repr=False)
    passphrase: str = field(default="", repr=False)
    sudo_password: str = field(default="", repr=False)


@dataclass(frozen=True)
class RemoteDeployment:
    project_dir: str
    config_root: str
    data_root: str
    uid: int
    gid: int
    stack_yaml: str = field(repr=False)
    image: str = ""
    veille_image: str = ""
    replace_existing: bool = False
    reset_existing: bool = False
    expected_existing_sha: str = field(default="", repr=False)


@dataclass(frozen=True)
class RemoteDeployResult:
    status: str
    events: tuple[dict[str, object], ...] = field(repr=False)


@dataclass(frozen=True)
class RemoteProjectState:
    exists: bool
    managed: bool
    stack_sha: str = ""
    project_name: str = ""
    config_root: str = ""
    data_root: str = ""
    services: tuple[str, ...] = ()
    stack_yaml: str = field(default="", repr=False, compare=False)


@dataclass(frozen=True)
class RemoteProbe:
    fingerprint: str
    system: str
    machine: str
    uid: int
    gid: int
    home: str
    docker_version: str
    addresses: tuple[str, ...] = ()
    route_address: str = ""

    @property
    def ready(self) -> bool:
        return self.system == "Linux" and bool(self.docker_version)

    def suggested_host(self, ssh_host: str) -> str:
        """Adresse que les conteneurs de la cible peuvent joindre.

        Essai reel du 25/09/2026 sur un VPS Oracle : l'IP publique SSH est
        traduite par le reseau du fournisseur, la machine ne porte que
        10.0.0.30. Utilisee comme hote, elle faisait expirer l'attente de
        Sonarr apres 300 s. Un nom DNS est garde : il n'est pas verifiable ici.
        """
        try:
            ipaddress.ip_address(ssh_host)
        except ValueError:
            return ssh_host
        if not self.addresses or ssh_host in self.addresses or not self.route_address:
            return ssh_host
        return self.route_address


class SSHSession(Protocol):
    fingerprint: str

    def run(self, command: str, *, stdin: bytes | None = None) -> tuple[int, str, str]: ...

    def run_stream(
        self,
        command: str,
        on_line: Callable[[str], None],
    ) -> tuple[int, str]: ...

    def upload(self, path: str, data: bytes, *, mode: int = 0o600) -> None: ...

    def close(self) -> None: ...


Connector = Callable[[RemoteTarget, RemoteCredentials], SSHSession]


class FingerprintMismatch(ValueError):
    """La cle presentee n'est pas celle que l'utilisateur a confirmee."""


class _ParamikoSession:
    """Adaptateur minimal autour de Paramiko, sans fichier de cle temporaire."""

    def __init__(self, client, fingerprint: str):
        self._client = client
        self.fingerprint = fingerprint

    def run(self, command: str, *, stdin: bytes | None = None) -> tuple[int, str, str]:
        remote_stdin, stdout, stderr = self._client.exec_command(command)
        if stdin:
            remote_stdin.write(stdin)
            remote_stdin.flush()
        remote_stdin.close()
        output = stdout.read().decode("utf-8", errors="replace")
        error = stderr.read().decode("utf-8", errors="replace")
        return stdout.channel.recv_exit_status(), output, error

    def upload(self, path: str, data: bytes, *, mode: int = 0o600) -> None:
        with self._client.open_sftp() as sftp:
            with sftp.file(path, "wb") as remote_file:
                remote_file.write(data)
                remote_file.flush()
            sftp.chmod(path, mode)

    def run_stream(
        self,
        command: str,
        on_line: Callable[[str], None],
    ) -> tuple[int, str]:
        remote_stdin, stdout, stderr = self._client.exec_command(command)
        remote_stdin.close()
        for raw_line in iter(stdout.readline, b""):
            if not raw_line:
                break
            if isinstance(raw_line, bytes):
                line = raw_line.decode("utf-8", errors="replace")
            else:
                line = str(raw_line)
            on_line(line.rstrip("\r\n"))
        error = stderr.read().decode("utf-8", errors="replace")
        return stdout.channel.recv_exit_status(), error

    def close(self) -> None:
        self._client.close()


def _private_key(paramiko, credentials: RemoteCredentials):
    if not credentials.private_key:
        return None
    errors = []
    for key_class_name in ("Ed25519Key", "ECDSAKey", "RSAKey"):
        key_class = getattr(paramiko, key_class_name, None)
        if key_class is None or not hasattr(key_class, "from_private_key"):
            continue
        try:
            return key_class.from_private_key(
                io.StringIO(credentials.private_key),
                password=credentials.passphrase or None,
            )
        except (paramiko.SSHException, ValueError) as exc:
            errors.append(str(exc))
    detail = errors[-1] if errors else "format de cle non pris en charge"
    raise ValueError(f"Cle privee SSH illisible : {detail}")


def connect_paramiko(
    target: RemoteTarget,
    credentials: RemoteCredentials,
) -> SSHSession:
    """Ouvre une session SSH sans enregistrer le secret ni le ``known_hosts``."""
    if not target.host.strip() or not target.username.strip():
        raise ValueError("Hote et utilisateur SSH requis.")
    if not 1 <= target.port <= 65535:
        raise ValueError("Port SSH invalide.")
    if not credentials.password and not credentials.private_key:
        raise ValueError("Mot de passe ou cle privee SSH requis.")

    try:
        import paramiko  # Import tardif pour garder les autres commandes legeres.
    except ImportError as exc:
        # Sans ce message, l'assistant web ne montrait qu'une erreur 500 muette.
        raise ValueError(
            "Module SSH (paramiko) absent de cette version de PlugArr. "
            "Reinstallez PlugArr ou utilisez un executable complet."
        ) from exc

    pkey = _private_key(paramiko, credentials)
    client = paramiko.SSHClient()
    # La premiere connexion est une TOFU explicite : ``probe`` renvoie cette
    # empreinte a l'utilisateur. ``deploy`` exigera ensuite sa confirmation.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=target.host,
            port=target.port,
            username=target.username,
            password=credentials.password or None,
            pkey=pkey,
            allow_agent=False,
            look_for_keys=False,
            timeout=10,
            banner_timeout=10,
            auth_timeout=15,
        )
        transport = client.get_transport()
        if transport is None:
            raise RuntimeError("La connexion SSH n'a pas fourni de transport.")
        server_key = transport.get_remote_server_key()
        fingerprint = getattr(server_key, "fingerprint", "")
        if not fingerprint:
            fingerprint = "MD5:" + ":".join(f"{byte:02x}" for byte in server_key.get_fingerprint())
        return _ParamikoSession(client, fingerprint)
    except Exception:
        client.close()
        raise


def _values(output: str) -> dict[str, str]:
    result = {}
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            result[key] = value
    return result


def _verified_session(
    target: RemoteTarget,
    credentials: RemoteCredentials,
    connect: Connector,
) -> SSHSession:
    session = connect(target, credentials)
    if target.expected_fingerprint and not hmac.compare_digest(
        target.expected_fingerprint, session.fingerprint
    ):
        session.close()
        raise FingerprintMismatch(
            "L'empreinte SSH a change depuis sa confirmation. Installation refusee."
        )
    return session


def _remote_path(value: str, label: str) -> str:
    path = PurePosixPath(value)
    if not path.is_absolute() or path == PurePosixPath("/") or "\n" in value:
        raise ValueError(f"{label} doit etre un chemin Linux absolu et non racine.")
    return str(path)


def _managed_stack_test(stack_path: str) -> str:
    """Reconnaît le vrai stack.yml PlugArr, sans afficher ses secrets."""
    quoted = shlex.quote(stack_path)
    return (
        f"head -n 1 {quoted} | grep -Eq '^# (Genere par|Generated by) plugarr -' "
        f"&& grep -q '^project_name:' {quoted} "
        f"&& grep -q '^config_root:' {quoted} "
        f"&& grep -q '^data_root:' {quoted} "
        f"&& grep -q '^services:' {quoted}"
    )


def probe(
    target: RemoteTarget,
    credentials: RemoteCredentials,
    *,
    connect: Connector,
) -> RemoteProbe:
    """Decrit une cible SSH sans modifier son systeme de fichiers."""
    session = _verified_session(target, credentials, connect)
    try:
        code, output, error = session.run(PROBE_SCRIPT)
        if code:
            raise RuntimeError(error.strip() or "Le diagnostic SSH a echoue.")
        values = _values(output)
        return RemoteProbe(
            fingerprint=session.fingerprint,
            system=values.get("system", ""),
            machine=values.get("machine", ""),
            uid=int(values.get("uid", "-1")),
            gid=int(values.get("gid", "-1")),
            home=values.get("home", ""),
            docker_version=values.get("docker", ""),
            addresses=tuple(values.get("addresses", "").split()),
            route_address=values.get("route_address", "").strip(),
        )
    finally:
        session.close()


def inspect_project(
    target: RemoteTarget,
    credentials: RemoteCredentials,
    project_dir: str,
    *,
    connect: Connector,
) -> RemoteProjectState:
    """Inspecte une pile distante sans l'ecrire ni demarrer de conteneur."""
    project = _remote_path(project_dir, "project_dir")
    stack = project + "/stack.yml"
    quoted = shlex.quote(stack)
    command = (
        "set -eu\n"
        f"if [ ! -f {quoted} ]; then printf 'exists=0\\n'; exit 0; fi\n"
        "printf 'exists=1\\n'\n"
        f"printf 'stack_sha=%s\\n' \"$(sha256sum {quoted} | awk '{{print $1}}')\"\n"
        f"if {_managed_stack_test(stack)}; then printf 'managed=1\\n'; "
        "else printf 'managed=0\\n'; fi\n"
        f"if command -v base64 >/dev/null 2>&1 && [ ! -L {quoted} ] "
        f"&& [ \"$(wc -c < {quoted})\" -le 1048576 ]; "
        f"then printf 'stack_b64='; base64 < {quoted} | tr -d '\\n'; printf '\\n'; fi\n"
    )
    session = _verified_session(target, credentials, connect)
    try:
        code, output, error = session.run(command)
        if code:
            raise RuntimeError(error.strip() or "Inspection de la pile distante impossible.")
        values = _values(output)
        summary = {}
        stack_text = ""
        if values.get("managed") == "1" and values.get("stack_b64"):
            try:
                stack_bytes = base64.b64decode(values["stack_b64"], validate=True)
                if hashlib.sha256(stack_bytes).hexdigest() == values.get("stack_sha"):
                    loaded = yaml.safe_load(stack_bytes) or {}
                    if isinstance(loaded, dict):
                        summary = loaded
                        stack_text = stack_bytes.decode("utf-8")
            except (ValueError, yaml.YAMLError):
                pass
        services = summary.get("services", {})
        if not isinstance(services, dict):
            services = {}
        return RemoteProjectState(
            exists=values.get("exists") == "1",
            managed=values.get("managed") == "1",
            stack_sha=values.get("stack_sha", ""),
            project_name=str(summary.get("project_name", "")),
            config_root=str(summary.get("config_root", "")),
            data_root=str(summary.get("data_root", "")),
            services=tuple(str(service) for service in services),
            stack_yaml=stack_text,
        )
    finally:
        session.close()


def test_vpn(
    target: RemoteTarget,
    credentials: RemoteCredentials,
    vpn_values: dict[str, object],
    *,
    uid: int,
    gid: int,
    admin_image: str,
    gluetun_image: str,
    connect: Connector,
) -> dict[str, object]:
    """Teste Gluetun sur le Docker distant, sans secret dans la commande SSH."""
    if not target.expected_fingerprint:
        raise ValueError("L'empreinte SSH doit etre confirmee avant l'essai VPN.")
    if uid < 0 or gid < 0:
        raise ValueError("UID et GID distants invalides.")
    if not admin_image or not gluetun_image:
        raise ValueError("Les images Docker de l'essai VPN sont requises.")

    token = secrets.token_urlsafe(12).replace("-", "").replace("_", "")
    config_path = f"/tmp/.plugarr-vpn-test-{token}.json"
    entry_path = f"/tmp/.plugarr-vpn-test-{token}.py"
    session = _verified_session(target, credentials, connect)
    try:
        session.upload(
            config_path,
            json.dumps(vpn_values, ensure_ascii=False).encode("utf-8"),
            mode=0o600,
        )
        session.upload(entry_path, VPN_TEST_ENTRYPOINT.encode("utf-8"), mode=0o600)
        code, output, error = session.run(
            "stat -c 'sock_gid=%g' /var/run/docker.sock"
        )
        if code:
            raise RuntimeError(error.strip() or "Socket Docker distante inaccessible.")
        socket_gid = _values(output).get("sock_gid", "")
        if not socket_gid.isdigit():
            raise RuntimeError("Groupe de la socket Docker distante introuvable.")

        command = " ".join(
            (
                "docker run --rm",
                f"--user {uid}:{gid}",
                f"--group-add {socket_gid}",
                "-e HOME=/tmp",
                "-e DOCKER_CONFIG=/tmp/.docker",
                "-v /var/run/docker.sock:/var/run/docker.sock",
                f"-v {shlex.quote(config_path)}:{shlex.quote(config_path)}:ro",
                f"-v {shlex.quote(entry_path)}:{shlex.quote(entry_path)}:ro",
                "--entrypoint python",
                shlex.quote(admin_image),
                shlex.quote(entry_path),
                shlex.quote(config_path),
                shlex.quote(gluetun_image),
            )
        )
        code, output, error = session.run(command)
        result = None
        for line in reversed(output.splitlines()):
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                result = candidate
                break
        if result is None:
            raise RuntimeError(error.strip() or "L'essai VPN distant n'a rendu aucun resultat.")
        if code and result.get("ok") is not False:
            raise RuntimeError(error.strip() or "L'essai VPN distant a echoue.")
        return result
    finally:
        session.run(
            "rm -f " + " ".join(shlex.quote(path) for path in (config_path, entry_path))
        )
        session.close()


def deploy(
    target: RemoteTarget,
    credentials: RemoteCredentials,
    deployment: RemoteDeployment,
    *,
    connect: Connector,
    on_event: Callable[[dict[str, object]], None] | None = None,
    operation: str = "install",
) -> RemoteDeployResult:
    """Installe PlugArr avec Docker sur une cible deja sondee et confirmee."""
    if not target.expected_fingerprint:
        raise ValueError("L'empreinte SSH doit etre confirmee avant l'installation.")
    if not deployment.image:
        raise ValueError("L'image d'administration PlugArr est requise.")
    if operation not in ("install", "activate", "inspect", "deactivate"):
        raise ValueError("Operation distante inconnue.")

    project = _remote_path(deployment.project_dir, "project_dir")
    config = _remote_path(deployment.config_root, "config_root")
    data = _remote_path(deployment.data_root, "data_root")
    if deployment.uid < 0 or deployment.gid < 0:
        raise ValueError("UID et GID distants invalides.")
    if deployment.reset_existing and operation != "install":
        raise ValueError("La remise a zero distante exige une installation confirmee.")

    session = _verified_session(target, credentials, connect)
    events: list[dict[str, object]] = []
    try:
        directories = tuple(dict.fromkeys((project, config, data)))
        quoted_dirs = " ".join(shlex.quote(path) for path in directories)
        prepare = (
            "set -eu\n"
            f"mkdir -p {quoted_dirs}\n"
            "printf 'sock_gid=%s\\n' \"$(stat -c %g /var/run/docker.sock)\"\n"
            f"if [ -f {shlex.quote(project + '/stack.yml')} ]; then "
            f"if [ -L {shlex.quote(project + '/stack.yml')} ]; then "
            "printf 'stack_symlink=1\\n'; fi; "
            f"printf 'stack_sha=%s\\n' \"$(sha256sum {shlex.quote(project + '/stack.yml')} "
            "| awk '{print $1}')\"; "
            f"if {_managed_stack_test(project + '/stack.yml')}; "
            "then printf 'stack_managed=1\n'; else printf 'stack_managed=0\n'; fi; fi\n"
        )
        code, output, error = session.run(prepare)
        run_as_root = False
        if code and credentials.sudo_password:
            sudo_lines = ["set -eu"]
            for path in directories:
                quoted = shlex.quote(path)
                sudo_lines.append(
                    f"if [ ! -d {quoted} ]; then "
                    f"install -d -m 700 -o {deployment.uid} -g {deployment.gid} {quoted}; fi"
                )
            sudo_lines.append(
                "printf 'sock_gid=%s\\n' \"$(stat -c %g /var/run/docker.sock)\""
            )
            sudo_lines.append(
                f"if [ -f {shlex.quote(project + '/stack.yml')} ]; then "
                f"if [ -L {shlex.quote(project + '/stack.yml')} ]; then "
                "printf 'stack_symlink=1\\n'; fi; "
                f"printf 'stack_sha=%s\\n' \"$(sha256sum "
                f"{shlex.quote(project + '/stack.yml')} | awk '{{print $1}}')\"; "
                f"if {_managed_stack_test(project + '/stack.yml')}; "
                "then printf 'stack_managed=1\n'; else printf 'stack_managed=0\n'; fi; fi"
            )
            sudo_command = "sudo -S -p '' sh -c " + shlex.quote("\n".join(sudo_lines))
            code, output, error = session.run(
                sudo_command,
                stdin=(credentials.sudo_password + "\n").encode("utf-8"),
            )
            run_as_root = code == 0
        if code:
            message = error.strip() or "Preparation des dossiers distants impossible."
            if not credentials.sudo_password:
                message += " Ajoutez le mot de passe sudo si ces dossiers appartiennent a root."
            raise RuntimeError(message)
        socket_gid = _values(output).get("sock_gid", "")
        if not socket_gid.isdigit():
            raise RuntimeError("Groupe de la socket Docker distante introuvable.")
        existing_sha = _values(output).get("stack_sha", "")
        if _values(output).get("stack_symlink") == "1":
            raise RuntimeError("stack.yml distant est un lien symbolique : ecriture refusee.")
        existing_managed = _values(output).get("stack_managed") == "1"
        expected_sha = hashlib.sha256(deployment.stack_yaml.encode("utf-8")).hexdigest()
        if deployment.reset_existing:
            if not existing_sha or not existing_managed:
                raise RuntimeError("Remise a zero refusee : aucune pile PlugArr reconnue.")
            if not deployment.expected_existing_sha or not hmac.compare_digest(
                existing_sha, deployment.expected_existing_sha
            ):
                raise RuntimeError("La pile distante a change depuis la verification.")
        if existing_sha and not hmac.compare_digest(existing_sha, expected_sha):
            if not deployment.replace_existing:
                raise RuntimeError(
                    "Une pile distante existe deja dans ce dossier. "
                    "Confirmez sa mise a jour dans le recapitulatif."
                )
            if operation != "install" or not existing_managed:
                raise RuntimeError(
                    "La pile distante existante n'est pas reconnue comme geree par PlugArr."
                )
            if not deployment.expected_existing_sha or not hmac.compare_digest(
                existing_sha, deployment.expected_existing_sha
            ):
                raise RuntimeError(
                    "La pile distante a change depuis la verification. Verifiez-la a nouveau."
                )
        if existing_sha and (deployment.reset_existing or not hmac.compare_digest(existing_sha, expected_sha)):
            backup_path = f"{project}/.stack-before-remote-{existing_sha[:16]}.yml"
            quoted_stack = shlex.quote(f"{project}/stack.yml")
            quoted_backup = shlex.quote(backup_path)
            backup_command = (
                "set -eu\n"
                f"if [ ! -e {quoted_backup} ]; then "
                f"cp {quoted_stack} {quoted_backup}; chmod 600 {quoted_backup}; fi"
            )
            code, _, error = session.run(backup_command)
            if code:
                raise RuntimeError(
                    error.strip() or "Sauvegarde de la pile distante impossible."
                )
            backup_event = {
                "kind": "progress",
                "phase": "Sauvegarde distante",
                "message": "Ancien stack.yml conserve avant la remise a zero."
                if deployment.reset_existing else "Ancien stack.yml conserve avant la mise a jour.",
            }
            events.append(backup_event)
            if on_event is not None:
                on_event(backup_event)

        stack_path = f"{project}/stack.yml"
        entry_path = f"{project}/.plugarr-remote-entry.py"
        session.upload(stack_path, deployment.stack_yaml.encode("utf-8"), mode=0o600)
        session.upload(entry_path, REMOTE_ENTRYPOINT.encode("utf-8"), mode=0o600)

        command_parts = [
                "docker run --rm",
                f"--group-add {socket_gid}",
                "-e HOME=/tmp",
                "-e DOCKER_CONFIG=/tmp/.docker",
                f"-e PLUGARR_CONSOLE_IMAGE={shlex.quote(deployment.image)}",
                *(
                    [f"-e PLUGARR_VEILLE_IMAGE={shlex.quote(deployment.veille_image)}"]
                    if deployment.veille_image
                    else []
                ),
                "-v /var/run/docker.sock:/var/run/docker.sock",
                f"-v {shlex.quote(project)}:{shlex.quote(project)}",
                f"-v {shlex.quote(config)}:{shlex.quote(config)}",
                f"-v {shlex.quote(data)}:{shlex.quote(data)}",
                f"-w {shlex.quote(project)}",
                "--entrypoint python",
                shlex.quote(deployment.image),
                shlex.quote(entry_path),
                shlex.quote(project),
                "reset-install" if deployment.reset_existing else operation,
        ]
        if deployment.reset_existing:
            command_parts.append(shlex.quote(existing_sha))
            command_parts.append(shlex.quote(deployment.image))
        if not run_as_root:
            command_parts.insert(1, f"--user {deployment.uid}:{deployment.gid}")
        command = " ".join(command_parts)
        def receive_line(line: str) -> None:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                event = {"kind": "log", "message": line}
            if isinstance(event, dict):
                events.append(event)
                if on_event is not None:
                    on_event(event)

        run_stream = getattr(session, "run_stream", None)
        if callable(run_stream):
            code, error = run_stream(command, receive_line)
        else:
            code, output, error = session.run(command)
            for line in output.splitlines():
                receive_line(line)

        status = str(events[-1].get("status", "failed")) if events else "failed"
        if code or status not in ("done", "partial"):
            message = error.strip()
            if events and events[-1].get("message"):
                message = str(events[-1]["message"])
            raise RuntimeError(message or "L'installation distante a echoue.")
        return RemoteDeployResult(status=status, events=tuple(events))
    finally:
        session.close()
