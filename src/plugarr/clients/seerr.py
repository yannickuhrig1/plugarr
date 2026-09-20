"""Client Seerr : accueil, connexion, declaration des *arr.

Seerr est le successeur commun de Jellyseerr et d'Overseerr, confirme par le
projet lui-meme. Son API en herite : elle est validee cote serveur contre une
specification OpenAPI livree DANS l'image, `/app/seerr-api.yml`. Les champs
ci-dessous en sont tires, pas devines — un champ manquant produit une reponse
nommant precisement la propriete absente, ce qui rend le contrat lisible sans
documentation externe.

L'accueil ne se fait PAS par un formulaire a nous. Il se fait en s'authentifiant
contre le serveur media, et la specification le dit noir sur blanc :

    Sign in using a Jellyfin username and password. If the user does not exist,
    and there are no other users, then a user will be created with full admin
    privileges.

Consequence de structure : **Seerr n'a pas de mot de passe a lui**. Son
administrateur EST le compte Jellyfin. PlugArr n'en genere donc aucun, et
l'annoncer serait mentir.

Ordre impose, releve a l'usage :

    POST /api/v1/auth/jellyfin        cree l'administrateur, ouvre la session
    POST /api/v1/settings/sonarr      declare les *arr
    POST /api/v1/settings/radarr
    POST /api/v1/settings/initialize  ferme l'accueil, EN DERNIER

Fermer l'accueil avant d'avoir declare les *arr laisse une instance qui se croit
prete et ne peut rien demander.
"""

from __future__ import annotations

from typing import Any, Self

import httpx

from ..i18n import t
from .base import WiringError, new_client, wait_until

#: `MediaServerType.JELLYFIN`, lu dans `dist/constants/server.js` de l'image.
#: Obligatoire malgre ce que dit la specification : sans lui, l'accueil repond
#: `NO_ADMIN_USER`, message qui envoie chercher un probleme de droits Jellyfin.
SERVEUR_JELLYFIN = 2

#: `minimumAvailability` de Radarr, transmis tel quel par Seerr. « released »
#: veut dire que le film est reellement sorti : les autres valeurs lancent des
#: recherches sur ce qui n'existe pas encore.
MINIMUM_DISPONIBILITE = "released"


