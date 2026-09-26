"""Les installations distantes que ce poste a posees par SSH.

Une installation distante reussie ne laissait aucune trace sur le poste qui
l'avait lancee : ni l'adresse du serveur, ni son empreinte SSH, ni le dossier de
la pile. Pour y revenir, il fallait tout ressaisir, et rien ne permettait de
verifier qu'on parlait bien au meme serveur que la premiere fois.

Ce fichier garde de quoi s'y reconnecter, **et rien de plus** :

- aucun mot de passe, aucune cle privee, aucun mot de passe sudo. Ils sont
  redemandes a chaque connexion, comme dans l'assistant, ou pris dans le coffre
  de Windows si l'utilisateur l'a demande (`coffre.py`) ;
- l'empreinte SSH confirmee a l'installation. C'est elle qui fait refuser une
  connexion si le serveur a change de cle, au lieu de l'accepter en silence.

Un fichier SEPARE de `installations.yml`, et c'est voulu : un executable plus
ancien reecrit ce dernier en entier a chaque installation locale. Il y
effacerait des entrees qu'il ne connait pas.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import yaml

from . import registre

FICHIER = "distantes.yml"

#: Au-dela, les plus anciennes sont oubliees, comme dans le registre local.
MAX_ENTREES = 30


@dataclass(frozen=True)
class Distante:
    """Une installation distante connue. Des coordonnees, jamais de secret."""

    host: str
    port: int
    user: str
    empreinte: str
    project_dir: str
    project_name: str = "plugarr"
    config_root: str = ""
    data_root: str = ""
    #: 0 quand la pile n'a pas de console en conteneur : il n'y a alors rien a
    #: ouvrir par un tunnel.
    console_port: int = 0
    uid: int = -1
    gid: int = -1
    #: Un nom choisi par l'utilisateur dans le gestionnaire, vide sinon.
    nom: str = ""
    date: str = ""

    @property
    def ident(self) -> str:
        """Identifiant stable : meme serveur, meme compte, meme dossier."""
        cle = f"{self.user}@{self.host.lower()}:{self.port}{self.project_dir}"
        return "ssh-" + hashlib.sha256(cle.encode("utf-8")).hexdigest()[:12]

    @property
    def libelle(self) -> str:
        return self.nom or f"{self.user}@{self.host}"


def chemin() -> Path:
    return registre.dossier() / FICHIER


def _entier(valeur, defaut: int) -> int:
    try:
        return int(valeur)
    except (TypeError, ValueError):
        return defaut


def lire() -> list[Distante]:
    """Installations distantes connues, de la plus recente a la plus ancienne.

    Un fichier illisible vaut une liste vide : c'est un confort, pas une source
    de verite. La verite est dans le `stack.yml` du serveur.
    """
    try:
        brut = yaml.safe_load(chemin().read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    if not isinstance(brut, dict):
        return []
    trouvees: list[Distante] = []
    for item in brut.get("distantes") or []:
        if not isinstance(item, dict):
            continue
        host = str(item.get("host") or "").strip()
        user = str(item.get("user") or "").strip()
        project_dir = str(item.get("project_dir") or "").strip()
        if not host or not user or not project_dir.startswith("/"):
            continue
        trouvees.append(
            Distante(
                host=host,
                port=_entier(item.get("port"), 22),
                user=user,
                empreinte=str(item.get("empreinte") or ""),
                project_dir=project_dir,
                project_name=str(item.get("project_name") or "plugarr"),
                config_root=str(item.get("config_root") or ""),
                data_root=str(item.get("data_root") or ""),
                console_port=_entier(item.get("console_port"), 0),
                uid=_entier(item.get("uid"), -1),
                gid=_entier(item.get("gid"), -1),
                nom=str(item.get("nom") or ""),
                date=str(item.get("date") or ""),
            )
        )
    return sorted(trouvees, key=lambda d: d.date, reverse=True)


def _ecrire(entrees: list[Distante]) -> None:
    fichier = chemin()
    fichier.parent.mkdir(parents=True, exist_ok=True)
    temporaire = fichier.with_suffix(".tmp")
    temporaire.write_text(
        "# Ecrit par PlugArr. Des adresses et des empreintes SSH : aucun mot de\n"
        "# passe, aucune cle. Ils sont redemandes a chaque connexion.\n"
        + yaml.safe_dump(
            {"distantes": [asdict(e) for e in entrees[:MAX_ENTREES]]},
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    temporaire.replace(fichier)


def enregistrer(distante: Distante) -> None:
    """Note une installation distante, ou rafraichit son entree.

    Le nom donne dans le gestionnaire survit a une reinstallation : c'est un
    choix de l'utilisateur, pas une propriete de la pile. Ne leve jamais :
    echouer a tenir cette liste ne doit pas faire echouer une installation
    qui, elle, a reussi.
    """
    try:
        connues = lire()
        ancienne = next((d for d in connues if d.ident == distante.ident), None)
        nouvelle = replace(
            distante,
            nom=distante.nom or (ancienne.nom if ancienne else ""),
            date=datetime.now(UTC).isoformat(timespec="seconds"),
        )
        _ecrire([nouvelle, *(d for d in connues if d.ident != distante.ident)])
    except OSError:
        return


def trouver(ident: str) -> Distante | None:
    return next((d for d in lire() if d.ident == ident), None)


def renommer(ident: str, nom: str) -> bool:
    connues = lire()
    if not any(d.ident == ident for d in connues):
        return False
    nom = " ".join(str(nom).split())[:60]
    _ecrire([replace(d, nom=nom) if d.ident == ident else d for d in connues])
    return True


def oublier(ident: str) -> bool:
    """Retire une installation de la liste. Ne touche a rien sur le serveur."""
    connues = lire()
    restantes = [d for d in connues if d.ident != ident]
    if len(restantes) == len(connues):
        return False
    _ecrire(restantes)
    return True
