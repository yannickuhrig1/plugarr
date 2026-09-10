"""Tests de la page d'acces. Aucun reseau, aucun navigateur."""

from __future__ import annotations

import re

import pytest

from plugarr import dashboard, orchestrator
from plugarr.models import PlatformProfile


def make(services=("prowlarr", "sonarr", "radarr", "qbittorrent", "jellyfin"), **kw):
    return orchestrator.build_config(
        services=list(services),
        data_root=kw.get("data_root", "/srv/data"),
        config_root=kw.get("config_root", "/opt/plugarr/config"),
        platform=PlatformProfile.GENERIC_LINUX,
    )


# ------------------------------------------------------------------- contenu


def test_every_installed_service_gets_a_link():
    cfg = make()
    page = dashboard.render(cfg)
    for sid, inst in orchestrator.iter_selected(cfg):
        assert f":{inst.host_port}" in page, sid


def test_service_cards_use_their_embedded_application_logos():
    page = dashboard.render(make(services=("transmission", "sonarr", "jellyfin")), live=True)

    assert page.count('class="badge app-icon"') >= 3
    assert page.count('src="data:image/svg+xml;base64,') >= 3
    assert '<span class="badge">T</span>' not in page
    assert '<span class="badge">S</span>' not in page


def test_services_that_were_not_installed_are_absent():
    page = dashboard.render(make(services=("sonarr",)))
    assert "Sonarr" in page
    assert "Jellyfin" not in page
    assert "qBittorrent" not in page


def test_download_and_media_folders_are_listed():
    page = dashboard.render(make(data_root="/srv/data"))
    assert "/srv/data/media/movies" in page
    assert "/srv/data/media/tv" in page
    assert "/srv/data/torrents" in page


def test_music_folder_only_appears_with_lidarr():
    assert "media/music" not in dashboard.render(make())
    assert "media/music" in dashboard.render(make(services=("lidarr",)))


def test_folder_rows_offer_a_copyable_path_and_a_local_link():
    """Le lien file:// ne marche que si le navigateur tourne sur la machine
    d'installation. Le chemin copiable doit donc exister aussi."""
    page = dashboard.render(make(data_root="/srv/data"))
    assert 'data-value="/srv/data/torrents"' in page
    assert "file:///srv/data/torrents" in page
    assert "ne fonctionnent que si ce navigateur tourne sur la" in page


# -------------------------------------------------------------------- secrets


def test_secrets_are_masked_until_clicked():
    cfg = make()
    page = dashboard.render(cfg)
    password = cfg.services["sonarr"].password
    # La valeur est dans le fichier - c'est un fichier local, comme le .env.
    # Ce qui compte est qu'elle ne s'AFFICHE pas sans un clic explicite.
    assert f'data-value="{password}"' in page
    assert "••••••••" in page


def test_the_page_warns_that_it_holds_secrets():
    page = dashboard.render(make())
    assert "chmod 600" in page
    assert "Ne la partagez pas" in page


def test_written_file_is_restricted_and_named_predictably(tmp_path):
    path = dashboard.write(make(), tmp_path)
    assert path.name == dashboard.FILENAME
    assert path.exists()


# ------------------------------------------------------------------- securite


def test_paths_are_html_escaped():
    """Les chemins viennent de l'utilisateur : sans echappement, un chemin
    malicieux injecterait du script dans la page."""
    page = dashboard.render(make(data_root='/srv/<script>alert(1)</script>'))
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_the_only_script_tag_is_our_own():
    page = dashboard.render(make(data_root="/srv/data"))
    assert len(re.findall(r"<script", page)) == 1


# ----------------------------------------------------------------------- hote


def test_localhost_is_replaced_by_the_lan_address(monkeypatch):
    """Installee sur un NAS et ouverte depuis un portable, une URL en localhost
    pointerait vers le portable."""
    monkeypatch.setattr(dashboard, "primary_lan_ip", lambda: "192.168.1.42")
    cfg = make()
    host, note = dashboard.resolve_host(cfg)
    assert host == "192.168.1.42"
    assert "192.168.1.42" in (note or "")
    assert "192.168.1.42" in dashboard.render(cfg)


def test_an_explicit_host_is_left_alone(monkeypatch):
    monkeypatch.setattr(dashboard, "primary_lan_ip", lambda: "192.168.1.42")
    cfg = make()
    cfg.host = "nas.local"
    host, note = dashboard.resolve_host(cfg)
    assert host == "nas.local"
    assert note is None


def test_without_a_lan_address_the_limit_is_stated(monkeypatch):
    monkeypatch.setattr(dashboard, "primary_lan_ip", lambda: None)
    _host, note = dashboard.resolve_host(make())
    assert note and "autre appareil" in note


