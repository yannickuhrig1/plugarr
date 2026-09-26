"""Tests du coeur : ils tournent sans Docker et sans reseau."""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
import yaml

from plugarr import catalog, compose, seed
from plugarr.clients.arr import ArrClient
from plugarr.layout import hardlink_supported
from plugarr.models import PlatformProfile, ServiceInstance, StackConfig


def make_cfg(tmp_path, services=("prowlarr", "sonarr", "radarr", "transmission", "jellyfin")):
    cfg = StackConfig(
        config_root=str(tmp_path / "config"),
        data_root=str(tmp_path / "data"),
        platform=PlatformProfile.GENERIC_LINUX,
    )
    for sid in catalog.resolve_dependencies(list(services)):
        spec = catalog.get(sid)
        cfg.services[sid] = ServiceInstance(
            spec_id=sid,
            host_port=spec.default_host_port,
            api_key=seed.generate_api_key() if spec.api_family == "arr" else None,
            username="plugarr",
            password="pw",
        )
    return cfg


# ------------------------------------------------------------------- catalogue


def test_startup_order_places_prowlarr_after_the_arrs():
    order = catalog.STARTUP_ORDER
    assert order.index("prowlarr") > order.index("sonarr")
    assert order.index("prowlarr") > order.index("radarr")


def test_every_image_tag_is_pinned():
    """Un tag flottant rend le cablage non reproductible."""
    for spec in catalog.CATALOG.values():
        tag = spec.image.rsplit(":", 1)[-1]
        assert tag not in ("latest", "develop", "nightly"), spec.id


def test_unknown_service_error_lists_known_ones():
    with pytest.raises(KeyError, match="sonarr"):
        catalog.get("sonaar")


# ---------------------------------------------------------------------- seeding


def test_arr_config_enforces_forms_auth():
    """Verifie contre Sonarr 4.0.19.2979 : Forms + Enabled protege l'UI web."""
    xml = ET.fromstring(
        seed.render_arr_config(
            api_key="a" * 32, port=8989, instance_name="Sonarr", username="u", password="p"
        )
    )
    assert xml.findtext("AuthenticationMethod") == "Forms"
    assert xml.findtext("AuthenticationRequired") == "Enabled"
    assert xml.findtext("ApiKey") == "a" * 32


def test_seed_arr_is_idempotent_and_adopts_existing_key(tmp_path):
    d = tmp_path / "sonarr"
    first, written = seed.seed_arr(
        d, api_key="b" * 32, port=8989, instance_name="Sonarr", username="u", password="p"
    )
    assert written and first == "b" * 32

    second, written_again = seed.seed_arr(
        d, api_key="c" * 32, port=8989, instance_name="Sonarr", username="u", password="p"
    )
    # La cle existante fait autorite : on ne l'ecrase jamais.
    assert not written_again
    assert second == "b" * 32


def test_transmission_settings_allow_container_to_container_rpc():
    s = seed.render_transmission_settings(rpc_username="u", rpc_password="p")
    # Sans ces deux reglages, Sonarr/Radarr sont refuses par Transmission.
    assert s["rpc-whitelist-enabled"] is False
    assert s["rpc-host-whitelist-enabled"] is False
    assert s["download-dir"].startswith("/data/")
    assert s["incomplete-dir"].startswith("/data/")


def test_seed_transmission_preserve_les_reglages_et_realigne_les_identifiants(tmp_path):
    """Les reglages de l'utilisateur restent, les identifiants sont imposes.

    Garder l'ancien mot de passe RPC laissait un rapport mensonger et un cablage
    en echec apres une reinstallation.
    """
    d = tmp_path / "transmission"
    d.mkdir()
    (d / "settings.json").write_text(json.dumps({"custom": True, "rpc-password": "ancien"}))

    seed.seed_transmission(d, rpc_username="u", rpc_password="Nouveau2@")
    reglages = json.loads((d / "settings.json").read_text())

    assert reglages["custom"] is True
    assert reglages["rpc-username"] == "u"
    assert reglages["rpc-password"] == "Nouveau2@"


# ---------------------------------------------------------------------- compose


def test_all_services_share_one_data_mount(tmp_path):
    """LE point critique : un seul montage /data, sinon les hardlinks echouent."""
    doc = compose.build_compose(make_cfg(tmp_path))
    for sid, block in doc["services"].items():
        mounts = [v.split(":")[-1] for v in block["volumes"]]
        assert "/data" in mounts, f"{sid} n'a pas le montage /data"
        assert not any(m.startswith("/downloads") or m == "/media" for m in mounts), sid


def test_compose_is_valid_yaml_and_pins_images(tmp_path):
    doc = yaml.safe_load(compose.render_compose(make_cfg(tmp_path)))
    assert set(doc["services"]) == {"transmission", "sonarr", "radarr", "prowlarr", "jellyfin"}
    for block in doc["services"].values():
        assert ":" in block["image"]


