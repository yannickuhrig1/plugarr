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


# ------------------------------------------------- piles reseau orphelines


class _RunnerFactice:
    """Compose reduit a ce que la reparation lui demande."""

    def __init__(self, ok=True):
        self.ok = ok
        self.recrees: list[str] = []

    def recreate(self, service, timeout=600):
        self.recrees.append(service)
        return self.ok, "" if self.ok else "no such service"


def test_une_pile_orpheline_est_detectee(monkeypatch):
    """Reproduit le 2026-09-07 : Gluetun recree seul, le client reste accroche
    au conteneur DETRUIT. Il affiche « Up », n'a plus que `lo`, et rien ne le
    dit."""
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "neuf")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: "container:detruit")

    assert vpncheck.piles_orphelines(_cfg("qbittorrent", vpn=True)) == ["qbittorrent"]


def test_une_pile_alignee_n_est_pas_orpheline(monkeypatch):
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "neuf")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: "container:neuf")

    assert vpncheck.piles_orphelines(_cfg("qbittorrent", vpn=True)) == []


def test_un_client_sur_le_reseau_nu_est_orphelin(monkeypatch):
    """L'incident du 2026-09-03 : la meme reparation le rattrape."""
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "neuf")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: "plugarr_plugarr")

    assert vpncheck.piles_orphelines(_cfg("qbittorrent", vpn=True)) == ["qbittorrent"]


def test_sans_vpn_aucune_pile_n_est_orpheline(monkeypatch):
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "neuf")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: "plugarr_plugarr")

    assert vpncheck.piles_orphelines(_cfg("qbittorrent")) == []


def test_un_client_adopte_n_est_jamais_recree(monkeypatch):
    """Il n'a pas de bloc compose : le recreer echouerait, et il ne nous
    appartient pas."""
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "neuf")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: "container:detruit")
    cfg = _cfg("qbittorrent", vpn=True)
    cfg.services["qbittorrent"].adopted = True

    assert vpncheck.piles_orphelines(cfg) == []


def test_l_installation_racroche_une_pile_orpheline(monkeypatch):
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "neuf")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: "container:detruit")
    runner = _RunnerFactice()
    emis = []

    orchestrator._reparer_piles_orphelines(_cfg("qbittorrent", vpn=True), runner, emis.append)

    assert runner.recrees == ["qbittorrent"]
    assert emis and emis[0].ok
    assert "rattaches" in emis[0].message


def test_une_reparation_impossible_est_signalee(monkeypatch):
    """Echouer en silence serait pire que ne rien tenter : le client resterait
    mort avec un rapport tout vert."""
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "neuf")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: "container:detruit")
    runner = _RunnerFactice(ok=False)
    emis = []

    orchestrator._reparer_piles_orphelines(_cfg("qbittorrent", vpn=True), runner, emis.append)

    assert emis and not emis[0].ok
    assert "doctor" in emis[0].message


def test_rien_a_reparer_n_emet_aucun_evenement(monkeypatch):
    """Annoncer « rien a faire » a chaque installation noierait le cas ou il y
    a vraiment eu quelque chose a faire."""
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "neuf")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: "container:neuf")
    runner = _RunnerFactice()
    emis = []

    orchestrator._reparer_piles_orphelines(_cfg("qbittorrent", vpn=True), runner, emis.append)

    assert emis == []
    assert runner.recrees == []


# ------------------------------------------------- verdict a l'installation


def test_l_installation_rend_un_verdict_vpn(monkeypatch):
    """`vpncheck` existait, mais seuls `doctor` et la console l'appelaient : on
    pouvait installer avec VPN et repartir sans qu'il ait jamais tourne."""
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "abc")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: "container:abc")
    monkeypatch.setattr(
        vpncheck,
        "exec_in",
        lambda c, cmd, **kw: (True, '{"public_ip":"1.2.3.4","country":"Netherlands"}'),
    )
    monkeypatch.setattr(vpncheck, "ip_de_l_hote", lambda: "9.9.9.9")
    emis = []

    orchestrator._verdict_vpn(_cfg("qbittorrent", vpn=True), emis.append)

    assert len(emis) == 1
    assert emis[0].ok
    assert emis[0].phase == "protection VPN"


