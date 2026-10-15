"""Optional remote gateway, activated separately from the media installation.

No remote endpoint is reported as verified merely because Docker started.
The generated sidecar never serves the private access report.
"""
from __future__ import annotations

import ipaddress
import json
import shutil
import socket
import ssl
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml

from . import catalog, runner
from .remote_models import identifiant_tunnel

SUPPORTED = ("sonarr", "radarr", "qbittorrent")
CADDY_IMAGE = "caddy:2.11.4-alpine"
#: Caddy avec le module caddy-dns/cloudflare, construit par PlugArr
#: (packaging/caddy, .github/workflows/caddy.yml) : l'image officielle ne sait
#: pas obtenir de certificat par DNS-01. Le tag suit les versions de la
#: recette ; le condensat s'ajoute a la publication (docs/PLAN_HTTPS_DNS01.md).
CADDY_DNS01_IMAGE = "ghcr.io/yannickuhrig1/plugarr-caddy:2.11.4-cloudflare-0.2.4"
# Official stable channel; the actual image ID is recorded by Docker.
TAILSCALE_IMAGE = "tailscale/tailscale:stable"
#: Connecteur du tunnel Cloudflare. Epingle tag ET digest, comme le catalogue :
#: index multi architecture (amd64, arm64) releve sur Docker Hub le 2026-09-27.
CLOUDFLARED_IMAGE = (
    "cloudflare/cloudflared:2026.9.3"
    "@sha256:072c067d25ccbe61d46e18f0d0723255f2bb5304f7317caa95b27031520ff92c"
)
#: Modes qui publient une adresse HTTPS par application sur le domaine.
DOMAIN_MODES = ("https", "cloudflare")
#: Ligne ecrite par cloudflared pour chaque connexion etablie avec Cloudflare
#: (connection/observer.go), et refus d'un jeton qu'il ne sait pas decoder
#: (cmd/cloudflared/tunnel/subcommands.go).
TUNNEL_CONNECTED = "Registered tunnel connection"
TUNNEL_BAD_TOKEN = "Provided Tunnel token is not valid"
#: API Cloudflare : la zone y est cherchee avec le jeton avant que Caddy ne
#: s'y essaie, lui, sans rien dire ailleurs que dans son journal.
CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"
#: Resolution publique (DoH, format JSON), pour reconnaitre un resolveur local
#: qui bloque les reponses vers une adresse privee.
DOH_URL = "https://cloudflare-dns.com/dns-query"
#: Lignes du journal de Caddy (CertMagic) que l'etat du certificat cherche.
#: Rien d'autre n'en est lu, ni affiche.
CADDY_CERT_OK = "certificate obtained successfully"
CADDY_CERT_ECHEC = "could not get certificate from issuer"
CADDY_PROPAGATION = "timed out waiting for record to fully propagate"
#: Message de l'API Cloudflare (code 10000), repris dans l'erreur de Caddy.
CADDY_JETON_REFUSE = "Authentication error"


def admin_image_ready(remote) -> bool:
    """L'image d'administration epinglee sait-elle lire ce choix ?

    Elle relit le vrai `stack.yml` sur un serveur SSH et dans la console en
    conteneur. Une image qui ne connait ni le tunnel ni les noms refuserait
    toute la pile ; la console, elle, redemarrerait en boucle.
    """
    if remote.dns01 and not catalog.CONSOLE_IMAGE_DNS01:
        return False
    return catalog.CONSOLE_IMAGE_TUNNEL_CLOUDFLARE or (remote.mode != "cloudflare" and not remote.names)


def external_urls(cfg, address=""):
    """En DNS-01, les applications publiees ont leur adresse HTTPS ; les autres
    gardent leur adresse Tailscale par IP."""
    remote = cfg.remote_access
    publiees = _published(cfg)
    port = f":{remote.https_port}" if remote.dns01 and remote.https_port != 443 else ""
    result = {}
    for sid in SUPPORTED:
        if not cfg.enabled(sid):
            continue
        if sid in publiees:
            result[sid] = f"https://{remote.hostname(sid)}{port}"
        elif remote.mode == "tailscale" and address:
            host = f"[{address}]" if ":" in address else address
            result[sid] = cfg.services[sid].url(host)
    return result


