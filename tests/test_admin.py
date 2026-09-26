"""Tests du serveur d'administration.

Le serveur est reellement demarre, sur un port ephemere de la boucle locale, mais
Docker n'est jamais appele : `Compose` est remplace par un double. Une page
capable d'arreter des conteneurs merite d'etre testee sur ses refus autant que
sur ses succes.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

from plugarr import admin, orchestrator
from plugarr.models import PlatformProfile

TOKEN = "jeton-de-test"


class FakeCompose:
    """Double de Compose : enregistre les appels, ne lance jamais Docker."""

    def __init__(self, running=("sonarr",)):
        self.running = set(running)
        self.calls: list[tuple[str, str]] = []

    def ps_json(self):
        return [
            {
                "Service": name,
                "State": "running" if name in self.running else "exited",
                "Status": "Up 3 minutes" if name in self.running else "Exited (0)",
                "Health": "",
            }
            for name in ("sonarr", "prowlarr")
        ]

    def control(self, action, service):
        self.calls.append((action, service))
        return True, f"{action} {service}"


@pytest.fixture
def cfg():
    return orchestrator.build_config(
        services=["prowlarr", "sonarr", "qbittorrent"],
        data_root="/srv/data",
        config_root="/opt/c",
        platform=PlatformProfile.GENERIC_LINUX,
    )


@pytest.fixture
def server(cfg, tmp_path):
    fake = FakeCompose()
    srv = admin.build_server(cfg, tmp_path, host="127.0.0.1", port=0, token=TOKEN)
    srv.RequestHandlerClass.compose = fake
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    port = srv.server_address[1]
    # Attendre que le port accepte reellement. Sans cela le test se connecte
    # parfois avant que la boucle d'acceptation ne tourne : constate une fois sur
    # une suite complete, et un echec au hasard vaut moins qu'une seconde d'attente.
    for _ in range(50):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.02)
    base = f"http://127.0.0.1:{port}"
    yield base, fake
    srv.shutdown()
    srv.server_close()


def call(url, *, token=TOKEN, method="GET", payload=None, cookie=False):
    if token and not cookie:
        url += ("&" if "?" in url else "?") + f"t={token}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if cookie and token:
        req.add_header("Cookie", f"{admin.COOKIE}={token}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode(), resp.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(), exc.headers


# ------------------------------------------------------------- authentification


def test_without_a_token_nothing_is_served(server):
    base, _ = server
    for url, method in (("/", "GET"), ("/api/status", "GET"), ("/api/action", "POST")):
        status, _body, _h = call(base + url, token=None, method=method, payload={} if method == "POST" else None)
        assert status == 401, url


def test_a_wrong_token_is_refused(server):
    base, _ = server
    status, _b, _h = call(base + "/api/status", token="pas-le-bon")
    assert status == 401


def test_a_wrong_token_cannot_act(server):
    """Le point le plus important : un inconnu ne doit pas pouvoir arreter un service."""
    base, fake = server
    status, _b, _h = call(
        base + "/api/action",
        token="pas-le-bon",
        method="POST",
        payload={"service": "sonarr", "action": "stop"},
    )
    assert status == 401
    assert fake.calls == []


def test_the_token_can_arrive_by_cookie(server):
    base, _ = server
    status, _b, _h = call(base + "/api/status", cookie=True)
    assert status == 200


def test_loading_the_page_sets_an_httponly_cookie(server):
    """Sans cela, le jeton resterait dans l'URL a chaque appel."""
    base, _ = server
    status, _body, headers = call(base + "/")
    assert status == 200
    cookie = headers.get("Set-Cookie", "")
    assert admin.COOKIE in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Strict" in cookie


def test_tokens_are_not_predictable():
    tokens = {admin.generate_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(t) >= 24 for t in tokens)


# -------------------------------------------------------------------- etat


def test_status_lists_every_selected_service(server, cfg):
    base, _ = server
    _s, body, _h = call(base + "/api/status")
    ids = {s["id"] for s in json.loads(body)["services"]}
    assert ids == set(cfg.services)


def test_a_service_docker_does_not_know_is_shown_as_absent(server):
    """qBittorrent est selectionne mais absent du double : il doit apparaitre
    quand meme, sinon l'utilisateur ne comprend pas qu'il manque."""
    base, _ = server
    _s, body, _h = call(base + "/api/status")
    services = {s["id"]: s for s in json.loads(body)["services"]}
    assert services["qbittorrent"]["state"] == "absent"
    assert services["qbittorrent"]["up"] is False


def test_running_state_is_reported(server):
    base, _ = server
    _s, body, _h = call(base + "/api/status")
    services = {s["id"]: s for s in json.loads(body)["services"]}
    assert services["sonarr"]["up"] is True
    assert services["prowlarr"]["up"] is False


def test_running_but_unhealthy_is_not_reported_as_up():
    state = admin.ServiceState("silo", "running", "Up 2 minutes (unhealthy)", "unhealthy")

    assert state.up is False


def test_unhealthy_in_status_is_not_reported_as_up_when_health_is_missing():
    state = admin.ServiceState("silo", "running", "Up 2 minutes (unhealthy)")

    assert state.up is False


# ------------------------------------------------------------------- actions


@pytest.mark.parametrize("action", ["start", "stop", "restart"])
def test_the_three_actions_reach_compose(server, action):
    base, fake = server
    status, _b, _h = call(
        base + "/api/action", method="POST", payload={"service": "sonarr", "action": action}
    )
    assert status == 200
    assert fake.calls == [(action, "sonarr")]


def test_an_unknown_action_is_refused_before_reaching_the_shell(server):
    base, fake = server
    status, body, _h = call(
        base + "/api/action", method="POST", payload={"service": "sonarr", "action": "rm -rf /"}
    )
    assert status == 400
    assert "refusee" in body
    assert fake.calls == []


