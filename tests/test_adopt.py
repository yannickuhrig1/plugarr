"""Tests de la detection et de la reprise d'une stack existante.

Aucun appel a Docker : `scan` est alimente par des `Found` construits a la main,
dont la forme reproduit ce qu'a renvoye `docker inspect` en conditions reelles.
"""

from __future__ import annotations

import json

import pytest
import yaml

from plugarr import adopt, catalog, discovery, report
from plugarr.discovery import Found
from plugarr.models import StackConfig


def found(service_id="sonarr", container="mon-sonarr", port=8991, key="a" * 32, **kw):
    return Found(
        service_id=service_id,
        container=container,
        image=kw.get("image", f"lscr.io/linuxserver/{service_id}:latest"),
        host_port=port,
        config_dir=kw.get("config_dir", "/opt/appdata/sonarr"),
        api_key=key,
        url_base=kw.get("url_base", ""),
        problems=kw.get("problems", []),
    )


# ------------------------------------------------------- reconnaissance d'image


@pytest.mark.parametrize(
    ("image", "expected"),
    [
        ("lscr.io/linuxserver/sonarr:4.0.19", "sonarr"),
        ("ghcr.io/onedr0p/sonarr:4", "sonarr"),
        ("hotio/radarr", "radarr"),
        ("linuxserver/prowlarr", "prowlarr"),
        ("lscr.io/linuxserver/qbittorrent:5.2.3", "qbittorrent"),
        # Les pieges : ces images contiennent "arr" mais n'en sont pas.
        ("ghcr.io/onedr0p/exportarr:v2", None),
        ("recyclarr/recyclarr:latest", None),
        ("ghcr.io/raydak-labs/configarr", None),
        # Et ceux qui n'ont rien a voir.
        ("alpine:3.21", None),
        ("seerr/seerr:v3.4.1", None),
        ("", None),
    ],
)
def test_image_identification(image, expected):
    assert discovery.identify(image) == expected


def test_identification_ignores_the_registry_and_the_tag():
    """Comparer la chaine entiere ferait passer `ghcr.io/x/exportarr` pour un *arr."""
    assert discovery.identify("un.registre.prive/equipe/sonarr:v4.0.19-custom") == "sonarr"


# --------------------------------------------------------------- utilisabilite


def test_an_arr_without_an_api_key_is_not_usable():
    assert not found(key=None).usable


def test_a_service_without_a_published_port_is_not_usable():
    """Sans port publie, plugarr ne peut pas le joindre depuis l'hote."""
    assert not found(port=None).usable


def test_a_download_client_needs_no_api_key():
    assert found(service_id="qbittorrent", key=None, port=8080).usable


def test_scan_follows_qbittorrent_port_published_by_gluetun(monkeypatch, tmp_path):
    """A real Unraid setup publishes qBittorrent's WebUI on Gluetun, not qBit."""
    settings = tmp_path / "qBittorrent" / "qBittorrent.conf"
    settings.parent.mkdir()
    settings.write_text("[Preferences]\nWebUI\\Port=8090\n", encoding="utf-8")
    gluetun_id = "3c283fd3cb365b03a3b7f44d2af0ba9e1c9c76e05999fb0f7aa48de5200e1894"
    containers = [
        {
            "Id": "qbittorrent-id",
            "Name": "/qbittorrent",
            "Config": {"Image": "lscr.io/linuxserver/qbittorrent:latest"},
            "HostConfig": {"NetworkMode": f"container:{gluetun_id}"},
            "NetworkSettings": {"Ports": {}},
            "Mounts": [{"Destination": "/config", "Source": str(tmp_path)}],
        },
        {
            "Id": gluetun_id,
            "Name": "/gluetun",
            "Config": {"Image": "qmcgaw/gluetun:v3.41.3"},
            "HostConfig": {"NetworkMode": "bridge"},
            "NetworkSettings": {"Ports": {
                "8090/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8090"}],
            }},
            "Mounts": [],
        },
    ]
    monkeypatch.setattr(
        discovery, "_docker",
        lambda *args, **_kw: "qbittorrent-id\n" + gluetun_id
        if args[0] == "ps" else json.dumps(containers),
    )

    entries = discovery.scan()

    assert len(entries) == 1
    assert entries[0].container == "qbittorrent"
    assert entries[0].host_port == 8090
    assert entries[0].network_owner == "gluetun"
    assert entries[0].usable
    assert adopt.build_plan(entries).chosen["qbittorrent"] is entries[0]


def test_qbittorrent_shared_network_owner_must_be_unambiguous():
    qbittorrent = {"HostConfig": {"NetworkMode": "container:abc"}}
    owners = [{"Id": "abc-one"}, {"Id": "abc-two"}]
    assert discovery._network_owner(qbittorrent, [qbittorrent, *owners]) is None


