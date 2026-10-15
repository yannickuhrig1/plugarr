"""Adresses HTTPS privees par DNS-01 : le modele (docs/PLAN_HTTPS_DNS01.md, etape 1).

Les jetons de test ont la forme exacte de ceux de Cloudflare, avec des valeurs
fictives : aucun compte n'est contacte.
"""
import base64
import json
import os
import re
import stat
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
import yaml
from pydantic import ValidationError

from plugarr import catalog, remote_access, reprise, veille_config, webwizard
from plugarr.models import StackConfig
from plugarr.remote_models import RemoteAccessConfig, jeton_api_cloudflare

#: Jeton classique : 40 caracteres, comme ceux que Cloudflare delivre.
JETON = "plugarr-essai-jeton-api-0123456789abcdef"
#: Jeton d'utilisateur, nouvelle forme.
JETON_UTILISATEUR = "cfut_" + "E" * 40
CLE_GLOBALE = "0123456789abcdef0123456789abcdef01234"
JETON_TUNNEL = base64.b64encode(json.dumps({
    "a": "0123456789abcdef0123456789abcdef",
    "t": "6f1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d",
    "s": base64.b64encode(b"fictif-" * 5).decode(),
}).encode()).decode()


def choix(**champs):
    return RemoteAccessConfig(**{"mode": "tailscale", "domain": "maison.example",
                                 "services": ["sonarr", "qbittorrent"], "dns_token": JETON, **champs})


def config(tmp_path, **acces):
    state = webwizard.WizardState(tmp_path, demo=True)
    form = state.bootstrap()["form"]
    form.update(services=["sonarr", "qbittorrent"], host="192.0.2.50", reprendre=False,
                remote_access={"mode": "tailscale", "domain": "maison.example",
                               "services": ["sonarr", "qbittorrent"], "dns_token": JETON, **acces})
    return state, state.build_config(form)


# -- jeton ----------------------------------------------------------------------


@pytest.mark.parametrize("colle, attendu", [
    (JETON, JETON),
    (f"  {JETON}\n", JETON),
    (JETON_UTILISATEUR, JETON_UTILISATEUR),
    ("cfat_" + "a1_-" * 10, "cfat_" + "a1_-" * 10),
    # La commande de verification que Cloudflare affiche a la creation.
    (('curl "https://api.cloudflare.com/client/v4/user/tokens/verify" \\\n'
      f'     -H "Authorization: Bearer {JETON}"'), JETON),
])
def test_le_jeton_est_extrait_de_ce_que_cloudflare_affiche(colle, attendu):
    assert jeton_api_cloudflare(colle) == attendu
    assert choix(dns_token=colle).dns_token == attendu


@pytest.mark.parametrize("colle, raison", [
    (CLE_GLOBALE, "clé d’API globale"),
    (JETON_TUNNEL, "jeton d’un tunnel"),
    (f"sudo cloudflared service install {JETON_TUNNEL}", "jeton d’un tunnel"),
    ("trop-court", "illisible"),
    (f"{JETON} {JETON_UTILISATEUR}", "illisible"),
    ("cfut_" + "x" * 20, "illisible"),
])
def test_un_autre_secret_est_refuse_sans_etre_recopie(colle, raison):
    with pytest.raises(ValidationError) as erreur:
        choix(dns_token=colle)
    message = str(erreur.value.errors(include_input=False))
    assert raison in message
    for secret in (JETON, JETON_UTILISATEUR, CLE_GLOBALE, JETON_TUNNEL):
        assert secret not in message


# -- mode -----------------------------------------------------------------------


def test_un_domaine_en_mode_tailscale_demande_applications_et_jeton():
    actif = choix()
    assert actif.dns01
    assert JETON not in repr(actif)
    with pytest.raises(ValidationError, match="jeton d’API"):
        choix(dns_token="")
    with pytest.raises(ValidationError, match="au moins une application"):
        choix(services=[])


