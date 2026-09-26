"""La notification Jellyfin d'un *arr suit la cle ACTUELLE de Jellyfin.

Essai reel du 26/09/2026 sous Windows : Jellyfin reinitialise (cle neuve),
Sonarr et Radarr repris de l'installation precedente. Leur notification
Jellyfin etait « deja presente » avec l'ancienne cle, et son test echouait :

    ECHEC sonarr -> jellyfin (rafraichissement de bibliotheque) - deja present
          (id=1) - le test de connexion a echoue
"""

from __future__ import annotations

from plugarr import orchestrator
from plugarr.clients.arr import ArrClient
from plugarr.wiring import Wirer


class _Arr:
    """Un *arr qui porte deja une notification Jellyfin, avec cette cle."""

    sync_fields = ArrClient.sync_fields

    def __init__(self, cle: str):
        self.cle = cle
        self.ecritures: list[tuple[str, dict]] = []

    def ensure_resource(self, resource, *, name, implementation, values, extra):
        champs = [
            {"name": "host", "value": "jellyfin"},
            {"name": "port", "value": 8096},
            {"name": "apiKey", "value": self.cle},
            {"name": "updateLibrary", "value": True},
        ]
        return {"id": 1, "name": name, "fields": champs}, False, []

    def put(self, chemin, corps):
        self.ecritures.append((chemin, corps))

    def find_by_name(self, resource, name):
        return {"id": 1, "name": name}


def _wirer(monkeypatch, arr):
    cfg = orchestrator.build_config(services=["sonarr", "jellyfin"], config_root="/c", data_root="/d")
    cfg.services["jellyfin"].api_key = "cle-neuve"
    wirer = Wirer(cfg)
    monkeypatch.setattr(wirer, "arr", lambda _sid: arr)
    monkeypatch.setattr(wirer, "_verify", lambda *a, **k: a[3])
    return wirer


def test_une_notification_existante_recoit_la_nouvelle_cle(monkeypatch):
    arr = _Arr("cle-perimee")

    resultat = _wirer(monkeypatch, arr).step_jellyfin_notification("sonarr")

    assert "realigne (apiKey)" in resultat.detail
    ((chemin, corps),) = arr.ecritures
    assert chemin == "notification/1"
    assert {c["name"]: c["value"] for c in corps["fields"]}["apiKey"] == "cle-neuve"


def test_une_notification_a_jour_n_est_pas_reecrite(monkeypatch):
    arr = _Arr("cle-neuve")

    resultat = _wirer(monkeypatch, arr).step_jellyfin_notification("sonarr")

    assert "deja present" in resultat.detail
    assert arr.ecritures == []