def _upstream(cfg, sid):
    inst = cfg.services[sid]
    return inst.internal_url(catalog.get(sid), cfg.host, behind_vpn=cfg.vpn.protects(sid))


def routes(cfg):
    """Routes a declarer dans le tunnel, champ par champ, comme le tableau de
    bord Cloudflare les demande : sous-domaine, domaine, URL du service."""
    if cfg.remote_access.mode != "cloudflare":
        return []
    return [{"service": sid, "subdomain": cfg.remote_access.label(sid), "domain": cfg.remote_access.domain,
             "hostname": cfg.remote_access.hostname(sid), "service_url": _upstream(cfg, sid)}
            for sid in SUPPORTED if sid in cfg.remote_access.services and cfg.enabled(sid)]


def summary(cfg, *, demo=False):
    result = {"mode": cfg.remote_access.mode, "status": "local" if cfg.remote_access.mode == "local" else "pending",
              "message": "Accès local uniquement." if cfg.remote_access.mode == "local" else "À activer après l’installation des applications.",
              "urls": {}, "demo": demo, "auth_url": ""}
    if cfg.remote_access.mode == "cloudflare":
        result.update(routes=routes(cfg), tunnel_id=identifiant_tunnel(cfg.remote_access.tunnel_token))
    return result


def _folder(project_dir):
    return Path(project_dir) / ".plugarr-remote"


def _command(cfg, project_dir, *args, timeout=30):
    _check_owned(_folder(project_dir))
    result = runner._run(["docker", "compose", "-p", cfg.project_name + "-remote", "-f",
                          str(_folder(project_dir) / "compose.yml"), *args], timeout=timeout)
    if result.returncode:
        # Docker output can contain association URLs. Do not echo it to logs.
        if cfg.remote_access.mode == "cloudflare":
            raise ValueError("Le connecteur Cloudflare n’a pas démarré. Vérifiez Docker et réessayez.")
        if cfg.remote_access.dns01:
            raise ValueError(f"La passerelle HTTPS n’a pas démarré. Vérifiez Docker et que le port "
                             f"{cfg.remote_access.https_port} est libre, puis réessayez.")
        raise ValueError("La passerelle distante n’a pas démarré. Vérifiez Docker, les ports 80/443 et réessayez.")
    return result.stdout


def _private_write(path, text):
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)


def _check_owned(directory):
    """Chaque service du compose doit porter l'etiquette de PlugArr : en mode
    DNS-01, Caddy tourne a cote de Tailscale, et le compose peut ne contenir
    que lui quand Tailscale est installe sur la machine."""
    path = directory / "compose.yml"
    if path.exists():
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        services = config.get("services") if isinstance(config, dict) else None
        if not isinstance(services, dict) or not services or any(
            not isinstance(service, dict) or (service.get("labels") or {}).get("plugarr.remote") != "true"
            for service in services.values()
        ):
            raise ValueError("Ce dossier contient une passerelle non gérée par PlugArr. Aucun remplacement effectué.")


def deactivate(cfg, project_dir, *, demo=False):
    if not demo and (_folder(project_dir) / "compose.yml").exists():
        _command(cfg, project_dir, "down", timeout=60)
    result = summary(cfg, demo=demo)
    message = "Désactivation simulée." if demo else "Passerelle Docker PlugArr arrêtée. Une connexion Tailscale native éventuelle reste gérée par Tailscale."
    if cfg.remote_access.mode == "cloudflare" and not demo:
        message = "Connecteur Cloudflare arrêté. Le tunnel et ses routes restent dans votre compte Cloudflare : supprimez-les là-bas si vous n’en voulez plus."
    result.update(status="disabled", urls={}, message=message)
    return result


