"""Le trafic torrent sort-il VRAIMENT par le VPN ?

Signale a l'usage, dans ces termes : « c'est le coup a lancer un torrent et ne
pas etre protege par le VPN ». La crainte est fondee, et plugarr ne verifiait
rien du tout : il ecrivait `network_mode: service:gluetun` dans le compose et
considerait l'affaire close.

Or ce reglage se perd. Constate en vrai le 2026-09-03 : une installation lancee
par-dessus une pile existante, depuis une configuration ou le VPN n'etait pas
active, a recree les clients torrent sur le reseau nu. Docker identifie une pile
par son nom : les conteneurs ont ete remplaces sans un mot, et rien dans
plugarr n'aurait signale que la protection avait disparu.

Deux controles, du moins cher au plus concluant.

**1. Structure.** `docker inspect` doit rendre `container:<id de gluetun>` pour
chaque client torrent. Hors ligne, instantane, et c'est celui qui aurait attrape
l'incident ci-dessus.

**2. Sortie reelle.** Depuis l'INTERIEUR du client, on interroge le serveur de
controle de Gluetun sur `127.0.0.1:8000`. Ce test est concluant parce qu'il ne
peut pas reussir par accident : seul un conteneur qui partage la pile reseau de
Gluetun voit ce `127.0.0.1`. Verifie dans les deux sens contre une pile reelle :

    depuis qbittorrent -> {"public_ip": ..., "country": "Netherlands", ...}
    depuis sonarr      -> can't connect to remote host (127.0.0.1): refused

L'adresse vient de Gluetun lui-meme, sans service exterieur.

**3. Le tunnel ressort-il ailleurs que chez vous ?** Un tunnel qui reboucle sur
la connexion du domicile ne protege de rien, et les deux controles precedents le
declarent pourtant bon : le conteneur EST dans le tunnel. Le cas est apparu sur
le banc d'essai — un serveur WireGuard local qui traduisait les adresses vers la
sortie de la maison — et un fournisseur mal configure produirait la meme chose.
On compare donc l'adresse du tunnel a celle de la machine.

C'est le SEUL appel exterieur de ce module, et il est facultatif : s'il echoue,
le controle rend quand meme son verdict, d'un cran moins ferme.

L'adresse IP n'est jamais journalisee, ni celle du tunnel ni celle de la
machine. On ne garde que le pays et l'operateur, qui suffisent a reconnaitre un
tunnel d'un fournisseur d'acces — et le journal est le fichier qu'on demande aux
utilisateurs de joindre a un rapport de bug.
"""

from __future__ import annotations

import json

import httpx

from . import catalog
from .i18n import t
from .models import Category, StackConfig
from .runner import Check, container_id, exec_in, network_mode

#: Serveur de controle de Gluetun, dans sa propre pile reseau. Le port n'est
#: jamais publie sur l'hote : il n'est visible que de l'interieur du tunnel,
#: et c'est precisement ce qui rend le test concluant.
CONTROLE = "http://127.0.0.1:8000/v1/publicip/ip"


def clients_torrent(cfg: StackConfig) -> list[str]:
    return [
        sid
        for sid in catalog.STARTUP_ORDER
        if cfg.enabled(sid) and catalog.get(sid).category is Category.DOWNLOAD
    ]


def nom_conteneur(cfg: StackConfig, sid: str) -> str:
    """Le nom REEL du conteneur de ce service.

    Un service ADOPTE garde le sien : plugarr ne l'a ni cree ni renomme. Chercher
    `{projet}-{service}` pour lui ne trouvait rien, `network_mode` rendait `None`,
    et `None` veut dire « conteneur arrete » — donc un controle **vert** sur un
    client qui tourne, hors du tunnel, et telecharge sur l'adresse de la maison.
    Le faux OK exact que ce module existe pour empecher.

    Aucun chemin ne produit aujourd'hui cette combinaison : `adopt` n'ecrit
    jamais de VPN, et `reprise` ne reporte ni `adopted` ni `container`. Mais
    `stack.yml` se lit et s'edite, et un verdict de protection ne doit pas
    dependre de ce qu'aucun chemin ne l'atteigne.
    """
    inst = cfg.services.get(sid)
    if inst is not None and inst.adopted and inst.container:
        return inst.container
    return f"{cfg.project_name}-{sid}"


