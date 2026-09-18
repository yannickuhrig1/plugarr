"""Persisted remote-access choices, independent of deployment code."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RemoteAccessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["local", "tailscale", "https"] = "local"
    domain: str = Field(default="", max_length=253)
    services: list[Literal["sonarr", "radarr", "qbittorrent"]] = Field(default_factory=list)

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

    @model_validator(mode="after")
    def complete(self):
        self.services = list(dict.fromkeys(self.services))
        if self.mode == "https" and (not self.domain or not self.services):
            raise ValueError("HTTPS demande un domaine et au moins une application.")
        return self
