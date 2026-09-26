"""Windows release updater. Never replaces the executable before its parent exits.

Deux voies, selon la facon dont PlugArr a ete pose :

- **executable portable** (`plugarr.exe` seul, telecharge a la main) : il se
  remplace lui-meme a sa fermeture, comme depuis la 0.8. Les executables deja
  distribues cherchent un fichier de release nomme EXACTEMENT `plugarr.exe` :
  il faut continuer de le publier, sans quoi ils restent sur leur version en
  disant seulement « mise a jour ignoree » ;
- **version installee** (installateur Inno Setup) : on telecharge le nouvel
  installateur, on verifie son empreinte, et on le lance en silencieux. Il
  remplace le dossier des programmes et ne touche pas aux donnees. Rien ne se
  fait a la fermeture d'une commande : c'est le gestionnaire qui propose la
  mise a jour, et l'utilisateur qui la lance.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import httpx

from . import __version__

REPOSITORY = "yannickuhrig1/plugarr"
API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MAX_BYTES = 250 * 1024 * 1024
_STAGE_LOCK = threading.Lock()
_STAGED = None


def version(value: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"v?\d+\.\d+\.\d+", value):
        raise ValueError("Version stable non reconnue")
    return tuple(map(int, value.removeprefix("v").split(".")))


#: Nom du fichier de release que les executables portables remplacent.
ASSET_PORTABLE = "plugarr.exe"


def nom_installateur(tag: str) -> str:
    """Nom de l'installateur publie pour une version : `PlugArr-Setup-0.11.0.exe`."""
    return f"PlugArr-Setup-{tag.removeprefix('v')}.exe"


def check(*, installateur: bool | None = None) -> dict:
    """Derniere release stable, et le fichier qui convient a CE PlugArr.

    `installateur` vaut par defaut « PlugArr a-t-il ete installe ? ». Une
    version installee ne se remplace pas fichier par fichier : elle attend
    l'installateur de la nouvelle version, qui sait aussi retirer ce qui a
    disparu et tenir a jour l'entree d'« Applications installees ».
    """
    if installateur is None:
        from .chemins import installe

        installateur = installe()
    with httpx.Client(timeout=10, follow_redirects=False) as client:
        response = client.get(API, headers={"Accept": "application/vnd.github+json"})
        response.raise_for_status()
        release = response.json()
    tag = release["tag_name"]
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("La release n'est pas stable")
    nom = nom_installateur(tag) if installateur else ASSET_PORTABLE
    assets = [a for a in release.get("assets", []) if a.get("name") == nom]
    asset = assets[0] if len(assets) == 1 else {}
    url = asset.get("browser_download_url", "")
    expected = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{nom}"
    digest = asset.get("digest") or ""
    ready = url == expected and bool(re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest))
    return {"current": __version__, "latest": tag,
            "available": version(tag) > version(__version__), "verified_asset": ready,
            "url": url if ready else "", "digest": digest if ready else "",
            "size": asset.get("size", 0), "notes": str(release.get("body") or "")[:12000],
            "release_url": f"https://github.com/{REPOSITORY}/releases/tag/{tag}",
            "installateur": installateur, "asset": nom}


def telecharger_installateur(info: dict) -> Path:
    """Telecharge et verifie l'installateur dans le dossier des mises a jour.

    Les memes garde-fous que pour l'executable portable : adresse attendue,
    taille annoncee, empreinte SHA256 publiee par GitHub, en-tete `MZ`. Un
    fichier du meme nom laisse par un essai precedent est remplace : il n'a
    peut-etre jamais ete verifie.
    """
    if not info.get("installateur"):
        raise ValueError("Cette version n'a pas ete installee par l'installateur")
    from .chemins import mises_a_jour

    dossier = mises_a_jour()
    dossier.mkdir(parents=True, exist_ok=True)
    cible = dossier / str(info["asset"])
    if cible.name != nom_installateur(str(info["latest"])):
        raise ValueError("Nom d'installateur inattendu")
    cible.unlink(missing_ok=True)
    download(info, cible)
    return cible


#: Options de l'installateur pour une mise a jour. `/RELANCER=1` est lu par le
#: script Inno : il rouvre le gestionnaire une fois les fichiers remplaces.
OPTIONS_SILENCIEUSES = ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/SP-")


def lancer_installateur(setup: Path, *, relancer: bool = True) -> None:
    """Lance l'installateur, detache : il doit survivre a notre fermeture.

    L'appelant se ferme juste apres. `CloseApplications` de l'installateur
    s'occupe de ce qui tournerait encore, mais on prefere ne pas compter sur
    lui : le gestionnaire ferme d'abord ses consoles.
    """
    if sys.platform != "win32":
        raise ValueError("L'installateur ne concerne que Windows")
    args = [str(setup), *OPTIONS_SILENCIEUSES]
    if relancer:
        args.append("/RELANCER=1")
    subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=0x00000008 | 0x00000200,  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    )


