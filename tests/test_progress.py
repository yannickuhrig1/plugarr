"""Tests de la barre de progression de l'installation.

Le total affiche est calcule d'un cote et les evenements sont emis de l'autre :
les deux peuvent diverger a la premiere etape ajoutee. Ce test les confronte en
deroulant un vrai `install()`, dont seules les parties couteuses (Docker, HTTP,
ecritures) sont neutralisees.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from plugarr import catalog, orchestrator
from plugarr.orchestrator import Progress, expected_events
from plugarr.wiring import StepResult

SELECTIONS = [
    ["sonarr", "radarr", "prowlarr", "transmission", "jellyfin", "recyclarr"],
    ["sonarr", "qbittorrent"],
    list(catalog.CATALOG),
]


def _cfg(tmp_path, services):
    return orchestrator.build_config(
        services=services,
        config_root=str(tmp_path / "config"),
        data_root=str(tmp_path / "data"),
    )


class _FakeCompose:
    def __init__(self, *a, **kw):
        pass

    def config_valid(self):
        return True, "compose valide"

    def stop(self, timeout=300):
        return False, "aucun conteneur"

    def up(self, timeout=1800):
        return True, ""

    def pull_many(self, services, timeout=1800):
        assert services
        return True, ""


@pytest.mark.parametrize("services", SELECTIONS, ids=["defaut", "minimal", "catalogue"])
def test_le_total_annonce_correspond_aux_evenements_emis(tmp_path, monkeypatch, services):
    cfg = _cfg(tmp_path, services)
    steps = [
        StepResult(f"etape {i}", ok=True, detail="") for i in range(orchestrator.planned_links(cfg))
    ]

    monkeypatch.setattr(orchestrator, "create_tree", lambda *a, **kw: [])
    monkeypatch.setattr(orchestrator, "Compose", _FakeCompose)
    monkeypatch.setattr(orchestrator.compose, "write_artifacts", lambda *a, **kw: [])
    monkeypatch.setattr(orchestrator.dashboard, "write", lambda *a, **kw: Path("page.html"))
    monkeypatch.setattr(
        orchestrator,
        "wait_for_arrs",
        lambda c, on_progress=None: [
            on_progress(Progress("attente", sid))
            for sid in catalog.STARTUP_ORDER
            if c.enabled(sid) and catalog.get(sid).api_family == "arr"
        ],
    )
    # `wait_for_download_clients` interroge REELLEMENT les clients par HTTP, avec
    # 180 s d'attente chacun. Non remplace, ce test attendait des services qui
    # n'existent pas : 738 s a lui seul sur les 913 de la suite entiere, soit
    # 81 %. Il emet un evenement par client, comme le vrai.
    monkeypatch.setattr(
        orchestrator,
        "wait_for_download_clients",
        lambda c, on_progress=None: [
            on_progress(Progress("attente", sid))
            for sid in catalog.DOWNLOAD_CLIENTS
            if c.enabled(sid) and not c.services[sid].adopted
        ],
    )
    monkeypatch.setattr(
        orchestrator.Wirer,
        "execute",
        lambda self, on_step=None: [on_step(s) for s in steps] and steps,
    )

    emitted = []
    orchestrator.install(
        cfg, tmp_path, on_progress=lambda p: emitted.append(p), on_step=lambda s: emitted.append(s)
    )

    completed = [event for event in emitted if not getattr(event, "started", False)]
    assert len(completed) == expected_events(cfg), (
        f"la barre annoncerait {expected_events(cfg)} etapes pour {len(completed)} terminees"
    )
    assert any(
        isinstance(event, Progress) and event.phase == "images Docker" and event.started
        for event in emitted
    )
    assert any(
        isinstance(event, Progress) and event.phase == "demarrage" and event.started
        for event in emitted
    )


def test_le_pre_semis_et_le_total_decrivent_les_memes_services(tmp_path):
    """`seed_all` boucle sur `seeded_services` : c'est ce qui empeche la derive."""
    cfg = _cfg(tmp_path, list(catalog.CATALOG))
    seeded = orchestrator.seeded_services(cfg)

    assert seeded == [
        sid
        for sid in catalog.STARTUP_ORDER
        if cfg.enabled(sid)
        and catalog.get(sid).api_family in orchestrator.FAMILLES_PRE_SEMEES
    ]
    # Recyclarr n'a pas de configuration a pre-semer : il ne doit pas etre compte.
    assert "recyclarr" not in seeded
    assert "jellyfin" not in seeded