def gateway_compose(cfg, *, tailscale_natif=False):
    """Only the gateway: no application recreation or mount of the project folder.

    En mode DNS-01, Caddy s'ajoute a Tailscale ; si Tailscale est deja installe
    sur la machine (`tailscale_natif`), Caddy est seul.
    """
    root = str(Path(cfg.config_root) / "plugarr-remote").replace("\\", "/")
    base = {"restart": "unless-stopped", "labels": {"plugarr.remote": "true"}}
    applications = {"applications": {"external": True, "name": cfg.project_name + "_plugarr"}}
    if cfg.remote_access.mode == "tailscale":
        services = {}
        if not tailscale_natif:
            services["gateway"] = {
                **base, "image": TAILSCALE_IMAGE, "network_mode": "host", "cap_add": ["NET_ADMIN", "NET_RAW"],
                "devices": ["/dev/net/tun:/dev/net/tun"],
                "volumes": [f"{root}/tailscale:/var/lib/tailscale"],
                "entrypoint": ["/usr/local/bin/tailscaled"],
                "command": ["--state=/var/lib/tailscale/tailscaled.state", "--socket=/tmp/tailscaled.sock"],
            }
        if not cfg.remote_access.dns01:
            return {"services": services}
        # Seul le TCP est publie, et pas le port 80 : le defi DNS-01 n'en a pas
        # besoin. Le jeton passe par CLOUDFLARE_API_TOKEN, lu dans un fichier
        # prive, jamais dans ce compose ni dans le Caddyfile.
        services["caddy"] = {
            **base, "image": CADDY_DNS01_IMAGE, "env_file": ["./caddy.env"],
            "ports": [f"{cfg.remote_access.https_port}:443"],
            "volumes": ["./Caddyfile:/etc/caddy/Caddyfile:ro", f"{root}/caddy-data:/data", f"{root}/caddy-config:/config"],
            "networks": ["applications"],
        }
        return {"services": services, "networks": applications}
    if cfg.remote_access.mode == "cloudflare":
        # Connexion SORTANTE vers Cloudflare : aucun port publie, rien a
        # rediriger sur la box, et le CGNAT n'y change rien. Les arguments sont
        # ceux de la commande Docker du tableau de bord ; le jeton passe par
        # TUNNEL_TOKEN, lu dans un fichier prive plutot que dans ce compose.
        base.update(image=CLOUDFLARED_IMAGE, command=["tunnel", "--no-autoupdate", "run"],
                    env_file=["./tunnel.env"], networks=["applications"])
        return {"services": {"gateway": base}, "networks": applications}
    base.update(image=CADDY_IMAGE, ports=["80:80", "443:443"],
                volumes=["./Caddyfile:/etc/caddy/Caddyfile:ro", f"{root}/caddy-data:/data", f"{root}/caddy-config:/config"],
                networks=["applications"])
    return {"services": {"gateway": base}, "networks": applications}


def _published(cfg):
    """Applications publiees sur le domaine, dans l'ordre de SUPPORTED."""
    remote = cfg.remote_access
    if remote.mode not in DOMAIN_MODES and not remote.dns01:
        return []
    return [sid for sid in SUPPORTED if sid in remote.services and cfg.enabled(sid)]


def _check_publishable(cfg):
    for sid in _published(cfg):
        inst = cfg.services[sid]
        if inst.adopted or inst.url_base:
            raise ValueError("L’accès HTTPS automatique est réservé aux services gérés par PlugArr, sans sous-chemin.")


def caddyfile(cfg):
    _check_publishable(cfg)
    blocks = ["# Managed by PlugArr. Private credentials are never served here.", "{\n admin off\n}"]
    for sid, url in external_urls(cfg).items():
        blocks.append(f"{urlsplit(url).hostname} {{\n reverse_proxy {_upstream(cfg, sid)}\n}}")
    return "\n\n".join(blocks) + "\n"


