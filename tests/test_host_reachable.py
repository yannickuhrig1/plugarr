"""Verification rapide de l'hote des URL apres `docker compose up`.

Essai reel du 25/09/2026 sur un VPS Oracle : l'attente de Sonarr expirait
apres 300 s. Deux causes distinctes, chacune avec son message : l'IP publique
traduite (delai depasse) et le pare-feu de la machine (connexion rejetee).
"""

from __future__ import annotations

import pytest

from plugarr import orchestrator
from plugarr.orchestrator import InstallAborted, check_host_reachable


def _cfg(host: str):
    cfg = orchestrator.build_config(services=["sonarr", "transmission"], host=host)
    return cfg


class _Socket:
    def close(self):
        pass


def test_un_port_publie_joignable_laisse_passer():
    appels = []

    def connect(address, timeout):
        appels.append((address, timeout))
        return _Socket()

    cfg = _cfg("10.0.0.30")
    check_host_reachable(cfg, connect=connect, sleep=lambda _s: None)

    assert appels == [(("10.0.0.30", cfg.services["sonarr"].host_port), 5)]


def test_ip_publique_traduite_echoue_vite_avec_la_bonne_cause():
    def connect(_address, timeout):
        raise TimeoutError("timed out")

    with pytest.raises(InstallAborted, match="adresse privee"):
        check_host_reachable(_cfg("203.0.113.10"), connect=connect, sleep=lambda _s: None)


def test_pare_feu_qui_rejette_les_conteneurs_est_nomme():
    def connect(_address, timeout):
        raise OSError(113, "No route to host")

    with pytest.raises(InstallAborted, match="pare-feu"):
        check_host_reachable(_cfg("10.0.0.30"), connect=connect, sleep=lambda _s: None)


def test_un_echec_passager_est_reessaye():
    reponses = [ConnectionRefusedError(111, "refused"), _Socket()]

    def connect(_address, timeout):
        reponse = reponses.pop(0)
        if isinstance(reponse, Exception):
            raise reponse
        return reponse

    check_host_reachable(_cfg("10.0.0.30"), connect=connect, sleep=lambda _s: None)
    assert reponses == []