def test_un_verdict_vpn_negatif_est_marque_en_echec(monkeypatch):
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "abc")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: "plugarr_plugarr")
    emis = []

    orchestrator._verdict_vpn(_cfg("qbittorrent", vpn=True), emis.append)

    assert len(emis) == 1
    assert not emis[0].ok
    assert "NON PROTEGE" in emis[0].message


def test_sans_client_torrent_aucun_verdict(monkeypatch):
    """Sans trafic BitTorrent, il n'y a rien a proteger et rien a annoncer."""
    emis = []

    orchestrator._verdict_vpn(_cfg("sonarr"), emis.append)

    assert emis == []


# --------------------------------------------- synchronisation du port entrant


def _cfg_pf(*services, provider="protonvpn"):
    cfg = _cfg(*services, vpn=True)
    cfg.vpn.provider = provider
    return cfg


def test_sans_port_entrant_aucune_synchronisation():
    """Mullvad chiffre autant, mais n'attribue aucun port : il n'y a rien a
    suivre, donc rien a poser."""
    assert compose.port_sync_clients(_cfg_pf("qbittorrent", provider="mullvad")) == []


def test_sans_vpn_aucune_synchronisation():
    assert compose.port_sync_clients(_cfg("qbittorrent")) == []


def test_les_deux_clients_sont_synchronises():
    assert compose.port_sync_clients(_cfg_pf("qbittorrent", "transmission")) == [
        "qbittorrent",
        "transmission",
    ]


def test_un_client_adopte_n_est_pas_synchronise():
    """Ses identifiants ne nous appartiennent pas."""
    cfg = _cfg_pf("qbittorrent", "transmission")
    cfg.services["qbittorrent"].adopted = True

    assert compose.port_sync_clients(cfg) == ["transmission"]


def test_gluetun_recoit_la_commande_et_les_identifiants():
    env = compose.build_compose(_cfg_pf("qbittorrent", "transmission"))["services"]["gluetun"][
        "environment"
    ]

    assert env["VPN_PORT_FORWARDING"] == "on"
    assert compose.PORT_SYNC in env["VPN_PORT_FORWARDING_UP_COMMAND"]
    assert "{{PORT}}" in env["VPN_PORT_FORWARDING_UP_COMMAND"]
    # Les mots de passe passent par le .env, comme celui de Flood.
    assert env["QBT_PASS"] == "${QBITTORRENT_PASS}"
    assert env["TR_PASS"] == "${TRANSMISSION_PASS}"


def test_aucun_mot_de_passe_en_clair_dans_le_compose():
    cfg = _cfg_pf("qbittorrent", "transmission")
    rendu = compose.render_compose(cfg)

    for sid in ("qbittorrent", "transmission"):
        assert cfg.services[sid].password not in rendu, sid


def test_gluetun_reste_nu_sans_port_entrant():
    env = compose.build_compose(_cfg_pf("qbittorrent", provider="mullvad"))["services"]["gluetun"][
        "environment"
    ]

    assert "VPN_PORT_FORWARDING_UP_COMMAND" not in env
    assert "QBT_PASS" not in env


def test_le_script_vise_les_ports_internes():
    """Dans la pile de Gluetun, c'est le port INTERNE du conteneur qui repond,
    pas celui publie sur l'hote."""
    script = compose.render_port_sync(_cfg_pf("qbittorrent", "transmission"))

    assert "127.0.0.1:8080/api/v2/app/setPreferences" in script
    assert "127.0.0.1:9091/transmission/rpc" in script


def test_le_script_attend_que_le_client_ecoute():
    """Au demarrage, le port peut arriver AVANT l'interface du client. Sans
    attente, la pose echouerait et le port resterait faux jusqu'au bail suivant."""
    script = compose.render_port_sync(_cfg_pf("qbittorrent"))

    assert "essayer poser_qbittorrent" in script
    assert "sleep" in script


def test_le_script_negocie_la_session_transmission():
    """Transmission repond 409 au premier appel : sans cet aller-retour, tout
    POST est refuse."""
    script = compose.render_port_sync(_cfg_pf("transmission"))

    assert "X-Transmission-Session-Id" in script
    assert "session-set" in script


