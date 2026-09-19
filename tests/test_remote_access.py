"""Remote configuration, non-publication on failure and private mobile exports."""
import json
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from plugarr import dashboard, remote_access, webwizard
from plugarr.remote_models import RemoteAccessConfig


def config(tmp_path, mode="https"):
    state = webwizard.WizardState(tmp_path, demo=True)
    form = state.bootstrap()["form"]
    form.update(services=["sonarr", "qbittorrent"], host="192.0.2.50", reprendre=False,
                remote_access={"mode": mode, "domain": "maison.example" if mode == "https" else "",
                               "services": ["sonarr", "qbittorrent"] if mode == "https" else []})
    return state, state.build_config(form)


@pytest.mark.parametrize("domain", ["https://abc.test", "abc.test/path", "a.test\n}", "-bad.test", "a..test", "127.0.0.1", "a.test:443"])
def test_invalid_domain_cannot_reach_caddy(domain):
    with pytest.raises(ValidationError):
        RemoteAccessConfig(mode="https", domain=domain, services=["sonarr"])


def test_only_supported_services_can_be_published():
    with pytest.raises(ValidationError):
        RemoteAccessConfig(mode="https", domain="maison.example", services=["flood"])


def test_gateway_uses_gluetun_but_not_vpn_for_caddy(tmp_path):
    _, cfg = config(tmp_path)
    cfg.vpn.enabled = True
    text = remote_access.caddyfile(cfg)
    assert "http://gluetun:8080" in text
    assert "http://sonarr:8989" in text
    compose = remote_access.gateway_compose(cfg)
    assert "network_mode" not in compose["services"]["gateway"]
    assert set(compose["services"]) == {"gateway"}
    assert "acces-plugarr" not in json.dumps(compose)
    cfg.services["sonarr"].adopted = True
    with pytest.raises(ValueError):
        remote_access.caddyfile(cfg)


def test_demo_does_not_call_docker_dns_or_write(tmp_path, monkeypatch):
    _, cfg = config(tmp_path, "tailscale")
    monkeypatch.setattr(remote_access.runner, "_run", Mock(side_effect=AssertionError("Docker")))
    monkeypatch.setattr(remote_access.socket, "getaddrinfo", Mock(side_effect=AssertionError("DNS")))
    result = remote_access.activate(cfg, tmp_path, demo=True)
    assert result["status"] == "simulated"
    assert result["urls"]["qbittorrent"].endswith(":8080")
    assert not (tmp_path / ".plugarr-remote").exists()


def test_tailnet_login_is_not_reported_as_connection(tmp_path):
    _, cfg = config(tmp_path, "tailscale")
    result = remote_access._tailscale_result(cfg, {"BackendState": "NeedsLogin", "AuthURL": "https://login.tailscale.com/a/example"})
    assert result["status"] == "association"
    assert not result["urls"]
    assert result["auth_url"].startswith("https://login.tailscale.com/")
    invalid = remote_access._tailscale_result(cfg, {"BackendState": "Running", "TailscaleIPs": ["192.168.1.1"], "AuthURL": "https://evil.example/"})
    assert not invalid["urls"] and not invalid["auth_url"]
    good = remote_access._tailscale_result(cfg, {"BackendState": "Running", "TailscaleIPs": ["100.100.100.1"]})
    assert good["status"] == "connected"


def test_auth_failure_prevents_starting_gateway(tmp_path, monkeypatch):
    _, cfg = config(tmp_path)
    monkeypatch.setattr(remote_access.socket, "getaddrinfo", lambda *a: [(1,)])
    monkeypatch.setattr(remote_access, "_protect_applications", Mock(side_effect=ValueError("auth")))
    start = Mock()
    monkeypatch.setattr(remote_access, "_command", start)
    with pytest.raises(ValueError, match="auth"):
        remote_access.activate(cfg, tmp_path)
    start.assert_not_called()
    assert not (tmp_path / ".plugarr-remote" / "compose.yml").exists()


def test_foreign_compose_is_never_overwritten(tmp_path):
    folder = tmp_path / ".plugarr-remote"
    folder.mkdir()
    path = folder / "compose.yml"
    path.write_text("services: {}", encoding="utf-8")
    with pytest.raises(ValueError):
        remote_access._check_owned(folder)
    assert path.read_text(encoding="utf-8") == "services: {}"


def test_mobile_export_escapes_secrets_and_never_embeds_auth_url(tmp_path):
    _, cfg = config(tmp_path)
    cfg.services["qbittorrent"].password = '</script><script>alert("secret")</script>'
    remote = {"mode": "https", "urls": remote_access.external_urls(cfg), "auth_url": "PRIVATE-ASSOCIATION"}
    page = dashboard.render(cfg, remote_report=remote)
    assert 'id="mobile-client"' in page
    assert 'https://qb.maison.example' in page
    assert 'PRIVATE-ASSOCIATION' not in page
    assert '<script>alert("secret")' not in page
    assert '\\u003c/script\\u003e' in page


