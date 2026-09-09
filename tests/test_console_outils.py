"""Diagnostic et recherche de mises a jour, depuis la console.

Deux demandes a l'usage : « un bouton pour lancer plugarr doctor », et « un
bouton de recherche de mise a jour ».

Le second existait a moitie. La console interrogeait deja les registres au
chargement puis toutes les quinze minutes, mais en silence : impossible de la
declencher, impossible de savoir quand elle avait eu lieu. Le bouton n'ajoute
pas la verification, il la rend demandable et datee.

Le premier n'existait pas du tout : `plugarr doctor` etait reserve a la ligne
de commande, ce qui allait contre la regle du projet — tout ce que plugarr sait
faire doit etre atteignable sans ouvrir un terminal.
"""

from __future__ import annotations

from pathlib import Path

from plugarr import admin, dashboard, orchestrator
from plugarr.models import VpnConfig


def _cfg():
    return orchestrator.build_config(services=["sonarr"], config_root="/c", data_root="/d")


def test_la_console_porte_les_deux_boutons():
    page = dashboard.render(_cfg(), live=True)

    assert 'id="btn-doctor"' in page
    assert 'id="btn-maj"' in page


def test_la_page_d_acces_statique_n_en_porte_aucun():
    """Elle est un fichier HTML pose sur le disque : aucun serveur derriere,
    donc aucun bouton branche a quoi que ce soit. En afficher serait mentir."""
    page = dashboard.render(_cfg())

    assert "btn-doctor" not in page
    assert "btn-maj" not in page
    assert "/api/doctor" not in page


def test_le_diagnostic_rend_les_memes_controles_que_preflight(monkeypatch):
    """Deux diagnostics du meme systeme finiraient par diverger : la console
    rejoue `preflight`, elle n'en ecrit pas un second."""
    temoin = [admin.orchestrator.Check("bidon", True, "detail", blocking=False)]
    monkeypatch.setattr(admin.orchestrator, "preflight", lambda cfg, d: temoin)
    monkeypatch.setattr(admin.orchestrator, "iter_selected", lambda cfg: [])

    charge = admin.doctor_payload(_cfg(), Path("."))

    assert charge["checks"] == [
        {"name": "bidon", "ok": True, "detail": "detail", "blocking": False, "partage": False}
    ]
    assert charge["failed"] == 0


def test_le_diagnostic_compte_les_echecs(monkeypatch):
    controles = [
        admin.orchestrator.Check("un", True, "", blocking=False),
        admin.orchestrator.Check("deux", False, "casse", blocking=False),
    ]
    monkeypatch.setattr(admin.orchestrator, "preflight", lambda cfg, d: controles)
    monkeypatch.setattr(admin.orchestrator, "iter_selected", lambda cfg: [])

    assert admin.doctor_payload(_cfg(), Path("."))["failed"] == 1


def test_une_api_muette_est_un_echec_lisible(monkeypatch):
    """Un conteneur qui tourne n'est pas un service qui repond. C'est toute la
    valeur ajoutee du diagnostic par rapport a la liste des conteneurs."""
    monkeypatch.setattr(admin.orchestrator, "preflight", lambda cfg, d: [])

    cfg = _cfg()
    monkeypatch.setattr(
        admin.orchestrator, "iter_selected", lambda c: [("sonarr", cfg.services["sonarr"])]
    )

    def _explose(*a, **k):
        raise RuntimeError("connexion refusee")

    monkeypatch.setattr(admin, "ArrClient", _explose)

    charge = admin.doctor_payload(cfg, Path("."))

    assert charge["failed"] == 1
    assert "connexion refusee" in charge["checks"][0]["detail"]


def test_aucune_chaine_javascript_ne_court_sur_deux_lignes():
    """Le script de la console vit dans une chaine Python NON brute : un `\n`
    ecrit simplement y devient un VRAI retour a la ligne, qui casse la chaine
    JavaScript et emporte tout le script.

    Constate en vrai : `lignes.join('\n')` a donne une page entierement
    blanche, avec pour seule trace « Uncaught SyntaxError: Invalid or
    unexpected token » dans la console du navigateur. Aucun test Python ne
    pouvait le voir — le HTML etait bien forme et le rendu cote Python
    parfaitement reussi.

    On compte les apostrophes de chaque ligne : une chaine qui se ferme sur la
    ligne suivante en laisse un nombre IMPAIR derriere elle. Les commentaires
    sont retires d'abord, sans quoi le moindre « s'arrete » francais fausserait
    le compte — premiere version de ce test, qui ne detectait plus rien.
    """
    import re

    page = dashboard.render(_cfg(), live=True)
    # La page porte PLUSIEURS blocs <script>. N'examiner que le premier laissait
    # passer tout le script vivant, celui qui portait justement le defaut.
    blocs = re.findall(r"<script>(.*?)</script>", page, re.DOTALL)
    assert len(blocs) >= 2, "le script de la console vivante n'est pas dans la page"

    fautives = []
    for bloc in blocs:
        for numero, ligne in enumerate(bloc.splitlines(), start=1):
            nette = re.sub(r"//.*$", "", ligne)
            nette = nette.replace(chr(92) + "'", "").replace(chr(92) + chr(34), "")
            if nette.count("'") % 2 or nette.count(chr(34)) % 2:
                fautives.append(f"ligne {numero} : {ligne.strip()[:70]}")

    assert not fautives, "chaine JavaScript non fermee : " + " | ".join(fautives[:3])


