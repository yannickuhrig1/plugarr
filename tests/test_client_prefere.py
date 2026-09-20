"""Deux clients torrent installes, et les *arr alternaient entre eux.

Releve en ecrivant la roadmap, puis verifie dans le code : le plan de cablage
declarait CHAQUE client dans CHAQUE *arr, tous avec `priority: 1`. La
documentation de Sonarr est explicite : « Round-Robin is used for clients of the
same type (torrent/usenet) that have the same priority ». Les episodes partaient
donc alternativement dans Transmission et dans qBittorrent, sans que personne
l'ait demande ni que rien ne le dise.

Demande a l'usage, en parallele : « lorsqu'on met plusieurs logiciels de
telechargement, demander vers lequel on cree le lien ».

Le correctif ne supprime rien. Le client prefere passe a 1, les autres
descendent et restent declares, en secours.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from plugarr import catalog, downloadclients, migrations, orchestrator, reprise, webwizard
from plugarr.cli import app
from plugarr.wiring import Wirer

DEUX_TORRENTS = ["sonarr", "transmission", "qbittorrent"]


def _cfg(services=DEUX_TORRENTS, prefere=""):
    cfg = orchestrator.build_config(services=services, config_root="/c", data_root="/d")
    cfg.client_prefere = prefere
    return cfg


# ------------------------------------------------------------------- la regle


def test_l_ordre_automatique_couvre_tous_les_clients():
    """Un client ajoute au catalogue sans rang recevrait une priorite au hasard."""
    assert set(downloadclients.ORDRE_AUTO) == set(catalog.DOWNLOAD_CLIENTS)


def test_sans_choix_qbittorrent_passe_devant():
    """Meme regle que le port entrant et que Flood : qBittorrent d'abord."""
    rangs = downloadclients.priorites(_cfg())

    assert rangs["qbittorrent"] == 1
    assert rangs["transmission"] == 2


def test_un_choix_explicite_l_emporte_sur_l_ordre_automatique():
    rangs = downloadclients.priorites(_cfg(prefere="transmission"))

    assert rangs["transmission"] == 1
    assert rangs["qbittorrent"] == 2


def test_des_protocoles_differents_ne_se_disputent_rien():
    """SABnzbd a cote de qBittorrent : chacun est seul dans son protocole."""
    cfg = _cfg(services=["sonarr", "qbittorrent", "sabnzbd"])

    assert downloadclients.priorites(cfg) == {"qbittorrent": 1, "sabnzbd": 1}
    assert downloadclients.concurrents(cfg.services) == []


def test_la_question_ne_se_pose_qu_entre_clients_du_meme_protocole():
    services = ["sonarr", "transmission", "qbittorrent", "sabnzbd"]

    assert downloadclients.concurrents(services) == ["qbittorrent", "transmission"]
    assert downloadclients.concurrents(["sonarr", "qbittorrent"]) == []


# ------------------------------------------------- cablage : pose et realignement


class FauxClient:
    """Juste ce que le realignement lit et ecrit dans un *arr."""

    def __init__(self, entrees):
        self.entrees = entrees
        self.ecritures = []

    def get(self, resource):
        assert resource == "downloadclient"
        return [dict(e) for e in self.entrees]

    def put(self, resource, payload):
        self.ecritures.append((resource, dict(payload)))


def _entrees(transmission, qbittorrent):
    return [
        {"id": 1, "name": "Transmission", "priority": transmission},
        {"id": 2, "name": "qBittorrent", "priority": qbittorrent},
    ]


def test_l_etat_fautif_herite_est_realigne():
    """Une installation existante, tous ses clients a 1 : c'est ce que PlugArr
    posait lui-meme, et c'est ce qui produit l'alternance."""
    client = FauxClient(_entrees(transmission=1, qbittorrent=1))

    suffixe = Wirer(_cfg())._aligner_priorites(client, "transmission")

    assert client.ecritures == [
        ("downloadclient/1", {"id": 1, "name": "Transmission", "priority": 2})
    ]
    assert "Transmission" in suffixe


def test_un_reglage_manuel_n_est_jamais_ecrase():
    """Quelqu'un a prefere Transmission a la main dans Sonarr. Sans choix
    explicite dans PlugArr, cette repartition lui appartient."""
    client = FauxClient(_entrees(transmission=1, qbittorrent=2))

    Wirer(_cfg())._aligner_priorites(client, "transmission")
    Wirer(_cfg())._aligner_priorites(client, "qbittorrent")

    assert client.ecritures == []


def test_un_choix_explicite_s_applique_a_une_installation_existante():
    """Choisi dans l'assistant a la reinstallation : l'utilisateur vient de le
    demander, et une installation deja realignee doit le suivre."""
    client = FauxClient(_entrees(transmission=2, qbittorrent=1))

    Wirer(_cfg(prefere="transmission"))._aligner_priorites(client, "transmission")

    assert sorted(client.ecritures) == [
        ("downloadclient/1", {"id": 1, "name": "Transmission", "priority": 1}),
        ("downloadclient/2", {"id": 2, "name": "qBittorrent", "priority": 2}),
    ]