def download(info: dict, destination: Path) -> None:
    if not info["verified_asset"] or not info["available"]:
        raise ValueError("Aucune mise a jour verifiable")
    if not 0 < info["size"] <= MAX_BYTES:
        raise ValueError("Taille du binaire refusee")
    digest = hashlib.sha256()
    size = 0
    created = False
    try:
        with httpx.stream("GET", info["url"], timeout=60, follow_redirects=True) as response:
            response.raise_for_status()
            if response.url.scheme != "https":
                raise ValueError("Telechargement non chiffre refuse")
            with destination.open("xb") as stream:
                created = True
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > info["size"] or size > MAX_BYTES:
                        raise ValueError("Binaire trop volumineux")
                    digest.update(chunk)
                    stream.write(chunk)
        if size != info["size"] or "sha256:" + digest.hexdigest() != info["digest"].lower():
            raise ValueError("L'integrite du telechargement n'est pas verifiee")
        with destination.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise ValueError("Ce fichier n'est pas un executable Windows")
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise


def stage(info: dict) -> Path:
    global _STAGED
    with _STAGE_LOCK:
        if _STAGED is None:
            _STAGED = _stage(info)
        return _STAGED


def _stage(info: dict) -> Path:
    if os.environ.get("PLUGARR_NO_SELF_UPDATE") == "1":
        raise ValueError("Mise a jour desactivee dans ce binaire de test local")
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        raise ValueError("La mise a jour automatique concerne uniquement plugarr.exe Windows")
    from .chemins import installe

    if installe():
        # Remplacer plugarr.exe seul laisserait le gestionnaire et le runtime
        # partage sur l'ancienne version : c'est le travail de l'installateur.
        raise ValueError("Version installee : la mise a jour passe par l'installateur")
    executable = Path(sys.executable).resolve()
    # Same volume for atomic moves, unique directory to prevent concurrent staging.
    directory = Path(tempfile.mkdtemp(prefix=".plugarr-update-", dir=executable.parent))
    target = directory / "plugarr.exe"
    try:
        download(info, target)
    except Exception:
        shutil.rmtree(directory)
        raise
    script = directory / "install.ps1"
    # Values are JSON data, never interpolated into PowerShell source.
    (directory / "update.json").write_text(json.dumps({
        "parent": os.getpid(), "executable": str(executable), "candidate": str(target),
        "backup": str(executable) + ".previous", "digest": info["digest"][7:],
    }), encoding="utf-8")
    script.write_text(r'''$ErrorActionPreference = 'Stop'
$c = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'update.json') -Raw | ConvertFrom-Json
try {
    Wait-Process -Id $c.parent -ErrorAction SilentlyContinue
    if ((Get-FileHash -LiteralPath $c.candidate -Algorithm SHA256).Hash -ne $c.digest) {
        throw 'Integrity check failed'
    }
    # The PyInstaller parent or antivirus may briefly keep the executable open.
    # ReplaceFile preserves destination permissions and keeps the old executable.
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            [System.IO.File]::Replace($c.candidate, $c.executable, $c.backup)
            break
        } catch [System.IO.IOException] {
            if ($attempt -eq 59) { throw }
            Start-Sleep -Milliseconds 500
        }
    }
    Remove-Item -LiteralPath $PSScriptRoot -Recurse -Force
} catch {
    $_.Exception.Message | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'error.txt')
}
''', encoding="utf-8-sig")
    command = "$updateDirectory = $env:PLUGARR_UPDATE_DIRECTORY\n" + script.read_text(encoding="utf-8-sig").replace("$PSScriptRoot", "$updateDirectory")
    subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                     env={**os.environ, "PLUGARR_UPDATE_DIRECTORY": str(directory)},
                     creationflags=0x08000000, close_fds=True)
    return directory


def startup() -> None:
    """Verifie GitHub a chaque lancement du binaire Windows.

    La verification etait limitee au double-clic sans argument. Les lanceurs
    fournis (`web`, `wizard` ou `--interface web`) la contournaient donc alors
    qu'ils sont precisement la facon normale d'ouvrir l'application. Les
    executions depuis les sources restent volontairement hors champ : elles
    n'ont aucun executable atomique a remplacer.
    """
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    if os.environ.get("PLUGARR_NO_SELF_UPDATE") == "1":
        return
    try:
        info = check()
        if info.get("installateur"):
            # Version installee : se remplacer seul a la fermeture d'une
            # commande fermerait aussi, sans prevenir, le gestionnaire et ses
            # consoles. On annonce ; le gestionnaire propose l'installation.
            if info["available"]:
                print(
                    f"PlugArr {info['latest']} est disponible (vous avez la {info['current']}). "
                    "Ouvrez PlugArr depuis le menu Demarrer pour l'installer."
                )
            else:
                print(f"PlugArr {info['current']} est a jour (GitHub : {info['latest']}).")
            return
        if info["available"] and info["verified_asset"]:
            print(
                f"Mise a jour PlugArr : {info['current']} -> {info['latest']} ; "
                "telechargement et verification en cours...",
                flush=True,
            )
            stage(info)
            print(f"PlugArr {info['latest']} telecharge et verifie. Installation automatique "
                  "a la fermeture ; disponible au prochain lancement.")
        elif info["available"]:
            print(
                f"PlugArr {info['current']} ; version {info['latest']} disponible, "
                "mais son executable n'a pas pu etre verifie. Mise a jour ignoree."
            )
        else:
            print(f"PlugArr {info['current']} est a jour (GitHub : {info['latest']}).")
    except Exception:  # noqa: BLE001 - keep API/worker failures contained and secrets out of responses
        # An offline machine must still be able to launch the installer.
        print("Recherche de mise a jour indisponible ; lancement de la version installee.")
