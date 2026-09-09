"""L'essai de la configuration VPN, avant de batir la stack.

L'assistant ne verifiait que la PRESENCE des champs : une cle fausse passait
l'ecran sans un mot, et l'utilisateur decouvrait un client de telechargement
injoignable sans lien evident avec ce qu'il avait tape trois ecrans plus tot.

Les deux pieges rencontres en ecrivant ce module ont chacun leur test : un
marqueur trop large qui declarait fausse une cle valide, et un verdict fonde sur
la sante du conteneur qui declarait bonne une cle fausse.
"""

from __future__ import annotations

import subprocess

import pytest

from plugarr import vpnessai
from plugarr.models import VpnConfig

IMAGE = "qmcgaw/gluetun:v3.41.3"


def _vpn(**kw):
    base = {
        "enabled": True,
        "provider": "protonvpn",
        "vpn_type": "wireguard",
        "wireguard_private_key": "a" * 43 + "=",
    }
    return VpnConfig(**{**base, **kw})


def _proc(stdout="", stderr="", code=0):
    return subprocess.CompletedProcess([], returncode=code, stdout=stdout, stderr=stderr)


# --------------------------------------------------------- marqueurs certains


def test_le_titre_de_section_n_est_pas_une_erreur():
    """Gluetun affiche « Wireguard settings: » comme titre au demarrage NORMAL.
    Un premier jet le prenait pour un refus et declarait fausse une cle
    parfaitement valide."""
    assert vpnessai._definitif("|   └── wireguard settings:") is None


def test_une_cle_malformee_est_reconnue():
    journal = (
        "error vpn settings: wireguard settings: private key is not valid: "
        "wgtypes: failed to parse base64-encoded key"
    )

    cause = vpnessai._definitif(journal)
    assert cause == "cle"
    assert "cle privee" in vpnessai._message_definitif(cause, "protonvpn")


def test_un_lieu_sans_serveur_est_reconnu():
    journal = "error [vpn] finding a vpn server: filtering servers: no server found:"

    cause = vpnessai._definitif(journal)
    assert cause == "serveur"
    assert "aucun serveur" in vpnessai._message_definitif(cause, "protonvpn")


def test_des_identifiants_openvpn_refuses_sont_reconnus():
    """L'equivalent OpenVPN de la cle refusee, et il manquait : l'essai
    patientait quarante-cinq secondes puis rendait « peut-etre » sur une reponse
    que le serveur avait deja donnee. Recopie d'un journal reel, image v3.41.3,
    avec un mot de passe volontairement faux."""
    journal = "error [openvpn] auth: received control message: auth_failed"

    cause = vpnessai._definitif(journal)
    assert cause == "identifiants"
    assert "identifiants" in vpnessai._message_definitif(cause, "protonvpn")


def test_une_authentification_qui_se_deroule_bien_n_est_pas_une_erreur():
    """Le journal parle d'authentification en marche NORMALE. Un marqueur pose
    sur le mot seul aurait declare faux des identifiants valides."""
    for ligne in (
        "info [openvpn] auth: received control message: auth_ok",
        "info [http server] authentication file path: /gluetun/auth/config.toml",
    ):
        assert vpnessai._definitif(ligne) is None


def test_les_explications_passent_par_la_traduction():
    """Un premier jet gardait la phrase francaise dans le tableau des marqueurs :
    elle serait apparue telle quelle au milieu d'un message anglais."""
    for _marqueur, cause in vpnessai.DEFINITIFS:
        assert cause in ("serveur", "cle", "identifiants"), (
            "un marqueur porte une phrase, pas une cle"
        )
        assert " " not in cause


def test_un_journal_ordinaire_ne_declenche_rien():
    assert vpnessai._definitif("info [wireguard] connecting to 1.2.3.4:51820") is None


# ------------------------------------------------------------ preuve de sortie


def test_une_adresse_vide_vaut_echec(monkeypatch):
    """Avec une cle bien formee mais fausse, WireGuard « s'etablit » sans
    qu'aucun paquet ne passe, et Gluetun rend une adresse vide. Un premier jet
    concluait « tunnel etabli »."""
    monkeypatch.setattr(vpnessai, "exec_in", lambda c, cmd, **kw: (True, '{"public_ip":""}'))

    assert vpnessai._sortie_observee() is None


def test_une_reponse_illisible_vaut_echec(monkeypatch):
    monkeypatch.setattr(vpnessai, "exec_in", lambda c, cmd, **kw: (True, "pas du json"))

    assert vpnessai._sortie_observee() is None


def test_une_sortie_reelle_rend_le_pays(monkeypatch):
    monkeypatch.setattr(
        vpnessai,
        "exec_in",
        lambda c, cmd, **kw: (True, '{"public_ip":"1.2.3.4","country":"Italy"}'),
    )

    assert vpnessai._sortie_observee() == "Italy"


