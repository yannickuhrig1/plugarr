"""Contrats sensibles de l'assistant web, avec serveur HTTP local et moteur simule."""

from __future__ import annotations

import json
import threading
from unittest.mock import Mock

import httpx
import pytest
from typer.testing import CliRunner

from plugarr import compose, interface, orchestrator, webwizard
from plugarr.cli import app
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
    with pytest.raises(ValueError, match="suppression"):
        state.validate(form)


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
