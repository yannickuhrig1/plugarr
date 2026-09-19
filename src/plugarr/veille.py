"""Veille de la console : disques, debits, sortie du VPN. Lecture seule.

Niveau 1 de la veille (ROADMAP, « Une veille en continu ») : rien ici ne
demande le socket Docker en ecriture, ni ne touche un reglage. Tout se lit la
ou la donnee existe deja :

- la place libre, sur les dossiers que PlugArr a lui-meme crees ;
- les debits, aupres des clients de telechargement, par leurs propres API
  (routes relevees le 2026-09-19 sur les instances du banc) ;
- la sortie du VPN, au serveur de controle de Gluetun, que `vpncheck` joint
  deja par `docker exec` : son port n'est jamais publie sur l'hote.

Un service qui ne repond pas donne une ligne en erreur, jamais une page en
erreur : c'est une veille, elle doit rester lisible quand quelque chose tombe.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from . import catalog
from .layout import DATA_SUBDIRS
from .models import StackConfig
from .runner import exec_in

#: Delai par client. La page se rafraichit toutes les 5 s : un client qui ne
#: repond pas ne doit pas la figer.
DELAI = 4.0

#: La sortie du VPN coute un `docker exec` : relue au plus une fois par minute.
DUREE_CACHE_VPN = 60.0
#: Un echec, lui, est relu vite : au demarrage de Gluetun, le serveur de
#: controle repond `public_ip` vide quelques secondes avant que le tunnel ne
#: soit monte (constate le 2026-09-19 sur ProtonVPN). Le garder une minute
#: afficherait « non verifiee » bien apres que tout va bien.
DUREE_CACHE_ECHEC_VPN = 10.0

CONTROLE_GLUETUN = "http://127.0.0.1:8000/v1/publicip/ip"

_cache_vpn: dict[str, tuple[float, dict]] = {}
_verrou_vpn = threading.Lock()


# ------------------------------------------------------------------- disques


def _dossiers(cfg: StackConfig) -> list[tuple[str, Path]]:
    """Dossiers a surveiller, avec leur libelle. Les dossiers `.incomplete`
    sont omis : ils partagent toujours le disque de leur parent."""
    racine = Path(cfg.data_root)
    dossiers = [("Configuration", Path(cfg.config_root)), ("Données", racine)]
    dossiers += [(sous, racine / sous) for sous in DATA_SUBDIRS if ".incomplete" not in sous]
    return dossiers


def disques(cfg: StackConfig) -> list[dict]:
    """Un element par DISQUE, pas par dossier.

    Une mediatheque montee sur un second disque se voit ainsi a part, et un
    disque partage par dix dossiers n'est compte qu'une fois.
    """
    groupes: dict[int, dict] = {}
    for libelle, chemin in _dossiers(cfg):
        try:
            peripherique = os.stat(chemin).st_dev
            usage = shutil.disk_usage(chemin)
        except OSError:
            continue
        groupe = groupes.setdefault(
            peripherique,
            {
                "dossiers": [],
                "chemin": str(chemin),
                "total": usage.total,
                "libre": usage.free,
            },
        )
        groupe["dossiers"].append(libelle)
    return [
        {**g, "utilise_pct": round(100 * (g["total"] - g["libre"]) / g["total"], 1) if g["total"] else 0}
        for g in groupes.values()
    ]


# -------------------------------------------------------------------- debits


def _qbittorrent(inst, base: str) -> dict:
    with httpx.Client(base_url=base, timeout=DELAI, headers={"Referer": base}) as http:
        http.post(
            "/api/v2/auth/login",
            data={"username": inst.username or "", "password": inst.password or ""},
        )
        info = http.get("/api/v2/transfer/info")
        info.raise_for_status()
        d = info.json()
    return {
        "down": int(d.get("dl_info_speed") or 0),
        "up": int(d.get("up_info_speed") or 0),
        # « connected », « firewalled » ou « disconnected » : firewalled veut
        # dire aucun port entrant, ce qui ralentit sans rien casser.
        "detail": str(d.get("connection_status") or ""),
    }


def _transmission(inst, base: str) -> dict:
    corps = {"method": "session-stats"}
    auth = (inst.username or "", inst.password or "")
    with httpx.Client(base_url=base, timeout=DELAI, auth=auth) as http:
        # Premier appel refuse en 409 : il sert a obtenir l'identifiant de
        # session, protection CSRF de Transmission.
        premier = http.post("/transmission/rpc", json=corps)
        session = premier.headers.get("X-Transmission-Session-Id", "")
        reponse = http.post(
            "/transmission/rpc", json=corps, headers={"X-Transmission-Session-Id": session}
        )
        reponse.raise_for_status()
        d = reponse.json().get("arguments") or {}
    return {
        "down": int(d.get("downloadSpeed") or 0),
        "up": int(d.get("uploadSpeed") or 0),
        "detail": f"{d.get('activeTorrentCount', 0)} actif(s) sur {d.get('torrentCount', 0)}",
    }


def _sabnzbd(inst, base: str) -> dict:
    with httpx.Client(base_url=base, timeout=DELAI) as http:
        reponse = http.get(
            "/api",
            params={
                "mode": "queue",
                "output": "json",
                "limit": 0,
                "apikey": inst.api_key or inst.password or "",
            },
        )
        reponse.raise_for_status()
        file = reponse.json().get("queue") or {}
    return {
        "down": int(float(file.get("kbpersec") or 0) * 1024),
        # Usenet ne partage rien : pas de debit montant.
        "up": None,
        "detail": f"{file.get('status', '?')}, {file.get('noofslots', 0)} en file",
    }


_LECTEURS = {"qbittorrent": _qbittorrent, "transmission": _transmission, "sabnzbd": _sabnzbd}


def _debit(cfg: StackConfig, sid: str) -> dict:
    inst = cfg.services[sid]
    ligne = {"id": sid, "name": catalog.get(sid).display_name}
    try:
        return {**ligne, "ok": True, **_LECTEURS[sid](inst, inst.url(cfg.host))}
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        # Jamais l'exception elle-meme : son texte peut porter l'URL appelee,
        # et celle de SABnzbd contient la cle API.
        return {**ligne, "ok": False, "down": None, "up": None, "detail": type(exc).__name__}


def debits(cfg: StackConfig) -> list[dict]:
    presents = [sid for sid in _LECTEURS if cfg.enabled(sid)]
    if not presents:
        return []
    with ThreadPoolExecutor(max_workers=len(presents)) as pool:
        return list(pool.map(lambda sid: _debit(cfg, sid), presents))


# ----------------------------------------------------------------------- VPN


def _lire_sortie_vpn(conteneur: str) -> dict:
    ok, sortie = exec_in(conteneur, ["wget", "-qO-", "--timeout=5", CONTROLE_GLUETUN])
    if not ok or not sortie:
        return {"ok": False, "detail": "serveur de controle de Gluetun injoignable"}
    try:
        d = json.loads(sortie)
    except ValueError:
        return {"ok": False, "detail": "reponse illisible de Gluetun"}
    if not isinstance(d, dict) or not d.get("public_ip"):
        return {"ok": False, "detail": "aucune adresse publique : le tunnel est-il monte ?"}
    return {
        "ok": True,
        "ip": d["public_ip"],
        "pays": d.get("country") or "?",
        "ville": d.get("city") or "",
        "operateur": (d.get("organization") or "")[:60],
    }


def vpn(cfg: StackConfig) -> dict | None:
    """Sortie du tunnel, ou None sans VPN. Mise en cache une minute."""
    if not cfg.vpn_enabled:
        return None
    conteneur = f"{cfg.project_name}-gluetun"
    with _verrou_vpn:
        lu = _cache_vpn.get(conteneur)
        if lu:
            duree = DUREE_CACHE_VPN if lu[1]["ok"] else DUREE_CACHE_ECHEC_VPN
            if time.monotonic() - lu[0] < duree:
                return lu[1]
    sortie = _lire_sortie_vpn(conteneur)
    with _verrou_vpn:
        _cache_vpn[conteneur] = (time.monotonic(), sortie)
    return sortie


# ------------------------------------------------------------------ ensemble


def payload(cfg: StackConfig) -> dict:
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_disques = pool.submit(disques, cfg)
        f_debits = pool.submit(debits, cfg)
        f_vpn = pool.submit(vpn, cfg)
        return {
            "disques": f_disques.result(),
            "debits": f_debits.result(),
            "vpn": f_vpn.result(),
        }
