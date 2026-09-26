"""Contrats sensibles de l'assistant web, avec serveur HTTP local et moteur simule."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from typer.testing import CliRunner

from plugarr import adminauth, catalog, compose, interface, orchestrator, remote_install, webwizard
from plugarr.cli import app
from plugarr.layout import default_profile
from plugarr.models import VpnConfig
from plugarr.runner import Check
from plugarr.wiring import StepResult


@pytest.fixture(autouse=True)
def _aucune_pile_distante(monkeypatch):
    """Le test SSH inspecte aussi la pile distante : par defaut, il n'y en a pas."""
    monkeypatch.setattr(
        remote_install,
        "inspect_project",
        lambda *_args, **_kwargs: remote_install.RemoteProjectState(exists=False, managed=False),
    )


@pytest.fixture
def server(tmp_path):
    server = webwizard.WizardServer(tmp_path, demo=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with httpx.Client(
        base_url=server.origin,
        trust_env=False,
        timeout=10,
        headers={"Authorization": "Bearer " + server.token},
    ) as client:
        yield server, client
    if server.state.admin_server:
        server.state.admin_server.shutdown()
        server.state.admin_server.server_close()
    server.state.close_resources()
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)
    if server.state.worker:
        server.state.worker.join(timeout=5)


def fields(state):
    return state.bootstrap()["form"]


def test_demo_goes_from_catalog_to_completion_without_docker_or_user_config(server, monkeypatch):
    srv, client = server
    forbidden = Mock(side_effect=AssertionError("Un appel reel a echappe au mode demo"))
    monkeypatch.setattr(orchestrator, "install", forbidden)
    monkeypatch.setattr(orchestrator, "preflight", forbidden)
    monkeypatch.setattr(webwizard.migrations, "lire", forbidden)
    monkeypatch.setattr(webwizard, "save_preference", forbidden)
    form = client.get("/api/bootstrap").json()["form"]
    form["services"] = ["flood"]
    deps = client.post("/api/selection", json={"services": ["flood"]}).json()["services"]
    assert "qbittorrent" in deps
    plan = client.post("/api/validate", json=form).json()
    assert plan["demo"] and plan["plan_id"] and plan["checks"] == []
    assert "qbittorrent" in [s["id"] for s in plan["services"]]
    assert (
        client.post("/api/install", json={"plan_id": plan["plan_id"], "confirm": True}).status_code
        == 200
    )
    assert (
        client.post("/api/install", json={"plan_id": plan["plan_id"], "confirm": True}).status_code
        == 400
    )
    srv.state.worker.join(timeout=5)
    progress = client.get("/api/progress").json()
    assert progress["status"] == "done"
    assert set(progress["graph_results"]) == set(progress["graph"]["etapes"])
    assert client.post("/api/admin", json={}).status_code == 200
    assert client.post("/api/preference", json={"interface": "web"}).status_code == 400
    assert list(srv.state.project_dir.iterdir()) == []
    forbidden.assert_not_called()


def test_un_corps_refuse_recoit_sa_reponse_et_pas_une_coupure(server):
    """L'instabilite qui deplacait l'echec de test en test.

    Refuser un POST sans lire son corps laisse des octets non lus dans la
    socket. La fermer dans cet etat fait repondre un RST a la pile TCP, et le
    client perd la reponse deja ecrite : « [WinError 10053] Une connexion
    etablie a ete abandonnee » au lieu du 400 annonce.

    A 65 537 octets le corps tient souvent dans les tampons, et la suite
    echouait donc environ une fois sur trois, sur un test different a chaque
    fois. A 5 Mo c'est certain. Dans un navigateur, cela donne un
    « Failed to fetch » la ou l'assistant avait une phrase a dire.

    Les quatre chemins de refus sont couverts : la taille, le type de contenu,
    l'origine et le jeton. Chacun repond sans le corps, donc chacun peut fermer
    sur des octets non lus.
    """
    _, client = server
    gros = "x" * 5_000_000

    taille = client.post(
        "/api/install", content=gros, headers={"Content-Type": "application/json"}
    )
    assert taille.status_code == 400
    assert "error" in taille.json(), "le refus doit porter son message, pas une coupure"

    typage = client.post("/api/install", content=gros, headers={"Content-Type": "text/plain"})
    assert typage.status_code == 400

    origine = client.post(
        "/api/install",
        content=gros,
        headers={"Content-Type": "application/json", "Origin": "https://attaquant.test"},
    )
    assert origine.status_code == 403

    jeton = client.post(
        "/api/install",
        content=gros,
        headers={"Content-Type": "application/json", "Authorization": ""},
    )
    assert jeton.status_code == 401


def test_la_vidange_est_plafonnee(server):
    """Un Content-Length enorme ne doit pas faire lire des giga-octets.

    Le plafond est assume : au-dela, la coupure nette est preferable a une
    lecture sans fin. Aucun client legitime n'envoie autant, et le serveur
    n'ecoute que sur 127.0.0.1 derriere un jeton.
    """
    from plugarr.admin import VIDANGE_MAX

    assert 0 < VIDANGE_MAX <= 64 * 1024 * 1024


