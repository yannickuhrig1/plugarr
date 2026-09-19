"""Veille de la console : disques, debits et sortie du VPN, en lecture seule.

Les reponses simulees reprennent les champs releves le 2026-09-19 sur les
instances du banc : `/api/v2/transfer/info` (qBittorrent 5.2.3),
`session-stats` (Transmission 4.1.3, apres le 409 qui donne la session) et
`mode=queue` (SABnzbd).
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from plugarr import console_ui, orchestrator, veille

CLE_SAB = "cle-sabnzbd-secrete"


class _Faux(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, code, corps, entetes=()):
        brut = json.dumps(corps).encode()
        self.send_response(code)
        for nom, valeur in entetes:
            self.send_header(nom, valeur)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(brut)))
        self.end_headers()
        self.wfile.write(brut)

    def do_POST(self):
        longueur = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(longueur)
        if self.path == "/api/v2/auth/login":
            self.send_response(204)
            self.send_header("Set-Cookie", "QBT_SID=abc; path=/")
            self.end_headers()
        elif self.path == "/transmission/rpc":
            if self.headers.get("X-Transmission-Session-Id") != "S1":
                self._json(409, {}, [("X-Transmission-Session-Id", "S1")])
            else:
                self._json(200, {"result": "success", "arguments": {
                    "downloadSpeed": 2048, "uploadSpeed": 512,
                    "activeTorrentCount": 1, "torrentCount": 3}})

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/api/v2/transfer/info":
            self._json(200, {"connection_status": "connected", "dl_info_speed": 1_500_000,
                             "up_info_speed": 30_000, "last_external_address_v4": "203.0.113.9"})
        elif url.path == "/api":
            if parse_qs(url.query).get("apikey") != [CLE_SAB]:
                self._json(403, {"error": "API Key Incorrect"})
            else:
                self._json(200, {"queue": {"kbpersec": "100.50", "status": "Downloading",
                                           "noofslots": 2}})


@pytest.fixture
def faux_clients():
    serveur = ThreadingHTTPServer(("127.0.0.1", 0), _Faux)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    yield serveur.server_address[1]
    serveur.shutdown()


def _cfg(tmp_path, services=("sonarr", "qbittorrent", "transmission", "sabnzbd"), port=None):
    cfg = orchestrator.build_config(
        services=list(services), config_root=str(tmp_path / "c"), data_root=str(tmp_path / "d")
    )
    cfg.host = "127.0.0.1"
    for sid in ("qbittorrent", "transmission", "sabnzbd"):
        if sid in cfg.services and port:
            cfg.services[sid].host_port = port
    if "sabnzbd" in cfg.services:
        cfg.services["sabnzbd"].password = CLE_SAB
        cfg.services["sabnzbd"].api_key = None
    return cfg


# ------------------------------------------------------------------- debits


def test_les_debits_sont_lus_chez_chaque_client(tmp_path, faux_clients):
    lignes = {d["id"]: d for d in veille.debits(_cfg(tmp_path, port=faux_clients))}

    assert lignes["qbittorrent"] == {
        "id": "qbittorrent", "name": "qBittorrent", "ok": True,
        "down": 1_500_000, "up": 30_000, "detail": "connected"}
    assert (lignes["transmission"]["down"], lignes["transmission"]["up"]) == (2048, 512)
    assert lignes["transmission"]["detail"] == "1 actif(s) sur 3"
    assert lignes["sabnzbd"]["down"] == int(100.5 * 1024)
    assert lignes["sabnzbd"]["up"] is None, "Usenet ne partage rien"


def test_l_adresse_vue_par_les_pairs_ne_sort_pas(tmp_path, faux_clients):
    """qBittorrent donne l'adresse publique de la connexion : la veille n'en a
    pas besoin et ne la renvoie pas."""
    texte = json.dumps(veille.debits(_cfg(tmp_path, port=faux_clients)))

    assert "203.0.113.9" not in texte


def test_un_client_injoignable_donne_une_ligne_en_erreur(tmp_path, faux_clients):
    cfg = _cfg(tmp_path, port=faux_clients)
    cfg.services["sabnzbd"].password = "mauvaise"
    cfg.services["qbittorrent"].host_port = 1  # rien n'ecoute

    lignes = {d["id"]: d for d in veille.debits(cfg)}

    assert lignes["transmission"]["ok"] is True
    assert lignes["qbittorrent"]["ok"] is False
    assert lignes["sabnzbd"]["ok"] is False
    # L'URL de SABnzbd porte la cle API : l'erreur ne doit jamais la citer.
    assert "mauvaise" not in json.dumps(lignes)


def test_sans_client_de_telechargement_rien_n_est_interroge(tmp_path):
    assert veille.debits(_cfg(tmp_path, services=("sonarr",))) == []


# ------------------------------------------------------------------ disques


def test_un_disque_partage_par_plusieurs_dossiers_n_est_compte_qu_une_fois(tmp_path):
    cfg = _cfg(tmp_path)
    for dossier in (tmp_path / "c", tmp_path / "d" / "torrents", tmp_path / "d" / "media"):
        dossier.mkdir(parents=True)

    groupes = veille.disques(cfg)

    assert len(groupes) == 1
    assert groupes[0]["dossiers"] == ["Configuration", "Données", "torrents", "media"]
    assert 0 <= groupes[0]["utilise_pct"] <= 100
    assert groupes[0]["libre"] <= groupes[0]["total"]


def test_un_dossier_absent_est_ignore(tmp_path):
    assert veille.disques(_cfg(tmp_path)) == []


# ---------------------------------------------------------------------- VPN


def test_sans_vpn_rien_n_est_lu(tmp_path, monkeypatch):
    monkeypatch.setattr(veille, "exec_in", lambda *a, **k: pytest.fail("docker exec inutile"))

    assert veille.vpn(_cfg(tmp_path)) is None


def _avec_vpn(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.vpn.enabled = True
    cfg.project_name = f"essai-{tmp_path.name}"
    return cfg


def test_la_sortie_du_vpn_est_lue_puis_gardee_une_minute(tmp_path, monkeypatch):
    appels = []

    def exec_in(conteneur, commande, timeout=0):
        appels.append(conteneur)
        return True, json.dumps({"public_ip": "198.51.100.7", "country": "Pays-Bas",
                                 "city": "Amsterdam", "organization": "Fournisseur"})

    monkeypatch.setattr(veille, "exec_in", exec_in)
    cfg = _avec_vpn(tmp_path)

    premiere = veille.vpn(cfg)
    assert premiere == {"ok": True, "ip": "198.51.100.7", "pays": "Pays-Bas",
                        "ville": "Amsterdam", "operateur": "Fournisseur"}
    assert veille.vpn(cfg) == premiere
    assert appels == [f"{cfg.project_name}-gluetun"], "un docker exec a chaque rafraichissement"


def test_un_echec_est_relu_vite_pour_voir_le_tunnel_monter(tmp_path, monkeypatch):
    """Au demarrage, Gluetun repond `public_ip` vide quelques secondes."""
    reponses = iter(['{"public_ip": ""}', '{"public_ip": "198.51.100.7", "country": "X"}'])
    horloge = [1000.0]
    monkeypatch.setattr(veille, "exec_in", lambda *a, **k: (True, next(reponses)))
    monkeypatch.setattr(veille.time, "monotonic", lambda: horloge[0])
    cfg = _avec_vpn(tmp_path)

    assert veille.vpn(cfg)["ok"] is False
    horloge[0] += veille.DUREE_CACHE_ECHEC_VPN + 1
    assert veille.vpn(cfg)["ok"] is True


def test_un_tunnel_sans_adresse_est_signale(tmp_path, monkeypatch):
    monkeypatch.setattr(veille, "exec_in", lambda *a, **k: (True, "{}"))

    sortie = veille.vpn(_avec_vpn(tmp_path))

    assert sortie["ok"] is False
    assert "tunnel" in sortie["detail"]


# ---------------------------------------------------------------- la page


def test_la_console_porte_le_panneau_de_veille_sans_bouton():
    page = console_ui.enhance(
        '<html lang="fr"><head></head><body><div class="wrap"><header></header>'
        "  <h2>Services</h2>  <footer></footer></div></body></html>"
    )

    assert 'id="veille"' in page and 'href="#veille"' in page
    debut = page.index('id="veille"')
    panneau = page[debut:page.index("</section>", debut)]
    assert "<button" not in panneau, "la veille ne doit rien pouvoir changer"
    assert "api('veille')" in page