def test_sans_domaine_tailscale_reste_par_adresse_ip():
    simple = choix(domain="", services=[], https_port=8443)
    assert not simple.dns01
    assert simple.dns_token == ""
    assert simple.https_port == 443


@pytest.mark.parametrize("mode, extra", [
    ("https", {}),
    ("cloudflare", {"tunnel_token": JETON_TUNNEL}),
    ("local", {"domain": "", "services": []}),
])
def test_les_autres_modes_ne_gardent_ni_jeton_ni_port(mode, extra):
    autre = choix(mode=mode, https_port=8443, **extra)
    assert not autre.dns01
    assert autre.dns_token == ""
    assert autre.https_port == 443


def test_le_port_https_se_change_dans_les_limites():
    assert choix(https_port=8443).https_port == 8443
    for refuse in (0, 65536):
        with pytest.raises(ValidationError):
            choix(https_port=refuse)


# -- stack.yml ------------------------------------------------------------------


def test_une_pile_sans_dns01_reste_lisible_par_une_image_plus_ancienne(tmp_path):
    """L'image d'administration epinglee refuse un champ inconnu : une pile qui
    ne se sert pas de DNS-01 ne doit ecrire ni le jeton ni le port."""
    _, cfg = config(tmp_path, domain="", services=[], dns_token="")
    assert set(cfg.model_dump(mode="json")["remote_access"]) == {"mode", "domain", "services"}


def test_le_port_par_defaut_n_est_pas_ecrit_et_tout_se_relit(tmp_path):
    _, defaut = config(tmp_path)
    assert "https_port" not in defaut.model_dump(mode="json")["remote_access"]
    _, cfg = config(tmp_path / "p", https_port=8443, names={"sonarr": "series"})
    relu = StackConfig.model_validate(yaml.safe_load(yaml.safe_dump(cfg.model_dump(mode="json"))))
    assert relu.remote_access == cfg.remote_access
    assert relu.remote_access.dns_token == JETON
    assert relu.remote_access.https_port == 8443
    assert relu.remote_access.hostname("sonarr") == "series.maison.example"


# -- assistant web --------------------------------------------------------------


def test_la_page_ne_recoit_jamais_le_jeton(tmp_path):
    _, cfg = config(tmp_path)
    state = webwizard.WizardState(tmp_path, demo=True)
    state.previous = cfg
    amorce = state.bootstrap()
    assert JETON not in json.dumps(amorce)
    assert amorce["form"]["remote_access"]["dns_token_saved"] is True
    assert amorce["form"]["remote_access"]["tunnel_token_saved"] is False


def test_un_champ_vide_garde_le_jeton_enregistre(tmp_path):
    _, cfg = config(tmp_path)
    state = webwizard.WizardState(tmp_path, demo=True)
    state.previous = cfg
    form = state.bootstrap()["form"]
    form.update(reprendre=True, remote_access={**form["remote_access"], "dns_token": ""})
    assert state.build_config(form).remote_access.dns_token == JETON
    form.update(reprendre=False)
    with pytest.raises(ValueError, match="jeton d’API"):
        state.build_config(form)


def test_un_jeton_invalide_est_refuse_sans_etre_renvoye(tmp_path):
    with pytest.raises(ValueError) as erreur:
        config(tmp_path, dns_token=CLE_GLOBALE)
    assert "clé d’API globale" in str(erreur.value)
    assert CLE_GLOBALE not in str(erreur.value)


def test_le_plan_et_les_erreurs_masquent_le_jeton(tmp_path):
    state, cfg = config(tmp_path)
    state.cfg = cfg
    assert state.redact(f"echec avec {JETON}") == "echec avec <masque>"
    form = state.bootstrap()["form"]
    form.update(services=["sonarr", "qbittorrent"], reprendre=False,
                remote_access={"mode": "tailscale", "domain": "maison.example",
                               "services": ["sonarr"], "dns_token": JETON})
    plan = state.validate(form)
    assert plan["remote_access"]["domain"] == "maison.example"
    assert JETON not in json.dumps(plan)


