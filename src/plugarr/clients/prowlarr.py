"""Gestion des indexeurs Prowlarr.

Position du projet : plugarr ne fournit, n'heberge et ne recommande AUCUN
indexeur. La liste proposee ici est celle que votre propre Prowlarr embarque
(626 definitions en 2.5.2) ; plugarr n'est qu'une interface de saisie par-dessus.
Rien n'est preconfigure, rien n'est preselectionne.

Point verifie contre Prowlarr 2.5.2 : l'ajout d'un indexeur CONTACTE cet indexeur
pour valider les identifiants, et `forceSave=true` ne change rien a ce comportement.
Il n'existe donc pas de moyen d'enregistrer un indexeur hors ligne. La contrepartie
est agreable : si l'enregistrement reussit, les identifiants sont bons.
"""


from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ..i18n import t
from .arr import ArrClient
from .base import WiringError

#: Noms de champs consideres comme des identifiants a saisir. Le marqueur
#: `privacy` de Prowlarr ne couvre que 115 champs sur plus de 9500 : la majorite
#: des definitions Cardigann laissent leurs cles en `privacy: normal`. Cette liste
#: complete donc le marqueur, elle ne le remplace pas.
CREDENTIAL_NAMES = frozenset(
    {
        "apikey",
        "api_key",
        "passkey",
        "pass_key",
        "rsskey",
        "rss_key",
        "authkey",
        "auth_key",
        "torrent_pass",
        "cookie",
        "username",
        "user",
        "password",
        "pass",
        "email",
        "token",
        "uid",
        "cfid",
        "cf_clearance",
    }
)

#: Prefixes de champs de reglage fin, jamais demandes a l'utilisateur.
_TUNING_PREFIXES = ("baseSettings.", "torrentBaseSettings.", "usenetBaseSettings.")

#: Zones de texte libres qui ne sont PAS des identifiants. Sans cette liste, la
#: regle structurelle ci-dessous les remonterait : ce sont des textbox sans valeur
#: par defaut, comme les vrais identifiants. Liste etablie par l'audit des 626
#: definitions (scripts/audit_indexers.py), pas devinee.
NON_CREDENTIAL_NAMES = frozenset(
    {
        "additionalparameters",  # parametres de requete optionnels
        "vipexpiration",  # date, purement informatif
        "thankyou",  # message de remerciement
        "audio_lang",  # preferences de recherche
        "fansub_lang",
        "sub_lang",
        "group_id",
    }
)


@dataclass(frozen=True)
class IndexerField:
    name: str
    label: str
    secret: bool
    value: Any = None

    @property
    def prefill(self) -> str:
        return "" if self.value is None else str(self.value)


@dataclass(frozen=True)
class IndexerDefinition:
    name: str
    implementation: str
    privacy: str
    protocol: str
    language: str
    description: str
    raw: dict

    @property
    def is_private(self) -> bool:
        return self.privacy in ("private", "semiPrivate")

    @property
    def urls(self) -> list[str]:
        """Miroirs connus de l'indexeur.

        Sur 626 definitions, 600 exposent un `baseUrl` de type `select` VIDE :
        les URL vivent au niveau de la definition, dans `indexerUrls`, pas dans
        le champ. Sans cette reprise, l'utilisateur devrait deviner l'adresse.
        """
        return [u for u in self.raw.get("indexerUrls", []) if u]

    def editable_fields(self) -> list[IndexerField]:
        """Champs a presenter : identifiants, plus l'URL de base.

        Tout le reste (limites de requetes, ratio de seed, textes d'aide) garde ses
        valeurs par defaut : les demander noierait les deux champs qui comptent.
        """
        fields: list[IndexerField] = []
        for raw in self.raw.get("fields", []):
            name = raw.get("name", "")
            if not name or is_tuning(name) or raw.get("type") == "info":
                continue
            if name == "baseUrl" or is_credential(raw):
                value = raw.get("value")
                if name == "baseUrl" and not value and self.urls:
                    value = self.urls[0]
                fields.append(
                    IndexerField(
                        name=name,
                        label=raw.get("label") or name,
                        secret=is_secret(raw),
                        value=value,
                    )
                )
        return fields


def is_tuning(name: str) -> bool:
    return name.startswith(_TUNING_PREFIXES) or name.startswith("info_")


