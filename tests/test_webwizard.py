"""Contrats sensibles de l'assistant web, avec serveur HTTP local et moteur simule."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from typer.testing import CliRunner

from plugarr import compose, interface, orchestrator, webwizard
from plugarr.cli import app
from plugarr.layout import default_profile
from plugarr.models import VpnConfig
from plugarr.runner import Check
from plugarr.wiring import StepResult


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
