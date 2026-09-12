"""Pre-semis des fichiers de configuration AVANT le premier demarrage.

C'est le coeur de l'architecture (PROMPT.md sec. 4.4). Plutot que de demarrer les
conteneurs puis de courir apres la cle API generee aleatoirement, on ecrit nous-memes
la cle dans `config.xml`. Le cablage devient deterministe et rejouable.

Le pre-semis n'ecrase JAMAIS un fichier existant : re-lancer `install` sur une stack
deja installee ne doit pas casser une configuration que l'utilisateur a modifiee.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import string
from pathlib import Path
from xml.etree import ElementTree as ET

from .i18n import t
from .layout import CONTAINER_PATHS


def generate_api_key() -> str:
    """32 caracteres hexadecimaux, format attendu par les *arr."""
    return secrets.token_hex(16)


#: Caracteres speciaux retenus. La liste est courte VOLONTAIREMENT : ces mots de
#: passe traversent un fichier .env lu par Docker Compose, une ligne de commande
#: de conteneur, un fichier XML, un INI et plusieurs charges JSON. Sont donc
#: exclus :
#:
#: - `$` : Compose l'interprete comme une interpolation de variable, meme dans un
#:   .env. Un mot de passe contenant `$HOME` arriverait vide dans le conteneur ;
#: - `'` : les valeurs du .env sont ecrites entre apostrophes, il les fermerait ;
#: - `"`, `\`, le backtick et `#` : citation, echappement et commentaires ;
#: - tout metacaractere de shell (`& ; | < > ( )`) : le .env est parfois source
#:   par un script, y compris dans notre propre CI.
#:
#: Ce qui reste donne 75 caracteres possibles, soit environ 125 bits d'entropie
#: sur 20 caracteres. Aucun de ces choix ne limite la solidite en pratique.
PASSWORD_SPECIALS = "!@%^*-_=+.,:?"

PASSWORD_CLASSES = (
    string.ascii_lowercase,
    string.ascii_uppercase,
    string.digits,
    PASSWORD_SPECIALS,
)

#: Longueur par defaut. Bien au-dela des 12 caracteres habituellement exiges :
#: personne n'a a retenir ces mots de passe, ils sont copies depuis la page
#: d'acces.
PASSWORD_LENGTH = 20


def generate_password(length: int = PASSWORD_LENGTH) -> str:
    """Mot de passe aleatoire, avec au moins un caractere de chaque classe.

    Tirer au hasard dans l'alphabet complet suffirait presque toujours, mais
    « presque » ne convient pas : certains services refusent un mot de passe sans
    chiffre. On garantit donc une occurrence de chaque classe, puis on melange —
    sinon les premiers caracteres suivraient toujours le meme ordre de classes.
    """
    if length < len(PASSWORD_CLASSES):
        raise ValueError(f"longueur minimale {len(PASSWORD_CLASSES)}, recu {length}")

    alphabet = "".join(PASSWORD_CLASSES)
    chars = [secrets.choice(group) for group in PASSWORD_CLASSES]
    chars += [secrets.choice(alphabet) for _ in range(length - len(chars))]
    # `SystemRandom.shuffle` puise dans la meme source que `secrets`.
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


# --------------------------------------------------------------------------- *arr


#: Longueur d'un mot de passe sans ponctuation. Plus long pour compenser :
#: 62 caracteres possibles sur 32 tirages donnent environ 190 bits, bien
#: au-dela des 125 bits du mot de passe ordinaire.
URL_PASSWORD_LENGTH = 32


def generate_url_password(length: int = URL_PASSWORD_LENGTH) -> str:
    """Mot de passe destine a vivre DANS une URL. Lettres et chiffres seulement.

    Un mot de passe ordinaire contient `?`, `^`, `@` ou `:`. Tous sont valides
    dans un fichier `.env` et tous cassent une URL : le `?` y ouvre la chaine de
    requete, le `@` separe l'identite de l'hote.

    Constate au premier demarrage reel de Silo, dont la connexion a sa base
    passe par `postgres://utilisateur:motdepasse@hote/base` :

        cannot parse `postgres://silo:xxxxxx@silo-postgres:5432/silo`:
        failed to parse as URL (net/url: invalid userinfo)

    Le conteneur redemarrait en boucle. Encoder le mot de passe serait l'autre
    voie, mais la substitution a lieu dans Docker, hors de notre portee : mieux
    vaut un mot de passe qui n'a jamais besoin d'etre encode. L'entropie vient
    alors de la longueur, ce qui ne coute rien — personne ne le tape.
    """
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_secret_key() -> str:
    """Cle de chiffrement au repos, 48 octets en base64.

    C'est la forme que Silo demande explicitement : « generate one with
    openssl rand -base64 48 ». Elle ne sert pas a se connecter, elle chiffre ce
    que le service stocke — on ne la reinitialise donc pas, on la perd.
    """
    return base64.b64encode(secrets.token_bytes(48)).decode()


def render_arr_config(
    *,
    api_key: str,
    port: int,
    instance_name: str,
    username: str,
    password: str,
    url_base: str = "",
    branch: str = "main",
) -> str:
    """Genere le config.xml minimal d'un *arr.

    Choix d'authentification, verifie empiriquement contre Sonarr 4.0.19.2979 :

    `Forms` + `Enabled` + un couple identifiant/mot de passe genere. C'est le seul
    reglage qui satisfait les trois contraintes a la fois :
      - l'UI web exige un login (GET / renvoie 302 vers /login)
      - l'API sans cle est refusee (401)
      - l'API avec X-Api-Key fonctionne, donc le cablage automatique reste possible

    L'alternative `External` + `DisabledForLocalAddresses` marche aussi pour le
    cablage, mais laisse les interfaces web ouvertes a tout le LAN. Refuse.

    Bonus verifie : l'application consomme <Username>/<Password> au premier
    demarrage, les migre en base, puis les EFFACE du fichier. Le mot de passe en
    clair ne survit donc pas sur le disque.
    """
    root = ET.Element("Config")
    values = {
        "BindAddress": "*",
        "Port": str(port),
        "UrlBase": url_base,
        "ApiKey": api_key,
        "AuthenticationMethod": "Forms",
        "AuthenticationRequired": "Enabled",
        "Username": username,
        "Password": password,
        "PasswordConfirmation": password,
        "InstanceName": instance_name,
        "Branch": branch,
        "LogLevel": "info",
        "UpdateMechanism": "Docker",
        "AnalyticsEnabled": "False",
    }
    for key, value in values.items():
        ET.SubElement(root, key).text = value
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode") + "\n"


def read_api_key(config_xml: Path) -> str | None:
    """Relit la cle d'un config.xml existant, pour rester idempotent."""
    try:
        text = config_xml.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        node = ET.fromstring(text).find("ApiKey")
    except ET.ParseError:
        return None
    return node.text.strip() if node is not None and node.text else None


