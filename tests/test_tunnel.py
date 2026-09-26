"""Le tunnel relaie vraiment les octets, dans les deux sens.

Le transport SSH est remplace par un faux dont `open_channel` ouvre une vraie
connexion TCP vers un serveur d'echo local : le tunnel, lui, est le vrai.
"""

from __future__ import annotations

import socket
import threading

import pytest

from plugarr.tunnel import Tunnel


class _Echo:
    def __init__(self):
        self.ecoute = socket.socket()
        self.ecoute.bind(("127.0.0.1", 0))
        self.ecoute.listen(4)
        self.port = self.ecoute.getsockname()[1]
        threading.Thread(target=self._servir, daemon=True).start()

    def _servir(self):
        while True:
            try:
                client, _ = self.ecoute.accept()
            except OSError:
                return
            threading.Thread(target=self._repeter, args=(client,), daemon=True).start()

    @staticmethod
    def _repeter(client):
        with client:
            while donnees := client.recv(4096):
                client.sendall(donnees.upper())


class _Transport:
    def __init__(self, port_echo: int):
        self.port_echo = port_echo
        self.demandes: list[tuple] = []

    def is_active(self):
        return True

    def open_channel(self, genre, destination, origine, timeout=None):
        self.demandes.append((genre, destination))
        return socket.create_connection(("127.0.0.1", self.port_echo), timeout=5)


def test_le_tunnel_relaie_dans_les_deux_sens():
    echo = _Echo()
    transport = _Transport(echo.port)
    tunnel = Tunnel(transport, 7373)
    try:
        with socket.create_connection(("127.0.0.1", tunnel.port), timeout=5) as client:
            client.sendall(b"console plugarr")
            assert client.recv(4096) == b"CONSOLE PLUGARR"
        assert transport.demandes == [("direct-tcpip", ("127.0.0.1", 7373))]
    finally:
        tunnel.fermer()


def test_le_tunnel_n_ecoute_que_sur_la_boucle_locale():
    tunnel = Tunnel(_Transport(1), 7373)
    try:
        assert tunnel._ecoute.getsockname()[0] == "127.0.0.1"
    finally:
        tunnel.fermer()


def test_un_port_distant_absurde_est_refuse():
    with pytest.raises(ValueError):
        Tunnel(_Transport(1), 0)


def test_un_refus_du_serveur_ferme_la_connexion_sans_planter():
    class Refus(_Transport):
        def open_channel(self, *args, **kwargs):
            raise OSError("administratively prohibited")

    tunnel = Tunnel(Refus(1), 7373)
    try:
        with socket.create_connection(("127.0.0.1", tunnel.port), timeout=5) as client:
            client.settimeout(5)
            assert client.recv(10) == b""
    finally:
        tunnel.fermer()
