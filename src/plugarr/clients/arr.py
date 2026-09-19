"""Client generique Sonarr / Radarr / Prowlarr, pilote par les schemas.

Principe (PROMPT.md sec. 4.5) : on ne fabrique JAMAIS un payload de download client
ou d'application a la main. On demande son gabarit a l'application via
`/api/<v>/<resource>/schema`, on remplit les champs par NOM, et on renvoie l'objet.

C'est ce qui rend l'outil resistant aux montees de version : quand Radarr 6 ajoute
ou renomme un champ, le gabarit suit et notre code continue de fonctionner. Un
payload code en dur, lui, casse silencieusement.
"""

from __future__ import annotations

from typing import Any, Self

import httpx

from ..i18n import t
from .base import WiringError, new_client, wait_until


class ArrClient:
    def __init__(self, base_url: str, api_key: str, *, api_version: str = "v3", name: str = "arr"):
        self.name = name
        self.api_version = api_version
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._http = new_client(self.base_url, headers={"X-Api-Key": api_key})

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- primitives ----------------------------------------------------------

    def _path(self, resource: str) -> str:
        return f"/api/{self.api_version}/{resource}"

    def _request(self, method: str, resource: str, **kw: Any) -> Any:
        try:
            resp = self._http.request(method, self._path(resource), **kw)
        except httpx.HTTPError as exc:
            raise WiringError(
                f"{self.name}: appel {method} {resource} impossible",
                str(exc),
                t(
                    "verifiez que {adresse} est joignable et que le conteneur tourne",
                    adresse=self.base_url,
                ),
            ) from exc
        if resp.status_code == 401:
            raise WiringError(
                f"{self.name}: cle API refusee sur {resource}",
                "HTTP 401",
                t(
                    "le config.xml pre-seme a peut-etre ete ecrase. "
                    "Relancez `plugarr doctor`."
                ),
            )
        if resp.status_code >= 400:
            raise WiringError(
                f"{self.name}: {method} {resource} a echoue",
                f"HTTP {resp.status_code} - {resp.text[:400]}",
                t("le gabarit renvoye par /schema a peut-etre change de forme"),
            )
        return resp.json() if resp.content else None

    def get(self, resource: str) -> Any:
        return self._request("GET", resource)

    def post(self, resource: str, payload: dict, *, timeout: float | None = None) -> Any:
        if timeout is None:
            return self._request("POST", resource, json=payload)
        return self._request("POST", resource, json=payload, timeout=timeout)

    def put(self, resource: str, payload: dict) -> Any:
        return self._request("PUT", resource, json=payload)

    # -- compte de l'interface web -------------------------------------------

    def web_login_works(self, username: str, password: str) -> bool:
        """Le couple identifiant/mot de passe ouvre-t-il VRAIMENT l'interface ?

        On poste le formulaire de connexion, comme le ferait un navigateur. Un
        echec renvoie 302 vers `/login?...loginFailed=true`, un succes 302 vers
        la racine. C'est la seule verification qui vaut : l'API peut parfaitement
        repondre alors qu'aucun compte n'existe.
        """
        if not username or not password:
            return False
        try:
            resp = self._http.post(
                "/login",
                data={"username": username, "password": password, "rememberMe": "on"},
                follow_redirects=False,
            )
        except httpx.HTTPError:
            return False
        if resp.status_code not in (301, 302, 303):
            # Certaines versions repondent 200 sur la page de connexion en cas
            # d'echec ; un succes redirige toujours.
            return False
        return "loginfailed" not in resp.headers.get("location", "").lower()

    def ensure_web_user(self, username: str, password: str) -> None:
        """Cree ou reinitialise le compte de l'interface web.

        `PUT config/host` est la voie supportee : l'application hache le mot de
        passe elle-meme. On relit la configuration complete avant de la renvoyer,
        pour ne modifier que les trois champs qui nous concernent.
        """
        host = self.get("config/host")
        host["username"] = username
        host["password"] = password
        host["passwordConfirmation"] = password
        self.put(f"config/host/{host['id']}", host)

    def set_ui_language(self, code: str, valeur: int) -> bool:
        """Pose la langue de l'INTERFACE. Renvoie True si elle a change.

        Le type de `uiLanguage` DEPEND DE L'APPLICATION, ce qui ne se devine
        pas : Sonarr et Radarr veulent un entier (2 pour le francais), Prowlarr
        veut le code lui-meme (`fr`). Poser l'entier a Prowlarr donne :

            "$.uiLanguage": ["The JSON value could not be converted to
             System.String"]

        On regarde donc ce que l'application expose DEJA et on lui rend la
        meme forme, plutot que de tenir une liste de qui veut quoi — une liste
        qui aurait vieilli a la premiere version suivante.

        On relit la configuration complete avant de la renvoyer : n'ecrire que
        ce champ effacerait le format de date, le theme et le reste.
        """
        ui = self.get("config/ui")
        actuel = ui.get("uiLanguage")
        attendu = code if isinstance(actuel, str) else valeur
        if actuel == attendu:
            return False
        ui["uiLanguage"] = attendu
        self.put(f"config/ui/{ui['id']}", ui)
        return True

    # -- disponibilite -------------------------------------------------------

    def status(self) -> dict:
        return self.get("system/status")

    def wait_ready(self, timeout: float = 300.0) -> None:
        def probe() -> bool:
            return bool(self.status().get("version"))

        result = wait_until(probe, label=self.name, timeout=timeout)
        if not result.ready:
            raise WiringError(
                t("{service} n'est jamais devenu disponible", service=self.name),
                result.detail,
                f"inspectez `docker logs {self.name}`",
            )

    @property
    def version(self) -> str:
        return str(self.status().get("version", "?"))

    # -- moteur de schema ----------------------------------------------------

    def schema_for(self, resource: str, implementation: str) -> dict:
        """Recupere le gabarit d'une implementation donnee.

        `implementation` est la valeur technique ("Transmission", "Sonarr"), pas le
        libelle affiche.
        """
        schemas = self.get(f"{resource}/schema") or []
        for entry in schemas:
            if entry.get("implementation") == implementation:
                return entry
        available = sorted({e.get("implementation", "?") for e in schemas})
        raise WiringError(
            t(
                "{service} : implementation {implementation} absente de "
                "{ressource}/schema",
                service=self.name,
                implementation=repr(implementation),
                ressource=resource,
            ),
            t(
                "implementations disponibles : {liste}",
                liste=", ".join(available),
            ),
            t("la version de l'application ne propose peut-etre pas ce connecteur"),
        )

    @staticmethod
    def fill(schema: dict, values: dict[str, Any]) -> tuple[dict, list[str], list[str]]:
        """Remplit les champs du gabarit par nom.

        Renvoie (gabarit_rempli, champs_appliques, champs_ignores). Les champs
        ignores sont ceux que nous voulions poser mais que cette version n'expose
        pas : ils sont journalises plutot que silencieusement perdus.

        Un champ qu'on voulait VIDER et qui n'existe pas n'est pas une perte : le
        resultat est identique avec ou sans lui. Le signaler n'apprenait rien et
        polluait chaque installation. Cas reel : les profils posent
        `tvDirectory: ""` pour interdire le couple categorie + repertoire, que
        les *arr refusent ; or Transmission expose ce champ et qBittorrent non,
        d'ou trois avertissements a chaque passage pour un effacement sans effet.
        """
        filled = dict(schema)
        fields = [dict(f) for f in schema.get("fields", [])]
        present = {f.get("name") for f in fields}
        applied: list[str] = []
        for field in fields:
            name = field.get("name")
            if name in values:
                field["value"] = values[name]
                applied.append(name)
        filled["fields"] = fields
        skipped = [k for k, v in values.items() if k not in present and v not in ("", None)]
        return filled, applied, skipped

    # -- operations idempotentes --------------------------------------------

    def find_by_name(self, resource: str, name: str) -> dict | None:
        for entry in self.get(resource) or []:
            if entry.get("name") == name:
                return entry
        return None

    def ensure_resource(
        self,
        resource: str,
        *,
        name: str,
        implementation: str,
        values: dict[str, Any],
        extra: dict[str, Any] | None = None,
    ) -> tuple[dict, bool, list[str]]:
        """Cree la ressource si elle n'existe pas deja sous ce nom.

        Renvoie (objet, a_ete_cree, champs_ignores). Ne modifie jamais une ressource
        existante : re-executer l'installeur ne doit pas ecraser un reglage manuel.
        """
        existing = self.find_by_name(resource, name)
        if existing is not None:
            return existing, False, []

        schema = self.schema_for(resource, implementation)
        payload, _applied, skipped = self.fill(schema, values)
        payload["name"] = name
        payload.update(extra or {})
        payload.setdefault("tags", [])
        created = self.post(resource, payload)
        return created, True, skipped

    def sync_fields(self, resource: str, existing: dict, values: dict[str, Any]) -> list[str]:
        """Aligne quelques champs d'une ressource existante. Renvoie ceux modifies.

        `ensure_resource` ne touche jamais a l'existant, et c'est voulu : un
        reglage manuel ne doit pas etre ecrase. Mais un mot de passe qui a change
        est un autre sujet — l'entree reste alors en place avec des identifiants
        perimes, et le bouton Test echoue sans que rien ne l'explique. Constate a
        l'usage apres une reinstallation.

        On ne compare et ne modifie que les champs demandes.
        """
        champs = {f.get("name"): f for f in existing.get("fields", []) if isinstance(f, dict)}
        modifies = []
        for nom, valeur in values.items():
            champ = champs.get(nom)
            if champ is None or champ.get("value") == valeur:
                continue
            champ["value"] = valeur
            modifies.append(nom)
        if modifies:
            self.put(f"{resource}/{existing['id']}", existing)
        return modifies

    def ensure_root_folder(self, path: str, extra: dict[str, Any] | None = None) -> tuple[dict, bool]:
        """Cree le dossier racine s'il n'existe pas.

        `extra` couvre les applications plus exigeantes : Sonarr et Radarr se
        contentent de `path`, alors que Lidarr impose en plus `name`,
        `defaultQualityProfileId` et `defaultMetadataProfileId`.
        """
        for entry in self.get("rootfolder") or []:
            if entry.get("path", "").rstrip("/") == path.rstrip("/"):
                return entry, False
        return self.post("rootfolder", {"path": path, **(extra or {})}), True

    def profile_id(self, resource: str, preferred: str) -> int:
        """Identifiant d'un profil par nom, avec repli sur le premier disponible.

        Les identifiants ne sont pas stables d'une version a l'autre : on les
        resout toujours par nom plutot que de les coder en dur.
        """
        profiles = self.get(resource) or []
        if not profiles:
            raise WiringError(
                t(
                    "{service} : aucun profil dans {ressource}",
                    service=self.name,
                    ressource=resource,
                ),
                t("la liste est vide"),
                t("l'application a-t-elle fini son initialisation ?"),
            )
        for entry in profiles:
            if entry.get("name") == preferred:
                return int(entry["id"])
        return int(profiles[0]["id"])

    def test_resource(self, resource: str, payload: dict) -> tuple[bool, str]:
        """Declenche le bouton "Test" de l'application. Verification reelle,
        pas une simple relecture de ce qu'on vient d'ecrire."""
        try:
            self.post(f"{resource}/test", payload)
            return True, "test OK"
        except WiringError as exc:
            return False, str(exc)
