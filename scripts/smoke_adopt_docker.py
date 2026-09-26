"""Disposable Windows Docker smoke test for the PlugArr preview executable.

Run from the user's normal PowerShell, where Docker Desktop is accessible.
Only the uniquely named test container, image alias, and local scratch folder
created here are removed. Existing containers, images and media are untouched.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRATCH_ROOT = ROOT / ".codex-tmp"
EXE = ROOT / "dist" / "plugarr-0.10.0-adopt-docker-smoke-v2-test.exe"
BASE_IMAGE = "python:3.12-alpine"
MOCK = ROOT / "scripts" / "fixtures" / "adopt_mock_server.py"


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, capture_output=True, text=True, errors="replace", check=False)
    if check and result.returncode:
        raise RuntimeError(f"Commande echouee : {args[0]} {args[1]}\n{result.stderr.strip()}")
    return result


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run("docker", *args, check=check)


def config_xml(key: str) -> str:
    return f"<Config><ApiKey>{key}</ApiKey><UrlBase></UrlBase></Config>\n"


def wait_api(port: int, key: str) -> None:
    url = f"http://127.0.0.1:{port}/api/v3/system/status"
    for _ in range(40):
        try:
            request = urllib.request.Request(url, headers={"X-Api-Key": key})
            with urllib.request.urlopen(request, timeout=1) as response:
                if json.load(response).get("version") == "4.0.0-smoke":
                    return
        except (OSError, ValueError):
            time.sleep(0.5)
    raise RuntimeError("Le serveur factice n'a pas repondu en 20 secondes.")


def main() -> int:
    if not EXE.is_file() or not MOCK.is_file():
        raise RuntimeError("EXE ou serveur factice absent du depot PlugArr.")
    if socket.gethostbyname("localhost.") != "127.0.0.1":
        raise RuntimeError("localhost. ne resout pas vers 127.0.0.1 sur ce PC.")
    if os.environ.get("DOCKER_HOST") or os.environ.get("DOCKER_CONTEXT"):
        raise RuntimeError("Contexte Docker surcharge par l'environnement ; test local refuse.")
    context = docker("context", "show").stdout.strip()
    details = json.loads(docker("context", "inspect", context).stdout)
    endpoint = details[0]["Endpoints"]["docker"]["Host"]
    if not endpoint.startswith("npipe:////./pipe/docker"):
        raise RuntimeError("Ce contexte Docker n'utilise pas le moteur local Windows.")
    docker("version", "--format", "{{.Server.Version}}")
    SCRATCH_ROOT.mkdir(exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="adopt-smoke-", dir=SCRATCH_ROOT))
    if not scratch.resolve().is_relative_to(SCRATCH_ROOT.resolve()):
        raise RuntimeError("Dossier temporaire hors de l'espace de test.")

    token = uuid.uuid4().hex[:12]
    name = f"plugarr-adopt-smoke-{token}"
    image = f"sonarr:plugarr-smoke-{token}"
    key = uuid.uuid4().hex
    config = scratch / "config"
    data = scratch / "data"
    config.mkdir()
    data.mkdir()
    (config / "config.xml").write_text(config_xml(key), encoding="utf-8")
    created_id = ""
    tagged = False
    try:
        if docker("image", "inspect", BASE_IMAGE, check=False).returncode:
            print(f"Telechargement de l'image de test {BASE_IMAGE}...")
            docker("pull", BASE_IMAGE)
        if docker("image", "inspect", image, check=False).returncode == 0:
            raise RuntimeError("Le tag d'image de test existe deja ; aucune suppression ne sera faite.")
        docker("tag", BASE_IMAGE, image)
        tagged = True
        created_id = docker(
            "run", "-d", "--rm", "--name", name,
            "--label", "plugarr.smoke=adopt-api",
            "--read-only",
            "-e", "PYTHONDONTWRITEBYTECODE=1",
            "--publish", "127.0.0.1::8989",
            "--mount", f"type=bind,source={config},target=/config,readonly",
            "--mount", f"type=bind,source={data},target=/data,readonly",
            "--mount", f"type=bind,source={MOCK},target=/mock.py,readonly",
            "-e", f"PLUGARR_SMOKE_KEY={key}", image, "python", "/mock.py",
        ).stdout.strip()
        mapping = docker("port", name, "8989/tcp").stdout.strip()
        port = int(mapping.rsplit(":", 1)[1])
        wait_api(port, key)
        print(f"API factice joignable uniquement en local sur le port {port}.")

        env = os.environ.copy()
        env["NO_PROXY"] = "localhost.,localhost,127.0.0.1"
        env["no_proxy"] = env["NO_PROXY"]
        scanned = subprocess.run(
            [str(EXE), "scan"], capture_output=True, text=True, errors="replace", env=env,
            check=False,
        )
        print(scanned.stdout)
        if scanned.returncode or name not in scanned.stdout or "adoptable" not in scanned.stdout:
            raise RuntimeError("L'EXE n'a pas reconnu le conteneur factice comme adoptable.")

        command = [
            str(EXE), "adopt", "--dry-run", "--host", "localhost.",
            "--data-root", str(data), "--config-root", str(config),
            "--project-dir", str(scratch / "plan"), "--pick", f"sonarr={name}",
        ]
        planned = subprocess.run(
            command, capture_output=True, text=True, errors="replace", env=env, check=False,
        )
        print(planned.stdout)
        if planned.returncode or "4.0.0-smoke" not in planned.stdout:
            raise RuntimeError("Le dry-run n'a pas valide la version de l'API factice.")
        if (scratch / "plan").exists():
            raise RuntimeError("Le dry-run a ecrit un dossier de projet.")

        (config / "config.xml").write_text(config_xml(uuid.uuid4().hex), encoding="utf-8")
        rejected = subprocess.run(
            command, capture_output=True, text=True, errors="replace", env=env, check=False,
        )
        if rejected.returncode != 1 or "Adoption interrompue" not in rejected.stdout:
            print(rejected.stdout)
            raise RuntimeError("Une mauvaise cle API n'a pas bloque le dry-run.")
        if (scratch / "plan").exists():
            raise RuntimeError("Le dry-run avec mauvaise cle a ecrit un dossier de projet.")
        print("OK : decouverte, version API, refus d'une mauvaise cle et zero ecriture.")
        return 0
    except Exception:
        if created_id:
            details = docker("inspect", "--format", "{{json .Mounts}}", created_id, check=False)
            if details.returncode == 0:
                print("Montages du conteneur de test :", details.stdout.strip())
        raise
    finally:
        if created_id:
            docker("stop", created_id, check=False)
        if tagged:
            docker("image", "rm", image, check=False)
        if scratch.resolve().is_relative_to(SCRATCH_ROOT.resolve()) and scratch.name.startswith("adopt-smoke-"):
            shutil.rmtree(scratch)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ECHEC : {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
