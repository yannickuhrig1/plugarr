"""`doctor` diagnoses without writing; `--repair` changes one thing per confirmation.

Every repair is followed by a re-read of the condition it targets, and the
verdict printed comes from that re-read, not from the write.
"""

from pathlib import Path

import pytest

from plugarr import cli, connections, diagnostics, orchestrator, vpncheck
from plugarr.runner import Check

EDGE = {
    "id": "sonarr/downloadclient/qbittorrent",
    "source": "sonarr",
    "target": "qbittorrent",
    "kind": "downloadclient",
}


class _Runner:
    """Docker answers, and every selected container is up."""

    def __init__(self, *_args):
        pass

    def ps_json(self):
        return [
            {"Service": sid, "State": "running", "Status": "Up 1 hour"}
            for sid in ("sonarr", "qbittorrent", "gluetun")
        ]


def _interdit(nom):
    def _leve(*_args, **_kwargs):
        raise AssertionError(f"{nom} appele sans confirmation")

    return _leve


@pytest.fixture
def pile(monkeypatch):
    """A stack with one desynchronised port and one broken link, nothing else."""
    cfg = orchestrator.build_config(
        services=["sonarr", "qbittorrent"], data_root="/d", config_root="/c"
    )
    monkeypatch.setattr(cli, "_load_config", lambda _path: cfg)
    monkeypatch.setattr(cli, "_annoncer_nouvelle_version", lambda: None)
    monkeypatch.setattr(cli, "Compose", _Runner)
    monkeypatch.setattr(orchestrator, "preflight", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(orchestrator, "iter_selected", lambda _cfg: [])
    monkeypatch.setattr(
        vpncheck,
        "verifier",
        lambda _cfg: [Check(f"{vpncheck.PREFIXE_PORT} qbittorrent", False, "desynchronise", blocking=False)],
    )
    monkeypatch.setattr(connections, "entries", lambda _cfg: [EDGE])
    monkeypatch.setattr(
        connections, "test", lambda _cfg, _edge: {"state": "en echec", "detail": "Connexion absente."}
    )
    monkeypatch.setattr(diagnostics, "compose_drift", lambda *_args: None)
    monkeypatch.setattr(vpncheck, "reparer_port", _interdit("reparer_port"))
    monkeypatch.setattr(connections, "repair", _interdit("connections.repair"))
    return cfg


@pytest.mark.parametrize("repair", [False, True])
def test_doctor_requires_user_confirmation_before_touching_vpn(monkeypatch, pile, repair):
    monkeypatch.setattr(cli.typer, "confirm", lambda *_args, **_kwargs: False)

    cli.doctor(project_dir=Path("."), repair=repair)


def test_sans_repair_doctor_ne_demande_rien_et_le_dit(monkeypatch, pile, capsys):
    monkeypatch.setattr(cli.typer, "confirm", _interdit("typer.confirm"))

    cli.doctor(project_dir=Path("."), repair=False)

    sortie = capsys.readouterr().out
    assert "--repair" in sortie
    assert "n'a rien modifie" in " ".join(sortie.split())


def test_chaque_reparation_confirmee_est_relue(monkeypatch, pile, capsys):
    appels = []
    monkeypatch.setattr(cli.typer, "confirm", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        vpncheck,
        "reparer_port",
        lambda _cfg: appels.append("port") or Check("Port entrant (remise en place)", True, "qbittorrent ecoute maintenant 48406"),
    )
    monkeypatch.setattr(connections, "repair", lambda _cfg, edge: appels.append(("repare", edge["id"])) or True)
    monkeypatch.setattr(
        connections,
        "test",
        lambda _cfg, edge: appels.append(("relu", edge["id"])) or {"state": "en echec", "detail": "Connexion absente."},
    )

    cli.doctor(project_dir=Path("."), repair=True)

    sortie = " ".join(capsys.readouterr().out.split())
    assert "port" in appels
    # La relecture vient APRES l'ecriture, et c'est elle qui donne le verdict.
    ecriture = appels.index(("repare", EDGE["id"]))
    assert appels[ecriture + 1] == ("relu", EDGE["id"])
    assert "CORRIGE" in sortie
    assert "TOUJOURS EN ECHEC" in sortie, "une liaison encore cassee a la relecture n'est pas corrigee"


def test_une_reparation_refusee_ne_touche_a_rien(monkeypatch, pile, capsys):
    reponses = iter([False, True])
    monkeypatch.setattr(cli.typer, "confirm", lambda *_args, **_kwargs: next(reponses))
    appliquees = []
    monkeypatch.setattr(connections, "repair", lambda _cfg, edge: appliquees.append(edge["id"]) or True)
    monkeypatch.setattr(
        vpncheck,
        "reparer_port",
        lambda _cfg: appliquees.append("port") or Check("Port entrant (remise en place)", True, "ok"),
    )

    cli.doctor(project_dir=Path("."), repair=True)

    # Premiere offre (la liaison, plus grave) refusee ; seconde (le port) acceptee.
    assert appliquees == ["port"]
    assert "ignoree" in capsys.readouterr().out


def test_un_service_adopte_n_est_jamais_repare(monkeypatch, pile):
    pile.services["sonarr"].adopted = True
    monkeypatch.setattr(cli.typer, "confirm", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        vpncheck, "reparer_port", lambda _cfg: Check("Port entrant (remise en place)", True, "ok")
    )

    cli.doctor(project_dir=Path("."), repair=True)