class SeerrClient:
    def __init__(self, base_url: str, *, name: str = "seerr"):
        self.name = name
        self.base_url = base_url.rstrip("/")
        # La session vit dans un COOKIE, pas dans un en-tete : le client doit
        # donc conserver ses cookies d'un appel a l'autre.
        self._http = new_client(self.base_url)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- primitives ----------------------------------------------------------

    def _request(self, method: str, path: str, **kw: Any) -> Any:
        try:
            resp = self._http.request(method, f"/api/v1{path}", **kw)
        except httpx.HTTPError as exc:
            raise WiringError(
                f"{self.name}: appel {method} {path} impossible",
                str(exc),
                f"verifiez que {self.base_url} repond",
            ) from exc
        if resp.status_code >= 400:
            raise WiringError(
                f"{self.name}: {method} {path} a echoue",
                f"HTTP {resp.status_code} - {resp.text[:300]}",
                t("le corps attendu est decrit dans /app/seerr-api.yml de l'image"),
            )
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text

    # -- disponibilite -------------------------------------------------------

    def wait_ready(self, timeout: float = 300.0) -> None:
        def probe() -> bool:
            try:
                return bool((self._request("GET", "/status") or {}).get("version"))
            except WiringError:
                return False

        result = wait_until(probe, label=self.name, timeout=timeout)
        if not result.ready:
            raise WiringError(
                t("{service} n'est jamais devenu disponible", service="Seerr"),
                result.detail,
                "inspectez `docker logs plugarr-seerr`",
            )

    @property
    def version(self) -> str:
        return str((self._request("GET", "/status") or {}).get("version", "?"))

    @property
    def initialized(self) -> bool:
        return bool((self._request("GET", "/settings/public") or {}).get("initialized"))

    # -- accueil -------------------------------------------------------------

    def login_jellyfin(
        self,
        *,
        username: str,
        password: str,
        hostname: str,
        port: int,
        use_ssl: bool = False,
        url_base: str = "",
    ) -> dict:
        """Ouvre la session, et cree l'administrateur au premier passage.

        **La specification embarquee est INCOMPLETE ici**, et deux essais l'ont
        montre. Elle ne declare que `username`, `password`, `hostname`, `email`
        et `serverType` ; l'implementation lit en plus `port`, `useSsl` et
        `urlBase`, qu'elle recompose ainsi (`dist/utils/getHostname.js`) :

            `${useSsl ? 'https' : 'http'}://${ip}:${port}${urlBase}`

        `hostname` est donc l'HOTE SEUL — `jellyfin` — et non une URL. Lui
        passer `http://jellyfin:8096` rend `HTTP 404 INVALID_URL`, un message
        qui ne dit pas quel champ est en cause.

        `serverType` est obligatoire alors que la specification le donne pour
        facultatif : sans lui la reponse est `NO_ADMIN_USER`, ce qui laisse
        croire a un probleme de droits cote Jellyfin. La valeur 2 vaut
        JELLYFIN, lue dans `dist/constants/server.js` :

            PLEX = 1, JELLYFIN = 2, EMBY = 3, NOT_CONFIGURED = 4
        """
        corps: dict[str, Any] = {
            "username": username,
            "password": password,
            "hostname": hostname,
            "port": port,
            "useSsl": use_ssl,
            "urlBase": url_base,
            "serverType": SERVEUR_JELLYFIN,
        }
        try:
            return self._request("POST", "/auth/jellyfin", json=corps) or {}
        except WiringError as exc:
            if "already configured" not in str(exc):
                raise
        # L'adresse du serveur media n'est acceptee qu'UNE FOIS. Passe ce
        # premier appel, la renvoyer produit « Jellyfin hostname already
        # configured » et 500, la ou l'omettre au premier appel produit « No
        # hostname provided ». Les deux erreurs sont symetriques et aucune
        # documentation ne les mentionne : on essaie avec, on retombe sans.
        # C'est ce qui rend l'etape rejouable.
        for cle in ("hostname", "port", "useSsl", "urlBase"):
            corps.pop(cle)
        return self._request("POST", "/auth/jellyfin", json=corps) or {}

    def api_key(self) -> str:
        """Cle API de Seerr, qu'il cree lui-meme a sa configuration.

        `GET /settings/main` ne la renvoie qu'a un administrateur
        (`filteredMainSettings`, server/routes/settings/index.ts, v3.4.1) :
        la session ouverte par `login_jellyfin` en est un, le premier compte
        Jellyfin recevant les pleins droits.
        """
        return str((self._request("GET", "/settings/main") or {}).get("apiKey") or "")

    def initialize(self) -> None:
        """Ferme l'accueil. A n'appeler QU'APRES avoir declare les *arr :
        autrement l'instance se croit prete et ne peut rien demander."""
        self._request("POST", "/settings/initialize")

    # -- declaration des *arr -------------------------------------------------

    def servarrs(self, genre: str) -> list[dict]:
        return self._request("GET", f"/settings/{genre}") or []

    def ensure_servarr(
        self,
        genre: str,
        *,
        name: str,
        hostname: str,
        port: int,
        api_key: str,
        profile_id: int,
        profile_name: str,
        directory: str,
        anime_directory: str | None = None,
    ) -> bool:
        """Declare un Sonarr ou un Radarr. Renvoie True s'il a ete ajoute.

        `genre` vaut `sonarr` ou `radarr`. Le doublon se juge sur le couple
        hote + port : deux entrees vers le meme service feraient partir chaque
        demande en double.

        Les champs obligatoires viennent de la specification embarquee, et ils
        sont plus nombreux qu'on ne l'attend — `activeProfileName` en plus de
        `activeProfileId`, `enableSeasonFolders` pour Sonarr. En omettre un
        rend une erreur qui nomme la propriete, ce qui est confortable, mais
        autant les poser tous.
        """
        for existant in self.servarrs(genre):
            if existant.get("hostname") == hostname and existant.get("port") == port:
                return False

        corps: dict[str, Any] = {
            "name": name,
            "hostname": hostname,
            "port": port,
            "apiKey": api_key,
            "useSsl": False,
            "activeProfileId": profile_id,
            "activeProfileName": profile_name,
            "activeDirectory": directory,
            "is4k": False,
            "isDefault": True,
            "syncEnabled": True,
        }
        if genre == "radarr":
            # Obligatoire pour Radarr seul, et absent du schema de Sonarr.
            # Seerr le transmet tel quel a Radarr : `released` signifie « le
            # film est reellement sorti ». Les autres valeurs — `announced`,
            # `inCinemas` — font partir des recherches sur des films qui
            # n'existent pas encore, ce qui remplit la file d'attente de rien.
            corps["minimumAvailability"] = MINIMUM_DISPONIBILITE
        if genre == "sonarr":
            # Obligatoire pour Sonarr seul. Les saisons en dossiers separes
            # sont la disposition que les *arr et les serveurs media attendent.
            corps["enableSeasonFolders"] = True
            if anime_directory:
                corps["activeAnimeProfileId"] = profile_id
                corps["activeAnimeProfileName"] = profile_name
                corps["activeAnimeDirectory"] = anime_directory
        self._request("POST", f"/settings/{genre}", json=corps)
        return True
