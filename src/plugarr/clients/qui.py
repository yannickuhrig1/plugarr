"""Client qui.

qui est une interface web moderne pour qBittorrent, du meme auteur qu'autobrr.
Elle sait piloter plusieurs instances, et n'a d'interet que reliee a au moins une.

Tout ce qui suit a ete releve sur v1.27.0, pas suppose :

- **tout repond 428** tant que le premier compte n'existe pas, y compris la page
  de connexion. C'est le signal « installation a terminer » ;
- le point d'entree de cette premiere creation est `POST /api/auth/setup`, et il
  repond **400 « Setup already completed »** une fois joue. C'est ce qui rend
  l'etape rejouable ;
- une instance se declare avec son **URL complete**. Passer `host` et `port`
  separement est accepte avec un 201 rassurant, mais le port est perdu : qui
  enregistre `http://qbittorrent` et la connexion ne s'etablit jamais ;
- **les doublons ne sont pas refuses**. Declarer deux fois la meme instance donne
  deux entrees. C'est a l'appelant de verifier avant d'ecrire ;
- `GET /api/instances` expose `connected` et `connectionStatus` : de quoi
  verifier le lien aupres de qui lui-meme, plutot que de croire le 201.
"""

from __future__ import annotations

from typing import Any, Self

import httpx

from ..i18n import t
from .base import WiringError, new_client, wait_until