def test_le_script_ne_contient_que_les_clients_installes():
    script = compose.render_port_sync(_cfg_pf("qbittorrent"))

    assert "poser_qbittorrent" in script
    assert "transmission" not in script


def test_le_script_est_ecrit_a_cote_de_gluetun(tmp_path):
    """C'est le seul dossier que Gluetun monte deja : lui en monter un second
    pour un fichier serait un mecanisme de plus a expliquer."""
    cfg = _cfg_pf("qbittorrent")
    cfg.config_root = str(tmp_path / "config")
    ecrits = compose.write_artifacts(cfg, tmp_path / "projet")

    script = tmp_path / "config" / "gluetun" / compose.PORT_SYNC
    assert script in ecrits
    assert script.read_text(encoding="utf-8").startswith("#!/bin/sh")


def test_aucun_script_sans_port_entrant(tmp_path):
    cfg = _cfg_pf("qbittorrent", provider="mullvad")
    cfg.config_root = str(tmp_path / "config")
    compose.write_artifacts(cfg, tmp_path / "projet")

    assert not (tmp_path / "config" / "gluetun" / compose.PORT_SYNC).exists()


# ------------------------------------------ controle du port reellement ecoute


def test_le_releve_des_ports_est_analyse(monkeypatch):
    monkeypatch.setattr(
        vpncheck,
        "exec_in",
        lambda c, cmd, **kw: (True, "annonce=37899\nqbittorrent=37899\ntransmission=51413\n"),
    )

    assert vpncheck.ports_entrants(_cfg_pf("qbittorrent", "transmission")) == {
        "annonce": 37899,
        "qbittorrent": 37899,
        "transmission": 51413,
    }


def test_aucun_releve_sans_port_entrant(monkeypatch):
    monkeypatch.setattr(vpncheck, "exec_in", lambda c, cmd, **kw: (True, "annonce=1"))

    assert vpncheck.ports_entrants(_cfg_pf("qbittorrent", provider="mullvad")) == {}


def test_un_port_qui_concorde_est_accepte(monkeypatch):
    monkeypatch.setattr(
        vpncheck, "ports_entrants", lambda cfg: {"annonce": 37899, "qbittorrent": 37899}
    )

    controle = vpncheck._controle_port(_cfg_pf("qbittorrent"))[0]

    assert controle.ok
    assert "37899" in controle.detail


def test_un_port_desynchronise_est_signale(monkeypatch):
    """Observe le 2026-09-08 : Proton avait change de port, qBittorrent ecoutait
    toujours l'ancien, et rien nulle part ne le disait."""
    monkeypatch.setattr(
        vpncheck, "ports_entrants", lambda cfg: {"annonce": 48406, "qbittorrent": 45270}
    )

    controle = vpncheck._controle_port(_cfg_pf("qbittorrent"))[0]

    assert not controle.ok
    assert "48406" in controle.detail and "45270" in controle.detail


def test_un_port_desynchronise_ne_bloque_pas(monkeypatch):
    """Sans port entrant on telecharge tres bien, on partage seulement moins.
    Faire echouer une installation pour un ratio serait disproportionne."""
    monkeypatch.setattr(
        vpncheck, "ports_entrants", lambda cfg: {"annonce": 48406, "qbittorrent": 45270}
    )

    assert vpncheck._controle_port(_cfg_pf("qbittorrent"))[0].blocking is False


def test_aucun_port_obtenu_est_distingue_d_un_port_different(monkeypatch):
    """`port: 0` est le sentinel de Gluetun : le tunnel tient, mais le
    fournisseur n'a rien attribue. Ce n'est pas la meme panne."""
    monkeypatch.setattr(
        vpncheck, "ports_entrants", lambda cfg: {"annonce": 0, "qbittorrent": 45270}
    )

    controles = vpncheck._controle_port(_cfg_pf("qbittorrent"))

    assert len(controles) == 1
    assert not controles[0].ok
    assert "aucun port" in controles[0].detail