# -- passerelle -----------------------------------------------------------------

RECETTE = Path(__file__).resolve().parent.parent / "packaging" / "caddy"


def _sans_commentaires(texte):
    return [ligne.rstrip() for ligne in texte.splitlines() if ligne.strip() and not ligne.strip().startswith("#")]


def test_le_caddyfile_est_celui_que_la_ci_fait_valider_par_caddy(tmp_path):
    """La CI de l'image (`.github/workflows/caddy.yml`) passe
    `packaging/caddy/essai.Caddyfile` a `caddy validate`. Le rendu doit lui
    rester identique : sinon, PlugArr ecrirait une configuration que rien n'a
    fait verifier par Caddy."""
    _, cfg = config(tmp_path)
    cfg.vpn.enabled = True
    rendu = remote_access.caddyfile_dns01(cfg)
    essai = (RECETTE / "essai.Caddyfile").read_text(encoding="utf-8")
    assert _sans_commentaires(rendu) == _sans_commentaires(essai)


def test_le_caddyfile_suit_les_noms_et_ne_porte_pas_le_jeton(tmp_path):
    state = webwizard.WizardState(tmp_path, demo=True)
    form = state.bootstrap()["form"]
    form.update(services=["sonarr", "radarr", "qbittorrent"], host="192.0.2.50", reprendre=False,
                remote_access={"mode": "tailscale", "domain": "maison.example",
                               "services": ["radarr", "qbittorrent"], "names": {"radarr": "films"},
                               "dns_token": JETON})
    rendu = remote_access.caddyfile_dns01(state.build_config(form))
    assert JETON not in rendu
    assert "{env.CLOUDFLARE_API_TOKEN}" in rendu
    # Un seul bloc de site, le wildcard ; Sonarr, non publie, n'y est pas.
    blocs = [ligne for ligne in rendu.splitlines() if ligne.endswith("{") and not ligne[:1].isspace()]
    assert blocs == ["{", "*.maison.example {"]
    assert "@radarr host films.maison.example" in rendu
    assert "@qbittorrent host qb.maison.example" in rendu
    assert "sonarr" not in rendu
    # Le filtre passe avant les applications, l'abort final apres.
    assert rendu.index("@hors_reseau") < rendu.index("@radarr") < rendu.rindex("handle {")


def test_un_service_adopte_n_est_pas_publie(tmp_path):
    _, cfg = config(tmp_path)
    cfg.services["sonarr"].adopted = True
    with pytest.raises(ValueError, match="gérés par PlugArr"):
        remote_access.caddyfile_dns01(cfg)


def test_caddy_s_ajoute_a_tailscale_sans_port_80_ni_secret(tmp_path):
    _, cfg = config(tmp_path, https_port=8443)
    compose = remote_access.gateway_compose(cfg)
    assert set(compose["services"]) == {"gateway", "caddy"}
    caddy = compose["services"]["caddy"]
    assert caddy["image"] == remote_access.CADDY_DNS01_IMAGE
    assert caddy["ports"] == ["8443:443"]
    assert caddy["env_file"] == ["./caddy.env"]
    assert caddy["networks"] == ["applications"]
    assert compose["networks"]["applications"] == {"external": True, "name": cfg.project_name + "_plugarr"}
    assert compose["services"]["gateway"]["image"] == remote_access.TAILSCALE_IMAGE
    assert all(s["labels"] == {"plugarr.remote": "true"} for s in compose["services"].values())
    assert JETON not in json.dumps(compose)


def test_avec_tailscale_installe_caddy_est_seul(tmp_path):
    _, cfg = config(tmp_path)
    compose = remote_access.gateway_compose(cfg, tailscale_natif=True)
    assert set(compose["services"]) == {"caddy"}
    assert compose["services"]["caddy"]["ports"] == ["443:443"]


