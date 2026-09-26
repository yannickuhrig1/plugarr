"""Cle du serveur de controle de Gluetun, posee dans `/gluetun/auth/config.toml`.

Mesure le 2026-09-19 sur Gluetun v3.41.3 : avec ce fichier, les routes lues
par PlugArr repondent 401 sans cle ou avec une mauvaise, 200 avec la bonne.
"""

from __future__ import annotations

import shutil
import subprocess
import tomllib

import pytest

from plugarr import gluetun_auth, orchestrator


def _cfg(tmp_path, vpn=True):
    cfg = orchestrator.build_config(
        services=["sonarr", "qbittorrent"], config_root=str(tmp_path / "c"), data_root=str(tmp_path / "d")
    )
    cfg.vpn.enabled = vpn
    return cfg


def test_le_role_couvre_les_deux_routes_lues_par_plugarr(tmp_path):
    cfg = _cfg(tmp_path)

    assert gluetun_auth.assurer(cfg)[0] is True
    roles = tomllib.loads(gluetun_auth.chemin(cfg).read_text(encoding="utf-8"))["roles"]

    assert roles == [{
        "name": "plugarr",
        "routes": ["GET /v1/publicip/ip", "GET /v1/portforward"],
        "auth": "apikey",
        "apikey": gluetun_auth.cle(cfg),
    }]
    assert len(gluetun_auth.cle(cfg)) >= 30


def test_la_cle_ne_change_pas_d_une_installation_a_l_autre(tmp_path):
    cfg = _cfg(tmp_path)
    gluetun_auth.assurer(cfg)
    premiere = gluetun_auth.cle(cfg)

    assert gluetun_auth.assurer(cfg)[0] is False
    assert gluetun_auth.cle(cfg) == premiere


def test_les_roles_de_l_utilisateur_sont_gardes(tmp_path):
    cfg = _cfg(tmp_path)
    fichier = gluetun_auth.chemin(cfg)
    fichier.parent.mkdir(parents=True)
    fichier.write_text(
        '[[roles]]\nname = "moi"\nroutes = ["PUT /v1/vpn/status"]\nauth = "basic"\n'
        'username = "a"\npassword = "b"\n',
        encoding="utf-8",
    )

    gluetun_auth.assurer(cfg)
    roles = tomllib.loads(fichier.read_text(encoding="utf-8"))["roles"]

    assert [r["name"] for r in roles] == ["moi", "plugarr"]
    assert roles[0]["password"] == "b"


def test_un_fichier_illisible_n_est_pas_touche(tmp_path):
    cfg = _cfg(tmp_path)
    fichier = gluetun_auth.chemin(cfg)
    fichier.parent.mkdir(parents=True)
    fichier.write_text("[[roles]\ncasse", encoding="utf-8")

    ecrit, message = gluetun_auth.assurer(cfg)

    assert ecrit is False and "illisible" in message
    assert fichier.read_text(encoding="utf-8") == "[[roles]\ncasse"


def test_le_pre_semis_pose_le_role_seulement_avec_un_vpn(tmp_path):
    avec, sans = _cfg(tmp_path / "a"), _cfg(tmp_path / "b", vpn=False)

    orchestrator.seed_all(avec)
    orchestrator.seed_all(sans)

    assert gluetun_auth.cle(avec)
    assert not gluetun_auth.chemin(sans).exists()


