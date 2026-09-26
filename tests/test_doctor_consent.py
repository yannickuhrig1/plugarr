"""A plain doctor run never applies the proposed VPN port correction."""

from pathlib import Path

import pytest

from plugarr import cli, orchestrator
from plugarr.runner import Check


@pytest.mark.parametrize("repair", [False, True])
def test_doctor_requires_user_confirmation_before_touching_vpn(monkeypatch, repair):
    cfg = orchestrator.build_config(services=[], data_root="/d", config_root="/c")
    monkeypatch.setattr(cli, "_load_config", lambda _path: cfg)
    monkeypatch.setattr(cli, "_annoncer_nouvelle_version", lambda: None)
    monkeypatch.setattr(cli.orchestrator, "preflight", lambda *_args: [])
    monkeypatch.setattr(cli.orchestrator, "iter_selected", lambda _cfg: [])
    monkeypatch.setattr(
        cli.vpncheck,
        "verifier",
        lambda _cfg: [Check(f"{cli.vpncheck.PREFIXE_PORT} qbittorrent", False, "desynchronise")],
    )
    monkeypatch.setattr(cli.vpncheck, "reparer_port", lambda _cfg: (_ for _ in ()).throw(AssertionError("repair called")))
    monkeypatch.setattr(cli.typer, "confirm", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(cli.diagnostics, "connection_checks", lambda _cfg: [])
    monkeypatch.setattr(cli.diagnostics, "compose_drift", lambda *_args: None)

    class Runner:
        def __init__(self, *_args):
            pass

        def ps(self):
            return ""

    monkeypatch.setattr(cli, "Compose", Runner)
    cli.doctor(project_dir=Path("."), repair=repair)