class QuiClient:
    def __init__(self, base_url: str, *, name: str = "qui"):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self._http = new_client(self.base_url)
        # qui v1.30.0 refuse toute ecriture authentifiee par cookie sans cet
        # en-tete (HTTP 403 « Missing X-Requested-With header », garde anti-CSRF
        # de internal/api/middleware/auth.go). Sans effet sur les versions
        # precedentes. Constate a l'installation reelle du 26/09/2026.
        self._http.headers["X-Requested-With"] = "XMLHttpRequest"

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- primitives ----------------------------------------------------------

    def _request(self, method: str, path: str, **kw: Any) -> httpx.Response:
        try:
            return self._http.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise WiringError(
                f"{self.name}: appel {method} {path} impossible",
                str(exc),
                f"verifiez que {self.base_url} repond",
            ) from exc

    # -- disponibilite -------------------------------------------------------

    def wait_ready(self, timeout: float = 120.0) -> None:
        """Attend que le serveur reponde, quelle que soit sa reponse.

        Toute reponse HTTP prouve que le service ecoute. Enumerer les codes
        acceptables etait une erreur : la liste (200, 401, 428) ne contenait pas
        **403**, que qui renvoie des qu'un compte existe. Sur une stack deja
        installee, l'attente allait donc jusqu'au bout du delai puis declarait
        « qui n'est jamais devenu disponible » — alors que le conteneur etait
        demarre, sain, et repondait en quelques millisecondes.

        Une erreur de connexion, elle, leve : c'est `wait_until` qui la rattrape.
        """

        def probe() -> bool:
            self._request("GET", "/api/auth/me")
            return True

        result = wait_until(probe, label=self.name, timeout=timeout)
        if not result.ready:
            raise WiringError(
                t("{service} n'est jamais devenu disponible", service="qui"),
                result.detail,
                "inspectez `docker logs qui`",
            )

    # -- premier compte ------------------------------------------------------

    def setup(self, username: str, password: str) -> bool:
        """Cree le compte initial. Renvoie False s'il existait deja."""
        resp = self._request(
            "POST", "/api/auth/setup", json={"username": username, "password": password}
        )
        if resp.status_code in (200, 201):
            return True
        if resp.status_code == 400 and "already" in resp.text.lower():
            return False
        raise WiringError(
            t("qui : creation du compte initial impossible"),
            f"HTTP {resp.status_code} - {resp.text[:300]}",
            t("l'API de qui a peut-etre change de forme"),
        )

    def login(self, username: str, password: str) -> None:
        resp = self._request(
            "POST", "/api/auth/login", json={"username": username, "password": password}
        )
        if resp.status_code not in (200, 204):
            raise WiringError(
                "qui: connexion refusee",
                f"HTTP {resp.status_code} - {resp.text[:200]}",
                t("le mot de passe enregistre ne correspond pas au compte existant"),
            )

    # -- instances -----------------------------------------------------------

    def instances(self) -> list[dict]:
        resp = self._request("GET", "/api/instances")
        return resp.json() if resp.status_code == 200 else []

    @staticmethod
    def _same_host(left: str, right: str) -> bool:
        return left.rstrip("/") == right.rstrip("/")

    def ensure_instance(self, *, name: str, host: str, username: str, password: str) -> bool:
        """Declare une instance qBittorrent. Renvoie False si elle existait deja.

        qui n'interdit pas les doublons : sans cette verification, chaque passage
        de `plugarr wire` ajouterait une entree de plus.

        Une instance existante est REALIGNEE, pas seulement reconnue. Essai reel
        du 25/09/2026 : le mot de passe de qBittorrent avait change et le VPN
        avait ete retire puis remis ; qui gardait l'ancien mot de passe, avait
        cree une seconde instance a la nouvelle adresse, et aucune ne se
        connectait. On la retrouve par son adresse, sinon par le nom que PlugArr
        lui donne, et on lui renvoie adresse et identifiants actuels.
        """
        existantes = self.instances()
        existante = next(
            (i for i in existantes if self._same_host(i.get("host", ""), host)), None
        ) or next((i for i in existantes if i.get("name") == name), None)
        if existante is not None:
            if existante.get("id") is not None:
                self._update_instance(existante["id"], name=existante.get("name") or name,
                                      host=host, username=username, password=password)
            return False

        resp = self._request(
            "POST",
            "/api/instances",
            json={"name": name, "host": host, "username": username, "password": password},
        )
        if resp.status_code not in (200, 201):
            raise WiringError(
                "qui: declaration de l'instance qBittorrent impossible",
                f"HTTP {resp.status_code} - {resp.text[:300]}",
                t("verifiez que qBittorrent est demarre"),
            )
        return True

    def _update_instance(self, instance_id, *, name: str, host: str, username: str, password: str) -> None:
        # qui v1.28.0 : PUT /api/instances/{id}, `name` et `host` obligatoires,
        # les autres reglages absents du corps sont conserves.
        resp = self._request(
            "PUT",
            f"/api/instances/{instance_id}",
            json={"name": name, "host": host, "username": username, "password": password},
        )
        if resp.status_code not in (200, 204):
            raise WiringError(
                "qui: mise a jour de l'instance qBittorrent impossible",
                f"HTTP {resp.status_code} - {resp.text[:300]}",
                t("verifiez que qBittorrent est demarre"),
            )

    def connected(self, host: str, timeout: float = 60.0) -> tuple[bool, str]:
        """La connexion est-elle etablie, selon qui lui-meme ?

        L'etat n'est pas immediat apres la creation : qui doit d'abord ouvrir une
        session vers qBittorrent. On laisse le temps de s'etablir plutot que de
        conclure trop tot.
        """
        state = {"detail": t("aucune instance a cette adresse"), "teste": False}

        def probe() -> bool:
            for inst in self.instances():
                if not self._same_host(inst.get("host", ""), host):
                    continue
                status = inst.get("connectionStatus") or "inconnu"
                state["detail"] = f"etat {status}"
                if inst.get("connected"):
                    return True
                # Essai reel du 25/09/2026 : apres des echecs, qui met l'instance
                # en attente (backoff) et son etat ne bouge plus pendant une
                # minute, meme une fois les identifiants corriges. Son test
                # explicite, lui, repond tout de suite et met l'etat a jour.
                if not state["teste"] and inst.get("id") is not None:
                    state["teste"] = True
                    resp = self._request("POST", f"/api/instances/{inst['id']}/test")
                    if resp.status_code == 200:
                        try:
                            verdict = resp.json()
                        except ValueError:
                            verdict = {}
                        if isinstance(verdict, dict) and verdict.get("connected"):
                            state["detail"] = "etat connecte (test explicite)"
                            return True
                return False
            return False

        result = wait_until(probe, label=self.name, timeout=timeout)
        return result.ready, state["detail"]