def test_le_total_grandit_avec_la_selection(tmp_path):
    petit = expected_events(_cfg(tmp_path, ["sonarr"]))
    grand = expected_events(_cfg(tmp_path, list(catalog.CATALOG)))

    assert 0 < petit < grand


# ----------------------------------------------------------------- assistant


@pytest.mark.asyncio
async def test_la_barre_du_tui_ne_depasse_jamais_son_total(tmp_path, monkeypatch):
    """Le total est une estimation. Une barre a 110 % ferait douter du reste."""
    from textual.widgets import ProgressBar

    from plugarr.tui.app import PlugArrApp
    from plugarr.tui.screens import InstallScreen

    # monkeypatch, pas une affectation de classe : sans annulation, l'ecran
    # resterait inerte pour tous les tests suivants de la meme session.
    monkeypatch.setattr(InstallScreen, "run_install", lambda self: None)
    app = PlugArrApp(project_dir=tmp_path)
    async with app.run_test() as pilot:
        app.selection = ["sonarr"]
        app.push_screen(InstallScreen())
        await pilot.pause()
        screen = app.screen

        screen._set_total(3)
        for _ in range(10):
            screen._advance()
        bar = screen.query_one("#install-progress", ProgressBar)

        assert bar.progress == 3

        screen._set_total(5)
        screen._advance()
        screen._complete()

        assert bar.progress == 5, "une barre figee avant la fin se lit comme un echec"


def test_une_coupure_du_registre_ne_fait_plus_echouer_l_installation(monkeypatch, tmp_path):
    """Releve sur un runner GitHub : « read: connection reset by peer » chez
    lscr.io, en plein telechargement des images. Sans nouvelle tentative, UNE
    coupure faisait echouer toute l'installation. `pull` est idempotent, donc
    reessayer ne coute que l'attente."""
    import subprocess

    from plugarr import runner

    reponses = [
        subprocess.CompletedProcess([], 1, "", "read: connection reset by peer"),
        subprocess.CompletedProcess([], 0, "", "sonarr Pulled"),
    ]
    appels = []
    monkeypatch.setattr(runner, "_run", lambda *a, **k: (appels.append(a), reponses.pop(0))[1])
    monkeypatch.setattr(runner.time, "sleep", lambda _s: None)

    ok, _message = runner.Compose(tmp_path, "essai").pull_many(["sonarr"])

    assert ok, "une coupure isolee a fait echouer le telechargement"
    assert len(appels) == 2


def test_une_erreur_definitive_du_registre_finit_par_etre_rapportee(monkeypatch, tmp_path):
    """Reessayer ne doit pas masquer une vraie erreur : un tag inconnu echoue a
    chaque tentative, et son message doit remonter tel quel."""
    import subprocess

    from plugarr import runner

    appels = []
    monkeypatch.setattr(
        runner,
        "_run",
        lambda *a, **k: (
            appels.append(a),
            subprocess.CompletedProcess([], 1, "", "manifest unknown"),
        )[1],
    )
    monkeypatch.setattr(runner.time, "sleep", lambda _s: None)

    ok, message = runner.Compose(tmp_path, "essai").pull_many(["sonarr"])

    assert not ok
    assert "manifest unknown" in message
    assert len(appels) == runner.PULL_TENTATIVES