def caddyfile_dns01(cfg):
    """Un seul bloc wildcard : un certificat `*.domaine` obtenu par DNS-01, donc
    aucun nom d'application dans les journaux Certificate Transparency.

    Le rendu de reference est `packaging/caddy/essai.Caddyfile`, que la CI fait
    valider par la vraie image ; tests/test_remote_dns01.py verifie qu'ils
    concordent.
    """
    _check_publishable(cfg)
    remote = cfg.remote_access
    lignes = [
        "# Managed by PlugArr. Private credentials are never served here.",
        "{",
        "\tadmin off",
        "\tauto_https disable_redirects",
        # Seul le TCP est publie : sans cela, Caddy annoncerait HTTP/3 sur un
        # port UDP ferme.
        "\tservers {",
        "\t\tprotocols h1 h2",
        "\t}",
        "}",
        "",
        f"*.{remote.domain} {{",
        "\ttls {",
        "\t\tdns cloudflare {env.CLOUDFLARE_API_TOKEN}",
        # Un DNS local (box, Pi-hole) ne doit pas fausser la recherche de zone.
        "\t\tresolvers 1.1.1.1 1.0.0.1",
        # Les valeurs par defaut de Caddy echouent souvent chez Cloudflare
        # (« timed out waiting for record to fully propagate »).
        "\t\tpropagation_delay 2m",
        "\t\tpropagation_timeout 10m",
        "\t}",
        # Le PREMIER `handle` : un `abort` pose a cote passerait apres les
        # `handle`, a cause de l'ordre des directives, et ne filtrerait rien.
        # `private_ranges` n'inclut pas la plage CGNAT de Tailscale.
        "\t@hors_reseau not remote_ip private_ranges 100.64.0.0/10",
        "\thandle @hors_reseau {",
        "\t\tabort",
        "\t}",
    ]
    for sid in _published(cfg):
        lignes += [
            f"\t@{sid} host {remote.hostname(sid)}",
            f"\thandle @{sid} {{",
            f"\t\treverse_proxy {_upstream(cfg, sid)}",
            "\t}",
        ]
    # Un sous-domaine inconnu ne mene nulle part.
    lignes += ["\thandle {", "\t\tabort", "\t}", "}"]
    return "\n".join(lignes) + "\n"


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
                hosts += [cfg.host, "localhost", "qbittorrent", "gluetun", cfg.remote_access.hostname("qbittorrent")]
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
        if cfg.remote_access.dns01:
            result.update(records=_records(cfg, "100.101.102.103"))
        return result
    if not cfg.remote_access.dns01:
        # Avant tout retour anticipe : Tailscale installe sur la machine ne
        # passe pas par l'ecriture du compose, plus bas.
        (_folder(project_dir) / "caddy.env").unlink(missing_ok=True)
    if cfg.remote_access.mode == "local":
        return summary(cfg)
    natif = False
    if cfg.remote_access.mode == "tailscale":
        # Reuse a native Tailscale connection rather than start a second daemon.
        if shutil.which("tailscale"):
            proc = runner._run(["tailscale", "status", "--json"], timeout=10)
            if proc.returncode:
                raise ValueError("Tailscale est installé : connectez-le à votre compte puis actualisez.")
            if not cfg.remote_access.dns01:
                return _tailscale_result(cfg, json.loads(proc.stdout))
            # DNS-01 : Caddy seul, a cote du Tailscale de la machine.
            natif = True
        elif not Path("/dev/net/tun").exists():
            raise ValueError("Installez et connectez Tailscale sur ce serveur, puis actualisez. L’installation automatique requiert Linux et /dev/net/tun.")
    directory = _folder(project_dir)
    directory.mkdir(parents=True, exist_ok=True)
    _check_owned(directory)
    config = gateway_compose(cfg, tailscale_natif=natif)
    if cfg.remote_access.mode == "https":
        rendered = caddyfile(cfg)
        for url in external_urls(cfg).values():
            try:
                socket.getaddrinfo(urlsplit(url).hostname, 443)
            except OSError as exc:
                raise ValueError("Configurez le DNS des sous-domaines vers votre connexion publique, puis réessayez.") from exc
        _protect_applications(cfg, directory)
        _private_write(directory / "Caddyfile", rendered)
    elif cfg.remote_access.mode == "cloudflare":
        # Pas de controle DNS ici : Cloudflare cree l'enregistrement quand on
        # ajoute la route, et le tableau de bord propose de le faire une fois
        # le connecteur en ligne. `inspect` dit ensuite ce qui manque.
        _check_publishable(cfg)
        _protect_applications(cfg, directory)
        _private_write(directory / "tunnel.env", f"TUNNEL_TOKEN={cfg.remote_access.tunnel_token}\n")
    elif cfg.remote_access.dns01:
        rendered = caddyfile_dns01(cfg)
        # Le jeton d'abord : un jeton refuse ne doit rien changer, ni aux
        # protections de qBittorrent, ni aux fichiers.
        _zone_cloudflare(cfg.remote_access)
        _protect_applications(cfg, directory)
        _private_write(directory / "Caddyfile", rendered)
        _private_write(directory / "caddy.env", f"CLOUDFLARE_API_TOKEN={cfg.remote_access.dns_token}\n")
    if cfg.remote_access.mode != "cloudflare":
        # Le compose qu'on ecrit ne le lit plus : ne pas garder un secret inutile.
        (directory / "tunnel.env").unlink(missing_ok=True)
    _private_write(directory / "compose.yml", yaml.safe_dump(config, sort_keys=False))
    _command(cfg, project_dir, "up", "-d", "--force-recreate", timeout=240)
    if cfg.remote_access.mode == "tailscale" and not natif:
        # Login command may return a timeout while the human authorizes the node.
        runner._run(["docker", "compose", "-p", cfg.project_name + "-remote", "-f",
                     str(directory / "compose.yml"), "exec", "-T", "gateway", "/usr/local/bin/tailscale",
                     "--socket=/tmp/tailscaled.sock", "up", "--json", "--timeout=5s"], timeout=15)
    return inspect(cfg, project_dir)