def test_a_service_outside_the_config_is_refused(server):
    """Le nom de service finit dans une ligne de commande : il doit venir de la
    configuration, jamais du client."""
    base, fake = server
    for name in ("jellyfin", "; rm -rf /", "../../etc", ""):
        status, _b, _h = call(
            base + "/api/action", method="POST", payload={"service": name, "action": "stop"}
        )
        assert status == 400, name
    assert fake.calls == []


def test_malformed_json_does_not_crash_the_server(server):
    base, fake = server
    req = urllib.request.Request(
        base + f"/api/action?t={TOKEN}", data=b"{pas du json", method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    assert status == 400
    assert fake.calls == []
    # Le serveur repond toujours apres coup.
    assert call(base + "/api/status")[0] == 200


def test_an_unknown_route_is_a_404_not_a_crash(server):
    base, _ = server
    assert call(base + "/api/inconnu")[0] == 404


# ---------------------------------------------------------- page servie


def test_the_served_page_carries_the_controls(server):
    base, _ = server
    _s, body, _h = call(base + "/")
    assert 'data-action="stop"' in body
    assert "rafraichir" in body


def test_a_dashboard_render_failure_returns_a_real_http_response(server, monkeypatch):
    """Une exception de rendu ne doit jamais devenir ERR_EMPTY_RESPONSE."""
    base, _ = server

    def fail(*_args, **_kwargs):
        raise RuntimeError("panne de rendu simulee")

    monkeypatch.setattr(admin.dashboard, "render", fail)

    status, body, headers = call(base + "/")

    assert status == 500
    assert "n'a pas pu etre generee" in body
    assert "docker logs --tail 200 plugarr-console" in body
    assert "panne de rendu simulee" not in body
    assert "HttpOnly" in headers.get("Set-Cookie", "")
    # Le serveur reste vivant et ses routes JSON restent utilisables.
    assert call(base + "/api/status")[0] == 200


def test_compose_control_refuses_an_action_outside_the_list(tmp_path):
    """Deuxieme barriere, cote runner : meme appele directement, `control` ne
    laisse pas passer autre chose que start/stop/restart."""
    from plugarr.runner import Compose

    with pytest.raises(ValueError, match="non autorisee"):
        Compose(tmp_path, "test").control("down", "sonarr")


# ------------------------------------------------------------- mises a jour


def test_an_update_target_that_is_not_a_version_is_refused(server, monkeypatch):
    """Le tag finit dans une reference d'image Docker : il doit ressembler a une
    version, jamais a ce que le client veut bien envoyer."""
    base, _ = server
    for bad in ("; rm -rf /", "latest", "../../etc", "4.0.19 && curl evil", ""):
        status, body, _h = call(
            base + "/api/update", method="POST", payload={"service": "sonarr", "target": bad}
        )
        assert status == 400, bad
        assert "refuse" in body or "inconnu" in body


def test_updating_a_service_outside_the_config_is_refused(server):
    base, _ = server
    status, _b, _h = call(
        base + "/api/update", method="POST", payload={"service": "jellyfin", "target": "1.0.0"}
    )
    assert status == 400


def test_a_valid_version_is_accepted_by_the_validator():
    from plugarr import updates

    assert updates.parse_version("4.0.19") == (4, 0, 19)
    assert updates.parse_version("v1.85.0") == (1, 85, 0)
    assert updates.parse_version("latest") is None


def test_silo_is_backed_up_before_its_update(server, cfg, monkeypatch):
    """Une migration Silo ne doit jamais commencer si la sauvegarde echoue."""
    base, _ = server
    silo = orchestrator.build_config(
        services=["silo"], config_root=cfg.config_root, data_root=cfg.data_root
    )
    cfg.services.update(silo.services)
    calls = []

    def backup(_maintenance):
        calls.append("backup")

    def update(*_args):
        calls.append("update")
        return True, "Silo mis a jour"

    monkeypatch.setattr(admin.Maintenance, "backup", backup)
    monkeypatch.setattr(admin, "apply_update", update)

    status, body, _headers = call(
        base + "/api/update",
        method="POST",
        payload={"service": "silo", "target": "build-523", "backup_first": False},
    )

    assert status == 200
    assert json.loads(body)["backup_first"] is True
    assert calls == ["backup", "update"]


def test_regular_update_runs_without_backup_when_not_requested(server, monkeypatch):
    base, _ = server
    calls = []
    monkeypatch.setattr(
        admin.Maintenance,
        "backup",
        lambda _maintenance: pytest.fail("no backup was requested"),
    )
    monkeypatch.setattr(
        admin,
        "apply_update",
        lambda *_args: (calls.append("update") or True, "updated"),
    )

    status, body, _headers = call(
        base + "/api/update",
        method="POST",
        payload={"service": "sonarr", "target": "4.0.20", "backup_first": False},
    )

    assert status == 200
    assert json.loads(body)["ok"] is True
    assert calls == ["update"]


def test_update_reports_the_backup_cause_and_never_pulls_after_failure(
    server, monkeypatch
):
    base, _ = server
    monkeypatch.setattr(
        admin.Maintenance,
        "backup",
        lambda _maintenance: (_ for _ in ()).throw(
            ValueError("ZIP does not support timestamps before 1980")
        ),
    )
    monkeypatch.setattr(
        admin,
        "apply_update",
        lambda *_args: pytest.fail("update must not start after a failed backup"),
    )

    status, body, _headers = call(
        base + "/api/update",
        method="POST",
        payload={"service": "sonarr", "target": "4.0.20", "backup_first": True},
    )

    assert status == 500
    error = json.loads(body)["error"]
    assert "Mise a jour annulee" in error
    assert "timestamps before 1980" in error
