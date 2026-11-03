"""Une session qBittorrent refusee se rouvre, une fois.

Elle expire, et ne survit pas a un redemarrage du client. Sans reprise, la
prochaine requete echouait avec « la session est-elle bien authentifiee ? », alors
que les identifiants etaient bons.
"""

from __future__ import annotations

import pytest

from plugarr.clients.base import WiringError
from plugarr.clients.qbittorrent import QBittorrentClient

BASE = "http://qb.test"
LOGIN = f"{BASE}/api/v2/auth/login"
PREFERENCES = f"{BASE}/api/v2/app/preferences"
CATEGORIES = f"{BASE}/api/v2/torrents/categories"


def _connexion_acceptee(httpx_mock):
    httpx_mock.add_response(url=LOGIN, status_code=204, headers={"set-cookie": "QBT_SID=a; path=/"})


def test_une_session_expiree_se_rouvre_d_elle_meme(httpx_mock):
    httpx_mock.add_response(url=PREFERENCES, status_code=403, text="Forbidden")
    _connexion_acceptee(httpx_mock)
    httpx_mock.add_response(url=PREFERENCES, json={"listen_port": 51413})

    with QBittorrentClient(BASE, "admin", "secret") as client:
        assert client.preferences() == {"listen_port": 51413}


def test_le_refus_deguise_en_200_se_rouvre_aussi(httpx_mock):
    """Le cas decrit dans `categories` : "Forbidden" en texte brut, code 200."""
    httpx_mock.add_response(url=CATEGORIES, text="Forbidden")
    _connexion_acceptee(httpx_mock)
    httpx_mock.add_response(url=CATEGORIES, json={"tv": {}})

    with QBittorrentClient(BASE, "admin", "secret") as client:
        assert client.categories() == {"tv": {}}


def test_la_version_ne_renvoie_plus_forbidden(httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/api/v2/app/version", status_code=403, text="Forbidden")
    _connexion_acceptee(httpx_mock)
    httpx_mock.add_response(url=f"{BASE}/api/v2/app/version", text="v5.2.3")

    with QBittorrentClient(BASE, "admin", "secret") as client:
        assert client.version == "v5.2.3"


def test_une_seule_reprise(httpx_mock):
    """Pas de boucle : qBittorrent bannit l'adresse apres quelques connexions."""
    httpx_mock.add_response(url=PREFERENCES, status_code=403, text="Forbidden", is_reusable=True)
    _connexion_acceptee(httpx_mock)

    with QBittorrentClient(BASE, "admin", "secret") as client, pytest.raises(WiringError):
        client.preferences()

    assert len(httpx_mock.get_requests(url=LOGIN)) == 1
    assert len(httpx_mock.get_requests(url=PREFERENCES)) == 2


def test_des_identifiants_faux_sont_nommes_comme_tels(httpx_mock):
    """Le vrai diagnostic, plutot que « preferences illisibles »."""
    httpx_mock.add_response(url=PREFERENCES, status_code=403, text="Forbidden")
    httpx_mock.add_response(url=LOGIN, text="Fails.")

    with (
        QBittorrentClient(BASE, "admin", "faux") as client,
        pytest.raises(WiringError, match="identifiants refuses"),
    ):
        client.preferences()


def test_une_reponse_normale_ne_rouvre_rien(httpx_mock):
    httpx_mock.add_response(url=PREFERENCES, json={"listen_port": 51413})

    with QBittorrentClient(BASE, "admin", "secret") as client:
        client.preferences()

    assert httpx_mock.get_requests(url=LOGIN) == []
