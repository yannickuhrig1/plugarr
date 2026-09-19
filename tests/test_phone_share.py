"""Envoi au telephone par QR code : un fichier, un lien, un telechargement.

Le serveur tourne pour de vrai. Seule la resolution d'adresse est remplacee :
en usage normal, elle refuse 127.0.0.1, que le telephone ne joindrait pas.
"""

from __future__ import annotations

import threading
import time

import httpx
import pytest

from plugarr import phone_share, webwizard
from plugarr.phone_share import PartageTelephone

CONTENU = b"PK\x03\x04 contenu fictif"


@pytest.fixture
def partage(monkeypatch):
    monkeypatch.setattr(phone_share, "_adresse_locale", lambda hote: "127.0.0.1")
    p = PartageTelephone("192.168.1.10")
    yield p
    p.arreter()


def _get(url, **kw):
    return httpx.get(url, trust_env=False, timeout=5, **kw)


def test_le_fichier_est_servi_une_seule_fois(partage):
    lien = partage.publier(CONTENU, "plugarr-nzb360-24.4.1-local.zip")

    premier = _get(lien["url"])
    assert premier.status_code == 200
    assert premier.content == CONTENU
    assert 'filename="plugarr-nzb360-24.4.1-local.zip"' in premier.headers["Content-Disposition"]
    assert premier.headers["Cache-Control"] == "no-store"

    # Le serveur se ferme apres le telechargement.
    for _ in range(50):
        if not partage.actif:
            break
        time.sleep(0.05)
    assert not partage.actif
    with pytest.raises(httpx.HTTPError):
        _get(lien["url"])


def test_un_mauvais_jeton_ne_consomme_rien(partage):
    lien = partage.publier(CONTENU, "f.zip")
    base, jeton = lien["url"].rsplit("/", 1)

    assert _get(f"{base}/{jeton[:-1]}x").status_code == 404
    assert _get(lien["url"].replace("/t/", "/autre/")).status_code == 404
    assert _get(lien["url"].rsplit("/t/", 1)[0] + "/").status_code == 404
    assert _get(lien["url"]).content == CONTENU


def test_un_apercu_de_lien_ne_consomme_rien(partage):
    """Une messagerie ou un navigateur qui sonde le lien (HEAD) ne doit pas
    avaler l'unique telechargement."""
    lien = partage.publier(CONTENU, "f.zip")

    assert httpx.head(lien["url"], trust_env=False, timeout=5).status_code == 404
    assert _get(lien["url"]).content == CONTENU


def test_le_lien_expire(monkeypatch):
    monkeypatch.setattr(phone_share, "_adresse_locale", lambda hote: "127.0.0.1")
    p = PartageTelephone("192.168.1.10", duree=0.3)
    try:
        lien = p.publier(CONTENU, "f.zip")
        time.sleep(0.6)
        assert not p.actif
        with pytest.raises(httpx.HTTPError):
            _get(lien["url"])
    finally:
        p.arreter()


def test_publier_remplace_le_lien_precedent(partage):
    ancien = partage.publier(CONTENU, "a.zip")
    nouveau = partage.publier(b"autre", "b.zip")

    assert ancien["url"] != nouveau["url"]
    assert _get(nouveau["url"]).content == b"autre"


@pytest.mark.parametrize(
    "nom", ["", "../evil.zip", "a/b.zip", "sans-extension", "x.exe", 'a".zip', "a" * 130 + ".zip"]
)
def test_les_noms_douteux_sont_refuses(partage, nom):
    with pytest.raises(ValueError, match="Nom"):
        partage.publier(CONTENU, nom)


def test_la_taille_est_bornee(partage):
    with pytest.raises(ValueError, match="Taille"):
        partage.publier(b"", "f.zip")
    with pytest.raises(ValueError, match="Taille"):
        partage.publier(b"x" * (phone_share.TAILLE_MAX + 1), "f.zip")


@pytest.mark.parametrize("hote", ["127.0.0.1", "localhost", "0.0.0.0", "8.8.8.8", "100.64.0.1"])
def test_seule_une_adresse_privee_est_acceptee(hote):
    """Ni boucle locale (le telephone ne la joint pas), ni adresse publique ou
    CGNAT (le lien sortirait du reseau de la maison)."""
    with pytest.raises(ValueError):
        PartageTelephone(hote)


def test_une_adresse_privee_est_acceptee():
    assert PartageTelephone("192.168.1.186").hote == "192.168.1.186"
    assert PartageTelephone("10.0.0.5").hote == "10.0.0.5"


# -- route de l'assistant ------------------------------------------------------------


@pytest.fixture
def assistant(tmp_path):
    server = webwizard.WizardServer(tmp_path / "projet", demo=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with httpx.Client(
        base_url=server.origin, trust_env=False, timeout=10,
        headers={"Authorization": "Bearer " + server.token},
    ) as client:
        yield server, client
    server.state.close_resources()
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)
    if server.state.worker:
        server.state.worker.join(timeout=5)


def envoyer(client, contenu=CONTENU, nom="plugarr-nzb360-24.4.1-local.zip", **kw):
    return client.post(
        "/api/phone-share", params={"name": nom}, content=contenu,
        headers={"Content-Type": "application/octet-stream", **kw.pop("headers", {})}, **kw,
    )


def test_la_route_exige_la_session(assistant):
    server, _client = assistant
    with httpx.Client(base_url=server.origin, trust_env=False, timeout=10) as anonyme:
        assert envoyer(anonyme).status_code == 401


def test_la_route_attend_la_fin_de_l_installation(assistant):
    _server, client = assistant
    reponse = envoyer(client)
    assert reponse.status_code == 400 and "fin de l'installation" in reponse.json()["error"]


def test_la_route_n_accepte_qu_un_fichier_brut(assistant):
    _server, client = assistant
    reponse = client.post("/api/phone-share", json={"x": 1})
    assert reponse.status_code == 400


def test_en_demonstration_aucun_serveur_n_est_ouvert(assistant):
    from tests.test_import_prowlarr import installer_demo

    server, client = assistant
    installer_demo(server, client)
    reponse = envoyer(client)
    assert reponse.status_code == 200, reponse.text
    assert reponse.json()["demo"] is True
    assert "192.0.2.50" in reponse.json()["url"]
    assert server.state.phone_share is None
