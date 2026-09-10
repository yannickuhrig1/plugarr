"""Generation de docker-compose.yml et .env.

Artefacts derives de StackConfig, jamais edites a la main.

Le rendu du client torrent existe en DEUX formes (PROMPT.md sec. 11.1) : avec et
sans VPN. Avec Gluetun le service perd son propre reseau et ses ports publies
migrent vers le conteneur VPN. La bascule est prevue ici des le depart pour ne pas
etre une rustine plus tard, meme si la Phase 1 n'expose que la forme sans VPN.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from . import catalog, registre
from .i18n import t
from .models import Category, StackConfig

NETWORK_NAME = "plugarr"

#: Volume Docker de la base de Silo. Voir `_service_block` : un montage vers le
#: disque de l'hote rend ses migrations 590 fois plus lentes sous Windows.
PG_VOLUME = "silo-pgdata"

#: Tag epingle de Gluetun. Le depot a ete transfere de qdm12/gluetun vers
#: passteque/gluetun ; l'image, elle, reste qmcgaw/gluetun.
GLUETUN_TAG = "v3.41.3"
def _entete() -> str:
    """En-tete des artefacts generes, dans la langue de l'installation."""
    return t(
        "# Genere par plugarr - NE PAS EDITER A LA MAIN.\n"
        "# Modifiez stack.yml puis relancez `plugarr generate`.\n"
    )


def flood_client(cfg: StackConfig) -> str | None:
    """Le client de telechargement que Flood pilote, ou None.

    Flood n'en pilote qu'un a la fois. Quand les deux sont installes,
    qBittorrent gagne : son API est plus riche.
    """
    if not cfg.enabled("flood"):
        return None
    for client_id in ("qbittorrent", "transmission"):
        if cfg.enabled(client_id):
            return client_id
    return None


def _flood_block(cfg: StackConfig) -> dict:
    """Options de Flood, selon le client de telechargement present.

    Flood n'est pas une image LinuxServer : ni PUID/PGID, ni UMASK. Il se
    configure entierement par ligne de commande.

    Les options ont ete relevees sur `flood --help` de l'image 4.16.1, pas
    supposees : `--qburl/--qbuser/--qbpass` pour qBittorrent,
    `--trurl/--truser/--trpass` pour Transmission.

    Quand les deux clients sont installes, qBittorrent gagne : son API est plus
    riche et Flood n'en pilote qu'un a la fois.
    """
    block: dict = {
        "environment": {"HOME": "/config", "TZ": cfg.timezone},
        "command": ["--port=3000", "--host=0.0.0.0", "--auth=none"],
    }
    for client_id, options in (
        ("qbittorrent", ("--qburl", "--qbuser", "--qbpass")),
        ("transmission", ("--trurl", "--truser", "--trpass")),
    ):
        if not cfg.enabled(client_id):
            continue
        spec, inst = catalog.get(client_id), cfg.services[client_id]
        # Flood n'est PAS dans le tunnel : sous VPN, le client de telechargement
        # y est, et perd son alias DNS. `http://qbittorrent:8080` ne resout donc
        # plus depuis Flood. Signale a l'usage : « Flood me dit impossible de se
        # connecter au client ». Meme cause que la panne de Prowlarr le meme
        # jour, et meme correction : on demande l'adresse a `internal_url`.
        base = inst.internal_url(
            spec, cfg.host, behind_vpn=cfg.vpn.enabled and spec.category is Category.DOWNLOAD
        )
        url_option, user_option, pass_option = options
        # Le mot de passe passe par le .env : le compose n'a pas a le porter en
        # clair. C'etait le dernier secret a y rester apres la cle WireGuard.
        variable = "FLOOD_CLIENT_PASS"
        block["command"] += [
            url_option,
            base if client_id == "qbittorrent" else f"{base}/transmission/rpc",
            user_option,
            inst.username or "",
            pass_option,
            "${" + variable + "}",
        ]
        block["depends_on"] = [client_id]
        break
    return block


