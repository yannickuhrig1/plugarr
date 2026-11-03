"""Authentification de la page d'administration.

Cette page arrete des conteneurs, affiche des mots de passe et en change. Le
jeton tire au hasard a chaque demarrage convient tant qu'on lance `plugarr
serve` a la main : il s'affiche dans le terminal, juste au-dessus de l'URL.

Il ne convient PLUS des que la console tourne en permanence. Personne ne va lire
un journal de conteneur pour retrouver un jeton a chaque redemarrage, et un
jeton qui vit dans l'URL finit dans l'historique du navigateur.

D'ou un mot de passe, stocke **hache** dans `stack.yml` — jamais en clair, parce
que ce fichier est celui qu'on ouvre pour retrouver un port. PBKDF2-HMAC-SHA256,
600 000 iterations, sel de 16 octets : le parametre recommande par l'OWASP pour
cet algorithme, et c'est la seule raison de ce chiffre.

Le jeton reste accepte en parallele. Un utilisateur qui lance la console depuis
son terminal ne doit pas avoir a inventer un mot de passe pour regarder l'etat
de ses services.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import math
import secrets
import threading
import time

ALGO = "pbkdf2-sha256"
ITERATIONS = 600_000
SALT_BYTES = 16

#: Duree de vie d'une session. Assez longue pour ne pas gener une soiree de
#: reglages, assez courte pour qu'un navigateur oublie ne reste pas ouvert.
SESSION_SECONDS = 12 * 3600

#: Essais permis par adresse pendant `LOCKOUT_SECONDS`. La console est jointe par
#: le reseau local des qu'on la sort de 127.0.0.1 : sans cela, un mot de passe se
#: devine en quelques heures.
#:
#: Par adresse et non en tout : avec un seul compteur, n'importe quel appareil du
#: reseau bloquait aussi l'administrateur, en dix essais.
MAX_ATTEMPTS = 10
#: Essais permis toutes adresses confondues, pendant la meme duree. Seule, la
#: limite par adresse se multiplierait par le nombre d'adresses. Ce plafond borne
#: aussi la memoire : une fois atteint, plus rien n'est note.
MAX_ATTEMPTS_TOTAL = 50
LOCKOUT_SECONDS = 300


def hash_password(password: str) -> str:
    """Empreinte stockable. Format : `pbkdf2-sha256$<iters>$<sel>$<empreinte>`."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return "$".join(
        [ALGO, str(ITERATIONS), base64.b64encode(salt).decode(), base64.b64encode(digest).decode()]
    )


def verify_password(password: str, stored: str) -> bool:
    """Le mot de passe correspond-il a l'empreinte ?

    Toute empreinte mal formee renvoie False plutot que de lever : une
    `stack.yml` modifiee a la main ne doit pas empecher la console de repondre,
    elle doit empecher d'entrer.
    """
    try:
        algo, iterations, salt, digest = stored.split("$")
        if algo != ALGO:
            return False
        candidat = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), base64.b64decode(salt), int(iterations)
        )
    except (ValueError, TypeError):
        return False
    # compare_digest : une comparaison naive fuite l'empreinte octet par octet.
    return hmac.compare_digest(candidat, base64.b64decode(digest))


class Sessions:
    """Sessions en memoire, avec limitation des tentatives par adresse.

    En memoire et non sur disque, volontairement : redemarrer la console doit
    deconnecter tout le monde. C'est le comportement qu'on attend d'un outil
    d'administration, et cela evite d'avoir a expirer des jetons persistes.

    Sous verrou : la console sert chaque requete dans son propre fil.
    """

    def __init__(self, *, now=time.monotonic) -> None:
        self._now = now
        self._lock = threading.Lock()
        self._sessions: dict[str, float] = {}
        self._failures: dict[str, list[float]] = {}

    # -- tentatives ----------------------------------------------------------

    def _attente(self, ip: str) -> int:
        """Secondes avant le prochain essai permis a `ip`. 0 s'il l'est deja."""
        maintenant = self._now()
        self._failures = {
            adresse: recents
            for adresse, essais in self._failures.items()
            if (recents := [t for t in essais if maintenant - t < LOCKOUT_SECONDS])
        }
        tous = [t for essais in self._failures.values() for t in essais]
        attente = 0.0
        for essais, plafond in (
            (self._failures.get(ip, []), MAX_ATTEMPTS),
            (tous, MAX_ATTEMPTS_TOTAL),
        ):
            if len(essais) >= plafond:
                # Une place se libere quand le plus ancien essai expire.
                attente = max(attente, LOCKOUT_SECONDS - (maintenant - min(essais)))
        # `ceil` : 0 veut dire « permis », pas « moins d'une seconde ».
        return math.ceil(attente)

    def reserve_attempt(self, ip: str) -> bool:
        """Compte un essai AVANT de verifier le mot de passe. False s'il est refuse.

        Compter apres l'echec laissait passer les rafales : le hachage prend une
        fraction de seconde, et les requetes paralleles franchissaient toutes le
        controle avant que la premiere ne soit notee. Mesure le 2026-11-03 : 22
        essais verifies sur 40 envoyes ensemble, pour une limite de dix.
        """
        with self._lock:
            if self._attente(ip):
                return False
            self._failures.setdefault(ip, []).append(self._now())
            return True

    def clear_failures(self, ip: str) -> None:
        with self._lock:
            self._failures.pop(ip, None)

    def retry_in(self, ip: str) -> int:
        """Secondes restantes avant une nouvelle tentative. 0 si aucune attente."""
        with self._lock:
            return self._attente(ip)

    # -- sessions ------------------------------------------------------------

    def open(self) -> str:
        jeton = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[jeton] = self._now() + SESSION_SECONDS
        return jeton

    def valid(self, jeton: str) -> bool:
        if not jeton:
            return False
        with self._lock:
            expiration = self._sessions.get(jeton)
            if expiration is None:
                return False
            if self._now() > expiration:
                del self._sessions[jeton]
                return False
            return True

    def close(self, jeton: str) -> None:
        with self._lock:
            self._sessions.pop(jeton, None)
