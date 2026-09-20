"""Configuration reduite de la veille : ce qu'elle garde, et ce qu'elle jette.

Constat du 2026-09-20, en lancant l'image publiee sur le banc contre la vraie
installation : `stack.yml` est en 600 root, et la veille, sous PUID:PGID, ne
peut pas le lire. D'ou ce fichier reduit, qui lui appartient.
"""

from __future__ import annotations

import os

import pytest

from plugarr import migrations, orchestrator, veille, veille_config

CLE_VPN = "kPmz9kMfQ0yv7l3D2sJcT1oXbW8eUuHgA6RnZ4pYiVs="


def _cfg(tmp_path):
    cfg = orchestrator.build_config(
        services=["sonarr", "prowlarr", "qbittorrent", "sabnzbd"],
        config_root=str(tmp_path / "c"),
        data_root=str(tmp_path / "d"),
    )
    cfg.vpn.enabled = True
    cfg.vpn.provider = "protonvpn"
    cfg.vpn.wireguard_private_key = CLE_VPN
    cfg.vpn.openvpn_user, cfg.vpn.openvpn_password = "moi", "secret-openvpn"
    cfg.admin_password_hash = "pbkdf2-sha256$1000$sel$empreinte"
    return cfg


def test_la_cle_du_vpn_ne_part_pas_dans_le_conteneur(tmp_path):
    """La veille lit la sortie du tunnel au serveur de controle de Gluetun :
    elle n'a jamais besoin de la cle qui le monte."""
    cfg = _cfg(tmp_path)

    texte = veille_config.ecrire(cfg).read_text(encoding="utf-8")

    assert CLE_VPN not in texte
    assert "secret-openvpn" not in texte
    # L'existence du VPN, elle, doit rester : sans elle, la veille chercherait
    # qBittorrent sur son propre nom au lieu de `gluetun`.
    reduit, _ = migrations.lire(veille_config.chemin(cfg))
    assert reduit.vpn_enabled is True
    assert reduit.vpn.protects("qbittorrent") is True


def test_les_cles_api_des_services_seulement_surveilles_sont_retirees(tmp_path):
    """Leur etat se lit par un GET : toute reponse sous 500 prouve qu'ils
    tournent, et cela ne demande aucune cle."""
    cfg = _cfg(tmp_path)
    cfg.services["sonarr"].api_key = "cle-api-de-sonarr"

    texte = veille_config.ecrire(cfg).read_text(encoding="utf-8")
    reduit, _ = migrations.lire(veille_config.chemin(cfg))

    assert "cle-api-de-sonarr" not in texte
    assert reduit.services["sonarr"].api_key is None
    assert reduit.services["sonarr"].host_port == cfg.services["sonarr"].host_port


def test_les_identifiants_des_clients_de_telechargement_restent(tmp_path):
    """Sans eux, aucun debit : leurs API demandent a se connecter."""
    cfg = _cfg(tmp_path)
    cfg.services["qbittorrent"].password = "mot-de-passe-qbittorrent"
    cfg.services["sabnzbd"].api_key = "cle-api-de-sabnzbd"

    veille_config.ecrire(cfg)
    reduit, _ = migrations.lire(veille_config.chemin(cfg))

    assert reduit.services["qbittorrent"].password == "mot-de-passe-qbittorrent"
    assert reduit.services["sabnzbd"].api_key == "cle-api-de-sabnzbd"


def test_l_empreinte_du_mot_de_passe_reste_pour_la_page_de_connexion(tmp_path):
    """Sans mot de passe pose, la veille refuse d'ecouter ailleurs que sur
    127.0.0.1 : dans un conteneur, elle ne servirait donc a rien."""
    cfg = _cfg(tmp_path)

    veille_config.ecrire(cfg)
    reduit, _ = migrations.lire(veille_config.chemin(cfg))

    assert reduit.admin_password_hash == cfg.admin_password_hash


def test_la_veille_travaille_avec_le_fichier_reduit(tmp_path, monkeypatch):
    """La preuve qui compte : ce que la veille lit doit suffire a la faire
    fonctionner, adresses internes comprises."""
    cfg = _cfg(tmp_path)
    veille_config.ecrire(cfg)
    reduit, _ = migrations.lire(veille_config.chemin(cfg))
    monkeypatch.setattr(veille, "exec_in", lambda *a, **k: (True, "{}"))

    assert veille._adresse(reduit, "qbittorrent", True) == "http://gluetun:8080"
    assert veille._adresse(reduit, "sonarr", True) == "http://sonarr:8989"
    assert veille.conteneurs(reduit, interne=True) == []
    assert veille.disques(reduit) == veille.disques(cfg)


def test_l_original_n_est_pas_touche(tmp_path):
    """La reduction travaille sur une COPIE : la configuration en memoire sert
    ensuite a ecrire le vrai `stack.yml` et le compose."""
    cfg = _cfg(tmp_path)
    cle_sonarr = cfg.services["sonarr"].api_key

    veille_config.ecrire(cfg)

    assert cfg.vpn.wireguard_private_key == CLE_VPN
    assert cfg.vpn.openvpn_password == "secret-openvpn"
    assert cfg.services["sonarr"].api_key == cle_sonarr


