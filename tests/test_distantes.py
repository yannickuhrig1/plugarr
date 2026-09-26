"""Les installations distantes que ce poste retient : des coordonnees, jamais un secret."""

from __future__ import annotations

from types import SimpleNamespace

import yaml

from plugarr import distantes, orchestrator, remote_install


def _distante(**extra) -> distantes.Distante:
    valeurs = {
        "host": "nas.local",
        "port": 22,
        "user": "yannick",
        "empreinte": "SHA256:abc",
        "project_dir": "/home/yannick/plugarr",
        "console_port": 7373,
        "uid": 1000,
        "gid": 1000,
    }
    valeurs.update(extra)
    return distantes.Distante(**valeurs)


def test_une_distante_enregistree_se_relit():
    distantes.enregistrer(_distante())

    [relue] = distantes.lire()

    assert relue.host == "nas.local"
    assert relue.empreinte == "SHA256:abc"
    assert relue.console_port == 7373
    assert relue.date


def test_l_identifiant_est_stable_et_distingue_les_dossiers():
    assert _distante().ident == _distante().ident
    assert _distante().ident != _distante(project_dir="/srv/autre").ident
    assert _distante().ident.startswith("ssh-")


def test_reenregistrer_remplace_et_garde_le_nom_choisi():
    distantes.enregistrer(_distante())
    distantes.renommer(_distante().ident, "  NAS   du salon ")
    distantes.enregistrer(_distante(empreinte="SHA256:nouvelle"))

    [relue] = distantes.lire()

    assert relue.nom == "NAS du salon"
    assert relue.empreinte == "SHA256:nouvelle"


def test_oublier_retire_seulement_la_bonne_entree():
    distantes.enregistrer(_distante())
    distantes.enregistrer(_distante(host="vps.exemple.fr"))

    assert distantes.oublier(_distante().ident)
    assert [d.host for d in distantes.lire()] == ["vps.exemple.fr"]
    assert not distantes.oublier(_distante().ident)


def test_une_entree_abimee_est_ignoree():
    distantes.chemin().parent.mkdir(parents=True, exist_ok=True)
    distantes.chemin().write_text(
        yaml.safe_dump(
            {
                "distantes": [
                    {"host": "", "user": "x", "project_dir": "/a"},
                    {"host": "h", "user": "u", "project_dir": "relatif"},
                    "texte",
                    {"host": "ok", "user": "u", "project_dir": "/srv", "port": "pas un port"},
                ]
            }
        ),
        encoding="utf-8",
    )

    [seule] = distantes.lire()

    assert seule.host == "ok"
    assert seule.port == 22


def test_un_fichier_illisible_vaut_une_liste_vide():
    distantes.chemin().parent.mkdir(parents=True, exist_ok=True)
    distantes.chemin().write_text(": : :\n\t", encoding="utf-8")

    assert distantes.lire() == []


def test_l_assistant_retient_le_serveur_apres_une_installation_reussie(tmp_path):
    """Sans secret : ni mot de passe SSH, ni cle, ni identifiant de service."""
    from plugarr import webwizard

    cfg = orchestrator.build_config(
        services=["sonarr", "jellyfin"], config_root="/srv/config", data_root="/srv/data"
    )
    cfg.console_enabled = True
    cfg.console_port = 7473
    etat = SimpleNamespace(cfg=cfg, remote_project_dir="/home/yannick/plugarr")
    cible = remote_install.RemoteTarget(
        host="192.168.1.20", port=2222, username="yannick", expected_fingerprint="SHA256:xyz"
    )

    webwizard.WizardState._retenir_distante(etat, cible)

    [retenue] = distantes.lire()
    assert (retenue.host, retenue.port, retenue.user) == ("192.168.1.20", 2222, "yannick")
    assert retenue.empreinte == "SHA256:xyz"
    assert retenue.console_port == 7473
    contenu = distantes.chemin().read_text(encoding="utf-8")
    for instance in cfg.services.values():
        for secret in (instance.password, instance.api_key):
            if secret:
                assert secret not in contenu
