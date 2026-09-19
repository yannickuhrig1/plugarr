"""Reprise des indexeurs depuis une sauvegarde Prowlarr. Aucun reseau.

La base de test reproduit le schema reel d'une sauvegarde Prowlarr 2.5.2
(tables, colonnes, forme du JSON `Settings`), releve sur une vraie sauvegarde.
Le Prowlarr d'en face est simule, et enregistre chaque appel : c'est ce qui
permet d'affirmer que l'import ne touche ni au client qBittorrent ni aux
Applications cablees par PlugArr.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import zipfile
from contextlib import closing

import httpx
import pytest
from typer.testing import CliRunner

from plugarr import import_prowlarr, webwizard
from plugarr.clients.prowlarr import ProwlarrIndexers

SCHEMA_SQL = """
CREATE TABLE Indexers (Id INTEGER PRIMARY KEY, Name TEXT, Implementation TEXT, Settings TEXT,
  ConfigContract TEXT, Enable INTEGER, Priority INTEGER, Added DATETIME, Redirect INTEGER,
  AppProfileId INTEGER, Tags TEXT, DownloadClientId INTEGER);
CREATE TABLE AppSyncProfiles (Id INTEGER PRIMARY KEY, Name TEXT);
CREATE TABLE Tags (Id INTEGER PRIMARY KEY, Label TEXT);
CREATE TABLE DownloadClients (Id INTEGER PRIMARY KEY, Enable INTEGER, Name TEXT, Implementation TEXT,
  Settings TEXT, ConfigContract TEXT, Priority INTEGER, Categories TEXT);
CREATE TABLE Applications (Id INTEGER PRIMARY KEY, Name TEXT, Implementation TEXT, Settings TEXT,
  ConfigContract TEXT, SyncLevel INTEGER, Tags TEXT);
CREATE TABLE IndexerProxies (Id INTEGER PRIMARY KEY, Name TEXT, Settings TEXT, Implementation TEXT,
  ConfigContract TEXT, Tags TEXT);