def test_le_diagnostic_tait_les_controles_d_avant_installation(monkeypatch):
    """« Une configuration existe deja » est un avertissement pour qui va en
    generer une neuve. Sur une pile en marche c'est la situation normale, et
    l'afficher en ECHEC envoie chercher une panne inexistante. Vu en vrai sur
    la console d'une pile Silo parfaitement saine."""
    controles = [
        admin.orchestrator.Check("docker", True, "trouve", blocking=False),
        admin.orchestrator.Check("configuration existante", False, "deja la", blocking=False),
        admin.orchestrator.Check("nom de projet", False, "ailleurs", blocking=False),
    ]
    monkeypatch.setattr(admin.orchestrator, "preflight", lambda cfg, d: controles)
    monkeypatch.setattr(admin.orchestrator, "iter_selected", lambda cfg: [])

    charge = admin.doctor_payload(_cfg(), Path("."))

    assert [c["name"] for c in charge["checks"]] == ["docker"]
    assert charge["failed"] == 0


# ------------------------- protection et partage sont deux verdicts distincts


def _cfg_vpn():
    cfg = orchestrator.build_config(
        services=["qbittorrent"], config_root="/c", data_root="/d"
    )
    cfg.vpn = VpnConfig(
        enabled=True, provider="protonvpn", vpn_type="wireguard", wireguard_private_key="k" * 44
    )
    return cfg


def _sans_preflight(monkeypatch):
    monkeypatch.setattr(admin.orchestrator, "preflight", lambda cfg, d: [])
    monkeypatch.setattr(admin.orchestrator, "iter_selected", lambda cfg: [])


def test_un_port_desynchronise_n_est_pas_compte_comme_un_echec(monkeypatch):
    """L'installation separait deja ses deux verdicts ; la console melangeait
    tout dans un seul total. Un port desynchronise coute du PARTAGE, pas de
    l'exposition, et le lire a cote d'un tunnel tombe ferait craindre une fuite
    la ou il n'y en a aucune."""
    _sans_preflight(monkeypatch)
    monkeypatch.setattr(
        admin.vpncheck,
        "verifier",
        lambda cfg: [
            admin.orchestrator.Check("VPN qbittorrent", True, "sortie par Austria"),
            admin.orchestrator.Check(
                f"{admin.vpncheck.PREFIXE_PORT} qbittorrent",
                False,
                "desynchronise",
                blocking=False,
            ),
        ],
    )

    charge = admin.doctor_payload(_cfg_vpn(), Path("."))

    assert charge["failed"] == 0, "la protection n'est pas en cause"
    assert charge["partage"] == 1


def test_une_protection_perdue_reste_un_echec(monkeypatch):
    """La distinction ne doit pas adoucir le seul controle qui compte vraiment."""
    _sans_preflight(monkeypatch)
    monkeypatch.setattr(
        admin.vpncheck,
        "verifier",
        lambda cfg: [
            admin.orchestrator.Check("VPN qbittorrent", False, "NON PROTEGE", blocking=True)
        ],
    )

    charge = admin.doctor_payload(_cfg_vpn(), Path("."))

    assert charge["failed"] == 1
    assert charge["partage"] == 0


def test_les_deux_se_comptent_separement(monkeypatch):
    _sans_preflight(monkeypatch)
    monkeypatch.setattr(
        admin.vpncheck,
        "verifier",
        lambda cfg: [
            admin.orchestrator.Check("VPN qbittorrent", False, "NON PROTEGE", blocking=True),
            admin.orchestrator.Check(
                f"{admin.vpncheck.PREFIXE_PORT} qbittorrent", False, "desynchronise", blocking=False
            ),
        ],
    )

    charge = admin.doctor_payload(_cfg_vpn(), Path("."))

    assert (charge["failed"], charge["partage"]) == (1, 1)


def test_chaque_controle_dit_de_quelle_famille_il_est(monkeypatch):
    """Sans ce drapeau, la console ne pourrait pas distinguer les deux a
    l'affichage et retomberait sur un ECHEC uniforme."""
    _sans_preflight(monkeypatch)
    monkeypatch.setattr(
        admin.vpncheck,
        "verifier",
        lambda cfg: [
            admin.orchestrator.Check("VPN qbittorrent", True, "sortie par Austria"),
            admin.orchestrator.Check(
                f"{admin.vpncheck.PREFIXE_PORT} qbittorrent", True, "ecoute sur 47878"
            ),
        ],
    )

    familles = {c["name"]: c["partage"] for c in admin.doctor_payload(_cfg_vpn(), Path("."))["checks"]}

    assert familles["VPN qbittorrent"] is False
    assert familles[f"{admin.vpncheck.PREFIXE_PORT} qbittorrent"] is True


def test_la_console_affiche_les_trois_marques():
    """Le rapport doit pouvoir ecrire PORT et non ECHEC. Le test porte sur le
    script rendu : aucun test Python ne voit ce que fait le navigateur."""
    page = dashboard.render(_cfg(), live=True)

    assert "c.partage ? '  PORT  ' : '  ECHEC '" in page
    assert "port(s) entrant(s) a revoir" in page
    assert "protection en ordre" in page