# ------------------------------------------------------------------- doublons


def test_two_sonarr_are_reported_as_ambiguous():
    """Cas courant et legitime : un Sonarr pour les series, un pour l'animation.
    plugarr ne peut pas deviner lequel recevra les indexeurs."""
    entries = [found(container="sonarr"), found(container="sonarr-anime", port=8992)]
    assert set(discovery.duplicates(entries)) == {"sonarr"}

    plan = adopt.build_plan(entries)
    assert not plan.ready
    assert "sonarr" in plan.ambiguous
    assert plan.chosen == {}


def test_a_pick_lifts_the_ambiguity():
    entries = [found(container="sonarr"), found(container="sonarr-anime", port=8992)]
    plan = adopt.build_plan(entries, {"sonarr": "sonarr-anime"})
    assert plan.ready
    assert plan.chosen["sonarr"].container == "sonarr-anime"
    assert [c.container for c, _ in plan.skipped] == ["sonarr"]


def test_a_pick_naming_an_unknown_container_stays_ambiguous():
    """Se tromper de nom ne doit pas cabler silencieusement le mauvais service."""
    entries = [found(container="sonarr"), found(container="sonarr-anime", port=8992)]
    plan = adopt.build_plan(entries, {"sonarr": "sonarr-inexistant"})
    assert not plan.ready


def test_a_single_instance_needs_no_pick():
    assert adopt.build_plan([found()]).ready


# ---------------------------------------------------------------- exclusions


def test_plugarr_does_not_adopt_its_own_containers():
    """Inutile de proposer d'adopter la stack qu'on vient d'installer."""
    mine = found(container="plugarr-sonarr")
    mine.managed_by_us = True
    assert discovery.looks_like_plugarr(mine)
    plan = adopt.build_plan([mine])
    assert plan.chosen == {}
    assert plan.skipped[0][1] == "deja gere par plugarr"


@pytest.mark.parametrize("name", ["mon-sonarr", "media-sonarr", "sonarr", "plugarr-sonarr"])
def test_a_foreign_container_is_never_mistaken_for_ours(name):
    """Un nom ne prouve rien. Une heuristique de nom sautait "mon-sonarr" en
    silence : plugarr ignorait un conteneur qui ne lui appartenait pas."""
    assert not discovery.looks_like_plugarr(found(container=name))


def test_an_unusable_service_is_skipped_with_its_reason():
    entry = found(key=None, problems=["le volume /config n'est pas monte"])
    plan = adopt.build_plan([entry])
    assert plan.chosen == {}
    assert "config" in plan.skipped[0][1]


# ------------------------------------------------------------------ config


def test_adopted_services_are_marked_as_such():
    cfg = adopt.config_from_plan(
        adopt.build_plan([found()]), data_root="/srv/d", config_root="/opt/c"
    )
    inst = cfg.services["sonarr"]
    assert inst.adopted
    assert inst.container == "mon-sonarr"
    assert inst.api_key == "a" * 32


def test_the_real_published_port_is_kept_not_the_catalog_default():
    """Une stack existante n'utilise pas forcement les ports par defaut."""
    cfg = adopt.config_from_plan(
        adopt.build_plan([found(port=18989)]), data_root="/srv/d", config_root="/opt/c"
    )
    assert cfg.services["sonarr"].host_port == 18989


def test_a_url_base_is_carried_over():
    """Derriere un reverse proxy, le service n'est pas servi a la racine."""
    cfg = adopt.config_from_plan(
        adopt.build_plan([found(url_base="sonarr")]), data_root="/srv/d", config_root="/opt/c"
    )
    assert cfg.services["sonarr"].url("nas") == "http://nas:8991/sonarr"


# --------------------------------------------------- URL vues d'un conteneur


def test_an_adopted_service_is_reached_through_the_host():
    """Les conteneurs existants vivent sur leurs propres reseaux : le nom de
    service compose n'y resout pas. Verifie en conditions reelles - Prowlarr
    repondait "cannot connect to Sonarr" sur une URL en nom de service."""
    cfg = adopt.config_from_plan(
        adopt.build_plan([found()]), data_root="/srv/d", config_root="/opt/c", host="192.168.1.10"
    )
    spec = catalog.get("sonarr")
    assert cfg.services["sonarr"].internal_url(spec, cfg.host) == "http://192.168.1.10:8991"


def test_a_managed_service_keeps_the_compose_service_name():
    from plugarr import orchestrator

    cfg = orchestrator.build_config(services=["sonarr"], data_root="/d", config_root="/c")
    spec = catalog.get("sonarr")
    assert cfg.services["sonarr"].internal_url(spec, cfg.host) == "http://sonarr:8989"


# --------------------------------------------------------------- persistance