def test_env_contains_secrets_and_compose_does_not(tmp_path):
    cfg = make_cfg(tmp_path)
    env = compose.render_env(cfg)
    key = cfg.services["sonarr"].api_key
    # Les valeurs sont protegees par des apostrophes : les mots de passe
    # contiennent des caracteres speciaux, et les chemins peuvent contenir une
    # espace.
    assert f"SONARR_API_KEY='{key}'" in env
    assert key not in compose.render_compose(cfg)


def test_write_artifacts_roundtrips_stack_yml(tmp_path):
    cfg = make_cfg(tmp_path)
    compose.write_artifacts(cfg, tmp_path / "proj")
    reloaded = StackConfig.model_validate(
        yaml.safe_load((tmp_path / "proj" / "stack.yml").read_text(encoding="utf-8"))
    )
    assert reloaded.services.keys() == cfg.services.keys()
    assert reloaded.services["sonarr"].api_key == cfg.services["sonarr"].api_key


# ----------------------------------------------------------------- schema fill


SCHEMA = {
    "implementation": "Transmission",
    "configContract": "TransmissionSettings",
    "fields": [
        {"name": "host", "value": ""},
        {"name": "port", "value": 9091},
        {"name": "tvDirectory", "value": ""},
    ],
}


def test_fill_applies_known_fields_and_reports_unknown_ones():
    filled, applied, skipped = ArrClient.fill(
        SCHEMA, {"host": "transmission", "tvDirectory": "/data/torrents/tv", "movieDirectory": "/x"}
    )
    by_name = {f["name"]: f["value"] for f in filled["fields"]}
    assert by_name["host"] == "transmission"
    assert by_name["tvDirectory"] == "/data/torrents/tv"
    assert sorted(applied) == ["host", "tvDirectory"]
    # movieDirectory n'existe pas dans CE gabarit : signale, pas perdu en silence.
    assert skipped == ["movieDirectory"]


def test_fill_does_not_mutate_the_source_schema():
    ArrClient.fill(SCHEMA, {"host": "x"})
    assert SCHEMA["fields"][0]["value"] == ""


# -------------------------------------------------------------------- hardlink


def test_hardlink_probe_actually_runs(tmp_path):
    ok, detail = hardlink_supported(tmp_path)
    assert isinstance(ok, bool) and detail
    # Aucun fichier temporaire ne doit survivre au test.
    assert not list((tmp_path / "torrents").glob(".plugarr-*"))
    assert not list((tmp_path / "media").glob(".plugarr-*"))


# ------------------------------------------------------------------ validation


def test_bad_umask_is_rejected_with_a_readable_message(tmp_path):
    with pytest.raises(ValueError, match="umask"):
        StackConfig(config_root=str(tmp_path), data_root=str(tmp_path), umask="99")


# ------------------------------------------------------- identifiants systeme


def test_unraid_uses_the_platform_constant_not_detection():
    """Unraid fait tourner ses conteneurs en nobody:users a l'echelle de la
    plateforme : detecter l'utilisateur courant y serait faux."""
    from plugarr.layout import PROFILE_DEFAULTS, resolve_ids

    uid, gid, source, certain = resolve_ids(PlatformProfile.UNRAID)
    assert (uid, gid) == (99, 100)
    assert certain
    assert "Unraid" in source
    assert not PROFILE_DEFAULTS[PlatformProfile.UNRAID].prefer_detection


def test_synology_detects_because_dsm_uids_vary():
    """Sur DSM l'UID depend de l'ordre de creation des utilisateurs : une
    constante serait fausse par conception."""
    from plugarr.layout import PROFILE_DEFAULTS

    assert PROFILE_DEFAULTS[PlatformProfile.SYNOLOGY].prefer_detection


def test_detection_returns_none_rather_than_inventing_a_value(monkeypatch):
    """Renvoyer 1000:1000 en silence empecherait d'avertir l'utilisateur."""
    import os as _os

    from plugarr.layout import detect_ids

    monkeypatch.delattr(_os, "getuid", raising=False)
    monkeypatch.delattr(_os, "getgid", raising=False)
    assert detect_ids() is None


def test_undetectable_ids_are_flagged_as_uncertain(monkeypatch):
    import os as _os

    from plugarr.layout import resolve_ids

    monkeypatch.delattr(_os, "getuid", raising=False)
    monkeypatch.delattr(_os, "getgid", raising=False)
    _uid, _gid, source, certain = resolve_ids(PlatformProfile.GENERIC_LINUX)
    assert not certain
    assert "detection impossible" in source


def test_config_records_where_the_ids_came_from(tmp_path):
    from plugarr import orchestrator

    cfg = orchestrator.build_config(services=["sonarr"], data_root=str(tmp_path))
    assert cfg.ids_source and cfg.ids_source != "non renseigne"


# -------------------------------------------------- coexistence avec l'existant


def test_container_names_are_prefixed_by_the_project(tmp_path):
    """Beaucoup de NAS font deja tourner un conteneur nomme `sonarr`. Sans
    prefixe, `docker compose up` entre en collision avec la production."""
    cfg = make_cfg(tmp_path)
    cfg.project_name = "plugarr"
    names = {b["container_name"] for b in compose.build_compose(cfg)["services"].values()}
    assert "sonarr" not in names
    assert "plugarr-sonarr" in names


