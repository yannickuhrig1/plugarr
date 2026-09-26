"""Choix local de l'interface, independant de la configuration des services."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from enum import Enum
from pathlib import Path

import typer

from .i18n import t


class Interface(str, Enum):
    AUTO = "auto"
    WEB = "web"
    TUI = "tui"


def preference_path() -> Path:
    """Sous Windows, dans le dossier de PlugArr, a cote du registre.

    Elle vivait seule dans `%APPDATA%` (le profil itinerant) alors que tout le
    reste de PlugArr est dans `%LOCALAPPDATA%` : deux dossiers a connaitre pour
    un seul programme. L'ancien emplacement est encore lu, voir
    `_ancienne_preference`.
    """
    if sys.platform == "win32":
        from .chemins import racine

        return racine() / "interface.json"
    root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return root / "plugarr" / "interface.json"


def _ancienne_preference() -> Path | None:
    if sys.platform != "win32" or os.environ.get("PLUGARR_HOME", "").strip():
        return None
    return Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))) / "plugarr" / "interface.json"


def read_preference() -> Interface:
    for chemin in (preference_path(), _ancienne_preference()):
        if chemin is None:
            continue
        try:
            value = json.loads(chemin.read_text(encoding="utf-8"))
            return Interface(value["interface"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return Interface.AUTO


def save_preference(mode: Interface) -> None:
    path = preference_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix="interface-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"interface": Interface(mode).value}, stream)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def desktop_available() -> bool:
    """Un indice de session graphique, pas une garantie d'ouverture navigateur."""
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return False
    return sys.platform in ("win32", "darwin") or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )


def launch(
    mode: Interface = Interface.AUTO,
    project_dir: Path | None = None,
    *,
    open_page: bool = True,
) -> int:
    from .chemins import dossier_de_lancement

    mode = Interface(mode)
    project_dir = dossier_de_lancement(project_dir)
    terminal = sys.stdin.isatty() and sys.stdout.isatty()
    if mode == Interface.AUTO:
        mode = read_preference()
        if mode == Interface.AUTO:
            if desktop_available():
                if terminal:
                    typer.echo(t("Choisir l'interface : web (graphique) ou tui (terminal)."))
                    while True:
                        choice = typer.prompt(t("Mode d'interface"), default="web").strip().lower()
                        if choice in ("web", "tui"):
                            mode = Interface(choice)
                            break
                    if typer.confirm(t("Memoriser ce choix sur cet ordinateur ?"), default=False):
                        save_preference(mode)
                else:
                    mode = Interface.WEB
            elif terminal:
                mode = Interface.TUI
            else:
                typer.echo(t("Aucun terminal interactif. Utilisez plugarr web --no-open."))
                return 2
    if mode == Interface.WEB:
        from .webwizard import run_web

        result = run_web(project_dir, open_page=open_page)
        if result != "tui":
            return int(result)
    from .tui.app import run_wizard

    return run_wizard(project_dir, open_page=open_page)
