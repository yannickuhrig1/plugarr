"""Renouvellement d'un mot de passe depuis la page d'administration.

Le changement lui-meme est la partie facile. Ce qui compte est le RECABLAGE :
un mot de passe de client de telechargement change a la main casse six liaisons
en silence — les quatre *arr, Prowlarr et autobrr gardent l'ancien, leur bouton
Test echoue, et rien ne l'explique.

Verifie en conditions reelles sur une stack de onze services : apres rotation
du mot de passe qBittorrent, 24 liaisons sur 25 se realignaient toutes seules.
La vingt-cinquieme, autobrr, gardait l'ancien et repondait :

    error logging into client: http://qbittorrent:8080:
    login error; status code: 401

C'etait le seul angle mort : les *arr sont realignes par `sync_fields`, autobrr
ne l'etait par personne.
"""

from __future__ import annotations

import pytest

from plugarr import catalog, orchestrator, seed
from plugarr.clients.autobrr import AutobrrClient

# ------------------------------------------------------------- garde-fous


@pytest.fixture
def cfg():
    return orchestrator.build_config(
        services=["sonarr", "qbittorrent", "jellyfin"],
        config_root="/c",
        data_root="/d",
    )


def test_un_service_inconnu_est_refuse(cfg, tmp_path):
    ok, message, secret = orchestrator.rotate_password(cfg, tmp_path, "nexiste-pas")

    assert ok is False
    assert "inconnu" in message
    assert secret == ""


def test_un_service_hors_liste_est_refuse(cfg, tmp_path):
    """Jellyfin n'a pas de chemin verifie : mieux vaut refuser que casser."""
    ok, message, secret = orchestrator.rotate_password(cfg, tmp_path, "jellyfin")

    assert ok is False
    assert "ne sait pas changer son mot de passe" in message
    assert secret == ""


def test_la_liste_des_familles_est_fermee():
    """Chaque entree correspond a un chemin verifie contre le service."""
    assert catalog.ROTATABLE_FAMILIES == ("arr", "qbittorrent", "transmission")
    assert orchestrator.ROTATABLE is catalog.ROTATABLE_FAMILIES


def test_un_echec_ne_revele_aucun_secret(cfg, tmp_path):
    """Le mot de passe n'est renvoye qu'en cas de succes : un appelant qui
    l'affiche ne doit jamais montrer une valeur qui n'a pas ete posee."""
    _ok, _message, secret = orchestrator.rotate_password(cfg, tmp_path, "jellyfin")

    assert secret == ""


def test_le_mot_de_passe_du_service_est_inchange_si_le_changement_echoue(cfg, tmp_path):
    avant = cfg.services["qbittorrent"].password
    # Le service ne repond pas : aucun conteneur ne tourne dans un test.
    orchestrator.rotate_password(cfg, tmp_path, "qbittorrent")

    assert cfg.services["qbittorrent"].password == avant


# ----------------------------------------------------- l'angle mort autobrr


class _FauxAutobrr(AutobrrClient):
    """Journalise les appels au lieu de les emettre."""

    def __init__(self, existants):
        self._existants = existants
        self.appels: list[tuple[str, str, dict]] = []
        self.name = "autobrr"
        # Route d'autobrr >= v1.87.0, deja connue : pas de sondage a journaliser.
        self._chemin_clients = "/api/downloaders"

    def clients(self):
        return self._existants

    def _request(self, method, path, **kw):
        self.appels.append((method, path, kw.get("json") or {}))

        class _Reponse:
            status_code = 200
            text = ""

        return _Reponse()

    def _expect(self, resp, path, *ok):
        return resp


ENTREE = {
    "id": 3,
    "name": "qBittorrent",
    "type": "QBITTORRENT",
    "enabled": True,
    "host": "http://qbittorrent:8080",
    "username": "yannick",
    "password": "ancien",
    "settings": {},
}


def test_un_mot_de_passe_change_est_pousse_dans_autobrr():
    client = _FauxAutobrr([dict(ENTREE)])

    cree, message = client.ensure_client(
        name="qBittorrent",
        service_id="qbittorrent",
        host="http://qbittorrent:8080",
        username="yannick",
        password="nouveau",
    )

    assert cree is False
    assert message == "identifiants mis a jour"
    methode, chemin, corps = client.appels[0]
    # PUT sur la COLLECTION : autobrr declare `r.Put("/", h.update)`, et
    # `/{id}` n'accepte que GET et DELETE — il repondait 405.
    assert (methode, chemin) == ("PUT", "/api/downloaders")
    assert corps["id"] == 3
    assert corps["password"] == "nouveau"


def test_une_entree_identique_n_est_pas_reecrite():
    """Rejouer le cablage ne doit produire aucune ecriture inutile."""
    client = _FauxAutobrr([dict(ENTREE)])

    cree, message = client.ensure_client(
        name="qBittorrent",
        service_id="qbittorrent",
        host="http://qbittorrent:8080",
        username="yannick",
        password="ancien",
    )

    assert (cree, message) == (False, "deja present")
    assert client.appels == []