"""

C411_SETTINGS = {
    "definitionFile": "c411",
    "extraFieldData": {"apikey": "CLE-SECRETE-C411", "info_key": "texte", "multilang": True, "vostfr": False},
    "baseUrl": "https://c411.example/",
    "baseSettings": {"limitsUnit": 0},
    "torrentBaseSettings": {"preferMagnetUrl": False},
}
NEWZNAB_SETTINGS = {
    "baseUrl": "https://nzb.example",
    "apiPath": "/api",
    "apiKey": "CLE-NZB",
    "baseSettings": {"queryLimit": 100},
}


def fabriquer_base(chemin):
    with closing(sqlite3.connect(chemin)) as db:
        db.executescript(SCHEMA_SQL)
        db.execute("insert into AppSyncProfiles values (1, 'Standard'), (2, 'Films')")
        db.execute("insert into Tags values (3, 'flaresolverr'), (4, 'ancienne')")
        db.execute(
            "insert into DownloadClients values (9, 1, 'qBittorrent', 'QBittorrent', '{}', 'x', 1, '[]'),"
            " (10, 1, 'Deluge perso', 'Deluge', '{}', 'x', 1, '[]')"
        )
        db.execute("insert into Applications values (1, 'Sonarr', 'Sonarr', '{\"apiKey\": \"VIEILLE\"}', 'x', 2, '[]')")
        rows = [
            (1, "C411", "Cardigann", json.dumps(C411_SETTINGS), "CardigannSettings", 1, 25, None, 0, 2, "[3, 4]", 9),
            (2, "Mon NZB", "Newznab", json.dumps(NEWZNAB_SETTINGS), "NewznabSettings", 0, 10, None, 1, 1, "[]", 10),
            (3, "Disparu", "Cardigann", json.dumps({"definitionFile": "disparu"}), "CardigannSettings", 1, 25, None, 0, 1, "[]", 0),
        ]
        db.executemany("insert into Indexers values (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        db.commit()


@pytest.fixture
def base(tmp_path):
    chemin = tmp_path / "prowlarr.db"
    fabriquer_base(chemin)
    return chemin


def champ(name, type_="textbox", value=None):
    return {"name": name, "type": type_, "value": value}


SCHEMA = [
    {
        "name": "C411",
        "implementation": "Cardigann",
        "configContract": "CardigannSettings",
        "protocol": "torrent",
        "privacy": "private",
        "fields": [
            champ("definitionFile", value="c411"),
            champ("baseUrl", "select"),
            champ("baseSettings.limitsUnit", "select", 0),
            champ("torrentBaseSettings.preferMagnetUrl", "checkbox", False),
            champ("apikey"),
            champ("info_key", "info", "aide"),
            champ("multilang", "checkbox", False),
        ],
    },
    {
        "name": "Generic Newznab",
        "implementation": "Newznab",
        "configContract": "NewznabSettings",
        "protocol": "usenet",
        "privacy": "private",
        "fields": [champ("baseUrl"), champ("apiPath", value="/api"), champ("apiKey"), champ("baseSettings.queryLimit", "number")],
    },
]


class ProwlarrSimule:
    """Enregistre chaque appel. Un import ne doit ecrire que `POST indexer`."""

    def __init__(self, configured=None, refuse=None):
        self.configured = list(configured or [])
        self.refuse = refuse
        self.appels: list[tuple[str, str]] = []
        self.envoyes: list[dict] = []

    def get(self, resource):
        self.appels.append(("GET", resource))
        return {
            "indexer/schema": SCHEMA,
            "indexer": self.configured,
            "appprofile": [{"id": 5, "name": "Standard"}, {"id": 6, "name": "Films"}],
            "tag": [{"id": 30, "label": "FlareSolverr"}],
            "downloadclient": [{"id": 1, "name": "qBittorrent", "implementation": "QBittorrent"}],
        }.get(resource, [])

    def post(self, resource, payload, *, timeout=None):
        self.appels.append(("POST", resource))
        if self.refuse and payload["name"] == self.refuse:
            from plugarr.clients.base import WiringError

            raise WiringError("prowlarr : POST indexer refuse", "Unable to connect to indexer, check apikey=CLE-SECRETE-C411&t=caps")
        self.envoyes.append(payload)
        self.configured.append({"name": payload["name"], "fields": payload["fields"]})
        return payload

    def put(self, resource, payload):  # pragma: no cover - ne doit jamais servir
        self.appels.append(("PUT", resource))

    def delete(self, resource):  # pragma: no cover - ne doit jamais servir
        self.appels.append(("DELETE", resource))


def ecritures(prowlarr):
    return [appel for appel in prowlarr.appels if appel[0] != "GET"]


# -- lecture ---------------------------------------------------------------------


def test_lit_une_base_seule(base):
    sauvegarde = import_prowlarr.lire(base)
    assert sauvegarde.source == "base"
    assert [i.name for i in sauvegarde.indexeurs] == ["C411", "Mon NZB", "Disparu"]
    c411 = sauvegarde.indexeurs[0]
    assert c411.app_profile == "Films"
    assert c411.tags == ("flaresolverr", "ancienne")
    assert c411.download_client == ("qBittorrent", "QBittorrent")
    assert sauvegarde.ignores == {"applications": 1, "download_clients": 2, "proxies": 0}


def test_lit_une_sauvegarde_prowlarr_zip(base, tmp_path):
    archive = tmp_path / "prowlarr_backup_v2.5.2.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(base, "prowlarr.db")
        zf.writestr("config.xml", "<Config><ApiKey>secret</ApiKey></Config>")
    sauvegarde = import_prowlarr.lire(archive)
    assert sauvegarde.source == "prowlarr" and len(sauvegarde.indexeurs) == 3


def test_lit_une_archive_plugarr(base, tmp_path):
    archive = tmp_path / "plugarr-plugarr-20260913.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("plugarr-sauvegarde.json", "{}")
        zf.writestr("projet/stack.yml", "")
        zf.write(base, "config/prowlarr/prowlarr.db")
    sauvegarde = import_prowlarr.lire(archive)
    assert sauvegarde.source == "plugarr" and len(sauvegarde.indexeurs) == 3


def test_le_journal_wal_d_une_sauvegarde_a_chaud_est_lu(tmp_path):
    """Sans le -wal, les indexeurs ajoutes juste avant la sauvegarde manquaient."""
    source = tmp_path / "vive"
    source.mkdir()
    db = sqlite3.connect(source / "prowlarr.db")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA wal_autocheckpoint=0")
    db.executescript(SCHEMA_SQL)
    db.execute("insert into Indexers (Id, Name, Implementation, Settings, ConfigContract, Enable, Priority)"
               " values (1, 'Recent', 'Cardigann', '{}', 'CardigannSettings', 1, 25)")
    db.commit()
    archive = tmp_path / "chaud.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for nom in ("prowlarr.db", "prowlarr.db-wal", "prowlarr.db-shm"):
            if (source / nom).exists():
                zf.write(source / nom, nom)
    db.close()
    assert "prowlarr.db-wal" in zipfile.ZipFile(archive).namelist()
    assert [i.name for i in import_prowlarr.lire(archive).indexeurs] == ["Recent"]


@pytest.mark.parametrize(
    "contenu",
    [b"pas une sauvegarde", b"PK\x03\x04tronque"],
)
def test_un_fichier_quelconque_est_refuse_proprement(tmp_path, contenu):
    fichier = tmp_path / "x.zip"
    fichier.write_bytes(contenu)
    with pytest.raises(ValueError):
        import_prowlarr.lire(fichier)


def test_un_zip_sans_base_prowlarr_est_refuse(tmp_path):
    archive = tmp_path / "autre.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("config/sonarr/sonarr.db", "x")
    with pytest.raises(ValueError, match="Aucune base Prowlarr"):
        import_prowlarr.lire(archive)


def test_une_base_sans_table_indexeurs_est_refusee(tmp_path):
    chemin = tmp_path / "sonarr.db"
    with closing(sqlite3.connect(chemin)) as db:
        db.execute("create table Series (Id integer)")
    with pytest.raises(ValueError, match="indexeurs"):
        import_prowlarr.lire(chemin)


def test_le_dossier_temporaire_est_efface(base, tmp_path, monkeypatch):
    """La base extraite contient les cles des indexeurs."""
    crees = []
    vrai = import_prowlarr.tempfile.mkdtemp

    def espion(**kw):
        crees.append(vrai(dir=tmp_path, **kw))
        return crees[-1]

    monkeypatch.setattr(import_prowlarr.tempfile, "mkdtemp", espion)
    import_prowlarr.lire(base)
    assert crees and not any(__import__("os").path.exists(d) for d in crees)


def test_les_reglages_prennent_les_noms_de_l_api(base):
    c411 = import_prowlarr.lire(base).indexeurs[0]
    valeurs = c411.valeurs_api()
    assert valeurs["apikey"] == "CLE-SECRETE-C411"
    assert valeurs["baseSettings.limitsUnit"] == 0
    assert valeurs["torrentBaseSettings.preferMagnetUrl"] is False
    assert valeurs["baseUrl"] == "https://c411.example/"
    assert "extraFieldData.apikey" not in valeurs


# -- confrontation et import -------------------------------------------------------


def test_examen_distingue_importable_configure_et_inconnu(base):
    prowlarr = ProwlarrSimule(configured=[{"name": "Mon NZB", "fields": []}])
    statuts = import_prowlarr.examiner(import_prowlarr.lire(base), ProwlarrIndexers(prowlarr))
    assert [(e.name, s) for e, s in statuts] == [
        ("C411", "importable"),
        ("Mon NZB", "configure"),
        ("Disparu", "inconnu"),
    ]
    assert ecritures(prowlarr) == []


def test_une_definition_renommee_est_reconnue_comme_deja_configuree(base):
    """Meme definitionFile sous un autre nom : c'est le meme tracker."""
    existant = {"name": "C411 perso", "fields": [champ("definitionFile", value="c411")]}
    statuts = import_prowlarr.examiner(import_prowlarr.lire(base), ProwlarrIndexers(ProwlarrSimule([existant])))
    assert statuts[0][1] == "configure"