def piles_orphelines(cfg: StackConfig) -> list[str]:
    """Clients torrent rattaches a une pile reseau qui n'est plus celle de Gluetun.

    Recreer Gluetun SEUL laisse les clients accroches au conteneur DETRUIT :

        docker compose up -d --no-deps gluetun

    Reproduit le 2026-09-07 sur la stack d'essai, et le resultat est trompeur au
    possible :

        docker ps           -> plugarr-qbittorrent   Up 5 hours
        ip -o addr show     -> 1: lo    inet 127.0.0.1/8
        ip route            -> (rien)

    Aucune fuite, le garde-fou tient : sans interface ni route, rien ne sort. Mais
    le client est mort en silence, affiche « Up », et son interface web ne repond
    plus sans qu'un seul message ne l'explique.

    Ce que ce controle n'est PAS : un rattrapage d'`install`. Verifie le
    2026-09-08, un `docker compose up -d` complet propage bien la recreation —
    Gluetun recree, qBittorrent redemarre onze secondes plus tard dans la
    nouvelle pile. Seule la recreation d'un service SEUL laisse des orphelins, et
    plugarr ne recree jamais Gluetun de cette facon.

    Il garde donc la porte d'a cote, qui reste grande ouverte : un utilisateur
    qui lance lui-meme une commande docker, ou l'incident du 2026-09-03 ou des
    clients avaient ete recrees sur le reseau nu. Toute pile differente de celle
    de Gluetun est signalee, qu'elle soit morte ou qu'elle soit une vraie fuite.

    Les services ADOPTES sont exclus : ils n'ont pas de bloc compose, et les
    recreer echouerait — ils ne nous appartiennent pas.
    """
    if not cfg.vpn.enabled:
        return []
    gluetun = container_id(f"{cfg.project_name}-gluetun")
    if not gluetun:
        return []
    attendu = f"container:{gluetun}"
    orphelins = []
    for sid in clients_torrent(cfg):
        if cfg.services[sid].adopted:
            continue
        mode = network_mode(f"{cfg.project_name}-{sid}")
        # None = conteneur absent ou arrete : ce n'est pas une pile orpheline,
        # et le demarrage s'en chargera.
        if mode is not None and mode != attendu:
            orphelins.append(sid)
    return orphelins


#: Relit, DEPUIS Gluetun, le port entrant annonce et celui que chaque client
#: ecoute vraiment. Depuis Gluetun parce qu'il est le seul a voir le serveur de
#: controle en `127.0.0.1`, et parce qu'il porte deja les identifiants des
#: clients : le controle n'a aucun secret a transporter.
#:
#: `sed` plutot qu'un analyseur JSON : l'image de Gluetun n'embarque ni python ni
#: jq, et les trois valeurs cherchees sont des entiers.
_LECTURE_PORTS = r"""
A=$(wget -qO- http://127.0.0.1:8000/v1/portforward 2>/dev/null \
    | sed -n 's/.*"port":\([0-9]*\).*/\1/p')
echo "annonce=${A:-0}"
if [ -n "$QBT_USER" ]; then
  CK=/tmp/plugarr-controle.cookies
  if wget -q --save-cookies "$CK" --keep-session-cookies \
       --post-data "username=$QBT_USER&password=$QBT_PASS" \
       -O /dev/null "http://127.0.0.1:%(qbittorrent)s/api/v2/auth/login" 2>/dev/null; then
    Q=$(wget -q --load-cookies "$CK" -O - \
        "http://127.0.0.1:%(qbittorrent)s/api/v2/app/preferences" 2>/dev/null \
        | sed -n 's/.*"listen_port":\([0-9]*\).*/\1/p')
    echo "qbittorrent=${Q:-0}"
  fi
fi
if [ -n "$TR_USER" ]; then
  RPC="http://127.0.0.1:%(transmission)s/transmission/rpc"
  S=$(wget -S -q -O /dev/null --user="$TR_USER" --password="$TR_PASS" "$RPC" 2>&1 \
      | sed -n 's/.*X-Transmission-Session-Id: *//p' | tr -d '\r')
  if [ -n "$S" ]; then
    T=$(wget -q -O - --user="$TR_USER" --password="$TR_PASS" \
        --header="X-Transmission-Session-Id: $S" \
        --post-data '{"method":"session-get","fields":["peer-port"]}' "$RPC" 2>/dev/null \
        | sed -n 's/.*"peer-port":\([0-9]*\).*/\1/p')
    echo "transmission=${T:-0}"
  fi
fi
"""