def _tailscale_ip(data):
    """Premiere adresse IPv4 Tailscale (100.64.0.0/10) du serveur, ou vide."""
    for value in data.get("TailscaleIPs") or []:
        try:
            ip = ipaddress.ip_address(value)
        except ValueError:
            continue
        if ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10"):
            return str(ip)
    return ""


def _tailscale_result(cfg, data):
    result = summary(cfg)
    auth_url = data.get("AuthURL", "")
    parts = urlsplit(auth_url)
    if parts.scheme == "https" and parts.hostname == "login.tailscale.com":
        result["auth_url"] = auth_url
    ip = _tailscale_ip(data)
    if data.get("BackendState") == "Running" and ip:
        result.update(status="connected", message="Serveur connecté à Tailscale. Connectez vos appareils au même réseau privé. Accès mobile encore à tester.", urls=external_urls(cfg, ip))
    else:
        result.update(status="association", message="Autorisez ce serveur dans Tailscale, puis cliquez sur Actualiser. Une approbation de l’appareil peut aussi être requise.")
    return result


def _zone_cloudflare(remote):
    """Zone Cloudflare du domaine, trouvee avec le jeton en remontant ses
    etiquettes (`maison.mondomaine.fr`, puis `mondomaine.fr`). Prouve que le
    jeton est accepte et qu'il voit la zone (droit Zone:Read). Le droit
    DNS:Edit ne se verifie qu'en ecrivant : c'est Caddy qui le fera."""
    etiquettes = remote.domain.split(".")
    with httpx.Client(base_url=CLOUDFLARE_API, timeout=10, trust_env=False,
                      headers={"Authorization": f"Bearer {remote.dns_token}"}) as client:
        for debut in range(len(etiquettes) - 1):
            try:
                response = client.get("/zones", params={"name": ".".join(etiquettes[debut:])})
                refuse = response.status_code in (400, 401, 403)
                if not refuse:
                    response.raise_for_status()
                    zones = [z["name"] for z in response.json().get("result") or []]
            except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
                raise ValueError("Cloudflare ne répond pas. Vérifiez l’accès Internet du serveur, "
                                 "puis réessayez.") from exc
            if refuse:
                raise ValueError("Cloudflare refuse ce jeton d’API. Recopiez-le, ou créez-en un "
                                 "nouveau avec les droits Zone:Read et DNS:Edit sur la zone.")
            if zones:
                return zones[0]
    raise ValueError(f"Ce jeton ne voit aucune zone Cloudflare pour {remote.domain}. Le domaine doit être "
                     "géré par Cloudflare, et le jeton avoir le droit Zone:Read sur sa zone.")


def _records(cfg, ip):
    """Enregistrements A a creer chez Cloudflare : un par application publiee,
    vers l'adresse Tailscale du serveur, sans proxy (nuage gris)."""
    return [{"service": sid, "hostname": cfg.remote_access.hostname(sid), "type": "A",
             "content": ip, "proxied": False} for sid in _published(cfg)]