def _gluetun_block(cfg: StackConfig) -> dict:
    """Le conteneur VPN, et les ports qu'il porte a la place du client.

    Un service en `network_mode: service:gluetun` n'a plus de pile reseau propre :
    il ne PEUT plus publier de port. Les siens doivent donc etre declares ici,
    sinon son interface web devient injoignable — panne silencieuse et tres
    deroutante.

    `cap_add: NET_ADMIN` et `/dev/net/tun` sont indispensables pour monter le
    tunnel. Le healthcheck est fourni par l'image elle-meme (verifie sur la
    v3.41.3), ce qui permet aux services qui en dependent d'attendre une
    connexion VPN reellement etablie, et pas seulement un conteneur demarre.
    """
    ports = []
    for sid in catalog.STARTUP_ORDER:
        if not cfg.enabled(sid):
            continue
        spec = catalog.get(sid)
        if spec.category is Category.DOWNLOAD:
            ports.append(f"{cfg.services[sid].host_port}:{spec.internal_port}")
    environnement = cfg.vpn.environment(cfg.timezone)

    # Le port entrant change tout seul, et le client ne le suit pas : il faut
    # aller le lui poser. Les identifiants passent par le .env, comme ceux de
    # Flood, plutot qu'en clair dans le compose.
    clients = port_sync_clients(cfg)
    if clients:
        environnement["VPN_PORT_FORWARDING_UP_COMMAND"] = (
            f"/bin/sh /gluetun/{PORT_SYNC} {{{{PORT}}}}"
        )
        if "qbittorrent" in clients:
            environnement["QBT_USER"] = cfg.services["qbittorrent"].username or ""
            environnement["QBT_PASS"] = "${QBITTORRENT_PASS}"
        if "transmission" in clients:
            environnement["TR_USER"] = cfg.services["transmission"].username or ""
            environnement["TR_PASS"] = "${TRANSMISSION_PASS}"

    return {
        "image": f"qmcgaw/gluetun:{GLUETUN_TAG}",
        "container_name": f"{cfg.project_name}-gluetun",
        "restart": "unless-stopped",
        "labels": {"plugarr.managed": "true", "plugarr.service": "gluetun"},
        "cap_add": ["NET_ADMIN"],
        "devices": ["/dev/net/tun:/dev/net/tun"],
        "environment": environnement,
        "volumes": ["${CONFIG_ROOT}/gluetun:/gluetun"],
        "ports": ports,
        "networks": [NETWORK_NAME],
    }


#: Nom du script de synchronisation, depose dans `${CONFIG_ROOT}/gluetun` — le
#: seul dossier que Gluetun monte deja. Un script plutot qu'une commande en
#: ligne : le YAML devrait sinon imbriquer trois niveaux de guillemets (shell,
#: JSON et interpolation Compose, ou `$` doit s'ecrire `$$`), et le resultat
#: serait illisible et impossible a deboguer.
PORT_SYNC = "port-sync.sh"


def port_sync_clients(cfg: StackConfig) -> list[str]:
    """Clients dont le port d'ecoute doit suivre celui que le VPN attribue.

    Vide si le fournisseur n'offre pas de port entrant : il n'y a alors aucun
    port a suivre. Les services adoptes sont exclus, leurs identifiants ne nous
    appartiennent pas.
    """
    from .vpnservers import port_forward

    if not cfg.vpn.enabled or not port_forward(cfg.vpn.provider):
        return []
    return [
        sid
        for sid in ("qbittorrent", "transmission")
        if cfg.enabled(sid) and not cfg.services[sid].adopted
    ]


