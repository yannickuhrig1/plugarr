"""La carte suit le plan executable et les evenements, jamais une animation fictive."""

import json

import pytest

from plugarr import catalog, orchestrator, wizard_graph
from plugarr.webwizard import WizardState
from plugarr.wiring import StepResult, Wirer, WiringStep


def config(services, vpn=False):
    cfg = orchestrator.build_config(services=services)
    cfg.vpn.enabled = vpn
    return cfg


@pytest.mark.parametrize("services", [[], ["sonarr"], ["flood"], ["seerr"], list(catalog.CATALOG)])
def test_graph_has_exact_selected_nodes_dependencies_and_no_dangling_links(services):
    cfg = config(services)
    graph = wizard_graph.build(cfg)
    ids = {n["id"] for n in graph["noeuds"]}
    assert ids == set(catalog.resolve_dependencies(services))
    assert all(e["source"] in ids and e["cible"] in ids for e in graph["liens"])
    assert all(e["structure"] or e["etape"] in graph["etapes"] for e in graph["liens"])
    wirer = Wirer(cfg)
    assert graph["etapes"] == [s.name for s in wirer.build_plan()]
    assert len(graph["etapes"]) == len(set(graph["etapes"]))


def test_selection_and_vpn_change_topology_without_running_or_writing(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("A preview must not install or contact Docker")

    monkeypatch.setattr(orchestrator, "install", forbidden)
    monkeypatch.setattr(orchestrator, "preflight", forbidden)
    monkeypatch.setattr(Wirer, "execute", forbidden)
    state = WizardState(tmp_path, demo=True)
    first = state.graph_preview({"services": ["sonarr", "qbittorrent"], "vpn_enabled": False})
    second = state.graph_preview({"services": ["sonarr", "qbittorrent"], "vpn_enabled": True})
    assert first["graph"]["id"] != second["graph"]["id"]
    assert "gluetun" not in {n["id"] for n in first["graph"]["noeuds"]}
    assert "gluetun" in {n["id"] for n in second["graph"]["noeuds"]}
    assert all(not edge["permanent"] for edge in second["graph"]["liens"])
    assert second["graph_results"] == {} and not second["deployed"]
    assert list(tmp_path.iterdir()) == []


def test_flood_only_targets_actual_backend_when_both_clients_are_selected():
    graph = wizard_graph.build(config(["flood", "transmission", "qbittorrent"]))
    edges = [e for e in graph["liens"] if e["source"] == "flood"]
    assert len(edges) == 1 and edges[0]["cible"] == "qbittorrent"
    assert edges[0]["structure"]


def test_one_composite_step_drives_multiple_cables_without_inventing_steps():
    graph = wizard_graph.build(config(["seerr", "sonarr", "radarr", "recyclarr"]))
    seerr = [e for e in graph["liens"] if e["etape"] == "seerr/setup"]
    assert {e["cible"] for e in seerr} == {"sonarr", "radarr", "jellyfin"}
    assert graph["etapes"].count("seerr/setup") == 1


def test_jellyfin_link_is_planned_before_its_generated_key_exists():
    cfg = config(["droppedneedle", "jellyfin"])
    assert not cfg.services["jellyfin"].api_key
    graph = wizard_graph.build(cfg)
    assert any(e["source"] == "droppedneedle" and e["cible"] == "jellyfin" for e in graph["liens"])
    for inst in cfg.services.values():
        for key in ("password", "api_key", "secret_key"):
            secret = getattr(inst, key, None)
            if secret:
                assert secret not in json.dumps(graph)


def test_engine_emits_stable_ids_even_when_labels_differ_and_after_failure(monkeypatch):
    events = []
    wirer = Wirer(config(["sonarr"]))

    def failure():
        raise RuntimeError("test failure")

    monkeypatch.setattr(
        wirer,
        "build_plan",
        lambda: [
            WiringStep("sonarr/one", lambda: StepResult("Libelle traduit", True, "OK")),
            WiringStep("sonarr/two", failure),
        ],
    )
    results = wirer.execute(
        on_start=lambda key: events.append(("start", key)),
        on_step=lambda result: events.append(("end", result.step_id)),
    )
    assert events == [
        ("start", "sonarr/one"),
        ("end", "sonarr/one"),
        ("start", "sonarr/two"),
        ("end", "sonarr/two"),
    ]
    assert results[0].name == "Libelle traduit"
    assert results[1].ok is False and results[1].step_id == "sonarr/two"


def test_snapshot_preserves_failures_warnings_and_active_step_when_logs_are_trimmed(tmp_path):
    state = WizardState(tmp_path, demo=True)
    state.set_status("running")
    state.event("One", "refuse", False, step_id="sonarr/one")
    state.event("Two", "partial", step_id="sonarr/two", warnings=["test not passed"])
    state.event("Three", "running", step_id="sonarr/three", started=True)
    for i in range(1002):
        state.event("waiting", str(i))
    result = state.progress()
    assert not result["graph_results"]["sonarr/one"]["ok"]
    assert result["graph_results"]["sonarr/two"]["warnings"]
    assert result["active_step"] == "sonarr/three"
    assert len(result["events"]) == 1000
    assert not result["deployed"]
    state.event("demarrage-termine", "done")
    assert state.progress()["deployed"]


def test_client_snapshot_rendering_contract():
    import shutil
    import subprocess
    from pathlib import Path

    if not shutil.which('node'):
        pytest.skip('Node is needed for the SVG component state test')
    root = Path(__file__).resolve().parent.parent
    subprocess.run(['node', 'tests/js/wizard_graph.cjs'], cwd=root, check=True,
                   capture_output=True, text=True)