def _resolve_doh(hostname):
    """Adresses IPv4 de `hostname` vues par le DNS public, sans le resolveur
    local. Vide si la question echoue : ce n'est qu'un indice."""
    try:
        with httpx.Client(timeout=8, trust_env=False) as client:
            response = client.get(DOH_URL, params={"name": hostname, "type": "A"},
                                  headers={"Accept": "application/dns-json"})
            response.raise_for_status()
            return {r["data"] for r in response.json().get("Answer") or [] if r.get("type") == 1}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return set()


def _check_dns01(cfg, sid, url, ip):
    """Le nom doit mener a l'adresse Tailscale de CE serveur avant que
    `_check_public` ne teste le certificat et l'authentification."""
    hostname = urlsplit(url).hostname
    try:
        adresses = {info[4][0] for info in socket.getaddrinfo(hostname, None, socket.AF_INET)}
    except OSError:
        adresses = set()
    base = {"service": sid, "ok": False, "ip": ip}
    if not adresses:
        # Le DNS public connait la bonne adresse, le resolveur local la tait :
        # c'est le signe d'une protection contre le DNS rebinding.
        return {**base, "reason": "rebind" if ip in _resolve_doh(hostname) else "dns"}
    if ip not in adresses:
        return {**base, "reason": "wrong_address", "found": sorted(adresses)}
    return {**_check_public(cfg, sid, url), "ip": ip}


def _erreur_tls(exc):
    while exc is not None:
        if isinstance(exc, ssl.SSLError) or "[SSL" in str(exc):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


def _caddy_state(cfg, project_dir):
    """Etat du certificat, lu dans le journal de Caddy. Seules quelques lignes
    connues sont cherchees, la derniere l'emporte ; rien n'est affiche. Apres
    un redemarrage, Caddy recharge son certificat sans rien ecrire : ce
    journal n'explique donc qu'un certificat absent, il ne juge pas."""
    compose = _folder(project_dir) / "compose.yml"
    if not compose.is_file() or CADDY_DNS01_IMAGE not in compose.read_text(encoding="utf-8"):
        return "absent"
    etat = "waiting"
    for ligne in _command(cfg, project_dir, "logs", "--no-color", "--tail", "500", "caddy").splitlines():
        if CADDY_CERT_OK in ligne:
            etat = "obtained"
        elif CADDY_JETON_REFUSE in ligne:
            etat = "token"
        elif CADDY_PROPAGATION in ligne:
            etat = "propagation"
        elif CADDY_CERT_ECHEC in ligne:
            etat = "failed"
    return etat


def _dns01_result(cfg, project_dir, result, ip):
    checks = [_check_dns01(cfg, sid, url, ip) for sid, url in external_urls(cfg).items()]
    if any(c["reason"] == "certificate" for c in checks):
        caddy = _caddy_state(cfg, project_dir)
        checks = [{**c, "caddy": caddy} if c["reason"] == "certificate" else c for c in checks]
    good = all(c["ok"] for c in checks) and bool(checks)
    details = " ".join(_explain(cfg, c) for c in checks if not c["ok"])
    message = ("Adresses HTTPS en place : certificat valide, accès anonyme refusé. Connectez Tailscale sur "
               "le téléphone, puis testez." if good else
               "Adresses HTTPS à terminer. Les adresses Tailscale par IP restent disponibles. " + details)
    result.update(status="checked" if good else "pending", urls=external_urls(cfg, ip), checks=checks,
                  records=_records(cfg, ip), message=message.strip())
    return result


