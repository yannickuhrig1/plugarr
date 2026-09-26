"""Le portage Python des exports du telephone rend la meme chose que web/remote.js.

Demande du 26/09/2026 : le TUI doit offrir la configuration du telephone comme
l'assistant web. Les formats (Arr Control, nzb360, qbRemote, QR code) sont
compares a la reference JavaScript, octet par octet quand ils sont
deterministes ; le chiffrement AES, a sel aleatoire, est verifie en relisant
chaque archive avec l'autre implementation.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from plugarr import telephone

RACINE = Path(__file__).resolve().parent.parent
MOT_DE_PASSE = "Essai-qbRemote-1"

DATA = {
    "demo": False,
    "services": [
        {"id": "sonarr", "name": "Sonarr", "url": "http://10.0.0.30:8989", "local_url": "http://192.0.2.5:8989",
         "remote_url": "https://sonarr.example.test", "username": "plugarr", "password": "p", "api_key": "SONARR-KEY"},
        {"id": "radarr", "name": "Radarr", "url": "http://10.0.0.30:7878", "local_url": "http://192.0.2.5:7878/",
         "remote_url": "", "username": "plugarr", "password": "p", "api_key": "RADARR-KEY"},
        {"id": "qbittorrent", "name": "qBittorrent", "url": "http://10.0.0.30:8080", "local_url": "http://192.0.2.5:8080",
         "remote_url": "https://qb.example.test", "username": "plugarr", "password": "TEST-é\u0000😀-pass", "api_key": "-"},
        {"id": "prowlarr", "name": "Prowlarr", "url": "http://10.0.0.30:9696", "local_url": "http://192.0.2.5:9696",
         "remote_url": "", "username": "plugarr", "password": "p", "api_key": "PROWLARR-KEY"},
        {"id": "sabnzbd", "name": "SABnzbd", "url": "http://10.0.0.30:8085", "local_url": "http://192.0.2.5:8085",
         "remote_url": "", "username": "-", "password": "-", "api_key": "SAB-KEY"},
        {"id": "lidarr", "name": "Lidarr", "url": "http://10.0.0.30:8686", "local_url": "http://192.0.2.5:8686",
         "remote_url": "", "username": "plugarr", "password": "p", "api_key": "LIDARR-KEY"},
        {"id": "seerr", "name": "Seerr", "url": "http://10.0.0.30:5055", "local_url": "http://192.0.2.5:5055",
         "remote_url": "", "username": "-", "password": "-", "api_key": "SEERR-KEY"},
        {"id": "transmission", "name": "Transmission", "url": "http://10.0.0.30:9091", "local_url": "http://192.0.2.5:9091",
         "remote_url": "", "username": "tr", "password": "TR-PASS", "api_key": "-"},
    ],
}

JAVA = [
    {"version": "24.4.1", "actif": True, "inactif": False, "texte": "é\u0000😀 ok"},
    {"entier": {"t": "I", "v": -42}, "long": {"t": "J", "v": 1790000000000}, "flottant": {"t": "F", "v": 1.5},
     "double": {"t": "D", "v": -2.25}, "servers": {"t": "set", "v": ["000Default*", "001test"]}},
    {},
]

QR = ["http://192.0.2.50:49152/t/AbCdEfGhIjKl", "x", "https://example.test/" + "a" * 150]


def _base_nzb360() -> bytes:
    """Une sauvegarde nzb360 synthetique : Sonarr deja configure, un profil test."""
    principal = telephone.java_preferences({
        "version": "24.4.1",
        "nzbdrone_server_enabled_preference": True,
        "nzbdrone_server_primary_connectionstring_preference": "http://nas:8989",
        "licensing_x": "garde-tel-quel",
    })
    return telephone.zip_stored([
        (telephone.NZB360_FILE, principal),
        ("nzb360prefs.xml", telephone.java_preferences({"version": "24.4.1", "lastActiveProfile": "*"})),
        ("servers.xml", telephone.java_preferences({"servers": {"t": "set", "v": ["000Default*", "001test"]}})),
        ("001.xml", telephone.java_preferences({"radarr_server_enabled_preference": True})),
    ])


@pytest.fixture(scope="module")
def reference():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node absent : la reference JavaScript ne peut pas tourner")
    aes = telephone.zip_aes(
        [("manifest.json", '{"version":1}'), ("servers.json", '[{"id":1}]')], MOT_DE_PASSE,
        datetime(2026, 9, 26, 10, 0, 0, tzinfo=UTC),
    )
    requete = {
        "data": DATA, "java": JAVA, "qr": QR,
        "zip": [["a.txt", "bonjour"], ["b/c.json", "{}"]],
        "nzbBase": base64.b64encode(_base_nzb360()).decode(),
        "aesFromPython": base64.b64encode(aes).decode(), "password": MOT_DE_PASSE,
    }
    sortie = subprocess.run(
        [node, "tests/js/telephone_reference.cjs"], input=json.dumps(requete), capture_output=True,
        text=True, encoding="utf-8", cwd=RACINE, timeout=120, check=True,
    )
    return json.loads(sortie.stdout)


def _b64(octets: bytes) -> str:
    return base64.b64encode(octets).decode()


def test_arr_control_identique(reference):
    for network, attendu in zip(("local", "remote"), reference["arr"], strict=True):
        payload, omis = telephone.arr_control(DATA, network, 1790000000000)
        assert {"payload": payload, "omitted": omis} == attendu


def test_nzb360_identique_octet_par_octet(reference):
    for (network, ssid), attendu in zip((("local", ""), ("remote", ""), ("remote", "Maison")), reference["nzb"], strict=True):
        resultat = telephone.nzb360_export(DATA, network, ssid)
        assert _b64(resultat["bytes"]) == attendu["bytes"], (network, ssid)
        assert (resultat["count"], resultat["omitted"], resultat["switching"]) == (
            attendu["count"], attendu["omitted"], attendu["switching"],
        )


def test_serialisation_java_identique_et_relue(reference):
    for prefs, attendu, relu in zip(JAVA, reference["java"], reference["javaRead"], strict=True):
        octets = telephone.java_preferences(prefs)
        assert _b64(octets) == attendu
        assert telephone.lire_java_preferences(octets) == relu


def test_zip_stocke_identique(reference):
    octets = telephone.zip_stored([("a.txt", b"bonjour"), ("b/c.json", b"{}")])
    assert _b64(octets) == reference["zip"]


def test_qr_identique(reference):
    for texte, attendu in zip(QR, reference["qr"], strict=True):
        qr = telephone.qr_matrice(texte)
        lignes = ["".join("1" if m else "0" for m in ligne) for ligne in qr["modules"]]
        assert (qr["version"], qr["mask"], lignes) == (attendu["version"], attendu["mask"], attendu["modules"]), texte


def test_serveur_qbremote_identique(reference):
    for (network, ssid), attendu in zip((("local", ""), ("remote", ""), ("remote", "Maison")), reference["qb"], strict=True):
        assert telephone.qbremote_serveur(DATA, network, ssid) == attendu


def test_fusions_nzb360_identiques(reference):
    base = telephone.nzb360_examiner(_base_nzb360())
    assert {"configured": base["configured"], "activeProfile": base["activeProfile"]} == reference["nzbInspect"]
    profil = telephone.nzb360_fusion_profil(base, DATA)
    assert _b64(profil["bytes"]) == reference["nzbProfile"]["bytes"]
    assert profil["profile"] == reference["nzbProfile"]["profile"]
    fusion = telephone.nzb360_fusion(base, DATA, remplacer=["sonarr"])
    assert _b64(fusion["bytes"]) == reference["nzbMerge"]["bytes"]
    assert (fusion["added"], fusion["replaced"], fusion["kept"]) == (
        reference["nzbMerge"]["added"], reference["nzbMerge"]["replaced"], reference["nzbMerge"]["kept"],
    )


def test_zip_aes_relu_dans_les_deux_sens(reference):
    assert reference["aesRead"] == [["manifest.json", '{"version":1}'], ["servers.json", '[{"id":1}]']]
    assert reference["aesWrongPassword"] is True
    fichiers = telephone.lire_zip(base64.b64decode(reference["aesFromJs"]), MOT_DE_PASSE)
    assert [(n, c.decode()) for n, c in fichiers] == [("manifest.json", '{"version":1}'), ("servers.json", '[{"id":1}]')]
    with pytest.raises(telephone.ErreurMotDePasse):
        telephone.lire_zip(base64.b64decode(reference["aesFromJs"]), "mauvais")


def test_export_et_fusion_qbremote():
    now = datetime(2026, 9, 26, 10, 0, 0, tzinfo=UTC)
    export = telephone.qbremote_export(DATA, "remote", "Maison", MOT_DE_PASSE, now)
    fichiers = dict(telephone.lire_zip(export, MOT_DE_PASSE))
    assert json.loads(fichiers["manifest.json"]) == {"version": 1, "createdAt": "2026-09-26T10:00:00.000Z", "appVersion": "1.8.0(73)"}
    serveur = json.loads(fichiers["servers.json"])[0]
    assert (serveur["host"], serveur["port"], serveur["localSsid"], serveur["localHost"]) == ("qb.example.test", "443", "Maison", "192.0.2.5")

    fusion = telephone.qbremote_fusion(export, MOT_DE_PASSE, DATA, "local", "", now)
    assert fusion["updated"] is True and fusion["kept"] == 0
    assert json.loads(dict(telephone.lire_zip(fusion["bytes"], MOT_DE_PASSE))["servers.json"])[0]["host"] == "192.0.2.5"


def test_qr_en_terminal_noir_sur_blanc():
    rendu = telephone.qr_terminal("http://192.0.2.50:49152/t/abc")
    styles = {str(span.style) for span in rendu.spans}
    assert styles <= {"black on black", "black on bright_white", "bright_white on black", "bright_white on bright_white"}
    assert rendu.plain.count("\n") > 10