def test_two_stacks_can_coexist(tmp_path):
    a, b = make_cfg(tmp_path), make_cfg(tmp_path)
    a.project_name, b.project_name = "maison", "labo"
    names_a = {x["container_name"] for x in compose.build_compose(a)["services"].values()}
    names_b = {x["container_name"] for x in compose.build_compose(b)["services"].values()}
    assert not (names_a & names_b)


def test_wiring_targets_service_names_not_container_names(tmp_path):
    """Verifie contre Docker Compose v5.3 : le nom de SERVICE resout meme quand
    container_name differe. Le cablage doit donc viser le service."""
    from plugarr.wiring import Wirer

    cfg = make_cfg(tmp_path)
    cfg.project_name = "prefixe-quelconque"
    assert Wirer(cfg).internal_url("sonarr") == "http://sonarr:8989"


def test_compose_service_keys_stay_bare(tmp_path):
    """Les cles de service sont ce que le DNS interne resout : elles ne doivent
    jamais porter le prefixe."""
    cfg = make_cfg(tmp_path)
    cfg.project_name = "maison"
    assert "sonarr" in compose.build_compose(cfg)["services"]


def test_running_as_root_is_flagged(monkeypatch):
    """Constate sur Linux natif : `sudo plugarr install` detecte 0:0 et faisait
    tourner toute la stack en root sans le dire. Les medias telecharges
    appartiennent alors a root et l'utilisateur ne peut plus y toucher."""
    import os as _os

    from plugarr.layout import resolve_ids

    monkeypatch.setattr(_os, "getuid", lambda: 0, raising=False)
    monkeypatch.setattr(_os, "getgid", lambda: 0, raising=False)
    uid, _gid, source, certain = resolve_ids(PlatformProfile.GENERIC_LINUX)
    assert uid == 0
    assert not certain
    assert "root" in source


def test_sous_sudo_c_est_le_compte_de_l_utilisateur_qui_est_retenu(monkeypatch):
    """Remonte le 2026-09-20 par un membre sur Synology.

    `/volume1` appartient a root : sans `sudo`, PlugArr ne peut meme pas y creer
    ses dossiers. Mais avec, il detectait 0:0 et posait tout en root ; Recyclarr,
    dont l'image tourne en 1000:1000 et ignore PUID, ne pouvait plus ecrire chez
    lui. sudo garde pourtant le vrai compte sous la main, dans SUDO_UID.
    """
    import os as _os

    from plugarr.layout import resolve_ids

    monkeypatch.setattr(_os, "getuid", lambda: 0, raising=False)
    monkeypatch.setattr(_os, "getgid", lambda: 0, raising=False)
    monkeypatch.setenv("SUDO_UID", "1000")
    monkeypatch.setenv("SUDO_GID", "10")

    uid, gid, source, certain = resolve_ids(PlatformProfile.GENERIC_LINUX)

    assert (uid, gid) == (1000, 10)
    assert certain, source
    assert "sudo" in source


def test_sudo_lance_depuis_root_n_apprend_rien(monkeypatch):
    """SUDO_UID=0 veut dire que root a fait un sudo : aucun vrai compte a
    retrouver, et l'avertissement doit rester."""
    import os as _os

    from plugarr.layout import resolve_ids

    monkeypatch.setattr(_os, "getuid", lambda: 0, raising=False)
    monkeypatch.setattr(_os, "getgid", lambda: 0, raising=False)
    monkeypatch.setenv("SUDO_UID", "0")

    uid, _gid, source, certain = resolve_ids(PlatformProfile.GENERIC_LINUX)

    assert uid == 0
    assert not certain
    assert "root" in source


@pytest.mark.parametrize("valeur", ["", "   ", "root", "-1000", "1000abc"])
def test_un_sudo_uid_illisible_ne_fabrique_pas_d_identifiant(monkeypatch, valeur):
    """Un environnement bricole ne doit pas produire un uid invente : mieux vaut
    l'avertissement sur root, que l'utilisateur peut corriger."""
    import os as _os

    from plugarr.layout import resolve_ids

    monkeypatch.setattr(_os, "getuid", lambda: 0, raising=False)
    monkeypatch.setattr(_os, "getgid", lambda: 0, raising=False)
    monkeypatch.setenv("SUDO_UID", valeur)

    uid, _gid, _source, certain = resolve_ids(PlatformProfile.GENERIC_LINUX)

    assert uid == 0
    assert not certain


def test_sans_sudo_gid_l_uid_est_garde_quand_meme(monkeypatch):
    """Perdre le bon uid parce qu'il manque le gid serait absurde."""
    import os as _os

    from plugarr.layout import resolve_ids

    monkeypatch.setattr(_os, "getuid", lambda: 0, raising=False)
    monkeypatch.setattr(_os, "getgid", lambda: 0, raising=False)
    monkeypatch.setenv("SUDO_UID", "1000")
    monkeypatch.delenv("SUDO_GID", raising=False)

    uid, gid, _source, certain = resolve_ids(PlatformProfile.GENERIC_LINUX)

    assert uid == 1000
    assert gid == 0  # celui du processus, faute de mieux
    assert certain