def _check_public(cfg, sid, url):
    """Ce que repond l'adresse publique, vue depuis le serveur.

    Un refus de l'API anonyme ne suffit pas : l'adresse peut mener a une AUTRE
    instance (un ancien `sonarr.` du meme domaine, relie a un autre tunnel). La
    cle API de celle-ci doit donc etre acceptee, et seulement apres le refus
    anonyme : c'est l'adresse que les fiches du telephone utiliseront.
    """
    hostname = urlsplit(url).hostname
    qb = sid == "qbittorrent"
    path = "/api/v2/app/preferences" if qb else "/api/v3/system/status"
    try:
        socket.getaddrinfo(hostname, 443)
    except OSError:
        return {"service": sid, "ok": False, "reason": "dns"}
    try:
        with httpx.Client(timeout=8, trust_env=False, follow_redirects=False) as client:
            response = client.get(url + path)
            # Page de verification anti-robot : la seule valeur possible de
            # `cf-mitigated` est `challenge` (documentation Cloudflare
            # « Detect a Challenge Page response »). Un 403 de qBittorrent
            # anonyme n'a pas cet en-tete.
            if response.headers.get("cf-mitigated") == "challenge":
                return {"service": sid, "ok": False, "reason": "challenge"}
            # qBittorrent 5 repond 403 sans session ; Sonarr et Radarr 401.
            if response.status_code in ((401, 403) if qb else (401,)):
                key = cfg.services[sid].api_key
                if not qb and key:
                    own = client.get(url + path, headers={"X-Api-Key": key})
                    if own.status_code != 200:
                        return {"service": sid, "ok": False, "reason": "other_instance"}
                return {"service": sid, "ok": True, "reason": ""}
    except httpx.HTTPError as exc:
        return {"service": sid, "ok": False, "reason": "certificate" if _erreur_tls(exc) else "unreachable"}
    code = response.status_code
    location = response.headers.get("location", "")
    if 300 <= code < 400 and (urlsplit(location).hostname or "").endswith(".cloudflareaccess.com"):
        reason = "access"
    elif code == 530 or (code >= 500 and "1033" in response.text[:4000]):
        reason = "tunnel"
    elif code in (502, 504):
        reason = "origin"
    elif code == 404:
        reason = "route"
    elif code == 403:
        reason = "blocked"
    elif code == 200:
        reason = "open"
    else:
        reason = f"http {code}"
    return {"service": sid, "ok": False, "reason": reason}


def _explain(cfg, check):
    sid, reason = check["service"], check["reason"]
    name = catalog.get(sid).display_name
    host = cfg.remote_access.hostname(sid)
    tunnel = cfg.remote_access.mode == "cloudflare"
    dns01 = cfg.remote_access.dns01
    ip = check.get("ip", "")
    if dns01:
        enregistrement = f"Créez l’enregistrement A {host} vers {ip}, en DNS only (nuage gris)."
    elif tunnel:
        enregistrement = "Ajoutez sa route dans le tunnel."
    else:
        enregistrement = "Créez l’enregistrement vers votre connexion publique."
    certificat = {
        "absent": "La passerelle HTTPS n’est pas installée : activez l’accès distant.",
        "waiting": "Caddy le demande à Let’s Encrypt : comptez quelques minutes, puis actualisez.",
        "obtained": "Caddy l’a obtenu : actualisez dans un instant.",
        "propagation": "Cloudflare n’avait pas encore propagé le défi DNS. Caddy réessaie seul : actualisez dans quelques minutes.",
        "token": "Cloudflare refuse le jeton d’API à Caddy : il lui faut le droit DNS:Edit sur la zone.",
        "failed": "Caddy n’a pas obtenu le certificat. Il réessaie seul ; vérifiez les droits du jeton d’API.",
    }.get(check.get("caddy", ""),
          "Le certificat gratuit de Cloudflare ne couvre qu’un niveau de sous-domaine : utilisez le "
          "domaine de la zone." if tunnel else
          "Vérifiez que les ports 80 et 443 de la box mènent à ce serveur.")
    texts = {
        "dns": f"{name} : {host} n’existe pas encore dans le DNS. " + enregistrement,
        "wrong_address": f"{name} : {host} mène à {', '.join(check.get('found', []))}, pas à {ip}, l’adresse "
                         "Tailscale de ce serveur. Corrigez l’enregistrement A, en DNS only (nuage gris).",
        "rebind": f"{name} : le DNS public donne bien {ip} pour {host}, mais le résolveur de ce serveur ne "
                  "répond rien. Votre box ou votre résolveur bloque sans doute les adresses privées "
                  "(protection contre le DNS rebinding) : autorisez ce domaine dans ses réglages.",
        "certificate": f"{name} : le certificat de {host} n’est pas encore valide. " + certificat,
        "tunnel": f"{name} : Cloudflare ne trouve aucun connecteur actif pour {host} (tunnel arrêté, ou adresse reliée à un autre tunnel).",
        "origin": f"{name} : Cloudflare joint le serveur mais pas l’application. "
                  + (f"Vérifiez l’URL du service de la route : {_upstream(cfg, sid)}." if tunnel else "Vérifiez que l’application tourne."),
        "route": f"{name} : {host} n’a pas de route vers l’application"
                 + (" dans ce tunnel." if tunnel else "."),
        # Essai reel du 2026-09-27 : une application Access `*.domaine` couvrait
        # toute nouvelle adresse. On ne la retire pas pour une adresse : on
        # ajoute celle-ci a une application en Bypass, qui passe en premier.
        "access": f"{name} : Cloudflare Access protège {host}. Les applications mobiles ne passeront pas : dans Zero Trust, ajoutez cette adresse à une application en Bypass, ou retirez-la de la protection.",
        "challenge": f"{name} : Cloudflare impose une vérification anti-robot sur {host}. Les applications mobiles seraient bloquées : désactivez cette règle pour cette adresse.",
        "blocked": f"{name} : {host} refuse la requête (403) avant l’application. Une règle de sécurité Cloudflare ou un pare-feu la filtre.",
        "other_instance": f"{name} : {host} mène à une autre instance, qui refuse la clé API de celle-ci. Un ancien enregistrement ou un autre tunnel utilise ce nom : choisissez un autre sous-domaine.",
        "open": f"{name} : l’API répond sans identifiants sur {host}. Coupez cet accès avant toute utilisation.",
        "unreachable": f"{name} : {host} ne répond pas en HTTPS.",
    }
    return texts.get(reason, f"{name} : réponse inattendue de {host} ({reason}).")


