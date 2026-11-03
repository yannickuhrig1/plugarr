"""Client qBittorrent WebUI API v2.

Sert uniquement a creer les categories avec leur chemin de sauvegarde. Le reste du
cablage passe par les *arr, qui parlent directement a qBittorrent.
"""

from __future__ import annotations

import json
from typing import Self

import httpx

from ..i18n import t
from .base import WiringError, new_client, wait_until


class QBittorrentClient:
    def __init__(self, base_url: str, username: str, password: str, *, name: str = "qbittorrent"):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self._username, self._password = username, password
        self._http = new_client(self.base_url, headers={"Referer": self.base_url})
        self._authenticated = False

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- session -------------------------------------------------------------

    def login(self) -> bool:
        """Ouvre une session. Renvoie True si authentifie.

        qBittorrent 5.x repond 204 avec un cookie QBT_SID en cas de succes, et 200
        avec le corps "Fails." en cas d'echec. C'est donc la PRESENCE DU COOKIE qui
        fait foi, pas le code de retour. Verifie contre 5.2.3.
        """
        try:
            resp = self._http.post(
                "/api/v2/auth/login",
                data={"username": self._username, "password": self._password},
            )
        except httpx.HTTPError as exc:
            raise WiringError(
                f"{self.name}: connexion impossible",
                str(exc),
                f"verifiez que {self.base_url} repond",
            ) from exc
        if "Fails." in resp.text:
            raise WiringError(
                t("{service} : identifiants refuses", service=self.name),
                t('la WebUI a repondu "Fails."'),
                t(
                    "le qBittorrent.conf pre-seme a peut-etre ete ecrase. "
                    "Relancez `plugarr doctor`."
                ),
            )
        self._authenticated = any(c.startswith("QBT_SID") for c in self._http.cookies) or (
            resp.status_code in (200, 204)
        )
        return self._authenticated

    def wait_ready(self, timeout: float = 300.0) -> None:
        def probe() -> bool:
            return bool(self._http.get("/api/v2/app/version").text.strip())

        result = wait_until(probe, label=self.name, timeout=timeout)
        if not result.ready:
            raise WiringError(
                t("{service} n'est jamais devenu disponible", service="qBittorrent"),
                result.detail,
                "inspectez `docker logs qbittorrent`",
            )
        self.login()

    def _call(self, method: str, path: str, **kw) -> httpx.Response:
        """Envoie la requete, et rouvre la session une fois si elle est refusee.

        Une session qBittorrent expire et ne survit pas a un redemarrage du client.
        Le refus arrive en 403, ou en 200 avec "Forbidden" pour corps (voir
        `categories`). Une seule reprise : au-dela, c'est a l'appelant de le dire.
        """
        resp = self._http.request(method, path, **kw)
        if resp.status_code == 403 or resp.text.strip() == "Forbidden":
            self.login()
            resp = self._http.request(method, path, **kw)
        return resp

    @property
    def version(self) -> str:
        return self._call("GET", "/api/v2/app/version").text.strip()

    # -- categories ----------------------------------------------------------

    def categories(self) -> dict:
        resp = self._call("GET", "/api/v2/torrents/categories")
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError as exc:
            # Sur une session refusee, qBittorrent repond "Forbidden" en texte
            # brut avec un code 200. Sans ce garde-fou, l'appelant recevait une
            # JSONDecodeError nue au lieu d'un diagnostic.
            raise WiringError(
                t("qbittorrent : reponse illisible sur les categories"),
                f"contenu non JSON : {resp.text[:120]!r}",
                t("les identifiants sont probablement refuses"),
            ) from exc

    def ensure_category(self, name: str, save_path: str) -> bool:
        """Cree la categorie si absente. Renvoie True si creee.

        La categorie porte son chemin de sauvegarde : c'est ainsi que les
        telechargements de Sonarr atterrissent dans /data/torrents/tv sans que les
        *arr aient besoin de poser un repertoire explicite.
        """
        if name in self.categories():
            return False
        resp = self._call(
            "POST",
            "/api/v2/torrents/createCategory",
            data={"category": name, "savePath": save_path},
        )
        if resp.status_code >= 400:
            raise WiringError(
                t(
                    "{service} : creation de la categorie {categorie} refusee",
                    service=self.name,
                    categorie=repr(name),
                ),
                f"HTTP {resp.status_code} - {resp.text[:200]}",
                t("la session est-elle bien authentifiee ?"),
            )
        return True

    def preferences(self) -> dict:
        resp = self._call("GET", "/api/v2/app/preferences")
        if resp.status_code >= 400:
            raise WiringError(
                f"{self.name}: preferences illisibles",
                f"HTTP {resp.status_code}",
                t("la session est-elle bien authentifiee ?"),
            )
        return resp.json()

    def ensure_rss(self, *, refresh_minutes: int = 15) -> list[str]:
        """Allume le lecteur RSS et le telechargement automatique.

        Renvoie la liste des reglages REELLEMENT changes, vide si tout etait
        deja en place.

        qBittorrent livre le moteur RSS actif mais le telechargement
        automatique ETEINT : les regles qu'on ecrit ne se declenchent jamais, et
        rien ne le dit. Verifie contre 5.2.3, sur une instance installee par
        plugarr — `rss_processing_enabled: True`,
        `rss_auto_downloading_enabled: False`.

        `setPreferences` attend un JSON dans un champ de formulaire nomme
        `json` : ce n'est pas un corps JSON.

        plugarr n'ajoute AUCUN flux ni AUCUNE regle : ils dependent de vos
        traqueurs, exactement comme les indexeurs de Prowlarr. Il pose
        l'interrupteur, vous posez le contenu.
        """
        voulu = {
            "rss_processing_enabled": True,
            "rss_auto_downloading_enabled": True,
            "rss_refresh_interval": refresh_minutes,
        }
        actuel = self.preferences()
        change = {k: v for k, v in voulu.items() if actuel.get(k) != v}
        if not change:
            return []
        resp = self._call("POST", "/api/v2/app/setPreferences", data={"json": json.dumps(change)})
        if resp.status_code >= 400:
            raise WiringError(
                f"{self.name}: activation du RSS refusee",
                f"HTTP {resp.status_code} - {resp.text[:200]}",
                t("la version de qBittorrent expose-t-elle bien ces reglages ?"),
            )
        # On RELIT : `setPreferences` repond 200 meme pour un reglage inconnu,
        # qu'il ignore ensuite en silence.
        relu = self.preferences()
        return [k for k, v in change.items() if relu.get(k) == v]

    def set_password(self, password: str) -> None:
        """Change le mot de passe de la WebUI par l'API de qBittorrent.

        `setPreferences` attend un JSON dans un champ de formulaire nomme `json` :
        ce n'est pas un corps JSON. Verifie contre 5.2.3.

        Passer par l'API plutot que par `qBittorrent.conf` evite d'arreter le
        conteneur : qBittorrent garde sa configuration en memoire et reecrit le
        fichier a l'arret, donc une modification a chaud du fichier serait
        purement et simplement perdue.
        """
        resp = self._call(
            "POST",
            "/api/v2/app/setPreferences",
            data={"json": json.dumps({"web_ui_password": password})},
        )
        if resp.status_code >= 400:
            raise WiringError(
                f"{self.name}: changement de mot de passe refuse",
                f"HTTP {resp.status_code} - {resp.text[:200]}",
                t("la session est-elle bien authentifiee ?"),
            )
        self._password = password
