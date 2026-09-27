"""Aucun programme console lance par PlugArr n'ouvre sa propre fenetre.

`plugarr-admin.exe` est un executable fenetre, sans console. Sous Windows,
chaque `docker` qu'il lancait en recevait une, qui s'ouvrait et se refermait
aussitot. Le gestionnaire relevant l'etat toutes les 4 secondes, la 0.11.0
faisait clignoter l'ecran sans arret. Constate le 27/09/2026 sur la version
installee : `docker ps` puis `docker compose ps`, chacun avec son `conhost`.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from plugarr import discovery, runner, updates

SOURCES = Path(runner.__file__).parent

#: Appels qui ne tournent jamais sous Windows, avec la raison.
HORS_WINDOWS = {
    ("autostart.py", "_systemctl"): "systemd n'existe que sous Linux",
}

LANCEURS = {"run", "Popen", "call", "check_call", "check_output"}


def _appels_sans_option() -> list[str]:
    """Appels a `subprocess` qui ne disent rien de la fenetre du programme lance.

    Un appel passe s'il porte `creationflags`, ou des options depliees
    (`**sans_fenetre()`, `**_detache()`) dont les tests ci-dessous verifient
    le contenu.
    """
    fautifs = []
    for fichier in sorted(SOURCES.rglob("*.py")):
        arbre = ast.parse(fichier.read_text(encoding="utf-8"))
        for fonction in ast.walk(arbre):
            if not isinstance(fonction, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for noeud in ast.walk(fonction):
                if not (
                    isinstance(noeud, ast.Call)
                    and isinstance(noeud.func, ast.Attribute)
                    and isinstance(noeud.func.value, ast.Name)
                    and noeud.func.value.id == "subprocess"
                    and noeud.func.attr in LANCEURS
                ):
                    continue
                if any(kw.arg in ("creationflags", None) for kw in noeud.keywords):
                    continue
                cle = (fichier.relative_to(SOURCES).as_posix(), fonction.name)
                if cle not in HORS_WINDOWS:
                    fautifs.append(f"{cle[0]}:{noeud.lineno} ({cle[1]})")
    return fautifs


def test_chaque_appel_dit_s_il_ouvre_une_fenetre():
    assert _appels_sans_option() == []


@pytest.mark.parametrize(
    "appel",
    [
        pytest.param(lambda: runner._run(["docker", "ps"]), id="runner"),
        pytest.param(lambda: discovery._docker("ps"), id="discovery"),
        pytest.param(lambda: updates._docker("ps"), id="updates"),
    ],
)
def test_docker_sans_fenetre_sous_windows(monkeypatch, appel):
    monkeypatch.setattr(runner.sys, "platform", "win32")
    options: dict = {}

    def faux_run(args, **kw):
        options.update(kw)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", faux_run)
    appel()
    assert options["creationflags"] & runner.CREATE_NO_WINDOW


def test_aucune_option_hors_windows(monkeypatch):
    # `creationflags` non nul leve ValueError hors de Windows.
    monkeypatch.setattr(runner.sys, "platform", "linux")
    assert runner.sans_fenetre() == {}


@pytest.mark.skipif(sys.platform != "win32", reason="constante propre a Windows")
def test_la_constante_est_celle_de_windows():
    assert runner.CREATE_NO_WINDOW == subprocess.CREATE_NO_WINDOW
