"""Tunnel Cloudflare et sous-domaines personnalises.

Le jeton de test a la forme exacte de celui de cloudflared (base64 standard
d'un JSON `a`/`s`/`t`, voir ParseToken dans cmd/cloudflared/tunnel), avec des
valeurs fictives : aucun compte Cloudflare n'est contacte.
"""
import base64
import json
import os
import stat
from unittest.mock import Mock

import httpx
import pytest
import yaml
from pydantic import ValidationError

from plugarr import catalog, remote_access, webwizard
from plugarr.models import StackConfig
from plugarr.remote_models import RemoteAccessConfig, identifiant_tunnel, jeton_tunnel

TUNNEL_ID = "6f1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
TOKEN = base64.b64encode(json.dumps({
    "a": "0123456789abcdef0123456789abcdef",
    "t": TUNNEL_ID,
    "s": base64.b64encode(b"fictif-" * 5).decode(),
}).encode()).decode()


def config(tmp_path, mode="cloudflare", names=None, services=("sonarr", "qbittorrent"), token=TOKEN):
    state = webwizard.WizardState(tmp_path, demo=True)
    form = state.bootstrap()["form"]
    form.update(services=list(services), host="192.0.2.50", reprendre=False,
                remote_access={"mode": mode, "domain": "maison.example", "services": list(services),
                               "names": names or {}, "tunnel_token": token if mode == "cloudflare" else ""})
    return state, state.build_config(form)


# -- jeton ----------------------------------------------------------------------


@pytest.mark.parametrize("colle", [
    TOKEN,
    f"  {TOKEN}\n",
    f"sudo cloudflared service install {TOKEN}",
    f"cloudflared.exe service install {TOKEN}",
    f"docker run cloudflare/cloudflared:latest tunnel --no-autoupdate run --token {TOKEN}",
])
def test_le_jeton_est_extrait_de_la_commande_affichee_par_cloudflare(colle):
    assert jeton_tunnel(colle) == TOKEN
    assert identifiant_tunnel(TOKEN) == TUNNEL_ID


@pytest.mark.parametrize("colle", [
    "pas un jeton",
    base64.b64encode(json.dumps({"a": "x", "t": "pas-un-uuid", "s": "c2VjcmV0"}).encode()).decode(),
    base64.b64encode(json.dumps({"t": TUNNEL_ID, "s": "c2VjcmV0"}).encode()).decode() + "A" * 10,
    TOKEN[:-8],
])
def test_un_jeton_illisible_est_refuse_sans_etre_recopie(colle):
    with pytest.raises(ValidationError) as erreur:
        RemoteAccessConfig(mode="cloudflare", domain="maison.example", services=["sonarr"], tunnel_token=colle)
    assert TOKEN not in str(erreur.value.errors(include_input=False))


def test_le_jeton_n_apparait_ni_dans_repr_ni_hors_du_mode_tunnel():
    choix = RemoteAccessConfig(mode="cloudflare", domain="maison.example", services=["sonarr"], tunnel_token=TOKEN)
    assert TOKEN not in repr(choix)
    https = RemoteAccessConfig(mode="https", domain="maison.example", services=["sonarr"], tunnel_token=TOKEN)
    assert https.tunnel_token == ""
    with pytest.raises(ValidationError, match="jeton"):
        RemoteAccessConfig(mode="cloudflare", domain="maison.example", services=["sonarr"])


# -- sous-domaines --------------------------------------------------------------


def test_les_sous_domaines_se_renomment_et_les_defauts_ne_sont_pas_ecrits():
    choix = RemoteAccessConfig(mode="https", domain="maison.example", services=["sonarr", "radarr", "qbittorrent"],
                               names={"sonarr": " Series ", "radarr": "radarr", "qbittorrent": ""})
    assert choix.names == {"sonarr": "series"}
    assert [choix.hostname(s) for s in choix.services] == [
        "series.maison.example", "radarr.maison.example", "qb.maison.example"]


@pytest.mark.parametrize("names", [
    {"sonarr": "a.b"}, {"sonarr": "-sonarr"}, {"sonarr": "sonarr-"}, {"sonarr": "son arr"},
    {"sonarr": "x" * 64}, {"sonarr": "qb"},
])
def test_un_sous_domaine_invalide_ou_en_double_est_refuse(names):
    with pytest.raises(ValidationError):
        RemoteAccessConfig(mode="https", domain="maison.example", services=["sonarr", "qbittorrent"], names=names)