def test_import_ne_touche_ni_au_client_qbittorrent_ni_aux_applications(base):
    prowlarr = ProwlarrSimule()
    indexers = ProwlarrIndexers(prowlarr)
    sauvegarde = import_prowlarr.lire(base)
    resultats = [import_prowlarr.importer(e, indexers) for e in sauvegarde.indexeurs]
    assert [r[0] for r in resultats] == [True, True, False]
    assert ecritures(prowlarr) == [("POST", "indexer"), ("POST", "indexer")]


def test_charge_utile_c411(base):
    prowlarr = ProwlarrSimule()
    c411 = import_prowlarr.lire(base).indexeurs[0]
    ok, _message, avertissements = import_prowlarr.importer(c411, ProwlarrIndexers(prowlarr))
    assert ok
    envoye = prowlarr.envoyes[0]
    valeurs = {f["name"]: f["value"] for f in envoye["fields"]}
    assert valeurs["apikey"] == "CLE-SECRETE-C411"
    assert valeurs["baseUrl"] == "https://c411.example/"
    assert valeurs["multilang"] is True
    assert valeurs["info_key"] == "aide", "un champ info garde le texte du Prowlarr installe"
    # Identifiants de l'ANCIENNE base resolus par nom dans le Prowlarr installe.
    assert envoye["appProfileId"] == 6
    assert envoye["tags"] == [30]
    assert envoye["downloadClientId"] == 1
    assert envoye["name"] == "C411" and envoye["enable"] is True and envoye["priority"] == 25
    assert any("ancienne" in a for a in avertissements)
    assert any("vostfr" in a for a in avertissements)
    assert not any("CLE-SECRETE" in a for a in avertissements)