def render_port_sync(cfg: StackConfig) -> str:
    """Le script que Gluetun lance a chaque obtention de port.

    Le probleme, mesure sur une stack reelle : Proton a change de port tout seul
    entre deux journees, Gluetun annoncait 48406, qBittorrent ecoutait toujours
    45270. Plus aucune connexion entrante, et rien nulle part ne le disait.

    Il tourne DANS Gluetun, qui partage sa pile reseau avec les clients : leurs
    interfaces sont donc joignables en `127.0.0.1`, sans conteneur tiers ni
    volume partage. C'est ce qui permet de se passer d'un mod externe telecharge
    a chaque demarrage.

    La boucle d'attente n'est pas une precaution de principe : au demarrage, le
    port peut arriver AVANT que l'interface du client n'ecoute. Sans elle, la
    pose echouerait et le port resterait faux jusqu'au renouvellement du bail.
    """
    lignes = [
        "#!/bin/sh",
        _entete().replace("docker-compose.yml", "stack.yml").rstrip("\n"),
        "",
        'PORT="$1"',
        '[ -n "$PORT" ] || exit 0',
        "",
        "# Le client peut ne pas encore ecouter quand le port arrive.",
        "essayer() {",
        "  i=0",
        "  while [ $i -lt 30 ]; do",
        '    if "$@" 2>/dev/null; then return 0; fi',
        "    i=$((i + 1))",
        "    sleep 2",
        "  done",
        "  return 1",
        "}",
        "",
    ]

    clients = port_sync_clients(cfg)
    if "qbittorrent" in clients:
        port = catalog.get("qbittorrent").internal_port
        lignes += [
            "poser_qbittorrent() {",
            '  wget -q --save-cookies "$CK" --keep-session-cookies \\',
            '    --post-data "username=$QBT_USER&password=$QBT_PASS" \\',
            f'    -O /dev/null "http://127.0.0.1:{port}/api/v2/auth/login" || return 1',
            '  wget -q --load-cookies "$CK" \\',
            '    --post-data "json={\\"listen_port\\":$PORT}" \\',
            f'    -O /dev/null "http://127.0.0.1:{port}/api/v2/app/setPreferences"',
            "}",
            'CK=/tmp/plugarr-qbittorrent.cookies',
            'essayer poser_qbittorrent && echo "qbittorrent ecoute sur $PORT"',
            "",
        ]

    if "transmission" in clients:
        port = catalog.get("transmission").internal_port
        lignes += [
            f'RPC="http://127.0.0.1:{port}/transmission/rpc"',
            "poser_transmission() {",
            "  # Transmission repond 409 au premier appel en donnant la session",
            "  # a reutiliser. Sans cet aller-retour, tout POST est refuse.",
            '  SID=$(wget -S -q -O /dev/null --user="$TR_USER" --password="$TR_PASS" \\',
            '        "$RPC" 2>&1 | sed -n "s/.*X-Transmission-Session-Id: *//p" | tr -d "\\r")',
            '  [ -n "$SID" ] || return 1',
            '  wget -q -O /dev/null --user="$TR_USER" --password="$TR_PASS" \\',
            '    --header="X-Transmission-Session-Id: $SID" \\',
            '    --post-data "{\\"method\\":\\"session-set\\",\\"arguments\\":{\\"peer-port\\":$PORT}}" \\',
            '    "$RPC"',
            "}",
            'essayer poser_transmission && echo "transmission ecoute sur $PORT"',
            "",
        ]
    return "\n".join(lignes)


