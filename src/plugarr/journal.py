"""Journal d'installation.

Une installation touche a Docker, a huit API et a une dizaine de fichiers. Quand
quelque chose echoue, l'ecran ne montre que la derniere ligne, et le terminal se
ferme. Ce module ecrit tout dans un fichier, a cote des artefacts, pour qu'un
rapport de bug contienne autre chose que « ca ne marche pas ».

**Aucun secret n'y figure.** Les mots de passe et les cles API de la stack sont
remplaces par leur nom avant ecriture. C'est la condition pour qu'un utilisateur
puisse joindre ce fichier a une issue publique sans y reflechir.
"""

from __future__ import annotations

import logging
import platform
import re
import sys
from datetime import datetime
from pathlib import Path

LOGGER = logging.getLogger("plugarr")

#: Nom du fichier, a cote de docker-compose.yml et stack.yml.
FILENAME = "plugarr.log"

#: En dessous de cette longueur, une valeur n'est pas masquee : elle serait trop
#: courte pour etre un secret, et la masquer rendrait le journal illisible.
MIN_SECRET = 8


#: Secrets passes en parametre d'URL. Ceux-la, plugarr ne les connait PAS : ce
#: sont les cles que l'utilisateur tape lui-meme pour ses indexeurs, et que
#: Prowlarr renvoie telles quelles dans ses messages d'erreur — l'URL complete
#: de l'appel echoue, parametres compris. Constate sur un tracker reel :
#:
#:   HTTP request failed: [401:Unauthorized] [GET] at
#:   [https://exemple.org/api/torznab?apikey=<la cle de l'utilisateur>&t=search
#:
#: Le masquage par valeur connue ne pouvait rien pour elles, et la cle partait
#: dans le fichier qu'on demande aux gens de nous envoyer quand ca casse.
_SECRET_EN_URL = re.compile(
    r"((?:api_?key|pass_?key|rss_?key|auth_?key|torrent_pass|token|secret|digest|passwd?"
    r"|password)=)([^&\s\"'\]]{4,})",
    re.IGNORECASE,
)


def _caviarder(texte: str) -> str:
    return _SECRET_EN_URL.sub(lambda m: f"{m.group(1)}<masque>", texte)


def caviarder(texte: str) -> str:
    """La meme regle de forme, pour un texte qui ne passe pas par le journal.

    Le diagnostic rend ses preuves a l'ecran et a la console : elles doivent
    etre aussi propres que le fichier qu'on joint a un rapport de bug.
    """
    return _caviarder(texte)


class _Formatter(logging.Formatter):
    """Masque aussi la TRACE, pas seulement le message.

    Un filtre de `logging` ne voit que `record.getMessage()`. La trace d'une
    exception est mise en forme ici, plus tard, et echappait donc entierement
    au masquage — alors que c'est precisement la qu'atterrit le texte d'erreur
    d'un service tiers.
    """

    def format(self, record: logging.LogRecord) -> str:
        return _caviarder(super().format(record))


class _Masker(logging.Filter):
    """Remplace les secrets connus par leur nom, avant ecriture.

    Le filtre porte d'abord sur les VALEURS enregistrees explicitement, jamais
    sur une forme devinee : un filtre qui tente de reconnaitre « ce qui
    ressemble a un secret » laisse forcement passer ce qu'il n'a pas prevu.

    S'y ajoute UNE regle de forme, et une seule, pour ce que le masquage par
    valeur ne peut pas atteindre : les cles que l'utilisateur saisit pour ses
    indexeurs. plugarr ne les stocke jamais, il ne peut donc pas les
    reconnaitre — mais il sait a quoi ressemble un parametre d'URL qui en porte
    une. Cette regle complete le masquage exact, elle ne le remplace pas.
    """

    def __init__(self) -> None:
        super().__init__()
        self._secrets: dict[str, str] = {}

    def remember(self, label: str, value: str | None) -> None:
        if value and len(value) >= MIN_SECRET:
            self._secrets[value] = f"<{label}>"

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for value, replacement in self._secrets.items():
            message = message.replace(value, replacement)
        record.msg, record.args = _caviarder(message), ()
        return True