def test_adopting_writes_stack_yml_but_never_a_compose_file(tmp_path):
    """Generer un docker-compose.yml donnerait a `uninstall` le pouvoir de
    detruire une stack qui n'appartient pas a plugarr."""
    cfg = adopt.config_from_plan(
        adopt.build_plan([found()]), data_root="/srv/d", config_root="/opt/c"
    )
    adopt.write_stack(cfg, tmp_path)
    assert (tmp_path / "stack.yml").exists()
    assert not (tmp_path / "docker-compose.yml").exists()
    assert not (tmp_path / ".env").exists()


def test_the_written_stack_says_it_is_adopted(tmp_path):
    cfg = adopt.config_from_plan(
        adopt.build_plan([found()]), data_root="/srv/d", config_root="/opt/c"
    )
    path = adopt.write_stack(cfg, tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "ADOPTEE" in text
    reloaded = StackConfig.model_validate(yaml.safe_load(text))
    assert reloaded.services["sonarr"].adopted


# ------------------------------------------------------------- diagnostics


def test_a_stack_without_a_download_client_is_flagged():
    cfg = adopt.config_from_plan(
        adopt.build_plan([found()]), data_root="/srv/d", config_root="/opt/c"
    )
    notes = adopt.missing_for_wiring(cfg)
    assert any("client de telechargement" in n for n in notes)


def test_prowlarr_alone_is_flagged():
    entry = found(service_id="prowlarr", container="prowlarr", port=9696)
    cfg = adopt.config_from_plan(
        adopt.build_plan([entry]), data_root="/srv/d", config_root="/opt/c"
    )
    assert any("Prowlarr est seul" in n for n in adopt.missing_for_wiring(cfg))


def test_a_complete_stack_raises_no_note():
    entries = [
        found(),
        found(service_id="prowlarr", container="prowlarr", port=9696),
        found(service_id="qbittorrent", container="qbit", port=8080, key=None),
    ]
    cfg = adopt.config_from_plan(
        adopt.build_plan(entries), data_root="/srv/d", config_root="/opt/c"
    )
    assert adopt.missing_for_wiring(cfg) == []


def test_keys_are_masked_for_display():
    assert discovery.mask_key("0123456789abcdef") == "0123…cdef"
    assert discovery.mask_key(None) == "-"


def test_adoption_report_does_not_claim_hardlinks_from_mismatched_mounts():
    arr = found()
    arr.data_mounts = {"/data": "/volume1/media"}
    client = found(service_id="qbittorrent", key=None, port=8080)
    client.data_mounts = {"/downloads": "/volume2/torrents"}
    plan = adopt.build_plan([arr, client])

    notes = adopt.compatibility_notes(plan, "/volume1/media")

    assert any("qbittorrent" in note and "hardlinks" in note for note in notes)
    assert not any("sonarr" in note for note in notes)


def test_adoption_report_recognises_shared_downloads_without_claiming_hardlinks():
    source = "/mnt/user/medias/downloads"
    arr = found()
    arr.data_mounts = {"/downloads": source, "/media": "/mnt/user/medias"}
    client = found(service_id="qbittorrent", key=None, port=8090)
    client.data_mounts = {"/downloads": source}

    notes = adopt.compatibility_notes(adopt.build_plan([arr, client]), "/mnt/user/medias")

    assert len(notes) == 1
    assert "/downloads commun" in notes[0]
    assert source in notes[0]
    assert "hardlinks restent a verifier" in notes[0]
    assert "pas de montage /data commun" not in notes[0]


def test_shared_downloads_outside_declared_data_root_are_flagged():
    arr = found()
    arr.data_mounts = {"/downloads": "/volume2/downloads"}
    client = found(service_id="qbittorrent", key=None, port=8090)
    client.data_mounts = {"/downloads": "/volume2/downloads"}

    notes = adopt.compatibility_notes(adopt.build_plan([arr, client]), "/volume1/media")

    assert any("hors de la racine declaree" in note for note in notes)


def test_adopt_summary_reports_vpn_topology_without_claiming_egress(monkeypatch):
    client = found(service_id="qbittorrent", key=None, port=8090)
    client.network_owner = "gluetun"
    plan = adopt.build_plan([client])
    cfg = adopt.config_from_plan(plan, data_root="/srv/data", config_root="/srv/config")
    monkeypatch.setattr(report, "console", report._ConsoleTraduisante(width=180))

    with report.console.capture() as captured:
        report.print_summary(cfg, adopted_sources=plan.chosen)
    output = captured.get()

    assert "partage le reseau du conteneur gluetun" in output
    assert "n'ont pas ete verifies" in output
    assert "sortira sur l'adresse IP publique" not in output


def test_adopt_summary_does_not_infer_a_vpn_from_unknown_topology(monkeypatch):
    client = found(service_id="qbittorrent", key=None, port=8090)
    plan = adopt.build_plan([client])
    cfg = adopt.config_from_plan(plan, data_root="/srv/data", config_root="/srv/config")
    monkeypatch.setattr(report, "console", report._ConsoleTraduisante(width=180))

    with report.console.capture() as captured:
        report.print_summary(cfg, adopted_sources=plan.chosen)
    output = captured.get()

    assert "n'ont pas ete verifies" in output
    assert "sortira sur l'adresse IP publique" not in output


def test_api_inventory_reports_version_without_exposing_key(monkeypatch):
    cfg = adopt.config_from_plan(
        adopt.build_plan([found()]), data_root="/srv/d", config_root="/opt/c",
        host="192.168.1.10",
    )

    class FakeClient:
        def __init__(self, url, key, **kwargs):
            assert url == "http://192.168.1.10:8991"
            assert key == "a" * 32

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @property
        def version(self):
            return "4.0.1"

    monkeypatch.setattr(adopt, "ArrClient", FakeClient)
    result = adopt.api_inventory(cfg)
    assert result == [{"service": "sonarr", "ok": True, "version": "4.0.1"}]
    assert "a" * 32 not in str(result)


def test_api_inventory_does_not_echo_failure_details(monkeypatch):
    cfg = adopt.config_from_plan(
        adopt.build_plan([found()]), data_root="/srv/d", config_root="/opt/c"
    )

    class FailedClient:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("secret in backend error")

    monkeypatch.setattr(adopt, "ArrClient", FailedClient)
    result = adopt.api_inventory(cfg)
    assert result == [{"service": "sonarr", "ok": False, "version": ""}]
    assert "secret" not in str(result)


def test_dry_run_does_not_write_stack_or_apply_links(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    from plugarr import cli

    monkeypatch.setattr(cli.discovery, "scan", lambda: [found()])
    monkeypatch.setattr(
        cli.adopt_mod, "api_inventory",
        lambda _cfg: [{"service": "sonarr", "ok": True, "version": "4.0.1"}],
    )
    project = tmp_path / "project"
    result = CliRunner().invoke(
        cli.app,
        [
            "adopt", "--host", "192.168.1.10", "--data-root", "/srv/data",
            "--config-root", "/srv/config", "--project-dir", str(project),
            "--dry-run", "--only", "sonarr/rootfolder/tv",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "sonarr/rootfolder/tv" in result.output
    assert "sonarr 4.0.1" in result.output
    assert not project.exists()


def test_adopt_summary_shows_discovered_image_and_config(monkeypatch):
    entry = found(image="sonarr:smoke", config_dir="/opt/sonarr-existing")
    plan = adopt.build_plan([entry])
    cfg = adopt.config_from_plan(
        plan, data_root="/srv/data", config_root="/srv/config"
    )
    monkeypatch.setattr(report, "console", report._ConsoleTraduisante(width=180))

    with report.console.capture() as captured:
        report.print_summary(cfg, adopted_sources=plan.chosen)
    output = captured.get()

    assert "sonarr:smoke" in output
    assert "/opt/sonarr-existing" in output
    assert catalog.get("sonarr").image not in output
    assert "/srv/config/sonarr" not in output
    assert "montages reels dans l'inventaire" in output
    assert "monte sur /data dans TOUS" not in output


def test_adopt_refuses_to_overwrite_an_existing_stack(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    from plugarr import cli

    monkeypatch.setattr(cli.discovery, "scan", lambda: [found()])
    stack = tmp_path / "stack.yml"
    stack.write_text("existing user content", encoding="utf-8")
    result = CliRunner().invoke(
        cli.app,
        [
            "adopt", "--host", "192.168.1.10", "--data-root", "/srv/data",
            "--config-root", "/srv/config", "--project-dir", str(tmp_path), "--yes",
        ],
    )

    assert result.exit_code == 1, result.output
    assert stack.read_text(encoding="utf-8") == "existing user content"


@pytest.mark.parametrize("apply", [False, True])
def test_adopt_does_not_write_or_wire_when_api_check_fails(monkeypatch, tmp_path, apply):
    from typer.testing import CliRunner

    from plugarr import cli

    monkeypatch.setattr(cli.discovery, "scan", lambda: [found()])
    monkeypatch.setattr(
        cli.adopt_mod, "api_inventory",
        lambda _cfg: [{"service": "sonarr", "ok": False, "version": ""}],
    )
    project = tmp_path / "project"
    result = CliRunner().invoke(
        cli.app,
        [
            "adopt", "--host", "192.168.1.10", "--data-root", "/srv/data",
            "--config-root", "/srv/config", "--project-dir", str(project),
            "--yes" if apply else "--dry-run",
        ],
    )

    assert result.exit_code == 1, result.output
    assert "Adoption interrompue" in result.output
    assert not project.exists()