#: Noms qui designent un secret, quoi qu'en dise la definition. Le repli par le
#: nom est necessaire : les definitions Cardigann ne renseignent pas toutes
#: `privacy`. Constate sur C411, dont le champ `apikey` arrive en `type:
#: textbox` sans `privacy` — la cle se tapait donc EN CLAIR a l'ecran.
_NOMS_SECRETS = ("apikey", "api_key", "passkey", "password", "passphrase", "token", "cookie",
                 "rsskey", "secret", "authkey", "digest")


def is_secret(raw: dict) -> bool:
    if raw.get("type") == "password" or raw.get("privacy") in ("apiKey", "password"):
        return True
    nom = raw.get("name", "").lower()
    return any(motif in nom for motif in _NOMS_SECRETS)


def is_credential(raw: dict) -> bool:
    """Un champ est-il un identifiant a saisir ?

    Quatre regles, de la plus sure a la plus large. La derniere est structurelle
    et rattrape ce qu'aucune liste de noms ne peut prevoir : un audit des 626
    definitions a montre que les manques (`mamId` de MyAnonamouse,
    `twoFactorAuthCode`, `alt2fatoken`, `passan`, `staffpass`, `csrf_token`)
    etaient TOUS des zones de texte sans valeur par defaut.

    Une zone de texte vide est, par construction, quelque chose que seul
    l'utilisateur peut fournir. Les reglages de comportement sont des cases a
    cocher ou des listes, jamais des textbox vides : la regle ne les attrape pas.
    """
    name = raw.get("name", "")
    if is_tuning(name) or raw.get("type") == "info":
        return False
    if raw.get("privacy") in ("apiKey", "password", "userName"):
        return True
    if raw.get("type") == "password":
        return True
    if name.lower() in CREDENTIAL_NAMES:
        return True
    if name.lower() in NON_CREDENTIAL_NAMES:
        return False
    return raw.get("type") == "textbox" and raw.get("value") in (None, "")


#: Duree laissee a Prowlarr pour valider un indexeur. Mesure sur Prowlarr 2.5.2
#: face a un tracker hors ligne (Cloudflare 522) : il abandonne apres 100 s.
#: Avec les 20 s par defaut du client, PlugArr coupait avant lui et accusait
#: Prowlarr d'etre injoignable, au lieu de rapporter la vraie cause.
INDEXER_SAVE_TIMEOUT = 150.0