def test_web_remote_requires_completion_confirmation_and_preserves_local_result(tmp_path, monkeypatch):
    state, cfg = config(tmp_path)
    state.cfg = cfg
    with pytest.raises(ValueError):
        state.remote_action({"action": "activate", "confirm": True})
    state.status = "done"
    with pytest.raises(ValueError):
        state.remote_action({"action": "activate"})
    monkeypatch.setattr(remote_access, "activate", Mock(side_effect=ValueError("DNS non prêt")))
    state.remote_action({"action": "activate", "confirm": True})
    state.remote_worker.join(timeout=5)
    assert state.status == "done"
    assert state.remote_result["status"] == "error"
    assert state.report()["services"]


def test_choice_survives_serialization(tmp_path):
    from plugarr.models import StackConfig
    _, cfg = config(tmp_path)
    restored = StackConfig.model_validate_json(cfg.model_dump_json())
    assert restored.remote_access == cfg.remote_access


def test_public_qb_preferences_are_backed_up_hardened_and_verified(tmp_path, httpx_mock):
    from urllib.parse import parse_qs
    import httpx

    _, cfg = config(tmp_path)
    cfg.remote_access.services = ["qbittorrent"]
    old = {"web_ui_csrf_protection_enabled": False,
           "web_ui_host_header_validation_enabled": False,
           "bypass_local_auth": True, "bypass_auth_subnet_whitelist_enabled": True,
           "web_ui_domain_list": "*;existing.example"}
    saved = dict(old)
    base = cfg.services["qbittorrent"].url(cfg.host)
    httpx_mock.add_response(method="POST", url=base + "/api/v2/auth/login", text="Ok.")
    httpx_mock.add_response(method="GET", url=base + "/api/v2/app/preferences", json=old)

    def update(request):
        saved.update(json.loads(parse_qs(request.content.decode())["json"][0]))
        return httpx.Response(200)

    httpx_mock.add_callback(update, method="POST", url=base + "/api/v2/app/setPreferences")
    httpx_mock.add_callback(lambda request: httpx.Response(200, json=saved),
                            method="GET", url=base + "/api/v2/app/preferences")
    remote_access._protect_applications(cfg, tmp_path)
    assert saved["web_ui_csrf_protection_enabled"] is True
    assert saved["web_ui_host_header_validation_enabled"] is True
    assert saved["bypass_local_auth"] is False
    assert saved["bypass_auth_subnet_whitelist_enabled"] is False
    assert "*" not in saved["web_ui_domain_list"]
    assert "existing.example" in saved["web_ui_domain_list"]
    assert "qb.maison.example" in saved["web_ui_domain_list"]
    assert json.loads((tmp_path / "qbittorrent-web-before.json").read_text()) == old


@pytest.mark.parametrize("required,method", [("disabledForLocalAddresses", "forms"), ("enabled", "none"), ("enabled", "external")])
def test_arr_auth_bypasses_block_publication(tmp_path, httpx_mock, required, method):
    _, cfg = config(tmp_path)
    cfg.remote_access.services = ["sonarr"]
    httpx_mock.add_response(url=cfg.services["sonarr"].url(cfg.host) + "/api/v3/config/host",
                            json={"authenticationRequired": required, "authenticationMethod": method})
    with pytest.raises(ValueError, match="authentification"):
        remote_access._protect_applications(cfg, tmp_path)


def test_qbremote_export_is_readable_by_an_independent_aes_zip_reader():
    """Le fichier de qbRemote 1.8.0 est un ZIP WinZip AES-256. Le test JS le
    relit avec un dechiffreur ecrit a part, sur des donnees fictives."""
    import shutil
    import subprocess
    from pathlib import Path

    if not shutil.which("node"):
        pytest.skip("Node requis pour l'export qbRemote")
    subprocess.run(["node", "tests/js/qbremote_export.cjs"],
                   cwd=Path(__file__).resolve().parent.parent,
                   check=True, capture_output=True, text=True)


def test_merge_with_user_backups_keeps_everything_else():
    """Fusion avec la sauvegarde de l'utilisateur (nzb360 et qbRemote) : rien
    d'autre que les services PlugArr ne change. Flux Java de reference ecrit par
    un vrai ObjectOutputStream, donnees fictives."""
    import shutil
    import subprocess
    from pathlib import Path

    if not shutil.which("node"):
        pytest.skip("Node requis pour la fusion des sauvegardes")
    subprocess.run(["node", "tests/js/fusion_export.cjs"],
                   cwd=Path(__file__).resolve().parent.parent,
                   check=True, capture_output=True, text=True)