def test_un_client_absent_retombe_sur_le_client_par_defaut(base):
    """Le Deluge de l'ancienne machine n'existe pas ici : jamais d'identifiant
    recopie tel quel, qui designerait un autre client."""
    prowlarr = ProwlarrSimule()
    nzb = import_prowlarr.lire(base).indexeurs[1]
    ok, _message, avertissements = import_prowlarr.importer(nzb, ProwlarrIndexers(prowlarr))
    envoye = prowlarr.envoyes[0]
    assert ok and envoye["downloadClientId"] == 0
    assert envoye["appProfileId"] == 5 and envoye["enable"] is False and envoye["redirect"] is True
    assert {f["name"]: f["value"] for f in envoye["fields"]}["apiKey"] == "CLE-NZB"
    assert any("Deluge perso" in a for a in avertissements)


def test_un_indexeur_deja_present_n_est_jamais_remplace(base):
    prowlarr = ProwlarrSimule(configured=[{"name": "c411", "fields": []}])
    c411 = import_prowlarr.lire(base).indexeurs[0]
    ok, message, _ = import_prowlarr.importer(c411, ProwlarrIndexers(prowlarr))
    assert ok and message == "deja configure"
    assert ecritures(prowlarr) == []


def test_un_refus_de_prowlarr_est_caviarde(base):
    prowlarr = ProwlarrSimule(refuse="C411")
    c411 = import_prowlarr.lire(base).indexeurs[0]
    ok, message, _ = import_prowlarr.importer(c411, ProwlarrIndexers(prowlarr))
    assert not ok and "CLE-SECRETE" not in message


# -- ligne de commande -------------------------------------------------------------


def test_commande_import_a_blanc(base, tmp_path, monkeypatch):
    from plugarr import indexers_cli
    from plugarr.cli import app

    prowlarr = ProwlarrSimule()
    monkeypatch.setattr(indexers_cli, "_open", lambda _dir: (type("C", (), {"close": lambda self: None})(), ProwlarrIndexers(prowlarr)))
    resultat = CliRunner().invoke(app, ["indexers", "import", str(base), "--dry-run"])
    assert resultat.exit_code == 0, resultat.output
    assert "C411" in resultat.output and "Disparu" in resultat.output
    assert ecritures(prowlarr) == []


# -- assistant web -------------------------------------------------------------------


@pytest.fixture
def assistant(tmp_path):
    server = webwizard.WizardServer(tmp_path / "projet", demo=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    with httpx.Client(
        base_url=server.origin, trust_env=False, timeout=10,
        headers={"Authorization": "Bearer " + server.token},
    ) as client:
        yield server, client
    server.state.close_resources()
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)
    if server.state.worker:
        server.state.worker.join(timeout=5)


def installer_demo(server, client, services=("prowlarr", "sonarr")):
    form = server.state.bootstrap()["form"]
    form.update(services=list(services))
    plan = client.post("/api/validate", json=form).json()
    assert client.post("/api/install", json={"plan_id": plan["plan_id"], "confirm": True}).status_code == 200
    server.state.worker.join(timeout=5)


