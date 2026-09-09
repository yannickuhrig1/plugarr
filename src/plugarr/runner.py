"""Pilotage de docker compose et preflight."""

from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .i18n import t
from .layout import hardlink_supported


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    blocking: bool = True


#: Un daemon Docker occupe peut mettre tres longtemps a repondre a `docker info`.
#: Constate en conditions reelles : la suite de tests est passee de 45 secondes a
#: 8 minutes, et l'ecran d'accueil de l'assistant serait reste muet tout ce temps.
#: Un diagnostic doit repondre vite, quitte a repondre « je ne sais pas ».
PROBE_TIMEOUT = 20


def _run(args: list[str], cwd: Path | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    # `text=True` seul decode avec l'encodage local, soit cp1252 sous Windows.
    # Docker, lui, ecrit de l'UTF-8 : le journal de Gluetun contient un emoji, et
    # `docker logs` faisait alors tomber le thread de lecture de subprocess.
    # L'exception mourait dans ce thread, `stdout` valait None, et l'appelant
    # recevait une sortie vide sans le moindre indice. `replace` plutot que
    # `strict` : un diagnostic doit survivre a un caractere qu'il ne sait pas
    # rendre.
    try:
        return subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args,
            returncode=124,
            stdout="",
            stderr=f"aucune reponse en {timeout}s",
        )


# --------------------------------------------------------------------- preflight


def check_docker() -> list[Check]:
    checks: list[Check] = []
    binary = shutil.which("docker")
    if not binary:
        return [
            Check(
                "docker",
                False,
                t(
                    "binaire `docker` introuvable dans le PATH. Installez "
                    "Docker Engine ou Docker Desktop, puis relancez."
                ),
            )
        ]
    checks.append(Check("docker", True, t("trouve : {chemin}", chemin=binary)))

    info = _run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=PROBE_TIMEOUT)
    if info.returncode != 0:
        checks.append(
            Check(
                t("daemon docker"),
                False,
                t(
                    "le binaire repond mais le daemon est injoignable ou trop "
                    "lent. Demarrez Docker (Desktop, ou `systemctl start "
                    "docker`). Detail : {detail}",
                    detail=info.stderr.strip()[:200],
                ),
            )
        )
        return checks
    checks.append(
        Check(
            t("daemon docker"),
            True,
            t("version serveur {version}", version=info.stdout.strip()),
        )
    )

    compose = _run(["docker", "compose", "version", "--short"], timeout=PROBE_TIMEOUT)
    checks.append(
        Check(
            "docker compose",
            compose.returncode == 0,
            f"v{compose.stdout.strip()}"
            if compose.returncode == 0
            else t("plugin `docker compose` absent. Installez docker-compose-plugin."),
        )
    )
    return checks


def running_project_dir(project_name: str) -> str | None:
    """Repertoire d'ou tourne DEJA une pile portant ce nom de projet, s'il y en
    a une. None si aucun conteneur ne porte ce nom.

    Docker range les conteneurs par LABEL de projet, pas par repertoire : deux
    installations qui partagent un nom partagent leurs conteneurs, ou que
    vivent leurs fichiers. Ce label est le seul moyen de les distinguer.
    """
    proc = _run(
        [
            "docker",
            "ps",
            "--all",
            "--filter",
            f"label=com.docker.compose.project={project_name}",
            "--format",
            "{{.Label \"com.docker.compose.project.working_dir\"}}",
        ],
        timeout=PROBE_TIMEOUT,
    )
    if proc.returncode != 0:
        return None
    for ligne in proc.stdout.splitlines():
        if ligne.strip():
            return ligne.strip()
    return None


def network_mode(container: str) -> str | None:
    """Mode reseau d'un conteneur, ou None s'il n'existe pas.

    Un client torrent protege renvoie `container:<id de gluetun>` : il partage
    la pile reseau du VPN et n'a aucune autre route. Un client expose renvoie
    le nom d'un reseau, `plugarr_plugarr`.
    """
    proc = _run(
        ["docker", "inspect", container, "--format", "{{.HostConfig.NetworkMode}}"],
        timeout=PROBE_TIMEOUT,
    )
    return proc.stdout.strip() or None if proc.returncode == 0 else None


def container_id(container: str) -> str | None:
    proc = _run(["docker", "inspect", container, "--format", "{{.Id}}"], timeout=PROBE_TIMEOUT)
    return proc.stdout.strip() or None if proc.returncode == 0 else None


