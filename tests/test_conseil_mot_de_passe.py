"""Le conseil « mot de passe hache herite » ne vaut que pour un refus d'identifiants.

Installation reelle du 26/09/2026 : autobrr v1.87.0 repondait 404 a l'ajout de
Sonarr (route renommee), et le rapport ajoutait « PlugArr a essaye les 4 mots de
passe qu'il connait : aucun n'est accepte », alors que la connexion avait reussi.
"""

from __future__ import annotations

import pytest

from plugarr import orchestrator
from plugarr.clients.base import WiringError
from plugarr.wiring import Wirer, WiringStep


@pytest.mark.parametrize(
    "erreur, conseille",
    [
        (WiringError("autobrr: ajout de Sonarr a echoue", "HTTP 404 - 404 page not found", ""), False),
        (WiringError("autobrr: connexion a echoue", "HTTP 401 - Unauthorized", ""), True),
        (WiringError("qui: connexion refusee", "HTTP 403", ""), True),
    ],
)
def test_le_conseil_ne_suit_que_les_refus_d_identifiants(tmp_path, monkeypatch, erreur, conseille):
    cfg = orchestrator.build_config(
        services=["autobrr", "sonarr"], config_root=str(tmp_path / "c"), data_root=str(tmp_path / "d")
    )
    wirer = Wirer(cfg)

    def echoue():
        raise erreur

    monkeypatch.setattr(wirer, "build_plan", lambda: [WiringStep("autobrr/clients", echoue)])
    monkeypatch.setattr(wirer, "_conseil_config_existante", lambda _sid: "CONSEIL")

    (resultat,) = wirer.execute()

    assert ("CONSEIL" in resultat.warnings) is conseille