def test_une_pile_sans_ces_options_reste_lisible_par_une_image_plus_ancienne(tmp_path):
    """L'image d'administration epinglee refuse un champ inconnu : une pile qui
    ne se sert ni du tunnel ni des noms ne doit donc pas les ecrire."""
    _, cfg = config(tmp_path, mode="https")
    ecrit = cfg.model_dump(mode="json")["remote_access"]
    assert set(ecrit) == {"mode", "domain", "services"}
    _, tunnel = config(tmp_path / "t", names={"sonarr": "series"})
    relu = StackConfig.model_validate(yaml.safe_load(yaml.safe_dump(tunnel.model_dump(mode="json"))))
    assert relu.remote_access == tunnel.remote_access
    assert relu.remote_access.tunnel_token == TOKEN


# -- passerelle -----------------------------------------------------------------


def test_le_connecteur_est_epingle_sans_port_ni_secret_dans_le_compose(tmp_path):
    _, cfg = config(tmp_path)
    compose = remote_access.gateway_compose(cfg)
    gateway = compose["services"]["gateway"]
    assert gateway["image"] == remote_access.CLOUDFLARED_IMAGE
    assert "@sha256:" in gateway["image"]
    assert gateway["command"] == ["tunnel", "--no-autoupdate", "run"]
    assert gateway["env_file"] == ["./tunnel.env"]
    assert "ports" not in gateway and "network_mode" not in gateway
    assert compose["networks"]["applications"]["name"] == cfg.project_name + "_plugarr"
    assert TOKEN not in json.dumps(compose)


def test_les_routes_donnent_les_champs_du_tableau_de_bord(tmp_path):
    _, cfg = config(tmp_path, names={"qbittorrent": "torrent"})
    cfg.vpn.enabled = True
    routes = {r["service"]: r for r in remote_access.routes(cfg)}
    assert routes["qbittorrent"] == {"service": "qbittorrent", "subdomain": "torrent", "domain": "maison.example",
                                     "hostname": "torrent.maison.example", "service_url": "http://gluetun:8080"}
    assert routes["sonarr"]["service_url"] == "http://sonarr:8989"
    assert remote_access.external_urls(cfg)["qbittorrent"] == "https://torrent.maison.example"
    resume = remote_access.summary(cfg)
    assert resume["tunnel_id"] == TUNNEL_ID and len(resume["routes"]) == 2
    assert TOKEN not in json.dumps(resume)


def test_caddy_suit_aussi_les_noms_personnalises(tmp_path):
    _, cfg = config(tmp_path, mode="https", names={"sonarr": "series"})
    texte = remote_access.caddyfile(cfg)
    assert "series.maison.example {" in texte and "sonarr.maison.example" not in texte


def test_l_activation_ecrit_le_jeton_a_part_et_protege_les_applications(tmp_path, monkeypatch):
    _, cfg = config(tmp_path)
    proteger = Mock()
    monkeypatch.setattr(remote_access, "_protect_applications", proteger)
    commandes = []
    monkeypatch.setattr(remote_access, "_command", lambda _cfg, _dir, *args, **_k: commandes.append(args) or "")
    monkeypatch.setattr(remote_access, "inspect", lambda *_a, **_k: {"status": "pending"})
    monkeypatch.setattr(remote_access.socket, "getaddrinfo", Mock(side_effect=AssertionError("pas de DNS avant la route")))
    remote_access.activate(cfg, tmp_path)
    dossier = tmp_path / ".plugarr-remote"
    proteger.assert_called_once()
    assert (dossier / "tunnel.env").read_text(encoding="utf-8") == f"TUNNEL_TOKEN={TOKEN}\n"
    assert TOKEN not in (dossier / "compose.yml").read_text(encoding="utf-8")
    assert commandes == [("up", "-d", "--force-recreate")]
    if os.name != "nt":
        assert stat.S_IMODE((dossier / "tunnel.env").stat().st_mode) == 0o600


def test_passer_a_https_retire_le_jeton_devenu_inutile(tmp_path, monkeypatch):
    _, cfg = config(tmp_path, mode="https")
    dossier = tmp_path / ".plugarr-remote"
    dossier.mkdir()
    (dossier / "tunnel.env").write_text(f"TUNNEL_TOKEN={TOKEN}\n", encoding="utf-8")
    monkeypatch.setattr(remote_access.socket, "getaddrinfo", lambda *a: [(1,)])
    monkeypatch.setattr(remote_access, "_protect_applications", Mock())
    monkeypatch.setattr(remote_access, "_command", Mock(return_value=""))
    monkeypatch.setattr(remote_access, "inspect", lambda *_a, **_k: {})
    remote_access.activate(cfg, tmp_path)
    assert not (dossier / "tunnel.env").exists()