def _service_block(cfg: StackConfig, service_id: str) -> dict:
    spec = catalog.get(service_id)
    inst = cfg.services[service_id]

    block: dict = {
        # L'image vient de l'INSTANCE, pas du catalogue : c'est ce qui permet de
        # mettre a jour un service sans attendre une nouvelle version de plugarr.
        "image": inst.image or spec.image,
        # Prefixe par le nom de projet, pour ne PAS entrer en collision avec une
        # stack existante. Beaucoup de NAS font deja tourner un conteneur nomme
        # `sonarr` : sans ce prefixe, `docker compose up` echoue ou, pire, prend
        # la place du conteneur de production.
        # Le cablage n'est pas affecte : les conteneurs se joignent par leur nom de
        # SERVICE compose (`http://sonarr:8989`), pas par container_name.
        "container_name": f"{cfg.project_name}-{spec.id}",
        "restart": "unless-stopped",
        # Marqueur explicite, pour que `scan` reconnaisse nos propres conteneurs
        # sans deviner d'apres leur nom. Deviner produisait des faux positifs sur
        # des noms legitimes comme "mon-sonarr" ou "media-sonarr", et sautait donc
        # en silence des conteneurs qui ne nous appartiennent pas.
        "labels": {"plugarr.managed": "true", "plugarr.service": spec.id},
        "environment": {
            "PUID": str(cfg.puid),
            "PGID": str(cfg.pgid),
            "TZ": cfg.timezone,
            "UMASK": cfg.umask,
        },
        "volumes": [
            f"${{CONFIG_ROOT}}/{spec.config_dir}:/config",
            "${DATA_ROOT}:/data",
        ],
        "networks": [NETWORK_NAME],
    }

    if service_id == "flood":
        block.update(_flood_block(cfg))
    elif service_id == "qui":
        # qui n'est pas une image LinuxServer : ni PUID/PGID ni UMASK. Il decouvre
        # ses instances qBittorrent par sa propre interface, on ne fait que lui
        # donner un port et un dossier de donnees.
        block["environment"] = {"TZ": cfg.timezone, "QUI__HOST": "0.0.0.0"}
        block["volumes"] = [f"${{CONFIG_ROOT}}/{spec.config_dir}:/config"]
        block["depends_on"] = ["qbittorrent"]
    elif service_id == "recyclarr":
        # Recyclarr n'expose rien et ne touche pas aux medias : il parle aux API
        # des *arr. `CRON_SCHEDULE` est sa planification, pas un reglage de plugarr.
        block["environment"] = {"TZ": cfg.timezone, "CRON_SCHEDULE": "@daily"}
        block["volumes"] = [f"${{CONFIG_ROOT}}/{spec.config_dir}:/config"]
    elif service_id == "seerr":
        # Ni PUID ni PGID, ni acces aux medias : Seerr ne touche AUCUN fichier.
        # Il transmet des demandes aux *arr, qui telechargent.
        block["environment"] = {"TZ": cfg.timezone, "LOG_LEVEL": "info"}
        block["volumes"] = [f"${{CONFIG_ROOT}}/{spec.config_dir}:/app/config"]
    elif service_id == "sabnzbd":
        block["environment"] = {
            "PUID": str(cfg.puid),
            "PGID": str(cfg.pgid),
            "TZ": cfg.timezone,
            "UMASK": cfg.umask,
        }
        block["volumes"] = [
            f"${{CONFIG_ROOT}}/{spec.config_dir}:/config",
            # `/data` ENTIER, comme les clients torrent : c'est ce qui rend les
            # liens physiques possibles entre le telechargement et la
            # mediatheque. Monter seulement `/data/usenet` obligerait chaque
            # import a recopier le fichier.
            "${DATA_ROOT}:/data",
        ]
    elif service_id == "droppedneedle":
        block["environment"] = {
            "PUID": str(cfg.puid),
            "PGID": str(cfg.pgid),
            "TZ": cfg.timezone,
        }
        block["volumes"] = [
            f"${{CONFIG_ROOT}}/{spec.config_dir}/config:/app/config",
            # `/app/cache` PORTE LA BASE, et rien ne le dit. La table
            # `auth_users` vit dans `/app/cache/library.db` : sans ce montage,
            # toute recreation du conteneur efface le compte administrateur, les
            # reglages du client de telechargement et la bibliotheque entiere.
            # Constate en vrai — l'accueil reussissait, puis la connexion avec
            # les identifiants annonces repondait 401 apres un simple
            # redemarrage. Le compose amont ne monte que /app/config.
            # `/data` ENTIER, comme SABnzbd. C'est ce qui fait que DroppedNeedle
            # voit les telechargements termines exactement la ou SABnzbd les
            # depose : son champ `downloads_mount` n'a alors rien a remapper, et
            # l'import lie le fichier au lieu de le recopier.
            "${DATA_ROOT}:/data",
        ]
    elif service_id == "audiobookshelf":
        # Ni PUID ni PGID : ce n'est pas une image LinuxServer.
        block["environment"] = {"TZ": cfg.timezone}
        block["volumes"] = [
            f"${{CONFIG_ROOT}}/{spec.config_dir}/config:/config",
            # `/metadata` est un SECOND volume, distinct de la configuration :
            # il porte les couvertures et les donnees extraites. Le confondre
            # avec /config gonfle les sauvegardes de plusieurs centaines de Mo
            # pour rien.
            f"${{CONFIG_ROOT}}/{spec.config_dir}/metadata:/metadata",
            # Les deux bibliotheques qu'il pilote, montees a l'endroit ou le
            # cablage ira les declarer. En LECTURE SEULE : Audiobookshelf lit,
            # il n'organise pas.
            "${DATA_ROOT}/media/books:/books:ro",
            "${DATA_ROOT}/media/audiobooks:/audiobooks:ro",
        ]
    elif service_id == "silo-postgres":
        # `POSTGRES_PASSWORD` vient du .env comme tout secret genere. Le
        # healthcheck n'est pas decoratif : Silo refuse de demarrer si sa base
        # n'a pas fini son initialisation, et `depends_on` s'appuie dessus.
        block["environment"] = {
            "POSTGRES_USER": "silo",
            "POSTGRES_PASSWORD": "${SILO_POSTGRES_PASS}",
            "POSTGRES_DB": "silo",
            "TZ": cfg.timezone,
        }
        # VOLUME DOCKER NOMME, pas un montage vers le disque de l'hote. C'est
        # le seul point du catalogue ou nous nous ecartons de la convention
        # « tout sous CONFIG_ROOT », et la mesure ne laisse pas le choix :
        #
        #   base vide, meme image, meme machine, Docker Desktop / Windows
        #   montage vers un dossier de l'hote -> migrations appliquees en 2935 s
        #   volume Docker nomme              -> les memes migrations en 5 s
        #
        # Silo enchaine des milliers de petites ecritures synchrones pendant ses
        # migrations ; chacune traverse la couche de partage de fichiers de
        # Docker Desktop. Le premier essai reel a expire au bout de 300 s alors
        # que PostgreSQL fonctionnait parfaitement : il etait simplement 590
        # fois plus lent. Une base de donnees n'a de toute facon rien a faire
        # dans un dossier que l'utilisateur ouvre et sauvegarde a la main.
        block["volumes"] = []
        block["healthcheck"] = {
            "test": ["CMD-SHELL", "pg_isready -U silo"],
            "interval": "5s",
            "timeout": "3s",
            "retries": 5,
            # `start_period` est ABSENT du compose amont, et c'est un piege.
            # Au tout premier demarrage `initdb` cree la base, ce qui depassait
            # les 25 s que 5 essais de 5 s accordent. Compose declarait alors le
            # conteneur malade et REFUSAIT de demarrer Silo, pendant que le
            # journal disait « database system is ready to accept connections ».
            # Le volume nomme a rendu ce cas rare, il ne l'a pas rendu
            # impossible : une machine chargee reste plus lente qu'une machine
            # au repos. On garde la marge, elle ne coute rien quand tout va
            # bien — la sonde repond des que la base repond.
            "start_period": "90s",
        }
        # pgvector construit ses index en memoire partagee. 8 Go est le defaut
        # du projet ; nous restons modestes, une stack media n'est pas un
        # entrepot de donnees et la valeur se releve dans le compose.
        block["shm_size"] = "1gb"
        block["command"] = ["postgres", "-c", "listen_addresses=*"]
    elif service_id == "silo-redis":
        block["environment"] = {"TZ": cfg.timezone}
        block["volumes"] = [f"${{CONFIG_ROOT}}/{spec.config_dir}:/data"]
        block["healthcheck"] = {
            "test": ["CMD", "redis-cli", "ping"],
            "interval": "5s",
            "timeout": "3s",
            "retries": 5,
            "start_period": "30s",
        }
    elif service_id == "silo":
        block["environment"] = {
            "MODE": "integrated",
            # Les ports INTERNES ne bougent jamais. Le decalage se fait cote
            # hote, ce que le projet prevoit explicitement.
            "PORT": "8080",
            "JF_PORT": "8096",
            # Sans elle, le serveur refuse de demarrer. Sa PERTE rend les
            # secrets chiffres irrecuperables : elle est donc generee une fois,
            # conservee dans le .env, et signalee a l'utilisateur.
            "SECRET_KEY": "${SILO_SECRET_KEY}",
            "DATABASE_URL": (
                "postgres://silo:${SILO_POSTGRES_PASS}@silo-postgres:5432/silo?sslmode=disable"
            ),
            "REDIS_URL": "redis://silo-redis:6379",
            "SILO_PLUGIN_CACHE_DIR": "/var/lib/silo/plugins",
            "TZ": cfg.timezone,
        }
        block["volumes"] = [
            f"${{CONFIG_ROOT}}/{spec.config_dir}/plugins:/var/lib/silo/plugins",
            f"${{CONFIG_ROOT}}/{spec.config_dir}/compat:/var/lib/silo/compat",
            f"${{CONFIG_ROOT}}/{spec.config_dir}/transcode:/tmp/silo-transcode",
            # LECTURE SEULE. Silo lit les medias, il ne les organise pas : ce
            # sont les *arr qui ecrivent. Le montage en lecture seule rend la
            # cohabitation sure plutot que simplement probable.
            "${DATA_ROOT}/media:/mnt/media:ro",
        ]
    elif service_id == "autobrr":
        # autobrr n'a pas besoin de /data : il ne touche pas aux fichiers, il
        # pousse des sorties vers les applications.
        block["volumes"] = [f"${{CONFIG_ROOT}}/{spec.config_dir}:/config"]

    for nom, chemin in spec.named_volumes:
        block.setdefault("volumes", []).insert(0, f"{nom}:{chemin}")

    torrent_client = spec.category is Category.DOWNLOAD
    if cfg.vpn_enabled and torrent_client:
        # Forme VPN : le client perd son reseau et ses ports. Gluetun les porte.
        block.pop("networks", None)
        block["network_mode"] = "service:gluetun"
        block["depends_on"] = {"gluetun": {"condition": "service_healthy"}}
    elif spec.internal_port:
        block["ports"] = [f"{inst.host_port}:{spec.internal_port}"]

    # Un service peut en publier plusieurs. Silo expose son interface, une API
    # compatible Jellyfin et une API compatible Audiobookshelf : trois portes
    # differentes sur le meme conteneur.
    for interne, hote in sorted(inst.extra_ports.items()):
        block.setdefault("ports", []).append(f"{hote}:{interne}")

    if spec.depends_on_healthy:
        # SAIN, pas seulement demarre. Silo refuse de demarrer si sa base n'a
        # pas fini son initialisation, et un `depends_on` nu ne l'attend pas.
        block["depends_on"] = {
            dep: {"condition": "service_healthy"}
            for dep in spec.depends_on_healthy
            if cfg.enabled(dep)
        }

    return block


