"""Condensat distant sans `buildx`.

Console reelle du 25/09/2026 : ni son image ni le VPS n'avaient `buildx`, et
chaque image epinglee par tag affichait « verification incomplete ».
"""

from __future__ import annotations

import httpx

from plugarr import updates

DIGEST = "sha256:" + "a" * 64


def test_sans_buildx_le_registre_donne_le_condensat(monkeypatch):
    monkeypatch.setattr(updates, "_docker", lambda *a, **k: (1, "docker: unknown command: docker buildx"))
    vues = []

    def handler(request: httpx.Request) -> httpx.Response:
        vues.append(request)
        if request.url.host == "auth.example":
            return httpx.Response(200, json={"token": "jeton"})
        if "authorization" not in request.headers:
            return httpx.Response(
                401,
                headers={"www-authenticate": 'Bearer realm="https://auth.example/token",service="lscr.io"'},
            )
        return httpx.Response(200, headers={"docker-content-digest": DIGEST})

    transport = httpx.MockTransport(handler)
    vrai_client = httpx.Client
    monkeypatch.setattr(updates.httpx, "Client", lambda **kw: vrai_client(transport=transport, **kw))

    assert updates.remote_digest("lscr.io/linuxserver/sonarr:4.0.19") == DIGEST
    manifeste = [r for r in vues if r.url.host == "lscr.io"][-1]
    assert manifeste.url.path == "/v2/linuxserver/sonarr/manifests/4.0.19"
    assert "manifest.list.v2+json" in manifeste.headers["accept"]


def test_un_registre_muet_reste_un_probleme_signale(monkeypatch):
    monkeypatch.setattr(updates, "_docker", lambda *a, **k: (1, ""))
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    vrai_client = httpx.Client
    monkeypatch.setattr(updates.httpx, "Client", lambda **kw: vrai_client(transport=transport, **kw))

    assert updates.remote_digest("lscr.io/linuxserver/sonarr:4.0.19") is None