def test_le_nom_personnalise_de_qbittorrent_est_accepte_par_sa_webui(tmp_path, httpx_mock):
    from urllib.parse import parse_qs

    _, cfg = config(tmp_path, names={"qbittorrent": "torrent"}, services=("qbittorrent",))
    base = cfg.services["qbittorrent"].url(cfg.host)
    old = {"web_ui_csrf_protection_enabled": True, "web_ui_host_header_validation_enabled": True,
           "bypass_local_auth": False, "bypass_auth_subnet_whitelist_enabled": False, "web_ui_domain_list": ""}
    saved = dict(old)

    def update(request):
        saved.update(json.loads(parse_qs(request.content.decode())["json"][0]))
        return httpx.Response(200)

    httpx_mock.add_response(method="POST", url=base + "/api/v2/auth/login", text="Ok.")
    httpx_mock.add_response(method="GET", url=base + "/api/v2/app/preferences", json=old)
    httpx_mock.add_callback(update, method="POST", url=base + "/api/v2/app/setPreferences")
    httpx_mock.add_callback(lambda request: httpx.Response(200, json=saved),
                            method="GET", url=base + "/api/v2/app/preferences")
    remote_access._protect_applications(cfg, tmp_path)
    assert "torrent.maison.example" in saved["web_ui_domain_list"].split(";")
    assert "qb.maison.example" not in saved["web_ui_domain_list"]


# -- verification ---------------------------------------------------------------


def _gateway(tmp_path, cfg):
    dossier = tmp_path / ".plugarr-remote"
    dossier.mkdir(exist_ok=True)
    (dossier / "compose.yml").write_text(yaml.safe_dump(remote_access.gateway_compose(cfg)), encoding="utf-8")


@pytest.mark.parametrize("journal,etat,extrait", [
    ("", "waiting", "pas encore relié"),
    ("ERR Provided Tunnel token is not valid.", "bad_token", "refuse ce jeton"),
])
def test_un_connecteur_hors_ligne_est_signale_sans_tester_les_adresses(tmp_path, monkeypatch, journal, etat, extrait):
    _, cfg = config(tmp_path)
    _gateway(tmp_path, cfg)
    monkeypatch.setattr(remote_access, "_command", lambda *_a, **_k: journal)
    monkeypatch.setattr(remote_access, "_check_public", Mock(side_effect=AssertionError("HTTP")))
    resultat = remote_access.inspect(cfg, tmp_path)
    assert (resultat["status"], resultat["tunnel"]) == ("pending", etat)
    assert extrait in resultat["message"]
    assert resultat["routes"]


def test_sans_connecteur_installe_l_etat_le_dit(tmp_path, monkeypatch):
    _, cfg = config(tmp_path)
    monkeypatch.setattr(remote_access, "_command", Mock(side_effect=AssertionError("docker")))
    assert remote_access.inspect(cfg, tmp_path)["tunnel"] == "absent"


def _connecte(tmp_path, monkeypatch, services=("sonarr",), names=None):
    _, cfg = config(tmp_path, services=services, names=names)
    if "sonarr" in services:
        cfg.services["sonarr"].api_key = "cle-de-cette-instance"
    _gateway(tmp_path, cfg)
    monkeypatch.setattr(remote_access, "_command",
                        lambda *_a, **_k: "INF Registered tunnel connection connIndex=0 location=cdg01")
    monkeypatch.setattr(remote_access.socket, "getaddrinfo", lambda *a: [(1,)])
    return cfg


def test_la_bonne_instance_refuse_l_anonyme_et_accepte_sa_cle(tmp_path, monkeypatch, httpx_mock):
    cfg = _connecte(tmp_path, monkeypatch)
    url = "https://sonarr.maison.example/api/v3/system/status"
    httpx_mock.add_callback(
        lambda r: httpx.Response(200 if r.headers.get("X-Api-Key") == "cle-de-cette-instance" else 401),
        url=url, is_reusable=True)
    resultat = remote_access.inspect(cfg, tmp_path)
    assert resultat["status"] == "checked"
    assert resultat["checks"] == [{"service": "sonarr", "ok": True, "reason": ""}]


