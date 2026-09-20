"""Pilotage de docker compose et preflight."""

from __future__ import annotations

import json
import re
import secrets
import shutil
import socket
import subprocess
import time
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


#: Tentatives de `docker compose pull`, et attente de base entre deux (en
#: secondes, multipliee par le rang de la tentative).
PULL_TENTATIVES = 3
PULL_ATTENTE = 5


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


#: Unites de `docker stats`. La memoire est en binaire (MiB, GiB), mesure le
#: 2026-09-20 sur Docker 29.8.0 : « 16.79MiB / 4GiB ».
_UNITES = {"B": 1, "KB": 10**3, "KIB": 2**10, "MB": 10**6, "MIB": 2**20,
           "GB": 10**9, "GIB": 2**30, "TB": 10**12, "TIB": 2**40}


def _octets(texte: str) -> int | None:
    trouve = re.fullmatch(r"\s*([0-9.]+)\s*([A-Za-z]+)\s*", texte or "")
    if not trouve or trouve.group(2).upper() not in _UNITES:
        return None
    return int(float(trouve.group(1)) * _UNITES[trouve.group(2).upper()])


def stats_conteneurs(noms: list[str]) -> dict[str, dict]:
    """CPU et memoire de chaque conteneur nomme, par `docker stats`.

    Un seul appel pour tous : `docker stats` prend deux mesures espacees pour
    calculer le CPU, et le faire conteneur par conteneur couterait ce delai
    autant de fois. Un nom inconnu est simplement absent du resultat.
    """
    if not noms:
        return {}
    proc = _run(
        ["docker", "stats", "--no-stream", "--format", "json", *noms],
        # Deux mesures a prendre : plus long que les autres sondes.
        timeout=PROBE_TIMEOUT + 10,
    )
    if proc.returncode != 0:
        return {}
    releves: dict[str, dict] = {}
    for ligne in (proc.stdout or "").splitlines():
        try:
            d = json.loads(ligne)
        except json.JSONDecodeError:
            continue
        usage, _, limite = (d.get("MemUsage") or "").partition("/")
        pourcent = re.sub(r"%", "", d.get("CPUPerc") or "")
        releves[str(d.get("Name") or "")] = {
            "cpu_pct": float(pourcent) if re.fullmatch(r"[0-9.]+", pourcent) else None,
            "memoire": _octets(usage),
            "memoire_max": _octets(limite),
        }
    return releves


#: Champs releves par conteneur. Jamais `docker inspect` entier : il rend les
#: variables d'environnement RESOLUES, donc la cle privee WireGuard, les cles
#: API et les mots de passe que `.env` est cense garder.
_GABARIT_ETAT = (
    "{{.Name}}|{{.State.Status}}|{{.RestartCount}}|{{.State.OOMKilled}}"
    "|{{.State.ExitCode}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}"
)