def test_sans_domaine_la_passerelle_tailscale_ne_change_pas(tmp_path):
    _, cfg = config(tmp_path, domain="", services=[], dns_token="")
    compose = remote_access.gateway_compose(cfg)
    assert set(compose) == {"services"}
    assert set(compose["services"]) == {"gateway"}


def test_un_service_etranger_dans_le_compose_bloque_le_remplacement(tmp_path):
    _, cfg = config(tmp_path)
    dossier = tmp_path / ".plugarr-remote"
    dossier.mkdir()
    compose = remote_access.gateway_compose(cfg)
    (dossier / "compose.yml").write_text(yaml.safe_dump(compose), encoding="utf-8")
    remote_access._check_owned(dossier)
    compose["services"]["autre"] = {"image": "nginx"}
    (dossier / "compose.yml").write_text(yaml.safe_dump(compose), encoding="utf-8")
    with pytest.raises(ValueError, match="non gérée par PlugArr"):
        remote_access._check_owned(dossier)


def test_l_image_epinglee_est_celle_de_la_recette():
    recette = (RECETTE / "Dockerfile").read_text(encoding="utf-8")
    caddy = re.search(r"^ARG CADDY_RELEASE=v(\S+)$", recette, re.MULTILINE).group(1)
    module = re.search(r"^ARG CLOUDFLARE_RELEASE=v(\S+)$", recette, re.MULTILINE).group(1)
    reference = remote_access.CADDY_DNS01_IMAGE.split("@")[0]
    assert reference == f"ghcr.io/yannickuhrig1/plugarr-caddy:{caddy}-cloudflare-{module}"


@pytest.mark.xfail(strict=True, reason="image plugarr-caddy pas encore publiee : epingler son condensat")
def test_l_image_est_epinglee_par_condensat():
    """Strict : des que le condensat est ajoute, ce test passe et le marqueur
    doit partir. Il rappelle, d'ici la, que l'image n'est pas figee."""
    assert re.search(r"@sha256:[0-9a-f]{64}$", remote_access.CADDY_DNS01_IMAGE)


# -- activation -----------------------------------------------------------------

IP = "100.101.102.103"
ZONES = "https://api.cloudflare.com/client/v4/zones?name="


def _tailscale_natif(monkeypatch, etat="Running"):
    """Tailscale installe sur la machine, connecte avec l'adresse IP."""
    statut = {"BackendState": etat, "TailscaleIPs": [IP, "fd7a:115c:a1e0::1"]}
    monkeypatch.setattr(remote_access.shutil, "which", lambda nom: "/usr/bin/tailscale" if nom == "tailscale" else None)
    monkeypatch.setattr(remote_access.runner, "_run",
                        lambda cmd, **_k: Mock(returncode=0, stdout=json.dumps(statut)))


def _activer(tmp_path, monkeypatch, cfg):
    commandes = []
    proteger = Mock()
    monkeypatch.setattr(remote_access, "_protect_applications", proteger)
    monkeypatch.setattr(remote_access, "_command", lambda _cfg, _dir, *args, **_k: commandes.append(args) or "")
    monkeypatch.setattr(remote_access, "inspect", lambda *_a, **_k: {"status": "pending"})
    remote_access.activate(cfg, tmp_path)
    return commandes, proteger