def test_le_port_et_la_protection_sont_deux_verdicts(monkeypatch):
    """Un port desynchronise coute du partage, pas de l'exposition. L'annoncer
    sous « protection VPN » ferait craindre une fuite la ou il n'y en a aucune."""
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "abc")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: "container:abc")
    monkeypatch.setattr(
        vpncheck,
        "_sortie",
        lambda conteneur: (True, "sortie par Austria"),
    )
    monkeypatch.setattr(
        vpncheck, "ports_entrants", lambda cfg: {"annonce": 48406, "qbittorrent": 45270}
    )
    emis = []

    orchestrator._verdict_vpn(_cfg_pf("qbittorrent"), emis.append)

    phases = {p.phase: p for p in emis}
    assert phases["protection VPN"].ok, "la protection n'est pas en cause"
    assert not phases["port entrant"].ok


# ------------------------------------------- la piste quand le port a manque


def _cfg_openvpn(*services, fournisseur="protonvpn", identifiant="bP56HY0lucT2voPV"):
    cfg = _cfg(*services)
    cfg.vpn = VpnConfig(
        enabled=True,
        provider=fournisseur,
        vpn_type="openvpn",
        openvpn_user=identifiant,
        openvpn_password="mdp",
    )
    return cfg


def test_un_port_manquant_en_openvpn_proton_donne_la_piste_pmp(monkeypatch):
    """Gluetun connait la reponse mais ne la dit que dans son propre journal, et
    seulement apres un refus : « make sure you have +pmp at the end of your
    OpenVPN username » (v3.41.3). L'utilisateur, lui, ne voyait que « aucun port
    obtenu »."""
    monkeypatch.setattr(vpncheck, "ports_entrants", lambda cfg: {"annonce": 0})

    controle = vpncheck._controle_port(_cfg_openvpn("qbittorrent"))[0]

    assert not controle.ok
    assert "+pmp" in controle.detail


def test_la_piste_ne_se_repete_pas_si_le_suffixe_est_deja_la(monkeypatch):
    monkeypatch.setattr(vpncheck, "ports_entrants", lambda cfg: {"annonce": 0})

    cfg = _cfg_openvpn("qbittorrent", identifiant="bP56HY0lucT2voPV+pmp")

    assert "+pmp" not in vpncheck._controle_port(cfg)[0].detail


def test_la_piste_ne_sort_pas_en_wireguard(monkeypatch):
    """La cle WireGuard porte deja les options de session, choisies sur le site
    au moment de la generer. Renvoyer vers un suffixe d'identifiant enverrait
    chercher une chose qui n'existe pas dans ce mode."""
    monkeypatch.setattr(vpncheck, "ports_entrants", lambda cfg: {"annonce": 0})

    assert "+pmp" not in vpncheck._controle_port(_cfg("qbittorrent", vpn=True))[0].detail


def test_la_piste_ne_sort_pas_chez_un_autre_fournisseur(monkeypatch):
    """`+pmp` est un suffixe ProtonVPN. Le proposer ailleurs enverrait inventer
    un identifiant que le fournisseur ne connait pas."""
    monkeypatch.setattr(vpncheck, "ports_entrants", lambda cfg: {"annonce": 0})

    cfg = _cfg_openvpn("qbittorrent", fournisseur="privatevpn")

    assert "+pmp" not in vpncheck._controle_port(cfg)[0].detail


def test_la_piste_ne_sort_pas_quand_le_port_est_arrive(monkeypatch):
    """Une piste affichee alors que tout va bien est du bruit, et elle ferait
    douter d'une installation saine."""
    monkeypatch.setattr(
        vpncheck, "ports_entrants", lambda cfg: {"annonce": 47878, "qbittorrent": 47878}
    )

    controles = vpncheck._controle_port(_cfg_openvpn("qbittorrent"))

    assert all(c.ok for c in controles)
    assert not any("+pmp" in c.detail for c in controles)


# --------------------------------------------- un client adopte sous VPN


def _cfg_adopte(nom="mon-qbittorrent-a-moi"):
    """La combinaison qu'aucun chemin ne produit aujourd'hui : `adopt` n'ecrit
    jamais de VPN et `reprise` ne reporte ni `adopted` ni `container`. Mais
    `stack.yml` se lit et s'edite, et un verdict de protection ne doit pas
    dependre de ce qu'aucun chemin ne l'atteigne."""
    cfg = _cfg("qbittorrent", vpn=True)
    cfg.services["qbittorrent"].adopted = True
    cfg.services["qbittorrent"].container = nom
    return cfg


