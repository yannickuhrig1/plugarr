"""Tests du client autobrr. Aucun reseau : les reponses sont simulees.

Les formes reproduites ici viennent d'une instance v1.85.0 reelle.
"""

from __future__ import annotations

import pytest

from plugarr import orchestrator
from plugarr.clients.autobrr import CLIENT_TYPES, AutobrrClient, client_host
from plugarr.clients.base import WiringError
from plugarr.wiring import _autobrr_targets


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class FakeClient(AutobrrClient):
    """Remplace la couche HTTP par un journal d'appels et des reponses fixes."""

    def __init__(self, responses):
        super().__init__("http://autobrr:7474")
        self._responses = responses
        self.calls: list[tuple[str, str, dict]] = []

    def _request(self, method, path, **kw):
        self.calls.append((method, path, kw.get("json") or {}))
        return self._responses.get(f"{method} {path}", FakeResponse(200, []))


def test_the_auth_header_is_x_api_token(monkeypatch):
    """Les *arr utilisent X-Api-Key, autobrr non. Se tromper donne un 403 nu."""
    captured: dict = {}

    class Spy:
        def request(self, method, path, headers=None, **kw):
            captured.update(headers or {})
            return FakeResponse(200, [])

    client = AutobrrClient("http://autobrr:7474")
    client._http = Spy()
    client._token = "un-jeton"
    client.clients()
    assert "X-API-Token" in captured
    assert "X-Api-Key" not in captured


def test_onboarding_is_skipped_when_a_user_exists():
    """GET /api/auth/onboard renvoie 503 des qu'un compte existe : c'est ce qui
    rend l'etape rejouable."""
    client = FakeClient({"GET /api/auth/onboard": FakeResponse(503, text="already registered")})
    assert client.onboarded
    assert client.onboard("u", "p") is False
    assert not any(m == "POST" and p == "/api/auth/onboard" for m, p, _ in client.calls)


def test_onboarding_runs_on_a_fresh_instance():
    client = FakeClient(
        {
            "GET /api/auth/onboard": FakeResponse(204),
            "POST /api/auth/onboard": FakeResponse(200, {"message": "user created"}),
        }
    )
    assert client.onboard("plugarr", "secret") is True
    posted = [kw for m, _p, kw in client.calls if m == "POST"]
    assert posted[0] == {"username": "plugarr", "password": "secret"}


def test_api_key_creation_always_sends_scopes():
    """Sans `scopes`, autobrr repond 500 sur une contrainte NOT NULL de sa base."""
    client = FakeClient(
        {
            "GET /api/keys": FakeResponse(200, []),
            "POST /api/keys": FakeResponse(201, {"name": "plugarr", "key": "abc123"}),
        }
    )
    assert client.ensure_api_key("plugarr") == "abc123"
    payload = next(kw for m, p, kw in client.calls if p == "/api/keys" and m == "POST")
    assert payload["scopes"] == ["read", "write"]


def test_an_existing_api_key_is_reused():
    client = FakeClient(
        {"GET /api/keys": FakeResponse(200, [{"name": "plugarr", "key": "deja-la"}])}
    )
    assert client.ensure_api_key("plugarr") == "deja-la"
    assert not any(m == "POST" for m, _p, _kw in client.calls)


@pytest.mark.parametrize(
    ("service_id", "expected"),
    [
        ("sonarr", "SONARR"),
        ("radarr", "RADARR"),
        ("lidarr", "LIDARR"),
        ("qbittorrent", "QBITTORRENT"),
        ("transmission", "TRANSMISSION"),
    ],
)
def test_applications_and_clients_share_one_endpoint(service_id, expected):
    """autobrr ne distingue pas les deux : seul le `type` change."""
    client = FakeClient(
        {
            "GET /api/download_clients": FakeResponse(200, []),
            "POST /api/download_clients": FakeResponse(201, {"id": 1}),
        }
    )
    added, _ = client.ensure_client(
        name="X", service_id=service_id, host="http://x:1", api_key="k"
    )
    assert added
    payload = next(kw for m, _p, kw in client.calls if m == "POST")
    assert payload["type"] == expected
    assert payload["settings"]["apikey"] == "k"


def test_an_unknown_service_is_refused_with_the_known_list():
    client = FakeClient({"GET /api/download_clients": FakeResponse(200, [])})
    with pytest.raises(WiringError, match="types acceptes"):
        client.ensure_client(name="X", service_id="jellyfin", host="http://x:1")


def test_adding_twice_does_nothing():
    client = FakeClient(
        {"GET /api/download_clients": FakeResponse(200, [{"name": "Sonarr", "type": "SONARR"}])}
    )
    added, message = client.ensure_client(name="Sonarr", service_id="sonarr", host="http://x:1")
    assert not added
    assert message == "deja present"


def test_a_download_client_carries_no_api_key():
    """qBittorrent s'authentifie par identifiant et mot de passe, pas par cle."""
    client = FakeClient(
        {
            "GET /api/download_clients": FakeResponse(200, []),
            "POST /api/download_clients": FakeResponse(201, {"id": 1}),
        }
    )
    client.ensure_client(
        name="qBittorrent",
        service_id="qbittorrent",
        host="http://q:8080",
        username="u",
        password="p",
    )
    payload = next(kw for m, _p, kw in client.calls if m == "POST")
    assert payload["settings"] == {}
    assert payload["username"] == "u"


def test_every_known_type_is_uppercase():
    assert all(v == v.upper() for v in CLIENT_TYPES.values())


def test_sabnzbd_is_not_sent_to_autobrr():
    """autobrr v1.85 n'a pas de type SABnzbd et refusait tout le cablage."""
    cfg = orchestrator.build_config(
        services=["sonarr", "autobrr", "qbittorrent", "sabnzbd"],
        config_root="/c",
        data_root="/d",
    )

    assert set(_autobrr_targets(cfg)) == {"sonarr", "qbittorrent"}


# ------------------------------------------------- point d'entree Transmission


def test_transmission_est_declare_sur_son_point_d_entree_rpc():
    """Transmission n'expose pas son RPC a la racine.

    `http://transmission:9091/` repond une redirection HTML ; autobrr attend du
    JSON et echoue sur « invalid character '<' ». Constate en conditions reelles :
    une installation complete affichait 19/20 liens pour cette seule raison.

    Verifie contre l'API d'autobrr v1.85.0 : racine -> HTTP 500,
    `/transmission/rpc` -> HTTP 204.
    """
    assert (
        client_host("transmission", "http://transmission:9091")
        == "http://transmission:9091/transmission/rpc"
    )


def test_les_autres_services_gardent_leur_racine():
    """qBittorrent et les *arr repondent bien a la racine : ne rien y ajouter."""
    for service in ("qbittorrent", "sonarr", "radarr", "lidarr"):
        assert client_host(service, "http://x:1") == "http://x:1"


def test_le_chemin_n_est_pas_double_par_une_barre():
    assert (
        client_host("transmission", "http://transmission:9091/")
        == "http://transmission:9091/transmission/rpc"
    )


def test_ensure_client_envoie_le_chemin_rpc():
    """Le chemin doit arriver dans la charge utile, pas seulement dans un helper."""
    fake = FakeClient({})
    fake._token = "t"
    fake.ensure_client(name="Transmission", service_id="transmission", host="http://transmission:9091")

    posted = [c for c in fake.calls if c[0] == "POST"]
    assert posted, "aucun POST emis"
    assert posted[-1][2]["host"] == "http://transmission:9091/transmission/rpc"