def build_compose(cfg: StackConfig) -> dict:
    services = {sid: _service_block(cfg, sid) for sid in catalog.STARTUP_ORDER if cfg.enabled(sid)}
    if not services:
        raise ValueError(t("aucun service selectionne"))
    if cfg.vpn.enabled:
        gaps = cfg.vpn.missing()
        if gaps:
            raise ValueError("VPN active mais incomplet : il manque " + ", ".join(gaps))
        services = {"gluetun": _gluetun_block(cfg), **services}
    doc: dict[str, Any] = {
        "name": cfg.project_name,
        "services": services,
        "networks": {NETWORK_NAME: {"driver": "bridge"}},
    }
    # Les volumes nommes, deduits du catalogue. Compose prefixe leur nom par
    # celui du projet : deux installations ne se marchent pas dessus.
    # `plugarr uninstall --remove-config` les emporte ; sans l'option ils
    # survivent a un `down`, ce qui est le comportement voulu pour une base.
    # `gluetun` est bati a part et n'entre pas au catalogue : l'interroger ici
    # levait « service inconnu: 'gluetun' » des qu'un VPN etait actif.
    nommes = {
        nom: {}
        for sid in services
        if sid in catalog.CATALOG
        for nom, _chemin in catalog.get(sid).named_volumes
    }
    if nommes:
        doc["volumes"] = nommes
    return doc