def test_un_client_adopte_est_cherche_sous_son_vrai_nom():
    cfg = _cfg_adopte()

    assert vpncheck.nom_conteneur(cfg, "qbittorrent") == "mon-qbittorrent-a-moi"
    assert vpncheck.nom_conteneur(_cfg("qbittorrent", vpn=True), "qbittorrent") == (
        "plugarr-qbittorrent"
    )


def test_un_client_adopte_hors_du_tunnel_n_est_pas_declare_vert(monkeypatch):
    """Chercher `plugarr-qbittorrent` pour un conteneur qui s'appelle autrement
    ne trouvait rien, `network_mode` rendait None, et None veut dire « conteneur
    arrete » : un controle VERT sur un client qui tourne hors du tunnel."""
    vus = []

    def _mode(nom):
        vus.append(nom)
        return "pont" if nom == "mon-qbittorrent-a-moi" else None

    monkeypatch.setattr(vpncheck, "container_id", lambda n: "abc123")
    monkeypatch.setattr(vpncheck, "network_mode", _mode)

    controle = vpncheck.verifier(_cfg_adopte())[0]

    assert "mon-qbittorrent-a-moi" in vus
    assert not controle.ok
    assert "NON PROTEGE" in controle.detail


def test_on_ne_conseille_pas_de_regenerer_une_pile_qu_on_ne_gere_pas(monkeypatch):
    """`adopt` ne genere aucun compose, deliberement : en generer un donnerait a
    `uninstall` le pouvoir de detruire la stack de l'utilisateur. « Regenerez la
    pile » enverrait donc tourner en rond."""
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "abc123")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: "pont")

    adopte = vpncheck.verifier(_cfg_adopte())[0].detail
    gere = vpncheck.verifier(_cfg("qbittorrent", vpn=True))[0].detail

    assert "Regenerez la pile" not in adopte
    assert "recreer vous-meme" in adopte
    assert "Regenerez la pile" in gere


def test_un_client_adopte_dans_le_tunnel_est_accepte(monkeypatch):
    """S'il y est deja — recree a la main par son proprietaire — le controle doit
    le constater comme n'importe quel autre."""
    monkeypatch.setattr(vpncheck, "container_id", lambda n: "abc123")
    monkeypatch.setattr(vpncheck, "network_mode", lambda n: "container:abc123")
    monkeypatch.setattr(
        vpncheck,
        "exec_in",
        lambda c, cmd, **kw: (True, '{"public_ip":"1.2.3.4","country":"Netherlands"}'),
    )

    controle = vpncheck.verifier(_cfg_adopte())[0]

    assert controle.ok
    assert "Netherlands" in controle.detail


# ------------------------- un fournisseur mal tape n'est pas un plantage


def _invoquer(*args):
    from typer.testing import CliRunner

    from plugarr import cli

    return CliRunner().invoke(cli.app, ["install", "--dry-run", *args])


def test_un_fournisseur_vpn_inconnu_donne_une_erreur_et_non_un_traceback():
    """Trouve en eprouvant l'executable de la 0.8.0, pas en relisant le code.

    `VpnConfig` refusait bien le fournisseur, mais la `ValidationError` remontait
    nue : traceback pydantic, lien vers errors.pydantic.dev, et une derniere
    ligne « Failed to execute script 'launcher' » qui annonce un plantage a
    quelqu'un qui a simplement fait une faute de frappe.

    La phrase utile etait pourtant deja ecrite par le validateur. Elle etait
    seulement noyee."""
    resultat = _invoquer("--vpn", "--vpn-provider", "zorglub", "--vpn-key", "abc")

    assert resultat.exit_code == 1
    assert "fournisseur VPN inconnu" in resultat.output
    assert "protonvpn" in resultat.output, "les choix possibles doivent rester lisibles"
    assert "Traceback" not in resultat.output
    assert "pydantic.dev" not in resultat.output


def test_un_protocole_vpn_inconnu_aussi():
    """L'autre validateur de `VpnConfig` passait par le meme chemin."""
    resultat = _invoquer(
        "--vpn", "--vpn-provider", "protonvpn", "--vpn-type", "ipsec", "--vpn-key", "abc"
    )

    assert resultat.exit_code == 1
    assert "type de VPN inconnu" in resultat.output
    assert "Traceback" not in resultat.output


