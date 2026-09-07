"""Ou sont les installations de cet utilisateur.

`stack.yml` porte tout ce que PlugArr a genere : identifiants, mots de passe,
cles API, VPN. C'est le seul endroit ou le mot de passe d'un Jellyfin ou d'un
qui existe encore en clair — eux n'en gardent qu'un hachage. Le retrouver n'est
donc pas un confort, c'est la condition pour qu'une reinstallation ne casse pas
ce qui marchait.

**Il etait cherche a un seul endroit : le repertoire courant.** Quelqu'un qui
double-clique `plugarr.exe` depuis son bureau apres l'avoir lance depuis
`Telechargements` la premiere fois repart donc de zero, sans un mot, avec des
mots de passe tout neufs que ses services refuseront. Le message d'erreur
renvoyait vers `--project-dir`, une option en ligne de commande — inutilisable
pour qui n'ouvre jamais de terminal.

Ce module tient une liste, hors de tout projet, des installations connues :
ou est leur `stack.yml`, quel `CONFIG_ROOT` elles pilotent, et quand elles ont
ete ecrites. Elle ne contient **aucun secret** : uniquement des chemins.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

FICHIER = "installations.yml"

#: Au-dela, les plus anciennes sont oubliees. Une liste sans fin finirait par
#: proposer des installations effacees depuis des mois.
MAX_ENTREES = 20


def dossier() -> Path:
    """Dossier de PlugArr propre a l'utilisateur, hors de tout projet.

    `PLUGARR_HOME` existe pour les tests et pour une installation portable sur
    cle USB. Ce n'est pas un reglage a documenter dans l'assistant : il ne
    change rien a ce que l'utilisateur peut faire, seulement ou le registre est
    pose.
    """
    force = os.environ.get("PLUGARR_HOME", "").strip()
    if force:
        return Path(force)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / "plugarr"
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg:
        return Path(xdg) / "plugarr"
    return Path.home() / ".local" / "share" / "plugarr"


def chemin() -> Path:
    return dossier() / FICHIER


@dataclass(frozen=True)
class Installation:
    """Une installation connue. Des chemins, jamais de secret."""

    project_dir: Path
    config_root: str
    project_name: str
    date: str

    @property
    def stack(self) -> Path:
        return self.project_dir / "stack.yml"

    @property
    def vivante(self) -> bool:
        """Son `stack.yml` est-il toujours la ?

        Un dossier efface ou un disque externe debranche laissent une entree
        derriere eux. La proposer enverrait l'utilisateur vers un fichier qui
        n'existe plus.
        """
        try:
            return self.stack.is_file()
        except OSError:
            return False


def _normaliser(valeur: str) -> str:
    """Comparaison de chemins tolerante : casse et separateurs.

    Une barre oblique inverse ou droite, une majuscule ou non : le meme
    dossier s'ecrit de plusieurs facons sous Windows. Les distinguer ferait
    rater la reprise a celui qui a retape son chemin a la main.
    """
    texte = str(valeur or "").strip().rstrip("/\\").replace("\\", "/")
    return texte.casefold() if os.name == "nt" else texte


def lire() -> list[Installation]:
    """Installations connues, de la plus recente a la plus ancienne.

    Un registre illisible n'arrete rien : il est traite comme vide. C'est un
    index reconstructible, pas une source de verite — la source, c'est
    `stack.yml` lui-meme.
    """
    fichier = chemin()
    try:
        brut = yaml.safe_load(fichier.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    if not isinstance(brut, dict):
        return []
    entrees = []
    for item in brut.get("installations") or []:
        if not isinstance(item, dict) or not item.get("project_dir"):
            continue
        entrees.append(
            Installation(
                project_dir=Path(str(item["project_dir"])),
                config_root=str(item.get("config_root") or ""),
                project_name=str(item.get("project_name") or "plugarr"),
                date=str(item.get("date") or ""),
            )
        )
    return sorted(entrees, key=lambda e: e.date, reverse=True)


def _ecrire(entrees: list[Installation]) -> None:
    fichier = chemin()
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(
        "# Ecrit par PlugArr. Uniquement des chemins : aucun mot de passe,\n"
        "# aucune cle API. Les secrets vivent dans le stack.yml de chaque\n"
        "# installation, et nulle part ailleurs.\n"
        + yaml.safe_dump(
            {
                "installations": [
                    {
                        "project_dir": str(e.project_dir),
                        "config_root": e.config_root,
                        "project_name": e.project_name,
                        "date": e.date,
                    }
                    for e in entrees[:MAX_ENTREES]
                ]
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def enregistrer(project_dir: Path, config_root: str, project_name: str = "plugarr") -> None:
    """Note cette installation, ou rafraichit son entree.

    Ne leve jamais : echouer a tenir un index ne doit pas faire echouer une
    installation qui, elle, s'est bien passee.
    """
    try:
        project_dir = Path(project_dir).resolve()
    except OSError:
        project_dir = Path(project_dir)
    entree = Installation(
        project_dir=project_dir,
        config_root=str(config_root or ""),
        project_name=project_name or "plugarr",
        date=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    autres = [
        e for e in lire() if _normaliser(str(e.project_dir)) != _normaliser(str(project_dir))
    ]
    try:
        _ecrire([entree, *autres])
    except OSError:
        return


def oublier(project_dir: Path) -> None:
    """Retire une installation du registre. Sans effet si elle n'y est pas."""
    cible = _normaliser(str(project_dir))
    restantes = [e for e in lire() if _normaliser(str(e.project_dir)) != cible]
    try:
        _ecrire(restantes)
    except OSError:
        return


def retrouver(config_root: str | None = None) -> Installation | None:
    """L'installation la plus plausible, `stack.yml` a l'appui.

    Le `CONFIG_ROOT` prime : c'est lui que l'utilisateur vient de saisir dans
    l'assistant, et c'est lui qui designe les services reellement en place. A
    defaut, la derniere installation ecrite — le cas de quelqu'un qui relance
    l'executable depuis un autre dossier sans rien changer d'autre.
    """
    vivantes = [e for e in lire() if e.vivante]
    if not vivantes:
        return None
    if config_root:
        vise = _normaliser(config_root)
        for entree in vivantes:
            if _normaliser(entree.config_root) == vise:
                return entree
    return vivantes[0]
