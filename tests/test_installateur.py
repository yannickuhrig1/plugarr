"""La version installee : installateur, mise a jour silencieuse, coherence des noms.

Plusieurs fichiers doivent s'accorder sans que rien ne le verifie a
l'execution : le nom de l'executable du gestionnaire (spec PyInstaller,
lanceur, script Inno), le nom de l'installateur (script Inno, workflow,
`selfupdate`), l'option `/RELANCER`. Un ecart ne se verrait qu'au moment ou
une mise a jour ne trouverait rien, ou relancerait le mauvais programme.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from plugarr import __version__, chemins, selfupdate

RACINE = Path(__file__).resolve().parent.parent
ISS = (RACINE / "packaging" / "installer" / "plugarr.iss").read_text(encoding="utf-8-sig")
SPEC = (RACINE / "packaging" / "plugarr.spec").read_text(encoding="utf-8")
LANCEUR = (RACINE / "packaging" / "launcher.py").read_text(encoding="utf-8")
WORKFLOW = (RACINE / ".github" / "workflows" / "windows-exe.yml").read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _sans_proxy(monkeypatch):
    for nom in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(nom, raising=False)


def _plus_recente() -> str:
    majeur, mineur, correctif = selfupdate.version(__version__)
    return f"v{majeur}.{mineur}.{correctif + 1}"


def _release(tag: str, *noms: str) -> dict:
    return {
        "tag_name": tag,
        "assets": [
            {
                "name": nom,
                "browser_download_url": f"https://github.com/{selfupdate.REPOSITORY}/releases/download/{tag}/{nom}",
                "digest": "sha256:" + "1" * 64,
                "size": 100,
            }
            for nom in noms
        ],
    }


# ------------------------------------------------------------- mise a jour


def test_une_version_installee_attend_l_installateur(httpx_mock):
    tag = _plus_recente()
    httpx_mock.add_response(
        url=selfupdate.API,
        json=_release(tag, "plugarr.exe", selfupdate.nom_installateur(tag)),
    )

    info = selfupdate.check(installateur=True)

    assert info["available"] and info["verified_asset"]
    assert info["asset"] == f"PlugArr-Setup-{tag[1:]}.exe"
    assert info["url"].endswith(info["asset"])


def test_sans_installateur_publie_la_version_installee_ne_se_met_pas_a_jour(httpx_mock):
    """Une release qui n'aurait que `plugarr.exe` ne doit pas remplacer, fichier
    par fichier, un seul des executables d'un dossier installe."""
    tag = _plus_recente()
    httpx_mock.add_response(url=selfupdate.API, json=_release(tag, "plugarr.exe"))

    info = selfupdate.check(installateur=True)

    assert info["available"] and not info["verified_asset"]


def test_l_executable_portable_garde_son_fichier(httpx_mock):
    """Les executables deja distribues cherchent `plugarr.exe` et rien d'autre."""
    tag = _plus_recente()
    httpx_mock.add_response(
        url=selfupdate.API, json=_release(tag, "plugarr.exe", selfupdate.nom_installateur(tag))
    )

    info = selfupdate.check(installateur=False)

    assert info["asset"] == "plugarr.exe"
    assert info["verified_asset"]


def test_l_installateur_est_telecharge_verifie_dans_le_dossier_des_mises_a_jour(httpx_mock):
    tag = _plus_recente()
    contenu = b"MZ-installateur"
    nom = selfupdate.nom_installateur(tag)
    url = f"https://github.com/{selfupdate.REPOSITORY}/releases/download/{tag}/{nom}"
    httpx_mock.add_response(url=url, content=contenu)
    info = {
        "installateur": True, "available": True, "verified_asset": True, "url": url,
        "size": len(contenu), "digest": "sha256:" + hashlib.sha256(contenu).hexdigest(),
        "asset": nom, "latest": tag,
    }
    ancien = chemins.mises_a_jour() / nom
    ancien.parent.mkdir(parents=True, exist_ok=True)
    ancien.write_bytes(b"jamais verifie")

    chemin = selfupdate.telecharger_installateur(info)

    assert chemin == ancien
    assert chemin.read_bytes() == contenu


def test_un_installateur_corrompu_est_refuse(httpx_mock):
    tag = _plus_recente()
    nom = selfupdate.nom_installateur(tag)
    url = f"https://github.com/{selfupdate.REPOSITORY}/releases/download/{tag}/{nom}"
    httpx_mock.add_response(url=url, content=b"MZ-altere")
    info = {
        "installateur": True, "available": True, "verified_asset": True, "url": url,
        "size": 9, "digest": "sha256:" + "0" * 64, "asset": nom, "latest": tag,
    }

    with pytest.raises(ValueError):
        selfupdate.telecharger_installateur(info)
    assert not (chemins.mises_a_jour() / nom).exists()


def test_un_nom_d_installateur_inattendu_est_refuse():
    info = {"installateur": True, "asset": "autre.exe", "latest": "v9.9.9"}

    with pytest.raises(ValueError, match="inattendu"):
        selfupdate.telecharger_installateur(info)


