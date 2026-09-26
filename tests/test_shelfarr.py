"""Integration de Shelfarr et de son compagnon Libation.

Le contrat teste ici vient du compose officiel Shelfarr 2026.09.18.1. Le
compagnon n'est pas une application a cocher : il accompagne Shelfarr, ne
publie aucun port et reste inactif tant que l'administrateur n'active pas la
sauvegarde Audible.
"""

from __future__ import annotations

from plugarr import catalog, compose, connections, orchestrator, sauvegarde


def _cfg(*services: str):
    return orchestrator.build_config(
        services=list(services or ("shelfarr",)),
        config_root="/c",
        data_root="/d",
    )


def test_shelfarr_est_choisissable_et_libation_reste_interne():
    choisissables = {spec.id for spec in catalog.selectable()}

    assert "shelfarr" in choisissables
    assert "shelfarr-libation" not in choisissables


def test_les_deux_images_sont_epinglees_a_la_meme_version_et_au_digest():
    shelfarr = catalog.get("shelfarr").image
    libation = catalog.get("shelfarr-libation").image

    assert ":2026.09.18.1@sha256:" in shelfarr
    assert ":2026.09.18.1@sha256:" in libation
    assert ":latest" not in shelfarr + libation


def test_une_selection_shelfarr_tire_une_pile_complete():
    services = set(_cfg().services)

    assert {
        "shelfarr",
        "shelfarr-libation",
        "prowlarr",
        "audiobookshelf",
        "qbittorrent",
    } <= services


def test_shelfarr_publie_5056_et_reutilise_toute_l_arborescence_plugarr():
    block = compose.build_compose(_cfg())["services"]["shelfarr"]

    assert block["ports"] == ["5056:80"]
    assert block["environment"] == {
        "SOLID_QUEUE_IN_PUMA": "1",
        "SHELFARR_LIBATION_URL": "http://shelfarr-libation:8080",
        "SHELFARR_LIBATION_TOKEN_FILE": "/run/shelfarr-libation/token",
        "SHELFARR_LIBATION_IMPORT_ROOT": "/imports/libation",
        "PUID": "1000",
        "PGID": "1000",
        "CHOWN_ON_START": "auto",
        "TZ": "Etc/UTC",
    }
    assert "${CONFIG_ROOT}/shelfarr:/rails/storage" in block["volumes"]
    assert "${DATA_ROOT}:/data" in block["volumes"]
    assert "${DATA_ROOT}:/downloads" in block["volumes"]
    assert "${DATA_ROOT}/media/books:/ebooks" in block["volumes"]
    assert "${DATA_ROOT}/media/audiobooks:/audiobooks" in block["volumes"]
    assert "shelfarr-libation-books:/imports/libation:ro" in block["volumes"]
    assert "shelfarr-libation-control:/run/shelfarr-libation:ro" in block["volumes"]
    assert block["healthcheck"]["test"] == ["CMD", "curl", "-f", "http://localhost:80/up"]


def test_libation_ne_publie_aucun_port_et_garde_son_etat_prive():
    doc = compose.build_compose(_cfg())
    block = doc["services"]["shelfarr-libation"]

    assert "ports" not in block
    assert block["expose"] == ["8080"]
    assert set(doc["volumes"]) >= {
        "shelfarr-libation-config",
        "shelfarr-libation-books",
        "shelfarr-libation-control",
    }
    assert set(block["volumes"]) == {
        "shelfarr-libation-config:/config",
        "shelfarr-libation-books:/data",
        "shelfarr-libation-control:/control",
    }
    assert block["environment"]["COMPANION_TOKEN_FILE"] == "/control/token"


def test_les_volumes_libation_entrent_dans_sauvegarde(monkeypatch):
    cfg = _cfg()
    attendus = [
        "plugarr_shelfarr-libation-config",
        "plugarr_shelfarr-libation-books",
        "plugarr_shelfarr-libation-control",
    ]

    monkeypatch.setattr(sauvegarde, "volume_exists", lambda _nom: True)

    assert orchestrator.volumes_nommes(cfg, "shelfarr-libation") == attendus
    assert sauvegarde.volumes_du_projet(cfg) == attendus


def test_la_remise_a_zero_supprime_les_trois_volumes_libation(monkeypatch):
    cfg = _cfg()
    supprimes = []

    monkeypatch.setattr(orchestrator, "volume_exists", lambda _nom: True)
    monkeypatch.setattr(
        orchestrator,
        "remove_volume",
        lambda nom: (supprimes.append(nom), (True, ""))[1],
    )

    orchestrator.reset_configs(cfg, ["shelfarr-libation"])

    assert supprimes == [
        "plugarr_shelfarr-libation-config",
        "plugarr_shelfarr-libation-books",
        "plugarr_shelfarr-libation-control",
    ]


def test_la_carte_montre_les_relations_sans_les_pretendre_verifiees():
    topo = connections.topology(_cfg())
    liens = {
        (edge["source"], edge["target"], edge["kind"]): edge
        for edge in topo["connections"]
    }

    for cle in (
        ("shelfarr", "prowlarr", "indexers"),
        ("shelfarr", "qbittorrent", "download"),
        ("shelfarr", "audiobookshelf", "library"),
        ("shelfarr", "shelfarr-libation", "dependency"),
    ):
        assert cle in liens
        assert liens[cle]["state"] == "non verifiee"
        assert not liens[cle]["testable"]
