"""Detection des mises a jour disponibles.

Deux choses differentes s'appellent « mise a jour », et les confondre rendrait
l'information inutile :

- **une reconstruction** : meme tag, nouveau contenu. LinuxServer republie ses
  images tres souvent, pour les correctifs de securite de l'image de base. Elle se
  detecte en comparant le digest local au digest distant du MEME tag, et se
  corrige par un `pull` suivi d'un `up -d` ;
- **une nouvelle version** : un tag plus recent existe en amont. Elle demande de
  changer le tag deploye, donc de reecrire `stack.yml`.

Les deux sont proposees separement, avec leur numero de version, parce qu'elles
n'ont pas les memes consequences.

Le listage des tags passe par le protocole registry v2 generique — challenge 401,
jeton, nouvelle tentative — et non par du code specifique a chaque registre.
Verifie sur lscr.io, ghcr.io et Docker Hub.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field

import httpx

from . import catalog, imageref
from .i18n import t
from .models import StackConfig

#: Qualificatifs qui designent une image instable. Un tag qui en contient un
#: n'est jamais propose comme mise a jour, sauf si le tag deploye en contient
#: deja un : quelqu'un qui suit `develop` le fait expres.
_UNSTABLE = ("develop", "nightly", "beta", "alpha", "rc", "master", "latest", "edge", "test")

_VERSION = re.compile(r"^v?(\d+(?:\.\d+)*)$")
_BUILD = re.compile(r"^build-(\d+)$")
#: Tags LinuxServer quand ils portent leur base et leur construction :
#: `12.1ubu2604-ls50`. Releve le 26/09/2026 : Jellyfin 12 n'est publie par
#: LinuxServer QUE sous cette forme, sans tag `12.1` nu.
_LSIO = re.compile(r"^(\d+(?:\.\d+)*)ubu\d+-ls(\d+)$")


@dataclass
class UpdateInfo:
    service: str
    image: str
    current_tag: str
    #: Le meme tag a ete republie avec un contenu different.
    rebuilt: bool = False
    #: Version plus recente disponible, si une existe.
    latest_tag: str | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def has_update(self) -> bool:
        return self.rebuilt or self.latest_tag is not None


def parse_version(tag: str) -> tuple[int, ...] | None:
    """Convertit un tag en tuple comparable, ou None s'il n'est pas une version.

    Accepte `4.0.19`, `v1.85.0` et les constructions monotones de Silo comme
    `build-522`. Refuse `version-3.0.4.999`, `latest`, `4.0.19-develop` :
    comparer des formes differentes n'a pas de sens.
    """
    propre = tag.strip()
    build = _BUILD.match(propre)
    if build is not None:
        return (int(build.group(1)),)
    lsio = _LSIO.match(propre)
    if lsio is not None:
        # Version completee a quatre rangs AVANT le numero de construction :
        # sans cela `12.1.1ubu2604-ls52` passerait derriere `12.1ubu2604-ls50`.
        version = [int(part) for part in lsio.group(1).split(".")]
        return (*version, *[0] * (4 - len(version)), int(lsio.group(2)))
    match = _VERSION.match(propre)
    if match is None:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _same_shape(candidate: str, current: str) -> bool:
    """Le candidat suit-il la meme convention que le tag deploye ?

    Un depot melange `v1.85.0`, `1.85`, `version-1.85.0` et `latest`. Comparer
    entre conventions produirait des propositions absurdes.
    """
    candidate_build = _BUILD.fullmatch(candidate) is not None
    current_build = _BUILD.fullmatch(current) is not None
    if candidate_build or current_build:
        return candidate_build and current_build
    candidate_lsio = _LSIO.fullmatch(candidate) is not None
    current_lsio = _LSIO.fullmatch(current) is not None
    if candidate_lsio or current_lsio:
        return candidate_lsio and current_lsio
    if candidate.startswith("v") != current.startswith("v"):
        return False
    return candidate.count(".") == current.count(".")


def newer_tags(image: str, *, timeout: float = 15.0) -> tuple[list[str], str | None]:
    """Tags plus recents que celui deploye. Renvoie (tags_tries, probleme)."""
    ref = imageref.parse(image)
    reference, current_tag = ref.repository, ref.tag
    current = parse_version(current_tag)
    if current is None:
        # Sans tag lisible, il n'y a rien a comparer. C'est le cas d'une image
        # epinglee par digest seul. Le controle de reconstruction, lui, continue
        # de valoir. Silo porte desormais un tag `build-N`, traite plus haut.
        manque = (
            t("aucun tag")
            if not current_tag
            else t("le tag deploye ({tag})", tag=current_tag)
        )
        return [], t("{quoi} n'est pas une version comparable", quoi=manque)

    tags, problem = list_tags(reference, timeout=timeout)
    if problem:
        return [], problem

    unstable_ok = any(bad in current_tag.lower() for bad in _UNSTABLE)
    candidates = []
    for tag in tags:
        if not _same_shape(tag, current_tag):
            continue
        if not unstable_ok and any(bad in tag.lower() for bad in _UNSTABLE):
            continue
        parsed = parse_version(tag)
        if parsed is not None and parsed > current:
            candidates.append((parsed, tag))
    return [tag for _v, tag in sorted(candidates)], None


#: Depots dont le contenu est identique a celui de Docker Hub. Verifie par
#: comparaison de digests : `lscr.io/linuxserver/sonarr:4.0.19` et
#: `linuxserver/sonarr:4.0.19` renvoient le meme sha256. Cela autorise a utiliser
#: l'API du Hub, qui sait trier par date de publication.
_HUB_MIRRORS = {"lscr.io": "hub.docker.com", "docker.io": "hub.docker.com"}


def list_tags(reference: str, *, timeout: float) -> tuple[list[str], str | None]:
    """Tags d'un depot, par la voie la plus economique disponible.

    Le protocole registry v2 renvoie les tags dans l'ordre de PUBLICATION, donc
    les plus anciens d'abord, par pages de 200. LinuxServer publie des milliers de
    tags par image : constate en conditions reelles, 25 pages et 6 secondes ne
    suffisaient meme pas a atteindre la version courante de Sonarr.

    Quand le depot est aussi sur Docker Hub, son API accepte
    `ordering=last_updated` et donne les plus RECENTS d'abord : une seule page
    suffit. Sinon on retombe sur le protocole generique, qui convient aux depots
    de taille normale (ghcr.io par exemple).
    """
    host = reference.split("/")[0] if "." in reference.split("/")[0] else "docker.io"
    if host in _HUB_MIRRORS:
        tags, problem = _hub_tags(reference, host, timeout=timeout)
        if not problem:
            return tags, None
        # Le Hub a echoue : on tente quand meme la voie generique.
    return _list_tags(reference, timeout=timeout)


def _hub_tags(reference: str, host: str, *, timeout: float) -> tuple[list[str], str | None]:
    repo = reference.split("/", 1)[1] if host != "docker.io" else reference
    if "/" not in repo:
        repo = f"library/{repo}"
    url = f"https://hub.docker.com/v2/repositories/{repo}/tags"
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, params={"page_size": 100, "ordering": "last_updated"})
            if resp.status_code != 200:
                return [], f"Docker Hub a repondu HTTP {resp.status_code}"
            return [r["name"] for r in resp.json().get("results", []) if r.get("name")], None
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        return [], f"Docker Hub injoignable : {exc}"


#: Nombre maximum de pages suivies. LinuxServer publie des milliers de tags par
#: image ; sans borne, un controle pourrait tourner tres longtemps.
MAX_PAGES = 25


def _list_tags(reference: str, *, timeout: float) -> tuple[list[str], str | None]:
    """Protocole registry v2 generique, pagination comprise.

    Un registre repond 401 avec un en-tete `WWW-Authenticate` decrivant ou
    obtenir un jeton. On le suit, plutot que d'ecrire un cas par registre.

    La pagination n'est pas un detail : le registre renvoie les tags dans l'ordre
    de publication, donc les PLUS ANCIENS d'abord. Constate en conditions
    reelles — une premiere version sans pagination ne voyait que des tags de
    Sonarr 2.x et 3.x, et ratait completement le 4.0.19 disponible. On suit donc
    l'en-tete `Link` jusqu'a epuisement.
    """
    if "/" not in reference or "." not in reference.split("/")[0]:
        host = "registry-1.docker.io"
        repo = reference if "/" in reference else f"library/{reference}"
    else:
        host, repo = reference.split("/", 1)

    base = f"https://{host}"
    path = f"/v2/{repo}/tags/list?n=200"
    collected: list[str] = []
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            headers: dict[str, str] = {}
            for _page in range(MAX_PAGES):
                resp = client.get(base + path, headers=headers)
                if resp.status_code == 401 and "Authorization" not in headers:
                    token = _bearer_token(
                        client, resp.headers.get("www-authenticate", ""), repo
                    )
                    if token is None:
                        return [], t("le registre demande une authentification non geree")
                    headers["Authorization"] = f"Bearer {token}"
                    continue
                if resp.status_code != 200:
                    return [], t(
                        "le registre a repondu HTTP {code}", code=resp.status_code
                    )
                collected += list(resp.json().get("tags") or [])
                nxt = _next_page(resp.headers.get("link", ""))
                if not nxt:
                    return collected, None
                path = nxt
            return collected, f"listage interrompu apres {MAX_PAGES} pages"
    except (httpx.HTTPError, ValueError) as exc:
        return [], f"registre injoignable : {exc}"


def _next_page(link_header: str) -> str | None:
    """Extrait l'URL suivante d'un en-tete `Link` de registre."""
    match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
    return match.group(1) if match else None


def _bearer_token(client: httpx.Client, challenge: str, repo: str) -> str | None:
    realm = re.search(r'realm="([^"]+)"', challenge)
    if not realm:
        return None
    params = {"scope": f"repository:{repo}:pull"}
    service = re.search(r'service="([^"]+)"', challenge)
    if service:
        params["service"] = service.group(1)
    try:
        return client.get(realm.group(1), params=params).json().get("token")
    except (httpx.HTTPError, ValueError):
        return None


# ------------------------------------------------------------------- digests


def _docker(*args: str, timeout: int = 60) -> tuple[int, str]:
    proc = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def local_digest(image: str) -> str | None:
    code, out = _docker("image", "inspect", image, "--format", "{{index .RepoDigests 0}}")
    if code != 0 or "@" not in out:
        return None
    return out.strip().split("@", 1)[1]


def remote_digest(image: str) -> str | None:
    """Digest publie, sans telecharger l'image.

    `buildx imagetools inspect` est livre avec Docker et fonctionne sur tous les
    registres testes, la ou `docker manifest inspect` a longtemps demande le mode
    experimental.
    """
    code, out = _docker("buildx", "imagetools", "inspect", image)
    match = re.search(r"Digest:\s+(sha256:[0-9a-f]+)", out) if code == 0 else None
    if match:
        return match.group(1)
    # Console reelle du 25/09/2026 : ni son image ni le VPS n'avaient `buildx`,
    # et chaque image epinglee par tag affichait « verification incomplete ».
    # Le registre donne le meme condensat par une simple requete HTTP.
    return _registry_digest(image)


#: Ce que `buildx imagetools` compare : l'index multi-architecture s'il existe,
#: sinon le manifeste simple. `RepoDigests` retient le meme condensat au pull.
_MANIFEST_TYPES = (
    "application/vnd.oci.image.index.v1+json, "
    "application/vnd.docker.distribution.manifest.list.v2+json, "
    "application/vnd.oci.image.manifest.v1+json, "
    "application/vnd.docker.distribution.manifest.v2+json"
)


def _registry_digest(image: str, *, timeout: float = 15.0) -> str | None:
    ref = imageref.parse(image)
    reference = ref.repository
    if "/" not in reference or "." not in reference.split("/")[0]:
        host = "registry-1.docker.io"
        repo = reference if "/" in reference else f"library/{reference}"
    else:
        host, repo = reference.split("/", 1)
    url = f"https://{host}/v2/{repo}/manifests/{ref.tag or 'latest'}"
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            headers = {"Accept": _MANIFEST_TYPES}
            resp = client.head(url, headers=headers)
            if resp.status_code == 401:
                token = _bearer_token(client, resp.headers.get("www-authenticate", ""), repo)
                if token is None:
                    return None
                headers["Authorization"] = f"Bearer {token}"
                resp = client.head(url, headers=headers)
            if resp.status_code != 200:
                return None
            digest = resp.headers.get("docker-content-digest", "")
            return digest if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) else None
    except httpx.HTTPError:
        return None


# -------------------------------------------------------------------- controle


def check_service(image: str, *, check_tags: bool = True) -> UpdateInfo:
    ref = imageref.parse(image)
    info = UpdateInfo(service="", image=image, current_tag=ref.tag)

    if ref.pinned:
        # Une reference epinglee par digest ne peut PAS etre reconstruite : le
        # condensat designe un contenu, pas un nom. Comparer local et distant
        # reviendrait a comparer une chose a elle-meme. Sans cette sortie, la
        # page affichait « image reconstruite » sur une image immuable.
        if check_tags:
            newer, probleme = newer_tags(image)
            if probleme:
                info.problems.append(probleme)
            elif newer:
                info.latest_tag = newer[-1]
        return info

    here, there = local_digest(image), remote_digest(image)
    if here is None:
        info.problems.append("image absente localement : rien a comparer")
    elif there is None:
        info.problems.append("digest distant illisible : registre injoignable ?")
    else:
        info.rebuilt = here != there

    if check_tags:
        newer, problem = newer_tags(image)
        if problem:
            info.problems.append(problem)
        elif newer:
            info.latest_tag = newer[-1]
    return info


def check(cfg: StackConfig, *, check_tags: bool = True) -> list[UpdateInfo]:
    """Controle chaque service selectionne. Aucune ecriture, aucun telechargement."""
    results: list[UpdateInfo] = []
    for sid in catalog.STARTUP_ORDER:
        if not cfg.enabled(sid):
            continue
        inst = cfg.services[sid]
        if inst.adopted:
            # Les conteneurs adoptes ne nous appartiennent pas : proposer de les
            # mettre a jour reviendrait a recreer la stack de quelqu'un d'autre.
            continue
        info = check_service(inst.image or catalog.get(sid).image, check_tags=check_tags)
        info.service = sid
        results.append(info)
    return results


def disponibles(cfg) -> dict:
    """Versions plus recentes que celles installees, application par application.

    Commun a l'assistant web et au TUI : PlugArr installe les versions qu'il a
    testees, puis dit ce qui existe de plus recent. Rien n'est change ici.
    """
    from concurrent.futures import ThreadPoolExecutor

    from . import catalog, orchestrator

    cibles = [
        (sid, catalog.get(sid).display_name, inst.image or catalog.get(sid).image)
        for sid, inst in orchestrator.iter_selected(cfg)
        if (inst.image or catalog.get(sid).image) and not inst.adopted
    ]

    def verifier(cible):
        sid, nom, image = cible
        try:
            recentes, probleme = newer_tags(image, timeout=10.0)
        except Exception as exc:  # noqa: BLE001 - un registre ne doit pas casser le rapport
            recentes, probleme = [], str(exc)
        return sid, nom, image, recentes, probleme

    with ThreadPoolExecutor(max_workers=8) as pool:
        resultats = list(pool.map(verifier, cibles))
    return {
        "updates": [
            {"id": sid, "name": nom, "current": imageref.parse(image).tag, "latest": recentes[-1]}
            for sid, nom, image, recentes, probleme in resultats
            if recentes and not probleme
        ],
        "unchecked": [nom for _sid, nom, _image, _recentes, probleme in resultats if probleme],
    }

