"""Garder un secret SSH pour une installation distante, si on le demande.

Par defaut, rien n'est garde : le mot de passe ou la cle sont redemandes a
chaque connexion, comme dans l'assistant. C'est la regle du projet, et ce
module ne la change pas. Il ajoute un choix explicite, « se souvenir », pour
qui administre un serveur tous les jours.

**Chiffrement par Windows, pour ce compte.** DPAPI (`CryptProtectData`) chiffre
avec une cle derivee de la session Windows : le fichier ne se dechiffre que
sous le meme compte, sur la meme machine. Copie ailleurs, ou lu par un autre
utilisateur, il ne sert a rien. PlugArr n'a aucune cle a gerer ni a cacher.

Pourquoi pas le Gestionnaire d'identifiants de Windows : il limite un secret a
2 560 octets, et une cle privee RSA de 4 096 bits en fait plus de 3 000 en PEM.
Tronquer une cle ne se voit qu'au moment ou elle ne marche plus.

Hors de Windows, `disponible()` est faux et le gestionnaire n'offre pas le
choix. Un secret en clair dans un fichier n'est pas une option.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

from . import registre

DOSSIER = "coffre"

#: Liee a PlugArr : un autre programme du meme compte qui appellerait DPAPI sur
#: ce fichier sans elle n'obtiendrait rien.
_ENTROPIE = b"PlugArr/coffre-ssh/1"

#: Ce que le coffre accepte de garder, et rien d'autre.
CHAMPS = ("password", "private_key", "passphrase", "sudo_password")


class CoffreIndisponible(RuntimeError):
    pass


def disponible() -> bool:
    return sys.platform == "win32"


def _fichier(ident: str) -> Path:
    if not re.fullmatch(r"[a-z0-9-]{4,40}", ident):
        raise ValueError("Identifiant d'installation invalide.")
    return registre.dossier() / DOSSIER / f"{ident}.bin"


def _dpapi(donnees: bytes, *, chiffrer: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(octets: bytes):
        tampon = ctypes.create_string_buffer(octets, len(octets))
        return DATA_BLOB(len(octets), ctypes.cast(tampon, ctypes.POINTER(ctypes.c_char))), tampon

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    fonction = crypt32.CryptProtectData if chiffrer else crypt32.CryptUnprotectData
    fonction.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    fonction.restype = wintypes.BOOL

    entree, _garde_entree = blob(donnees)
    entropie, _garde_entropie = blob(_ENTROPIE)
    sortie = DATA_BLOB()
    # 0x1 : CRYPTPROTECT_UI_FORBIDDEN. Jamais de fenetre de Windows surgie au
    # milieu d'une connexion ; un echec vaut mieux.
    if not fonction(
        ctypes.byref(entree), None, ctypes.byref(entropie), None, None, 0x1, ctypes.byref(sortie)
    ):
        raise OSError(ctypes.get_last_error(), "DPAPI a refuse l'operation")
    try:
        return ctypes.string_at(sortie.pbData, sortie.cbData)
    finally:
        kernel32.LocalFree(sortie.pbData)


def garder(ident: str, secrets: dict[str, str]) -> None:
    if not disponible():
        raise CoffreIndisponible("Le coffre n'existe que sous Windows.")
    retenus = {cle: str(valeur) for cle, valeur in secrets.items() if cle in CHAMPS and valeur}
    if not retenus:
        oublier(ident)
        return
    chiffre = _dpapi(json.dumps(retenus).encode("utf-8"), chiffrer=True)
    fichier = _fichier(ident)
    fichier.parent.mkdir(parents=True, exist_ok=True)
    temporaire = fichier.with_suffix(".tmp")
    temporaire.write_bytes(chiffre)
    os.replace(temporaire, fichier)


def lire(ident: str) -> dict[str, str]:
    """Les secrets gardes pour cette installation, ou un dictionnaire vide.

    Un fichier qui ne se dechiffre pas (autre compte, autre machine, fichier
    abime) vaut « rien de garde » : on redemande, on ne plante pas.
    """
    if not disponible():
        return {}
    try:
        chiffre = _fichier(ident).read_bytes()
    except (OSError, ValueError):
        return {}
    try:
        valeurs = json.loads(_dpapi(chiffre, chiffrer=False).decode("utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(valeurs, dict):
        return {}
    return {cle: str(v) for cle, v in valeurs.items() if cle in CHAMPS and isinstance(v, str)}


def garde(ident: str) -> bool:
    try:
        return _fichier(ident).is_file()
    except (OSError, ValueError):
        return False


def oublier(ident: str) -> None:
    try:
        _fichier(ident).unlink(missing_ok=True)
    except (OSError, ValueError):
        return
