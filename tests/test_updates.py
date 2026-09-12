"""Tests de la detection de mises a jour. Aucun appel reseau ni Docker."""

from __future__ import annotations

import pytest

from plugarr import updates


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("4.0.19", (4, 0, 19)),
        ("v1.85.0", (1, 85, 0)),
        ("10.11.11", (10, 11, 11)),
        ("3.41", (3, 41)),
        ("build-522", (522,)),
        ("latest", None),
        ("develop", None),
        ("version-3.0.4.999", None),
        ("4.0.19-develop", None),
        ("5.2.3_v2.0.14-ls474", None),
        ("", None),
    ],
)
def test_version_parsing(tag, expected):
    assert updates.parse_version(tag) == expected


def test_versions_compare_numerically_not_alphabetically():
    """4.9.5 vient AVANT 4.16.1, ce que le tri alphabetique inverse."""
    assert updates.parse_version("4.9.5") < updates.parse_version("4.16.1")
    assert updates.parse_version("v1.85.0") > updates.parse_version("v1.9.0")
    assert updates.parse_version("build-523") > updates.parse_version("build-99")


def test_only_tags_of_the_same_shape_are_compared():
    """Un depot melange v1.85.0, 1.85 et version-1.85.0. Comparer entre
    conventions produirait des propositions absurdes."""
    assert updates._same_shape("v1.86.0", "v1.85.0")
    assert not updates._same_shape("1.86.0", "v1.85.0")
    assert not updates._same_shape("1.86", "1.85.0")
    assert updates._same_shape("build-523", "build-522")
    assert not updates._same_shape("523", "build-522")


def test_silo_builds_are_proposed_in_numeric_order(monkeypatch):
    monkeypatch.setattr(
        updates,
        "list_tags",
        lambda ref, timeout: (["build-99", "build-522", "build-523", "latest"], None),
    )

    newer, problem = updates.newer_tags("ghcr.io/silo-server/silo-server:build-522")

    assert problem is None
    assert newer == ["build-523"]


def test_unstable_tags_are_never_proposed(monkeypatch):
    monkeypatch.setattr(
        updates,
        "list_tags",
        lambda ref, timeout: (["4.0.20", "4.0.21-beta", "4.0.99-develop", "latest"], None),
    )
    newer, problem = updates.newer_tags("x/y:4.0.19")
    assert problem is None
    assert newer == ["4.0.20"]


def test_someone_already_on_develop_keeps_getting_develop(monkeypatch):
    """Suivre une branche instable est un choix : on ne le contrarie pas."""
    monkeypatch.setattr(
        updates, "list_tags", lambda ref, timeout: (["4.0.20-develop", "4.0.21-develop"], None)
    )
    newer, _p = updates.newer_tags("x/y:4.0.19-develop")
    # Le tag deploye n'est pas une version comparable : on le dit plutot que de
    # proposer n'importe quoi.
    assert newer == []


def test_only_strictly_newer_tags_are_proposed(monkeypatch):
    monkeypatch.setattr(
        updates, "list_tags", lambda ref, timeout: (["4.0.18", "4.0.19", "4.0.20"], None)
    )
    newer, _p = updates.newer_tags("x/y:4.0.19")
    assert newer == ["4.0.20"]


def test_a_registry_problem_is_reported_not_hidden(monkeypatch):
    """Sans cela, « aucune mise a jour » voudrait dire « je n'ai pas pu verifier »."""
    monkeypatch.setattr(updates, "list_tags", lambda ref, timeout: ([], "registre injoignable"))
    newer, problem = updates.newer_tags("x/y:4.0.19")
    assert newer == []
    assert problem == "registre injoignable"


def test_an_uncomparable_deployed_tag_is_reported():
    newer, problem = updates.newer_tags("x/y:latest")
    assert newer == []
    assert "comparable" in problem


def test_the_next_page_link_is_read():
    header = '</v2/linuxserver/sonarr/tags/list?last=abc&n=200>; rel="next"'
    assert updates._next_page(header) == "/v2/linuxserver/sonarr/tags/list?last=abc&n=200"
    assert updates._next_page("") is None


def test_update_info_reports_both_kinds():
    rebuilt = updates.UpdateInfo(service="s", image="i:1.0", current_tag="1.0", rebuilt=True)
    newer = updates.UpdateInfo(service="s", image="i:1.0", current_tag="1.0", latest_tag="1.1")
    nothing = updates.UpdateInfo(service="s", image="i:1.0", current_tag="1.0")
    assert rebuilt.has_update and newer.has_update
    assert not nothing.has_update


def test_adopted_services_are_never_offered_an_update():
    """Ces conteneurs ne nous appartiennent pas : proposer de les recreer
    reviendrait a toucher a la stack de quelqu'un d'autre."""
    from plugarr import adopt
    from plugarr.discovery import Found

    entry = Found(
        service_id="sonarr", container="mon-sonarr", image="lscr.io/linuxserver/sonarr:4.0.19",
        host_port=8989, config_dir="/c", api_key="a" * 32,
    )
    cfg = adopt.config_from_plan(
        adopt.build_plan([entry]), data_root="/d", config_root="/c"
    )
    assert updates.check(cfg, check_tags=False) == []