def etats_conteneurs(noms: list[str]) -> dict[str, dict]:
    """Etat, redemarrages, kill OOM et sante de chaque conteneur nomme."""
    if not noms:
        return {}
    proc = _run(["docker", "inspect", "--format", _GABARIT_ETAT, *noms], timeout=PROBE_TIMEOUT)
    etats: dict[str, dict] = {}
    for ligne in (proc.stdout or "").splitlines():
        champs = ligne.strip().split("|")
        if len(champs) != 6:
            continue
        nom, statut, redemarrages, oom, code, sante = champs
        etats[nom.lstrip("/")] = {
            "statut": statut,
            "redemarrages": int(redemarrages) if redemarrages.isdigit() else 0,
            "oom": oom == "true",
            "code": int(code) if re.fullmatch(r"-?[0-9]+", code) else 0,
            "sante": "" if sante == "-" else sante,
        }
    return etats


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
    r"""Peut-on REELLEMENT ecrire a cet endroit ? BLOQUANT.

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

    L'essai se fait a la main, PAS avec `tempfile.NamedTemporaryFile`. Sous
    Windows, celui-ci RATTRAPE `PermissionError` et recommence — jusqu'a
    `tempfile.TMP_MAX`, soit dix mille fois — des lors que `os.access(dir,
    W_OK)` repond oui. Or c'est exactement ce qu'`os.access` repond pour
    `C:\`, ou l'ecriture est en realite refusee a un compte non eleve. Le
    controle ne rendait alors la main qu'apres plus de dix minutes, sans un
    mot, au lieu de dire tout de suite « impossible d'ecrire ».

    Le cas n'a rien d'exotique : `C:/plugarr/data`, le defaut du profil
    Windows, a pour premier ancetre existant la racine du disque tant que
    `C:\plugarr` n'existe pas — c'est-a-dire a la toute premiere installation.

    Et l'essai doit reproduire ce que PlugArr fera VRAIMENT. A la racine d'un
    disque Windows, un compte standard n'a pas le droit de creer un FICHIER
    mais a bien celui de creer un DOSSIER, puis d'ecrire dedans. Sonder par un
    fichier y repondait « impossible d'ecrire dans C:\ » et BLOQUAIT une
    installation parfaitement realisable — celle des chemins proposes par
    defaut. Quand la cible n'existe pas encore, on cree donc un dossier, on
    ecrit dedans, et on retire les deux.
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

    essai = ancetre / f".plugarr-ecriture-{secrets.token_hex(8)}"
    try:
        if ancetre == cible:
            # La cible existe : PlugArr y ecrira des fichiers.
            try:
                with essai.open("xb"):
                    pass
            finally:
                essai.unlink(missing_ok=True)
        else:
            # PlugArr creera l'arborescence : on essaie un dossier, puis un
            # fichier DEDANS, ce qui est exactement la suite d'operations reelle.
            essai.mkdir()
            try:
                fichier = essai / "essai"
                with fichier.open("xb"):
                    pass
                fichier.unlink(missing_ok=True)
            finally:
                essai.rmdir()
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
        # La sortie de Docker n'est pas une API : elle peut changer de langue
        # ou de forme. On releve donc les conteneurs en marche AVANT l'arret,
        # au lieu de chercher les mots anglais "Stopping" / "Stopped" pour
        # decider s'il faudra les relancer apres une sauvegarde.
        running = _run(self._cmd("ps", "-q"), cwd=self.dir, timeout=PROBE_TIMEOUT)
        proc = _run(self._cmd("stop"), cwd=self.dir, timeout=timeout)
        sortie = (proc.stderr or "") + (proc.stdout or "")
        if proc.returncode != 0:
            raise OSError(sortie.strip() or t("docker compose stop a echoue"))
        if running.returncode == 0:
            return bool((running.stdout or "").strip()), sortie.strip()
        return "Stopping" in sortie or "Stopped" in sortie, sortie.strip()

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
        if proc.returncode != 0:
            raise OSError((proc.stderr or proc.stdout or "docker compose ps a echoue").strip())
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

    def pull_many(self, services: list[str], timeout: int = 1800) -> tuple[bool, str]:
        """Telecharge en parallele toutes les images de l'installation.

        `docker compose up` sait le faire implicitement, mais melange alors le
        telechargement, la creation et le demarrage dans une seule attente
        opaque. Une commande separee permet aux interfaces d'annoncer la phase
        exacte sans ralentir le telechargement par un `pull` sequentiel.
        """
        # Un registre coupe parfois la connexion en plein telechargement :
        # « read: connection reset by peer » chez lscr.io, releve sur un runner
        # GitHub. Sans nouvelle tentative, UNE coupure faisait echouer toute
        # l'installation. `pull` est idempotent — les couches deja recuperees ne
        # se retelechargent pas — donc reessayer ne coute que le temps d'attente,
        # et une erreur definitive (tag inconnu) echoue simplement trois fois.
        tentatives = PULL_TENTATIVES
        for tentative in range(1, tentatives + 1):
            proc = _run(self._cmd("pull", *services), cwd=self.dir, timeout=timeout)
            if proc.returncode == 0:
                return True, (proc.stderr or proc.stdout).strip()
            if tentative < tentatives:
                time.sleep(PULL_ATTENTE * tentative)
        return False, (proc.stderr or proc.stdout).strip()

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
