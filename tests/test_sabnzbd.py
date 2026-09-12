"""SABnzbd : l'Usenet a cote des torrents, et quatre pieges enchaines.

Demande a l'usage : « il faut trouver un remplacant pour DroppedNeedle ». La
premisse meritait d'etre corrigee — DroppedNeedle n'est pas un mauvais choix, il
est bloque par son client de telechargement, et tous les chemins vers
l'acquisition automatisee de musique passent par slskd ou SABnzbd. Ajouter le
client debloque DroppedNeedle sans le remplacer, et sert toute la pile au
passage : Sonarr, Radarr et Lidarr y gagnent l'Usenet a cote des torrents.

Quatre pieges, chacun trouve en essayant pour de vrai, et chacun muet.

**La liste blanche d'hotes.** SABnzbd refuse toute requete dont l'en-tete `Host`
n'y figure pas, et n'y met par defaut QUE l'identifiant de son conteneur. Sonarr
appelant `http://sabnzbd:8085` recoit « Access denied - Hostname verification
failed », message qui ne nomme ni l'appelant ni le reglage.

**Sa cle API n'etait pas generee.** SABnzbd n'a ni identifiant ni mot de passe :
sa cle tient lieu des deux, et rien dans PlugArr ne lui en attribuait. Le
pre-semis ecrivait une cle vide, SABnzbd en generait une a lui, et tout le
cablage repondait « API Key Required ».

**Le pre-semis ne tournait pas.** `seeded_services` listait trois familles
d'API ; la sienne n'y etait pas. La cle generee n'atteignait donc jamais le
fichier.

**Les categories d'usine ont un repertoire VIDE.** `movies`, `tv`, `audio`,
`software` existent des l'installation. Se contenter de les creer si absentes
les laisse inutilisables : le nom existe, Sonarr l'accepte, et tout atterrit
dans le repertoire par defaut.

Et Prowlarr refuse de se declarer si SA categorie n'existe pas cote client :
« The category you entered doesn't exist in Sabnzbd. »
"""

from __future__ import annotations

import httpx
import pytest

from plugarr import catalog, compose, orchestrator, seed
from plugarr.clients.sabnzbd import SabnzbdClient
from plugarr.downloadclients import profile_for
from plugarr.layout import CONTAINER_PATHS, DATA_SUBDIRS
from plugarr.models import VpnConfig
from plugarr.wiring import Wirer


def _cfg(*services: str):
    return orchestrator.build_config(
        services=list(services or ("sabnzbd",)), config_root="/c", data_root="/d"
    )


# ------------------------------------------------------------------ catalogue


def test_le_service_est_choisissable():
    assert "sabnzbd" in {s.id for s in catalog.selectable()}


def test_l_image_est_epinglee_au_digest():
    assert "@sha256:" in catalog.get("sabnzbd").image


def test_il_compte_comme_client_de_telechargement():
    """Il est declare aux *arr, attendu au demarrage et protege par le VPN
    exactement comme les clients torrent."""
    assert "sabnzbd" in catalog.DOWNLOAD_CLIENTS
    assert catalog.get("sabnzbd").category is catalog.Category.DOWNLOAD


def test_son_port_interne_ne_heurte_pas_qbittorrent():
    """Sous Gluetun les conteneurs partagent aussi leurs ports INTERNES."""
    assert catalog.get("sabnzbd").internal_port == 8085
    assert catalog.get("sabnzbd").internal_port != catalog.get("qbittorrent").internal_port


def test_sous_vpn_les_deux_interfaces_ont_des_sockets_distincts():
    cfg = _cfg("qbittorrent", "sabnzbd")
    cfg.vpn = VpnConfig(
        enabled=True,
        provider="nordvpn",
        wireguard_private_key="k" * 44,
        protect_sabnzbd=True,
    )

    doc = compose.build_compose(cfg)

    assert doc["services"]["gluetun"]["ports"] == ["8080:8080", "8085:8085"]
    wirer = Wirer(cfg)
    try:
        assert wirer.internal_url("qbittorrent") == "http://gluetun:8080"
        assert wirer.internal_url("sabnzbd") == "http://gluetun:8085"
    finally:
        wirer.close()