def exec_in(container: str, commande: list[str], timeout: int = PROBE_TIMEOUT) -> tuple[bool, str]:
    """Execute une commande DANS un conteneur. Renvoie (succes, sortie)."""
    proc = _run(["docker", "exec", container, *commande], timeout=timeout)
    return proc.returncode == 0, (proc.stdout or proc.stderr).strip()


def volume_name(project_name: str, volume: str) -> str:
    """Nom REEL d'un volume nomme, tel que Docker Compose le cree.

    Compose prefixe par le nom du projet, en retirant tout ce qui n'est ni
    lettre, ni chiffre, ni tiret bas, ni tiret. Sans cette regle, on chercherait
    un volume qui n'existe pas et l'installation repartirait sur une base
    qu'elle croit neuve.
    """
    prefixe = re.sub(r"[^a-zA-Z0-9_-]", "", project_name)
    return f"{prefixe}_{volume}"


def volume_exists(name: str) -> bool:
    return _run(["docker", "volume", "inspect", name], timeout=PROBE_TIMEOUT).returncode == 0


def remove_volume(name: str) -> tuple[bool, str]:
    """Supprime un volume Docker. Destructeur : reserve a une remise a zero
    demandee explicitement."""
    proc = _run(["docker", "volume", "rm", name], timeout=PROBE_TIMEOUT)
    return proc.returncode == 0, (proc.stderr or proc.stdout).strip()


def check_port_free(port: int, label: str) -> Check:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        busy = sock.connect_ex(("127.0.0.1", port)) == 0
    return Check(
        f"port {port} ({label})",
        not busy,
        t("libre")
        if not busy
        else t(
            "deja utilise. Changez le port de {service} dans stack.yml.",
            service=label,
        ),
    )


def check_writable(path: str | Path, label: str) -> Check:
    """Peut-on REELLEMENT ecrire a cet endroit ? BLOQUANT.

    Le controle qui manquait, et son absence coutait cher. Le preflight ne
    testait que les hardlinks, en non bloquant : un chemin impossible a creer
    s'affichait en AVERTISSEMENT jaune, l'installation partait quand meme, et
    mourait sur sa toute premiere ecriture avec un errno nu :

        OSError : [Errno 30] Read-only file system: '/srv/data'

    Rien dans ce message ne dit quoi changer. Signale par un utilisateur macOS,
    dont la racine systeme est en lecture seule et pour qui `/srv` — le defaut
    de `generic-linux`, seul profil qu'on lui proposait — ne peut pas exister.

    On ne suppose rien, on essaie : `os.access` ment sur plus d'un montage.
    L'essai porte sur le premier ancetre EXISTANT, et ne laisse rien derriere
    lui — un preflight, a plus forte raison sous `--dry-run`, ne doit pas
    creer l'arborescence qu'il controle.
    """
    cible = Path(path).expanduser()
    ancetre = cible
    while not ancetre.exists() and ancetre != ancetre.parent:
        ancetre = ancetre.parent

    if not ancetre.is_dir():
        return Check(
            label,
            False,
            t(
                "{chemin} n'est pas dans un dossier : {obstacle} existe et n'en "
                "est pas un.",
                chemin=cible,
                obstacle=ancetre,
            ),
        )

    try:
        with tempfile.NamedTemporaryFile(dir=ancetre, prefix=".plugarr-ecriture-"):
            pass
    except OSError as exc:
        return Check(
            label,
            False,
            t(
                "impossible d'ecrire dans {obstacle} ({erreur}). Choisissez un "
                "autre emplacement : --data-root et --config-root, ou l'ecran "
                "des chemins dans l'assistant.",
                obstacle=ancetre,
                erreur=exc,
            ),
        )

    if ancetre == cible:
        return Check(label, True, t("existe et est inscriptible"))
    return Check(
        label,
        True,
        t("sera cree dans {parent}, qui est inscriptible", parent=ancetre),
    )


def check_hardlinks(data_root: str | Path) -> Check:
    ok, detail = hardlink_supported(data_root)
    # Non bloquant : la stack fonctionne sans hardlinks, elle est juste beaucoup
    # moins efficace. L'utilisateur doit le savoir, pas etre arrete.
    return Check("hardlinks /data", ok, detail, blocking=False)


def check_disk_space(path: str | Path, min_gb: int = 20) -> Check:
    try:
        usage = shutil.disk_usage(Path(path).anchor or str(path))
    except OSError as exc:
        return Check(
            t("espace disque"),
            False,
            t("impossible de lire {chemin} : {erreur}", chemin=path, erreur=exc),
            blocking=False,
        )
    free_gb = usage.free / 1024**3
    return Check(
        t("espace disque"),
        free_gb >= min_gb,
        t("{libres:.1f} Go libres", libres=free_gb)
        + (
            ""
            if free_gb >= min_gb
            else t(
                " - moins que le minimum conseille de {minimum} Go",
                minimum=min_gb,
            )
        ),
        blocking=False,
    )