class ProwlarrIndexers:
    """Recherche et ajout d'indexeurs dans Prowlarr."""

    def __init__(self, client: ArrClient):
        self._client = client
        self._definitions: list[IndexerDefinition] | None = None
        self._app_profile: int | None = None

    # -- catalogue Prowlarr --------------------------------------------------

    def definitions(self) -> list[IndexerDefinition]:
        """Definitions embarquees par Prowlarr. Environ 5,7 Mo : mis en cache.

        Ce sont les donnees de Prowlarr, pas les notres.
        """
        if self._definitions is None:
            self._definitions = [
                IndexerDefinition(
                    name=entry.get("name", "?"),
                    implementation=entry.get("implementation", "?"),
                    privacy=entry.get("privacy", "unknown"),
                    protocol=entry.get("protocol", "unknown"),
                    language=entry.get("language", ""),
                    description=entry.get("description", "") or "",
                    raw=entry,
                )
                for entry in self._client.get("indexer/schema") or []
            ]
        return self._definitions

    def search(self, term: str, limit: int = 25) -> list[IndexerDefinition]:
        """Filtre par nom, insensible a la casse. Les correspondances exactes
        en tete : taper "nzbgeek" ne doit pas renvoyer d'abord "NZBgeekPlus"."""
        needle = term.strip().lower()
        if not needle:
            return []
        matches = [d for d in self.definitions() if needle in d.name.lower()]
        matches.sort(key=lambda d: (not d.name.lower().startswith(needle), d.name.lower()))
        return matches[:limit]

    def find(self, name: str) -> IndexerDefinition:
        for definition in self.definitions():
            if definition.name.lower() == name.lower():
                return definition
        raise WiringError(
            t("indexeur {nom} inconnu de votre Prowlarr", nom=repr(name)),
            t("aucune definition de ce nom"),
            t("utilisez `plugarr indexers search <terme>` pour trouver le nom exact"),
        )

    # -- etat courant --------------------------------------------------------

    def configured(self) -> list[dict]:
        return self._client.get("indexer") or []

    def app_profiles(self) -> list[dict]:
        return self._client.get("appprofile") or []

    def tags(self) -> list[dict]:
        return self._client.get("tag") or []

    def download_clients(self) -> list[dict]:
        """Lecture seule : l'import d'indexeurs ne cree ni ne modifie jamais
        un client de telechargement."""
        return self._client.get("downloadclient") or []

    def app_profile_id(self) -> int:
        """Prowlarr refuse un indexeur sans appProfileId > 0. L'identifiant n'est
        pas garanti stable : on le resout, on ne le code pas en dur."""
        if self._app_profile is None:
            self._app_profile = self._client.profile_id("appprofile", "Standard")
        return self._app_profile

    # -- ajout ---------------------------------------------------------------

    def add(self, definition: IndexerDefinition, values: dict[str, str]) -> tuple[bool, str]:
        """Ajoute l'indexeur. Renvoie (succes, message).

        ATTENTION : Prowlarr contacte l'indexeur pour valider. C'est son
        comportement, pas un choix de plugarr, et `forceSave` n'y change rien.
        """
        existing = {i.get("name", "").lower() for i in self.configured()}
        if definition.name.lower() in existing:
            return True, t("deja configure")

        payload = dict(definition.raw)
        payload["fields"] = [
            {**field, "value": values.get(field["name"], field.get("value"))}
            if field.get("name") in values
            else dict(field)
            for field in definition.raw.get("fields", [])
        ]
        payload["name"] = definition.name
        payload["enable"] = True
        payload["appProfileId"] = self.app_profile_id()
        payload.setdefault("tags", [])
        return self.create(payload)

    def create(self, payload: dict) -> tuple[bool, str]:
        """Enregistre un indexeur deja rempli. Renvoie (succes, message)."""
        try:
            self._client.post("indexer", payload, timeout=INDEXER_SAVE_TIMEOUT)
        except WiringError as exc:
            return False, _readable(str(exc))
        return True, "ajoute et valide par Prowlarr"


#: Parametres d'URL a caviarder dans les messages d'erreur. Prowlarr RENVOIE
#: l'URL complete de son appel echoue : `... [GET] at [https://exemple/api/
#: torznab?apikey=<votre cle>&t=search...`. Sans ce filtre, la cle de
#: l'utilisateur s'affichait a l'ecran et partait dans le journal — celui-la
#: meme qu'on lui demande de nous envoyer quand quelque chose casse.
_PARAM_SECRET = re.compile(
    r"((?:api_?key|pass_?key|rss_?key|auth_?key|token|secret|digest)=)([^&\s\]]+)",
    re.IGNORECASE,
)


def redact(message: str) -> str:
    """Remplace la valeur des parametres sensibles par des points."""
    return _PARAM_SECRET.sub(lambda m: f"{m.group(1)}...", message)


#: Sequences \uXXXX laissees par le JSON de Prowlarr dans ses messages.
_ECHAPPEMENT_JSON = re.compile(r"[\\]u([0-9a-fA-F]{4})")


def _readable(message: str) -> str:
    """Extrait la ligne utile d'une erreur Prowlarr, souvent tres verbeuse."""
    # Prowlarr renvoie du JSON : sans ce decodage, l'utilisateur lisait
    # « indexer\u0027s server » et des URL hachees de « \u0026 ».
    message = redact(_ECHAPPEMENT_JSON.sub(lambda m: chr(int(m.group(1), 16)), message))
    for marker in ("Unable to connect", "Invalid API Key", "Authentication failed", "errorMessage"):
        if marker in message:
            fragment = message.split(marker, 1)[1][:180].strip(' ":,')
            return f"{marker}{': ' if marker != 'errorMessage' else ' '}{fragment}"
    # `splitlines()[0]` sur un message vide leve IndexError - dans le gestionnaire
    # d'erreur lui-meme, ce qui transformait un echec d'ajout en plantage.
    lignes = message.splitlines()
    return lignes[0][:200] if lignes else t("aucun detail renvoye par Prowlarr")