def test_a_normal_user_is_not_flagged(monkeypatch):
    import os as _os

    from plugarr.layout import resolve_ids

    monkeypatch.setattr(_os, "getuid", lambda: 1000, raising=False)
    monkeypatch.setattr(_os, "getgid", lambda: 1000, raising=False)
    uid, gid, _source, certain = resolve_ids(PlatformProfile.GENERIC_LINUX)
    assert (uid, gid) == (1000, 1000)
    assert certain


# ------------------------------------------------------------ Flood, deux clients


def test_flood_alone_pulls_in_the_first_client():
    assert catalog.resolve_dependencies(["flood"]) == ["qbittorrent", "flood"]


def test_flood_next_to_qbittorrent_does_not_also_pull_transmission():
    """Cocher Flood a cote d'un client deja choisi ne doit pas en installer un second."""
    assert catalog.resolve_dependencies(["qbittorrent", "flood"]) == ["qbittorrent", "flood"]


def test_flood_next_to_transmission_does_not_also_pull_qbittorrent():
    assert catalog.resolve_dependencies(["transmission", "flood"]) == ["transmission", "flood"]


def test_flood_targets_qbittorrent_with_the_right_flags(tmp_path):
    """Options relevees sur `flood --help` de l'image 4.16.1, pas supposees."""
    cfg = make_cfg(tmp_path, services=("qbittorrent", "flood"))
    command = compose.build_compose(cfg)["services"]["flood"]["command"]
    assert "--qburl" in command
    assert "http://qbittorrent:8080" in command
    assert "--trurl" not in command


def test_flood_targets_transmission_with_the_right_rpc_path(tmp_path):
    cfg = make_cfg(tmp_path, services=("transmission", "flood"))
    command = compose.build_compose(cfg)["services"]["flood"]["command"]
    assert "--trurl" in command
    assert "http://transmission:9091/transmission/rpc" in command
    assert "--qburl" not in command


def test_with_both_clients_flood_picks_qbittorrent(tmp_path):
    """Flood ne pilote qu'un client a la fois : l'API de qBittorrent est plus riche."""
    cfg = make_cfg(tmp_path, services=("transmission", "qbittorrent", "flood"))
    block = compose.build_compose(cfg)["services"]["flood"]
    assert "--qburl" in block["command"]
    assert block["depends_on"] == ["qbittorrent"]


def test_flood_gets_no_puid_pgid(tmp_path):
    """Flood ignore PUID/PGID mais doit tourner avec ces identifiants.

    Remonte sur UGOS le 2026-09-23 : l'image utilisait son compte interne et
    redemarrait en boucle sur « Failed to access runtime directory » quand elle
    tentait de creer `/config/.local/share/flood`.
    """
    cfg = make_cfg(tmp_path, services=("qbittorrent", "flood"))
    cfg.puid, cfg.pgid = 1000, 10
    block = compose.build_compose(cfg)["services"]["flood"]
    env = block["environment"]
    assert "PUID" not in env
    assert "PGID" not in env
    assert block["user"] == "1000:10"


def test_autobrr_needs_at_least_one_arr():
    """Sans application a alimenter, autobrr n'a rien a faire."""
    assert "sonarr" in catalog.resolve_dependencies(["autobrr"])


def test_autobrr_next_to_radarr_does_not_pull_sonarr():
    assert catalog.resolve_dependencies(["radarr", "autobrr"]) == ["radarr", "autobrr"]


def test_qui_pulls_in_qbittorrent():
    """qui est une UI pour qBittorrent : il n'a pas d'autre backend."""
    assert catalog.resolve_dependencies(["qui"]) == ["qbittorrent", "qui"]


def test_autobrr_is_wired_after_the_arrs_and_the_clients():
    """autobrr les declare tous les deux, et son test de connexion les contacte
    reellement : ils doivent repondre avant."""
    order = catalog.STARTUP_ORDER
    for sid in ("sonarr", "radarr", "qbittorrent", "prowlarr"):
        assert order.index("autobrr") > order.index(sid), sid


def test_autobrr_gets_no_data_mount(tmp_path):
    """autobrr ne touche pas aux fichiers : il pousse des sorties vers les
    applications. Lui monter /data serait un acces inutile."""
    cfg = make_cfg(tmp_path, services=("sonarr", "autobrr"))
    volumes = compose.build_compose(cfg)["services"]["autobrr"]["volumes"]
    assert not any(v.endswith(":/data") for v in volumes)
    assert any(v.endswith(":/config") for v in volumes)


def test_qui_gets_no_puid_pgid(tmp_path):
    """qui n'est pas une image LinuxServer : ces variables n'y font rien."""
    cfg = make_cfg(tmp_path, services=("qbittorrent", "qui"))
    env = compose.build_compose(cfg)["services"]["qui"]["environment"]
    assert "PUID" not in env
    assert env["QUI__HOST"] == "0.0.0.0"