def test_l_activation_pose_caddy_seul_a_cote_du_tailscale_installe(tmp_path, monkeypatch, httpx_mock):
    _, cfg = config(tmp_path)
    _tailscale_natif(monkeypatch)
    httpx_mock.add_response(url=ZONES + "maison.example", json={"result": [{"name": "maison.example"}]})
    commandes, proteger = _activer(tmp_path, monkeypatch, cfg)
    dossier = tmp_path / ".plugarr-remote"
    assert set(yaml.safe_load((dossier / "compose.yml").read_text(encoding="utf-8"))["services"]) == {"caddy"}
    assert (dossier / "caddy.env").read_text(encoding="utf-8") == f"CLOUDFLARE_API_TOKEN={JETON}\n"
    assert JETON not in (dossier / "Caddyfile").read_text(encoding="utf-8")
    assert JETON not in (dossier / "compose.yml").read_text(encoding="utf-8")
    # Pas de `tailscale up` dans un conteneur qui n'existe pas.
    assert commandes == [("up", "-d", "--force-recreate")]
    proteger.assert_called_once()
    assert httpx_mock.get_requests()[0].headers["Authorization"] == f"Bearer {JETON}"
    if os.name != "nt":
        for nom in ("caddy.env", "Caddyfile", "compose.yml"):
            assert stat.S_IMODE((dossier / nom).stat().st_mode) == 0o600


def test_la_zone_se_trouve_en_remontant_le_domaine(tmp_path, httpx_mock):
    _, cfg = config(tmp_path, domain="nas.maison.example")
    httpx_mock.add_response(url=ZONES + "nas.maison.example", json={"result": []})
    httpx_mock.add_response(url=ZONES + "maison.example", json={"result": [{"name": "maison.example"}]})
    assert remote_access._zone_cloudflare(cfg.remote_access) == "maison.example"


@pytest.mark.parametrize("reponse, extrait", [
    ({"status_code": 403, "json": {"success": False, "errors": [{"code": 9109}]}}, "refuse ce jeton"),
    ({"json": {"result": []}}, "ne voit aucune zone"),
    ({"text": "<html>"}, "ne répond pas"),
])
def test_un_jeton_inutilisable_ne_change_rien(tmp_path, monkeypatch, httpx_mock, reponse, extrait):
    _, cfg = config(tmp_path)
    _tailscale_natif(monkeypatch)
    httpx_mock.add_response(url=ZONES + "maison.example", **reponse)
    with pytest.raises(ValueError, match=extrait) as erreur:
        _activer(tmp_path, monkeypatch, cfg)
    assert JETON not in str(erreur.value)
    dossier = tmp_path / ".plugarr-remote"
    assert not (dossier / "caddy.env").exists() and not (dossier / "compose.yml").exists()


def test_quitter_dns01_retire_le_jeton_meme_sans_passerelle(tmp_path, monkeypatch):
    _, cfg = config(tmp_path, domain="", services=[], dns_token="")
    dossier = tmp_path / ".plugarr-remote"
    dossier.mkdir()
    (dossier / "caddy.env").write_text(f"CLOUDFLARE_API_TOKEN={JETON}\n", encoding="utf-8")
    _tailscale_natif(monkeypatch)
    assert remote_access.activate(cfg, tmp_path)["status"] == "connected"
    assert not (dossier / "caddy.env").exists()


def test_les_applications_publiees_ont_leur_adresse_https(tmp_path):
    _, cfg = config(tmp_path, services=["sonarr"], https_port=8443)
    assert remote_access.external_urls(cfg, IP) == {
        "sonarr": "https://sonarr.maison.example:8443",
        "qbittorrent": f"http://{IP}:8080",
    }
    assert remote_access.external_urls(cfg) == {"sonarr": "https://sonarr.maison.example:8443"}


def test_la_simulation_montre_les_enregistrements_a_creer(tmp_path):
    _, cfg = config(tmp_path)
    resultat = remote_access.activate(cfg, tmp_path, demo=True)
    assert resultat["urls"]["sonarr"] == "https://sonarr.maison.example"
    assert resultat["records"] == [
        {"service": s, "hostname": h, "type": "A", "content": IP, "proxied": False}
        for s, h in (("sonarr", "sonarr.maison.example"), ("qbittorrent", "qb.maison.example"))
    ]


# -- diagnostic -----------------------------------------------------------------