def test_sabnzbd_reste_direct_par_defaut_meme_si_les_torrents_ont_un_vpn():
    cfg = _cfg("qbittorrent", "sabnzbd")
    cfg.vpn = VpnConfig(
        enabled=True,
        provider="nordvpn",
        wireguard_private_key="k" * 44,
    )

    doc = compose.build_compose(cfg)

    assert doc["services"]["gluetun"]["ports"] == ["8080:8080"]
    assert doc["services"]["sabnzbd"]["ports"] == ["8085:8085"]
    assert "network_mode" not in doc["services"]["sabnzbd"]
    wirer = Wirer(cfg)
    try:
        assert wirer.internal_url("sabnzbd") == "http://sabnzbd:8085"
    finally:
        wirer.close()


def test_sous_vpn_tous_les_ports_internes_partages_sont_uniques():
    cfg = _cfg(*catalog.DOWNLOAD_CLIENTS)
    ports = [catalog.get(sid).internal_port for sid in cfg.services]

    assert len(ports) == len(set(ports))


def test_il_parle_usenet_et_non_torrent():
    """Les *arr rangent leurs clients par protocole et ne proposent un client
    Usenet que pour les publications Usenet."""
    assert profile_for("sabnzbd").protocol == "usenet"
    assert profile_for("qbittorrent").protocol == "torrent"


# ------------------------------------------------------------------ identifiants


def test_sa_cle_api_est_generee():
    """Sans elle, le pre-semis ecrit une cle vide, SABnzbd en genere une a lui,
    et tout le cablage repond « API Key Required »."""
    inst = _cfg().services["sabnzbd"]

    assert inst.api_key
    assert len(inst.api_key) == 32


def test_la_cle_sert_aussi_de_mot_de_passe():
    """Il n'a ni identifiant ni mot de passe : sa cle tient lieu des deux. Le
    champ `password` la publie dans le .env et la repose dans `apiKey`."""
    inst = _cfg().services["sabnzbd"]

    assert inst.password == inst.api_key


def test_la_sonde_sabnzbd_refuse_une_reponse_404_de_qbittorrent(monkeypatch):
    appels = []

    def faux_get(url, **kwargs):
        appels.append((url, kwargs))
        return httpx.Response(404, text="Not Found")

    monkeypatch.setattr(httpx, "get", faux_get)

    assert not orchestrator._download_client_responds(
        "sabnzbd", "http://localhost:8085", api_key="CLE"
    )
    assert appels[0][0] == "http://localhost:8085/api"
    assert appels[0][1]["params"]["mode"] == "version"


def test_la_sonde_sabnzbd_exige_sa_signature_api(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **kw: httpx.Response(200, json={"version": "5.1.2"}),
    )

    assert orchestrator._download_client_responds(
        "sabnzbd", "http://localhost:8085", api_key="CLE"
    )


def test_il_est_pre_seme():
    """`seeded_services` ne listait pas sa famille d'API : la cle generee
    n'atteignait donc jamais son fichier."""
    assert "sabnzbd" in orchestrator.seeded_services(_cfg("sabnzbd", "sonarr"))


def test_les_arr_recoivent_la_cle_et_non_un_mot_de_passe():
    """Poser un identifiant et un mot de passe ferait echouer le test de
    connexion : son interface n'en demande pas."""
    valeurs = profile_for("sabnzbd").arr_values(
        host="sabnzbd", port=8080, username="plugarr", password="LA-CLE", arr_id="sonarr"
    )

    assert valeurs["apiKey"] == "LA-CLE"
    assert valeurs["username"] == ""
    assert valeurs["password"] == ""


# ------------------------------------------------------------------ pre-semis


def test_le_pre_semis_pose_les_noms_d_hote(tmp_path):
    """Sans eux : « Access denied - Hostname verification failed »."""
    seed.seed_sabnzbd(
        tmp_path, api_key="CLE", port=8080,
        hotes_autorises=["sabnzbd", "plugarr-sabnzbd", "localhost"],
        incomplet="/data/usenet/.incomplete", complet="/data/usenet",
    )
    texte = (tmp_path / "sabnzbd.ini").read_text(encoding="utf-8")

    for hote in ("sabnzbd", "plugarr-sabnzbd", "localhost"):
        assert hote in texte


