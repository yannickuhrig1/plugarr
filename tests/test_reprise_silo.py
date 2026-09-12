"""Le volume de la base de Silo survit a une desinstallation. Il faut le savoir.

Panne reelle, trouvee en installant deux fois de suite depuis l'executable :

    docker compose down          -> les conteneurs partent, le VOLUME reste
    plugarr install             -> un nouveau SILO_POSTGRES_PASS est genere
    PostgreSQL demarre           -> il IGNORE POSTGRES_PASSWORD, sa base existe
    Silo                         -> « password authentication failed for user
                                     "silo" », redemarrage en boucle, sans fin

`POSTGRES_PASSWORD` n'est applique qu'au tout premier demarrage, celui qui cree
la base. Sur un volume deja rempli, l'image ne s'en sert pas et ne dit rien.

C'est le meme piege que les mots de passe haches de qBittorrent ou Jellyfin — un
secret que plugarr ne peut pas relire — sous une forme que la verification
d'origine ne voyait pas, parce qu'elle ne regardait que le disque.
"""

from __future__ import annotations

import pytest

from plugarr import compose, orchestrator, runner


def _cfg(nom="plugarr"):
    cfg = orchestrator.build_config(services=["silo"], config_root="/c", data_root="/d")
    cfg.project_name = nom
    return cfg


def test_le_nom_du_volume_suit_celui_du_projet():
    """Compose prefixe par le nom du projet : chercher `silo-pgdata` tout court
    ne trouverait jamais rien."""
    assert runner.volume_name("plugarr", compose.PG_VOLUME) == "plugarr_silo-pgdata"


def test_le_nom_du_projet_est_nettoye_comme_par_compose():
    """Compose retire tout ce qui n'est ni lettre, ni chiffre, ni _ ni -."""
    assert runner.volume_name("Ma Pile !", "v") == "MaPile_v"


def test_un_volume_present_compte_comme_configuration_existante(monkeypatch):
    monkeypatch.setattr(orchestrator, "volume_exists", lambda nom: True)

    assert "silo-postgres" in orchestrator.existing_configs(_cfg())


def test_un_volume_absent_laisse_l_installation_neuve(monkeypatch):
    monkeypatch.setattr(orchestrator, "volume_exists", lambda nom: False)

    assert "silo-postgres" not in orchestrator.existing_configs(_cfg())


def test_le_volume_rend_la_reprise_impossible(monkeypatch):
    """Son mot de passe ne se relit pas plus que celui de qBittorrent : la
    reprise doit etre refusee, pas tentee."""
    monkeypatch.setattr(orchestrator, "volume_exists", lambda nom: True)

    assert "silo-postgres" in orchestrator.unusable_configs(_cfg())


def test_la_remise_a_zero_supprime_le_volume(monkeypatch):
    supprimes = []
    monkeypatch.setattr(orchestrator, "volume_exists", lambda nom: True)
    monkeypatch.setattr(
        orchestrator, "remove_volume", lambda nom: (supprimes.append(nom), (True, ""))[1]
    )

    efface = orchestrator.reset_configs(_cfg(), ["silo-postgres"])

    assert supprimes == ["plugarr_silo-pgdata"]
    assert efface, "la remise a zero doit rendre compte de ce qu'elle a supprime"


def test_la_remise_a_zero_ne_touche_a_rien_si_le_volume_n_existe_pas(monkeypatch):
    supprimes = []
    monkeypatch.setattr(orchestrator, "volume_exists", lambda nom: False)
    monkeypatch.setattr(
        orchestrator, "remove_volume", lambda nom: (supprimes.append(nom), (True, ""))[1]
    )

    orchestrator.reset_configs(_cfg(), ["silo-postgres"])

    assert supprimes == []


def test_la_remise_a_zero_n_annonce_pas_un_volume_que_docker_refuse(monkeypatch):
    monkeypatch.setattr(orchestrator, "volume_exists", lambda nom: True)
    monkeypatch.setattr(
        orchestrator,
        "remove_volume",
        lambda nom: (False, "volume is in use"),
    )

    with pytest.raises(OSError, match="volume is in use"):
        orchestrator.reset_configs(_cfg(), ["silo-postgres"])


def test_l_emplacement_annonce_est_le_vrai():
    """Le message disait « C:/config/silo-postgres », un dossier qui n'existe
    pas : l'utilisateur allait y chercher, ne trouvait rien, et doutait de
    l'avertissement entier."""
    cfg = _cfg("plugarr-essai")

    assert orchestrator.emplacement_etat(cfg, "silo-postgres") == (
        "volume Docker plugarr-essai_silo-pgdata"
    )


def test_les_autres_services_gardent_leur_dossier():
    cfg = orchestrator.build_config(
        services=["jellyfin"], config_root="C:/x/config", data_root="/d"
    )

    assert orchestrator.emplacement_etat(cfg, "jellyfin") == "C:/x/config/jellyfin"