def render_compose(cfg: StackConfig) -> str:
    return _entete() + yaml.safe_dump(
        build_compose(cfg), sort_keys=False, default_flow_style=False, width=100
    )


def _env_value(value: object) -> str:
    """Valeur de .env, protegee par des apostrophes.

    Les mots de passe generes contiennent des caracteres speciaux. Sans
    apostrophes, Compose interpreterait certains d'entre eux, et un `.env` parfois
    source par un script y verrait des metacaracteres. Les apostrophes empechent
    aussi l'interpolation, ce qui est exactement ce qu'on veut pour un secret.

    L'apostrophe elle-meme est exclue de l'alphabet des mots de passe ; on la
    neutralise malgre tout, au cas ou une valeur viendrait d'ailleurs.
    """
    text = str(value)
    return "'" + text.replace("'", "'\\''") + "'"


def render_env(cfg: StackConfig) -> str:
    lines = [
        t("# Genere par plugarr. Contient des secrets : ne JAMAIS commiter."),
        f"COMPOSE_PROJECT_NAME={_env_value(cfg.project_name)}",
        # Les chemins aussi : un dossier contenant une espace est parfaitement
        # ordinaire sous Windows comme sur un NAS.
        f"CONFIG_ROOT={_env_value(cfg.config_root)}",
        f"DATA_ROOT={_env_value(cfg.data_root)}",
        f"PUID={_env_value(cfg.puid)}",
        f"PGID={_env_value(cfg.pgid)}",
        f"TZ={_env_value(cfg.timezone)}",
        f"UMASK={_env_value(cfg.umask)}",
        "",
        t("# Cles API pre-semees - utilisees par le cablage automatique."),
    ]
    pilote = flood_client(cfg)
    if pilote is not None:
        # Flood recoit le mot de passe du client qu'il pilote. Il etait ecrit en
        # clair dans le compose, dernier secret a y rester.
        lines.append(f"FLOOD_CLIENT_PASS={_env_value(cfg.services[pilote].password or '')}")
    if cfg.vpn.enabled:
        # Le compose ne porte plus que le NOM de ces variables.
        if cfg.vpn.vpn_type == "wireguard":
            lines.append(f"VPN_WIREGUARD_KEY={_env_value(cfg.vpn.wireguard_private_key)}")
        else:
            lines.append(f"VPN_OPENVPN_USER={_env_value(cfg.vpn.openvpn_user)}")
            lines.append(f"VPN_OPENVPN_PASS={_env_value(cfg.vpn.openvpn_password)}")
    for sid in catalog.STARTUP_ORDER:
        inst = cfg.services.get(sid)
        if inst is None:
            continue
        # Un identifiant de service peut contenir un tiret (`silo-postgres`) ;
        # un nom de variable d'environnement, non.
        up = sid.upper().replace("-", "_")
        if inst.secret_key:
            lines.append(f"{up}_SECRET_KEY={_env_value(inst.secret_key)}")
        if inst.api_key:
            lines.append(f"{up}_API_KEY={_env_value(inst.api_key)}")
        if inst.username:
            lines.append(f"{up}_USER={_env_value(inst.username)}")
        if inst.password:
            lines.append(f"{up}_PASS={_env_value(inst.password)}")
    return "\n".join(lines) + "\n"