def test_sous_vpn_le_pre_semis_autorise_les_noms_de_gluetun(tmp_path):
    """C'est Gluetun, et non `sabnzbd`, que les autres conteneurs appellent."""
    cfg = orchestrator.build_config(
        services=["sabnzbd"], config_root=str(tmp_path), data_root="/d"
    )
    cfg.vpn = VpnConfig(
        enabled=True,
        provider="nordvpn",
        wireguard_private_key="k" * 44,
        protect_sabnzbd=True,
    )

    orchestrator.seed_all(cfg)
    texte = (tmp_path / "sabnzbd" / "sabnzbd.ini").read_text(encoding="utf-8")

    assert "port = 8085" in texte
    for hote in ("gluetun", "plugarr-gluetun"):
        assert hote in texte


def test_le_pre_semis_met_les_telechargements_sous_data(tmp_path):
    """Par defaut ils sont sous /config : les liens physiques deviennent
    impossibles et chaque import recopie le fichier."""
    seed.seed_sabnzbd(
        tmp_path, api_key="CLE", port=8080, hotes_autorises=["sabnzbd"],
        incomplet="/data/usenet/.incomplete", complet="/data/usenet",
    )
    texte = (tmp_path / "sabnzbd.ini").read_text(encoding="utf-8")

    assert "/data/usenet/.incomplete" in texte
    assert "/data/usenet" in texte


def test_un_fichier_existant_garde_ses_secrets_et_aligne_sa_topologie(tmp_path):
    """La cle reste souveraine ; le port interne et les hotes suivent le compose."""
    seed.seed_sabnzbd(
        tmp_path, api_key="PREMIERE", port=8080, hotes_autorises=["sabnzbd"],
        incomplet="/a", complet="/b",
    )
    ecrit, message = seed.seed_sabnzbd(
        tmp_path, api_key="SECONDE", port=9999, hotes_autorises=["sabnzbd", "autre-nom"],
        incomplet="/x", complet="/y",
    )
    texte = (tmp_path / "sabnzbd.ini").read_text(encoding="utf-8")

    assert ecrit is False
    assert "PREMIERE" in texte, "la cle existante a ete ecrasee"
    assert "port = 9999" in texte, "le port interne n'a pas suivi le compose"
    assert "autre-nom" in texte, "le nouvel hote n'a pas ete ajoute"
    assert "port 8080 -> 9999" in message
    assert "autre-nom" in message


def test_un_ini_sans_section_misc_recoit_vraiment_ce_qu_on_annonce(tmp_path):
    """Le message disait « port ajoute » et « hotes ajoutes » sans rien ecrire.

    Sans section `[misc]`, le port et la liste d'hotes n'avaient nulle part ou
    aller : la boucle ne les posait pas, et le rapport d'installation annoncait
    pourtant les deux. SABnzbd restait sur 8080 et refusait les *arr, avec un
    journal qui affirmait le contraire.
    """
    existant = "__version__ = 19\n[servers]\nhost = news.example.invalid\n"
    (tmp_path / "sabnzbd.ini").write_text(existant, encoding="utf-8")

    _ecrit, message = seed.seed_sabnzbd(
        tmp_path,
        api_key="CLE",
        port=8085,
        hotes_autorises=["sabnzbd", "plugarr-sabnzbd", "localhost"],
        incomplet="/data/usenet/.incomplete",
        complet="/data/usenet",
    )
    texte = (tmp_path / "sabnzbd.ini").read_text(encoding="utf-8")

    assert "news.example.invalid" in texte, "la configuration existante a ete perdue"
    if "port ajoute" in message:
        assert "port = 8085" in texte, "port annonce mais absent du fichier"
    if "hotes ajoutes" in message:
        assert "host_whitelist" in texte, "hotes annonces mais absents du fichier"


