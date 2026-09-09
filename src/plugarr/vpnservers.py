"""Filtre geographique accepte par Gluetun, fournisseur par fournisseur.

Les donnees viennent de l'IMAGE epinglee elle-meme, pas du depot amont :
`scripts/vpn_countries.py` demande a `gluetun-entrypoint format-servers` ce
qu'il connait, dans la version exacte que le compose deploie. Le depot avance ;
une valeur proposee par la liste amont mais absente de la version epinglee
serait refusee au demarrage, sans que rien ne l'explique a l'utilisateur.

**Tous les fournisseurs ne se filtrent pas par pays**, et c'est le piege que ce
module existe pour eviter. Cinq d'entre eux n'exposent AUCUN pays dans les
donnees de Gluetun :

- Windscribe, VyprVPN, Giganews et Private Internet Access classent par REGION ;
- Perfect Privacy ne connait que des VILLES.

Leur poser `SERVER_COUNTRIES` ne filtre rien du tout. Chaque fournisseur porte
donc le nom de la variable qu'il faut reellement lui donner.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data" / "vpn_countries.json"

#: Variable posee quand le fournisseur est inconnu du fichier — `custom`, ou un
#: fournisseur ajoute par une version plus recente de Gluetun.
DEFAULT_ENV = "SERVER_COUNTRIES"


@lru_cache(maxsize=1)
def _tables() -> tuple[str, dict[str, dict]]:
    contenu = json.loads(DATA.read_text(encoding="utf-8"))
    return contenu["gluetun"], contenu["providers"]


def gluetun_version() -> str:
    """Version de Gluetun d'ou proviennent ces listes."""
    return _tables()[0]


def filter_env(provider: str) -> str:
    """Variable d'environnement a poser pour filtrer ce fournisseur."""
    return _tables()[1].get(provider.strip().lower(), {}).get("env", DEFAULT_ENV)


def choices(provider: str) -> list[str]:
    """Valeurs acceptees par ce fournisseur. Vide = saisie libre.

    Vide n'est pas une erreur : `custom` n'a par construction aucune liste, et un
    fournisseur inconnu du fichier doit rester utilisable — la saisie libre passe
    alors telle quelle a Gluetun, qui la validera lui-meme.
    """
    return list(_tables()[1].get(provider.strip().lower(), {}).get("values", []))


def label(provider: str) -> str:
    """Libelle du filtre, pour l'ecran de saisie."""
    return {
        "SERVER_COUNTRIES": "Pays souhaites",
        "SERVER_REGIONS": "Regions souhaitees",
        "SERVER_CITIES": "Villes souhaitees",
    }.get(filter_env(provider), "Pays souhaites")


def port_forward(provider: str) -> bool:
    """Gluetun sait-il obtenir un port entrant chez ce fournisseur ?

    Quatre le permettent sur vingt-cinq. Ce n'est PAS une question de protection :
    les vingt et un autres chiffrent exactement pareil. Un port entrant rend
    seulement joignable, ce qui change le partage et le ratio, pas l'exposition.
    """
    return bool(_tables()[1].get(provider.strip().lower(), {}).get("port_forward"))


def pf_choices(provider: str) -> list[str]:
    """Lieux qui permettent reellement un port entrant chez ce fournisseur.

    Tous les serveurs ne l'offrent pas, et le lieu choisi decide donc si un port
    arrivera un jour. Releve contre l'image epinglee, l'ecart n'a rien d'anecdotique :

        private internet access   110 regions sur 165
        protonvpn                 125 pays sur 127

    Chez PIA, les 55 regions ecartees sont les 55 regions des Etats-Unis. Un
    utilisateur qui choisit son propre pays n'obtiendrait jamais de port, sans
    qu'aucun message ne l'explique.

    Renvoie la liste complete quand le fournisseur ne distingue pas ses serveurs :
    chez Perfect Privacy et PrivateVPN, le port ne depend pas du lieu.
    """
    table = _tables()[1].get(provider.strip().lower(), {})
    return list(table.get("pf_values") or table.get("values", []))
