"""Client DroppedNeedle : accueil, serveur media, client de telechargement.

DroppedNeedle remplace Lidarr plutot qu'il ne le complete : il gere la musique
de la demande au rangement. Il etait bloque au catalogue tant qu'aucun client de
telechargement ne l'accompagnait — c'est SABnzbd qui l'a debloque.

**Sa documentation vit dans son propre code**, et elle est bonne. Les schemas
portent des commentaires qui expliquent les pieges au lieu de les taire, ce qui
est rare. Deux exemples repris tels quels ci-dessous.

Une note de la feuille de route disait « son premier compte administrateur se
cree par l'interface web ». C'etait FAUX : `POST /api/v1/auth/setup` existe,
rend 201 avec un jeton, et 409 si l'accueil a deja eu lieu.

Le contrat, releve appel par appel contre la v2.9.0 :

    GET  /api/v1/auth/setup/status      -> {"required": true|false}
    POST /api/v1/auth/setup             -> 201 + jeton, corps display_name,
                                           username, email, password
    POST /api/v1/auth/login             -> 200 + jeton
    GET  /api/v1/settings/jellyfin      -> {jellyfin_url, api_key, user_id, ...}
    PUT  /api/v1/settings/jellyfin
    GET  /api/v1/download-clients/sabnzbd
    PUT  /api/v1/download-clients/sabnzbd
    POST /api/v1/download-clients/sabnzbd/test
"""

from __future__ import annotations

from typing import Any, Self

import httpx

from ..i18n import t
from .base import WiringError, new_client, wait_until

#: `post_processing` de SABnzbd tel que DroppedNeedle l'attend. 3 vaut
#: « telecharger, reparer, decompresser » — le comportement complet, releve
#: dans son schema comme valeur par defaut.
POST_TRAITEMENT_COMPLET = 3


