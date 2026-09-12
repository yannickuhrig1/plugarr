"""Client SABnzbd : disponibilite et categories.

SABnzbd n'a ni identifiant ni mot de passe : **sa cle API tient lieu des deux**.
Toute son API vit sur une seule route, `/api`, ou le verbe est un parametre
`mode` — c'est une API de 2008, et elle n'a pas change.

Deux pieges releves contre la 5.1.2, et le premier fait perdre une soiree.

**La liste blanche d'hotes.** SABnzbd refuse toute requete dont l'en-tete `Host`
ne figure pas dans `host_whitelist`, et n'y met par defaut QUE l'identifiant de
son conteneur. Sonarr appelant `http://sabnzbd:8085` recoit :

    Access denied - Hostname verification failed

Le message ne nomme ni l'appelant, ni le reglage en cause, et renvoie vers une
page d'aide generale. C'est `seed.seed_sabnzbd` qui l'evite, en posant les noms
d'avance.

**Les categories portent le repertoire.** C'est par elles que les
telechargements de Sonarr atterrissent dans `/data/usenet/tv` : les *arr
n'envoient qu'un nom de categorie, jamais un chemin.
"""

from __future__ import annotations

from typing import Any, Self

import httpx

from ..i18n import t
from .base import WiringError, new_client, wait_until

#: Priorite « par defaut » de SABnzbd. -100 signifie « celle de la categorie »,
#: releve dans sa reponse : poser autre chose surclasserait le reglage global
#: sans que personne ne l'ait demande.
PRIORITE_DEFAUT = -100


class SabnzbdClient:
    def __init__(self, base_url: str, api_key: str, *, name: str = "sabnzbd"):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._http = new_client(self.base_url)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- primitives ----------------------------------------------------------

    def _call(self, mode: str, **params: Any) -> Any:
        """Toute l'API tient sur `/api`, le verbe etant le parametre `mode`."""
        requete = {"mode": mode, "apikey": self._api_key, "output": "json", **params}
        try:
            resp = self._http.get("/api", params=requete)
        except httpx.HTTPError as exc:
            raise WiringError(
                f"{self.name}: appel {mode} impossible",
                str(exc),
                f"verifiez que {self.base_url} repond",
            ) from exc
        if resp.status_code >= 400:
            raise WiringError(
                f"{self.name}: {mode} a echoue",
                f"HTTP {resp.status_code} - {resp.text[:200]}",
                t("la cle API est-elle la bonne ?"),
            )
        texte = resp.text.strip()
        if texte.startswith("Access denied"):
            # Reponse en 200 avec un corps d'erreur : sans ce controle, elle
            # passerait pour un succes.
            raise WiringError(
                f"{self.name}: acces refuse",
                texte[:200],
                t("le nom d'hote appelant est-il dans host_whitelist ?"),
            )
        try:
            return resp.json()
        except ValueError:
            return texte

    # -- disponibilite -------------------------------------------------------

    def wait_ready(self, timeout: float = 300.0) -> None:
        def probe() -> bool:
            try:
                return bool((self._call("version") or {}).get("version"))
            except WiringError:
                return False

        result = wait_until(probe, label=self.name, timeout=timeout)
        if not result.ready:
            raise WiringError(
                t("{service} n'est jamais devenu disponible", service="SABnzbd"),
                result.detail,
                "inspectez `docker logs plugarr-sabnzbd`",
            )

    @property
    def version(self) -> str:
        return str((self._call("version") or {}).get("version", "?"))

    # -- categories ----------------------------------------------------------

    def categories(self) -> dict[str, str]:
        """Categories existantes, nom -> repertoire."""
        config = (self._call("get_config", section="categories") or {}).get("config") or {}
        return {c["name"]: c.get("dir", "") for c in config.get("categories") or []}

    def ensure_category(self, nom: str, repertoire: str) -> bool:
        """Pose la categorie et son repertoire. Renvoie True si quelque chose a
        change.

        **« Creer si absente » ne suffit pas ici**, et c'est le second piege.
        SABnzbd livre des categories d'usine — `movies`, `tv`, `audio`,
        `software` — toutes avec un repertoire VIDE. Se contenter de tester la
        presence du nom les laisse telles quelles : la categorie existe, Sonarr
        l'accepte, et les telechargements atterrissent dans le repertoire par
        defaut au lieu de `/data/usenet/tv`. Rien ne le signale.

        La regle exacte : on remplit le repertoire quand il est VIDE, jamais
        quand il porte deja une valeur. Un repertoire vide est un defaut
        d'usine ; un repertoire renseigne est une decision, et on n'ecrase pas
        les decisions de quelqu'un.
        """
        existantes = self.categories()
        if existantes.get(nom):
            return False
        self._call(
            "set_config",
            section="categories",
            keyword=nom,
            dir=repertoire,
            priority=PRIORITE_DEFAUT,
        )
        # On RELIT : `set_config` repond 200 avec la configuration meme quand
        # elle n'a pas change.
        return self.categories().get(nom) == repertoire