def test_autobrr_step_appears_only_when_selected(tmp_path):
    from plugarr.wiring import Wirer

    without = {s.name for s in Wirer(make_cfg(tmp_path, services=("sonarr",))).build_plan()}
    with_it = {
        s.name for s in Wirer(make_cfg(tmp_path, services=("sonarr", "autobrr"))).build_plan()
    }
    assert "autobrr/clients" not in without
    assert "autobrr/clients" in with_it


# --------------------------------------------------------------------- Gluetun


def _vpn(cfg, **kw):
    from plugarr.models import VpnConfig

    defaults = {"enabled": True, "provider": "nordvpn", "wireguard_private_key": "cle="}
    cfg.vpn = VpnConfig(**{**defaults, **kw})
    return cfg


def test_the_torrent_client_ports_move_to_gluetun(tmp_path):
    """Un service en network_mode: service:X ne PEUT plus publier de port. Sans
    ce transfert, l'interface du client devient injoignable en silence."""
    cfg = _vpn(make_cfg(tmp_path, services=("sonarr", "qbittorrent")))
    doc = compose.build_compose(cfg)
    assert doc["services"]["gluetun"]["ports"] == ["8080:8080"]
    assert "ports" not in doc["services"]["qbittorrent"]
    assert doc["services"]["qbittorrent"]["network_mode"] == "service:gluetun"


def test_services_outside_the_vpn_keep_their_ports(tmp_path):
    cfg = _vpn(make_cfg(tmp_path, services=("sonarr", "qbittorrent")))
    doc = compose.build_compose(cfg)
    assert doc["services"]["sonarr"]["ports"] == ["8989:8989"]
    assert "network_mode" not in doc["services"]["sonarr"]


def test_gluetun_gets_what_a_tunnel_needs(tmp_path):
    cfg = _vpn(make_cfg(tmp_path, services=("qbittorrent",)))
    block = compose.build_compose(cfg)["services"]["gluetun"]
    assert block["cap_add"] == ["NET_ADMIN"]
    assert "/dev/net/tun:/dev/net/tun" in block["devices"]


def test_the_client_waits_for_a_healthy_tunnel(tmp_path):
    """L'image fournit son propre healthcheck : on attend une connexion VPN
    reellement etablie, pas seulement un conteneur demarre."""
    cfg = _vpn(make_cfg(tmp_path, services=("qbittorrent",)))
    block = compose.build_compose(cfg)["services"]["qbittorrent"]
    assert block["depends_on"] == {"gluetun": {"condition": "service_healthy"}}


def test_no_gluetun_without_the_vpn(tmp_path):
    assert "gluetun" not in compose.build_compose(make_cfg(tmp_path))["services"]


def test_an_incomplete_vpn_refuses_to_generate(tmp_path):
    """Mieux vaut refuser que produire un compose qui ne demarrera pas."""
    cfg = _vpn(make_cfg(tmp_path, services=("qbittorrent",)), wireguard_private_key="")
    with pytest.raises(ValueError, match="incomplet"):
        compose.build_compose(cfg)


def test_wireguard_and_openvpn_do_not_need_the_same_fields():
    from plugarr.models import VpnConfig

    wg = VpnConfig(enabled=True, provider="mullvad", vpn_type="wireguard")
    assert "WireGuard" in wg.missing()[0]
    wg.wireguard_private_key = "cle="
    assert wg.missing() == []

    ovpn = VpnConfig(enabled=True, provider="mullvad", vpn_type="openvpn")
    assert "OpenVPN" in ovpn.missing()[0]
    ovpn.openvpn_user, ovpn.openvpn_password = "u", "p"
    assert ovpn.missing() == []


def test_an_unknown_provider_is_refused_with_the_list():
    from plugarr.models import VpnConfig

    with pytest.raises(ValueError, match="nordvpn"):
        VpnConfig(provider="fournisseur-invente")


def test_the_provider_list_comes_from_gluetun():
    """Obtenue de Gluetun v3.41.3 en lui passant un nom invalide : il repond avec
    l'enumeration exacte."""
    from plugarr.models import VPN_PROVIDERS

    for expected in ("nordvpn", "mullvad", "protonvpn", "surfshark", "custom"):
        assert expected in VPN_PROVIDERS


def test_a_vpn_bound_client_is_reached_through_gluetun(tmp_path):
    """Sous network_mode: service:X, le conteneur perd son alias DNS. Verifie
    contre Docker : seul le nom du conteneur VPN resout."""
    from plugarr.wiring import Wirer

    cfg = _vpn(make_cfg(tmp_path, services=("sonarr", "qbittorrent")))
    wirer = Wirer(cfg)
    assert wirer.internal_url("qbittorrent") == "http://gluetun:8080"
    assert wirer.internal_url("sonarr") == "http://sonarr:8989"


