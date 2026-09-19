"""`plugarr veille` : une page en lecture seule, jamais exposee sans verrou."""

from __future__ import annotations

import threading

import httpx
import pytest

from plugarr import adminauth, orchestrator, veille, veille_serveur

FAUSSE_VEILLE = {"disques": [], "debits": [], "vpn": None, "services": []}


def _cfg(tmp_path, *, mot_de_passe=""):
    cfg = orchestrator.build_config(
        services=["sonarr", "qbittorrent"], config_root=str(tmp_path / "c"), data_root=str(tmp_path / "d")
    )
    cfg.admin_password_hash = adminauth.hash_password(mot_de_passe) if mot_de_passe else ""
    return cfg


@pytest.fixture
def serveur(tmp_path, monkeypatch):
    lances = []
    appels = []

    def fausse(cfg, *, interne=False, avec_etats=False):
        appels.append((interne, avec_etats))
        return FAUSSE_VEILLE

    monkeypatch.setattr(veille, "payload", fausse)

    def lancer(cfg, interne=False):
        srv, jeton = veille_serveur.construire(cfg, hote="127.0.0.1", port=0, interne=interne)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        lances.append(srv)
        return f"http://127.0.0.1:{srv.server_port}", jeton, appels

    yield lancer
    for srv in lances:
        srv.shutdown()
        srv.server_close()


def test_sans_mot_de_passe_la_veille_refuse_le_reseau(tmp_path):
    with pytest.raises(veille_serveur.VeilleRefusee, match="admin-password"):
        veille_serveur.construire(_cfg(tmp_path), hote="0.0.0.0", port=0, interne=True)


def test_avec_mot_de_passe_le_reseau_est_accepte(tmp_path):
    srv, jeton = veille_serveur.construire(
        _cfg(tmp_path, mot_de_passe="s3cret"), hote="0.0.0.0", port=0, interne=True
    )
    srv.server_close()
    assert jeton == "", "un jeton en plus du mot de passe serait une seconde porte"


def test_sur_127_0_0_1_sans_mot_de_passe_le_jeton_ouvre_la_page(tmp_path, serveur):
    base, jeton, appels = serveur(_cfg(tmp_path), interne=True)
    with httpx.Client(base_url=base) as c:
        assert c.get("/").status_code == 401
        assert c.get("/api/veille").status_code == 401
        assert c.get("/", params={"t": "faux"}).status_code == 401

        page = c.get("/", params={"t": jeton})
        assert page.status_code == 200 and "Veille PlugArr" in page.text
        assert c.get("/api/veille").json() == FAUSSE_VEILLE
    assert appels == [(True, True)], "la veille seule doit relever l'etat des services"


def test_le_mot_de_passe_de_la_console_ouvre_puis_ferme_la_session(tmp_path, serveur):
    base, _, _ = serveur(_cfg(tmp_path, mot_de_passe="s3cret"))
    with httpx.Client(base_url=base) as c:
        assert "Mot de passe" in c.get("/").text
        assert c.post("/login", data={"password": "faux"}).status_code == 401
        assert c.get("/api/veille").status_code == 401

        assert c.post("/login", data={"password": "s3cret"}).status_code == 200
        assert c.get("/api/veille").status_code == 200

        c.post("/logout")
        assert c.get("/api/veille").status_code == 401


def test_aucune_route_ne_modifie_quoi_que_ce_soit(tmp_path, serveur):
    base, jeton, _ = serveur(_cfg(tmp_path))
    with httpx.Client(base_url=base) as c:
        c.get("/", params={"t": jeton})
        for route in ("/api/veille", "/api/action", "/api/update", "/"):
            assert c.post(route, json={"service": "sonarr"}).status_code == 404, route


def test_la_page_ne_porte_aucun_bouton_d_action():
    page = veille_serveur._PAGE.format(style="")
    boutons = page.count("<button")
    assert boutons == 1 and "Se déconnecter" in page


# ------------------------------------------------------- adresses internes


def test_dans_la_pile_les_services_sont_joints_par_leur_nom(tmp_path):
    cfg = _cfg(tmp_path)

    assert veille._adresse(cfg, "qbittorrent", True) == "http://qbittorrent:8080"
    assert veille._adresse(cfg, "qbittorrent", False).startswith("http://localhost:")


def test_un_client_derriere_le_vpn_est_joint_par_gluetun(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.vpn.enabled = True

    assert veille._adresse(cfg, "qbittorrent", True) == "http://gluetun:8080"