@pytest.mark.skipif(shutil.which("sh") is None, reason="pas de sh")
def test_gluetun_relit_la_cle_sur_place(tmp_path):
    """L'extrait `sed` tourne dans Gluetun : il doit trouver la cle du role
    PlugArr, et celle-la seulement, meme apres un role de l'utilisateur."""
    cfg = _cfg(tmp_path)
    fichier = gluetun_auth.chemin(cfg)
    fichier.parent.mkdir(parents=True)
    fichier.write_text(
        '[[roles]]\nname = "moi"\nroutes = ["GET /v1/vpn/status"]\nauth = "apikey"\n'
        'apikey = "cle-de-l-utilisateur"\n',
        encoding="utf-8",
    )
    gluetun_auth.assurer(cfg)
    script = gluetun_auth.LIRE_CLE_SH.replace(
        gluetun_auth.FICHIER_CONTENEUR, fichier.as_posix()
    )

    sortie = subprocess.run(
        ["sh", "-c", script + '; printf %s "$K"'], capture_output=True, text=True, check=True
    ).stdout

    assert sortie == gluetun_auth.cle(cfg)


def test_le_fichier_est_ecrit_en_lf_meme_sous_windows(tmp_path):
    """Essai reel du 26/09/2026 sous Windows : fichier en CRLF, cle relue vide
    dans Gluetun, 401 sur /v1/portforward et « aucun port obtenu » a tort."""
    cfg = _cfg(tmp_path)

    gluetun_auth.assurer(cfg)

    assert b"\r" not in gluetun_auth.chemin(cfg).read_bytes()


def test_un_fichier_crlf_existant_passe_en_lf_sans_autre_changement(tmp_path):
    cfg = _cfg(tmp_path)
    fichier = gluetun_auth.chemin(cfg)
    fichier.parent.mkdir(parents=True)
    fichier.write_bytes(
        b'[[roles]]\r\nname = "plugarr"\r\nroutes = ["GET /v1/portforward"]\r\n'
        b'auth = "apikey"\r\napikey = "cle-en-crlf"\r\n'
    )

    assert gluetun_auth.assurer(cfg)[0] is False
    assert fichier.read_bytes() == (
        b'[[roles]]\nname = "plugarr"\nroutes = ["GET /v1/portforward"]\n'
        b'auth = "apikey"\napikey = "cle-en-crlf"\n'
    )


@pytest.mark.skipif(shutil.which("sh") is None, reason="pas de sh")
def test_la_cle_est_relue_dans_un_fichier_crlf(tmp_path):
    """Un fichier deja ecrit en CRLF par une version precedente reste lisible.

    Le `sed` de Git pour Windows ignore deja les CR : sous Windows ce test passe
    meme sans le correctif. Il porte sur le `sed` de busybox, celui de Gluetun,
    et c'est sous Linux qu'il fait foi."""
    cfg = _cfg(tmp_path)
    fichier = gluetun_auth.chemin(cfg)
    fichier.parent.mkdir(parents=True)
    fichier.write_bytes(
        b'[[roles]]\r\nname = "plugarr"\r\nroutes = ["GET /v1/portforward"]\r\n'
        b'auth = "apikey"\r\napikey = "cle-en-crlf"\r\n'
    )
    script = gluetun_auth.LIRE_CLE_SH.replace(
        gluetun_auth.FICHIER_CONTENEUR, fichier.as_posix()
    )

    sortie = subprocess.run(
        ["sh", "-c", script + '; printf %s "$K"'], capture_output=True, text=True, check=True
    ).stdout

    assert sortie == "cle-en-crlf"


def test_le_fichier_est_donne_a_puid_pgid_pour_la_veille(tmp_path, monkeypatch):
    """La veille tourne sous PUID:PGID ; ecrit par root en 600, le fichier lui
    restait illisible (constate sur le banc : 401 de Gluetun)."""
    import os

    from plugarr import layout

    attribues = []
    monkeypatch.setattr(layout, "_est_root", lambda: True)
    monkeypatch.setattr(os, "chown", lambda p, u, g, **k: attribues.append((str(p), u, g)),
                        raising=False)
    cfg = _cfg(tmp_path)
    cfg.puid, cfg.pgid = 1000, 1001

    gluetun_auth.assurer(cfg)

    assert (str(gluetun_auth.chemin(cfg)), 1000, 1001) in attribues
    assert (str(gluetun_auth.chemin(cfg).parent), 1000, 1001) in attribues
