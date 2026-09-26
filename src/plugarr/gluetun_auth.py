"""Cle d'acces au serveur de controle de Gluetun.

PlugArr lit deux routes du serveur de controle : l'adresse publique (controle
de fuite, veille) et le port entrant (synchronisation des clients). Mesure le
2026-09-19 sur Gluetun v3.41.3 : elles repondent encore sans authentification,
mais Gluetun previent a chaque appel qu'elles deviendront privees, et sa
documentation les dit deja toutes privees dans la version en cours.

On pose donc un role, et une cle d'API, dans `/gluetun/auth/config.toml`. Ce
chemin est DEJA monte : `CONFIG_ROOT/gluetun` est le volume `/gluetun`. Aucun
changement de compose. Mesure sur v3.41.3 : sans cle ou avec une mauvaise, 401 ;
avec la bonne, 200. Des qu'un fichier existe, les routes NON listees deviennent
elles aussi privees ; PlugArr n'en appelle pas d'autre.

Le fichier fait foi : la cle n'est pas copiee dans `stack.yml`. Ce qui tourne
DANS Gluetun la relit sur place (`LIRE_CLE_SH`), sans qu'elle passe sur une
ligne de commande. Un fichier deja present, ecrit par l'utilisateur, est
complete, jamais reecrit.
"""

from __future__ import annotations

import os
import secrets
import tomllib
from pathlib import Path

from .layout import _donner
from .models import StackConfig

ROLE = "plugarr"
ROUTES = ("GET /v1/publicip/ip", "GET /v1/portforward")
FICHIER_CONTENEUR = "/gluetun/auth/config.toml"

#: Relit la cle du role PlugArr depuis l'interieur de Gluetun. `sed` et non un
#: analyseur TOML : l'image de Gluetun n'en a pas, et le bloc est le notre.
#:
#: `tr -d '\r'` d'abord : un fichier ecrit sous Windows finit ses lignes par
#: CRLF, et le `"$` du motif ne trouvait plus rien. Essai reel du 26/09/2026 :
#: cle lue vide, 401 sur /v1/portforward, et « aucun port obtenu » annonce
#: alors que Gluetun avait bien un port et que Transmission l'ecoutait.
LIRE_CLE_SH = (
    f"K=$(tr -d '\\r' < {FICHIER_CONTENEUR} 2>/dev/null "
    f"| sed -n '/^name = \"{ROLE}\"$/,/^\\[\\[/ s/^apikey = \"\\(.*\\)\"$/\\1/p' "
    f"| head -n 1)"
)


def chemin(cfg: StackConfig) -> Path:
    return Path(cfg.config_path("gluetun")) / "auth" / "config.toml"


def cle(cfg: StackConfig) -> str:
    """Cle du role PlugArr, ou chaine vide si le fichier n'en porte pas."""
    try:
        donnees = tomllib.loads(chemin(cfg).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return ""
    for role in donnees.get("roles") or []:
        if isinstance(role, dict) and role.get("name") == ROLE:
            return str(role.get("apikey") or "")
    return ""


def assurer(cfg: StackConfig) -> tuple[bool, str]:
    """Ajoute le role PlugArr s'il manque. Renvoie (ecrit, message).

    Le fichier est donne a PUID:PGID : la veille, dans son conteneur, tourne
    sous ce compte et doit lire la cle. Constate sur le banc : ecrit par root
    en 600, il restait illisible pour elle, et Gluetun lui repondait 401.
    Gluetun, lui, le lit en root.
    """
    if cle(cfg):
        # Un fichier ecrit en CRLF par une version precedente sous Windows :
        # seules les fins de ligne changent. La veille, dont l'image publiee
        # relit la cle avec l'ancien `sed`, la retrouve alors elle aussi.
        brut = chemin(cfg).read_bytes()
        if b"\r\n" in brut:
            chemin(cfg).write_bytes(brut.replace(b"\r\n", b"\n"))
        _donner(chemin(cfg).parent, (cfg.puid, cfg.pgid))
        return False, "role plugarr deja present"
    cible = chemin(cfg)
    cible.parent.mkdir(parents=True, exist_ok=True)
    existant = cible.read_text(encoding="utf-8") if cible.exists() else ""
    if existant.strip():
        try:
            tomllib.loads(existant)
        except tomllib.TOMLDecodeError:
            # Un fichier illisible ne se complete pas : Gluetun le refuserait
            # tout entier, et avec lui les roles de l'utilisateur.
            return False, "fichier d'authentification illisible, laisse tel quel"
    routes = ", ".join(f'"{r}"' for r in ROUTES)
    bloc = (
        f'\n[[roles]]\nname = "{ROLE}"\nroutes = [{routes}]\n'
        f'auth = "apikey"\napikey = "{secrets.token_urlsafe(24)}"\n'
    )
    contenu = existant.rstrip("\n") + "\n" + bloc if existant.strip() else bloc.lstrip("\n")
    # LF meme sous Windows : le fichier est lu dans un conteneur Linux.
    cible.write_text(contenu, encoding="utf-8", newline="\n")
    if os.name == "posix":
        cible.chmod(0o600)
    _donner(cible.parent, (cfg.puid, cfg.pgid))
    return True, "role plugarr ajoute au serveur de controle"