def ports_entrants(cfg: StackConfig) -> dict[str, int]:
    """Port annonce par Gluetun et port reellement ecoute par chaque client.

    Vide si rien n'est a synchroniser. `annonce` vaut 0 quand aucun port n'a ete
    obtenu : c'est le sentinel de Gluetun lui-meme, verifie contre la v3.41.3, et
    il distingue « pas de port » de « port different ».
    """
    from .compose import port_sync_clients

    clients = port_sync_clients(cfg)
    if not clients:
        return {}
    script = _LECTURE_PORTS % {
        sid: catalog.get(sid).internal_port for sid in ("qbittorrent", "transmission")
    }
    ok, sortie = exec_in(f"{cfg.project_name}-gluetun", ["sh", "-c", script])
    if not ok:
        return {}
    releve = {}
    for ligne in sortie.splitlines():
        cle, _, valeur = ligne.partition("=")
        if valeur.strip().isdigit():
            releve[cle.strip()] = int(valeur)
    return releve


#: Prefixe des controles de port entrant. Il les rend reconnaissables dans la
#: liste plate que rend `verifier`, pour que le rapport d'installation ne range
#: PAS un port desynchronise sous « protection VPN » : ce serait alarmer sur
#: l'exposition alors qu'il ne s'agit que de partage.
PREFIXE_PORT = "Port entrant"


def _piste_pmp(cfg: StackConfig) -> str:
    """La piste `+pmp`, et SEULEMENT quand le port a reellement manque.

    Chez ProtonVPN, le suffixe de l'identifiant OpenVPN active des options de
    session. Le fichier `.ovpn` telecharge chez eux documente `+f1`, `+f2` et
    `+nr` en commentaire, jamais le quatrieme. Gluetun, lui, le nomme, mais dans
    son propre journal et seulement apres un refus — v3.41.3,
    `internal/provider/protonvpn/portforward.go` :

        %w - make sure you have +pmp at the end of your OpenVPN username

    **On ne l'ajoute PAS d'office.** Essai du 2026-09-09 sur un compte reel, en
    OpenVPN vers la Suisse : le port entrant est arrive dans les DEUX cas, avec
    et sans le suffixe. Modifier l'identifiant que quelqu'un a tape pour corriger
    un probleme qu'il n'a pas serait un pari, pas une correction — et un compte
    ou Proton refuserait ce suffixe se retrouverait sans tunnel du tout.

    On le mentionne donc la ou il repond a quelque chose : le port a manque,
    voici la seule piste connue, a l'utilisateur de juger.
    """
    if cfg.vpn.provider != "protonvpn" or cfg.vpn.vpn_type != "openvpn":
        return ""
    if "+pmp" in cfg.vpn.openvpn_user:
        return ""
    return " " + t(
        "Chez ProtonVPN en OpenVPN, le port entrant depend du suffixe de "
        "l'identifiant : essayez d'ajouter +pmp a la fin du votre."
    )


def _controle_port(cfg: StackConfig) -> list[Check]:
    """Le port entrant est-il REELLEMENT arrive jusqu'au client ?

    Meme exigence que le cablage : on ne dit pas « j'ai pose le port », on relit
    la valeur chez le client et on la compare.

    Le cas vise a ete observe le 2026-09-08 sur la stack d'essai : Proton avait
    change de port entre deux journees, Gluetun annoncait 48406, qBittorrent
    ecoutait toujours 45270. Plus aucune connexion entrante, et rien nulle part
    ne le disait.

    Deliberement NON bloquant : sans port entrant on telecharge tres bien, on
    partage seulement moins. Faire echouer une installation pour un ratio serait
    disproportionne.
    """
    releve = ports_entrants(cfg)
    if not releve:
        return []
    annonce = releve.get("annonce", 0)
    if not annonce:
        return [
            Check(
                PREFIXE_PORT,
                False,
                t(
                    "aucun port obtenu aupres de {fournisseur} : le client ne "
                    "recevra pas de connexions entrantes",
                    fournisseur=cfg.vpn.provider,
                )
                + _piste_pmp(cfg),
                blocking=False,
            )
        ]
    controles = []
    for sid, port in sorted(releve.items()):
        if sid == "annonce":
            continue
        if port == annonce:
            controles.append(
                Check(f"{PREFIXE_PORT} {sid}", True, t("ecoute sur {port}", port=annonce))
            )
        else:
            controles.append(
                Check(
                    f"{PREFIXE_PORT} {sid}",
                    False,
                    t(
                        "desynchronise : le VPN a ouvert {annonce}, le client "
                        "ecoute {port}. Aucune connexion entrante n'arrive.",
                        annonce=annonce,
                        port=port,
                    ),
                    blocking=False,
                )
            )
    return controles