# ---------------------------------------------------------------------- compose


class Compose:
    def __init__(self, project_dir: Path, project_name: str):
        self.dir = project_dir
        self.name = project_name

    def _cmd(self, *args: str) -> list[str]:
        return ["docker", "compose", "-p", self.name, *args]

    def up(self, timeout: int = 1800) -> tuple[bool, str]:
        proc = _run(self._cmd("up", "-d", "--remove-orphans"), cwd=self.dir, timeout=timeout)
        return proc.returncode == 0, (proc.stderr or proc.stdout).strip()

    def stop(self, timeout: int = 300) -> tuple[bool, str]:
        """Arrete les conteneurs du projet sans les supprimer.

        Sert avant un pre-semis : une application qui tourne garde sa
        configuration en memoire, et certaines la reecrivent en s'arretant.

        Renvoie (quelque_chose_a_ete_arrete, message). Un projet inexistant n'est
        pas une erreur : c'est le cas d'une premiere installation.
        """
        proc = _run(self._cmd("stop"), cwd=self.dir, timeout=timeout)
        sortie = (proc.stderr or "") + (proc.stdout or "")
        return proc.returncode == 0 and "Stopping" in sortie or "Stopped" in sortie, sortie.strip()

    def down(self, *, volumes: bool = False) -> tuple[bool, str]:
        args = ["down"] + (["-v"] if volumes else [])
        proc = _run(self._cmd(*args), cwd=self.dir)
        return proc.returncode == 0, (proc.stderr or proc.stdout).strip()

    def config_valid(self) -> tuple[bool, str]:
        proc = _run(self._cmd("config", "--quiet"), cwd=self.dir)
        return proc.returncode == 0, (proc.stderr or "compose valide").strip()

    def ps(self) -> str:
        return _run(self._cmd("ps"), cwd=self.dir).stdout

    def ps_json(self) -> list[dict]:
        """Etat de chaque service.

        Docker Compose 5.x emet un objet JSON PAR LIGNE ; les versions plus
        anciennes emettent un tableau unique. Les deux formes sont acceptees.
        """
        proc = _run(self._cmd("ps", "--all", "--format", "json"), cwd=self.dir)
        raw = (proc.stdout or "").strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            entries = []
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return entries
        return parsed if isinstance(parsed, list) else [parsed]

    def control(self, action: str, service: str) -> tuple[bool, str]:
        """Demarre, arrete ou redemarre UN service.

        `action` et `service` sont valides par l'appelant contre des listes
        fermees : ils finissent dans une ligne de commande.
        """
        if action not in ("start", "stop", "restart"):
            raise ValueError(f"action non autorisee: {action!r}")
        proc = _run(self._cmd(action, service), cwd=self.dir, timeout=180)
        return proc.returncode == 0, (proc.stderr or proc.stdout).strip()

    def pull(self, service: str, timeout: int = 900) -> tuple[bool, str]:
        proc = _run(self._cmd("pull", service), cwd=self.dir, timeout=timeout)
        return proc.returncode == 0, (proc.stderr or proc.stdout).strip()

    def recreate(self, service: str, timeout: int = 600) -> tuple[bool, str]:
        """Recree UN service avec son image a jour.

        `--no-deps` evite de toucher aux autres : mettre a jour Sonarr ne doit pas
        redemarrer le client de telechargement au passage.
        """
        proc = _run(
            self._cmd("up", "-d", "--no-deps", "--force-recreate", service),
            cwd=self.dir,
            timeout=timeout,
        )
        return proc.returncode == 0, (proc.stderr or proc.stdout).strip()

    def run_once(self, service: str, args: list[str], timeout: int = 600) -> tuple[bool, str]:
        """Lance une commande ponctuelle dans un service, sans le demarrer.

        `run --rm` cree un conteneur jetable a partir de la meme image et des
        memes volumes : Recyclarr peut generer sa configuration avant meme que le
        service planifie n'ait tourne.
        """
        proc = _run(
            self._cmd("run", "--rm", "--no-deps", service, *args), cwd=self.dir, timeout=timeout
        )
        return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")

    def logs(self, service: str, tail: int = 50) -> str:
        return _run(self._cmd("logs", "--tail", str(tail), service), cwd=self.dir).stdout
