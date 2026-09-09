"""La configuration VPN saisie fonctionne-t-elle, avant de batir la stack ?

L'assistant ne verifiait que la PRESENCE des champs : une cle WireGuard fausse
passait l'ecran sans un mot. L'installation se deroulait ensuite normalement,
Gluetun restait `unhealthy`, le client de telechargement ne quittait jamais
l'etat `created`, et l'utilisateur se retrouvait devant un service injoignable
sans lien evident avec ce qu'il avait tape trois ecrans plus tot.

On monte donc un Gluetun JETABLE avec exactement la configuration saisie, on
attend qu'il se declare en bonne sante, et on lui demande par ou il sort. Le
conteneur est supprime dans tous les cas.

**Un avertissement, jamais un blocage.** Un essai peut echouer pour des raisons
qui ne sont pas la faute de la cle : un serveur du fournisseur en carafe, une
resolution DNS lente, une connexion capricieuse. Bloquer le bouton « suivant »
la-dessus empecherait d'installer avec une configuration parfaitement valide.
Le message dit donc ce qui a ete observe, pas ce qui est suppose.

Deux echecs sont pourtant certains, et ils meritent d'etre nommes :

- `no server found` : le fournisseur, le lieu et le port entrant demandes ne se
  recoupent sur aucun serveur. Gluetun ne demarrera jamais, ici ou plus tard.
- une cle refusee des la lecture de la configuration, avant toute connexion.
"""

from __future__ import annotations

import json
import time

from .i18n import t
from .models import VpnConfig
from .runner import Check, _run, exec_in

#: Nom du conteneur d'essai. Prefixe distinctif : il ne doit ressembler a aucune
#: stack, pour qu'un nettoyage rate ne laisse pas un conteneur qu'on prendrait
#: pour un service.
CONTENEUR = "plugarr-essai-vpn"

#: Duree d'attente en WireGuard. Un tunnel sain se declare en bonne sante en une
#: quinzaine de secondes, relais compris quand le premier serveur ne repond pas
#: — mesure sur ProtonVPN WireGuard. Au-dela, on n'apprend plus rien de plus.
ATTENTE = 45

#: Duree d'attente en OpenVPN, et elle ne peut PAS etre la meme.
#:
#: La difference n'est pas une marge de confort, c'est un delai fixe du
#: protocole. WireGuard echange des paquets UDP : un serveur muet se constate en
#: quelques secondes. OpenVPN negocie du TLS, et sa patience est de SOIXANTE
#: secondes avant de renoncer a un serveur — non configurable ici, c'est
#: OpenVPN 2.6 qui le decide :
#:
#:   WARN [openvpn] TLS Error: TLS key negotiation failed to occur within
#:   60 seconds (check your network connectivity)
#:
#: Or tomber sur un serveur muet n'a rien d'exceptionnel : la liste de serveurs
#: embarquee dans l'image v3.41.3 datait deja du 2025-11-18 quand l'image a ete
#: batie, et un des neuf serveurs suisses a port entrant ne repondait plus.
#:
#: Mesure le 2026-09-09, avec un mot de passe volontairement faux : premier
#: serveur muet a 0 s, renoncement TLS a 60 s, nouvel essai a 75 s, verdict
#: `AUTH_FAILED` a 93 s. A 45 secondes, l'essai expirait AVANT que Gluetun ait
#: dit quoi que ce soit, et rendait « peut-etre » sur une reponse certaine.
ATTENTE_OPENVPN = 120