def seed_arr(
    config_dir: Path,
    *,
    api_key: str,
    port: int,
    instance_name: str,
    username: str,
    password: str,
) -> tuple[str, bool]:
    """Ecrit config.xml s'il n'existe pas. Renvoie (cle_effective, a_ete_ecrit).

    Si le fichier existe deja, on adopte SA cle : l'utilisateur ou un run precedent
    fait autorite, jamais nous.
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    target = config_dir / "config.xml"
    if target.exists():
        existing = read_api_key(target)
        if existing:
            return existing, False
    target.write_text(
        render_arr_config(
            api_key=api_key,
            port=port,
            instance_name=instance_name,
            username=username,
            password=password,
        ),
        encoding="utf-8",
    )
    return api_key, True


# ------------------------------------------------------------------- Transmission


def render_transmission_settings(*, rpc_username: str, rpc_password: str) -> dict:
    """settings.json de Transmission.

    Points importants :
    - `rpc-whitelist-enabled: false` : sans ca, les conteneurs Sonarr/Radarr sont
      refuses par Transmission (adresses du reseau bridge non whitelistees).
    - `rpc-host-whitelist-enabled: false` : meme raison, cote en-tete Host.
    - `download-dir` sous /data/torrents pour que les hardlinks vers /data/media
      restent possibles.
    - Transmission hashe le mot de passe en clair au premier demarrage et REECRIT
      ce fichier a l'arret. Ne jamais l'editer pendant que le conteneur tourne.
    """
    return {
        "rpc-enabled": True,
        "rpc-bind-address": "0.0.0.0",
        "rpc-port": 9091,
        "rpc-url": "/transmission/",
        "rpc-authentication-required": True,
        "rpc-username": rpc_username,
        "rpc-password": rpc_password,
        "rpc-whitelist-enabled": False,
        "rpc-host-whitelist-enabled": False,
        "download-dir": CONTAINER_PATHS["torrents_root"],
        "incomplete-dir": CONTAINER_PATHS["torrents_incomplete"],
        "incomplete-dir-enabled": True,
        "rename-partial-files": True,
        "start-added-torrents": True,
        "watch-dir-enabled": False,
        "umask": 2,
    }


# -------------------------------------------------------------------- qBittorrent


def qbittorrent_password_hash(password: str) -> str:
    """Produit la valeur de `WebUI\\Password_PBKDF2`.

    Format : @ByteArray(<sel base64>:<empreinte base64>), PBKDF2-HMAC-SHA512,
    100000 iterations, cle de 64 octets, sel de 16 octets.

    Sans ce pre-semis, qBittorrent genere depuis la 4.6.1 un mot de passe temporaire
    aleatoire ecrit sur sa sortie standard : impossible a cabler automatiquement.
    Verifie contre qBittorrent 5.2.3 (image LinuxServer).
    """
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha512", password.encode(), salt, 100000, dklen=64)
    value = base64.b64encode(salt).decode() + ":" + base64.b64encode(digest).decode()
    return f"@ByteArray({value})"


def render_qbittorrent_conf(*, username: str, password: str, port: int = 8080) -> str:
    """qBittorrent.conf minimal.

    `HostHeaderValidation=false` est indispensable : sans lui, qBittorrent rejette
    les requetes de Sonarr et Radarr, qui l'appellent par son nom de conteneur
    (`http://qbittorrent:8080`) et non par une adresse IP.
    """
    lines = [
        "[LegalNotice]",
        "Accepted=true",
        "",
        "[Preferences]",
        f"WebUI\\Username={username}",
        f'WebUI\\Password_PBKDF2="{qbittorrent_password_hash(password)}"',
        f"WebUI\\Port={port}",
        "WebUI\\HostHeaderValidation=false",
        "WebUI\\CSRFProtection=false",
        # qBittorrent bannit une adresse apres cinq echecs d'authentification,
        # une heure durant. Le bannissement est PAR ADRESSE : une installation
        # qui s'est trompee de mot de passe fait bannir l'adresse de Sonarr, et
        # la suite est cruelle — le mot de passe redevient correct, mais le *arr
        # recoit un 403 et accuse les identifiants. Constate : 204 depuis l'hote
        # et 403 depuis le conteneur Sonarr, au meme instant, meme mot de passe.
        # Le seuil est releve, pas supprime : la protection contre une force
        # brute reste utile, elle ne doit simplement pas viser nos conteneurs.
        "WebUI\\MaxAuthenticationFailCount=100",
        "WebUI\\BanDuration=60",
        f"Downloads\\SavePath={CONTAINER_PATHS['torrents_root']}/",
        f"Downloads\\TempPath={CONTAINER_PATHS['torrents_incomplete']}/",
        "Downloads\\TempPathEnabled=true",
        "",
    ]
    return "\n".join(lines)


def seed_qbittorrent(
    config_dir: Path, *, username: str, password: str, port: int = 8080
) -> tuple[bool, str]:
    """Ecrit qBittorrent.conf s'il n'existe pas.

    Chemin impose par l'image LinuxServer : /config/qBittorrent/qBittorrent.conf.
    """
    target_dir = config_dir / "qBittorrent"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "qBittorrent.conf"
    if target.exists():
        # Conserver le fichier tel quel laissait une installation cassee : le
        # mot de passe qui y est hache vient d'une installation precedente, mais
        # plugarr en a genere un nouveau et l'annonce dans son rapport.
        # qBittorrent repondait alors « Forbidden » a tout le cablage. Constate
        # a l'usage. On ne remplace que l'identifiant et le mot de passe : le
        # reste des reglages appartient a l'utilisateur.
        return _replace_qbittorrent_credentials(target, username=username, password=password)
    target.write_text(
        render_qbittorrent_conf(username=username, password=password, port=port),
        encoding="utf-8",
    )
    return True, "qBittorrent.conf pre-seme (mot de passe hashe PBKDF2)"


def seed_transmission(
    config_dir: Path, *, rpc_username: str, rpc_password: str
) -> tuple[bool, str]:
    """Ecrit settings.json s'il n'existe pas. Renvoie (a_ete_ecrit, message)."""
    config_dir.mkdir(parents=True, exist_ok=True)
    target = config_dir / "settings.json"
    if target.exists():
        # Meme raison que pour qBittorrent : garder l'ancien mot de passe rendait
        # faux tout ce que le rapport annonce.
        return _replace_transmission_credentials(
            target, rpc_username=rpc_username, rpc_password=rpc_password
        )
    target.write_text(
        json.dumps(
            render_transmission_settings(
                rpc_username=rpc_username, rpc_password=rpc_password
            ),
            indent=4,
        )
        + "\n",
        encoding="utf-8",
    )
    return True, "settings.json pre-seme"


def _replace_qbittorrent_credentials(
    target: Path, *, username: str, password: str
) -> tuple[bool, str]:
    """Met a jour identifiant et mot de passe dans un qBittorrent.conf existant.

    Le fichier est un INI de Qt : on remplace deux lignes, on ne le reecrit pas.
    Les cles absentes sont ajoutees a la section `[Preferences]`.
    """
    texte = target.read_text(encoding="utf-8")
    remplacements = {
        r"WebUI\Username": username,
        r"WebUI\Password_PBKDF2": qbittorrent_password_hash(password),
        # Meme raison que dans le gabarit : ne pas se faire bannir soi-meme.
        r"WebUI\MaxAuthenticationFailCount": "100",
        r"WebUI\BanDuration": "60",
    }
    for cle, valeur in remplacements.items():
        motif = re.compile(rf"^{re.escape(cle)}=.*$", re.MULTILINE)
        if motif.search(texte):
            texte = motif.sub(lambda _m, v=valeur, c=cle: f"{c}={v}", texte)
        elif "[Preferences]" in texte:
            texte = texte.replace("[Preferences]", f"[Preferences]\n{cle}={valeur}", 1)
        else:
            texte = texte.rstrip("\n") + f"\n[Preferences]\n{cle}={valeur}\n"
    target.write_text(texte, encoding="utf-8")
    return True, "qBittorrent.conf existant : identifiants mis a jour"


def _replace_transmission_credentials(
    target: Path, *, rpc_username: str, rpc_password: str
) -> tuple[bool, str]:
    """Met a jour les identifiants RPC dans un settings.json existant.

    Transmission stocke le mot de passe HACHE apres son premier demarrage. Le
    reecrire en clair est la facon prevue de le changer : il le rehache au
    demarrage suivant.
    """
    try:
        reglages = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, f"settings.json illisible, conserve tel quel ({exc})"
    if not isinstance(reglages, dict):
        return False, "settings.json inattendu, conserve tel quel"

    reglages["rpc-username"] = rpc_username
    reglages["rpc-password"] = rpc_password
    reglages["rpc-authentication-required"] = True
    target.write_text(json.dumps(reglages, indent=4) + "\n", encoding="utf-8")
    return True, "settings.json existant : identifiants RPC mis a jour"


def replace_arr_api_key(config_dir: Path, api_key: str) -> bool:
    """Remplace la cle API dans un config.xml existant. Renvoie True si ecrit.

    C'est la SEULE voie qui fonctionne, et elle a demande un essai pour le
    savoir. `PUT config/host` accepte pourtant la nouvelle cle, repond **202
    Accepted**, et ne change rien : verifie contre Sonarr 4.0.19, la cle relue
    par l'API vaut toujours l'ancienne soixante secondes plus tard, et la
    nouvelle repond 401. Un code de retour n'est pas une preuve.

    On ne reecrit pas le fichier entier : apres son premier demarrage il
    contient bien plus que la cle, et le regenerer effacerait tout le reste.

    L'application relit le fichier au demarrage, et ne le reecrit PAS a l'arret
    — contrairement a Transmission. Une modification a chaud survit donc, et un
    simple redemarrage suffit a la prendre en compte : constate en changeant la
    cle sur une instance en marche, redemarrage, nouvelle cle acceptee en cinq
    secondes et ancienne refusee.
    """
    target = config_dir / "config.xml"
    if not target.is_file():
        return False
    texte = target.read_text(encoding="utf-8")
    remplace, nombre = re.subn(
        r"<ApiKey>[^<]*</ApiKey>", f"<ApiKey>{api_key}</ApiKey>", texte, count=1
    )
    if not nombre:
        return False
    target.write_text(remplace, encoding="utf-8")
    return True


def seed_sabnzbd(
    config_dir: Path,
    *,
    api_key: str,
    port: int,
    hotes_autorises: list[str],
    incomplet: str,
    complet: str,
) -> tuple[bool, str]:
    """Pre-seme `sabnzbd.ini`. Renvoie (ecrit, message).

    Trois reglages, et le deuxieme est celui qui fait perdre une soiree.

    **La cle API.** SABnzbd en genere une au premier demarrage, comme les *arr.
    La poser d'avance evite d'avoir a la relire ensuite, et permet aux *arr
    d'etre cables avant meme qu'il ait fini de demarrer.

    **La liste blanche d'hotes.** SABnzbd refuse toute requete dont l'en-tete
    `Host` ne figure pas dans `host_whitelist`, et n'y met par defaut QUE
    l'identifiant du conteneur. Sonarr appelant `http://sabnzbd:8085` recoit
    donc :

        Access denied - Hostname verification failed

    Verifie contre la 5.1.2. Le message ne mentionne ni Sonarr ni le reglage en
    cause, et renvoie vers une page d'aide generale.

    **Les repertoires.** Par defaut relatifs et sous `/config`, ce qui met les
    telechargements hors de `/data` : les liens physiques deviennent impossibles
    et chaque import recopie le fichier.

    Un fichier existant fait autorite pour sa cle, ses categories, ses serveurs
    et ses scripts. Deux valeurs relevent toutefois de la topologie que PlugArr
    genere et doivent rester coherentes avec le compose : le port d'ecoute
    INTERNE et les noms d'hote autorises. Les laisser diverger rendrait le
    service injoignable tout en conservant une configuration apparemment valide.
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    ini = config_dir / "sabnzbd.ini"
    hotes = ",".join(hotes_autorises) + ","

    if ini.exists():
        texte = ini.read_text(encoding="utf-8", errors="replace")
        lignes = []
        section = ""
        ancien_port: int | None = None
        port_trouve = False
        hotes_trouves = False
        manquants = list(filter(None, hotes_autorises))

        def completer_misc() -> None:
            nonlocal port_trouve, hotes_trouves
            if not port_trouve:
                lignes.append(f"port = {port}")
                port_trouve = True
            if not hotes_trouves:
                lignes.append(f"host_whitelist = {hotes}")
                hotes_trouves = True

        for ligne in texte.splitlines():
            depouillee = ligne.strip()
            if depouillee.startswith("[") and depouillee.endswith("]"):
                if section == "misc":
                    completer_misc()
                section = depouillee[1:-1].strip().lower()
            if section == "misc" and re.match(r"^\s*port\s*=", ligne):
                trouve = re.match(r"^(\s*port\s*=\s*)(\d+)(.*)$", ligne)
                if trouve:
                    port_trouve = True
                    ancien_port = int(trouve.group(2))
                    ligne = f"{trouve.group(1)}{port}{trouve.group(3)}"
            if section == "misc" and re.match(r"^\s*host_whitelist\s*=", ligne):
                hotes_trouves = True
                actuels = [
                    h.strip()
                    for h in ligne.split("=", 1)[1].strip().rstrip(",").split(",")
                    if h.strip()
                ]
                manquants = [h for h in hotes_autorises if h and h not in actuels]
                if manquants:
                    ligne = "host_whitelist = " + ",".join([*actuels, *manquants]) + ","
            lignes.append(ligne)
        if section == "misc":
            completer_misc()
        elif not port_trouve or not hotes_trouves:
            # Fichier sans `[misc]` : ni le port ni la liste d'hotes n'avaient
            # d'endroit ou aller. La fonction annoncait pourtant « port ajoute »
            # et « hotes ajoutes » en n'ecrivant rien, et SABnzbd restait sur
            # 8080 en refusant les *arr. On cree la section manquante.
            lignes.append("[misc]")
            completer_misc()
        port_change = ancien_port != port
        hotes_change = bool(manquants)
        if not hotes_change and not port_change:
            return False, t("sabnzbd.ini existant, port et liste d'hotes deja alignes")
        ini.write_text("\n".join(lignes) + "\n", encoding="utf-8")
        changements = []
        if port_change:
            changements.append(
                f"port {ancien_port} -> {port}" if ancien_port is not None else f"port ajoute : {port}"
            )
        if hotes_change:
            changements.append(f"hotes ajoutes : {', '.join(manquants)}")
        return False, "sabnzbd.ini existant, " + ", ".join(changements)

    ini.write_text(
        "\n".join(
            [
                "__version__ = 19",
                "[misc]",
                'host = "0.0.0.0"',
                f"port = {port}",
                f"api_key = {api_key}",
                f"nzb_key = {api_key}",
                f"host_whitelist = {hotes}",
                # `inet_exposure = 0` garde l'interface accessible sans mot de
                # passe depuis le reseau local, comme les autres services de la
                # pile. Le rendre public serait un autre sujet, et un choix.
                "inet_exposure = 0",
                f'download_dir = "{incomplet}"',
                f'complete_dir = "{complet}"',
                "permissions = 775",
                "auto_browser = 0",
                "check_new_rel = 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    # chmod 600 : le fichier porte la cle API. Sans effet utile sous Windows,
    # silencieux plutot que bruyant, comme partout ailleurs dans le projet.
    try:
        ini.chmod(0o600)
    except (OSError, NotImplementedError):
        pass
    return True, "sabnzbd.ini pre-seme (cle API et liste d'hotes)"