def test_api_rejects_other_origins_hosts_and_missing_sessions(server):
    _, client = server
    assert client.get("/").status_code == 200
    assert client.get("/api/bootstrap", headers={"Authorization": ""}).status_code == 401
    assert client.get("/api/startup", headers={"Authorization": ""}).status_code == 401
    assert client.get("/api/access", headers={"Authorization": ""}).status_code == 401
    assert client.get("/api/bootstrap", headers={"Host": "attacker.test"}).status_code == 403
    assert (
        client.post(
            "/api/install", json={}, headers={"Origin": "https://attacker.test"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/install", content="{}", headers={"Content-Type": "text/plain"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/install", content="x" * 65537, headers={"Content-Type": "application/json"}
        ).status_code
        == 400
    )
    assert client.post("/api/install", json={}).status_code == 400
    page = client.get("/")
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert page.headers["cache-control"] == "no-store"
    assert client.get("/wizard.js").status_code == 200
    assert client.get("/wizard.css").status_code == 200
    assert client.get("/wizard-profile.css").status_code == 200
    assert client.get("/wizard-parity.css").status_code == 200
    assert client.get("/api/unknown").status_code == 404


def test_api_sonde_une_cible_ssh_et_ne_renvoie_jamais_son_secret(server, monkeypatch):
    srv, client = server

    def fake_probe(target, credentials, *, connect):
        assert target.host == "nas.local"
        assert target.port == 2222
        assert target.username == "yannick"
        assert credentials.password == "secret-ssh"
        assert connect is remote_install.connect_paramiko
        return remote_install.RemoteProbe(
            fingerprint="SHA256:serveur-maison",
            system="Linux",
            machine="x86_64",
            uid=1000,
            gid=100,
            home="/home/yannick",
            docker_version="29.8.1",
        )

    monkeypatch.setattr(remote_install, "probe", fake_probe)
    response = client.post(
        "/api/remote-install/probe",
        json={
            "host": "nas.local",
            "port": 2222,
            "username": "yannick",
            "password": "secret-ssh",
            "private_key": "",
            "passphrase": "",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["connection_id"]
    assert result["fingerprint"] == "SHA256:serveur-maison"
    assert result["ready"] is True
    assert result["project_dir"] == "/home/yannick/plugarr"
    assert result["config_root"] == "/home/yannick/plugarr/config"
    assert "secret-ssh" not in response.text
    assert result["connection_id"] in srv.state.remote_connections


def test_web_installe_sur_la_cible_confirmee_sans_preflight_docker_local(server, monkeypatch):
    srv, client = server
    srv.state.demo = False
    monkeypatch.setattr(
        remote_install,
        "probe",
        lambda *_args, **_kwargs: remote_install.RemoteProbe(
            fingerprint="SHA256:serveur-maison",
            system="Linux",
            machine="x86_64",
            uid=1000,
            gid=100,
            home="/home/yannick",
            docker_version="29.8.1",
        ),
    )
    monkeypatch.setattr(
        remote_install,
        "inspect_project",
        lambda *_args, **_kwargs: remote_install.RemoteProjectState(
            exists=False, managed=False
        ),
    )
    probe_result = client.post(
        "/api/remote-install/probe",
        json={
            "host": "nas.local",
            "port": 22,
            "username": "yannick",
            "password": "secret-ssh",
        },
    ).json()
    local_preflight = Mock(side_effect=AssertionError("preflight local interdit"))
    monkeypatch.setattr(orchestrator, "preflight", local_preflight)
    deployments = []

    def fake_deploy(target, credentials, deployment, *, connect, on_event):
        deployments.append((target, credentials, deployment, connect))
        on_event({"kind": "progress", "phase": "images Docker", "message": "Images pretes"})
        on_event(
            {
                "kind": "step",
                "name": "Prowlarr vers Sonarr",
                "detail": "Connexion verifiee",
                "ok": True,
                "step_id": "prowlarr-sonarr",
            }
        )
        on_event({"kind": "credentials", "services": {
            "prowlarr": {"api_key": "a" * 32},
            "qbittorrent": {"username": "ancien", "password": "mot-de-passe-repris"},
        }})
        on_event({"kind": "done", "status": "done"})
        return remote_install.RemoteDeployResult(status="done", events=())

    monkeypatch.setattr(remote_install, "deploy", fake_deploy)
    form = fields(srv.state)
    form.update(
        {
            "services": ["sonarr", "prowlarr", "qbittorrent"],
            "install_target": "ssh",
            "remote_connection_id": probe_result["connection_id"],
            "remote_fingerprint": probe_result["fingerprint"],
            "remote_project_dir": probe_result["project_dir"],
            "platform": "generic-linux",
            "config_root": probe_result["config_root"],
            "data_root": probe_result["data_root"],
            "host": "nas.local",
            "reprendre": False,
            "console_enabled": True,
        }
    )
    plan = client.post("/api/validate", json=form)

    assert plan.status_code == 200, plan.text
    summary = plan.json()
    assert summary["install_target"] == "ssh"
    assert summary["project_dir"] == "/home/yannick/plugarr"
    assert summary["puid"] == 1000
    assert summary["pgid"] == 100
    assert summary["plan_id"]
    started = client.post(
        "/api/install", json={"plan_id": summary["plan_id"], "confirm": True}
    )
    assert started.status_code == 200
    srv.state.worker.join(timeout=5)

    assert client.get("/api/progress").json()["status"] == "done"
    assert len(deployments) == 1
    target, credentials, deployment, connect = deployments[0]
    assert target.expected_fingerprint == "SHA256:serveur-maison"
    assert credentials.password == "secret-ssh"
    assert connect is remote_install.connect_paramiko
    assert deployment.project_dir == "/home/yannick/plugarr"
    assert "services:" in deployment.stack_yaml
    assert list(srv.state.launch_project_dir.iterdir()) == []
    local_preflight.assert_not_called()
    report = client.get("/api/report").json()
    assert report["console_url"] == "http://nas.local:7373/"
    assert report["console_password"]
    assert adminauth.verify_password(
        report["console_password"], srv.state.cfg.admin_password_hash
    )
    assert report["console_password"] not in deployment.stack_yaml
    assert srv.state.cfg.admin_password_hash in deployment.stack_yaml
    assert report["console_password"] not in client.get("/api/progress").text
    assert report["console_password"] in client.get("/api/access").text
    services = {item["id"]: item for item in report["services"]}
    assert services["prowlarr"]["api_key"] == "a" * 32
    assert services["qbittorrent"]["password"] == "mot-de-passe-repris"
    assert "mot-de-passe-repris" not in client.get("/api/progress").text


def test_pile_ssh_existante_demande_une_confirmation_distante_et_ignore_le_nettoyage_local(
    tmp_path, monkeypatch
):
    state = webwizard.WizardState(tmp_path, demo=True)
    state.previous = orchestrator.build_config(
        services=["sonarr"],
        config_root=str(tmp_path / "ancienne-config"),
        data_root=str(tmp_path / "medias"),
        platform=default_profile(),
    )
    probe_result = remote_install.RemoteProbe(
        fingerprint="SHA256:serveur-maison",
        system="Linux",
        machine="aarch64",
        uid=1000,
        gid=1000,
        home="/home/yannick",
        docker_version="29.8.1",
    )
    state.remote_connections["remote-1"] = {
        "target": remote_install.RemoteTarget(
            host="nas.local", username="yannick"
        ),
        "credentials": remote_install.RemoteCredentials(password="secret"),
        "probe": probe_result,
        "created_at": webwizard.time.monotonic(),
    }
    monkeypatch.setattr(
        remote_install,
        "inspect_project",
        lambda *_args, **_kwargs: remote_install.RemoteProjectState(
            exists=True, managed=True, stack_sha="ancienne-pile",
            project_name="plugarr", config_root="/home/yannick/plugarr/config",
            data_root="/home/yannick/data", services=("sonarr",),
        ),
    )
    form = fields(state)
    form.update(
        install_target="ssh",
        remote_connection_id="remote-1",
        remote_fingerprint=probe_result.fingerprint,
        remote_project_dir="/home/yannick/plugarr",
        platform="generic-linux",
        config_root="/home/yannick/plugarr/config",
        data_root="/home/yannick/data",
        host="nas.local",
        reprendre=False,
        reset_config=False,
    )

    blocked = state.validate(form)
    assert blocked["blocked"] is True
    assert blocked["plan_id"] is None
    assert blocked["remote_replace_required"] is True
    assert blocked["remote_replace_managed"] is True
    assert blocked["reset_candidates"] == ["sonarr"]

    form["remote_replace"] = True
    confirmed = state.validate(form)
    assert confirmed["blocked"] is False
    assert confirmed["plan_id"]
    assert confirmed["remote_replace_confirmed"] is True
    assert confirmed["reset_candidates"] == ["sonarr"]
    assert confirmed["reset_requested"] is False

    form["reset_config"] = True
    reset_plan = state.validate(form)
    assert reset_plan["blocked"] is False
    assert reset_plan["reset_requested"] is True
    assert reset_plan["reset_locations"] == []


def test_essai_vpn_ssh_utilise_le_docker_distant(server, monkeypatch):
    srv, client = server
    srv.state.demo = False
    monkeypatch.setattr(
        remote_install,
        "probe",
        lambda *_args, **_kwargs: remote_install.RemoteProbe(
            fingerprint="SHA256:serveur-maison",
            system="Linux",
            machine="aarch64",
            uid=1000,
            gid=1000,
            home="/home/yannick",
            docker_version="29.8.1",
        ),
    )
    probe_result = client.post(
        "/api/remote-install/probe",
        json={
            "host": "nas.local",
            "port": 22,
            "username": "yannick",
            "password": "secret-ssh",
        },
    ).json()
    local_test = Mock(side_effect=AssertionError("Docker local interdit"))
    monkeypatch.setattr(webwizard.vpnessai, "essayer", local_test)
    calls = []

    def fake_remote_test(target, credentials, vpn, **kwargs):
        calls.append((target, credentials, vpn, kwargs))
        return {
            "name": "Essai VPN",
            "ok": True,
            "detail": "tunnel distant etabli",
            "blocking": False,
        }

    monkeypatch.setattr(remote_install, "test_vpn", fake_remote_test)
    response = client.post(
        "/api/vpn-test",
        json={
            "install_target": "ssh",
            "remote_connection_id": probe_result["connection_id"],
            "remote_fingerprint": probe_result["fingerprint"],
            "vpn": {
                "enabled": True,
                "provider": "protonvpn",
                "vpn_type": "wireguard",
                "wireguard_private_key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
                "countries": "France",
            },
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["detail"] == "tunnel distant etabli"
    assert len(calls) == 1
    target, credentials, _vpn, kwargs = calls[0]
    assert target.expected_fingerprint == probe_result["fingerprint"]
    assert credentials.password == "secret-ssh"
    assert kwargs["uid"] == 1000
    assert kwargs["gid"] == 1000
    local_test.assert_not_called()


def test_ports_veille_et_console_restent_des_champs_numeriques_larges():
    html = (webwizard.ASSETS / "wizard.html").read_text(encoding="utf-8")
    css = (webwizard.ASSETS / "wizard-parity.css").read_text(encoding="utf-8")

    assert 'class="port-field"><span data-i18n="veillePort"' in html
    assert 'class="port-field"><span data-i18n="consolePort"' in html
    assert '.choice-box input[type="checkbox"]' in css
    assert '.choice-box .port-field input[type="number"]' in css


def test_validation_failure_invalidates_previous_plan_and_hides_secret_input(server):
    srv, client = server
    form = fields(srv.state)
    plan = client.post("/api/validate", json=form).json()
    form["vpn"] = {"enabled": True, "provider": "secret-sensitive-test-value"}
    response = client.post("/api/validate", json=form)
    assert response.status_code == 400
    assert "secret-sensitive-test-value" not in response.text
    assert (
        client.post("/api/install", json={"plan_id": plan["plan_id"], "confirm": True}).status_code
        == 400
    )


def test_blocking_preflight_never_permits_real_install(tmp_path, monkeypatch):
    state = webwizard.WizardState(tmp_path)
    install = Mock()
    monkeypatch.setattr(orchestrator, "install", install)
    monkeypatch.setattr(orchestrator, "preflight", lambda *_: [Check("docker", False, "absent")])
    plan = state.validate(fields(state))
    assert plan["blocked"] and plan["plan_id"] is None
    with pytest.raises(ValueError):
        state.start({"plan_id": None, "confirm": True})
    install.assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_real_mode_calls_shared_engine_after_confirmation_and_redacts_progress(
    tmp_path, monkeypatch
):
    state = webwizard.WizardState(tmp_path)
    monkeypatch.setattr(orchestrator, "preflight", lambda *_: [])
    plan = state.validate(fields(state))
    calls = []

    def install(cfg, project_dir, *, on_progress, on_step, on_step_start):
        calls.append((cfg, project_dir))
        secret = next(inst.password for inst in cfg.services.values() if inst.password)
        on_progress(orchestrator.Progress("test", f"password={secret}"))
        result = StepResult("cablage", True, "termine")
        on_step(result)
        return [result]

    monkeypatch.setattr(orchestrator, "install", install)
    with pytest.raises(ValueError):
        state.start({"plan_id": plan["plan_id"], "confirm": False})
    state.start({"plan_id": plan["plan_id"], "confirm": True})
    state.worker.join(timeout=5)
    assert len(calls) == 1 and calls[0][0] is state.cfg
    assert state.status == "done"
    secret = next(inst.password for inst in state.cfg.services.values() if inst.password)
    assert secret not in json.dumps(state.progress())


def test_reinstall_preserves_credentials_ports_versions_and_vpn(tmp_path, monkeypatch):
    old = orchestrator.build_config(
        services=["sonarr", "qbittorrent"],
        data_root=str(tmp_path / "media"),
        config_root=str(tmp_path / "config"),
        # tmp_path appartient a la machine qui joue le test. Laisser le profil
        # par defaut `generic-linux` fabriquait une pile Windows declaree Linux,
        # que l'assistant refuse a juste titre : le test echouait sous Windows
        # pour une raison sans rapport avec ce qu'il verifie.
        platform=default_profile(),
    )
    old.services["sonarr"].host_port = 19989
    old.services["sonarr"].image = "lscr.io/linuxserver/sonarr:99.0.0"
    old.vpn = VpnConfig(enabled=True, provider="mullvad", wireguard_private_key="A" * 43 + "=")
    old.admin_password_hash = "preserved-hash"
    compose.write_artifacts(old, tmp_path)
    state = webwizard.WizardState(tmp_path)
    monkeypatch.setattr(orchestrator, "preflight", lambda *_: [])
    form = fields(state)
    assert form["vpn"]["wireguard_private_key"] == ""
    state.validate(form)
    assert state.cfg.services["sonarr"] == old.services["sonarr"]
    assert state.cfg.vpn == old.vpn
    assert state.cfg.admin_password_hash == old.admin_password_hash
    form["services"] = ["qbittorrent"]
    state.validate(form)
    assert "sonarr" not in state.cfg.services

    form["reprendre"] = False
    form["vpn"]["enabled"] = False
    state.validate(form)
    assert state.reprise is None
    assert state.cfg.admin_password_hash == ""
    assert state.project_dir == tmp_path


def test_starting_fresh_offers_all_old_configs_and_only_deletes_after_confirmation(
    tmp_path, monkeypatch
):
    old = orchestrator.build_config(
        services=["sonarr", "jellyfin"],
        data_root=str(tmp_path / "media"),
        config_root=str(tmp_path / "config"),
        platform=default_profile(),
    )
    for service in ("sonarr", "jellyfin"):
        directory = Path(old.config_path(service))
        directory.mkdir(parents=True)
        (directory / "state.db").write_text("old", encoding="utf-8")
    compose.write_artifacts(old, tmp_path)

    state = webwizard.WizardState(tmp_path)
    form = fields(state)
    form.update(services=["sonarr"], reprendre=False, reset_config=False)
    monkeypatch.setattr(orchestrator, "preflight", lambda *_: [])

    proposed = state.validate(form)
    assert set(proposed["reset_candidates"]) == {"sonarr", "jellyfin"}
    assert not proposed["reset_requested"]
    assert any("jellyfin" in location for location in proposed["reset_locations"])

    reset = Mock(return_value=[Path(old.config_path("sonarr")), Path(old.config_path("jellyfin"))])
    monkeypatch.setattr(orchestrator, "reset_installation_configs", reset)
    monkeypatch.setattr(orchestrator, "install", Mock(return_value=[]))
    form["reset_config"] = True
    plan = state.validate(form)
    reset.assert_not_called()
    state.start({"plan_id": plan["plan_id"], "confirm": True})
    state.worker.join(timeout=5)
    reset.assert_called_once_with(state.previous, tmp_path, plan["reset_candidates"])


def test_web_sabnzbd_route_is_explicit_and_direct_by_default(tmp_path, monkeypatch):
    state = webwizard.WizardState(tmp_path, demo=True)
    form = fields(state)
    form["services"] = ["sabnzbd"]

    plan = state.validate(form)

    assert plan["sabnzbd_route"] == "direct"
    assert state.cfg.vpn.protect_sabnzbd is False


def test_web_can_route_sabnzbd_through_vpn(tmp_path):
    state = webwizard.WizardState(tmp_path, demo=True)
    form = fields(state)
    form["services"] = ["sabnzbd"]
    form["vpn"].update(
        enabled=True,
        provider="mullvad",
        wireguard_private_key="A" * 43 + "=",
        protect_sabnzbd=True,
    )

    plan = state.validate(form)

    assert plan["sabnzbd_route"] == "vpn"
    assert state.cfg.vpn.protects("sabnzbd")


def test_demo_exposes_startup_backup_restore_paths_and_vpn_tools(server, monkeypatch):
    srv, client = server
    forbidden = Mock(side_effect=AssertionError("Operation reelle en demonstration"))
    monkeypatch.setattr(webwizard, "check_docker", forbidden)
    monkeypatch.setattr(webwizard.sauvegarde, "sauvegarder", forbidden)
    monkeypatch.setattr(webwizard.sauvegarde, "lire_manifeste", forbidden)
    monkeypatch.setattr(webwizard.sauvegarde, "restaurer", forbidden)
    monkeypatch.setattr(webwizard.vpnessai, "essayer", forbidden)

    startup = client.get("/api/startup").json()
    assert startup["ok"] and startup["checks"][0]["name"] == "Docker"
    profile = srv.state.bootstrap()["form"]
    paths = client.post(
        "/api/path-check",
        json={"platform": profile["platform"], "data_root": profile["data_root"]},
    ).json()
    assert paths["ok"] and paths["demo"] and "puid" in paths and "pgid" in paths

    assert client.post("/api/backup", json={"source": "", "destination": ""}).status_code == 400
    backup = client.post(
        "/api/backup",
        json={"source": "C:/PlugArr", "destination": "C:/backup.zip", "live": False},
    ).json()
    assert backup["ok"] and backup["demo"] and backup["stopped"]

    inspection = client.post(
        "/api/restore/inspect", json={"archive": "C:/backup.zip"}
    ).json()
    restore_payload = {
        "archive": "C:/backup.zip",
        "target": "C:/PlugArr/config",
        "inspection_id": inspection["inspection_id"],
        "confirm": False,
    }
    assert client.post("/api/restore", json=restore_payload).status_code == 400
    restore_payload["confirm"] = True
    restored = client.post("/api/restore", json=restore_payload).json()
    assert restored["ok"] and restored["demo"]

    vpn = client.post(
        "/api/vpn-test",
        json={
            "vpn": {
                "enabled": True,
                "provider": "protonvpn",
                "vpn_type": "openvpn",
                "openvpn_user": "demo",
                "openvpn_password": "demo-password",
            }
        },
    ).json()
    assert vpn["ok"] and not vpn["blocking"]
    forbidden.assert_not_called()


def test_provider_catalog_matches_tui_order_aliases_and_port_forward_filter(tmp_path):
    bootstrap = webwizard.WizardState(tmp_path, demo=True).bootstrap()
    providers = bootstrap["providers"]
    assert "pia" not in providers
    assert bootstrap["form"]["vpn"]["provider"] == "protonvpn"
    forwarding = [details["port_forward"] for details in providers.values()]
    assert forwarding == sorted(forwarding, reverse=True)
    pia = providers["private internet access"]
    assert pia["port_forward"] and len(pia["choices"]) < pia["total"]


def test_selection_reports_dependencies_and_planned_links(server):
    _, client = server
    result = client.post("/api/selection", json={"services": ["flood"]}).json()
    assert result["selected_count"] == 1
    assert result["effective_count"] == 2
    assert set(result["services"]) == {"flood", "qbittorrent"}
    assert result["planned_links"] >= 1


def test_reset_is_only_executed_after_explicit_install_confirmation(tmp_path, monkeypatch):
    config = tmp_path / "config"
    (config / "qbittorrent").mkdir(parents=True)
    (config / "qbittorrent" / "qBittorrent.conf").write_text("[Preferences]\n")
    state = webwizard.WizardState(tmp_path)
    form = fields(state)
    form.update(
        services=["qbittorrent"],
        config_root=str(config),
        data_root=str(tmp_path / "data"),
        reset_config=True,
    )
    monkeypatch.setattr(orchestrator, "preflight", lambda *_: [])
    reset = Mock(return_value=[config / "qbittorrent"])
    monkeypatch.setattr(orchestrator, "reset_configs", reset)
    monkeypatch.setattr(orchestrator, "install", Mock(return_value=[]))

    plan = state.validate(form)
    assert plan["reset_candidates"] == ["qbittorrent"]
    assert plan["reset_requested"]
    reset.assert_not_called()
    with pytest.raises(ValueError):
        state.start({"plan_id": plan["plan_id"], "confirm": False})
    reset.assert_not_called()
    state.start({"plan_id": plan["plan_id"], "confirm": True})
    state.worker.join(timeout=5)
    reset.assert_called_once_with(state.cfg, ["qbittorrent"])


def test_demo_post_install_indexers_report_and_access_page(server):
    srv, client = server
    form = fields(srv.state)
    form.update(services=["prowlarr", "sonarr"], host="plugarr.lan")
    plan = client.post("/api/validate", json=form).json()
    assert client.post(
        "/api/install", json={"plan_id": plan["plan_id"], "confirm": True}
    ).status_code == 200
    srv.state.worker.join(timeout=5)

    report = client.get("/api/report").json()
    assert {service["id"] for service in report["services"]} == {"prowlarr", "sonarr"}
    assert all("plugarr.lan" in service["url"] for service in report["services"])
    assert report["env_path"].endswith(".env")
    access = client.get("/api/access")
    assert access.headers["content-type"].startswith("text/html")
    assert "plugarr.lan" in access.text
    preview = client.post("/api/access-preview", json={}).json()["url"]
    assert preview.startswith("/access-preview/")
    assert srv.token not in preview
    rendered = client.get(preview, headers={"Authorization": ""})
    assert rendered.status_code == 200
    assert rendered.content == access.content
    assert "style-src 'unsafe-inline'" in rendered.headers["content-security-policy"]
    assert "'unsafe-inline'" not in rendered.headers["content-security-policy"].split("script-src ")[1].split(";")[0]
    assert "'sha256-" in rendered.headers["content-security-policy"]
    scripts = re.findall(rb"<script(?:\s[^>]*)?>(.*?)</script>", rendered.content, re.IGNORECASE | re.DOTALL)
    for script in scripts:
        digest = base64.b64encode(hashlib.sha256(script).digest()).decode()
        assert f"'sha256-{digest}'" in rendered.headers["content-security-policy"]
    assert client.get(preview, headers={"Authorization": ""}).status_code == 404
    assert client.get(preview, headers={"Host": "attacker.test"}).status_code == 403

    overview = client.get("/api/indexers").json()
    assert overview["available"] and overview["count"] == 2
    matches = client.post("/api/indexers/search", json={"query": "ex"}).json()["results"]
    assert len(matches) == 2
    private = next(item for item in matches if item["private"])
    assert {field["name"] for field in private["fields"]} == {
        "baseUrl",
        "username",
        "password",
    }
    public = next(item for item in matches if not item["private"])
    added = client.post(
        "/api/indexers/add", json={"key": public["key"], "values": {}}
    ).json()
    assert added["ok"] and public["name"] in added["configured"]


def test_web_assets_cover_every_tui_stage():
    html = (webwizard.ASSETS / "wizard.html").read_text(encoding="utf-8")
    javascript = (webwizard.ASSETS / "wizard.js").read_text(encoding="utf-8")
    for element_id in (
        "startup-card",
        "backup-tool",
        "restore-tool",
        "services",
        "path-check",
        "vpn-test",
        "sab-route",
        "quality-controls",
        "resume-box",
        "reset-box",
        "progress-state",
        "indexer-panel",
        "report-services",
        "access-page",
        "download-access",
        "finish",
    ):
        assert f'id="{element_id}"' in html
    for route in (
        "/api/startup",
        "/api/backup",
        "/api/restore/inspect",
        "/api/restore",
        "/api/path-check",
        "/api/vpn-test",
        "/api/indexers/search",
        "/api/indexers/add",
        "/api/report",
        "/api/access",
        "/api/access-preview",
        "/api/close",
    ):
        assert route in javascript

    parity = (webwizard.ASSETS / "wizard-parity.css").read_text(encoding="utf-8")
    assert ".place-choice[hidden]" in parity
    assert "display: none !important" in parity
    assert "downloadAccessPage" in javascript


def test_external_config_change_or_expired_checks_prevent_install(tmp_path, monkeypatch):
    state = webwizard.WizardState(tmp_path)
    monkeypatch.setattr(orchestrator, "preflight", lambda *_: [])
    plan = state.validate(fields(state))
    state.validated_at -= 301
    with pytest.raises(ValueError, match="expire"):
        state.start({"plan_id": plan["plan_id"], "confirm": True})
    plan = state.validate(fields(state))
    (tmp_path / "stack.yml").write_text("version: 999\n")
    with pytest.raises(ValueError, match="change"):
        state.start({"plan_id": plan["plan_id"], "confirm": True})


@pytest.mark.parametrize(
    "changes",
    [
        {"services": ["does-not-exist"]},
        {"config_root": "relative/path"},
        {"project_name": "invalid;command"},
        {"timezone": "invented/zone"},
        {"vpn": {"enabled": True, "provider": "mullvad", "wireguard_private_key": "invalid"}},
    ],
)
def test_invalid_configuration_cannot_reach_engine(tmp_path, changes):
    state = webwizard.WizardState(tmp_path, demo=True)
    form = fields(state)
    form.update(changes)
    with pytest.raises((ValueError, KeyError)):
        state.validate(form)
    assert state.plan_id is None


def test_malformed_or_future_configuration_is_never_treated_as_fresh_install(tmp_path):
    (tmp_path / "stack.yml").write_text("version: 999\n")
    with pytest.raises(ValueError):
        webwizard.WizardState(tmp_path)
    assert webwizard.WizardState(tmp_path, demo=True).previous is None


def test_explicit_interface_overrides_preference_and_subcommands_stay_scriptable(
    tmp_path, monkeypatch
):
    from plugarr.tui import app as tui

    monkeypatch.setattr(interface, "preference_path", lambda: tmp_path / "preferences.json")
    interface.save_preference(interface.Interface.WEB)
    tui_call = Mock(return_value=0)
    web_call = Mock(return_value=0)
    monkeypatch.setattr(tui, "run_wizard", tui_call)
    monkeypatch.setattr(webwizard, "run_web", web_call)
    runner = CliRunner()
    assert runner.invoke(app, ["--interface", "tui"]).exit_code == 0
    tui_call.assert_called_once()
    assert runner.invoke(app, ["--interface", "web"]).exit_code == 0
    web_call.assert_called_once()
    web_call.reset_mock()
    assert runner.invoke(app, ["list"]).exit_code == 0
    web_call.assert_not_called()
    assert runner.invoke(app, ["web", "--demo", "--no-open"]).exit_code == 0
    assert web_call.call_args.kwargs["demo"] is True
    assert web_call.call_args.kwargs["open_page"] is False
    web_call.reset_mock()
    assert runner.invoke(app, ["web", "--no-open"]).exit_code == 0
    assert web_call.call_args.kwargs["demo"] is False
    assert web_call.call_args.kwargs["open_page"] is False


def test_windows_real_install_launcher_never_enables_demo():
    root = Path(__file__).parents[1]
    launcher = (root / "TESTER-INSTALLATION-REELLE.cmd").read_text(encoding="utf-8")
    starter = (root / "scripts" / "start-web-local.cmd").read_text(encoding="utf-8")
    real_block = starter.split('if "%~1"=="real" (', 1)[1].split(
        ') else if "%~1"=="tui" (', 1
    )[0]

    assert 'start-web-local.cmd" real' in launcher
    assert "-m plugarr --lang fr web --project-dir" in real_block
    assert "--demo" not in real_block
    assert "installation-test-reelle" in real_block


def test_headless_auto_does_not_launch_an_unusable_tui(tmp_path, monkeypatch):
    monkeypatch.setattr(interface, "preference_path", lambda: tmp_path / "absent.json")
    monkeypatch.setattr(interface, "desktop_available", lambda: False)
    monkeypatch.setattr(interface.sys.stdin, "isatty", lambda: False)
    assert interface.launch() == 2


def test_preferences_are_local_and_invalid_values_fall_back_to_auto(tmp_path, monkeypatch):
    path = tmp_path / "nested" / "interface.json"
    monkeypatch.setattr(interface, "preference_path", lambda: path)
    assert interface.read_preference() == interface.Interface.AUTO
    interface.save_preference(interface.Interface.TUI)
    assert interface.read_preference() == interface.Interface.TUI
    path.write_text("invalid json")
    assert interface.read_preference() == interface.Interface.AUTO


def test_normalized_overlapping_folders_are_rejected_before_preflight(tmp_path):
    state = webwizard.WizardState(tmp_path, demo=True)
    form = fields(state)
    form.update(platform="windows", data_root="C:/media", config_root="C:/other/../media/config")
    with pytest.raises(ValueError, match="imbrication"):
        state.validate(form)


def test_windows_form_is_accepted_with_a_valid_timezone(tmp_path):
    state = webwizard.WizardState(tmp_path, demo=True)
    form = fields(state)
    form.update(
        platform="windows",
        data_root="C:/PlugArr-Test/data",
        config_root="C:/PlugArr-Test/config",
        timezone="Europe/Paris",
    )
    assert state.validate(form)["plan_id"]


def test_multiline_vpn_values_are_rejected_without_echoing_them(tmp_path):
    state = webwizard.WizardState(tmp_path, demo=True)
    form = fields(state)
    form["vpn"] = {
        "enabled": True,
        "provider": "mullvad",
        "vpn_type": "openvpn",
        "openvpn_user": "user",
        "openvpn_password": "secret\nsecond-line",
    }
    with pytest.raises(ValueError, match="retour a la ligne") as error:
        state.validate(form)
    assert "secret" not in str(error.value)


def test_graph_preview_endpoint_is_authenticated_and_accepts_incomplete_forms(server):
    srv, client = server
    assert (
        client.post("/api/graph", json={"services": []}, headers={"Authorization": ""}).status_code
        == 401
    )
    result = client.post("/api/graph", json={"services": ["flood"], "vpn_enabled": True})
    assert result.status_code == 200
    data = result.json()
    assert {n["id"] for n in data["graph"]["noeuds"]} == {"flood", "qbittorrent", "gluetun"}
    assert data["status"] == "idle" and data["graph_results"] == {}
    assert srv.state.plan_id is None
    assert client.get("/graph.js").status_code == 200
    assert client.get("/graph.css").status_code == 200


def test_event_stream_pushes_updates_and_reconnects_with_full_state(server):
    srv, client = server
    state = srv.state
    state.graph = state.graph_preview({"services": ["sonarr"]})["graph"]
    state.set_status("running")

    def next_data(lines):
        for line in lines:
            if line.startswith("data: "):
                return json.loads(line[6:])
        pytest.fail("SSE closed without an update")

    with client.stream("GET", "/api/events") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        lines = response.iter_lines()
        first = next_data(lines)
        assert first["active_step"] is None
        state.event("start", "active", step_id="sonarr/acces-web", started=True)
        current = next_data(lines)
        assert current["active_step"] == "sonarr/acces-web"
        state.event("result", "failed", False, step_id="sonarr/acces-web")
        failed = next_data(lines)
        assert failed["graph_results"]["sonarr/acces-web"]["ok"] is False
        state.set_status("partial")
        assert next_data(lines)["status"] == "partial"
    with client.stream("GET", "/api/events") as response:
        recovered = next_data(response.iter_lines())
        assert recovered["graph_results"]["sonarr/acces-web"]["ok"] is False
        assert recovered["status"] == "partial"


def test_demo_admin_actions_remain_isolated(server, monkeypatch):
    import subprocess

    from plugarr import admin, dashboard

    srv, client = server
    forbidden = Mock(side_effect=AssertionError("Operation reelle en demonstration"))
    monkeypatch.setattr(admin, "build_server", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(dashboard, "primary_lan_ip", forbidden)
    assert client.post("/api/admin", json={}).status_code == 400
    form = fields(srv.state)
    form["services"] = ["flood"]
    plan = client.post("/api/validate", json=form).json()
    client.post("/api/install", json={"plan_id": plan["plan_id"], "confirm": True})
    srv.state.worker.join(timeout=5)
    original = srv.state.cfg.model_dump()
    result = client.post("/api/admin", json={}).json()
    assert client.post("/api/admin", json={}).json() == result
    demo = srv.state.admin_server
    with httpx.Client(base_url=demo.origin, trust_env=False) as console:
        assert console.get('/api/status').status_code == 401
        page = console.get(result['url'])
        assert page.status_code == 200
        assert 'DÉMO' in page.text and '192.0.2.10' in page.text
        assert 'DEMO-password' in page.text
        assert 'HttpOnly' in page.headers['set-cookie']
        assert console.get('/').status_code == 200
        states = console.get('/api/status').json()['services']
        assert {s['id'] for s in states} == {'flood', 'qbittorrent'}
        assert all(s['up'] for s in states)
        graph = console.get('/api/connections').json()
        assert {n['id'] for n in graph['graph']['noeuds']} == {'flood', 'qbittorrent'}
        assert console.post('/api/action', json={'service': 'flood', 'action': 'stop'},
                            headers={'Origin': 'https://evil.test'}).status_code == 403
        assert console.get('/api/status', headers={'Host': 'evil.test'}).status_code == 403
        for action, expected in [('stop', False), ('start', True), ('restart', True)]:
            assert console.post('/api/action', json={'service': 'flood', 'action': action}).json()['ok']
            states = console.get('/api/status').json()['services']
            assert next(s for s in states if s['id'] == 'flood')['up'] is expected
        assert console.post('/api/update', json={'service': 'flood'}).json()['ok']
        updates = console.get('/api/updates').json()['services']
        assert not next(s for s in updates if s['id'] == 'flood')['available']
        rotated = console.post('/api/rotate', json={'service': 'flood', 'what': 'password'}).json()
        assert rotated['secret'] in console.get('/').text
        assert console.post('/api/backup').json()['ok']
        assert console.post('/api/maintenance', json={'schedule': {'enabled': True}}).json()['ok']
        assert console.get('/api/maintenance').json()['schedule']['enabled']
        assert console.post('/api/self-update', json={}).json()['ok']
        assert not console.get('/api/self-update').json()['available']
        assert console.post('/api/add', json={'service': 'sonarr'}).json()['ok']
        assert 'sonarr' in {s['id'] for s in console.get('/api/status').json()['services']}
        graph = console.get('/api/connections').json()
        assert 'sonarr' in {n['id'] for n in graph['graph']['noeuds']}
        edge_id = 'sonarr/downloadclient/qbittorrent'
        assert console.post('/api/connections/test', json={'id': edge_id}).json()['ok']
        tested = console.get('/api/connections').json()
        assert next(e for e in tested['connections'] if e['id'] == edge_id)['checked_at']
        assert tested['graph']['id'] == graph['graph']['id']
        assert console.post('/api/action', json={'service': 'unknown', 'action': 'stop'}).status_code == 400
        assert console.post('/api/action', json={'service': 'flood', 'action': 'shell'}).status_code == 400
        assert console.post('/api/action', json=[]).status_code == 400
        assert console.post('/api/unknown', json={}).status_code == 404
    assert srv.state.cfg.model_dump() == original
    assert list(srv.state.project_dir.iterdir()) == []
    forbidden.assert_not_called()


def test_client_opens_demo_console_once_after_completion():
    import shutil
    import subprocess
    from pathlib import Path

    if not shutil.which('node'):
        pytest.skip('Node required for client completion test')
    subprocess.run(['node', 'tests/js/wizard_completion.cjs'],
                   cwd=Path(__file__).resolve().parent.parent,
                   check=True, capture_output=True, text=True)


def test_browser_reads_the_wizard_markup_as_the_wizard_expects():
    """Deux defauts vus dans un navigateur, invisibles cote Python.

    L'attribut `pattern` du nom de pile etait rejete par Chrome (tiret non
    echappe sous le drapeau `v`) : la validation locale ne s'appliquait plus, et
    « Ma Pile ! » passait jusqu'au serveur. Et les cles de
    `data-i18n-placeholder` n'existaient que dans le dictionnaire anglais : en
    francais, les deux champs de localisation VPN affichaient « locationSearch »
    et « locationManual ».
    """
    import shutil
    import subprocess
    from pathlib import Path

    if not shutil.which('node'):
        pytest.skip('Node required for wizard markup test')
    subprocess.run(['node', 'tests/js/wizard_html.cjs'],
                   cwd=Path(__file__).resolve().parent.parent,
                   check=True, capture_output=True, text=True)


def test_demo_exposes_and_accepts_complete_official_quality_catalog(server, monkeypatch):
    srv, client = server
    forbidden = Mock(side_effect=AssertionError('La démo doit garder son catalogue hors ligne'))
    monkeypatch.setattr(webwizard.recyclarr, 'available_templates', forbidden)
    monkeypatch.setattr(webwizard.recyclarr, 'fetch_manifest', forbidden)
    response = client.get('/api/templates')
    assert response.status_code == 200
    catalog = response.json()
    assert catalog['bundled'] and not catalog['problem']
    assert len(catalog['names']['sonarr']) == 22
    assert len(catalog['names']['radarr']) == 35
    form = fields(srv.state)
    form['services'] = ['recyclarr', 'sonarr', 'radarr']
    form['recyclarr_templates'] = {
        'sonarr': 'french-vostfr-bluray-web-2160p',
        'radarr': 'sqp-3-audio',
    }
    result = client.post('/api/validate', json=form)
    assert result.status_code == 200, result.json()
    assert result.json()['recyclarr_templates'] == form['recyclarr_templates']
    form['recyclarr_templates']['radarr'] = 'template-invente'
    assert client.post('/api/validate', json=form).status_code == 400
    forbidden.assert_not_called()


def test_l_assistant_web_propose_chaque_profil_de_plateforme():
    """Le `<select>` est ecrit a la main dans le HTML, contrairement au TUI qui
    parcourt l'enumeration. Un profil ajoute cote Python restait donc invisible
    dans le navigateur, sans que rien ne le signale."""
    from plugarr.models import PlatformProfile

    html = (webwizard.ASSETS / "wizard.html").read_text(encoding="utf-8")
    debut = html.index('<select id="platform"')
    bloc = html[debut : html.index("</select>", debut)]

    for profil in PlatformProfile:
        assert f'value="{profil.value}"' in bloc, profil.value


def test_l_assistant_web_porte_la_note_du_profil():
    """Un profil experimental doit le dire dans le navigateur aussi, pas
    seulement dans le terminal."""
    html = (webwizard.ASSETS / "wizard.html").read_text(encoding="utf-8")
    javascript = (webwizard.ASSETS / "wizard.js").read_text(encoding="utf-8")

    assert 'id="platform-note"' in html
    assert "platform-note" in javascript
    assert "profile.note" in javascript


def test_installation_distante_n_interroge_pas_prowlarr_depuis_ce_poste(server, monkeypatch):
    """VPS reel du 25/09/2026 : Prowlarr a l'adresse privee, injoignable d'ici."""
    srv, client = server
    form = fields(srv.state)
    form.update(services=["prowlarr", "sonarr"], host="10.0.0.30")
    plan = client.post("/api/validate", json=form).json()
    assert client.post(
        "/api/install", json={"plan_id": plan["plan_id"], "confirm": True}
    ).status_code == 200
    srv.state.worker.join(timeout=5)
    srv.state.install_target = "ssh"
    srv.state.demo = False
    monkeypatch.setattr(
        srv.state,
        "_ensure_indexers",
        Mock(side_effect=AssertionError("Prowlarr interroge depuis le poste")),
    )

    overview = client.get("/api/indexers").json()

    assert overview["available"] is False



def test_ssh_reprend_la_pile_trouvee_sur_le_serveur(server, monkeypatch):
    """Second passage reel du 25/09/2026 sur un VPS : sans reprise, l'assistant
    regenerait les mots de passe et perdait la cle VPN."""
    import yaml

    srv, client = server
    srv.state.demo = False
    ancienne = orchestrator.build_config(
        services=["sonarr", "qbittorrent"],
        config_root="/home/ubuntu/plugarr/config",
        data_root="/home/ubuntu/data",
        host="10.0.0.30",
    )
    ancienne.services["sonarr"].password = "mot-de-passe-du-serveur"
    ancienne.vpn = VpnConfig(
        enabled=True,
        provider="protonvpn",
        vpn_type="wireguard",
        wireguard_private_key="a2tra2tra2tra2tra2tra2tra2tra2tra2tra2tra2s=",
        server_countries="France",
    )
    monkeypatch.setattr(
        remote_install,
        "probe",
        lambda *_args, **_kwargs: remote_install.RemoteProbe(
            fingerprint="SHA256:vps",
            system="Linux",
            machine="aarch64",
            uid=1001,
            gid=1001,
            home="/home/ubuntu",
            docker_version="29.1.3",
        ),
    )
    monkeypatch.setattr(
        remote_install,
        "inspect_project",
        lambda *_args, **_kwargs: remote_install.RemoteProjectState(
            exists=True,
            managed=True,
            stack_sha="x",
            stack_yaml=compose.render_stack(ancienne),
        ),
    )
    probe_result = client.post(
        "/api/remote-install/probe",
        json={"host": "203.0.113.10", "port": 22, "username": "ubuntu", "private_key": "cle"},
    ).json()

    assert probe_result["existing"] is True
    assert probe_result["existing_form"]["vpn"]["enabled"] is True
    assert "a2tra2tra2tra2tra2tra2tra2tra2tra2tra2tra2s=" not in json.dumps(probe_result)
    assert "mot-de-passe-du-serveur" not in json.dumps(probe_result)

    deployments = []

    def fake_deploy(target, credentials, deployment, *, connect, on_event):
        deployments.append(deployment)
        on_event({"kind": "done", "status": "done"})
        return remote_install.RemoteDeployResult(status="done", events=())

    monkeypatch.setattr(remote_install, "deploy", fake_deploy)
    form = fields(srv.state)
    form.update(probe_result["existing_form"])
    form.update(
        {
            "install_target": "ssh",
            "remote_connection_id": probe_result["connection_id"],
            "remote_fingerprint": probe_result["fingerprint"],
            "remote_project_dir": probe_result["project_dir"],
            "platform": "generic-linux",
            "config_root": probe_result["config_root"],
            "data_root": probe_result["data_root"],
            "host": "10.0.0.30",
            "reprendre": True,
            "remote_replace": True,
        }
    )
    plan = client.post("/api/validate", json=form)
    assert plan.status_code == 200, plan.text
    assert client.post(
        "/api/install", json={"plan_id": plan.json()["plan_id"], "confirm": True}
    ).status_code == 200
    srv.state.worker.join(timeout=5)

    pile = yaml.safe_load(deployments[0].stack_yaml)
    assert pile["services"]["sonarr"]["password"] == "mot-de-passe-du-serveur"
    assert pile["vpn"]["enabled"] is True
    assert pile["vpn"]["wireguard_private_key"] == "a2tra2tra2tra2tra2tra2tra2tra2tra2tra2tra2s="


def _installation_terminee(srv, client):
    form = fields(srv.state)
    form.update(services=["prowlarr", "sonarr"], host="plugarr.lan")
    plan = client.post("/api/validate", json=form).json()
    assert client.post(
        "/api/install", json={"plan_id": plan["plan_id"], "confirm": True}
    ).status_code == 200
    srv.state.worker.join(timeout=5)


def test_le_rapport_liste_les_mises_a_jour_sans_rien_changer(server, monkeypatch):
    """Demande du 26/09/2026 : versions testees installees, les plus recentes signalees."""
    srv, client = server
    _installation_terminee(srv, client)
    assert client.get("/api/updates").json() == {"demo": True, "updates": [], "unchecked": []}

    srv.state.demo = False
    vues = []

    def newer(image, *, timeout):
        vues.append(image)
        if "sonarr" in image:
            return ["4.0.21", "4.0.22"], None
        return [], "registre injoignable"

    monkeypatch.setattr(webwizard.updates, "newer_tags", newer)

    donnees = client.get("/api/updates").json()

    assert donnees["updates"] == [
        {"id": "sonarr", "name": "Sonarr", "current": "4.0.20", "latest": "4.0.22"}
    ]
    assert donnees["unchecked"] == ["Prowlarr"]
    assert "4.0.22" not in (srv.state.cfg.services["sonarr"].image or "")



def _pile_distante_ancienne(monkeypatch):
    ancienne = orchestrator.build_config(
        services=["sonarr", "jellyfin"],
        config_root="/home/ubuntu/plugarr/config",
        data_root="/home/ubuntu/data",
        host="10.0.0.30",
    )
    ancienne.services["sonarr"].image = "lscr.io/linuxserver/sonarr:4.0.19"
    ancienne.services["jellyfin"].image = "lscr.io/linuxserver/jellyfin:10.11.11"
    ancienne.services["sonarr"].password = "mot-de-passe-du-serveur"
    monkeypatch.setattr(
        remote_install,
        "probe",
        lambda *_a, **_k: remote_install.RemoteProbe(
            fingerprint="SHA256:vps", system="Linux", machine="aarch64",
            uid=1001, gid=1001, home="/home/ubuntu", docker_version="29.1.3",
        ),
    )
    monkeypatch.setattr(
        remote_install,
        "inspect_project",
        lambda *_a, **_k: remote_install.RemoteProjectState(
            exists=True, managed=True, stack_sha="x", stack_yaml=compose.render_stack(ancienne)
        ),
    )


def _deployer(srv, client, monkeypatch, probe_result, **choix):
    import yaml

    deployments = []

    def fake_deploy(target, credentials, deployment, *, connect, on_event):
        deployments.append(deployment)
        on_event({"kind": "done", "status": "done"})
        return remote_install.RemoteDeployResult(status="done", events=())

    monkeypatch.setattr(remote_install, "deploy", fake_deploy)
    form = fields(srv.state)
    form.update(probe_result["existing_form"])
    form.update({
        "install_target": "ssh",
        "remote_connection_id": probe_result["connection_id"],
        "remote_fingerprint": probe_result["fingerprint"],
        "remote_project_dir": probe_result["project_dir"],
        "platform": "generic-linux",
        "config_root": probe_result["config_root"],
        "data_root": probe_result["data_root"],
        "host": "10.0.0.30",
        "remote_replace": True,
        **choix,
    })
    plan = client.post("/api/validate", json=form)
    assert plan.status_code == 200, plan.text
    assert client.post(
        "/api/install", json={"plan_id": plan.json()["plan_id"], "confirm": True}
    ).status_code == 200
    srv.state.worker.join(timeout=5)
    return yaml.safe_load(deployments[0].stack_yaml)


def test_le_test_ssh_annonce_les_versions_testees_plus_recentes(server, monkeypatch):
    """Demande du 26/09/2026 : choisir reprise ou zero juste apres la connexion,
    et voir ce que « passer aux versions testees » changerait."""
    srv, client = server
    srv.state.demo = False
    _pile_distante_ancienne(monkeypatch)

    resultat = client.post(
        "/api/remote-install/probe",
        json={"host": "203.0.113.10", "port": 22, "username": "ubuntu", "private_key": "cle"},
    ).json()

    changements = {c["id"]: c for c in resultat["version_changes"]}
    assert changements["jellyfin"]["installed"] == "10.11.11"
    assert changements["jellyfin"]["major"] is True
    assert changements["sonarr"]["installed"] == "4.0.19"
    assert changements["sonarr"]["major"] is False
    assert resultat["fresh_form"]["vpn"]["enabled"] is False
    assert "mot-de-passe-du-serveur" not in json.dumps(resultat)


@pytest.mark.parametrize("monter", [False, True])
def test_la_reprise_ne_change_de_version_que_sur_demande(server, monkeypatch, monter):
    srv, client = server
    srv.state.demo = False
    _pile_distante_ancienne(monkeypatch)
    resultat = client.post(
        "/api/remote-install/probe",
        json={"host": "203.0.113.10", "port": 22, "username": "ubuntu", "private_key": "cle"},
    ).json()

    pile = _deployer(srv, client, monkeypatch, resultat, reprendre=True, upgrade_images=monter)

    assert pile["services"]["sonarr"]["password"] == "mot-de-passe-du-serveur"
    attendu = (
        {"sonarr": catalog.get("sonarr").image, "jellyfin": catalog.get("jellyfin").image}
        if monter
        else {"sonarr": "lscr.io/linuxserver/sonarr:4.0.19", "jellyfin": "lscr.io/linuxserver/jellyfin:10.11.11"}
    )
    assert {sid: pile["services"][sid]["image"] for sid in attendu} == attendu