def reparer_port(cfg: StackConfig) -> Check | None:
    """Repose le port annonce chez les clients qui ne l'ecoutent pas.

    `_controle_port` savait DETECTER la desynchronisation, personne ne la
    corrigeait : le diagnostic disait « le VPN a ouvert 48406, le client ecoute
    45270 », et l'utilisateur restait avec le probleme et sans le remede.

    Le cas existe parce que la pose est un EVENEMENT : Gluetun appelle
    `VPN_PORT_FORWARDING_UP_COMMAND` au moment ou il obtient un port — verifie le
    2026-09-10 contre la v3.41.3, appel une seconde apres l'attribution. Si le
    client est recree ENTRE deux attributions, aucun evenement ne survient et il
    garde son port par defaut jusqu'au renouvellement du bail. C'est le seul
    avantage reel qu'a une sonde periodique sur un evenement, et il se rattrape
    ici.

    **On rejoue le script que Gluetun lance lui-meme**, plutot que d'ecrire une
    seconde pose : deux implementations de la meme chose finiraient par ne plus
    faire la meme chose, et c'est la pose de Gluetun qui fait foi.

    Et on RELIT avant de conclure. Meme exigence que partout ailleurs : on ne dit
    pas « j'ai repose le port », on redemande au client ce qu'il ecoute.

    Renvoie None quand il n'y avait rien a reparer — annoncer « rien a faire »
    a chaque diagnostic noierait le cas ou il y a vraiment eu quelque chose.
    """
    from .compose import PORT_SYNC

    releve = ports_entrants(cfg)
    annonce = releve.get("annonce", 0)
    if not annonce:
        return None
    decales = [sid for sid, port in releve.items() if sid != "annonce" and port != annonce]
    if not decales:
        return None

    # Genereux : le script attend que l'interface du client reponde, trente
    # essais espaces de deux secondes, et il le fait pour chaque client.
    exec_in(
        f"{cfg.project_name}-gluetun",
        ["sh", f"/gluetun/{PORT_SYNC}", str(annonce)],
        timeout=180,
    )

    apres = ports_entrants(cfg)
    restants = [sid for sid in decales if apres.get(sid) != annonce]
    if restants:
        return Check(
            f"{PREFIXE_PORT} (remise en place)",
            False,
            t(
                "{clients} n'ecoute toujours pas {port}",
                clients=", ".join(sorted(restants)),
                port=annonce,
            ),
            blocking=False,
        )
    return Check(
        f"{PREFIXE_PORT} (remise en place)",
        True,
        t(
            "{clients} ecoute maintenant {port}",
            clients=", ".join(sorted(decales)),
            port=annonce,
        ),
    )


def ip_de_l_hote() -> str | None:
    """Adresse publique de la MACHINE, hors tunnel. None si indeterminable.

    Le seul appel exterieur de tout ce module, et il est facultatif : sans lui
    le controle rend quand meme son verdict, un cran moins ferme.
    """
    try:
        reponse = httpx.get("https://ipinfo.io/json", timeout=6.0)
        return str(reponse.json().get("ip") or "") or None
    except Exception:  # noqa: BLE001 - un diagnostic ne tombe pas pour ca
        return None


