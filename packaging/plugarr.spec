# Recette PyInstaller de l'executable Windows.
#
#     pyinstaller packaging/plugarr.spec --noconfirm
#
# Trois points qu'il a fallu trouver, aucun devinable :
#
# - le point d'entree ne peut pas etre `src/plugarr/__main__.py` : il fait un
#   import RELATIF, et PyInstaller execute son script d'entree sans paquet
#   parent. D'ou `packaging/launcher.py` ;
# - `app.tcss` doit etre embarque explicitement. Sans lui, Textual leve
#   `StylesheetError` au demarrage et l'assistant ne s'ouvre pas du tout ;
# - TOUT autre fichier non-Python aussi. Oubli reel en 0.1.8 : le fichier des
#   pays VPN etait absent de l'executable ET du paquet, et l'assistant plantait
#   sur l'ecran VPN. Un test compare desormais les deux listes au contenu reel
#   du paquet ;
# - Textual charge des ressources et des widgets par nom : `collect_all` evite
#   d'avoir a lister ses modules internes un par un.
#
# Verifie sur l'executable produit : la feuille de style chargee, les 16
# services affiches, et une installation complete de bout en bout.

import importlib.util
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"

textual_datas, textual_binaries, textual_hidden = collect_all("textual")
# `collect_all` rend des listes vides, sans erreur, si le paquet manque. Build
# reel du 25/09/2026 : compile depuis un venv sans paramiko, l'executable
# echouait des le premier test SSH de l'assistant. On refuse de compiler.
if importlib.util.find_spec("paramiko") is None:
    raise SystemExit(
        "paramiko absent de l'environnement de build : installez le projet "
        "(pip install -e .) avant de lancer PyInstaller."
    )
paramiko_datas, paramiko_binaries, paramiko_hidden = collect_all("paramiko")
# Windows n'embarque pas la base IANA necessaire a zoneinfo.
tz_datas, tz_binaries, tz_hidden = collect_all("tzdata") if sys.platform == "win32" else ([], [], [])

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(SRC)],
    binaries=[*textual_binaries, *paramiko_binaries, *tz_binaries],
    datas=[
        (str(SRC / "plugarr" / "tui" / "app.tcss"), "plugarr/tui"),
        # Les pays, regions et villes acceptes par chaque fournisseur VPN. Sans
        # eux, l'ecran VPN de l'assistant leve `FileNotFoundError` — donc des
        # qu'un client de telechargement est coche, c'est-a-dire toujours.
        (str(SRC / "plugarr" / "data" / "vpn_countries.json"), "plugarr/data"),
        (str(SRC / "plugarr" / "data" / "connection_icons.json"), "plugarr/data"),
        (str(SRC / "plugarr" / "data" / "recyclarr_templates.json"), "plugarr/data"),
        (str(SRC / "plugarr" / "data" / "recyclarr_templates.source.json"), "plugarr/data"),
        (str(SRC / "plugarr" / "web" / "wizard.html"), "plugarr/web"),
        (str(SRC / "plugarr" / "web" / "wizard.css"), "plugarr/web"),
        (str(SRC / "plugarr" / "web" / "wizard-profile.css"), "plugarr/web"),
        (str(SRC / "plugarr" / "web" / "wizard-parity.css"), "plugarr/web"),
        (str(SRC / "plugarr" / "web" / "wizard.js"), "plugarr/web"),
        (str(SRC / "plugarr" / "web" / "remote.js"), "plugarr/web"),
        (str(SRC / "plugarr" / "web" / "graph.js"), "plugarr/web"),
        (str(SRC / "plugarr" / "web" / "admin-graph.js"), "plugarr/web"),
        (str(SRC / "plugarr" / "web" / "graph.css"), "plugarr/web"),
        (str(SRC / "plugarr" / "web" / "gestionnaire.html"), "plugarr/web"),
        (str(SRC / "plugarr" / "web" / "gestionnaire.css"), "plugarr/web"),
        (str(SRC / "plugarr" / "web" / "gestionnaire.js"), "plugarr/web"),
        *textual_datas,
        *paramiko_datas,
        *tz_datas,
    ],
    hiddenimports=[
        *textual_hidden,
        *paramiko_hidden,
        *tz_hidden,
        # Importes tardivement dans le code : PyInstaller ne peut pas les voir.
        "plugarr.webwizard",
        "plugarr.wizard_graph",
        "plugarr.demo_admin",
        "plugarr.interface",
        "plugarr.tui.app",
        "plugarr.tui.indexers",
        # Le gestionnaire est importe par le lanceur seulement quand
        # l'executable s'appelle plugarr-admin.exe.
        "plugarr.gestionnaire",
        "plugarr.fenetre",
        "plugarr.tunnel",
        "plugarr.coffre",
        "plugarr.distantes",
        "plugarr.chemins",
    ],
    hookspath=[],
    runtime_hooks=([] if os.environ.get("PLUGARR_RELEASE_BUILD") == "1"
                   else [str(ROOT / "packaging" / "local_preview.py")]),
    excludes=[
        # Uniquement utiles au developpement : ils pesent sans rien apporter.
        "pytest",
        "_pytest",
        "PyInstaller",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

# L'executable n'avait aucune icone : Windows lui collait celle, generique,
# de tout binaire console. `assets/plugarr.ico` porte sept tailles, de 16 a
# 256 px — voir scripts/icone.py, qui l'engendre depuis le visuel d'origine.
# Elle est ecrite en toutes lettres dans chaque EXE : un test la cherche.

if os.environ.get("PLUGARR_ONEDIR") == "1":
    # Version installee (packaging/installer/plugarr.iss) : un DOSSIER, deux
    # executables, un seul `_internal` partage. Verifie avec PyInstaller 6.22.3
    # le 26/09/2026 : les deux executables demarrent sur le meme runtime.
    #
    # Pas d'extraction dans %TEMP% a chaque lancement, contrairement a
    # l'executable portable : le demarrage est plus rapide, et les antivirus
    # voient des fichiers stables plutot qu'un binaire qui se decompresse.
    moteur = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="plugarr",
        icon=str(ROOT / "assets" / "plugarr.ico"),
        debug=False,
        strip=False,
        upx=False,
        # L'assistant en mode terminal et les commandes ont besoin d'une console.
        console=True,
    )
    gestionnaire = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        # Le lanceur reconnait ce nom : voir packaging/launcher.py.
        name="plugarr-admin",
        icon=str(ROOT / "assets" / "plugarr.ico"),
        debug=False,
        strip=False,
        upx=False,
        # Le gestionnaire est une fenetre : une console noire a cote n'aurait
        # rien a afficher.
        console=False,
    )
    coll = COLLECT(
        moteur,
        gestionnaire,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="PlugArr",
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=os.environ.get("PLUGARR_EXE_NAME", "plugarr"),
        icon=str(ROOT / "assets" / "plugarr.ico"),
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        runtime_tmpdir=None,
        # L'assistant est une application de TERMINAL : sans console, il n'aurait
        # nulle part ou s'afficher.
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