@pytest.mark.parametrize("reponses,raison,extrait", [
    ([httpx.Response(401), httpx.Response(401)], "other_instance", "autre instance"),
    ([httpx.Response(530, text="error code: 1033")], "tunnel", "aucun connecteur actif"),
    ([httpx.Response(502)], "origin", "http://sonarr:8989"),
    ([httpx.Response(404)], "route", "pas de route"),
    ([httpx.Response(302, headers={"location": "https://moi.cloudflareaccess.com/cdn-cgi/access/login"})],
     "access", "Cloudflare Access"),
    ([httpx.Response(403, headers={"cf-mitigated": "challenge"})], "challenge", "anti-robot"),
    ([httpx.Response(403)], "blocked", "403"),
    ([httpx.Response(200, json={"version": "4"})], "open", "sans identifiants"),
])
def test_chaque_panne_de_route_a_son_explication(tmp_path, monkeypatch, httpx_mock, reponses, raison, extrait):
    cfg = _connecte(tmp_path, monkeypatch)
    for reponse in reponses:
        httpx_mock.add_response(url="https://sonarr.maison.example/api/v3/system/status",
                                status_code=reponse.status_code, headers=dict(reponse.headers),
                                content=reponse.content)
    resultat = remote_access.inspect(cfg, tmp_path)
    assert resultat["status"] == "pending"
    assert resultat["checks"][0]["reason"] == raison
    assert extrait in resultat["message"]


def test_une_adresse_absente_du_dns_demande_sa_route(tmp_path, monkeypatch):
    cfg = _connecte(tmp_path, monkeypatch, names={"sonarr": "series"})
    monkeypatch.setattr(remote_access.socket, "getaddrinfo", Mock(side_effect=OSError("NXDOMAIN")))
    resultat = remote_access.inspect(cfg, tmp_path)
    assert resultat["checks"][0]["reason"] == "dns"
    assert "series.maison.example" in resultat["message"] and "route" in resultat["message"]


def test_qbittorrent_anonyme_refuse_suffit(tmp_path, monkeypatch, httpx_mock):
    cfg = _connecte(tmp_path, monkeypatch, services=("qbittorrent",))
    httpx_mock.add_response(url="https://qb.maison.example/api/v2/app/preferences", status_code=403, text="Forbidden")
    assert remote_access.inspect(cfg, tmp_path)["status"] == "checked"


# -- assistant web --------------------------------------------------------------


def test_la_page_ne_recoit_jamais_le_jeton(tmp_path):
    _, cfg = config(tmp_path)
    state = webwizard.WizardState(tmp_path, demo=True)
    state.previous = cfg
    amorce = state.bootstrap()
    assert TOKEN not in json.dumps(amorce)
    assert amorce["form"]["remote_access"]["tunnel_token_saved"] is True
    assert amorce["form"]["remote_access"]["mode"] == "cloudflare"


def test_un_champ_vide_garde_le_jeton_enregistre(tmp_path):
    _, cfg = config(tmp_path)
    state = webwizard.WizardState(tmp_path, demo=True)
    state.previous = cfg
    form = state.bootstrap()["form"]
    form.update(reprendre=True, remote_access={**form["remote_access"], "tunnel_token": ""})
    form["remote_access"].pop("tunnel_token_saved")
    assert state.build_config(form).remote_access.tunnel_token == TOKEN
    form.update(reprendre=False)
    with pytest.raises(ValueError, match="jeton"):
        state.build_config(form)


def test_un_jeton_invalide_est_refuse_sans_etre_renvoye(tmp_path):
    state = webwizard.WizardState(tmp_path, demo=True)
    form = state.bootstrap()["form"]
    secret = "eyJ" + "Z" * 60
    form.update(services=["sonarr"], reprendre=False,
                remote_access={"mode": "cloudflare", "domain": "maison.example", "services": ["sonarr"],
                               "tunnel_token": secret})
    with pytest.raises(ValueError) as erreur:
        state.build_config(form)
    assert "Jeton de tunnel illisible" in str(erreur.value)
    assert secret not in str(erreur.value)


def test_le_recapitulatif_et_les_erreurs_masquent_le_jeton(tmp_path):
    state, cfg = config(tmp_path)
    state.cfg = cfg
    assert state.redact(f"echec avec {TOKEN}") == "echec avec <masque>"


def test_un_serveur_ssh_attend_une_image_qui_connait_le_tunnel(tmp_path, monkeypatch):
    state = webwizard.WizardState(tmp_path, demo=True)
    form = state.bootstrap()["form"]
    form.update(services=["sonarr"], reprendre=False, platform="generic-linux",
                config_root="/srv/plugarr/config", data_root="/srv/data",
                remote_access={"mode": "cloudflare", "domain": "maison.example", "services": ["sonarr"],
                               "tunnel_token": TOKEN})
    monkeypatch.setattr(state, "_remote_connection_for", lambda _form: {"probe": Mock(uid=1000, gid=1000)})
    monkeypatch.setattr(catalog, "CONSOLE_IMAGE_TUNNEL_CLOUDFLARE", False)
    with pytest.raises(ValueError, match="image d’administration"):
        state.build_config(form)
