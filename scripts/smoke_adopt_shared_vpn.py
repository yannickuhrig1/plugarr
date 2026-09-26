"""Disposable Docker check for adopting qBittorrent behind a shared VPN network."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from smoke_adopt_docker import BASE_IMAGE, SCRATCH_ROOT, docker

from plugarr import discovery

EXE = SCRATCH_ROOT.parent / "dist" / "plugarr-0.10.0-adopt-vpn-smoke-test.exe"


def main() -> None:
    if not EXE.is_file():
        raise RuntimeError("L'EXE de test VPN est absent.")
    if os.environ.get("DOCKER_HOST") or os.environ.get("DOCKER_CONTEXT"):
        raise RuntimeError("Contexte Docker surcharge ; test local refuse.")
    context = docker("context", "show").stdout.strip()
    details = json.loads(docker("context", "inspect", context).stdout)
    endpoint = details[0]["Endpoints"]["docker"]["Host"]
    if not endpoint.startswith("npipe:////./pipe/docker"):
        raise RuntimeError("Le test exige le moteur Docker local Windows.")

    token = uuid.uuid4().hex[:12]
    owner_name = f"plugarr-vpn-owner-smoke-{token}"
    qbit_name = f"plugarr-qbit-{token}"
    qbit_image = f"qbittorrent:plugarr-smoke-{token}"
    SCRATCH_ROOT.mkdir(exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="vpn-owner-smoke-", dir=SCRATCH_ROOT))
    if not scratch.resolve().is_relative_to(SCRATCH_ROOT.resolve()):
        raise RuntimeError("Dossier temporaire hors de l'espace de test.")
    settings = scratch / "qBittorrent" / "qBittorrent.conf"
    settings.parent.mkdir()
    settings.write_text("[Preferences]\nWebUI\\Port=8090\n", encoding="utf-8")

    owner_id = ""
    qbit_id = ""
    tagged = False
    try:
        if docker("image", "inspect", BASE_IMAGE, check=False).returncode:
            docker("pull", BASE_IMAGE)
        if docker("image", "inspect", qbit_image, check=False).returncode == 0:
            raise RuntimeError("Le tag de test existe deja ; suppression refusee.")
        docker("tag", BASE_IMAGE, qbit_image)
        tagged = True
        owner_id = docker(
            "run", "-d", "--rm", "--name", owner_name,
            "--label", "plugarr.smoke=shared-vpn-owner", "--read-only",
            "--publish", "127.0.0.1::8090", BASE_IMAGE,
            "python", "-m", "http.server", "8090", "--bind", "0.0.0.0",
        ).stdout.strip()
        qbit_id = docker(
            "run", "-d", "--rm", "--name", qbit_name,
            "--label", "plugarr.smoke=shared-vpn-client", "--read-only",
            "--network", f"container:{owner_id}",
            "--mount", f"type=bind,source={scratch},target=/config,readonly",
            qbit_image, "python", "-c", "import time; time.sleep(120)",
        ).stdout.strip()

        published = docker("port", owner_name, "8090/tcp").stdout.strip()
        port = int(published.rsplit(":", 1)[1])
        inspected = json.loads(docker("inspect", qbit_id).stdout)[0]
        if (inspected.get("NetworkSettings") or {}).get("Ports"):
            raise RuntimeError("Le faux qBittorrent publie un port directement.")

        original_docker = discovery._docker
        try:
            discovery._docker = lambda *args, **kw: (
                f"{owner_id}\n{qbit_id}\n" if args[0] == "ps"
                else original_docker(*args, **kw)
            )
            entries = discovery.scan()
        finally:
            discovery._docker = original_docker
        matching = [entry for entry in entries if entry.container == qbit_name]
        if len(matching) != 1 or matching[0].host_port != port or not matching[0].usable:
            raise RuntimeError("Le port publie par le VPN n'a pas ete attribue a qBittorrent.")
        packaged = subprocess.run(
            [str(EXE), "scan"], capture_output=True, text=True, errors="replace", check=False,
        )
        if packaged.returncode or qbit_name not in packaged.stdout or str(port) not in packaged.stdout:
            raise RuntimeError(f"L'EXE n'a pas confirme le port VPN (code {packaged.returncode}).")
        print(f"OK : qBittorrent detecte derriere le reseau VPN, port local {port}.")
    finally:
        if qbit_id:
            docker("stop", qbit_id, check=False)
        if owner_id:
            docker("stop", owner_id, check=False)
        if tagged:
            docker("image", "rm", qbit_image, check=False)
        if (
            scratch.resolve().is_relative_to(SCRATCH_ROOT.resolve())
            and scratch.name.startswith("vpn-owner-smoke-")
        ):
            shutil.rmtree(scratch)


if __name__ == "__main__":
    main()
