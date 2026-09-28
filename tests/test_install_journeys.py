"""Les parcours ne changent que la selection initiale du catalogue."""

from __future__ import annotations

import pytest

from plugarr import catalog, orchestrator


@pytest.mark.parametrize("journey", catalog.INSTALL_JOURNEYS)
def test_journey_services_are_selectable_and_config_is_exact(journey):
    selected = list(catalog.INSTALL_JOURNEYS[journey])
    selectable = {spec.id for spec in catalog.selectable()}
    assert set(selected) <= selectable
    assert len(selected) == len(set(selected))

    resolved = catalog.resolve_dependencies(selected)
    cfg = orchestrator.build_config(services=selected, config_root="/tmp/plugarr-config", data_root="/tmp/plugarr-data")
    assert list(cfg.services) == resolved
    assert set(cfg.services) - set(selected) == set(resolved) - set(selected)


def test_family_journey_announces_only_its_catalog_dependency():
    selected = list(catalog.INSTALL_JOURNEYS["family"])
    assert set(catalog.resolve_dependencies(selected)) - set(selected) == {"jellyfin"}
    assert "jellyfin" in {spec.id for spec in catalog.selectable()}


def test_custom_starts_empty_but_accepts_each_service_and_dependency():
    assert catalog.INSTALL_JOURNEYS["custom"] == ()
    for service in catalog.selectable():
        resolved = catalog.resolve_dependencies([service.id])
        assert service.id in resolved
        assert set(resolved) <= set(catalog.CATALOG)


def test_existing_default_cli_selection_is_unchanged():
    assert catalog.INSTALL_JOURNEYS["films_series"] == catalog.DEFAULT_SELECTION
