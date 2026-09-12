"""Configuration de Recyclarr.

Recyclarr synchronise les profils de qualite et les custom formats des TRaSH
Guides vers Sonarr et Radarr. plugarr ne reimplemente rien : il demande a
Recyclarr de generer sa configuration a partir d'un template OFFICIEL, puis se
contente d'y ecrire l'adresse et la cle API. La repartition est nette — TRaSH
fournit les profils, plugarr fournit le cablage.

Trois choses relevees sur l'image 8.7.1, aucune devinable :

- `config create --template X` ignore `--path` et ecrit `/config/configs/X.yml`,
  un fichier par template. Recyclarr charge ensuite tout ce dossier ;
- les templates arrivent avec des marqueurs en clair : `base_url: Put your Sonarr
  URL here` et `api_key: Put your API key here`. Ce sont eux qu'on remplace ;
- le conteneur n'a pas d'interface web. Il tourne sur une planification,
  `CRON_SCHEDULE=@daily` par defaut.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..i18n import t

#: Marqueurs poses par les templates officiels. Les remplacer est tout ce
#: que plugarr a a faire.
#:
#: On borne l'espace a l'espace HORIZONTAL. `\s` matche aussi le retour a la
#: ligne : un `\s*$` gourmand avale les lignes vides qui suivent le marqueur et
#: reformate le fichier des TRaSH Guides au passage, ce que ce module s'interdit.
_HSPACE = r"[^\S\n]*"
_URL_MARKER = re.compile(
    rf"^({_HSPACE}base_url:{_HSPACE}).*Put your .* URL here{_HSPACE}$", re.MULTILINE
)
_KEY_MARKER = re.compile(
    rf"^({_HSPACE}api_key:{_HSPACE}).*Put your API key here{_HSPACE}$", re.MULTILINE
)

#: Templates par defaut. Choisis parce qu'ils sont les points de depart les plus
#: courants des TRaSH Guides, pas parce qu'ils conviendraient a tout le monde :
#: le materiel et la bande passante decident, et l'utilisateur peut en changer.
DEFAULT_TEMPLATES = {"sonarr": "web-1080p", "radarr": "hd-bluray-web"}


@dataclass
class Filled:
    path: Path
    service: str
    url_written: bool
    key_written: bool

    @property
    def ok(self) -> bool:
        return self.url_written and self.key_written


#: Manifeste des templates racine, dans le depot clone par Recyclarr.
#:
#: C'est LUI qui fait foi, pas le contenu du dossier `templates/`. Un nom de
#: fichier n'est pas un identifiant : `sonarr/templates/german-hd-bluray-web.yml`
#: s'appelle `sonarr-german-hd-bluray-web` pour `config create`, parce que Radarr
#: a un fichier du meme nom. 11 templates sur 22 sont dans ce cas de chaque cote,
#: et Radarr en range 10 de plus dans un sous-dossier `sqp/` qu'un simple glob ne
#: voit pas. Lister les fichiers proposerait donc des noms que Recyclarr refuse.
MANIFEST_PATH = Path("resources/config-templates/git/official/templates.json")

#: Le meme manifeste, servi par GitHub. Verifie : le contenu est IDENTIQUE octet
#: pour octet a celui que Recyclarr clone. Cela permet de proposer la liste dans
#: l'assistant en une fraction de seconde, sans avoir a telecharger l'image ni a
#: attendre le premier demarrage du conteneur (une minute, mesuree).
MANIFEST_URL = "https://raw.githubusercontent.com/recyclarr/config-templates/master/templates.json"


def parse_manifest(payload: str | bytes) -> dict[str, list[str]]:
    """Identifiants des templates racine, par service.

    Renvoie un dictionnaire vide plutot que de lever : un manifeste illisible doit
    degrader l'assistant, pas l'interrompre.
    """
    try:
        data = json.loads(payload)
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    names: dict[str, list[str]] = {}
    for service, entries in data.items():
        if not isinstance(entries, list):
            continue
        ids = [
            entry["id"]
            for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        ]
        if ids:
            names[service] = sorted(ids)
    return names


def bundled_manifest() -> dict[str, list[str]]:
    """Complete official catalog shipped with the offline demo (see source JSON)."""
    return parse_manifest((Path(__file__).parents[1] / 'data' / 'recyclarr_templates.json').read_bytes())


def local_manifest(config_dir: Path) -> dict[str, list[str]]:
    """Manifeste clone par Recyclarr, s'il a deja tourne. Vide sinon."""
    try:
        return parse_manifest((config_dir / MANIFEST_PATH).read_bytes())
    except OSError:
        return {}