def test_lance_en_root_recyclarr_recoit_son_dossier(tmp_path, monkeypatch):
    """Remonte le 2026-09-20 par un membre sur Synology.

    L'image de Recyclarr tourne en 1000:1000 en dur et ne lit pas PUID. Une
    installation en `sudo` creait son dossier en root, et il se faisait jeter a
    l'ecriture. Sans interface web, il n'avait aucun moyen de le dire.
    """
    from plugarr import layout

    donnes: list[tuple[str, tuple[int, int]]] = []
    monkeypatch.setattr(layout, "_est_root", lambda: True)
    monkeypatch.setattr(layout, "_reparer_dossier_donnees", lambda *_args: None)
    monkeypatch.setattr(
        layout, "_donner", lambda dossier, owner: donnes.append((dossier.name, owner))
    )

    layout.create_tree(
        tmp_path / "data", tmp_path / "config", ["recyclarr", "sonarr"], owner=(1000, 10)
    )

    attribues = {nom for nom, _ in donnes}
    assert "recyclarr" in attribues, attribues
    # Les images LinuxServer se donnent leur dossier elles-memes, a partir de
    # PUID : le faire ici masquerait a qui revient le travail.
    assert "sonarr" not in attribues, attribues
    assert all(owner == (1000, 10) for _, owner in donnes)


def test_lance_en_root_les_dossiers_de_donnees_vont_a_l_utilisateur(tmp_path, monkeypatch):
    """Mesure sur le banc le 2026-09-20, image linuxserver/sonarr:4.0.19.

    Les deux montages a root, PUID=1000 PGID=10 : au demarrage, /config passe a
    1000:10 — l'image s'en charge — mais /data reste a root, et un `touch` sous
    1000:10 dans /data/torrents repond « Permission denied ». Une installation
    en sudo donnait donc une pile qui demarre et qui ne telecharge rien.
    """
    from plugarr import layout

    donnes: list[tuple[Path, tuple[int, int]]] = []
    monkeypatch.setattr(
        layout,
        "_reparer_dossier_donnees",
        lambda dossier, owner: donnes.append((dossier, owner)),
    )

    layout.create_tree(tmp_path / "data", tmp_path / "config", ["sonarr"], owner=(1000, 10))

    assert (tmp_path / "data", (1000, 10)) in donnes
    for sous_dossier in layout.DATA_SUBDIRS:
        dossier = tmp_path / "data" / sous_dossier
        assert (dossier, (1000, 10)) in donnes, f"{sous_dossier} laisse a root : {donnes}"


def test_une_racine_de_donnees_deja_peuplee_n_est_pas_reprise(tmp_path, monkeypatch):
    """Un `chown -R` sur une mediatheque de plusieurs tera serait long, et ce
    n'est pas a une installation de redistribuer ce qu'elle n'a pas cree."""
    from plugarr import layout

    data = tmp_path / "data"
    for sous_dossier in layout.DATA_SUBDIRS:
        (data / sous_dossier).mkdir(parents=True, exist_ok=True)
    donnes: list[str] = []
    monkeypatch.setattr(layout, "_est_root", lambda: True)
    monkeypatch.setattr(layout, "_reparer_dossier_donnees", lambda *_args: None)
    monkeypatch.setattr(layout, "_donner", lambda dossier, owner: donnes.append(dossier.name))

    layout.create_tree(data, tmp_path / "config", ["sonarr"], owner=(1000, 10))

    assert donnes == [], donnes


def test_les_dossiers_de_donnees_existants_sont_repares_sans_toucher_aux_fichiers(
    tmp_path, monkeypatch
):
    """Correctif valide sur UGOS avec ``chown/chmod`` le 2026-09-23.

    Une premiere installation interrompue avait deja cree l'arborescence sous
    root. La relance la sautait entierement et Sonarr ne pouvait pas declarer
    ses dossiers racines. PlugArr doit reprendre les dossiers attendus, sans
    parcourir une mediatheque potentiellement enorme ni changer ses fichiers.
    """
    from plugarr import layout

    data = tmp_path / "data"
    for sous_dossier in layout.DATA_SUBDIRS:
        (data / sous_dossier).mkdir(parents=True, exist_ok=True)
    media_existant = data / "media" / "movies" / "film.mkv"
    media_existant.write_bytes(b"deja-la")

    repares: list[tuple[Path, tuple[int, int]]] = []
    recursifs: list[Path] = []
    monkeypatch.setattr(
        layout,
        "_reparer_dossier_donnees",
        lambda dossier, owner: repares.append((dossier, owner)),
    )
    monkeypatch.setattr(layout, "_donner", lambda dossier, owner: recursifs.append(dossier))

    layout.create_tree(data, tmp_path / "config", ["sonarr"], owner=(1000, 10))

    assert (data, (1000, 10)) in repares
    for sous_dossier in layout.DATA_SUBDIRS:
        assert (data / sous_dossier, (1000, 10)) in repares
    assert media_existant not in [dossier for dossier, _ in repares]
    assert recursifs == [], "les donnees existantes ne doivent jamais etre chown -R"