#: Marqueurs d'un echec CERTAIN. Les reconnaitre evite de faire patienter
#: quarante-cinq secondes pour une configuration qui ne peut pas fonctionner.
#:
#: Chacun a ete PROVOQUE contre l'image v3.41.3 et recopie de son journal. Un
#: premier jet contenait `wireguard settings`, qui semblait raisonnable et
#: declarait fausse une cle parfaitement valide : Gluetun affiche « Wireguard
#: settings: » comme TITRE de section au demarrage normal. La ligne qui distingue
#: vraiment est celle-ci :
#:
#:   ERROR VPN settings: Wireguard settings: private key is not valid:
#:   wgtypes: failed to parse base64-encoded key
#:
#: Rien n'entre ici sans avoir ete observe. Un marqueur trop large transforme cet
#: essai en generateur de fausses alertes, ce qui est pire que pas d'essai.
#:
#: Le marqueur ne porte qu'une CLE : la phrase rendue a l'utilisateur est
#: construite par `_message_definitif`, ou elle passe par `t()` comme tout le
#: reste. Un premier jet gardait la phrase francaise dans ce tableau, et elle
#: serait apparue telle quelle au milieu d'un message anglais.
DEFINITIFS = (
    # ERROR [vpn] finding a VPN server: filtering servers: no server found:
    # for VPN wireguard; protocol udp; country macedonia; port forwarding only
    ("no server found", "serveur"),
    # ERROR VPN settings: Wireguard settings: private key is not valid:
    # wgtypes: failed to parse base64-encoded key
    ("private key is not valid", "cle"),
    # ERROR [openvpn] AUTH: Received control message: AUTH_FAILED
    #
    # L'equivalent OpenVPN de la cle refusee, et il manquait. Le serveur a lu
    # les identifiants et les a rejetes : aucune attente supplementaire ne les
    # rendra bons. Sans ce marqueur, l'essai patientait jusqu'a l'expiration
    # puis rendait « la cle est peut-etre fausse » — un peut-etre sur une
    # certitude, et en parlant d'une cle qui n'existe pas dans ce mode.
    #
    # Le marqueur porte le souligne (`auth_failed`) et non le mot seul : le
    # journal contient « AUTH: Received control message » et « authentication »
    # dans des lignes parfaitement normales.
    ("auth_failed", "identifiants"),
)


def _message_definitif(cause: str, fournisseur: str) -> str:
    if cause == "serveur":
        return t(
            "{fournisseur} refuse cette configuration : aucun serveur ne "
            "correspond au lieu et au port entrant demandes",
            fournisseur=fournisseur,
        )
    if cause == "identifiants":
        return t(
            "{fournisseur} refuse ces identifiants OpenVPN : l'identifiant ou "
            "le mot de passe n'est pas le bon",
            fournisseur=fournisseur,
        )
    return t(
        "{fournisseur} refuse cette configuration : la cle privee WireGuard "
        "n'est pas valide",
        fournisseur=fournisseur,
    )


def _supprimer() -> None:
    _run(["docker", "rm", "-f", CONTENEUR], timeout=30)


def _journal() -> str:
    """Le journal du conteneur d'essai, les deux flux reunis.

    Gluetun ecrit l'essentiel sur la sortie d'erreur : ne lire que `stdout`
    laissait passer justement les lignes qui expliquent l'echec.
    """
    proc = _run(["docker", "logs", CONTENEUR], timeout=30)
    return ((proc.stdout or "") + (proc.stderr or "")).lower()


def _definitif(journal: str) -> str | None:
    for marqueur, explication in DEFINITIFS:
        if marqueur in journal:
            return explication
    return None


def attente_pour(vpn: VpnConfig) -> int:
    """Combien de temps laisser a CE protocole. Voir `ATTENTE_OPENVPN`."""
    return ATTENTE_OPENVPN if vpn.vpn_type == "openvpn" else ATTENTE


