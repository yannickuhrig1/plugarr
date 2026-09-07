"""Le trafic torrent sort-il vraiment par le tunnel, et qui sait le joindre ?

Deux demandes le meme jour, meme racine.

« C'est le coup a lancer un torrent et ne pas etre protege par le VPN. » La
crainte est fondee : plugarr ecrivait `network_mode: service:gluetun` et
considerait l'affaire close. Or ce reglage se perd — une installation lancee
par-dessus une pile existante, depuis une configuration sans VPN, a recree les
clients torrent sur le reseau nu, sans un mot.

« Flood me dit impossible de se connecter au client. » Flood, lui, n'est PAS
dans le tunnel : le client de telechargement y est et perd son alias DNS.
`http://qbittorrent:8080` ne resout plus depuis Flood.
"""

from __future__ import annotations

import json

import pytest

from plugarr import compose, orchestrator, vpncheck
from plugarr.models import Category, VpnConfig


def _cfg(*services, vpn=False):
    cfg = orchestrator.build_config(
        services=list(services), config_root="/c", data_root="/d"
    )
    if vpn:
        cfg.vpn = VpnConfig(
            enabled=True, provider="protonvpn", vpn_type="wireguard", wireguard_private_key="k" * 44
        )
    return cfg


# --------------------------------------------------------------- Flood


@pytest.mark.parametrize("client", ["qbittorrent", "transmission"])
def test_flood_vise_gluetun_sous_vpn(client):
    commande = compose.build_compose(_cfg("flood", client, vpn=True))["services"]["flood"]["command"]

    assert any("gluetun" in a for a in commande), commande
    assert not any(f"//{client}:" in a for a in commande), "Flood vise un nom qui ne resout plus"


@pytest.mark.parametrize("client", ["qbittorrent", "transmission"])
def test_flood_vise_le_client_sans_vpn(client):
    commande = compose.build_compose(_cfg("flood", client))["services"]["flood"]["command"]

    assert any(f"//{client}:" in a for a in commande), commande


def test_le_mot_de_passe_du_client_quitte_le_compose():
    """Dernier secret a rester en clair dans docker-compose.yml, apres la cle
    WireGuard."""
    cfg = _cfg("flood", "qbittorrent")
    secret = cfg.services["qbittorrent"].password

    assert secret and secret not in compose.render_compose(cfg)
    assert "FLOOD_CLIENT_PASS" in compose.render_env(cfg)
    assert secret in compose.render_env(cfg)


def test_flood_ne_pilote_qu_un_client():
    """Les deux installes : qBittorrent gagne, son API est plus riche."""
    assert compose.flood_client(_cfg("flood", "qbittorrent", "transmission")) == "qbittorrent"
    assert compose.flood_client(_cfg("flood", "transmission")) == "transmission"
    assert compose.flood_client(_cfg("qbittorrent")) is None


# --------------------------------------------------- controle de fuite


def test_sans_client_torrent_il_n_y_a_rien_a_verifier():
    assert vpncheck.verifier(_cfg("sonarr")) == []


def test_sans_vpn_le_controle_le_dit_sans_crier():
    """Se passer de VPN est un choix, pas une panne. Mais il doit etre visible."""
    controles = vpncheck.verifier(_cfg("qbittorrent"))

    assert len(controles) == 1
    assert controles[0].ok and not controles[0].blocking
    assert "aucun VPN" in controles[0].detail


def test_un_client_hors_du_tunnel_est_un_echec_bloquant(monkeypatch):
    """Le scenario redoute, mot pour mot : le conteneur a ete recree sur le
    reseau nu et tout torrent lance sortirait par la connexion de la maison."""
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "abc123")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: "plugarr_plugarr")

    controle = vpncheck.verifier(_cfg("qbittorrent", vpn=True))[0]

    assert not controle.ok
    assert controle.blocking
    assert "NON PROTEGE" in controle.detail


def test_un_client_dans_le_tunnel_qui_sort_est_accepte(monkeypatch):
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "abc123")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: "container:abc123")
    monkeypatch.setattr(
        vpncheck,
        "exec_in",
        lambda c, cmd, **kw: (True, '{"public_ip":"1.2.3.4","country":"Netherlands"}'),
    )

    controle = vpncheck.verifier(_cfg("qbittorrent", vpn=True))[0]

    assert controle.ok
    assert "Netherlands" in controle.detail


def test_l_adresse_ip_n_est_jamais_rapportee(monkeypatch):
    """Le journal est le fichier qu'on demande de joindre a un rapport de bug.
    Le pays et l'operateur suffisent a reconnaitre un tunnel."""
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "abc123")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: "container:abc123")
    monkeypatch.setattr(
        vpncheck,
        "exec_in",
        lambda c, cmd, **kw: (True, '{"public_ip":"62.112.9.192","country":"Netherlands"}'),
    )

    controle = vpncheck.verifier(_cfg("qbittorrent", vpn=True))[0]

    assert "62.112.9.192" not in controle.detail


