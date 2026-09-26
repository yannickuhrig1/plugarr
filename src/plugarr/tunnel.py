"""Un port de ce poste qui mene a un port du serveur, a travers SSH.

La console d'une installation distante ecoute sur le serveur. La joindre
demandait de taper `ssh -L 17373:127.0.0.1:7373 ...` dans un terminal, puis
d'ouvrir l'adresse a la main : une etape que personne ne retient, et qui exige
un client SSH en ligne de commande.

Le gestionnaire ouvre ce tunnel lui-meme, dans la session SSH qu'il a deja :
un port local tire au hasard sur 127.0.0.1, et chaque connexion entrante est
relayee par un canal `direct-tcpip` vers l'adresse du serveur. Rien n'ecoute
sur le reseau du poste, et rien n'est ouvert sur le serveur.

Deux fils par connexion plutot qu'un `select` : un canal Paramiko n'est pas un
socket, et son comportement sous `select` differe selon les systemes. Deux
lectures bloquantes marchent partout de la meme facon.
"""

from __future__ import annotations

import socket
import threading


class Tunnel:
    """Relaie `127.0.0.1:<port>` vers `hote:port_distant`, vu depuis le serveur."""

    def __init__(self, transport, port_distant: int, hote_distant: str = "127.0.0.1"):
        if not 1 <= int(port_distant) <= 65535:
            raise ValueError("Port distant invalide.")
        self.transport = transport
        self.hote_distant = hote_distant
        self.port_distant = int(port_distant)
        self._arret = threading.Event()
        self._ecoute = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._ecoute.bind(("127.0.0.1", 0))
        self._ecoute.listen(16)
        self._ecoute.settimeout(0.5)
        self.port = self._ecoute.getsockname()[1]
        self._fil = threading.Thread(target=self._accepter, name="tunnel-ssh", daemon=True)
        self._fil.start()

    @property
    def actif(self) -> bool:
        return not self._arret.is_set() and bool(self.transport and self.transport.is_active())

    def _accepter(self) -> None:
        while not self._arret.is_set():
            try:
                client, adresse = self._ecoute.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            threading.Thread(
                target=self._ouvrir, args=(client, adresse), name="tunnel-canal", daemon=True
            ).start()

    def _ouvrir(self, client: socket.socket, adresse) -> None:
        try:
            canal = self.transport.open_channel(
                "direct-tcpip", (self.hote_distant, self.port_distant), adresse, timeout=10
            )
        except Exception:  # noqa: BLE001 - le serveur refuse : on ferme, le navigateur le dira
            client.close()
            return
        threading.Thread(
            target=_copier, args=(canal, client), name="tunnel-retour", daemon=True
        ).start()
        _copier(client, canal)

    def fermer(self) -> None:
        self._arret.set()
        try:
            self._ecoute.close()
        except OSError:
            pass


def _copier(source, destination) -> None:
    """Recopie jusqu'a la fin de l'un des deux cotes, puis ferme les deux."""
    try:
        while True:
            donnees = source.recv(65536)
            if not donnees:
                break
            destination.sendall(donnees)
    except (OSError, EOFError):
        pass
    finally:
        for bout in (source, destination):
            try:
                bout.close()
            except OSError:
                pass