@pytest.mark.skipif(os.name != "posix", reason="droits POSIX")
def test_le_fichier_n_est_lisible_que_par_son_proprietaire(tmp_path):
    cfg = _cfg(tmp_path)

    cible = veille_config.ecrire(cfg)

    assert oct(cible.stat().st_mode & 0o777) == "0o600"


# ------------------------------------------------------- service du compose


def test_le_service_de_veille_ne_peut_rien_changer(tmp_path):
    """Sa declaration doit porter les limites : pas de root, pas de socket,
    rien d'accessible en ecriture."""
    from plugarr import compose

    cfg = _cfg(tmp_path)
    cfg.veille_enabled = True

    bloc = compose.build_compose(cfg)["services"]["veille"]

    assert bloc["user"] == "${PUID}:${PGID}"
    assert all(montage.endswith(":ro") for montage in bloc["volumes"])
    assert bloc["read_only"] is True
    assert bloc["security_opt"] == ["no-new-privileges:true"]
    texte = str(bloc)
    assert "docker.sock" not in texte
    # Elle lit la configuration REDUITE, jamais le stack.yml du projet.
    assert f"${{CONFIG_ROOT}}/{veille_config.DOSSIER}" in bloc["command"]
    assert "@sha256:" in bloc["image"], "image epinglee par digest"


def test_sans_la_veille_aucun_conteneur_n_est_declare(tmp_path):
    from plugarr import compose

    cfg = _cfg(tmp_path)

    assert "veille" not in compose.build_compose(cfg)["services"]


def test_les_racines_sont_montees_a_leur_propre_chemin(tmp_path):
    """La veille mesure la place libre des dossiers que la configuration
    nomme : montes ailleurs, elle chercherait des chemins inexistants."""
    from plugarr import compose

    cfg = _cfg(tmp_path)
    cfg.veille_enabled = True

    volumes = compose.build_compose(cfg)["services"]["veille"]["volumes"]

    assert "${CONFIG_ROOT}:${CONFIG_ROOT}:ro" in volumes
    assert "${DATA_ROOT}:${DATA_ROOT}:ro" in volumes


def test_le_pre_semis_ecrit_la_configuration_reduite_seulement_si_demandee(tmp_path):
    avec, sans = _cfg(tmp_path / "a"), _cfg(tmp_path / "b")
    avec.veille_enabled = True

    orchestrator.seed_all(avec)
    orchestrator.seed_all(sans)

    assert veille_config.chemin(avec).exists()
    assert not veille_config.chemin(sans).exists()


# --------------------------------------------- console en conteneur (option)


def test_la_console_en_conteneur_dit_ce_qu_elle_prend(tmp_path):
    """Elle cree et recree des conteneurs : sans le socket elle ne sert a rien,
    et avec lui elle peut tout faire sur la machine. Sa declaration ne doit
    donc pas faire croire le contraire — pas de faux compte sans privilege,
    pas de montage en lecture seule qui donnerait le change."""
    from plugarr import compose

    cfg = _cfg(tmp_path)
    cfg.console_enabled = True

    bloc = compose.build_compose(cfg)["services"]["console"]

    assert "/var/run/docker.sock:/var/run/docker.sock" in bloc["volumes"]
    assert bloc["user"] == "0:0"
    # Le projet et les configurations sont en ECRITURE : faire tourner une cle
    # reecrit stack.yml. Les donnees, non : la console n'y touche jamais.
    assert "${PROJECT_DIR}:${PROJECT_DIR}" in bloc["volumes"]
    assert "${DATA_ROOT}:${DATA_ROOT}:ro" in bloc["volumes"]
    assert bloc["command"][0] == "serve"


def test_l_image_de_la_console_est_une_autre_que_celle_de_la_veille(tmp_path):
    """Celle de la veille n'a AUCUN client Docker : les confondre reviendrait a
    donner le socket a un service qui n'en a pas besoin."""
    from plugarr import catalog, compose

    cfg = _cfg(tmp_path)
    cfg.console_enabled = True
    cfg.veille_enabled = True
    services = compose.build_compose(cfg)["services"]

    assert services["console"]["image"] != services["veille"]["image"]
    assert services["console"]["image"] == catalog.CONSOLE_IMAGE
    assert catalog.CONSOLE_IMAGE.endswith("-admin") or "-admin@" in catalog.CONSOLE_IMAGE


def test_sans_l_option_aucune_console_en_conteneur(tmp_path):
    from plugarr import compose

    assert "console" not in compose.build_compose(_cfg(tmp_path))["services"]


def test_le_repertoire_du_projet_est_donne_au_env(tmp_path):
    """La console monte le projet a SON chemin de l'hote : le compose qu'elle
    lance porte des chemins de l'hote, executes par le demon de l'hote."""
    from plugarr import compose

    env = compose.render_env(_cfg(tmp_path), tmp_path / "projet")

    assert f"PROJECT_DIR='{(tmp_path / 'projet').resolve()}'" in env
    assert "PROJECT_DIR" not in compose.render_env(_cfg(tmp_path))
