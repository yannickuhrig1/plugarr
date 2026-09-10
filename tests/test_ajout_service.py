"""Ajouter un service absent de l'installation initiale.

Une stack grandit. Jusqu'ici, ajouter Lidarr six mois plus tard imposait de
relancer l'installation entiere en cochant tout — avec le risque, connu et
documente, de perdre les mots de passe des services qui ne stockent que des
empreintes.

Ce que ces tests verrouillent, c'est surtout ce que l'ajout ne doit PAS faire :
arreter des conteneurs, reecrire des configurations en marche, ou toucher a un
secret existant.
"""

from __future__ import annotations

import pytest

from plugarr import catalog, dashboard, orchestrator


@pytest.fixture
def cfg():
    return orchestrator.build_config(
        services=["sonarr", "qbittorrent"], config_root="/c", data_root="/d"
    )


# ------------------------------------------------------------- ce qui manque


def test_les_services_absents_sont_listes(cfg):
    absents = orchestrator.installable(cfg)

    assert "radarr" in absents
    assert "jellyfin" in absents
    assert "sonarr" not in absents
    assert "qbittorrent" not in absents


def test_l_ordre_de_demarrage_est_respecte(cfg):
    """La liste est affichee telle quelle : elle doit se lire comme le reste."""
    absents = orchestrator.installable(cfg)

    assert absents == [s for s in catalog.STARTUP_ORDER if s in absents]


def test_une_stack_complete_ne_propose_rien():
    complete = orchestrator.build_config(
        services=list(catalog.CATALOG), config_root="/c", data_root="/d"
    )

    assert orchestrator.installable(complete) == []


# ---------------------------------------------------------------- garde-fous


def test_un_service_inconnu_est_refuse(cfg, tmp_path):
    ok, message, ajoutes = orchestrator.add_service(cfg, tmp_path, "nexiste-pas")

    assert ok is False
    assert "inconnu" in message
    assert ajoutes == []


def test_un_service_deja_installe_est_refuse(cfg, tmp_path):
    ok, message, ajoutes = orchestrator.add_service(cfg, tmp_path, "sonarr")

    assert ok is False
    assert "deja installe" in message
    assert ajoutes == []


def test_un_refus_ne_modifie_pas_la_configuration(cfg, tmp_path):
    avant = set(cfg.services)

    orchestrator.add_service(cfg, tmp_path, "sonarr")
    orchestrator.add_service(cfg, tmp_path, "nexiste-pas")

    assert set(cfg.services) == avant


# ------------------------------------------------------------- la fabrique


def test_un_service_ajoute_est_identique_a_un_service_installe(cfg):
    """Deux fabriques auraient fini par diverger, et la difference ne se serait
    vue que chez quelqu'un dont la stack a grandi."""
    ajoute = orchestrator.new_instance(cfg, "radarr")
    installe = orchestrator.build_config(
        services=["radarr"], config_root="/c", data_root="/d"
    ).services["radarr"]

    assert ajoute.spec_id == installe.spec_id
    assert ajoute.host_port == installe.host_port
    assert ajoute.image == installe.image
    assert ajoute.username == installe.username
    assert bool(ajoute.api_key) == bool(installe.api_key)
    assert bool(ajoute.password) == bool(installe.password)


def test_les_secrets_sont_neufs(cfg):
    """Reutiliser le secret d'un autre service serait une faute silencieuse."""
    un = orchestrator.new_instance(cfg, "radarr")
    deux = orchestrator.new_instance(cfg, "lidarr")

    assert un.api_key != deux.api_key
    assert un.password != deux.password
    assert un.api_key != cfg.services["sonarr"].api_key


def test_un_service_sans_compte_n_en_recoit_pas(cfg):
    """Recyclarr n'a pas d'interface : lui inventer un mot de passe n'aurait
    aucun sens et brouillerait la page d'acces."""
    recyclarr = orchestrator.new_instance(cfg, "recyclarr")

    assert recyclarr.password is None or recyclarr.password == ""
    assert recyclarr.api_key is None or recyclarr.api_key == ""


# ------------------------------------------------------------------ la page


def test_la_section_n_existe_que_sur_la_page_pilotee(cfg):
    assert "Ajouter un service" in dashboard.render(cfg, live=True)
    assert "Ajouter un service" not in dashboard.render(cfg, live=False)


def test_chaque_service_absent_a_son_bouton(cfg):
    page = dashboard.render(cfg, live=True)

    for sid in orchestrator.installable(cfg):
        assert f'data-add="{sid}"' in page
        assert f'class="install" data-service="{sid}"' in page


def test_un_service_installe_n_a_pas_de_bouton_installer(cfg):
    page = dashboard.render(cfg, live=True)

    assert 'data-add="sonarr"' not in page
    assert 'class="install" data-service="sonarr"' not in page


def test_les_prerequis_sont_annonces():
    """Cocher Flood tire son client par défaut : l'écrire évite la surprise."""
    seul = orchestrator.build_config(services=["sonarr"], config_root="/c", data_root="/d")
    page = dashboard.render(seul, live=True)

    debut = page.index('data-add="flood"')
    carte = page[debut : page.index("</article>", debut)]
    assert "tirera aussi" in carte
    assert "qBittorrent" in carte


def test_une_stack_complete_n_affiche_pas_la_section():
    complete = orchestrator.build_config(
        services=list(catalog.CATALOG), config_root="/c", data_root="/d"
    )

    assert "Ajouter un service" not in dashboard.render(complete, live=True)