# ------------------------------- reposer le port, pas seulement le constater


def _releves(monkeypatch, *suites):
    """Fait rendre a `ports_entrants` un releve different a chaque appel."""
    restants = list(suites)
    monkeypatch.setattr(vpncheck, "ports_entrants", lambda cfg: restants.pop(0))
    return restants


def test_un_port_synchronise_ne_declenche_aucune_remise(monkeypatch):
    """Annoncer « rien a faire » a chaque diagnostic noierait le cas ou il y a
    vraiment eu quelque chose."""
    _releves(monkeypatch, {"annonce": 47878, "qbittorrent": 47878})

    assert vpncheck.reparer_port(_cfg_pf("qbittorrent")) is None


def test_sans_port_annonce_il_n_y_a_rien_a_reposer(monkeypatch):
    """0 est le sentinel de Gluetun : pas de port du tout. Poser 0 chez le client
    serait pire que ne rien faire."""
    _releves(monkeypatch, {"annonce": 0, "qbittorrent": 45270})

    assert vpncheck.reparer_port(_cfg_pf("qbittorrent")) is None


def test_le_port_desynchronise_est_repose_avec_le_script_de_gluetun(monkeypatch):
    """On rejoue le script que Gluetun lance lui-meme plutot que d ecrire une
    seconde pose : deux implementations de la meme chose finiraient par ne plus
    faire la meme chose."""
    from plugarr.compose import PORT_SYNC

    _releves(
        monkeypatch,
        {"annonce": 48406, "qbittorrent": 45270},
        {"annonce": 48406, "qbittorrent": 48406},
    )
    appels = []
    monkeypatch.setattr(
        vpncheck, "exec_in", lambda c, cmd, **kw: (appels.append((c, cmd)), (True, ""))[1]
    )

    controle = vpncheck.reparer_port(_cfg_pf("qbittorrent"))

    assert appels == [("plugarr-gluetun", ["sh", f"/gluetun/{PORT_SYNC}", "48406"])]
    assert controle is not None and controle.ok
    assert "48406" in controle.detail


def test_la_remise_est_RELUE_avant_d_etre_annoncee(monkeypatch):
    """Meme exigence que partout ailleurs : on ne dit pas « j ai repose le
    port », on redemande au client ce qu il ecoute. Ici la pose echoue en
    silence et le controle doit le voir."""
    _releves(
        monkeypatch,
        {"annonce": 48406, "qbittorrent": 45270},
        {"annonce": 48406, "qbittorrent": 45270},
    )
    monkeypatch.setattr(vpncheck, "exec_in", lambda c, cmd, **kw: (True, ""))

    controle = vpncheck.reparer_port(_cfg_pf("qbittorrent"))

    assert controle is not None and not controle.ok
    assert "qbittorrent" in controle.detail


def test_la_remise_ne_bloque_jamais(monkeypatch):
    """Sans port entrant on telecharge tres bien, on partage seulement moins."""
    _releves(
        monkeypatch,
        {"annonce": 48406, "qbittorrent": 45270},
        {"annonce": 48406, "qbittorrent": 45270},
    )
    monkeypatch.setattr(vpncheck, "exec_in", lambda c, cmd, **kw: (True, ""))

    assert vpncheck.reparer_port(_cfg_pf("qbittorrent")).blocking is False


def test_doctor_repose_le_port_au_lieu_de_seulement_le_signaler():
    """Le test porte sur la STRUCTURE : `doctor` doit appeler la remise, et
    seulement quand un controle de port a echoue — sans cette condition, chaque
    diagnostic relirait les ports une seconde fois pour rien."""
    import ast
    import inspect
    import textwrap

    from plugarr import cli

    source = textwrap.dedent(inspect.getsource(cli.doctor))
    arbre = ast.parse(source)
    appelle = any(
        isinstance(n, ast.Attribute) and n.attr == "reparer_port" for n in ast.walk(arbre)
    )

    assert appelle, "doctor doit reposer le port, pas seulement le constater"
    assert "PREFIXE_PORT" in source, "et seulement si un controle de port a echoue"

