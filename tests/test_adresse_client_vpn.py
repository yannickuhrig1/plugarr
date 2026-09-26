"""Prowlarr doit viser le client de telechargement au MEME endroit que les *arr.

Panne reelle, signalee apres une installation avec VPN. Sur quatorze liaisons,
deux echouaient, et seulement celles de Prowlarr :

    ECHEC prowlarr/downloadclient/transmission
      Unknown exception: Name does not resolve (transmission:9091)
    ECHEC prowlarr/downloadclient/qbittorrent
      Unable to connect to qBittorrent — Name does not resolve (qbittorrent:8080)

Sonarr, Radarr et Lidarr se cablaient tres bien sur les MEMES clients au meme
instant, ce qui rendait la panne incomprehensible a lire.

La cause : VPN active, un client torrent passe en `network_mode: service:gluetun`
et perd son nom sur le reseau — c'est `gluetun` qu'il faut viser.
`step_download_client` le savait ; `step_prowlarr_download_client` posait
`dl_spec.id` en dur.

C'est la TROISIEME fois que ces deux etapes divergent : le mot de passe d'un
client, puis sa cle apres rotation, maintenant son adresse. Elles lisent
desormais la meme fonction.
"""

from __future__ import annotations

import pytest

from plugarr import orchestrator
from plugarr.models import VpnConfig
from plugarr.wiring import Wirer


def _wirer(*, vpn: bool = False, adopte: bool = False):
    cfg = orchestrator.build_config(
        services=["sonarr", "prowlarr", "transmission", "qbittorrent"],
        config_root="/c",
        data_root="/d",
    )
    if vpn:
        cfg.vpn = VpnConfig(
            enabled=True, provider="protonvpn", vpn_type="wireguard", wireguard_private_key="k" * 44
        )
    if adopte:
        for sid in ("transmission", "qbittorrent"):
            cfg.services[sid].adopted = True
    cfg.host = "192.168.1.50"
    return Wirer(cfg)


@pytest.mark.parametrize("dl_id", ["transmission", "qbittorrent"])
def test_sans_vpn_le_client_se_joint_par_son_nom(dl_id):
    hote, _port = _wirer().adresse_client(dl_id)

    assert hote == dl_id


@pytest.mark.parametrize("dl_id", ["transmission", "qbittorrent"])
def test_sous_vpn_le_client_se_joint_par_gluetun(dl_id):
    """Son propre nom ne resout plus : il n'a plus de pile reseau a lui."""
    hote, _port = _wirer(vpn=True).adresse_client(dl_id)

    assert hote == "gluetun"


def test_sous_vpn_le_port_reste_celui_du_conteneur():
    """Gluetun publie les ports INTERNES des clients qu'il porte."""
    assert _wirer(vpn=True).adresse_client("transmission")[1] == 9091
    assert _wirer(vpn=True).adresse_client("qbittorrent")[1] == 8080


def test_un_client_adopte_se_joint_par_l_hote():
    """Il n'est pas sur le reseau compose : seul son port publie le rend
    joignable."""
    hote, port = _wirer(adopte=True).adresse_client("qbittorrent")

    assert hote == "192.168.1.50"
    assert port == 8080


def test_prowlarr_et_les_arr_visent_la_meme_adresse():
    """Le coeur de la panne. Deux etapes distinctes, une seule verite."""
    import inspect

    from plugarr.wiring import Wirer as W

    for etape in (W.step_download_client, W.step_prowlarr_download_client):
        source = inspect.getsource(etape)
        assert "adresse_client" in source, f"{etape.__name__} resout l'adresse dans son coin"
        assert "host=dl_spec.id" not in source, f"{etape.__name__} pose encore le nom en dur"


@pytest.mark.parametrize("vpn_avant, attendu", [(True, "transmission"), (False, "gluetun")])
def test_une_entree_existante_suit_le_trajet_reseau_actuel(monkeypatch, vpn_avant, attendu):
    """Second passage reel du 25/09/2026, VPN retire : les *arr visaient encore
    gluetun:9091 et chaque test echouait. Le sens inverse casse de la meme facon."""
    wirer = _wirer(vpn=not vpn_avant)
    ancien = "gluetun" if vpn_avant else "transmission"
    alignes = []

    class Arr:
        def ensure_resource(self, resource, *, name, implementation, values, extra):
            return {"id": 1, "name": name, "fields": [{"name": "host", "value": ancien}]}, False, []

        def sync_fields(self, resource, existing, values):
            alignes.append(values)
            return [k for k in values if k == "host"]

        def find_by_name(self, resource, name):
            return {"id": 1, "name": name}

        def get(self, resource):
            return []

    faux = Arr()
    monkeypatch.setattr(wirer, "arr", lambda _sid: faux)
    monkeypatch.setattr(wirer, "prowlarr", lambda: faux, raising=False)
    monkeypatch.setattr(wirer, "_verify", lambda *a, **k: a[3])

    wirer.step_download_client("sonarr", "transmission")

    assert alignes[0]["host"] == attendu
    assert alignes[0]["port"] == 9091


def test_une_entree_adoptee_garde_son_adresse(monkeypatch):
    """Un client adopte appartient a l'utilisateur : son adresse n'est pas la notre."""
    wirer = _wirer(adopte=True)
    alignes = []

    class Arr:
        def ensure_resource(self, resource, *, name, implementation, values, extra):
            return {"id": 1, "name": name, "fields": []}, False, []

        def sync_fields(self, resource, existing, values):
            alignes.append(values)
            return []

        def find_by_name(self, resource, name):
            return {"id": 1, "name": name}

        def get(self, resource):
            return []

    faux = Arr()
    monkeypatch.setattr(wirer, "arr", lambda _sid: faux)
    monkeypatch.setattr(wirer, "_verify", lambda *a, **k: a[3])

    wirer.step_download_client("sonarr", "qbittorrent")

    assert "host" not in alignes[0]
