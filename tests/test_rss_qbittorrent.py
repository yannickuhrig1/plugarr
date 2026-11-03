"""Le lecteur RSS de qBittorrent, et son interrupteur cache.

Demande a l'usage : « le lecteur RSS interne de qBittorrent avec ses regles de
telechargement automatique, oui c'est de ca que je parle ».

Le piege est net et verifie contre une 5.2.3 installee par plugarr : le moteur
RSS est livre ACTIF, mais le telechargement automatique ETEINT.

    rss_processing_enabled       = True
    rss_auto_downloading_enabled = False

Une regle ecrite dans cet etat ne se declenche jamais, et rien ne l'explique.

plugarr n'ajoute AUCUN flux ni AUCUNE regle : ils dependent de vos traqueurs,
exactement comme les indexeurs de Prowlarr. Il pose l'interrupteur.
"""

from __future__ import annotations

import json

from plugarr.clients.qbittorrent import QBittorrentClient


class _FauxQb(QBittorrentClient):
    """Journalise les appels au lieu de les emettre."""

    def __init__(self, prefs):
        self.name = "faux"
        self._prefs = dict(prefs)
        self.ecrits: list[dict] = []

    def preferences(self):
        return dict(self._prefs)

    class _Reponse:
        status_code = 200
        text = ""

    def _poster(self, chemin, data):
        self.ecrits.append(json.loads(data["json"]))
        self._prefs.update(json.loads(data["json"]))
        return self._Reponse()

    @property
    def _http(self):
        faux = self

        class _Client:
            @staticmethod
            def request(methode, chemin, data=None, **kw):
                return faux._poster(chemin, data)

        return _Client()


def test_le_telechargement_automatique_est_allume():
    qb = _FauxQb({"rss_processing_enabled": True, "rss_auto_downloading_enabled": False})

    changes = qb.ensure_rss()

    assert "rss_auto_downloading_enabled" in changes
    assert qb.ecrits[0]["rss_auto_downloading_enabled"] is True


def test_un_reglage_deja_bon_n_est_pas_reecrit():
    qb = _FauxQb(
        {
            "rss_processing_enabled": True,
            "rss_auto_downloading_enabled": True,
            "rss_refresh_interval": 15,
        }
    )

    assert qb.ensure_rss() == []
    assert qb.ecrits == []


def test_seuls_les_reglages_a_changer_sont_envoyes():
    """Renvoyer la preference entiere ecraserait tout le reste."""
    qb = _FauxQb(
        {
            "rss_processing_enabled": True,
            "rss_auto_downloading_enabled": False,
            "rss_refresh_interval": 15,
            "dht": True,
        }
    )

    qb.ensure_rss()

    assert set(qb.ecrits[0]) == {"rss_auto_downloading_enabled"}
    assert qb.preferences()["dht"] is True


def test_l_intervalle_se_regle():
    qb = _FauxQb({"rss_refresh_interval": 30})

    qb.ensure_rss(refresh_minutes=5)

    assert qb.ecrits[0]["rss_refresh_interval"] == 5


def test_le_resultat_est_RELU_et_non_suppose():
    """`setPreferences` repond 200 meme pour un reglage inconnu, qu'il ignore
    ensuite en silence. Le meme piege que `PUT config/host` chez Sonarr."""
    import inspect

    source = inspect.getsource(QBittorrentClient.ensure_rss)

    assert "relu = self.preferences()" in source


def test_l_etape_est_au_plan_quand_qbittorrent_est_installe():
    from plugarr import orchestrator
    from plugarr.wiring import Wirer

    cfg = orchestrator.build_config(
        services=["qbittorrent", "sonarr"], config_root="/c", data_root="/d"
    )

    assert "qbittorrent/rss" in [e.name for e in Wirer(cfg).build_plan()]


def test_aucune_etape_rss_sans_qbittorrent():
    """Transmission n'a pas de lecteur RSS."""
    from plugarr import orchestrator
    from plugarr.wiring import Wirer

    cfg = orchestrator.build_config(
        services=["transmission", "sonarr"], config_root="/c", data_root="/d"
    )

    assert "qbittorrent/rss" not in [e.name for e in Wirer(cfg).build_plan()]