def _tunnel_state(cfg, project_dir):
    """Etat du connecteur, lu dans son journal. Rien de ce journal n'est
    affiche : seules deux lignes connues sont cherchees."""
    compose = _folder(project_dir) / "compose.yml"
    # Pas encore active, ou passerelle d'un autre mode (Caddy, Tailscale).
    if not compose.is_file() or CLOUDFLARED_IMAGE not in compose.read_text(encoding="utf-8"):
        return "absent"
    logs = _command(cfg, project_dir, "logs", "--no-color", "--tail", "500", "gateway")
    if TUNNEL_CONNECTED in logs:
        return "connected"
    if TUNNEL_BAD_TOKEN in logs:
        return "bad_token"
    return "waiting"


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
        data = json.loads(raw)
        result = _tailscale_result(cfg, data)
        if not cfg.remote_access.dns01 or result["status"] != "connected":
            return result
        return _dns01_result(cfg, project_dir, result, _tailscale_ip(data))
    result = summary(cfg)
    urls = external_urls(cfg)
    if cfg.remote_access.mode == "cloudflare":
        state = _tunnel_state(cfg, project_dir)
        if state != "connected":
            message = {
                "absent": "Connecteur Cloudflare pas encore installé : activez l’accès distant.",
                "bad_token": "Cloudflare refuse ce jeton : recopiez la commande d’installation du tunnel, puis réactivez.",
            }.get(state, "Le connecteur n’est pas encore relié à Cloudflare. Vérifiez le jeton (tunnel supprimé ?) et l’accès Internet sortant du serveur, puis actualisez.")
            result.update(status="pending", urls=urls, checks=[], tunnel=state, message=message)
            return result
    checks = [_check_public(cfg, sid, url) for sid, url in urls.items()]
    good = all(c["ok"] for c in checks) and bool(checks)
    details = " ".join(_explain(cfg, c) for c in checks if not c["ok"])
    if cfg.remote_access.mode == "cloudflare":
        message = ("Le tunnel répond par Cloudflare et refuse l’API anonyme. Configurez maintenant votre téléphone, puis testez en 4G/5G."
                   if good else "Connecteur en ligne. Reste à ajouter ou corriger les routes du tunnel dans Cloudflare. " + details)
        result.update(tunnel="connected")
    else:
        message = ("HTTPS répond depuis le serveur et refuse l’API anonyme. Testez maintenant depuis votre téléphone en 4G/5G."
                   if good else "HTTPS reste à vérifier : DNS, certificat, ports de la box ou authentification. La stack locale reste disponible. " + details)
    result.update(status="checked" if good else "pending", urls=urls, checks=checks, message=message.strip())
    return result