def essayer(vpn: VpnConfig, image: str, *, attente: int | None = None) -> Check:
    """Monte un Gluetun jetable avec cette configuration. Jamais bloquant.

    `image` est passee plutot que lue ici : c'est `compose` qui epingle la
    version deployee, et l'essai doit porter sur CELLE-LA. En tester une autre
    ne prouverait rien de l'installation a venir.

    `attente` non precisee suit le protocole : OpenVPN est structurellement plus
    lent a rendre son verdict, et lui imposer le rythme de WireGuard revenait a
    rendre « peut-etre » sur des reponses certaines.
    """
    if attente is None:
        attente = attente_pour(vpn)
    if not vpn.enabled or vpn.missing():
        return Check("Essai VPN", True, t("rien a essayer"), blocking=False)

    _supprimer()
    environnement = []
    for cle, valeur in vpn.environment("Etc/UTC").items():
        # `environment()` rend des references au .env (`${VPN_WIREGUARD_KEY}`)
        # parce qu'elle sert d'abord au compose. Ici, aucun .env n'existe encore :
        # on pose les valeurs reellement saisies.
        environnement += ["-e", f"{cle}={_valeur_reelle(vpn, cle, valeur)}"]

    demarre = _run(
        [
            "docker", "run", "-d", "--name", CONTENEUR,
            "--cap-add=NET_ADMIN", "--device", "/dev/net/tun",
            *environnement,
            image,
        ],
        timeout=120,
    )
    if demarre.returncode != 0:
        _supprimer()
        return Check(
            "Essai VPN",
            False,
            t("Gluetun n'a pas demarre : {cause}", cause=demarre.stderr.strip()[:120]),
            blocking=False,
        )

    try:
        return _attendre(vpn, attente)
    finally:
        _supprimer()


def _valeur_reelle(vpn: VpnConfig, cle: str, valeur: str) -> str:
    """Remplace les references au .env par ce que l'utilisateur a saisi."""
    return {
        "${VPN_WIREGUARD_KEY}": vpn.wireguard_private_key,
        "${VPN_OPENVPN_USER}": vpn.openvpn_user,
        "${VPN_OPENVPN_PASS}": vpn.openvpn_password,
    }.get(valeur, valeur)


def _attendre(vpn: VpnConfig, attente: int) -> Check:
    """Boucle jusqu'a la bonne sante, un echec certain, ou l'expiration."""
    fin = time.monotonic() + attente
    while time.monotonic() < fin:
        # La sortie reelle d'abord : c'est elle qui tranche. La sante du
        # conteneur ne sert qu'a arreter d'attendre plus tot.
        if pays := _sortie_observee():
            return Check(
                "Essai VPN",
                True,
                t(
                    "tunnel etabli avec {fournisseur}, sortie par {pays}",
                    fournisseur=vpn.provider,
                    pays=pays,
                ),
                blocking=False,
            )
        if cause := _definitif(_journal()):
            return Check(
                "Essai VPN", False, _message_definitif(cause, vpn.provider), blocking=False
            )
        time.sleep(2)

    # Le doute est nomme dans les termes du protocole employe : parler d'une
    # « cle » a quelqu'un qui vient de taper un identifiant et un mot de passe
    # l'envoie verifier une chose qu'il n'a jamais saisie.
    if vpn.vpn_type == "openvpn":
        doute = t(
            "aucun tunnel etabli en {attente} secondes. Les identifiants sont "
            "peut-etre faux, mais le fournisseur peut aussi etre indisponible.",
            attente=attente,
        )
    else:
        doute = t(
            "aucun tunnel etabli en {attente} secondes. La cle est peut-etre "
            "fausse, mais le fournisseur peut aussi etre indisponible.",
            attente=attente,
        )
    return Check("Essai VPN", False, doute, blocking=False)


def _sortie_observee() -> str | None:
    """Le pays par lequel le tunnel sort, ou None s'il ne sort pas.

    C'est la SEULE preuve acceptee. Un premier jet se contentait de la sante du
    conteneur et declarait bonne une cle fausse : avec une cle bien formee mais
    invalide, WireGuard « s'etablit » sans qu'aucun paquet ne passe — le
    protocole est silencieux, Gluetun le dit lui-meme au demarrage — et le
    serveur de controle rend alors :

        {"public_ip":""}

    Une adresse vide vaut donc echec. Meme regle que `vpncheck`, qui refuse
    d'affirmer une protection qu'il n'a pas constatee.

    L'adresse elle-meme n'est jamais rendue, seulement le pays : ce texte finit
    dans un journal qu'on demande de joindre aux rapports de bug.
    """
    ok, sortie = exec_in(
        CONTENEUR, ["wget", "-qO-", "--timeout=8", "http://127.0.0.1:8000/v1/publicip/ip"]
    )
    if not ok or not sortie:
        return None
    try:
        donnees = json.loads(sortie)
    except ValueError:
        return None
    if not donnees.get("public_ip"):
        return None
    return str(donnees.get("country") or "?")