def test_la_reparation_ugreen_ne_touche_qu_aux_dossiers_root(tmp_path, monkeypatch):
    """On reproduit le ``chown 1000:10`` et le ``chmod 775`` du ticket,
    uniquement sur le dossier exact et uniquement s'il appartient a root."""
    from types import SimpleNamespace

    from plugarr import layout

    ouverts: list[Path] = []
    chown: list[tuple[int, int, int]] = []
    chmod: list[tuple[int, int]] = []
    fermes: list[int] = []
    informations = SimpleNamespace(st_uid=0, st_mode=0o40500)
    monkeypatch.setattr(layout, "_est_root", lambda: True)
    monkeypatch.setattr(layout.os, "O_DIRECTORY", 0x10000, raising=False)
    monkeypatch.setattr(layout.os, "O_NOFOLLOW", 0x20000, raising=False)
    monkeypatch.setattr(
        layout.os,
        "stat",
        lambda path, **_kw: SimpleNamespace(
            st_mode=0o120777 if Path(path).name == "link" else 0o40500
        ),
    )
    monkeypatch.setattr(layout.os, "open", lambda path, _flags: ouverts.append(Path(path)) or 42)
    monkeypatch.setattr(layout.os, "fstat", lambda _fd: informations)
    monkeypatch.setattr(
        layout.os,
        "fchown",
        lambda fd, uid, gid: chown.append((fd, uid, gid)),
        raising=False,
    )
    monkeypatch.setattr(
        layout.os,
        "fchmod",
        lambda fd, mode: chmod.append((fd, mode)),
        raising=False,
    )
    monkeypatch.setattr(layout.os, "close", lambda fd: fermes.append(fd))

    dossier = tmp_path / "data" / "media" / "movies"
    layout._reparer_dossier_donnees(dossier, (1000, 10))

    informations = SimpleNamespace(st_uid=1000, st_mode=0o40500)
    layout._reparer_dossier_donnees(tmp_path / "data" / "media" / "tv", (1000, 10))

    informations = SimpleNamespace(st_uid=0, st_mode=0o100777)
    layout._reparer_dossier_donnees(tmp_path / "data" / "media" / "link", (1000, 10))

    assert ouverts == [
        dossier,
        tmp_path / "data" / "media" / "tv",
    ]
    assert chown == [(42, 1000, 10)]
    assert chmod == [(42, 0o770)]
    assert fermes == [42, 42]


def test_sans_proprietaire_on_ne_touche_a_rien(tmp_path, monkeypatch):
    """Hors root, il n'y a rien a redistribuer : les dossiers appartiennent deja
    a celui qui les a crees."""
    from plugarr import layout

    donnes: list[str] = []
    monkeypatch.setattr(layout, "_donner", lambda dossier, owner: donnes.append(dossier.name))

    layout.create_tree(tmp_path / "data", tmp_path / "config", ["recyclarr"], owner=None)

    assert donnes == []


def test_le_dossier_de_recyclarr_est_repris_meme_s_il_existe_deja(tmp_path, monkeypatch):
    """Celui qui a deja installe en sudo a un dossier en root. Le reparer au
    passage evite de lui demander un `chown` a la main."""
    from plugarr import layout

    deja = tmp_path / "config" / "recyclarr"
    deja.mkdir(parents=True)
    donnes: list[str] = []
    monkeypatch.setattr(layout, "_est_root", lambda: True)
    monkeypatch.setattr(layout, "_reparer_dossier_donnees", lambda *_args: None)
    monkeypatch.setattr(layout, "_donner", lambda dossier, owner: donnes.append(dossier.name))

    layout.create_tree(tmp_path / "data", tmp_path / "config", ["recyclarr"], owner=(1000, 10))

    assert "recyclarr" in donnes, donnes


def test_le_dossier_de_flood_est_repris_meme_s_il_existe_deja(tmp_path, monkeypatch):
    """Une ancienne installation sudo ne doit pas condamner Flood a redemarrer.

    Le compte force dans le compose doit pouvoir creer son repertoire
    d'execution sous `/config/.local/share/flood`.
    """
    from plugarr import layout

    deja = tmp_path / "config" / "flood"
    runtime = deja / ".local" / "share" / "flood"
    runtime.mkdir(parents=True)
    donnes: list[tuple[Path, tuple[int, int]]] = []
    monkeypatch.setattr(layout, "_est_root", lambda: True)
    monkeypatch.setattr(layout, "_reparer_dossier_donnees", lambda *_args: None)
    monkeypatch.setattr(
        layout, "_donner", lambda dossier, owner: donnes.append((dossier, owner))
    )

    layout.create_tree(
        tmp_path / "data", tmp_path / "config", ["flood"], owner=(1000, 10)
    )

    assert (deja, (1000, 10)) in donnes