def televerser(client, contenu):
    return client.post(
        "/api/indexers/backup", content=contenu, headers={"Content-Type": "application/octet-stream"}
    )


def test_assistant_refuse_le_televersement_avant_la_fin_de_l_installation(assistant, base):
    _server, client = assistant
    reponse = televerser(client, base.read_bytes())
    assert reponse.status_code == 400 and "fin de l'installation" in reponse.json()["error"]


def test_assistant_examine_puis_importe_sans_exposer_les_cles(assistant, base, tmp_path):
    server, client = assistant
    installer_demo(server, client)
    archive = tmp_path / "prowlarr_backup.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(base, "prowlarr.db")
    reponse = televerser(client, archive.read_bytes())
    assert reponse.status_code == 200, reponse.text
    assert "CLE-SECRETE" not in reponse.text and "CLE-NZB" not in reponse.text
    examen = reponse.json()
    assert examen["source"] == "prowlarr"
    assert [i["name"] for i in examen["indexers"]] == ["C411", "Mon NZB", "Disparu"]
    cle = examen["indexers"][0]["key"]
    importe = client.post("/api/indexers/backup/import", json={"key": cle}).json()
    assert importe["ok"] and importe["name"] == "C411"
    # Une cle deja importee ne se rejoue pas.
    assert client.post("/api/indexers/backup/import", json={"key": cle}).status_code == 400


def test_assistant_refuse_un_corps_json_sur_la_route_de_televersement(assistant):
    server, client = assistant
    installer_demo(server, client)
    reponse = client.post("/api/indexers/backup", json={"chemin": "C:/x.zip"})
    assert reponse.status_code == 400 and "Fichier de sauvegarde attendu" in reponse.json()["error"]


def test_assistant_refuse_sans_prowlarr(assistant, base):
    server, client = assistant
    installer_demo(server, client, services=("sonarr",))
    reponse = televerser(client, base.read_bytes())
    assert reponse.status_code == 400 and "Prowlarr" in reponse.json()["error"]


def test_assistant_signale_un_fichier_invalide(assistant):
    server, client = assistant
    installer_demo(server, client)
    reponse = televerser(client, b"rien a voir")
    assert reponse.status_code == 400 and "ni une sauvegarde Prowlarr" in reponse.json()["error"]


def test_la_route_d_import_est_appelee_par_l_interface():
    javascript = (webwizard.ASSETS / "wizard.js").read_text(encoding="utf-8")
    html = (webwizard.ASSETS / "wizard.html").read_text(encoding="utf-8")
    for route in ("/api/indexers/backup", "/api/indexers/backup/import"):
        assert route in javascript
    for element_id in ("indexer-backup-file", "indexer-backup-inspect", "indexer-backup-list", "indexer-backup-import"):
        assert f'id="{element_id}"' in html


def test_prowlarr_a_le_temps_de_valider_un_tracker_lent(base):
    """Prowlarr 2.5.2 met 100 s a renoncer devant un tracker hors ligne."""
    prowlarr = ProwlarrSimule()
    delais = []
    envoyer = prowlarr.post
    prowlarr.post = lambda resource, payload, *, timeout=None: delais.append(timeout) or envoyer(resource, payload)
    import_prowlarr.importer(import_prowlarr.lire(base).indexeurs[0], ProwlarrIndexers(prowlarr))
    assert delais == [150.0]


def test_le_message_de_prowlarr_est_lisible_et_caviarde():
    """Texte reel de Prowlarr 2.5.2 face a un tracker hors ligne, avec ses
    echappements JSON (construits par chr(92) pour rester lisibles ici)."""
    from plugarr.clients.prowlarr import _readable

    b = chr(92)
    brut = (f'HTTP 400 - [{{"errorMessage": "Unable to connect to indexer, indexer{b}u0027s server is unavailable.'
            f' HTTP request failed: [522:522] [GET] at [https://t.example/api?api_token=SECRET{b}u0026perPage=1]"}}]')
    lisible = _readable(brut)
    assert "indexer's server" in lisible and b not in lisible and "SECRET" not in lisible