def test_lan_detection_never_returns_loopback(monkeypatch):
    class FakeSock:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def settimeout(self, _):
            pass

        def connect(self, _):
            pass

        def getsockname(self):
            return ("127.0.0.1", 0)

    monkeypatch.setattr(dashboard.socket, "socket", lambda *a, **k: FakeSock())
    assert dashboard.primary_lan_ip() is None


# ---------------------------------------------------------------- avertissements


def test_failed_links_are_surfaced_on_the_page():
    page = dashboard.render(make(), failed=3)
    assert "3 lien(s)" in page
    assert "plugarr doctor" in page


def test_a_clean_install_shows_no_failure_banner():
    assert "plugarr doctor" not in dashboard.render(make())


def test_the_vpn_warning_follows_the_config():
    cfg = make()
    assert "Aucun VPN" in dashboard.render(cfg)
    cfg.vpn.enabled = True
    assert "Aucun VPN" not in dashboard.render(cfg)


def test_uncertain_ids_are_repeated_on_the_page():
    cfg = make()
    cfg.ids_certain = False
    cfg.ids_source = "lance en root : conteneurs et medias appartiendront a root"
    page = dashboard.render(cfg)
    assert "root" in page
    assert "qui possede vos medias" in page


@pytest.mark.parametrize("marker", ["<!doctype html>", 'lang="fr"', "prefers-color-scheme"])
def test_page_is_a_standalone_document(marker):
    """Aucune ressource externe : la page doit s'ouvrir hors ligne."""
    page = dashboard.render(make())
    assert marker in page
    assert "http://cdn" not in page
    assert "https://" not in page.split("<style>")[0]


def test_no_vpn_warning_without_a_download_client():
    """Sans client torrent il n'y a pas de trafic BitTorrent : l'avertissement
    serait du bruit, et le bruit fait ignorer les vrais avertissements."""
    assert "Aucun VPN" not in dashboard.render(make(services=("sonarr", "jellyfin")))
    assert "Aucun VPN" in dashboard.render(make(services=("sonarr", "qbittorrent")))


# ------------------------------------------------- integrite du script servi


def _script_of(page: str) -> str:
    import re

    blocks = re.findall(r"<script>(.*?)</script>", page, re.DOTALL)
    assert blocks, "aucun bloc script dans la page"
    return blocks[-1]


def test_no_javascript_string_spans_a_line_break():
    """Une chaine JS ne peut pas franchir une ligne : elle casse le script ENTIER,
    silencieusement. Un `\n` mal echappe dans le source Python a deja produit
    exactement cela - la page se chargeait, et plus rien ne se mettait a jour.
    """
    for line in _script_of(dashboard.render(make(), live=True)).splitlines():
        stripped = line.replace("\'", "").replace('\\"', "")
        assert stripped.count("'") % 2 == 0, f"apostrophe non fermee : {line.strip()[:80]}"
        assert stripped.count('"') % 2 == 0, f"guillemet non ferme : {line.strip()[:80]}"


def test_the_live_script_braces_are_balanced():
    script = _script_of(dashboard.render(make(), live=True))
    assert script.count("{") == script.count("}")
    assert script.count("(") == script.count(")")


def test_the_update_zone_exists_for_every_service():
    cfg = make(services=("sonarr", "qbittorrent"))
    page = dashboard.render(cfg, live=True)
    for sid in cfg.services:
        assert f'class="upd" data-service="{sid}"' in page


def test_the_static_page_carries_no_update_machinery():
    """Le fichier fige ne peut rien mettre a jour : lui donner des boutons serait
    un mensonge."""
    page = dashboard.render(make())
    assert "verifierMaj" not in page
    assert 'class="upd"' not in page


def test_l_identifiant_a_son_bouton_de_copie():
    """Demande a l'usage : « ajoute un bouton pour copier le user comme pour le
    password ».

    L'identifiant se recopie autant que le mot de passe — dans un formulaire de
    connexion, juste avant lui — et il n'avait pas de bouton. Il n'est pas
    secret pour autant : il reste affiche en clair, seul le bouton manquait.
    """
    cfg = orchestrator.build_config(
        services=["sonarr"], config_root="/c", data_root="/d", username="yannick"
    )
    page = dashboard.render(cfg)

    ligne = next(bloc for bloc in page.split('<div class="row">') if "yannick" in bloc)

    assert 'class="copy" data-value="yannick"' in ligne
    assert "yannick" in ligne, "l'identifiant reste lisible : ce n'est pas un secret"
    assert 'class="secret"' not in ligne, "il ne doit pas etre masque"


def test_le_bouton_de_l_identifiant_est_celui_des_autres():
    """C'est le script de la page qui l'anime, sur `button.copy[data-value]`.
    Un bouton d'une autre forme serait inerte."""
    cfg = orchestrator.build_config(
        services=["sonarr"], config_root="/c", data_root="/d", username="yannick"
    )
    page = dashboard.render(cfg)

    assert page.count('class="copy" data-value=') >= 2, "identifiant ET secrets"
    assert "button.copy" in page, "le script qui anime les boutons"
