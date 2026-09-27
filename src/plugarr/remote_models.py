"""Persisted remote-access choices, independent of deployment code."""
import base64
import binascii
import json
import re
import uuid
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)

Publiable = Literal["sonarr", "radarr", "qbittorrent"]

#: Sous-domaine propose par defaut. `qb` reste court : c'est celui qu'on tape
#: sur un telephone.
NOMS_PAR_DEFAUT = {"sonarr": "sonarr", "radarr": "radarr", "qbittorrent": "qb"}

_ETIQUETTE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
#: Le jeton est du base64 standard : cloudflared le lit avec
#: `base64.StdEncoding` (cmd/cloudflared/tunnel/subcommands.go, ParseToken).
_CANDIDAT_JETON = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")


def jeton_tunnel(texte: str) -> str:
    """Jeton de tunnel Cloudflare, extrait de ce que l'utilisateur a colle.

    Le tableau de bord Cloudflare ne montre pas le jeton seul : il montre une
    commande d'installation qui le contient (`cloudflared service install
    <jeton>`, ou `docker run ... --token <jeton>`). On accepte les deux, et on
    ne garde que le jeton, apres avoir verifie qu'il se decode comme
    cloudflared le decode : un JSON avec le compte (`a`), le secret (`s`) et
    l'identifiant du tunnel (`t`).
    """
    for candidat in _CANDIDAT_JETON.findall(texte):
        try:
            contenu = json.loads(base64.b64decode(candidat, validate=True))
            if not isinstance(contenu, dict):
                continue
            uuid.UUID(str(contenu.get("t", "")))
            if not isinstance(contenu.get("a"), str) or not contenu["a"]:
                continue
            if not isinstance(contenu.get("s"), str) or not base64.b64decode(contenu["s"], validate=True):
                continue
        except (ValueError, binascii.Error, TypeError):
            continue
        return candidat
    raise ValueError(
        "Jeton de tunnel illisible : collez la commande d’installation affichée par Cloudflare, ou le jeton seul."
    )


def identifiant_tunnel(jeton: str) -> str:
    """Identifiant du tunnel porte par le jeton. Il n'a rien de secret : c'est
    celui que le tableau de bord affiche, et il aide a choisir le bon tunnel."""
    try:
        return str(uuid.UUID(json.loads(base64.b64decode(jeton))["t"]))
    except (ValueError, binascii.Error, TypeError, KeyError):
        return ""


class RemoteAccessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["local", "tailscale", "https", "cloudflare"] = "local"
    domain: str = Field(default="", max_length=253)
    services: list[Publiable] = Field(default_factory=list)
    #: Sous-domaine choisi, quand il differe de `NOMS_PAR_DEFAUT`. Un nom deja
    #: pris ailleurs sur le domaine (un ancien `sonarr.`) serait refuse par
    #: Cloudflare, ou menerait a une autre instance.
    names: dict[Publiable, str] = Field(default_factory=dict)
    #: Secret du tunnel Cloudflare : il permet de faire tourner ce tunnel
    #: n'importe ou. Meme rang que les mots de passe des applications, deja
    #: dans ce fichier (0600) ; jamais renvoye au navigateur.
    tunnel_token: str = Field(default="", max_length=4096, repr=False)

    @field_validator("domain")
    @classmethod
    def domain_name(cls, value):
        value = value.strip().lower().rstrip(".")
        if value and ("." not in value or not all(
            re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", p)
            for p in value.split(".")
        ) or not re.search(r"[a-z]", value.split(".")[-1])):
            raise ValueError("Indiquez un domaine seul, sans protocole, port ni chemin.")
        return value

    @field_validator("names")
    @classmethod
    def subdomain_names(cls, value):
        noms = {}
        for sid, nom in value.items():
            nom = nom.strip().lower()
            if not nom or nom == NOMS_PAR_DEFAUT[sid]:
                continue
            if not _ETIQUETTE.fullmatch(nom):
                raise ValueError(
                    "Sous-domaine invalide : lettres, chiffres et tirets, sans point ni tiret aux extrémités."
                )
            noms[sid] = nom
        return noms

    @field_validator("tunnel_token")
    @classmethod
    def token(cls, value):
        return jeton_tunnel(value) if value.strip() else ""

    @model_validator(mode="after")
    def complete(self):
        self.services = list(dict.fromkeys(self.services))
        if self.mode in ("https", "cloudflare") and (not self.domain or not self.services):
            raise ValueError("Un accès par domaine demande un domaine et au moins une application.")
        if self.mode == "cloudflare" and not self.tunnel_token:
            raise ValueError("Le tunnel Cloudflare demande le jeton du tunnel.")
        if self.mode != "cloudflare":
            self.tunnel_token = ""
        self.names = {sid: nom for sid, nom in self.names.items() if sid in self.services}
        adresses = [self.hostname(sid) for sid in self.services]
        if len(set(adresses)) != len(adresses):
            raise ValueError("Deux applications ne peuvent pas partager le même sous-domaine.")
        if any(len(adresse) > 253 for adresse in adresses):
            raise ValueError("Adresse trop longue : raccourcissez le sous-domaine ou le domaine.")
        return self

    @model_serializer(mode="wrap")
    def _compatible(self, handler):
        # Pas de nouvelle version de stack.yml pour ces deux champs : une PlugArr
        # plus ancienne REFUSE un champ inconnu ici (extra="forbid"), elle ne
        # l'efface pas en silence. Les omettre quand ils sont vides garde donc
        # lisibles, par l'image d'administration epinglee, toutes les piles qui
        # ne s'en servent pas.
        data = handler(self)
        for champ in ("names", "tunnel_token"):
            if not data.get(champ):
                data.pop(champ, None)
        return data

    def label(self, sid: str) -> str:
        return self.names.get(sid) or NOMS_PAR_DEFAUT[sid]

    def hostname(self, sid: str) -> str:
        return f"{self.label(sid)}.{self.domain}"