def test_installe_en_root_les_artefacts_reviennent_a_l_utilisateur(tmp_path, monkeypatch):
    """`stack.yml` et `.env` sont en 600. Ecrits par root, ils deviennent
    illisibles a leur proprietaire legitime, et `plugarr` sans `sudo` s'arrete
    sur un PermissionError : l'utilisateur est condamne a `sudo` pour toujours,
    y compris pour regarder l'etat de ses services.

    Le cas est le chemin NORMAL sur un NAS, ou `/volume1` appartient a root et
    ou creer les dossiers EXIGE `sudo`.
    """
    import os as _os

    from plugarr import compose as _compose
    from plugarr import layout

    donnes: dict[str, tuple[int, int]] = {}
    monkeypatch.setattr(layout, "_est_root", lambda: True)
    monkeypatch.setattr(
        _os, "chown", lambda p, u, g, **kw: donnes.__setitem__(Path(p).name, (u, g)), raising=False
    )

    cfg = make_cfg(tmp_path)
    cfg.puid, cfg.pgid = 1000, 10
    projet = tmp_path / "projet"
    _compose.write_artifacts(cfg, projet)

    for nom in ("stack.yml", ".env", "docker-compose.yml"):
        assert donnes.get(nom) == (1000, 10), f"{nom} laisse a root : {donnes}"
    # Le dossier aussi : sans lui, l'utilisateur ne peut rien y reecrire.
    assert donnes.get("projet") == (1000, 10), donnes


def test_hors_root_les_artefacts_ne_changent_pas_de_main(tmp_path, monkeypatch):
    """Ils appartiennent deja a celui qui les a ecrits."""
    import os as _os

    from plugarr import compose as _compose
    from plugarr import layout

    appels: list[str] = []
    monkeypatch.setattr(layout, "_est_root", lambda: False)
    monkeypatch.setattr(_os, "chown", lambda *a, **kw: appels.append("chown"), raising=False)

    _compose.write_artifacts(make_cfg(tmp_path), tmp_path / "projet")

    assert appels == []


# --------------------------------------------------------------- profil UGREEN


def test_le_profil_ugreen_propose_les_chemins_d_un_volume(monkeypatch):
    """UGOS range ses volumes comme DSM : /volume1, /volume2, crees dans
    l'interface. `/srv` et `/opt` y sont refuses, comme sur tout NAS : herite de
    `generic-linux`, un utilisateur UGREEN se voyait proposer des chemins que le
    systeme refuse.

    Chemins releves avec un utilisateur sur son propre NAS, le 2026-09-18.
    """
    from plugarr.layout import PROFILE_DEFAULTS

    defauts = PROFILE_DEFAULTS[PlatformProfile.UGREEN]

    assert defauts.config_root == "/volume1/docker/plugarr"
    assert defauts.data_root == "/volume1/data"
    assert not defauts.config_root.startswith(("/srv", "/opt"))


def test_le_profil_ugreen_detecte_les_identifiants(monkeypatch):
    """La constante 1000:10 vient d'UN SEUL NAS. Sur UGOS comme sur DSM, l'UID
    depend de l'ordre de creation des comptes : une constante serait fausse par
    conception, d'ou la detection qui passe devant."""
    import os as _os

    from plugarr.layout import PROFILE_DEFAULTS, resolve_ids

    assert PROFILE_DEFAULTS[PlatformProfile.UGREEN].prefer_detection

    monkeypatch.setattr(_os, "getuid", lambda: 1027, raising=False)
    monkeypatch.setattr(_os, "getgid", lambda: 100, raising=False)
    uid, gid, _source, certain = resolve_ids(PlatformProfile.UGREEN)

    assert (uid, gid) == (1027, 100), "la constante a pris le pas sur la detection"
    assert certain


def test_le_profil_ugreen_se_dit_experimental():
    """Il vient d'une seule installation reelle. Le taire serait le presenter
    pour ce qu'il n'est pas, et deux contraintes d'UGOS ne se devinent pas : les
    volumes appartiennent a root, et les tunnels SSH sont interdits."""
    from plugarr.layout import PROFILE_DEFAULTS

    note = PROFILE_DEFAULTS[PlatformProfile.UGREEN].note

    assert "EXPERIMENTAL" in note
    assert "sudo" in note
    assert "SSH" in note


def test_les_profils_eprouves_n_affichent_aucune_note():
    """Une note sur chaque profil ne voudrait plus rien dire."""
    from plugarr.layout import PROFILE_DEFAULTS

    for profil in (PlatformProfile.GENERIC_LINUX, PlatformProfile.WINDOWS,
                   PlatformProfile.UNRAID, PlatformProfile.SYNOLOGY):
        assert PROFILE_DEFAULTS[profil].note == "", profil


def test_chaque_profil_declare_ses_defauts():
    """Un profil ajoute a l'enumeration sans entree ici planterait a l'ouverture
    de l'ecran des chemins, pas avant."""
    from plugarr.layout import PROFILE_DEFAULTS

    assert set(PROFILE_DEFAULTS) == set(PlatformProfile)


def test_hardlink_probe_sur_donnees_en_lecture_seule_ne_plante_pas(tmp_path, monkeypatch):
    """Console en conteneur reelle du 25/09/2026 : DATA_ROOT monte en lecture seule."""
    import errno
    import tempfile

    from plugarr.layout import hardlink_supported

    (tmp_path / "torrents").mkdir()
    (tmp_path / "media").mkdir()

    def lecture_seule(*_args, **_kwargs):
        raise OSError(errno.EROFS, "Read-only file system")

    monkeypatch.setattr(tempfile, "mkstemp", lecture_seule)

    ok, detail = hardlink_supported(tmp_path)

    assert ok is False
    assert "Read-only file system" in detail