def test_une_entree_absente_est_creee():
    client = _FauxAutobrr([])

    cree, message = client.ensure_client(
        name="qBittorrent",
        service_id="qbittorrent",
        host="http://qbittorrent:8080",
        username="yannick",
        password="nouveau",
    )

    assert (cree, message) == (True, "cree")
    assert client.appels[0][0] == "POST"


def test_un_changement_d_adresse_est_aussi_repris():
    """Le passage derriere un VPN change l'hote du client."""
    client = _FauxAutobrr([dict(ENTREE)])

    client.ensure_client(
        name="qBittorrent",
        service_id="qbittorrent",
        host="http://gluetun:8080",
        username="yannick",
        password="ancien",
    )

    assert client.appels[0][2]["host"] == "http://gluetun:8080"


# ------------------------------------------------------------ le bouton


def test_le_bouton_n_apparait_que_sur_la_page_pilotee():
    """La page statique n'execute rien : un bouton mort y serait pire que rien."""
    from plugarr import dashboard

    cfg = orchestrator.build_config(
        services=["sonarr", "qbittorrent"], config_root="/c", data_root="/d"
    )

    assert 'class="rotate"' not in dashboard.render(cfg, live=False)
    assert 'class="rotate"' in dashboard.render(cfg, live=True)


def test_le_bouton_ne_s_affiche_que_pour_les_familles_traitees():
    from plugarr import dashboard

    cfg = orchestrator.build_config(
        services=["jellyfin", "qbittorrent"], config_root="/c", data_root="/d"
    )
    page = dashboard.render(cfg, live=True)

    assert 'data-service="qbittorrent"' in page
    assert page.count('class="rotate"') == 1, "jellyfin ne doit pas en avoir"


def test_une_entree_sans_identifiant_est_laissee_tranquille():
    """On ne peut pas designer ce qu'on ne sait pas nommer : ne rien faire vaut
    mieux qu'un appel qui echouerait."""
    client = _FauxAutobrr([{"name": "qBittorrent", "type": "QBITTORRENT"}])

    cree, message = client.ensure_client(
        name="qBittorrent",
        service_id="qbittorrent",
        host="http://qbittorrent:8080",
        username="yannick",
        password="nouveau",
    )

    assert (cree, message) == (False, "deja present")
    assert client.appels == []


# ------------------------------------------------------------- la cle API


CONFIG_XML = """<Config>
  <BindAddress>*</BindAddress>
  <Port>8989</Port>
  <ApiKey>c3829ffb4c844cf88a607996efc459f1</ApiKey>
  <AuthenticationMethod>Forms</AuthenticationMethod>
  <InstanceName>Sonarr</InstanceName>
</Config>
"""


def test_la_cle_est_remplacee_dans_le_config_xml(tmp_path):
    (tmp_path / "config.xml").write_text(CONFIG_XML, encoding="utf-8")

    assert seed.replace_arr_api_key(tmp_path, "f" * 32) is True

    texte = (tmp_path / "config.xml").read_text(encoding="utf-8")
    assert f"<ApiKey>{'f' * 32}</ApiKey>" in texte
    assert "c3829ffb" not in texte


def test_le_reste_du_fichier_est_intact(tmp_path):
    """Apres son premier demarrage, config.xml contient bien plus que la cle :
    le regenerer effacerait tout le reste."""
    (tmp_path / "config.xml").write_text(CONFIG_XML, encoding="utf-8")

    seed.replace_arr_api_key(tmp_path, "f" * 32)

    texte = (tmp_path / "config.xml").read_text(encoding="utf-8")
    for garde in ("<Port>8989</Port>", "<AuthenticationMethod>Forms<", "<InstanceName>Sonarr<"):
        assert garde in texte


def test_un_fichier_absent_est_signale(tmp_path):
    assert seed.replace_arr_api_key(tmp_path, "f" * 32) is False


def test_un_fichier_sans_cle_est_signale(tmp_path):
    (tmp_path / "config.xml").write_text("<Config><Port>8989</Port></Config>", encoding="utf-8")

    assert seed.replace_arr_api_key(tmp_path, "f" * 32) is False


def test_seuls_les_arr_ont_une_cle_renouvelable(cfg, tmp_path):
    """Celle de Jellyfin est emise par Jellyfin, pas choisie par plugarr."""
    ok, message, secret = orchestrator.rotate_api_key(cfg, tmp_path, "jellyfin")

    assert ok is False
    assert "n'a pas de cle API geree par plugarr" in message
    assert secret == ""


def test_un_config_xml_introuvable_arrete_tout(cfg, tmp_path):
    """Sans reecriture reussie, on ne redemarre rien et on ne touche a rien."""
    avant = cfg.services["sonarr"].api_key
    ok, message, _secret = orchestrator.rotate_api_key(cfg, tmp_path, "sonarr")

    assert ok is False
    assert "config.xml" in message
    assert cfg.services["sonarr"].api_key == avant


def test_le_bouton_de_cle_ne_vise_que_les_arr():
    from plugarr import dashboard

    config = orchestrator.build_config(
        services=["sonarr", "qbittorrent", "jellyfin"], config_root="/c", data_root="/d"
    )
    page = dashboard.render(config, live=True)

    assert page.count('data-what="api_key"') == 1
    assert 'data-service="sonarr" data-what="api_key"' in page
