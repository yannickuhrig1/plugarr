"""Windows release updater. Never replaces the executable before its parent exits."""
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


def check() -> dict:
    with httpx.Client(timeout=10, follow_redirects=False) as client:
        response = client.get(API, headers={"Accept": "application/vnd.github+json"})
        response.raise_for_status()
        release = response.json()
    tag = release["tag_name"]
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("La release n'est pas stable")
    assets = [a for a in release.get("assets", []) if a.get("name") == "plugarr.exe"]
    asset = assets[0] if len(assets) == 1 else {}
    url = asset.get("browser_download_url", "")
    expected = f"https://github.com/{REPOSITORY}/releases/download/{tag}/plugarr.exe"
    digest = asset.get("digest") or ""
    ready = url == expected and bool(re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest))
    return {"current": __version__, "latest": tag,
            "available": version(tag) > version(__version__), "verified_asset": ready,
            "url": url if ready else "", "digest": digest if ready else "",
            "size": asset.get("size", 0), "notes": str(release.get("body") or "")[:12000],
            "release_url": f"https://github.com/{REPOSITORY}/releases/tag/{tag}"}


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
    """Automatic on interactive exe startup; source runs and CLI jobs are untouched."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False) or len(sys.argv) > 1:
        return
    if os.environ.get("PLUGARR_NO_SELF_UPDATE") == "1":
        return
    try:
        info = check()
        if info["available"] and info["verified_asset"]:
            stage(info)
            print(f"PlugArr {info['latest']} telecharge et verifie. Installation automatique "
                  "a la fermeture ; disponible au prochain lancement.")
    except Exception:  # noqa: BLE001 - keep API/worker failures contained and secrets out of responses
        # An offline machine must still be able to launch the installer.
        print("Recherche de mise a jour indisponible ; lancement de la version installee.")
