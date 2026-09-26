"""Detection d'une stack deja installee.

La plupart des gens qui installent une stack media en ont deja une, montee a la
main et cablee a moitie. Leur demander de tout refaire n'a aucun sens : il vaut
mieux reprendre ce qui tourne et le cabler.

Le principe est le meme que pour une installation neuve — on ne devine rien. La
cle API est lue dans le `config.xml` du conteneur, pas demandee ni inventee.

Une difference majeure avec `install` : les services adoptes n'appartiennent pas
au meme reseau Docker. `http://sonarr:8989` ne resout pas d'un reseau a l'autre.
Le cablage doit donc passer par l'adresse de l'HOTE et le port publie, ce que
`ServiceInstance.wiring_url` exprime.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from . import catalog
from .i18n import t
from .seed import read_api_key

#: Fragment d'image permettant de reconnaitre un service. Volontairement large :
#: on rencontre lscr.io/linuxserver/sonarr, hotio/sonarr, ghcr.io/.../sonarr...
_IMAGE_HINTS = {
    "sonarr": ("sonarr",),
    "radarr": ("radarr",),
    "lidarr": ("lidarr",),
    "prowlarr": ("prowlarr",),
    "qbittorrent": ("qbittorrent",),
    "transmission": ("transmission",),
    "jellyfin": ("jellyfin",),
}

#: Images a NE PAS confondre : "sonarr-anime" contient "sonarr", mais aussi
#: "prowlarr" contient "arr". On exige une correspondance sur le nom d'image seul.
_EXCLUDE = ("exportarr", "buildarr", "recyclarr", "configarr", "unpackerr")


@dataclass
class Found:
    """Un service detecte sur la machine."""

    service_id: str
    container: str
    image: str
    host_port: int | None
    config_dir: str | None = None
    api_key: str | None = None
    url_base: str = ""
    #: Bind mounts relevant to media paths; destination -> host source.
    data_mounts: dict[str, str] = field(default_factory=dict)
    #: Docker network namespace owner, when NetworkMode is container:<id/name>.
    network_owner: str | None = None
    #: True quand le conteneur porte le marqueur pose par plugarr.
    managed_by_us: bool = False
    problems: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """Utilisable pour le cablage : il faut un port ET, pour les *arr, une cle."""
        if self.host_port is None:
            return False
        if catalog.get(self.service_id).api_family == "arr":
            return bool(self.api_key)
        return True


def _docker(*args: str, timeout: int = 30) -> str:
    proc = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
    )
    return proc.stdout if proc.returncode == 0 else ""


def identify(image: str) -> str | None:
    """Quel service correspond a cette image ?

    On compare sur le DERNIER segment du nom, sans le tag : `lscr.io/linuxserver/
    sonarr:4.0.19` donne `sonarr`. Comparer sur la chaine entiere ferait passer
    `exportarr` pour un *arr.
    """
    name = image.rsplit("/", 1)[-1].split(":")[0].lower()
    if any(bad in name for bad in _EXCLUDE):
        return None
    for service_id, hints in _IMAGE_HINTS.items():
        if any(name == hint or name.startswith(f"{hint}-") for hint in hints):
            return service_id
    return None


def _published_port(container: dict, internal_port: int) -> int | None:
    """Port de l'hote correspondant au port interne du service."""
    ports = (container.get("NetworkSettings") or {}).get("Ports") or {}
    for spec, bindings in ports.items():
        if not bindings:
            continue
        if spec.startswith(f"{internal_port}/"):
            try:
                return int(bindings[0].get("HostPort"))
            except (TypeError, ValueError):
                continue
    return None


def _qbittorrent_webui_port(config_dir: str | None, default: int) -> int:
    """Read the actual WebUI port without exposing the rest of qBittorrent.conf."""
    if not config_dir:
        return default
    path = Path(config_dir) / "qBittorrent" / "qBittorrent.conf"
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for _, line in zip(range(4096), handle, strict=False):
                if not line.startswith(r"WebUI\Port="):
                    continue
                port = int(line.partition("=")[2].strip())
                return port if 1 <= port <= 65535 else default
    except (OSError, ValueError):
        pass
    return default


def _network_owner(container: dict, containers: list[dict]) -> dict | None:
    """Find the container publishing ports for a shared network namespace."""
    mode = str((container.get("HostConfig") or {}).get("NetworkMode") or "")
    if not mode.startswith("container:"):
        return None
    reference = mode.partition(":")[2].lstrip("/")
    if not reference:
        return None
    matches = [
        candidate for candidate in containers
        if candidate is not container and (
            str(candidate.get("Id") or "").startswith(reference)
            or str(candidate.get("Name") or "").lstrip("/") == reference
        )
    ]
    return matches[0] if len(matches) == 1 else None


def _config_mount(container: dict) -> str | None:
    for mount in container.get("Mounts") or []:
        if mount.get("Destination") == "/config":
            return mount.get("Source")
    return None


