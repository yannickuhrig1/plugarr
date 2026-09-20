"""Optional remote gateway, activated separately from the media installation.

No remote endpoint is reported as verified merely because Docker started.
The generated sidecar never serves the private access report.
"""
from __future__ import annotations

import ipaddress
import json
import shutil
import socket
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml

from . import catalog, runner

SUPPORTED = ("sonarr", "radarr", "qbittorrent")
CADDY_IMAGE = "caddy:2.11.4-alpine"
# Official stable channel; the actual image ID is recorded by Docker.
TAILSCALE_IMAGE = "tailscale/tailscale:stable"


def external_urls(cfg, address=""):
    result = {}
    for sid in SUPPORTED:
        if not cfg.enabled(sid):
            continue
        if cfg.remote_access.mode == "https" and sid in cfg.remote_access.services:
            prefix = "qb" if sid == "qbittorrent" else sid
            result[sid] = f"https://{prefix}.{cfg.remote_access.domain}"
        elif cfg.remote_access.mode == "tailscale" and address:
            host = f"[{address}]" if ":" in address else address
            result[sid] = cfg.services[sid].url(host)
    return result


def summary(cfg, *, demo=False):
    return {"mode": cfg.remote_access.mode, "status": "local" if cfg.remote_access.mode == "local" else "pending",
            "message": "Accès local uniquement." if cfg.remote_access.mode == "local" else "À activer après l’installation des applications.",
            "urls": {}, "demo": demo, "auth_url": ""}


def _folder(project_dir):
    return Path(project_dir) / ".plugarr-remote"


def _command(cfg, project_dir, *args, timeout=30):
    _check_owned(_folder(project_dir))
    result = runner._run(["docker", "compose", "-p", cfg.project_name + "-remote", "-f",
                          str(_folder(project_dir) / "compose.yml"), *args], timeout=timeout)
    if result.returncode:
        # Docker output can contain association URLs. Do not echo it to logs.
        raise ValueError("La passerelle distante n’a pas démarré. Vérifiez Docker, les ports 80/443 et réessayez.")
    return result.stdout


def _private_write(path, text):
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)


def _check_owned(directory):
    path = directory / "compose.yml"
    if path.exists():
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(config, dict) or config.get("services", {}).get("gateway", {}).get("labels", {}).get("plugarr.remote") != "true":
            raise ValueError("Ce dossier contient une passerelle non gérée par PlugArr. Aucun remplacement effectué.")


def deactivate(cfg, project_dir, *, demo=False):
    if not demo and (_folder(project_dir) / "compose.yml").exists():
        _command(cfg, project_dir, "down", timeout=60)
    result = summary(cfg, demo=demo)
    result.update(status="disabled", urls={}, message="Désactivation simulée." if demo else "Passerelle Docker PlugArr arrêtée. Une connexion Tailscale native éventuelle reste gérée par Tailscale.")
    return result


def gateway_compose(cfg):
    """Only the gateway: no application recreation or mount of the project folder."""
    root = str(Path(cfg.config_root) / "plugarr-remote").replace("\\", "/")
    base = {"restart": "unless-stopped", "labels": {"plugarr.remote": "true"}}
    if cfg.remote_access.mode == "tailscale":
        base.update(image=TAILSCALE_IMAGE, network_mode="host", cap_add=["NET_ADMIN", "NET_RAW"],
                    devices=["/dev/net/tun:/dev/net/tun"],
                    volumes=[f"{root}/tailscale:/var/lib/tailscale"],
                    entrypoint=["/usr/local/bin/tailscaled"],
                    command=["--state=/var/lib/tailscale/tailscaled.state", "--socket=/tmp/tailscaled.sock"])
        return {"services": {"gateway": base}}
    base.update(image=CADDY_IMAGE, ports=["80:80", "443:443"],
                volumes=["./Caddyfile:/etc/caddy/Caddyfile:ro", f"{root}/caddy-data:/data", f"{root}/caddy-config:/config"],
                networks=["applications"])
    return {"services": {"gateway": base},
            "networks": {"applications": {"external": True, "name": cfg.project_name + "_plugarr"}}}