def _en_ligne(tmp_path, monkeypatch, adresses=(IP,), journal=""):
    _, cfg = config(tmp_path, services=["sonarr"])
    cfg.services["sonarr"].api_key = "cle-de-cette-instance"
    dossier = tmp_path / ".plugarr-remote"
    dossier.mkdir()
    (dossier / "compose.yml").write_text(
        yaml.safe_dump(remote_access.gateway_compose(cfg, tailscale_natif=True)), encoding="utf-8")
    _tailscale_natif(monkeypatch)
    monkeypatch.setattr(remote_access, "_command", lambda *_a, **_k: journal)
    if adresses:
        monkeypatch.setattr(remote_access.socket, "getaddrinfo",
                            lambda *_a, **_k: [(2, 1, 6, "", (a, 0)) for a in adresses])
    else:
        monkeypatch.setattr(remote_access.socket, "getaddrinfo", Mock(side_effect=OSError("NXDOMAIN")))
    return cfg


URL_SONARR = "https://sonarr.maison.example/api/v3/system/status"


def test_tout_est_en_place(tmp_path, monkeypatch, httpx_mock):
    cfg = _en_ligne(tmp_path, monkeypatch)
    httpx_mock.add_callback(
        lambda r: httpx.Response(200 if r.headers.get("X-Api-Key") == "cle-de-cette-instance" else 401),
        url=URL_SONARR, is_reusable=True)
    resultat = remote_access.inspect(cfg, tmp_path)
    assert resultat["status"] == "checked"
    assert resultat["urls"] == {"sonarr": "https://sonarr.maison.example", "qbittorrent": f"http://{IP}:8080"}
    assert resultat["records"][0]["content"] == IP


def test_sans_tailscale_connecte_rien_n_est_teste(tmp_path, monkeypatch):
    cfg = _en_ligne(tmp_path, monkeypatch)
    _tailscale_natif(monkeypatch, etat="NeedsLogin")
    monkeypatch.setattr(remote_access, "_check_dns01", Mock(side_effect=AssertionError("DNS")))
    assert remote_access.inspect(cfg, tmp_path)["status"] == "association"


def test_un_nom_qui_mene_ailleurs_est_signale(tmp_path, monkeypatch):
    cfg = _en_ligne(tmp_path, monkeypatch, adresses=("104.16.0.1",))
    resultat = remote_access.inspect(cfg, tmp_path)
    assert resultat["checks"][0]["reason"] == "wrong_address"
    assert "104.16.0.1" in resultat["message"] and "nuage gris" in resultat["message"]


@pytest.mark.parametrize("publiques, raison, extrait", [
    ([], "dns", f"Créez l’enregistrement A sonarr.maison.example vers {IP}"),
    ([IP], "rebind", "DNS rebinding"),
])
def test_un_nom_absent_ou_bloque_par_la_box(tmp_path, monkeypatch, httpx_mock, publiques, raison, extrait):
    cfg = _en_ligne(tmp_path, monkeypatch, adresses=())
    httpx_mock.add_response(url=f"{remote_access.DOH_URL}?name=sonarr.maison.example&type=A",
                            json={"Answer": [{"type": 1, "data": a} for a in publiques]})
    resultat = remote_access.inspect(cfg, tmp_path)
    assert resultat["checks"][0]["reason"] == raison
    assert extrait in resultat["message"]


@pytest.mark.parametrize("journal, extrait", [
    ("", "quelques minutes"),
    ('{"msg":"could not get certificate from issuer","error":"timed out waiting for record to fully propagate"}',
     "pas encore propagé"),
    ('{"msg":"could not get certificate from issuer","error":"HTTP 403: Authentication error"}', "DNS:Edit"),
    ('{"msg":"could not get certificate from issuer"}\n{"msg":"certificate obtained successfully"}',
     "Caddy l’a obtenu"),
])
def test_un_certificat_absent_s_explique_par_le_journal(tmp_path, monkeypatch, httpx_mock, journal, extrait):
    cfg = _en_ligne(tmp_path, monkeypatch, journal=journal)
    erreur = httpx.ConnectError("[SSL: TLSV1_ALERT_INTERNAL_ERROR] tlsv1 alert internal error")
    httpx_mock.add_exception(erreur, url=URL_SONARR)
    resultat = remote_access.inspect(cfg, tmp_path)
    assert resultat["checks"][0]["reason"] == "certificate"
    assert extrait in resultat["message"]


