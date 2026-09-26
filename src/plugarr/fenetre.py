"""Ouvrir une page locale comme une fenetre d'application.

Le gestionnaire et les consoles sont des pages servies sur 127.0.0.1. Dans un
onglet de navigateur, ils se perdent parmi les autres et affichent une barre
d'adresse qui n'a rien a faire la. Edge et Chrome savent ouvrir une adresse
comme une application (`--app=`) : une fenetre a part, avec son icone dans la
barre des taches, sans onglets ni barre d'adresse.

Edge est present sur tout Windows 10 et 11 : c'est lui qu'on cherche d'abord.
S'il manque, le navigateur par defaut prend le relais, en onglet ordinaire : la
page marche de la meme facon, elle est seulement moins bien rangee.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from collections.abc import Iterator
from pathlib import Path


def _candidats_windows() -> Iterator[Path]:
    bases = [
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramFiles"),
        os.environ.get("LOCALAPPDATA"),
    ]
    for editeur, produit, exe in (
        ("Microsoft", "Edge", "msedge.exe"),
        ("Google", "Chrome", "chrome.exe"),
    ):
        for base in filter(None, bases):
            yield Path(base) / editeur / produit / "Application" / exe


def navigateur_app() -> Path | None:
    """Un navigateur qui sait ouvrir une page comme une application."""
    if sys.platform == "win32":
        for candidat in _candidats_windows():
            try:
                if candidat.is_file():
                    return candidat
            except OSError:
                continue
        return None
    for nom in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
        trouve = shutil.which(nom)
        if trouve:
            return Path(trouve)
    return None


def _detache() -> dict:
    """Le navigateur ne doit ni heriter de nos tubes, ni mourir avec nous."""
    options: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        options["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        options["start_new_session"] = True
    return options


def ouvrir(url: str, *, largeur: int = 1180, hauteur: int = 820) -> bool:
    """Ouvre `url` dans une fenetre d'application, ou a defaut un onglet.

    Renvoie False seulement si rien n'a pu etre ouvert : l'appelant affiche
    alors l'adresse, qui reste le moyen sur d'y arriver.
    """
    navigateur = navigateur_app()
    if navigateur is not None:
        try:
            subprocess.Popen(
                [str(navigateur), f"--app={url}", f"--window-size={largeur},{hauteur}"],
                **_detache(),
            )
            return True
        except OSError:
            pass
    try:
        return bool(webbrowser.open(url))
    except Exception:  # noqa: BLE001 - un poste sans navigateur n'est pas une erreur
        return False