def fetch_manifest(*, timeout: float = 10.0) -> tuple[dict[str, list[str]], str | None]:
    """Manifeste distant. Renvoie (templates, probleme)."""
    try:
        response = httpx.get(MANIFEST_URL, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as exc:
        return {}, t("depot des templates injoignable : {erreur}", erreur=exc)
    if response.status_code != 200:
        return {}, t(
            "le depot des templates a repondu HTTP {code}", code=response.status_code
        )
    names = parse_manifest(response.content)
    return names, None if names else t("manifeste des templates illisible")


def available_templates(
    config_dir: Path | None = None, *, timeout: float = 10.0
) -> tuple[dict[str, list[str]], str | None]:
    """Templates proposables, disque d'abord, reseau ensuite.

    Le disque fait foi quand Recyclarr a deja tourne : c'est exactement ce que
    cette installation-la connait. Sinon on interroge le depot, ce qui evite
    d'imposer un telechargement d'image avant meme le recapitulatif.
    """
    if config_dir is not None:
        local = local_manifest(config_dir)
        if local:
            return local, None
    return fetch_manifest(timeout=timeout)


def template_names(config_dir: Path, service: str) -> list[str]:
    """Templates presents sur disque pour un service. Vide si Recyclarr n'a pas
    encore tourne."""
    return local_manifest(config_dir).get(service, [])


def fill(config_file: Path, base_url: str, api_key: str, service: str) -> Filled:
    """Ecrit l'adresse et la cle dans un fichier genere par Recyclarr.

    On remplace les marqueurs, on ne reecrit pas le fichier : tout le reste vient
    des TRaSH Guides et doit rester intact.
    """
    text = config_file.read_text(encoding="utf-8")
    # Le remplacement passe par une fonction, pas par une chaine : dans une chaine
    # de remplacement, re interprete les antislashs. Une url_base saisie a la main
    # avec un antislash ferait lever « bad escape » au lieu d'ecrire le fichier.
    text, url_count = _URL_MARKER.subn(lambda m: m.group(1) + base_url, text)
    text, key_count = _KEY_MARKER.subn(lambda m: m.group(1) + api_key, text)
    if url_count or key_count:
        config_file.write_text(text, encoding="utf-8")
    return Filled(
        path=config_file,
        service=service,
        url_written=bool(url_count),
        key_written=bool(key_count),
    )


def target_service(config_file: Path) -> str | None:
    """Quel service ce fichier configure-t-il ?

    Le template le declare a la racine du YAML : `sonarr:` ou `radarr:`. On le lit
    plutot que de se fier au nom du fichier, qui n'est qu'un titre de template.
    """
    try:
        for line in config_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith(("sonarr:", "radarr:")):
                return stripped.rstrip(":").strip()
    except OSError:
        return None
    return None


def pending_markers(config_dir: Path) -> list[Path]:
    """Fichiers ou un marqueur n'a pas ete remplace.

    Un marqueur oublie fait echouer la synchronisation avec un message obscur :
    mieux vaut le detecter avant.
    """
    configs = config_dir / "configs"
    if not configs.is_dir():
        return []
    return [
        path
        for path in sorted(configs.glob("*.yml"))
        if "Put your" in path.read_text(encoding="utf-8")
    ]


#: Suffixe donne aux fichiers ecartes. On ne SUPPRIME pas : le fichier a pu etre
#: modifie a la main, et Recyclarr ignore tout ce qui ne finit pas par `.yml`.
DISABLED_SUFFIX = ".yml.desactive"


def split_instances(config_dir: Path) -> dict[str, list[Path]]:
    """Services configures par PLUSIEURS fichiers. Chacun est une panne muette.

    Recyclarr groupe ses instances par `base_url` et **ecarte tout groupe qui en
    compte plus d'une** — c'est `SplitInstancesFilter`, verifie dans son code
    source. Or plugarr ecrit toujours la meme URL interne pour un service donne
    : deux fichiers visant Sonarr, ce sont deux instances sur la meme URL, donc
    ZERO instance synchronisee. Pas « la derniere gagne » : plus rien du tout.

    Constate sur une stack reelle. Deux installations successives avec des
    profils differents avaient laisse quatre fichiers, deux par service :

        [DBG] Split instances: [{"BaseUrl":"http://sonarr:8989",
                                 "InstanceNames":["web-1080p","web-2160p"]}]
        [INF] Found 0 config files with 0 Radarr and 0 Sonarr instances

    Recyclarr sortait malgre tout en code 0, et plugarr annoncait
    « synchronise ». Aucun profil TRaSH n'etait pose depuis des semaines.
    """
    configs = config_dir / "configs"
    if not configs.is_dir():
        return {}
    par_service: dict[str, list[Path]] = {}
    for path in sorted(configs.glob("*.yml")):
        service = target_service(path)
        if service:
            par_service.setdefault(service, []).append(path)
    return {service: paths for service, paths in par_service.items() if len(paths) > 1}


def resolve_split_instances(config_dir: Path, keep: dict[str, str]) -> list[tuple[Path, str]]:
    """Ne laisse qu'un fichier par service. Renvoie (fichier, service) ecartes.

    `keep` donne le template retenu par service ; a defaut, le plus recemment
    modifie est conserve — c'est le dernier choix de l'utilisateur.

    Les autres sont RENOMMES, jamais effaces : l'un d'eux a pu etre ajuste a la
    main, et le rendre a nouveau actif ne demande qu'un changement d'extension.
    """
    ecartes: list[tuple[Path, str]] = []
    for service, paths in split_instances(config_dir).items():
        voulu = keep.get(service)
        garde = next((p for p in paths if p.stem == voulu), None)
        if garde is None:
            garde = max(paths, key=lambda p: p.stat().st_mtime)
        for path in paths:
            if path == garde:
                continue
            path.rename(path.with_suffix("").with_suffix(DISABLED_SUFFIX))
            ecartes.append((path, service))
    return ecartes