def test_un_fichier_080_est_migre_vers_le_nouveau_port_sans_perdre_sa_cle(tmp_path):
    seed.seed_sabnzbd(
        tmp_path,
        api_key="CLE-080",
        port=8080,
        hotes_autorises=["sabnzbd", "plugarr-sabnzbd", "localhost"],
        incomplet="/data/usenet/.incomplete",
        complet="/data/usenet",
    )

    _ecrit, message = seed.seed_sabnzbd(
        tmp_path,
        api_key="NOUVELLE-CLE-A-IGNORER",
        port=8085,
        hotes_autorises=[
            "sabnzbd",
            "plugarr-sabnzbd",
            "localhost",
            "gluetun",
            "plugarr-gluetun",
        ],
        incomplet="/autre/incomplet",
        complet="/autre/complet",
    )
    texte = (tmp_path / "sabnzbd.ini").read_text(encoding="utf-8")

    assert "port = 8085" in texte
    assert "CLE-080" in texte
    assert "NOUVELLE-CLE-A-IGNORER" not in texte
    assert '/data/usenet/.incomplete' in texte
    assert "gluetun" in texte and "plugarr-gluetun" in texte
    assert "port 8080 -> 8085" in message


# ------------------------------------------------------------------ arborescence


def test_l_usenet_a_son_propre_arbre():
    """Torrent et Usenet ont des durees de vie differentes : un torrent doit
    rester en partage apres l'import, un NZB non. Melanger les deux fait
    effacer par l'un ce que l'autre partage encore."""
    assert "usenet/.incomplete" in DATA_SUBDIRS
    assert "usenet/tv" in DATA_SUBDIRS
    assert "torrents/tv" in DATA_SUBDIRS


def test_les_deux_arbres_partagent_le_point_de_montage():
    """Condition des liens physiques."""
    assert CONTAINER_PATHS["usenet_root"].startswith("/data/")
    assert CONTAINER_PATHS["torrents_root"].startswith("/data/")


def test_il_voit_data_en_entier():
    """Monter seulement /data/usenet obligerait chaque import a recopier."""
    volumes = compose.build_compose(_cfg())["services"]["sabnzbd"]["volumes"]

    assert "${DATA_ROOT}:/data" in volumes


# ------------------------------------------------------------------ categories


class _Faux(SabnzbdClient):
    """Journalise, et reproduit les categories d'usine."""

    def __init__(self, categories=None):
        self.name = "faux"
        self._cats = dict(categories if categories is not None else {"movies": "", "tv": ""})
        self.poses: list[tuple[str, str]] = []

    def categories(self):
        return dict(self._cats)

    def _call(self, mode, **params):
        if mode == "set_config":
            self._cats[params["keyword"]] = params["dir"]
            self.poses.append((params["keyword"], params["dir"]))
        return {}


def test_une_categorie_d_usine_vide_est_remplie():
    """Le piege : le nom existe deja, mais son repertoire est vide. Se
    contenter de tester la presence laisse tout atterrir au mauvais endroit."""
    faux = _Faux({"tv": ""})

    assert faux.ensure_category("tv", "/data/usenet/tv") is True
    assert faux.categories()["tv"] == "/data/usenet/tv"


def test_une_categorie_deja_reglee_n_est_pas_ecrasee():
    """Un repertoire vide est un defaut d'usine ; un repertoire renseigne est
    une decision."""
    faux = _Faux({"tv": "/mon/chemin/a/moi"})

    assert faux.ensure_category("tv", "/data/usenet/tv") is False
    assert faux.categories()["tv"] == "/mon/chemin/a/moi"


def test_une_categorie_absente_est_creee():
    faux = _Faux({})

    assert faux.ensure_category("anime", "/data/usenet/anime") is True


def test_prowlarr_recoit_sa_categorie():
    """Il REFUSE de se declarer sans elle : « The category you entered doesn't
    exist in Sabnzbd. »"""
    import inspect

    source = inspect.getsource(Wirer.step_sabnzbd_categories)

    assert '"prowlarr"' in source


def test_les_categories_precedent_la_declaration():
    """Les *arr n'envoient qu'un NOM de categorie : elle doit deja porter son
    repertoire quand ils la citent."""
    noms = [e.name for e in Wirer(_cfg("sabnzbd", "sonarr")).build_plan()]

    assert noms.index("sabnzbd/categories") < noms.index("sonarr/downloadclient/sabnzbd")


@pytest.mark.parametrize("arr_id", ["sonarr", "radarr", "lidarr"])
def test_chaque_arr_le_declare(arr_id):
    noms = [e.name for e in Wirer(_cfg("sabnzbd", arr_id)).build_plan()]

    assert f"{arr_id}/downloadclient/sabnzbd" in noms