@pytest.mark.parametrize("mode, extrait", [
    ("https", "ports 80 et 443"),
    ("cloudflare", "un niveau de sous-domaine"),
])
def test_un_certificat_refuse_hors_dns01_a_aussi_son_explication(tmp_path, mode, extrait):
    """Avant, une erreur TLS passait pour une adresse muette ; elle se nomme
    desormais, avec la cause propre a chaque mode."""
    _, cfg = config(tmp_path, mode=mode, dns_token="", tunnel_token=JETON_TUNNEL if mode == "cloudflare" else "")
    texte = remote_access._explain(cfg, {"service": "sonarr", "reason": "certificate"})
    assert "pas encore valide" in texte and extrait in texte


def test_une_passerelle_qui_ne_demarre_pas_nomme_son_port(tmp_path, monkeypatch):
    _, cfg = config(tmp_path, https_port=8443)
    monkeypatch.setattr(remote_access.runner, "_run", lambda *_a, **_k: Mock(returncode=1, stdout=""))
    with pytest.raises(ValueError, match="port 8443"):
        remote_access._command(cfg, tmp_path, "up")


# -- images epinglees, reprise et veille ----------------------------------------


def test_l_image_d_administration_doit_connaitre_dns01(monkeypatch):
    monkeypatch.setattr(catalog, "CONSOLE_IMAGE_TUNNEL_CLOUDFLARE", True)
    monkeypatch.setattr(catalog, "CONSOLE_IMAGE_DNS01", False)
    assert not remote_access.admin_image_ready(choix())
    assert remote_access.admin_image_ready(choix(domain="", services=[]))
    monkeypatch.setattr(catalog, "CONSOLE_IMAGE_DNS01", True)
    assert remote_access.admin_image_ready(choix())


def test_la_console_en_conteneur_attend_une_image_qui_connait_dns01(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "CONSOLE_IMAGE_DNS01", False)
    state = webwizard.WizardState(tmp_path, demo=True)
    form = state.bootstrap()["form"]
    form.update(services=["sonarr"], reprendre=False, console_enabled=True,
                remote_access={"mode": "tailscale", "domain": "maison.example", "services": ["sonarr"],
                               "dns_token": JETON})
    with pytest.raises(ValueError, match="console en conteneur ne connaît pas encore cet accès"):
        state.build_config(form)
    form["remote_access"] = {"mode": "tailscale", "domain": "", "services": []}
    assert state.build_config(form).console_enabled is True


def test_sans_application_publiee_la_reprise_garde_tailscale_par_ip(tmp_path):
    _, ancienne = config(tmp_path, services=["qbittorrent"], https_port=8443)
    _, neuve = config(tmp_path / "n", domain="", services=[], dns_token="")
    del neuve.services["qbittorrent"]
    reprise.appliquer(neuve, ancienne)
    assert neuve.remote_access.mode == "tailscale"
    assert not neuve.remote_access.dns01
    assert neuve.remote_access.dns_token == ""
    assert neuve.remote_access.https_port == 443


def test_la_veille_ne_recoit_pas_le_jeton(tmp_path):
    _, cfg = config(tmp_path)
    reduit = veille_config.reduire(cfg).model_dump(mode="json")
    assert reduit["remote_access"] == {"mode": "local", "domain": "", "services": []}
    assert JETON not in json.dumps(reduit)
    assert cfg.remote_access.dns_token == JETON
