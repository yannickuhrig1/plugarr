"""Veille de la console : disques, debits, sortie du VPN. Lecture seule.

Niveau 1 de la veille (ROADMAP, « Une veille en continu ») : rien ici ne
demande le socket Docker en ecriture, ni ne touche un reglage. Tout se lit la
ou la donnee existe deja :

- la place libre, sur les dossiers que PlugArr a lui-meme crees ;
- les debits, aupres des clients de telechargement, par leurs propres API
  (routes relevees le 2026-09-19 sur les instances du banc) ;
- la sortie du VPN, au serveur de controle de Gluetun, que `vpncheck` joint
  deja par `docker exec` : son port n'est jamais publie sur l'hote ;
- le CPU, la memoire, les redemarrages et les kills OOM par conteneur, par la
  ligne de commande Docker, sur l'hote uniquement. Des CHAMPS choisis, jamais
  l'inspection entiere : elle rend les variables d'environnement resolues.

Un service qui ne repond pas donne une ligne en erreur, jamais une page en
erreur : c'est une veille, elle doit rester lisible quand quelque chose tombe.

Deux emplacements, un seul code :

- sur l'HOTE (la console) : les services par leur port publie, Gluetun par
  `docker exec` ;
- dans un CONTENEUR de la pile (`interne=True`, `plugarr veille --interne`) :
  les services par leur nom sur le reseau compose, Gluetun par HTTP. Aucun
  socket Docker, donc aucun droit sur les conteneurs, et pas de CPU ni de
  memoire par conteneur : la section disparait au lieu de mentir.
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

from . import catalog, gluetun_auth
from .layout import DATA_SUBDIRS
from .models import StackConfig
from .runner import etats_conteneurs, exec_in, stats_conteneurs

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
#: Le meme serveur de controle, vu d'un AUTRE conteneur du reseau compose.
#: Mesure le 2026-09-19 (Gluetun v3.41.3) : repond 200 sans authentification,
#: mais Gluetun previent a chaque appel que la route deviendra protegee.
CONTROLE_GLUETUN_INTERNE = "http://gluetun:8000/v1/publicip/ip"

#: Le releve des conteneurs coute `docker stats`, qui prend DEUX mesures
#: espacees pour calculer le CPU : 2,1 s mesurees sur le banc pour neuf
#: conteneurs, le 2026-09-20. La page se rafraichit toutes les 5 s ; sans ce
#: cache, Docker travaillerait presque sans arret.
DUREE_CACHE_CONTENEURS = 10.0

_cache_vpn: dict[str, tuple[float, dict]] = {}
_verrou_vpn = threading.Lock()
_cache_conteneurs: dict[str, tuple[float, list[dict]]] = {}
_verrou_conteneurs = threading.Lock()


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


def _adresse(cfg: StackConfig, sid: str, interne: bool) -> str:
    inst = cfg.services[sid]
    if interne:
        return inst.internal_url(catalog.get(sid), cfg.host, behind_vpn=cfg.vpn.protects(sid))
    return inst.url(cfg.host)


def _debit(cfg: StackConfig, sid: str, interne: bool = False) -> dict:
    inst = cfg.services[sid]
    ligne = {"id": sid, "name": catalog.get(sid).display_name}
    try:
        return {**ligne, "ok": True, **_LECTEURS[sid](inst, _adresse(cfg, sid, interne))}
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        # Jamais l'exception elle-meme : son texte peut porter l'URL appelee,
        # et celle de SABnzbd contient la cle API.
        return {**ligne, "ok": False, "down": None, "up": None, "detail": type(exc).__name__}


def debits(cfg: StackConfig, *, interne: bool = False) -> list[dict]:
    presents = [sid for sid in _LECTEURS if cfg.enabled(sid)]
    if not presents:
        return []
    with ThreadPoolExecutor(max_workers=len(presents)) as pool:
        return list(pool.map(lambda sid: _debit(cfg, sid, interne), presents))


# ------------------------------------------------------------------ services


def _etat(cfg: StackConfig, sid: str, interne: bool) -> dict:
    """Le service repond-il a HTTP ? Toute reponse sous 500 compte : une page
    de connexion (401, 302) prouve que le service tourne."""
    ligne = {"id": sid, "name": catalog.get(sid).display_name}
    try:
        with httpx.Client(timeout=DELAI, follow_redirects=False) as http:
            code = http.get(_adresse(cfg, sid, interne)).status_code
    except httpx.HTTPError as exc:
        return {**ligne, "up": False, "detail": type(exc).__name__}
    return {**ligne, "up": code < 500, "detail": f"HTTP {code}"}


def etats(cfg: StackConfig, *, interne: bool = False) -> list[dict]:
    """Etat de chaque service a interface, par sa propre adresse.

    La console lit l'etat Docker ; un conteneur sans socket ne le peut pas.
    Repondre a HTTP est la preuve qui reste, et c'est celle qui compte.
    """
    presents = [
        sid
        for sid in catalog.STARTUP_ORDER
        if cfg.enabled(sid) and cfg.services[sid].has_web_ui and catalog.get(sid).internal_port
    ]
    if not presents:
        return []
    with ThreadPoolExecutor(max_workers=min(len(presents), 8)) as pool:
        return list(pool.map(lambda sid: _etat(cfg, sid, interne), presents))


# -------------------------------------------------------------- conteneurs


def _noms_conteneurs(cfg: StackConfig) -> list[str]:
    noms = [f"{cfg.project_name}-{sid}" for sid in catalog.STARTUP_ORDER if cfg.enabled(sid)]
    if cfg.vpn_enabled:
        noms.insert(0, f"{cfg.project_name}-gluetun")
    return noms


def conteneurs(cfg: StackConfig, *, interne: bool = False) -> list[dict]:
    """CPU, memoire, redemarrages et kills OOM, un element par conteneur.

    Lu par la ligne de commande Docker, sur l'HOTE seulement. Dans un
    conteneur (`interne`), la veille n'a pas de socket Docker et n'en veut
    pas : la liste est vide, et la page n'affiche pas la section.

    Un compteur de redemarrages qui monte est le signe le plus utile ici : un
    service qui boucle repond parfois a HTTP entre deux chutes, et la ligne
    « en marche » seule ne le dirait pas.
    """
    if interne:
        return []
    with _verrou_conteneurs:
        lu = _cache_conteneurs.get(cfg.project_name)
        if lu and time.monotonic() - lu[0] < DUREE_CACHE_CONTENEURS:
            return lu[1]
    noms = _noms_conteneurs(cfg)
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_stats = pool.submit(stats_conteneurs, noms)
        f_etats = pool.submit(etats_conteneurs, noms)
        releves, etats_lus = f_stats.result(), f_etats.result()
    lignes = []
    for nom in noms:
        etat = etats_lus.get(nom)
        if etat is None:
            # Conteneur jamais cree, ou supprime depuis : rien a en dire.
            continue
        lignes.append({
            "nom": nom,
            "service": nom[len(cfg.project_name) + 1:],
            **etat,
            **releves.get(nom, {"cpu_pct": None, "memoire": None, "memoire_max": None}),
        })
    with _verrou_conteneurs:
        _cache_conteneurs[cfg.project_name] = (time.monotonic(), lignes)
    return lignes


# ----------------------------------------------------------------------- VPN


def _lire_sortie_vpn(conteneur: str, interne: bool = False, cle: str = "") -> dict:
    if interne:
        # Le fichier de Gluetun est lu sur CONFIG_ROOT, monte en lecture seule.
        entetes = {"X-API-Key": cle} if cle else {}
        try:
            reponse = httpx.get(CONTROLE_GLUETUN_INTERNE, timeout=DELAI, headers=entetes)
            ok, sortie = reponse.status_code == 200, reponse.text.strip()
        except httpx.HTTPError:
            ok, sortie = False, ""
    else:
        # Sur l'hote, la cle est relue DANS Gluetun : jamais en argument.
        script = (
            f'{gluetun_auth.LIRE_CLE_SH}; wget -qO- --timeout=5 '
            f'--header "X-API-Key: $K" {CONTROLE_GLUETUN}'
        )
        ok, sortie = exec_in(conteneur, ["sh", "-c", script])
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


def vpn(cfg: StackConfig, *, interne: bool = False) -> dict | None:
    """Sortie du tunnel, ou None sans VPN. Mise en cache une minute."""
    if not cfg.vpn_enabled:
        return None
    conteneur = f"{cfg.project_name}-gluetun"
    cle = f"{conteneur}:{interne}"
    with _verrou_vpn:
        lu = _cache_vpn.get(cle)
        if lu:
            duree = DUREE_CACHE_VPN if lu[1]["ok"] else DUREE_CACHE_ECHEC_VPN
            if time.monotonic() - lu[0] < duree:
                return lu[1]
    sortie = _lire_sortie_vpn(conteneur, interne, gluetun_auth.cle(cfg) if interne else "")
    with _verrou_vpn:
        _cache_vpn[cle] = (time.monotonic(), sortie)
    return sortie


# ------------------------------------------------------------------ ensemble


def payload(cfg: StackConfig, *, interne: bool = False, avec_etats: bool = False) -> dict:
    """`avec_etats` : la console a deja l'etat Docker, la veille seule non."""
    with ThreadPoolExecutor(max_workers=5) as pool:
        f_disques = pool.submit(disques, cfg)
        f_debits = pool.submit(debits, cfg, interne=interne)
        f_vpn = pool.submit(vpn, cfg, interne=interne)
        f_conteneurs = pool.submit(conteneurs, cfg, interne=interne)
        f_etats = pool.submit(etats, cfg, interne=interne) if avec_etats else None
        donnees = {
            "disques": f_disques.result(),
            "debits": f_debits.result(),
            "vpn": f_vpn.result(),
            "conteneurs": f_conteneurs.result(),
        }
        if f_etats is not None:
            donnees["services"] = f_etats.result()
        return donnees