def test_un_tunnel_tombe_est_un_echec(monkeypatch):
    """Gluetun ne repond plus : on ne peut PAS affirmer que le trafic est
    protege, donc on ne l'affirme pas."""
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "abc123")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: "container:abc123")
    monkeypatch.setattr(vpncheck, "exec_in", lambda c, cmd, **kw: (False, "refused"))

    controle = vpncheck.verifier(_cfg("qbittorrent", vpn=True))[0]

    assert not controle.ok


def test_un_conteneur_arrete_n_est_pas_une_fuite(monkeypatch):
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "abc123")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: None)

    controle = vpncheck.verifier(_cfg("qbittorrent", vpn=True))[0]

    assert controle.ok and not controle.blocking


def test_tous_les_clients_torrent_sont_examines(monkeypatch):
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "abc123")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: "container:abc123")
    monkeypatch.setattr(vpncheck, "exec_in", lambda c, cmd, **kw: (True, '{"public_ip":"1.2.3.4"}'))

    noms = [c.name for c in vpncheck.verifier(_cfg("qbittorrent", "transmission", vpn=True))]

    assert sorted(noms) == ["VPN qbittorrent", "VPN transmission"]


def test_seuls_les_clients_torrent_comptent():
    """Jellyfin ou Sonarr n'ont rien a faire dans le tunnel."""
    cfg = _cfg("qbittorrent", "sonarr", "jellyfin", vpn=True)

    assert vpncheck.clients_torrent(cfg) == ["qbittorrent"]
    for sid in vpncheck.clients_torrent(cfg):
        from plugarr import catalog

        assert catalog.get(sid).category is Category.DOWNLOAD


# ------------------------------ le tunnel ressort-il ailleurs que chez vous ?


def _tunnel(monkeypatch, ip_tunnel, ip_hote):
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "abc")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: "container:abc")
    monkeypatch.setattr(
        vpncheck,
        "exec_in",
        lambda c, cmd, **kw: (
            True,
            json.dumps(
                {
                    "public_ip": ip_tunnel,
                    "country": "France",
                    "organization": "AS12322 Free",
                }
            ),
        ),
    )
    monkeypatch.setattr(vpncheck, "ip_de_l_hote", lambda: ip_hote)
    return vpncheck.verifier(_cfg("qbittorrent", vpn=True))[0]


def test_un_tunnel_qui_reboucle_a_la_maison_est_une_fuite(monkeypatch):
    """Les deux premiers controles le declarent bon : le conteneur EST dans le
    tunnel. Trouve sur le banc d'essai, avec un serveur WireGuard local qui
    traduisait les adresses vers la sortie du domicile. Un fournisseur mal
    configure produirait exactement la meme chose."""
    controle = _tunnel(monkeypatch, "82.67.130.52", "82.67.130.52")

    assert not controle.ok
    assert controle.blocking
    assert "VOTRE adresse publique" in controle.detail


def test_une_sortie_differente_est_acceptee(monkeypatch):
    controle = _tunnel(monkeypatch, "62.112.9.192", "82.67.130.52")

    assert controle.ok
    assert "differente de la votre" in controle.detail


def test_l_adresse_de_l_hote_introuvable_ne_fait_pas_echouer(monkeypatch):
    """Le diagnostic ne tombe pas parce qu'un service d'adresse est muet : il
    rend son verdict, d'un cran moins ferme, et le dit."""
    controle = _tunnel(monkeypatch, "62.112.9.192", None)

    assert controle.ok
    assert "indeterminable" in controle.detail


def test_aucune_adresse_ne_fuit_dans_le_message(monkeypatch):
    """Ni celle du tunnel ni celle de la machine : le journal se partage."""
    for tunnel, hote in (("82.67.130.52", "82.67.130.52"), ("62.112.9.192", "82.67.130.52")):
        detail = _tunnel(monkeypatch, tunnel, hote).detail
        assert tunnel not in detail
        assert hote not in detail


# ------------------------------------------------- l'avertissement « --vpn seul »


def test_l_avertissement_vpn_est_sous_l_option_vpn():
    """Il vivait sous `if reprendre:`, et parlait donc a tort et a travers.

    Consequence mesuree en lancant l'executable : une reinstallation de Sonarr
    et Jellyfin, sans `--vpn` et sans client de telechargement, affichait
    « --vpn sans client de telechargement » a quelqu'un qui n'avait jamais
    ecrit `--vpn`. Et il restait muet dans le seul cas ou il sert, puisque
    `--repartir-de-zero` sautait le bloc entier.

    Le test porte sur la STRUCTURE et non sur le texte : c'est le placement du
    message qui etait faux, pas sa formulation.
    """
    import ast
    import inspect
    import textwrap

    from plugarr import cli

    arbre = ast.parse(textwrap.dedent(inspect.getsource(cli.install)))
    marqueur = "--vpn sans client de telechargement"

    def porte(noeud) -> bool:
        return any(
            isinstance(n, ast.Constant) and isinstance(n.value, str) and marqueur in n.value
            for n in ast.walk(noeud)
        )

    blocs = {
        noeud.test.id: noeud
        for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.If) and isinstance(noeud.test, ast.Name)
    }

    assert porte(blocs["vpn"]), "l'avertissement doit vivre sous `if vpn:`"
    assert not any(porte(n) for n in blocs["reprendre"].body), (
        "et surtout pas sous `if reprendre:` : il sortirait a chaque reinstallation"
    )