def test_l_adresse_ip_n_est_jamais_rendue(monkeypatch):
    """Ce texte finit dans un journal qu'on demande de joindre aux rapports de
    bug."""
    monkeypatch.setattr(
        vpnessai,
        "exec_in",
        lambda c, cmd, **kw: (True, '{"public_ip":"62.112.9.192","country":"Italy"}'),
    )

    assert "62.112.9.192" not in (vpnessai._sortie_observee() or "")


# ------------------------------------------------------------------- l'essai


def test_rien_a_essayer_sans_vpn():
    controle = vpnessai.essayer(VpnConfig(), IMAGE)

    assert controle.ok
    assert controle.blocking is False


def test_rien_a_essayer_si_un_champ_manque():
    controle = vpnessai.essayer(_vpn(wireguard_private_key=""), IMAGE)

    assert controle.ok


def test_le_conteneur_est_supprime_meme_en_cas_d_echec(monkeypatch):
    """Un essai qui laisserait derriere lui un conteneur nomme finirait par
    faire echouer le suivant."""
    appels = []

    def faux_run(args, cwd=None, timeout=600):
        appels.append(args)
        if args[:2] == ["docker", "run"]:
            return _proc(stderr="boum", code=1)
        return _proc()

    monkeypatch.setattr(vpnessai, "_run", faux_run)
    controle = vpnessai.essayer(_vpn(), IMAGE)

    assert not controle.ok
    suppressions = [a for a in appels if a[:3] == ["docker", "rm", "-f"]]
    assert len(suppressions) >= 2, "avant ET apres"


def test_la_cle_saisie_remplace_la_reference_au_env(monkeypatch):
    """`environment()` rend `${VPN_WIREGUARD_KEY}` parce qu'elle sert d'abord au
    compose. A l'essai, aucun .env n'existe encore."""
    lancements = []

    def faux_run(args, cwd=None, timeout=600):
        if args[:2] == ["docker", "run"]:
            lancements.append(args)
            return _proc(stderr="refuse", code=1)
        return _proc()

    monkeypatch.setattr(vpnessai, "_run", faux_run)
    vpnessai.essayer(_vpn(wireguard_private_key="ma-vraie-cle"), IMAGE)

    passe = " ".join(lancements[0])
    assert "WIREGUARD_PRIVATE_KEY=ma-vraie-cle" in passe
    assert "${VPN_WIREGUARD_KEY}" not in passe


def test_un_essai_n_est_jamais_bloquant(monkeypatch):
    """Un serveur du fournisseur en carafe ne doit pas empecher d'installer avec
    une configuration valide."""
    monkeypatch.setattr(vpnessai, "_run", lambda *a, **kw: _proc(stderr="boum", code=1))

    assert vpnessai.essayer(_vpn(), IMAGE).blocking is False


@pytest.mark.parametrize("etat", ["starting", "unhealthy", ""])
def test_sans_sortie_observee_l_essai_echoue(monkeypatch, etat):
    monkeypatch.setattr(vpnessai, "_run", lambda *a, **kw: _proc(stdout=etat))
    monkeypatch.setattr(vpnessai, "_sortie_observee", lambda: None)
    monkeypatch.setattr(vpnessai, "_journal", lambda: "")

    controle = vpnessai.essayer(_vpn(), IMAGE, attente=0)

    assert not controle.ok
    assert "peut-etre" in controle.detail, "on ne conclut pas a la place du fournisseur"


# --------------------------------------------------- le rythme de chaque mode


def test_openvpn_recoit_plus_de_temps_que_wireguard():
    """Ce n'est pas une marge de confort : OpenVPN patiente SOIXANTE secondes
    sur un serveur muet avant d'en changer, la ou WireGuard le constate en
    quelques secondes. Mesure le 2026-09-09 contre v3.41.3, premier verdict a
    93 s — au-dela des 45 s alors accordees."""
    lent = vpnessai.attente_pour(_vpn(vpn_type="openvpn", openvpn_user="u", openvpn_password="p"))
    rapide = vpnessai.attente_pour(_vpn())

    assert lent > 60, "un seul serveur muet consomme deja 60 secondes"
    assert lent > rapide


def test_le_doute_est_dit_dans_les_termes_du_protocole(monkeypatch):
    """Parler d'une « cle » a quelqu'un qui vient de taper un identifiant et un
    mot de passe l'envoie verifier une chose qu'il n'a jamais saisie."""
    monkeypatch.setattr(vpnessai, "_run", lambda *a, **kw: _proc(stdout=""))
    monkeypatch.setattr(vpnessai, "_sortie_observee", lambda: None)
    monkeypatch.setattr(vpnessai, "_journal", lambda: "")
    ovpn = _vpn(vpn_type="openvpn", openvpn_user="u", openvpn_password="p")

    detail = vpnessai.essayer(ovpn, IMAGE, attente=0).detail

    assert "identifiants" in detail
    assert "cle" not in detail
