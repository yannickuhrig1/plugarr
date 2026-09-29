"""Controlled update preview and live verification boundaries."""

from types import SimpleNamespace

from typer.testing import CliRunner

from plugarr import cli, compose, maintenance, orchestrator, update_operation


def test_upgrade_preview_does_not_write_or_start_operations(tmp_path, monkeypatch):
    cfg = orchestrator.build_config(
        services=["sonarr"], config_root=str(tmp_path / "config"),
        data_root=str(tmp_path / "data"),
    )
    cfg.services["sonarr"].image = "lscr.io/linuxserver/sonarr:0.0.1"
    stack = tmp_path / "stack.yml"
    stack.write_text(compose.render_stack(cfg), encoding="utf-8")
    before = stack.read_bytes()
    monkeypatch.setattr(cli, "_annoncer_nouvelle_version", lambda: None)
    monkeypatch.setattr(
        cli.journal, "start",
        lambda *_args: (_ for _ in ()).throw(AssertionError("preview started journal")),
    )
    monkeypatch.setattr(
        cli.sauvegarde, "sauvegarder",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("preview wrote backup")),
    )

    result = CliRunner().invoke(cli.app, ["upgrade", "--project-dir", str(tmp_path),
                                           "--dry-run", "--skip-wire"])
    assert result.exit_code == 0, result.output
    assert "Pré-rapport" in result.output
    assert stack.read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["stack.yml"]


def test_upgrade_blocks_wiring_unbacked_adopted_service(tmp_path, monkeypatch):
    cfg = orchestrator.build_config(
        services=["sonarr"], config_root=str(tmp_path / "config"),
        data_root=str(tmp_path / "data"),
    )
    cfg.services["sonarr"].adopted = True
    stack = tmp_path / "stack.yml"
    stack.write_text(compose.render_stack(cfg), encoding="utf-8")
    before = stack.read_bytes()
    monkeypatch.setattr(cli, "_annoncer_nouvelle_version", lambda: None)
    result = CliRunner().invoke(cli.app, ["upgrade", "--project-dir", str(tmp_path),
                                           "--dry-run"])
    assert result.exit_code == 2
    assert "--skip-wire" in result.output
    assert stack.read_bytes() == before


def test_post_validation_fails_on_unhealthy_service_or_broken_link(tmp_path, monkeypatch):
    from plugarr import admin

    cfg = orchestrator.build_config(
        services=["sonarr"], config_root=str(tmp_path / "config"),
        data_root=str(tmp_path / "data"),
    )
    monkeypatch.setattr(
        admin, "doctor_payload",
        lambda *_args: {"checks": [
            {"name": "Etat Sonarr", "ok": False},
            {"name": "API Sonarr", "ok": True},
            {"name": "Liaison Sonarr -> Prowlarr", "ok": False},
        ]},
    )
    result = update_operation.verify(cfg, tmp_path, object(), ["sonarr"], attempts=1)
    assert result["ok"] is False
    assert len(result["checks"]) == 3


def test_failed_probe_is_reported_as_failed_validation(tmp_path, monkeypatch):
    from plugarr import admin

    monkeypatch.setattr(
        admin, "doctor_payload",
        lambda *_args: (_ for _ in ()).throw(OSError("token=private")),
    )
    result = update_operation.verify(object(), tmp_path, object(), ["sonarr"], attempts=1)
    assert result["ok"] is False
    assert result["checks"][0]["detail"] == "OSError"


def test_strict_preupdate_backup_keeps_older_archives(tmp_path, monkeypatch):
    cfg = orchestrator.build_config(
        services=["sonarr"], config_root=str(tmp_path / "config"),
        data_root=str(tmp_path / "data"),
    )
    worker = maintenance.Maintenance(cfg, tmp_path, persistent=False)
    directory = tmp_path / "backups"
    directory.mkdir()
    old = directory / "plugarr-older.zip"
    old.write_bytes(b"older archive")
    worker.state["archives"] = [old.name]
    worker.state["schedule"]["keep"] = 1

    def fake_backup(_cfg, _project_dir, destination, *, strict):
        assert strict
        destination.write_bytes(b"new archive")
        return SimpleNamespace(archive=destination)

    monkeypatch.setattr(maintenance.sauvegarde, "sauvegarder", fake_backup)
    worker.backup(strict=True)
    assert old.read_bytes() == b"older archive"
    assert old.name in worker.state["archives"]