def caddyfile(cfg):
    blocks = ["# Managed by PlugArr. Private credentials are never served here.", "{\n admin off\n}"]
    for sid, url in external_urls(cfg).items():
        inst = cfg.services[sid]
        if inst.adopted or inst.url_base:
            raise ValueError("L’accès HTTPS automatique est réservé aux services gérés par PlugArr, sans sous-chemin.")
        upstream = inst.internal_url(catalog.get(sid), cfg.host, behind_vpn=cfg.vpn.protects(sid))
        blocks.append(f"{urlsplit(url).hostname} {{\n reverse_proxy {upstream}\n}}")
    return "\n\n".join(blocks) + "\n"


def _protect_applications(cfg, directory):
    """Refuse unsafe public auth, and preserve qB settings before hardening."""
    for sid in cfg.remote_access.services:
        inst = cfg.services[sid]
        if inst.adopted:
            raise ValueError("Un service adopté doit être configuré séparément avant publication.")
        if sid in ("sonarr", "radarr"):
            with httpx.Client(base_url=inst.url(cfg.host), timeout=8, trust_env=False) as client:
                response = client.get("/api/v3/config/host", headers={"X-Api-Key": inst.api_key or ""})
                response.raise_for_status()
                host = response.json()
                if str(host.get("authenticationRequired", "")).lower() != "enabled" or str(host.get("authenticationMethod", "")).lower() in ("", "none", "external"):
                    raise ValueError(f"Activez l’authentification pour toutes les adresses dans {sid} avant publication.")
        else:
            from .clients.qbittorrent import QBittorrentClient
            with QBittorrentClient(inst.url(cfg.host), inst.username or "", inst.password or "") as client:
                client.login()
                old = client.preferences()
                desired = {"web_ui_csrf_protection_enabled": True,
                           "web_ui_host_header_validation_enabled": True,
                           "bypass_local_auth": False, "bypass_auth_subnet_whitelist_enabled": False}
                if any(k not in old for k in desired):
                    raise ValueError("Cette version de qBittorrent ne permet pas de vérifier ses protections WebUI.")
                # Keep existing accepted domains; append the proxy domain and internal aliases.
                existing = str(old.get("web_ui_domain_list", ""))
                hosts = [h for h in existing.split(";") if h and h != "*"]
                hosts += [cfg.host, "localhost", "qbittorrent", "gluetun", "qb." + cfg.remote_access.domain]
                desired["web_ui_domain_list"] = ";".join(dict.fromkeys(hosts))
                backup = directory / "qbittorrent-web-before.json"
                if not backup.exists():
                    _private_write(backup, json.dumps({k: old.get(k) for k in desired}, indent=2))
                client._http.headers.update({"Referer": inst.url(cfg.host) + "/", "Origin": inst.url(cfg.host)})
                response = client._http.post("/api/v2/app/setPreferences", data={"json": json.dumps(desired)})
                response.raise_for_status()
                actual = client.preferences()
                if any(actual.get(k) != v for k, v in desired.items()):
                    raise ValueError("Les protections qBittorrent n’ont pas été confirmées. HTTPS non activé.")


