"""Ou PlugArr range ses fichiers sur cette machine.

**Le defaut que ce module corrige.** Le dossier du projet valait `.` : une
installation ecrivait `docker-compose.yml`, `.env`, `stack.yml` et son
historique, la page d'acces et `administration.cmd` la ou l'executable avait
ete double-clique. Le plus souvent `Telechargements`, parfois le bureau. Deux
de ces fichiers portent tous les secrets de la pile en clair.

Sous Windows, dans l'executable, une installation neuve va desormais dans
`%LOCALAPPDATA%\\plugarr\\instances\\<nom>`. Rien ne change ailleurs : sur un
serveur Linux, lancer `plugarr` depuis le dossier qu'on a choisi reste la facon
normale de dire ou l'on veut sa pile.

Deux cas passent avant le defaut, et ils comptent :

- un `--project-dir` ecrit a la main : c'est une decision, pas un oubli ;
- un `stack.yml` deja present dans le dossier courant : quelqu'un qui a range
  son executable a cote de sa pile le relance la ou elle vit. Ecrire ailleurs
  ferait deux piles portant les memes mots de passe.

Une installation posee AILLEURS avant cette version est retrouvee par le
registre (`registre.py`), et l'assistant la suit : elle n'est pas perdue parce
que le defaut a change.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import registre

#: Sous-dossiers de la racine de PlugArr. Des noms stables : l'installateur et
#: la documentation les citent.
INSTANCES = "instances"
JOURNAUX = "logs"
MISES_A_JOUR = "updates"

#: Nom du dossier d'une installation neuve. Le meme que le nom de pile par
#: defaut : une seule pile locale vit sur un Docker Desktop, et la retrouver
#: sous son nom evite de chercher.
NOM_PAR_DEFAUT = "plugarr"


def racine() -> Path:
    """Dossier de PlugArr propre a l'utilisateur. Le meme que celui du registre."""
    return registre.dossier()


def instances() -> Path:
    return racine() / INSTANCES


def journaux() -> Path:
    return racine() / JOURNAUX


def mises_a_jour() -> Path:
    return racine() / MISES_A_JOUR


def gele() -> bool:
    """Code execute depuis un executable PyInstaller, et non depuis les sources."""
    return bool(getattr(sys, "frozen", False))


def exe_windows() -> bool:
    return sys.platform == "win32" and gele()


def dossier_programme() -> Path | None:
    """Dossier de l'executable en cours, ou None depuis les sources."""
    if not gele():
        return None
    return Path(sys.executable).resolve().parent


def installe() -> bool:
    """PlugArr a-t-il ete pose par l'installateur Windows ?

    Inno Setup depose son desinstalleur (`unins000.exe`) a cote des programmes.
    C'est un temoin plus sur qu'un fichier a nous : il n'existe que si
    l'installation s'est terminee, et disparait avec elle. Un executable
    portable, lui, se decompresse dans un dossier temporaire sans rien autour.
    """
    dossier = dossier_programme()
    if dossier is None or sys.platform != "win32":
        return False
    try:
        return any(dossier.glob("unins*.exe"))
    except OSError:
        return False


def instance_par_defaut(nom: str = NOM_PAR_DEFAUT) -> Path:
    return instances() / nom


def dossier_de_lancement(explicite: Path | None = None, ici: Path | None = None) -> Path:
    """Ou l'assistant ecrit une installation, faute d'autre indication.

    `explicite` est le `--project-dir` de la ligne de commande, ou None s'il n'a
    pas ete donne. Voir la docstring du module pour l'ordre et ses raisons.
    """
    if explicite is not None:
        return Path(explicite)
    ici = Path(ici) if ici is not None else Path.cwd()
    try:
        if (ici / "stack.yml").is_file():
            return ici
    except OSError:
        pass
    if exe_windows():
        return instance_par_defaut()
    return ici


def moteur() -> list[str]:
    """Commande qui lance PlugArr lui-meme, pour un sous-processus.

    Depuis l'executable installe, c'est `plugarr.exe`, pose a cote du
    gestionnaire : le gestionnaire est un programme fenetre, sans console, et
    ne sait pas lancer un assistant en mode terminal. Depuis les sources, c'est
    l'interpreteur courant : `python -m plugarr` marche partout ou le paquet
    est importable.
    """
    if gele():
        dossier = dossier_programme()
        if dossier is not None:
            voisin = dossier / ("plugarr.exe" if sys.platform == "win32" else "plugarr")
            if voisin.is_file():
                return [str(voisin)]
        return [sys.executable]
    return [sys.executable, "-m", "plugarr"]


def environnement_moteur() -> dict[str, str]:
    """Environnement d'un sous-processus PlugArr, sortie lisible par un programme.

    Pas de couleurs ni de codes de terminal : la sortie est relue par le
    gestionnaire et affichee dans une page. `PYTHONIOENCODING` evite qu'un
    accent sous Windows fasse tomber une commande dont la sortie est un tube.

    Pas de mise a jour de PlugArr non plus : c'est le gestionnaire qui la
    propose. Un executable portable lance pour un `doctor` se serait sinon
    remplace lui-meme a sa fermeture, dans le dos du gestionnaire.
    """
    env = dict(os.environ)
    env.update(
        {
            "NO_COLOR": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "PLUGARR_NO_SELF_UPDATE": "1",
        }
    )
    if not gele():
        source = str(Path(__file__).resolve().parent.parent)
        env["PYTHONPATH"] = os.pathsep.join(p for p in (source, env.get("PYTHONPATH", "")) if p)
    return env