def test_l_installateur_part_en_silencieux_et_detache(monkeypatch, tmp_path):
    monkeypatch.setattr(selfupdate.sys, "platform", "win32")
    lances = []
    monkeypatch.setattr(
        selfupdate.subprocess, "Popen", lambda args, **options: lances.append((args, options))
    )

    selfupdate.lancer_installateur(tmp_path / "PlugArr-Setup-9.9.9.exe")

    [(args, options)] = lances
    assert args[0].endswith("PlugArr-Setup-9.9.9.exe")
    assert {"/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RELANCER=1"} <= set(args)
    assert options["creationflags"] & 0x00000008, "DETACHED_PROCESS : il doit survivre au gestionnaire"


def test_une_version_installee_ne_se_remplace_pas_seule_a_la_fermeture(monkeypatch, capsys):
    monkeypatch.setattr(selfupdate.sys, "platform", "win32")
    monkeypatch.setattr(selfupdate.sys, "frozen", True, raising=False)
    monkeypatch.delenv("PLUGARR_NO_SELF_UPDATE", raising=False)
    monkeypatch.setattr(
        selfupdate, "check",
        lambda: {"current": "0.10.0", "latest": "v0.11.0", "available": True,
                 "verified_asset": True, "installateur": True},
    )
    monkeypatch.setattr(selfupdate, "stage", lambda info: pytest.fail("aucun remplacement sur place"))

    selfupdate.startup()

    assert "v0.11.0" in capsys.readouterr().out


def test_le_remplacement_sur_place_refuse_une_version_installee(monkeypatch):
    monkeypatch.setattr(selfupdate.sys, "platform", "win32")
    monkeypatch.setattr(selfupdate.sys, "frozen", True, raising=False)
    monkeypatch.delenv("PLUGARR_NO_SELF_UPDATE", raising=False)
    monkeypatch.setattr(chemins, "installe", lambda: True)

    with pytest.raises(ValueError, match="installateur"):
        selfupdate._stage({})


# -------------------------------------------------------------- coherence


def test_le_gestionnaire_porte_le_meme_nom_partout():
    nom = re.search(r'NOM_GESTIONNAIRE = "([^"]+)"', LANCEUR).group(1)

    assert f'name="{nom}"' in SPEC
    assert f"{{app}}\\{nom}.exe" in ISS
    assert f"{nom}.exe" in WORKFLOW


def test_le_moteur_porte_le_meme_nom_partout():
    assert 'name="plugarr",' in SPEC
    assert "{app}\\plugarr.exe" in ISS
    # C'est ce nom que `chemins.moteur()` cherche a cote du gestionnaire.
    assert '"plugarr.exe"' in (RACINE / "src" / "plugarr" / "chemins.py").read_text(encoding="utf-8")


def test_l_installateur_porte_le_nom_que_la_mise_a_jour_cherche():
    modele = re.search(r"OutputBaseFilename=(\S+)", ISS).group(1)

    assert modele.replace("{#Version}", "1.2.3") + ".exe" == selfupdate.nom_installateur("v1.2.3")
    assert "PlugArr-Setup-$env:VERSION.exe" in WORKFLOW


def test_l_option_de_relance_est_celle_que_lit_le_script():
    assert "{param:RELANCER|0}" in ISS
    assert "/RELANCER=1" in (RACINE / "src" / "plugarr" / "selfupdate.py").read_text(encoding="utf-8")


def test_l_installateur_ferme_le_gestionnaire_par_la_commande_qui_existe():
    from typer.testing import CliRunner

    from plugarr.cli import app

    assert "'manager --quitter'" in ISS
    resultat = CliRunner().invoke(app, ["manager", "--help"])
    assert "--quitter" in resultat.output


def test_l_installation_se_fait_sans_droits_administrateur():
    assert re.search(r"^PrivilegesRequired=lowest$", ISS, re.MULTILINE)
    assert re.search(r"^DefaultDirName=\{autopf\}\\PlugArr$", ISS, re.MULTILINE)


def test_la_desinstallation_ne_touche_pas_aux_donnees():
    """Ni section [UninstallDelete], ni suppression de %LOCALAPPDATA%\\plugarr :
    `stack.yml` est la seule copie en clair de mots de passe haches ailleurs."""
    assert "[UninstallDelete]" not in ISS
    code = ISS.split("[Code]", 1)[1]
    assert "DelTree" not in code
    assert "{localappdata}\\plugarr" in code, "le message de fin doit dire ou sont les donnees"


def test_l_ancien_runtime_est_retire_avant_la_copie():
    assert re.search(r'Type: filesandordirs; Name: "\{app\}\\_internal"', ISS)


def test_l_identifiant_de_l_application_ne_change_pas():
    """Le changer ferait installer chaque nouvelle version A COTE de l'ancienne."""
    assert "AppId={{8C5B2E57-3E1F-4B8A-9D3A-6F1B2C7A9E41}" in ISS


def test_le_script_inno_est_en_utf8_avec_bom():
    """Sans BOM, Inno Setup lit le script comme de l'ANSI et abime les accents
    des messages de l'installateur."""
    assert (RACINE / "packaging" / "installer" / "plugarr.iss").read_bytes()[:3] == b"\xef\xbb\xbf"


def test_le_fichier_portable_reste_publie():
    assert "dist/plugarr.exe" in WORKFLOW.split("Publier sur la release", 1)[1]
