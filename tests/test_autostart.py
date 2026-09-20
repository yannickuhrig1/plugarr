"""Lancement automatique de la console, sur l'hote.

Pas dans un conteneur, et ce n'est pas un detail de mise en oeuvre. La console
doit creer, demarrer et recreer des conteneurs — soit `POST /containers/create`
puis `/start`. Or un conteneur qu'on cree peut monter la racine de l'hote et
tourner en root : un proxy de socket qui autorise ces deux appels n'enferme
rien, et sans eux la console ne sert plus a rien.

Sur l'hote, elle tourne sous le compte de l'utilisateur, ecoute sur 127.0.0.1
et reste hors du reseau Docker. Le confort recherche est le meme.
"""

from __future__ import annotations

import pytest

from plugarr import autostart

# ------------------------------------------------------------------ commande


def test_la_commande_vise_le_bon_repertoire(tmp_path):
    ligne = autostart.commande(tmp_path, host="127.0.0.1", port=7373)

    assert str(tmp_path.resolve()) in ligne
    assert "serve" in ligne


def test_la_commande_n_ouvre_pas_de_navigateur(tmp_path):
    """Ouvrir un navigateur a chaque ouverture de session serait insupportable."""
    assert "--no-open" in autostart.commande(tmp_path, host="127.0.0.1", port=7373)


def test_la_commande_reprend_l_interpreteur_courant(tmp_path):
    """Quelqu'un qui a double-clique un executable n'a pas `plugarr` dans son
    PATH : lui dire « lancez plugarr serve » ne l'avance a rien."""
    import sys

    assert sys.executable in autostart.commande(tmp_path, host="127.0.0.1", port=7373)


def test_l_interpreteur_d_un_environnement_virtuel_n_est_pas_resolu(tmp_path, monkeypatch):
    """Dans un venv, `bin/python3` est un LIEN vers l'interpreteur du systeme.
    Le resoudre sort du venv : l'unite lancait `/usr/bin/python3 -m plugarr`,
    qui repondait « No module named plugarr ». Constate sur le banc, le service
    redemarrait en boucle."""
    import sys

    venv = tmp_path / "venv" / "bin" / "python3"
    venv.parent.mkdir(parents=True)
    venv.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(venv))

    ligne = autostart.commande(tmp_path, host="127.0.0.1", port=7373)

    assert str(venv) in ligne


def test_l_adresse_et_le_port_sont_repris(tmp_path):
    ligne = autostart.commande(tmp_path, host="0.0.0.0", port=9999)

    assert "--host 0.0.0.0" in ligne
    assert "--port 9999" in ligne


def test_un_chemin_avec_espaces_est_protege(tmp_path):
    """« Arr auto install » contient des espaces : sans guillemets, la commande
    se coupe en deux au demarrage."""
    dossier = tmp_path / "un dossier avec espaces"
    dossier.mkdir()

    ligne = autostart.commande(dossier, host="127.0.0.1", port=7373)

    assert f'"{dossier.resolve()}"' in ligne


# ------------------------------------------------------------------- Windows


@pytest.fixture
def demarrage_windows(tmp_path, monkeypatch):
    """Simule Windows, avec un dossier Demarrage jetable."""
    monkeypatch.setattr(autostart.sys, "platform", "win32")
    dossier = tmp_path / "Startup"
    monkeypatch.setattr(autostart, "_dossier_demarrage", lambda: dossier)
    return dossier


def test_windows_pose_un_script_dans_le_dossier_demarrage(demarrage_windows, tmp_path):
    ok, message = autostart.enable(tmp_path, host="127.0.0.1", port=7373)

    cible = demarrage_windows / "plugarr-console.cmd"
    assert ok
    assert cible.is_file()
    assert str(cible) in message


def test_le_script_windows_est_lisible_et_explique_comment_le_retirer(
    demarrage_windows, tmp_path
):
    """Il atterrit dans le dossier Demarrage de quelqu'un : il doit dire d'ou il
    vient et comment s'en debarrasser."""
    autostart.enable(tmp_path, host="127.0.0.1", port=7373)
    contenu = (demarrage_windows / "plugarr-console.cmd").read_text(encoding="utf-8")

    assert "plugarr autostart" in contenu
    assert "Supprimez ce fichier" in contenu
    assert "serve" in contenu


def test_windows_signale_l_etat(demarrage_windows, tmp_path):
    assert autostart.status(tmp_path).actif is False

    autostart.enable(tmp_path, host="127.0.0.1", port=7373)

    etat = autostart.status(tmp_path)
    assert etat.actif is True
    assert etat.mecanisme == "demarrage-windows"


def test_windows_retire_le_script(demarrage_windows, tmp_path):
    autostart.enable(tmp_path, host="127.0.0.1", port=7373)

    ok, _message = autostart.disable(tmp_path)

    assert ok
    assert not (demarrage_windows / "plugarr-console.cmd").exists()
    assert autostart.status(tmp_path).actif is False