def activate(cfg, project_dir, *, demo=False):
    if demo:
        result = summary(cfg, demo=True)
        result.update(status="simulated", message="Simulation : aucune passerelle n’a été installée.",
                      urls=external_urls(cfg, "100.101.102.103"))
        return result
    if cfg.remote_access.mode == "local":
        return summary(cfg)
    if cfg.remote_access.mode == "tailscale":
        # Reuse a native Tailscale connection rather than start a second daemon.
        if shutil.which("tailscale"):
            proc = runner._run(["tailscale", "status", "--json"], timeout=10)
            if proc.returncode == 0:
                return _tailscale_result(cfg, json.loads(proc.stdout))
            raise ValueError("Tailscale est installé : connectez-le à votre compte puis actualisez.")
        if not Path("/dev/net/tun").exists():
            raise ValueError("Installez et connectez Tailscale sur ce serveur, puis actualisez. L’installation automatique requiert Linux et /dev/net/tun.")
    directory = _folder(project_dir)
    directory.mkdir(parents=True, exist_ok=True)
    _check_owned(directory)
    config = gateway_compose(cfg)
    if cfg.remote_access.mode == "https":
        rendered = caddyfile(cfg)
        for url in external_urls(cfg).values():
            try:
                socket.getaddrinfo(urlsplit(url).hostname, 443)
            except OSError as exc:
                raise ValueError("Configurez le DNS des sous-domaines vers votre connexion publique, puis réessayez.") from exc
        _protect_applications(cfg, directory)
        _private_write(directory / "Caddyfile", rendered)
    _private_write(directory / "compose.yml", yaml.safe_dump(config, sort_keys=False))
    _command(cfg, project_dir, "up", "-d", "--force-recreate", timeout=240)
    if cfg.remote_access.mode == "tailscale":
        # Login command may return a timeout while the human authorizes the node.
        runner._run(["docker", "compose", "-p", cfg.project_name + "-remote", "-f",
                     str(directory / "compose.yml"), "exec", "-T", "gateway", "/usr/local/bin/tailscale",
                     "--socket=/tmp/tailscaled.sock", "up", "--json", "--timeout=5s"], timeout=15)
    return inspect(cfg, project_dir)


def _tailscale_result(cfg, data):
    result = summary(cfg)
    auth_url = data.get("AuthURL", "")
    parts = urlsplit(auth_url)
    if parts.scheme == "https" and parts.hostname == "login.tailscale.com":
        result["auth_url"] = auth_url
    ips = data.get("TailscaleIPs") or []
    valid = []
    for value in ips:
        try:
            ip = ipaddress.ip_address(value)
            if ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10"):
                valid.append(str(ip))
        except ValueError:
            continue
    if data.get("BackendState") == "Running" and valid:
        result.update(status="connected", message="Serveur connecté à Tailscale. Connectez vos appareils au même réseau privé. Accès mobile encore à tester.", urls=external_urls(cfg, valid[0]))
    else:
        result.update(status="association", message="Autorisez ce serveur dans Tailscale, puis cliquez sur Actualiser. Une approbation de l’appareil peut aussi être requise.")
    return result


def inspect(cfg, project_dir, *, demo=False):
    if demo:
        return activate(cfg, project_dir, demo=True)
    if cfg.remote_access.mode == "local":
        return summary(cfg)
    if cfg.remote_access.mode == "tailscale":
        if shutil.which("tailscale"):
            proc = runner._run(["tailscale", "status", "--json"], timeout=10)
            if proc.returncode:
                raise ValueError("Tailscale n’est pas connecté sur le serveur.")
            raw = proc.stdout
        else:
            raw = _command(cfg, project_dir, "exec", "-T", "gateway", "/usr/local/bin/tailscale", "--socket=/tmp/tailscaled.sock", "status", "--json")
        return _tailscale_result(cfg, json.loads(raw))
    result = summary(cfg)
    urls = external_urls(cfg)
    checks = []
    for sid, url in urls.items():
        try:
            with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client:
                path = "/api/v2/app/preferences" if sid == "qbittorrent" else "/api/v3/system/status"
                response = client.get(url + path)
                ok = response.status_code in (401, 403)
        except httpx.HTTPError:
            ok = False
        checks.append({"service": sid, "ok": ok})
    good = all(c["ok"] for c in checks) and bool(checks)
    result.update(status="checked" if good else "pending", urls=urls, checks=checks,
                  message="HTTPS répond depuis le serveur et refuse l’API anonyme. Testez maintenant depuis votre téléphone en 4G/5G." if good else "HTTPS reste à vérifier : DNS, certificat, ports de la box ou authentification. La stack locale reste disponible.")
    return result