def test_un_client_seul_dans_son_protocole_ne_consulte_rien():
    client = FauxClient([])

    assert Wirer(_cfg(services=["sonarr", "qbittorrent"]))._aligner_priorites(
        client, "qbittorrent"
    ) == ""


def test_la_creation_pose_la_priorite_calculee_et_non_plus_1(monkeypatch):
    """Le coeur de la panne : `priority: 1` etait ecrit en dur."""
    wirer = Wirer(_cfg())
    poses = {}

    class Arr:
        def ensure_resource(self, resource, *, name, implementation, values, extra):
            poses[name] = extra["priority"]
            return {"id": 9, "name": name}, True, []

        def find_by_name(self, resource, name):
            return {"id": 9, "name": name}

        def get(self, resource):
            return [{"id": 9, "name": n, "priority": p} for n, p in poses.items()]

        def put(self, resource, payload):
            raise AssertionError("une creation correcte n'a rien a realigner")

    faux = Arr()
    monkeypatch.setattr(wirer, "arr", lambda _sid: faux)
    monkeypatch.setattr(wirer, "_verify", lambda *a, **k: a[3])

    wirer.step_download_client("sonarr", "transmission")
    wirer.step_download_client("sonarr", "qbittorrent")

    assert poses == {"Transmission": 2, "qBittorrent": 1}


# ------------------------------------------------- persistance et reinstallation


def test_stack_yml_passe_en_version_3():
    """Une PlugArr plus ancienne doit REFUSER ce fichier plutot que d'en
    effacer le client prefere, champ qu'elle ne connait pas."""
    migre, notes = migrations.migrer({"version": 2})

    assert migre["version"] == migrations.VERSION_COURANTE >= 3
    assert notes[0] == "stack.yml migre en version 3"


def test_une_reinstallation_reprend_le_client_prefere():
    ancienne = _cfg(prefere="transmission")
    neuve = _cfg()

    reprise.appliquer(neuve, ancienne)

    assert neuve.client_prefere == "transmission"


def test_un_choix_donne_a_la_reinstallation_prime_sur_l_heritage():
    ancienne = _cfg(prefere="transmission")
    neuve = _cfg(prefere="qbittorrent")

    reprise.appliquer(neuve, ancienne, imposes={"client_prefere"})

    assert neuve.client_prefere == "qbittorrent"


# ----------------------------------------------------- les trois interfaces


def test_la_ligne_de_commande_refuse_un_client_hors_concurrence(tmp_path):
    resultat = CliRunner().invoke(
        app,
        [
            "install",
            "--services", "sonarr,qbittorrent",
            "--client-prefere", "qbittorrent",
            "--config-root", str(tmp_path / "c"),
            "--data-root", str(tmp_path / "d"),
            "--project-dir", str(tmp_path),
            "--dry-run",
        ],
    )

    assert resultat.exit_code == 1
    assert "--client-prefere" in resultat.output


def test_l_assistant_web_accepte_et_valide_le_choix(tmp_path):
    etat = webwizard.WizardState(tmp_path, demo=True)
    formulaire = etat.bootstrap()["form"]
    formulaire["services"] = DEUX_TORRENTS
    formulaire["client_prefere"] = "transmission"

    cfg = etat.build_config(formulaire)

    assert cfg.client_prefere == "transmission"
    assert downloadclients.priorites(cfg)["transmission"] == 1

    formulaire["services"] = ["sonarr", "transmission"]
    with pytest.raises(ValueError, match="prefere"):
        etat.build_config(formulaire)


@pytest.mark.asyncio
async def test_le_tui_ne_pose_la_question_qu_avec_deux_clients_torrent(tmp_path):
    from textual.widgets import RadioButton

    from plugarr.tui.app import PlugArrApp
    from plugarr.tui.screens import VpnScreen

    app_tui = PlugArrApp(project_dir=tmp_path)
    async with app_tui.run_test() as pilot:
        pilot.app.selection = ["sonarr", "qbittorrent"]
        await pilot.app.push_screen(VpnScreen())
        await pilot.pause()
        assert not pilot.app.screen.query("#client-prefere"), "question posee sans objet"
        pilot.app.pop_screen()
        await pilot.pause()

        pilot.app.selection = DEUX_TORRENTS
        await pilot.app.push_screen(VpnScreen())
        await pilot.pause()
        ecran = pilot.app.screen
        assert ecran.client_prefere_voulu() == "qbittorrent", "defaut different de la regle"

        ecran.query_one("#prefere-transmission", RadioButton).value = True
        await pilot.pause()
        assert ecran.client_prefere_voulu() == "transmission"