def test_retirer_ce_qui_n_existe_pas_n_est_pas_une_erreur(demarrage_windows, tmp_path):
    ok, message = autostart.disable(tmp_path)

    assert ok
    assert "aucun" in message.lower()


def test_reinstaller_ecrase_sans_broncher(demarrage_windows, tmp_path):
    autostart.enable(tmp_path, host="127.0.0.1", port=7373)
    ok, _message = autostart.enable(tmp_path, host="127.0.0.1", port=8888)

    contenu = (demarrage_windows / "plugarr-console.cmd").read_text(encoding="utf-8")
    assert ok
    assert "--port 8888" in contenu
    assert "--port 7373" not in contenu


# ------------------------------------------------------------------ systemd


def test_l_unite_systemd_a_la_forme_attendue(tmp_path):
    unite = autostart._unite_systemd("/bin/plugarr serve", tmp_path)

    assert "[Unit]" in unite and "[Service]" in unite and "[Install]" in unite
    assert "ExecStart=/bin/plugarr serve" in unite
    # Sans redemarrage, une console tombee reste tombee jusqu'a la prochaine
    # ouverture de session.
    assert "Restart=on-failure" in unite
    assert "After=docker.service" in unite


# ----------------------------------------------------- plateforme inconnue


def test_une_plateforme_inconnue_rend_la_commande_a_coller(tmp_path, monkeypatch):
    """Unraid n'a pas de systemd. Inventer un mecanisme non verifie serait pire
    que de rendre la main."""
    monkeypatch.setattr(autostart.sys, "platform", "freebsd")
    monkeypatch.setattr(autostart.shutil, "which", lambda _nom: None)

    ok, message = autostart.enable(tmp_path, host="127.0.0.1", port=7373)

    assert ok is False
    assert "serve" in message
    assert str(tmp_path.resolve()) in message


def test_une_plateforme_inconnue_ne_pretend_pas_avoir_installe(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart.sys, "platform", "freebsd")
    monkeypatch.setattr(autostart.shutil, "which", lambda _nom: None)

    assert autostart.status(tmp_path).actif is False
    assert autostart.mecanisme() == "aucun"


# ------------------------------------------------------------ portee systeme


def test_l_unite_systeme_demarre_avec_la_machine_et_nomme_son_compte(tmp_path):
    """Une unite utilisateur s'arrete a la deconnexion et ne demarre qu'a
    l'ouverture de session : elle ne couvre pas un serveur ou personne ne se
    connecte, qui est justement le cas de l'administration a distance."""
    unite = autostart._unite_systemd("plugarr serve", tmp_path, "mediatheque")

    assert "WantedBy=multi-user.target" in unite
    assert "User=mediatheque" in unite
    # Sans cela, la console demarre avant Docker et ne voit aucun conteneur.
    assert "After=docker.service" in unite


def test_l_unite_utilisateur_ne_nomme_aucun_compte(tmp_path):
    """Elle tourne deja sous celui qui ouvre la session."""
    unite = autostart._unite_systemd("plugarr serve", tmp_path)

    assert "User=" not in unite
    assert "WantedBy=default.target" in unite


def test_sans_root_l_installation_systeme_refuse_et_dit_comment(tmp_path, monkeypatch):
    import os

    monkeypatch.setattr(autostart, "mecanisme", lambda portee="utilisateur": "systemd-systeme")
    monkeypatch.setattr(os, "geteuid", lambda: 1000, raising=False)

    ok, message = autostart.enable(tmp_path, portee="systeme")

    assert ok is False
    assert "sudo" in message


def test_sans_proprietaire_connu_l_unite_n_est_pas_ecrite(tmp_path, monkeypatch):
    """L'unite tournerait alors sous un compte devine : mieux vaut refuser."""
    import os

    ecrits = []
    monkeypatch.setattr(autostart, "mecanisme", lambda portee="utilisateur": "systemd-systeme")
    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(autostart, "_proprietaire", lambda chemin: "")
    monkeypatch.setattr(autostart, "_systemctl", lambda *a, **k: ecrits.append(a) or (True, ""))

    ok, message = autostart.enable(tmp_path, portee="systeme")

    assert ok is False and "stack.yml" in message
    assert ecrits == []


def test_la_portee_systeme_n_est_pas_celle_par_defaut(tmp_path, monkeypatch):
    """Le cas courant reste le poste de travail : rien ne doit demander root
    sans qu'on l'ait ecrit."""
    monkeypatch.setattr(autostart.shutil, "which", lambda nom: "/usr/bin/systemctl")
    monkeypatch.setattr(autostart.sys, "platform", "linux")

    assert autostart.mecanisme() == "systemd-utilisateur"
    assert autostart.mecanisme("systeme") == "systemd-systeme"
