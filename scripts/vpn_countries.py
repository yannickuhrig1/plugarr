"""Extrait, par fournisseur VPN, le filtre geographique et ses valeurs.

    python scripts/vpn_countries.py

Ecrit `src/plugarr/data/vpn_countries.json`, embarque dans le paquet.

Tous les fournisseurs ne se filtrent PAS par pays, et c'est le piege. Cinq
d'entre eux n'exposent aucun pays dans les donnees de Gluetun : Windscribe,
Private Internet Access, VyprVPN, Giganews et Perfect Privacy classent leurs
serveurs par REGION. Leur poser `SERVER_COUNTRIES` ne filtre rien. On releve
donc pour chacun le champ qu'il renseigne reellement, et l'assistant pose la
bonne variable d'environnement.

Pourquoi generer plutot que telecharger a l'usage : l'assistant doit proposer
ces pays alors qu'aucun conteneur ne tourne encore, et sans dependre du reseau.
Le fichier fait quelques dizaines de kilo-octets ; les donnees d'origine pesent
plusieurs mega-octets.

Pourquoi l'IMAGE et pas le depot amont : le compose epingle une version precise
de Gluetun, et c'est celle-la qui validera les valeurs saisies. Le depot, lui,
avance. Un pays propose par la liste amont mais absent de la version epinglee
serait refuse au demarrage, ce que rien n'expliquerait a l'utilisateur.

Les valeurs viennent donc de `gluetun-entrypoint format-servers`, dans l'image
exacte que le compose deploie.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from plugarr.compose import GLUETUN_TAG
from plugarr.models import VPN_PROVIDERS

SORTIE = ROOT / "src" / "plugarr" / "data" / "vpn_countries.json"

#: Fournisseurs sans liste de serveurs embarquee.
#: - `custom` : l'utilisateur fournit sa propre configuration, Gluetun ne connait
#:   aucun serveur pour lui. `GetFilterChoices` renvoie d'ailleurs du vide.
#: - `pia` : alias de `private internet access`, accepte par Gluetun mais absent
#:   de `providers.All()`. Verifie contre l'image : `pia` demarre et tente de se
#:   connecter, la valeur est donc bien reconnue.
SANS_LISTE = {"custom"}

#: Fournisseurs pour lesquels Gluetun sait obtenir un port entrant. La liste
#: vient de sa documentation (`setup/advanced/vpn-port-forwarding.md`) et non des
#: donnees de serveurs : seuls DEUX d'entre eux marquent leurs serveurs un par un.
#:
#: Releve contre l'image v3.41.3, et l'ecart compte :
#:
#:   protonvpn                782 serveurs sur 1600 portent `port_forward`
#:   private internet access  301 serveurs sur  447 portent `port_forward`
#:   perfect privacy, privatevpn   aucun marqueur : le port ne depend pas du serveur
#:
#: Pour les deux premiers, le lieu choisi DECIDE donc si un port arrivera un
#: jour. Chez PIA, les 55 regions sans port forwarding sont les 55 regions des
#: Etats-Unis : un utilisateur qui choisit son propre pays n'obtient jamais rien,
#: sans le moindre message. C'est ce que `pf_values` sert a eviter.
PORT_FORWARD = {
    "private internet access",
    "protonvpn",
    "perfect privacy",
    "privatevpn",
}

#: Variable d'environnement Gluetun correspondant a chaque champ, et son libelle.
#: Les trois noms sont releves dans `serverselection.go` de la version epinglee.
VARIABLE = {"country": "SERVER_COUNTRIES", "region": "SERVER_REGIONS", "city": "SERVER_CITIES"}
LIBELLE = {"country": "pays", "region": "regions", "city": "villes"}
ALIAS = {"pia": "private internet access"}


def format_servers(provider: str) -> list[dict]:
    """Demande a l'image ce qu'elle connait pour ce fournisseur."""
    drapeau = "-" + provider.replace(" ", "-")
    commande = [
        "docker", "run", "--rm", "--entrypoint", "sh",
        f"qmcgaw/gluetun:{GLUETUN_TAG}",
        "-c", f"/gluetun-entrypoint format-servers {drapeau} -format json",
    ]
    # MSYS_NO_PATHCONV : sous Git Bash, `/gluetun-entrypoint` serait reecrit en
    # chemin Windows avant d'atteindre Docker.
    proc = subprocess.run(
        commande, capture_output=True, text=True, timeout=300, check=False,
        env={"MSYS_NO_PATHCONV": "1", "PATH": os.environ.get("PATH", "")},
    )
    if proc.returncode != 0:
        raise SystemExit(f"format-servers a echoue pour {provider} : {proc.stderr[:300]}")
    # La sortie est une LISTE de serveurs, chacun portant son pays. Verifie
    # contre l'image : pas d'enveloppe, pas de cle « servers ».
    return json.loads(proc.stdout)


def main() -> None:
    par_fournisseur: dict[str, list[str]] = {}
    reels = [p for p in VPN_PROVIDERS if p not in SANS_LISTE and p not in ALIAS]

    for provider in reels:
        serveurs = format_servers(provider)
        # `country` d'abord, `region` en repli : c'est ce que le fournisseur
        # renseigne qui decide, pas une preference de notre part.
        for champ in ("country", "region", "city"):
            valeurs = sorted({s[champ] for s in serveurs if s.get(champ)})
            if valeurs:
                break
        entree = {"env": VARIABLE[champ], "values": valeurs}

        # Le lieu qui permet REELLEMENT un port entrant, quand l'image le dit
        # serveur par serveur. On n'ecrit `pf_values` que s'il RESTREINT quelque
        # chose : une copie de `values` doublerait le fichier sans rien apprendre.
        if provider in PORT_FORWARD:
            entree["port_forward"] = True
            avec_pf = sorted({s[champ] for s in serveurs if s.get("port_forward") and s.get(champ)})
            if avec_pf and avec_pf != valeurs:
                entree["pf_values"] = avec_pf
        par_fournisseur[provider] = entree

        marque = ""
        if provider in PORT_FORWARD:
            restreint = entree.get("pf_values")
            marque = f"  port entrant : {len(restreint)}/{len(valeurs)}" if restreint else "  port entrant"
        print(
            f"  {provider:26} {len(valeurs):3} {LIBELLE[champ]:10} "
            f"({len(serveurs):5} serveurs){marque}"
        )

    for alias, cible in ALIAS.items():
        if cible in par_fournisseur:
            par_fournisseur[alias] = par_fournisseur[cible]
            print(f"  {alias:26} alias de {cible}")

    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    contenu = {"gluetun": GLUETUN_TAG, "providers": par_fournisseur}
    with SORTIE.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(contenu, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    total = sum(len(v["values"]) for v in par_fournisseur.values())
    print(f"\n{SORTIE.relative_to(ROOT)} : {len(par_fournisseur)} fournisseurs, {total} entrees")


if __name__ == "__main__":
    print(f"Extraction depuis qmcgaw/gluetun:{GLUETUN_TAG} :")
    main()
