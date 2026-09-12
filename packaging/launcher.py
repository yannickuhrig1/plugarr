"""Point d'entree de l'executable Windows.

`src/plugarr/__main__.py` ne convient pas : il fait un import RELATIF
(`from .cli import app`), et PyInstaller execute son script d'entree comme un
module de premier niveau, sans paquet parent. L'executable s'arretait donc sur
`attempted relative import with no known parent package`.

Ce lanceur ne fait rien d'autre qu'un import absolu.
"""

from __future__ import annotations

import multiprocessing

from plugarr.cli import app

if __name__ == "__main__":
    # Obligatoire dans un executable gele : sans cela, tout processus enfant
    # relancerait l'executable entier au lieu du travailleur attendu.
    multiprocessing.freeze_support()
    from plugarr.selfupdate import startup

    startup()
    app()