def _sortie(conteneur: str) -> tuple[bool, str]:
    """Pays et operateur vus depuis l'interieur du conteneur.

    Renvoie (protege, description). L'IP elle-meme n'est JAMAIS renvoyee : le
    journal est le fichier qu'on demande de joindre aux rapports de bug.
    """
    ok, sortie = exec_in(conteneur, ["wget", "-qO-", "--timeout=8", CONTROLE])
    if not ok or not sortie:
        return False, t(
            "le serveur de controle de Gluetun est injoignable depuis ce conteneur"
        )
    try:
        donnees = json.loads(sortie)
    except ValueError:
        return False, t("reponse illisible de Gluetun : {reponse}", reponse=sortie[:80])
    tunnel = donnees.get("public_ip")
    if not tunnel:
        return False, t(
            "Gluetun ne rapporte aucune adresse publique : le tunnel est-il monte ?"
        )
    pays = donnees.get("country") or "?"
    operateur = (donnees.get("organization") or "?")[:40]

    # Un tunnel qui RESSORT chez vous ne protege de rien. Le cas s'est presente
    # pour de vrai sur un serveur WireGuard d'essai qui traduisait les adresses
    # vers la connexion de la maison : le conteneur etait bien dans le tunnel,
    # tout etait vert, et l'adresse vue de l'exterieur restait celle du domicile.
    # Un fournisseur commercial ne fait jamais cela ; une configuration
    # bricolee, si.
    hote = ip_de_l_hote()
    if hote and hote == tunnel:
        return False, t(
            "NON PROTEGE : le tunnel ressort sur VOTRE adresse publique "
            "({pays}, {operateur}). Verifiez la configuration du fournisseur.",
            pays=pays,
            operateur=operateur,
        )
    if hote is None:
        return True, t(
            "sortie par {pays}, {operateur} (adresse de l'hote indeterminable)",
            pays=pays,
            operateur=operateur,
        )
    return True, t(
        "sortie par {pays}, {operateur}, differente de la votre",
        pays=pays,
        operateur=operateur,
    )


def verifier(cfg: StackConfig) -> list[Check]:
    """Controles de fuite VPN. Vide si aucun client torrent n'est installe."""
    clients = clients_torrent(cfg)
    if not clients:
        return []

    if not cfg.vpn.enabled:
        # Ce n'est pas une panne : se passer de VPN est un choix. Mais il doit
        # etre visible, pas silencieux.
        return [
            Check(
                "VPN",
                True,
                t(
                    "aucun VPN configure : {clients} sort par votre connexion",
                    clients=", ".join(clients),
                ),
                blocking=False,
            )
        ]

    gluetun = container_id(f"{cfg.project_name}-gluetun")
    controles: list[Check] = []
    tunnel_verifie = False
    for sid in clients:
        conteneur = nom_conteneur(cfg, sid)
        mode = network_mode(conteneur)
        if mode is None:
            controles.append(
                Check(f"VPN {sid}", True, t("conteneur arrete"), blocking=False)
            )
            continue

        # Le test structurel d'abord : il ne coute rien et sa reponse est nette.
        attendu = f"container:{gluetun}" if gluetun else None
        if not mode.startswith("container:"):
            # Le remede n'est pas le meme selon a qui appartient le conteneur.
            # « Regenerez la pile » n'avance a rien pour un service adopte :
            # `adopt` ne genere aucun compose, deliberement — en generer un
            # donnerait a `uninstall` le pouvoir de detruire la stack de
            # l'utilisateur. Lui donner ce conseil l'enverrait tourner en rond.
            if cfg.services[sid].adopted:
                detail = t(
                    "NON PROTEGE : {conteneur} est sur le reseau {reseau}, pas dans "
                    "le tunnel. plugarr ne gere pas ce conteneur et ne peut pas l'y "
                    "placer : il faut le recreer vous-meme avec "
                    "network_mode: container:{gluetun}.",
                    conteneur=conteneur,
                    reseau=mode,
                    gluetun=f"{cfg.project_name}-gluetun",
                )
            else:
                detail = t(
                    "NON PROTEGE : le conteneur est sur le reseau {reseau}, pas "
                    "dans le tunnel. Tout torrent lance sort par votre "
                    "connexion. Regenerez la pile puis redemarrez-la.",
                    reseau=mode,
                )
            controles.append(Check(f"VPN {sid}", False, detail))
            continue
        if attendu and mode != attendu:
            controles.append(
                Check(
                    f"VPN {sid}",
                    False,
                    t(
                        "il partage la pile reseau d'un AUTRE conteneur que "
                        "{attendu} ({reseau}...)",
                        attendu=f"{cfg.project_name}-gluetun",
                        reseau=mode[:24],
                    ),
                )
            )
            continue

        protege, description = _sortie(conteneur)
        controles.append(Check(f"VPN {sid}", protege, description, blocking=not protege))
        tunnel_verifie = tunnel_verifie or protege

    # Le port entrant EN DERNIER : il ne se lit que si le tunnel tient, et un
    # verdict de protection doit passer avant une question de ratio.
    if tunnel_verifie:
        controles += _controle_port(cfg)
    return controles