#: Ce que plugarr depose a cote de ses artefacts. Il n'ecrase jamais un
#: .gitignore existant : le repertoire peut etre celui de quelqu'un d'autre.
#: L'en-tete est traduit a l'ecriture ; la liste, elle, ne se traduit pas.
_GITIGNORE_ENTETE = (
    "# Ecrit par plugarr. Ces fichiers contiennent vos mots de passe, vos "
    "cles API\n"
    "# et, si le VPN est active, votre cle privee WireGuard. Ne les "
    "commitez pas.\n"
)

_GITIGNORE = """.env
stack.yml
stack.yml.*
docker-compose.yml
acces-plugarr.html
plugarr.log
.plugarr-maintenance.json
.plugarr-maintenance.tmp
backups/
"""

#: Combien de `stack.yml` precedents sont gardes a cote du courant.
#:
#: Douze, et le chiffre vient d'une mesure, pas d'une intuition. Une SEULE
#: installation reelle sur une pile de cinq services a consomme QUATRE entrees :
#: `write_artifacts` est appele trois fois par `install` — avant le pre-semis,
#: apres l'adoption des cles API, apres le cablage — puis une fois de plus par
#: `wire`, et chaque passage ecrit un contenu different.
#:
#: A cinq, deux installations ratees de suite chassaient donc le mot de passe
#: qui, lui, fonctionnait : exactement ce que cet historique existe pour
#: empecher. Douze couvre trois installations completes.
HISTORIQUE = 12


def historique(project_dir: Path) -> list[Path]:
    """Les `stack.yml` precedents, du plus recent au plus ancien."""
    return [
        chemin
        for chemin in (Path(project_dir) / f"stack.yml.{n}" for n in range(1, HISTORIQUE + 1))
        if chemin.is_file()
    ]


