"""The diagnostic reports evidence and plans without silently changing a stack."""

from plugarr import compose, diagnostics, orchestrator
from plugarr.wiring import StepResult, Wirer, WiringStep


def test_existing_hardlinks_confirms_only_real_shared_inodes(tmp_path):
    from os import link

    torrents = tmp_path / "torrents"
    media = tmp_path / "media"
    torrents.mkdir()
    media.mkdir()
    source = torrents / "movie.mkv"
    source.write_bytes(b"sample")
    link(source, media / "movie.mkv")
    (media / "other.mkv").write_bytes(b"sample")

    result = diagnostics.existing_hardlinks(tmp_path)

    assert result == {"checked": 3, "matched": 1, "partial": False, "available": True}


def test_existing_hardlinks_never_counts_equal_content_as_a_link(tmp_path):
    for directory in ("torrents", "media"):
        folder = tmp_path / directory
        folder.mkdir()
        (folder / "same.mkv").write_bytes(b"same bytes")

    result = diagnostics.existing_hardlinks(tmp_path)

    assert result["matched"] == 0
    assert result["available"]


def test_existing_hardlinks_reports_partial_scan(tmp_path):
    for directory in ("torrents", "media"):
        folder = tmp_path / directory
        folder.mkdir()
        for index in range(3):
            (folder / f"{index}.mkv").write_bytes(b"x")

    result = diagnostics.existing_hardlinks(tmp_path, max_files=2)

    assert result["partial"]
    assert result["checked"] == 2


def _cfg(*services):
    return orchestrator.build_config(
        services=list(services), data_root="/data", config_root="/config"
    )


def test_broken_link_has_a_targeted_repair_plan(monkeypatch):
    cfg = _cfg("sonarr", "qbittorrent")
    edge = {
        "id": "sonarr/downloadclient/qbittorrent",
        "source": "sonarr",
        "target": "qbittorrent",
        "kind": "downloadclient",
    }
    monkeypatch.setattr(diagnostics.connections, "entries", lambda _cfg: [edge])
    monkeypatch.setattr(
        diagnostics.connections,
        "test",
        lambda _cfg, _edge: {"state": "en echec", "detail": "Connexion absente."},
    )

    check = diagnostics.connection_checks(cfg)[0]

    assert check["ok"] is False
    assert check["edge_id"] == edge["id"]
    assert edge["id"] in check["next_step"]
    cfg.services["sonarr"].adopted = True
    assert "Service adopte" in diagnostics.connection_checks(cfg)[0]["next_step"]


def test_compose_drift_reports_change_without_exposing_secrets(tmp_path):
    cfg = _cfg("sonarr")
    cfg.services["sonarr"].api_key = "private-key"
    path = tmp_path / "docker-compose.yml"
    path.write_text("services:\n  sonarr:\n    image: different\n", encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text(compose.render_env(cfg, tmp_path), encoding="utf-8")

    check = diagnostics.compose_drift(cfg, tmp_path)

    assert check["ok"] is False
    assert "private-key" not in str(check)
    assert "Sauvegardez" in check["next_step"]
    path.write_text(compose.render_compose(cfg), encoding="utf-8")
    assert diagnostics.compose_drift(cfg, tmp_path)["ok"] is True
    env_path.write_text(env_path.read_text(encoding="utf-8").replace("private-key", "changed"), encoding="utf-8")
    assert diagnostics.compose_drift(cfg, tmp_path)["ok"] is False
    cfg.services["sonarr"].adopted = True
    assert diagnostics.compose_drift(cfg, tmp_path) is None


def test_selective_wiring_runs_only_the_approved_step(monkeypatch):
    wirer = Wirer(_cfg("sonarr", "qbittorrent"))
    called = []

    def step(name):
        return WiringStep(name, lambda: called.append(name) or StepResult(name, True, "ok"))

    monkeypatch.setattr(wirer, "build_plan", lambda: [step("a"), step("b")])

    result = wirer.execute(selected_steps={"b"})

    assert called == ["b"]
    assert [item.step_id for item in result] == ["b"]


def test_le_diagnostic_de_la_console_ne_signale_pas_ses_donnees_en_lecture_seule(tmp_path, monkeypatch):
    """Essai reel du 26/09/2026 : « racine des donnees » en echec BLOQUANT dans la
    console, qui monte DATA_ROOT en lecture seule par conception."""
    from plugarr import orchestrator
    from plugarr.i18n import t
    from plugarr.runner import Check

    cfg = orchestrator.build_config(
        services=["sonarr"], config_root=str(tmp_path / "c"), data_root=str(tmp_path / "d")
    )
    monkeypatch.setattr(
        orchestrator,
        "preflight",
        lambda *_a, **_k: [
            Check(t("racine des donnees"), False, "Read-only file system", blocking=True),
            Check("hardlinks /data", False, "Read-only file system", blocking=False),
            Check("docker", True, "ok"),
        ],
    )

    monkeypatch.setattr(orchestrator, "_donnees_en_lecture_seule_voulue", lambda _d: True)
    console = orchestrator.diagnostic(cfg)
    assert all(c.ok for c in console)
    assert not any(c.blocking and not c.ok for c in console)

    monkeypatch.setattr(orchestrator, "_donnees_en_lecture_seule_voulue", lambda _d: False)
    hote = orchestrator.diagnostic(cfg)
    assert [c.ok for c in hote] == [False, False, True]

