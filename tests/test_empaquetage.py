"""Tout fichier non-Python doit etre declare dans les DEUX empaquetages.

Panne reelle en 0.1.8 et 0.1.9, signalee ainsi : « impossible de les
installer ». Le fichier des pays VPN etait present dans l'arborescence source —
donc invisible au developpement, ou tout marchait — mais absent de l'executable
ET de la roue :

    [tool.hatch.build.targets.wheel]
    artifacts = ["*.tcss"]          # le .json manquait

    datas=[(app.tcss, "plugarr/tui")]   # le .json manquait aussi

Resultat : `FileNotFoundError` sur l'ecran VPN de l'assistant, c'est-a-dire des
qu'un client de telechargement etait coche. La CI ne l'a pas vu : elle teste que
l'executable repond a `--help` et que l'assistant s'ouvre, pas qu'on peut aller
jusqu'au bout.

Ce test regarde ce qui existe REELLEMENT sous `src/plugarr`, et non une liste
qu'il faudrait penser a tenir a jour.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
PAQUET = RACINE / "src" / "plugarr"
SPEC = RACINE / "packaging" / "plugarr.spec"

#: Ce qui n'a rien a faire dans un paquet installe.
IGNORES = {".pyc", ".pyo"}
DOSSIERS_IGNORES = {"__pycache__"}


def fichiers_de_donnees() -> list[Path]:
    """Fichiers non-Python vivant dans le paquet, relatifs a `src/plugarr`."""
    trouves = []
    for chemin in PAQUET.rglob("*"):
        if not chemin.is_file() or chemin.suffix == ".py" or chemin.suffix in IGNORES:
            continue
        if DOSSIERS_IGNORES & set(chemin.parts):
            continue
        trouves.append(chemin.relative_to(PAQUET))
    return sorted(trouves)


def test_il_y_a_bien_des_fichiers_de_donnees():
    """Si ce test tombe, les deux suivants ne prouvent plus rien."""
    trouves = fichiers_de_donnees()

    assert trouves, "aucun fichier de donnees trouve : le reste du fichier ne teste rien"
    assert Path("tui/app.tcss") in trouves
    assert Path("data/vpn_countries.json") in trouves


@pytest.mark.parametrize("fichier", [str(f) for f in fichiers_de_donnees()])
def test_le_fichier_entre_dans_la_roue(fichier):
    """`artifacts` de hatch decide de ce qui suit le code dans le paquet."""
    config = tomllib.loads((RACINE / "pyproject.toml").read_text(encoding="utf-8"))
    motifs = config["tool"]["hatch"]["build"]["targets"]["wheel"]["artifacts"]

    suffixe = Path(fichier).suffix
    assert any(m == f"*{suffixe}" or m.endswith(fichier) for m in motifs), (
        f"{fichier} n'est couvert par aucun motif de `artifacts` : {motifs}. "
        f"Il sera absent du paquet installe."
    )


@pytest.mark.parametrize("fichier", [str(f) for f in fichiers_de_donnees()])
def test_le_fichier_entre_dans_l_executable(fichier):
    """`datas` du spec decide de ce que PyInstaller embarque."""
    spec = SPEC.read_text(encoding="utf-8")

    nom = Path(fichier).name
    assert re.search(rf'"{re.escape(nom)}"', spec), (
        f"{fichier} n'apparait pas dans les `datas` de {SPEC.name}. "
        f"Il sera absent de l'executable Windows."
    )


def test_le_fichier_des_pays_est_lisible_depuis_le_paquet():
    """Le chemin calcule par le module doit exister, pas seulement le fichier."""
    from plugarr import vpnservers

    assert vpnservers.DATA.is_file(), vpnservers.DATA
    assert vpnservers.choices("mullvad"), "le fichier est la mais ne dit rien"


def test_le_build_refuse_de_partir_sans_paramiko():
    """`collect_all` ignore un paquet absent : EXE reel du 25/09/2026 sans SSH."""
    spec = SPEC.read_text(encoding="utf-8")

    garde = spec.index('find_spec("paramiko") is None')
    assert garde < spec.index('collect_all("paramiko")')