def _data_mounts(container: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for mount in container.get("Mounts") or []:
        destination = str(mount.get("Destination") or "")
        source = str(mount.get("Source") or "")
        if destination in ("/data", "/downloads", "/media") and source:
            result[destination] = source
    return result


def _read_url_base(config_xml: Path) -> str:
    """Un `UrlBase` non vide change toutes les URL du service : sans lui, le
    cablage viserait la racine et echouerait."""
    try:
        node = ET.fromstring(config_xml.read_text(encoding="utf-8")).find("UrlBase")
    except (OSError, ET.ParseError):
        return ""
    return (node.text or "").strip("/") if node is not None and node.text else ""


def scan(*, include_stopped: bool = False) -> list[Found]:
    """Parcourt les conteneurs de la machine et reconnait les services connus.

    N'ecrit rien, ne demarre rien, ne touche a rien.
    """
    args = ["ps", "--format", "{{.ID}}"]
    if include_stopped:
        args.insert(1, "--all")
    ids = [line.strip() for line in _docker(*args).splitlines() if line.strip()]
    if not ids:
        return []

    raw = _docker("inspect", *ids, timeout=60)
    try:
        containers = json.loads(raw) if raw.strip() else []
    except json.JSONDecodeError:
        return []

    found: list[Found] = []
    for container in containers:
        image = ((container.get("Config") or {}).get("Image")) or ""
        service_id = identify(image)
        if service_id is None:
            continue
        spec = catalog.get(service_id)
        name = str(container.get("Name", "")).lstrip("/")

        config_dir = _config_mount(container)
        internal_port = (
            _qbittorrent_webui_port(config_dir, spec.internal_port)
            if service_id == "qbittorrent" else spec.internal_port
        )
        host_port = _published_port(container, internal_port)
        owner = _network_owner(container, containers)
        if host_port is None and owner is not None:
            host_port = _published_port(owner, internal_port)

        entry = Found(
            service_id=service_id,
            container=name,
            image=image,
            host_port=host_port,
            config_dir=config_dir,
            data_mounts=_data_mounts(container),
            network_owner=(str(owner.get("Name") or "").lstrip("/") or None)
            if owner is not None else None,
            managed_by_us=_pose_par_nous(container),
        )
        if entry.host_port is None:
            entry.problems.append(
                t(
                    "aucun port de l'hote ne publie {port} : plugarr ne pourra "
                    "pas le joindre",
                    port=internal_port,
                )
            )
        if spec.api_family == "arr":
            _fill_arr_credentials(entry)
        found.append(entry)

    found.sort(key=lambda f: (catalog.STARTUP_ORDER.index(f.service_id), f.container))
    return found


def _fill_arr_credentials(entry: Found) -> None:
    if not entry.config_dir:
        entry.problems.append(
            t(
                "le volume /config n'est pas monte depuis l'hote : impossible de "
                "lire la cle API"
            )
        )
        return
    config_xml = Path(entry.config_dir) / "config.xml"
    if not config_xml.exists():
        entry.problems.append(
            t("{chemin} introuvable depuis cette machine", chemin=config_xml)
        )
        return
    key = read_api_key(config_xml)
    if not key:
        entry.problems.append(t("aucune cle API dans {chemin}", chemin=config_xml))
        return
    entry.api_key = key
    entry.url_base = _read_url_base(config_xml)


def duplicates(found: list[Found]) -> dict[str, list[Found]]:
    """Services detectes plusieurs fois.

    Cas courant et legitime : deux Sonarr, l'un pour les series, l'autre pour
    l'animation. plugarr ne peut pas deviner lequel cabler, il doit demander.
    """
    by_service: dict[str, list[Found]] = {}
    for entry in found:
        by_service.setdefault(entry.service_id, []).append(entry)
    return {sid: items for sid, items in by_service.items() if len(items) > 1}


def mask_key(key: str | None) -> str:
    if not key:
        return "-"
    return f"{key[:4]}…{key[-4:]}"


#: Marqueurs poses sur les conteneurs, du plus recent au plus ancien.
#:
#: `arrsenal.managed` est l'ancien nom du projet. Les piles installees avant le
#: renommage le portent encore, et elles tournent : ne lire que le nouveau les
#: rendrait invisibles a `scan` et a `adopt`, sans un mot. Une installation
#: qu'un outil ne voit plus est une installation qu'il proposera de recreer
#: par-dessus.
MARQUEURS = ("plugarr.managed", "arrsenal.managed")


def _pose_par_nous(container: dict) -> bool:
    labels = (container.get("Config") or {}).get("Labels") or {}
    return any(labels.get(m) == "true" for m in MARQUEURS)


def looks_like_plugarr(entry: Found) -> bool:
    """Ce conteneur vient-il de plugarr ?

    On lit les marqueurs poses a la generation, jamais le nom. L'ancien,
    `arrsenal.managed`, compte toujours : les piles installees avant le
    renommage tournent encore.
    Une heuristique de nom produisait des faux positifs sur des noms parfaitement
    legitimes — `mon-sonarr`, `media-sonarr` — et sautait donc en silence des
    conteneurs qui n'appartiennent pas a plugarr.
    """
    return entry.managed_by_us