_MASKER = _Masker()


def remember_secrets(cfg: object) -> None:
    """Enregistre les secrets d'une StackConfig pour qu'ils soient masques."""
    services = getattr(cfg, "services", {}) or {}
    for sid, inst in services.items():
        _MASKER.remember(f"cle-api-{sid}", getattr(inst, "api_key", None))
        _MASKER.remember(f"mot-de-passe-{sid}", getattr(inst, "password", None))
    vpn = getattr(cfg, "vpn", None)
    if vpn is not None:
        _MASKER.remember("cle-wireguard", getattr(vpn, "wireguard_private_key", None))
        _MASKER.remember("mot-de-passe-openvpn", getattr(vpn, "openvpn_password", None))


def start(project_dir: Path, commande: str) -> Path:
    """Ouvre le journal et ecrit l'entete de session. Renvoie son chemin.

    Le fichier est ouvert en AJOUT : deux installations successives se relisent
    l'une apres l'autre, ce qui est precisement ce qu'on veut pour comprendre un
    second passage qui echoue la ou le premier avait reussi.
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    path = project_dir / FILENAME

    LOGGER.handlers.clear()
    LOGGER.setLevel(logging.DEBUG)
    LOGGER.propagate = False

    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(_Formatter("%(asctime)s  %(levelname)-7s %(message)s"))
    handler.addFilter(_MASKER)
    LOGGER.addHandler(handler)

    from . import __version__

    LOGGER.info("=" * 78)
    LOGGER.info("plugarr %s - %s", __version__, datetime.now().astimezone().isoformat(" ", "seconds"))
    LOGGER.info("commande   : %s", commande)
    LOGGER.info("plateforme : %s %s (%s)", platform.system(), platform.release(), sys.platform)
    LOGGER.info("python     : %s", sys.version.split()[0])
    LOGGER.info("gele       : %s", getattr(sys, "frozen", False))
    LOGGER.info("=" * 78)
    return path


def config(cfg: object) -> None:
    """Enregistre la configuration retenue, secrets exclus."""
    remember_secrets(cfg)
    LOGGER.info("plateforme choisie : %s", getattr(getattr(cfg, "platform", None), "value", "?"))
    LOGGER.info("config_root        : %s", getattr(cfg, "config_root", "?"))
    LOGGER.info("data_root          : %s", getattr(cfg, "data_root", "?"))
    LOGGER.info("PUID/PGID          : %s:%s (%s)", getattr(cfg, "puid", "?"),
                getattr(cfg, "pgid", "?"), getattr(cfg, "ids_source", "?"))
    LOGGER.info("services           : %s", ", ".join(getattr(cfg, "services", {})))


def checks(items: list) -> None:
    for check in items:
        LOGGER.log(
            logging.INFO if check.ok else logging.WARNING,
            "preflight %-24s %-5s %s",
            check.name,
            "OK" if check.ok else "ECHEC",
            check.detail,
        )


def progress(phase: str, message: str, ok: bool = True) -> None:
    LOGGER.log(logging.INFO if ok else logging.ERROR, "%-14s %s", phase, message)


def step(result: object) -> None:
    ok = getattr(result, "ok", False)
    LOGGER.log(
        logging.INFO if ok else logging.ERROR,
        "%-5s %s - %s",
        "OK" if ok else "ECHEC",
        getattr(result, "name", "?"),
        getattr(result, "detail", ""),
    )
    for warning in getattr(result, "warnings", []) or []:
        LOGGER.warning("      %s", warning)


def failure(message: str) -> None:
    LOGGER.error("%s", message)


def finish(message: str) -> None:
    LOGGER.info("%s", message)
    for handler in LOGGER.handlers:
        handler.flush()
