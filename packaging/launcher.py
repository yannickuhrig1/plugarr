"""Point d'entree des executables Windows.

`src/plugarr/__main__.py` ne convient pas : il fait un import RELATIF
(`from .cli import app`), et PyInstaller execute son script d'entree comme un
module de premier niveau, sans paquet parent. L'executable s'arretait donc sur
`attempted relative import with no known parent package`.

Le meme script sert aux DEUX executables de la version installee, qui partagent
un seul dossier `_internal` : `plugarr.exe` (console : commandes, assistant) et
`plugarr-admin.exe` (fenetre : le gestionnaire). C'est le nom de l'executable
qui decide. Deux scripts d'entree auraient voulu deux analyses PyInstaller, et
deux copies de tout le code Python.
"""

from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path

NOM_GESTIONNAIRE = "plugarr-admin"


def _sorties_du_gestionnaire() -> None:
    """Un executable sans console n'a ni `stdout` ni `stderr` : ils valent None.

    `print` s'en accommode, pas `rich` ni une trace d'exception. On les dirige
    vers un journal, dans le dossier de PlugArr, ou un rapport de bogue peut
    aller le chercher.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    from plugarr import chemins

    dossier = chemins.journaux()
    dossier.mkdir(parents=True, exist_ok=True)
    flux = open(dossier / "gestionnaire.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    sys.stdout = sys.stdout or flux
    sys.stderr = sys.stderr or flux


if __name__ == "__main__":
    # Obligatoire dans un executable gele : sans cela, tout processus enfant
    # relancerait l'executable entier au lieu du travailleur attendu.
    multiprocessing.freeze_support()
    if Path(sys.executable).stem.lower() == NOM_GESTIONNAIRE:
        _sorties_du_gestionnaire()
        from plugarr.gestionnaire import principal

        raise SystemExit(principal())

    from plugarr.cli import app
    from plugarr.selfupdate import startup

    startup()
    app()