def _historiser(stack_path: Path) -> None:
    """Decale stack.yml vers stack.yml.1, .1 vers .2, et ainsi de suite.

    **Pourquoi cela existe.** `write_artifacts` est appele AVANT que le cablage
    n'ait prouve quoi que ce soit — trois fois par installation, dont une avant
    meme le `docker compose up`. Le `stack.yml` ecrase portait le seul
    exemplaire en clair des mots de passe de Jellyfin, autobrr et qui, qui n'en
    gardent qu'un hachage. Une installation qui echouait detruisait donc le mot
    de passe qui, lui, fonctionnait — sans retour possible.

    Constate sur une installation reelle : un compte Jellyfin cree le 4
    septembre, un `stack.yml` reecrit les jours suivants, et plus aucun moyen
    d'entrer dans Jellyfin autrement qu'en effacant sa configuration.

    Un fichier identique au dernier garde n'est pas historise : sans cela,
    `plugarr generate` lance trois fois de suite chasserait les cinq versions
    utiles avec cinq copies de la meme.
    """
    if not stack_path.is_file():
        return
    try:
        actuel = stack_path.read_bytes()
    except OSError:
        return

    premier = stack_path.with_suffix(stack_path.suffix + ".1")
    if premier.is_file():
        try:
            if premier.read_bytes() == actuel:
                return
        except OSError:
            pass

    for rang in range(HISTORIQUE - 1, 0, -1):
        source = stack_path.parent / f"{stack_path.name}.{rang}"
        cible = stack_path.parent / f"{stack_path.name}.{rang + 1}"
        if not source.is_file():
            continue
        try:
            cible.unlink(missing_ok=True)
            source.rename(cible)
        except OSError:
            # Un fichier verrouille ne doit pas empecher l'installation : on
            # perd une entree d'historique, pas la configuration courante.
            continue
    try:
        premier.write_bytes(actuel)
        _restrict(premier)
    except OSError:
        return


def write_artifacts(cfg: StackConfig, target_dir: Path) -> list[Path]:
    """Ecrit docker-compose.yml, .env et stack.yml. Renvoie les chemins ecrits."""
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    compose_path = target_dir / "docker-compose.yml"
    compose_path.write_text(render_compose(cfg), encoding="utf-8")
    written.append(compose_path)

    env_path = target_dir / ".env"
    env_path.write_text(render_env(cfg), encoding="utf-8")
    _restrict(env_path)
    written.append(env_path)

    stack_path = target_dir / "stack.yml"
    # L'historique AVANT l'ecriture : c'est le fichier sur le point d'etre
    # ecrase qu'il faut garder, pas celui qu'on s'apprete a poser.
    _historiser(stack_path)
    stack_path.write_text(
        _entete().replace("docker-compose.yml", "stack.yml")
        + yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    _restrict(stack_path)
    written.append(stack_path)

    # Le registre note OU vit cette installation. Sans lui, `stack.yml` n'est
    # cherche que dans le repertoire courant : lancer l'executable depuis un
    # autre dossier repartait de zero en silence, avec des mots de passe neufs
    # que les services refusaient ensuite.
    registre.enregistrer(target_dir, cfg.config_root, cfg.project_name)

    # plugarr annonce a l'utilisateur, en fin d'installation et sur la page
    # d'acces, que ses identifiants sont « deja dans .gitignore ». C'etait faux :
    # aucun .gitignore n'etait ecrit. Trois des fichiers ci-dessus contiennent
    # des secrets en clair — .env les porte tous, stack.yml les repete, et
    # docker-compose.yml porte la cle WireGuard. Une promesse tenue vaut mieux
    # qu'une promesse repetee.
    gitignore = target_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(t(_GITIGNORE_ENTETE) + _GITIGNORE, encoding="utf-8")
        written.append(gitignore)

    # Le script de synchronisation du port entrant. Il va dans CONFIG_ROOT et non
    # a cote du compose : c'est le seul dossier que Gluetun monte deja, et lui en
    # monter un second pour un fichier serait un mecanisme de plus a expliquer.
    if port_sync_clients(cfg):
        gluetun_dir = Path(cfg.config_root) / "gluetun"
        gluetun_dir.mkdir(parents=True, exist_ok=True)
        script = gluetun_dir / PORT_SYNC
        script.write_text(render_port_sync(cfg), encoding="utf-8", newline="\n")
        # Le conteneur le lance par `sh script`, donc le bit d'execution n'est pas
        # requis. On le pose quand meme, pour qui l'essaierait a la main.
        try:
            script.chmod(0o755)
        except (OSError, NotImplementedError):
            pass
        written.append(script)
    return written


def _restrict(path: Path) -> None:
    """chmod 600. Sans effet utile sur Windows, silencieux plutot que bruyant."""
    try:
        path.chmod(0o600)
    except (OSError, NotImplementedError):
        pass
