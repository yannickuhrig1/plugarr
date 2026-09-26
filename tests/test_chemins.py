"""Ou une installation neuve est ecrite, et ou PlugArr range le reste.

Le defaut constate : le dossier du projet valait `.`, et une installation
lancee par double-clic ecrivait `.env` et `stack.yml`, avec tous leurs secrets,
dans `Telechargements`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from plugarr import chemins, interface


def test_un_dossier_donne_a_la_main_prime(tmp_path, monkeypatch):
    monkeypatch.setattr(chemins, "exe_windows", lambda: True)

    assert chemins.dossier_de_lancement(tmp_path / "choisi", ici=tmp_path) == tmp_path / "choisi"


def test_un_stack_sous_la_main_prime_sur_le_dossier_des_instances(tmp_path, monkeypatch):
    """Quelqu'un qui a range l'executable a cote de sa pile la relance la."""
    monkeypatch.setattr(chemins, "exe_windows", lambda: True)
    (tmp_path / "stack.yml").write_text("version: 7\n", encoding="utf-8")

    assert chemins.dossier_de_lancement(None, ici=tmp_path) == tmp_path


def test_l_executable_windows_ecrit_dans_le_dossier_des_instances(tmp_path, monkeypatch):
    monkeypatch.setattr(chemins, "exe_windows", lambda: True)

    lance = chemins.dossier_de_lancement(None, ici=tmp_path / "Telechargements")

    assert lance == chemins.instances() / "plugarr"
    assert lance.is_relative_to(chemins.racine())


def test_hors_de_l_executable_rien_ne_change(tmp_path, monkeypatch):
    """Sur un serveur Linux, le dossier courant reste la facon de choisir."""
    monkeypatch.setattr(chemins, "exe_windows", lambda: False)

    assert chemins.dossier_de_lancement(None, ici=tmp_path) == tmp_path


def test_la_racine_est_celle_du_registre(tmp_path, monkeypatch):
    monkeypatch.setenv("PLUGARR_HOME", str(tmp_path / "home"))

    assert chemins.racine() == tmp_path / "home"
    assert chemins.instances() == tmp_path / "home" / "instances"
    assert chemins.journaux() == tmp_path / "home" / "logs"
    assert chemins.mises_a_jour() == tmp_path / "home" / "updates"


def test_installe_reconnait_le_desinstalleur_d_inno(tmp_path, monkeypatch):
    monkeypatch.setattr(chemins.sys, "platform", "win32")
    monkeypatch.setattr(chemins, "dossier_programme", lambda: tmp_path)

    assert not chemins.installe()
    (tmp_path / "unins000.exe").write_bytes(b"MZ")
    assert chemins.installe()


def test_depuis_les_sources_ce_n_est_pas_une_installation():
    assert not getattr(sys, "frozen", False)
    assert not chemins.installe()


def test_le_moteur_depuis_les_sources_est_l_interpreteur():
    assert chemins.moteur() == [sys.executable, "-m", "plugarr"]


def test_le_moteur_d_un_executable_est_plugarr_exe_voisin(tmp_path, monkeypatch):
    """Depuis plugarr-admin.exe, `sys.executable` rouvrirait le gestionnaire."""
    monkeypatch.setattr(chemins.sys, "frozen", True, raising=False)
    monkeypatch.setattr(chemins.sys, "platform", "win32")
    monkeypatch.setattr(chemins.sys, "executable", str(tmp_path / "plugarr-admin.exe"))
    (tmp_path / "plugarr.exe").write_bytes(b"MZ")

    assert chemins.moteur() == [str((tmp_path / "plugarr.exe").resolve())]


def test_l_environnement_du_moteur_trouve_les_sources():
    env = chemins.environnement_moteur()

    source = str(Path(chemins.__file__).resolve().parent.parent)
    assert source in env["PYTHONPATH"].split(";" if sys.platform == "win32" else ":")
    assert env["NO_COLOR"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_l_assistant_web_part_du_dossier_des_instances(tmp_path, monkeypatch):
    """Le double-clic ne pose plus rien dans le dossier ou il a eu lieu."""
    from plugarr import webwizard

    monkeypatch.setattr(chemins, "exe_windows", lambda: True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(interface, "read_preference", lambda: interface.Interface.WEB)
    vus: list[Path] = []
    monkeypatch.setattr(webwizard, "run_web", lambda dossier, **_: vus.append(dossier) or 0)

    assert interface.launch(interface.Interface.WEB) == 0
    assert vus == [chemins.instance_par_defaut()]
    assert not any(tmp_path.iterdir())


def test_la_preference_d_interface_rejoint_le_dossier_de_plugarr(tmp_path, monkeypatch):
    monkeypatch.setattr(interface.sys, "platform", "win32")
    monkeypatch.setenv("PLUGARR_HOME", str(tmp_path / "home"))

    interface.save_preference(interface.Interface.TUI)

    assert interface.preference_path() == tmp_path / "home" / "interface.json"
    assert interface.read_preference() == interface.Interface.TUI


def test_l_ancienne_preference_est_encore_lue(tmp_path, monkeypatch):
    """Une preference posee par une version precedente ne se perd pas."""
    monkeypatch.setattr(interface.sys, "platform", "win32")
    monkeypatch.delenv("PLUGARR_HOME", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    ancienne = tmp_path / "roaming" / "plugarr" / "interface.json"
    ancienne.parent.mkdir(parents=True)
    ancienne.write_text('{"interface": "web"}', encoding="utf-8")

    assert interface.read_preference() == interface.Interface.WEB
