"""Configuration reduite, pour la veille qui tourne en conteneur.

`stack.yml` porte TOUT : la cle privee WireGuard, les identifiants OpenVPN,
les cles API de chaque service et l'empreinte du mot de passe de la console.
Il est donc ecrit en 600 pour le compte qui installe, root sur un NAS. La
veille, elle, tourne sous PUID:PGID et ne peut pas le lire — constate le
2026-09-20 en lancant l'image publiee sur le banc : `PermissionError`.

Trois sorties possibles, et une seule bonne. Ouvrir le vrai fichier au groupe
donnerait la cle du tunnel a qui lit les debits. Faire tourner ce conteneur en
root donnerait tous les droits a une page qui ne fait que regarder. PlugArr
ecrit donc ICI une version REDUITE, dans `CONFIG_ROOT/veille/`, appartenant a
PUID:PGID, avec seulement ce dont la veille se sert :

- les services, l'hote et les ports, pour les joindre ;
- les identifiants des trois clients de telechargement, pour lire les debits ;
- l'empreinte du mot de passe de la console, pour sa propre page de connexion ;
- les racines, pour la place libre ;
- l'existence du VPN, pour savoir que qBittorrent se joint par `gluetun`.

Ce qu'elle n'a jamais a connaitre en est retire : la cle privee WireGuard, les
identifiants OpenVPN, et les cles API des services dont elle ne lit que
l'etat — une reponse HTTP sous 500 suffit, sans cle.

L'ADMINISTRATION, elle, est un autre role : elle montre les identifiants, fait
tourner les cles et recree des conteneurs. Elle lit le vrai `stack.yml`, sur
l'hote ou dans un conteneur declare pour cela. Aucune reduction n'a de sens
la : administrer, c'est pouvoir.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from .layout import _donner
from .models import StackConfig

DOSSIER = "veille"
FICHIER = "stack.yml"

#: Les seuls services dont la veille lit autre chose qu'un code HTTP : elle
#: interroge leur API pour les debits, et cela demande leurs identifiants.
CLIENTS = ("qbittorrent", "transmission", "sabnzbd")


def chemin(cfg: StackConfig) -> Path:
    return Path(cfg.config_path(DOSSIER)) / FICHIER


def reduire(cfg: StackConfig) -> StackConfig:
    """Copie de la configuration sans les secrets que la veille n'utilise pas."""
    reduit = cfg.model_copy(deep=True)
    reduit.vpn.wireguard_private_key = ""
    reduit.vpn.wireguard_addresses = ""
    reduit.vpn.openvpn_user = ""
    reduit.vpn.openvpn_password = ""
    for sid, instance in reduit.services.items():
        if sid in CLIENTS:
            continue
        instance.api_key = None
        instance.username = None
        instance.password = None
        instance.secret_key = ""
    return reduit


def ecrire(cfg: StackConfig) -> Path:
    """Ecrit la configuration reduite et la donne a PUID:PGID.

    Le fichier reste en 600 : le compte qui fait tourner la veille le lit, et
    personne d'autre. Reecrit a chaque semis, comme `stack.yml` lui-meme, pour
    qu'un port change ou un mot de passe tourne y arrive aussi.
    """
    cible = chemin(cfg)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(
        "# Genere par plugarr pour la veille en conteneur - NE PAS EDITER.\n"
        "# Version reduite de stack.yml : sans la cle du VPN ni les cles API\n"
        "# des services dont la veille ne lit que l'etat.\n"
        + yaml.safe_dump(reduire(cfg).model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    if os.name == "posix":
        cible.chmod(0o600)
    _donner(cible.parent, (cfg.puid, cfg.pgid))
    return cible