class DroppedNeedleClient:
    def __init__(self, base_url: str, *, name: str = "droppedneedle"):
        self.name = name
        self.base_url = base_url.rstrip("/")
        # La session vit dans un cookie pose par `/setup` et `/login` : le
        # client doit donc conserver ses cookies d'un appel a l'autre.
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
                t("l'accueil a peut-etre deja ete termine manuellement"),
            )
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text

    # -- disponibilite -------------------------------------------------------

    def wait_ready(self, timeout: float = 300.0) -> None:
        """Attend la route d'ACCUEIL, seule joignable sans jeton.

        Toutes les autres repondent 401 tant qu'on n'est pas connecte : les
        sonder ferait croire a une application indisponible alors qu'elle
        fonctionne parfaitement.
        """

        def probe() -> bool:
            try:
                return "required" in (self._request("GET", "/auth/setup/status") or {})
            except WiringError:
                return False

        result = wait_until(probe, label=self.name, timeout=timeout)
        if not result.ready:
            raise WiringError(
                t("{service} n'est jamais devenu disponible", service="DroppedNeedle"),
                result.detail,
                "inspectez `docker logs plugarr-droppedneedle`",
            )

    @property
    def needs_setup(self) -> bool:
        return bool((self._request("GET", "/auth/setup/status") or {}).get("required"))

    # -- accueil -------------------------------------------------------------

    def setup(self, *, username: str, password: str, email: str = "") -> bool:
        """Cree le premier administrateur. Renvoie True s'il a ete cree ici.

        Un second appel rendrait 409 « Setup has already been completed » : on
        relit l'etat avant plutot que d'interpreter un code d'erreur.

        L'adresse est obligatoire. Faute d'en connaitre une, on en fabrique une
        sous `.invalid`, domaine reserve par la RFC 2606 qui ne peut par
        construction jamais resoudre.

        DroppedNeedle refuse les mots de passe figurant dans les fuites
        connues — son code le dit : « breached password ». Ceux que PlugArr
        engendre sont aleatoires, la question ne se pose pas.
        """
        if not self.needs_setup:
            return False
        self._request(
            "POST",
            "/auth/setup",
            json={
                "display_name": username,
                "username": username,
                "email": email or f"{username}@plugarr.invalid",
                "password": password,
            },
        )
        return True

    def login(self, username: str, password: str) -> None:
        reponse = self._request(
            "POST", "/auth/login", json={"username": username, "password": password}
        )
        if not (reponse or {}).get("token"):
            raise WiringError(
                f"{self.name}: connexion refusee",
                t("aucun jeton dans la reponse"),
                t("les identifiants annonces sont-ils bien ceux du compte ?"),
            )

    # -- serveur media -------------------------------------------------------

    def ensure_jellyfin(self, *, url: str, api_key: str) -> bool:
        """Declare le serveur media. Renvoie True si quelque chose a change.

        On relit la configuration complete avant de la renvoyer : n'ecrire que
        deux champs effacerait `user_id` et les autres reglages.
        """
        actuel = self._request("GET", "/settings/jellyfin") or {}
        if actuel.get("jellyfin_url") == url and actuel.get("enabled") and actuel.get("api_key"):
            return False
        actuel.update({"jellyfin_url": url, "api_key": api_key, "enabled": True})
        self._request("PUT", "/settings/jellyfin", json=actuel)
        return True

    # -- client de telechargement --------------------------------------------

    def ensure_sabnzbd(
        self, *, url: str, api_key: str, categorie: str, montage: str
    ) -> bool:
        """Declare SABnzbd. Renvoie True si quelque chose a change.

        Deux pieges, tous deux ecrits noir sur blanc dans le schema de
        DroppedNeedle — une franchise assez rare pour etre citee :

            « `api_key` is the FULL key (the add-only nzbkey can't do
              queue/history/delete) »

        La cle de PlugArr est la cle complete : le pre-semis pose la meme valeur
        dans `api_key` et `nzb_key`.

            « `downloads_mount` is where DroppedNeedle sees SABnzbd's completed
              dir (the remap target) »

        Les deux conteneurs montent `${DATA_ROOT}` sur `/data` : DroppedNeedle
        voit donc les telechargements termines exactement la ou SABnzbd les
        depose. Sans ce montage commun, il faudrait remapper les chemins, et
        chaque import recopierait le fichier au lieu de le lier.
        """
        actuel = self._request("GET", "/download-clients/sabnzbd") or {}
        voulu = {
            "enabled": True,
            "client_type": "sabnzbd",
            "url": url,
            "api_key": api_key,
            "category": categorie,
            "priority": actuel.get("priority", 0),
            "post_processing": POST_TRAITEMENT_COMPLET,
            "downloads_mount": montage,
        }
        # La cle est MASQUEE a la lecture : la comparer n'apprendrait rien. On
        # se fie aux autres champs pour decider s'il y a quelque chose a faire.
        inchange = all(
            actuel.get(cle) == valeur
            for cle, valeur in voulu.items()
            if cle != "api_key"
        )
        if inchange and actuel.get("api_key"):
            # Installation reelle du 26/09/2026 : SABnzbd recree avec une
            # nouvelle cle, DroppedNeedle garde l'ancienne, masquee, et chaque
            # test rendait « API Key Incorrect ». Son propre test tranche : on ne
            # renvoie la cle que s'il echoue.
            valide, _detail = self.test_sabnzbd()
            if valide:
                return False
        self._request("PUT", "/download-clients/sabnzbd", json=voulu)
        return True

    def test_sabnzbd(self) -> tuple[bool, str]:
        """Declenche son propre bouton « Test ». Verification reelle, pas une
        relecture de ce qu'on vient d'ecrire.

        La route teste les reglages SOUMIS et non ceux stockes — son code le
        dit. On lui renvoie donc ce qu'on vient d'enregistrer, cle masquee
        comprise : « A masked key resolves to the stored one ».

        Le champ de verdict s'appelle `valid`, pas `success`. Le lire au
        mauvais nom faisait passer chaque test pour un echec.
        """
        try:
            actuel = self._request("GET", "/download-clients/sabnzbd") or {}
            reponse = self._request(
                "POST", "/download-clients/sabnzbd/test", json=actuel
            ) or {}
        except WiringError as exc:
            return False, str(exc)
        return bool(reponse.get("valid")), str(reponse.get("message") or "test OK")
