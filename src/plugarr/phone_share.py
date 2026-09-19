"""Envoi d'un fichier au telephone par QR code.

Ni nzb360 ni qbRemote ne restaurent depuis un QR code, et un QR ne porte pas
plus de 2,9 Ko : le QR contient donc un LIEN. L'assistant n'ecoute que sur
127.0.0.1, que le telephone ne joint pas. Ce module ouvre, le temps d'un
envoi, un second serveur sur l'adresse de la machine dans le reseau local :

- une seule adresse servie, `/t/<jeton>`, jeton aleatoire de 192 bits ;
- un seul telechargement : le fichier est oublie des qu'il est servi ;
- dix minutes au plus, puis le serveur s'arrete de lui-meme ;
- rien d'autre : toute autre requete recoit 404, sans detail.

Le transfert se fait en HTTP sur le reseau local. Le fichier qbRemote reste
chiffre par son mot de passe ; celui de nzb360 ne l'est pas, comme lorsqu'il
est telecharge sur le PC.
"""

from __future__ import annotations

import hmac
import ipaddress
import re
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DUREE = 600
TAILLE_MAX = 1024 * 1024
NOM_FICHIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,118}\.zip")


class PartageTelephone:
    """Un fichier, un lien, un telechargement. Publier remplace le precedent."""

    def __init__(self, hote: str, *, duree: float = DUREE):
        self.hote = _adresse_locale(hote)
        self.duree = duree
        self._verrou = threading.Lock()
        self._serveur: ThreadingHTTPServer | None = None
        self._jeton = ""
        self._contenu: bytes | None = None
        self._nom = ""
        self._echeance = 0.0
        self._minuteur: threading.Timer | None = None

    def publier(self, contenu: bytes, nom: str) -> dict:
        if not NOM_FICHIER.fullmatch(nom):
            raise ValueError("Nom de fichier refuse.")
        if not 0 < len(contenu) <= TAILLE_MAX:
            raise ValueError("Taille de fichier refusee (1 Mo au plus).")
        self.arreter()
        partage = self

        class Gestionnaire(_Gestionnaire):
            servir = staticmethod(partage._servir)

        try:
            serveur = ThreadingHTTPServer((self.hote, 0), Gestionnaire)
        except OSError as exc:
            raise ValueError(
                f"Impossible d'ouvrir le lien sur {self.hote} : {exc.strerror or exc}."
            ) from exc
        serveur.daemon_threads = True
        with self._verrou:
            self._serveur = serveur
            self._jeton = secrets.token_urlsafe(24)
            self._contenu = contenu
            self._nom = nom
            self._echeance = time.monotonic() + self.duree
            jeton = self._jeton
            self._minuteur = threading.Timer(self.duree, self.arreter)
            self._minuteur.daemon = True
            self._minuteur.start()
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        hote = f"[{self.hote}]" if ":" in self.hote else self.hote
        return {
            "url": f"http://{hote}:{serveur.server_address[1]}/t/{jeton}",
            "expires_in": int(self.duree),
        }

    def _servir(self, jeton: str) -> tuple[bytes, str] | None:
        """Rend le fichier une seule fois, puis ferme le serveur."""
        with self._verrou:
            valide = (
                self._contenu is not None
                and time.monotonic() < self._echeance
                and hmac.compare_digest(jeton.encode(), self._jeton.encode())
            )
            if not valide:
                return None
            contenu, nom = self._contenu, self._nom
            self._contenu = None
        # shutdown() attend la fin de serve_forever : jamais depuis son fil.
        threading.Thread(target=self.arreter, daemon=True).start()
        return contenu, nom

    @property
    def actif(self) -> bool:
        with self._verrou:
            return self._serveur is not None

    def arreter(self) -> None:
        with self._verrou:
            serveur, self._serveur = self._serveur, None
            minuteur, self._minuteur = self._minuteur, None
            self._contenu = None
            self._jeton = ""
        if minuteur is not None and minuteur is not threading.current_thread():
            minuteur.cancel()
        if serveur is not None:
            serveur.shutdown()
            serveur.server_close()


class _Gestionnaire(BaseHTTPRequestHandler):
    servir = None  # remplace par PartageTelephone.publier

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *args):
        pass  # Jamais le jeton dans un journal.

    def do_GET(self):
        chemin = self.path.split("?", 1)[0]
        resultat = self.servir(chemin[3:]) if chemin.startswith("/t/") else None
        if resultat is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        contenu, nom = resultat
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", f'attachment; filename="{nom}"')
        self.send_header("Content-Length", str(len(contenu)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(contenu)

    def do_HEAD(self):
        # Un apercu de lien ne doit pas consommer l'unique telechargement.
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()


def _adresse_locale(hote: str) -> str:
    """Adresse IP privee de la machine : jamais localhost, jamais publique."""
    try:
        ip = ipaddress.ip_address(hote)
    except ValueError:
        try:
            ip = ipaddress.ip_address(socket.gethostbyname(hote))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Adresse du reseau local introuvable ({hote}).") from exc
    if ip.is_loopback or ip.is_unspecified or not ip.is_private:
        raise ValueError(
            f"{ip} n'est pas une adresse du reseau local : le telephone ne pourrait pas la joindre."
        )
    return str(ip)
