"""Reprise d'une stack existante.

`install` s'adresse a qui part de zero. `adopt` s'adresse a qui a deja tout
installe a la main — et ils sont bien plus nombreux.

Ce que la commande fait, et surtout ce qu'elle ne fait pas :

- elle ne demarre, n'arrete et ne recree AUCUN conteneur ;
- elle ne genere pas de `docker-compose.yml` : ces services ne lui appartiennent
  pas ;
- elle lit les cles API dans les `config.xml` des conteneurs, puis pose les memes
  liens que `install` : dossiers racine, clients de telechargement, applications
  Prowlarr, notifications.

Elle ecrit un `stack.yml` marque comme adopte, pour que `wire` et `serve` sachent
sur quoi ils travaillent.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import catalog, discovery, registre
from .discovery import Found
from .i18n import t
from .models import PlatformProfile, ServiceInstance, StackConfig


@dataclass
class Plan:
    """Ce qui sera cable, ce qui sera ignore, et pourquoi."""

    chosen: dict[str, Found]
    skipped: list[tuple[Found, str]]
    ambiguous: dict[str, list[Found]]

    @property
    def ready(self) -> bool:
        return bool(self.chosen) and not self.ambiguous


def build_plan(found: list[Found], picks: dict[str, str] | None = None) -> Plan:
    """Choisit un conteneur par service.

    `picks` associe un identifiant de service au nom de conteneur retenu. Sans
    lui, un service detecte plusieurs fois reste ambigu : plugarr ne devine pas
    lequel de vos deux Sonarr doit recevoir les indexeurs.
    """
    picks = picks or {}
    chosen: dict[str, Found] = {}
    skipped: list[tuple[Found, str]] = []
    ambiguous: dict[str, list[Found]] = {}

    by_service: dict[str, list[Found]] = {}
    for entry in found:
        if discovery.looks_like_plugarr(entry):
            skipped.append((entry, t("deja gere par plugarr")))
            continue
        if not entry.usable:
            skipped.append((entry, entry.problems[0] if entry.problems else "inutilisable"))
            continue
        by_service.setdefault(entry.service_id, []).append(entry)

    for service_id, candidates in by_service.items():
        wanted = picks.get(service_id)
        if wanted:
            match = next((c for c in candidates if c.container == wanted), None)
            if match is None:
                ambiguous[service_id] = candidates
                continue
            chosen[service_id] = match
            skipped += [(c, "non retenu") for c in candidates if c is not match]
        elif len(candidates) == 1:
            chosen[service_id] = candidates[0]
        else:
            ambiguous[service_id] = candidates

    return Plan(chosen=chosen, skipped=skipped, ambiguous=ambiguous)


def config_from_plan(
    plan: Plan,
    *,
    data_root: str,
    config_root: str,
    host: str = "localhost",
    project_name: str = "plugarr-adopte",
) -> StackConfig:
    """Materialise le plan en StackConfig.

    Les chemins de donnees restent ceux que l'utilisateur indique : plugarr ne
    deplace rien et ne suppose pas que la stack existante suit son arborescence.
    """
    cfg = StackConfig(
        project_name=project_name,
        platform=PlatformProfile.GENERIC_LINUX,
        config_root=config_root,
        data_root=data_root,
        host=host,
        ids_source=t("stack existante : plugarr ne gere pas ces conteneurs"),
        ids_certain=True,
    )
    for service_id, entry in plan.chosen.items():
        cfg.services[service_id] = ServiceInstance(
            spec_id=service_id,
            host_port=entry.host_port or catalog.get(service_id).default_host_port,
            api_key=entry.api_key,
            adopted=True,
            container=entry.container,
            url_base=entry.url_base,
        )
    return cfg


def write_stack(cfg: StackConfig, project_dir: Path) -> Path:
    """Ecrit stack.yml SEUL.

    Surtout pas de docker-compose.yml : ces conteneurs ne nous appartiennent pas,
    et en generer un donnerait a `uninstall` le pouvoir de detruire la stack de
    l'utilisateur.
    """
    import yaml

    project_dir.mkdir(parents=True, exist_ok=True)
    path = project_dir / "stack.yml"
    # Une stack adoptee se retrouve comme les autres : c'est ce qui permet de la
    # reprendre quand l'executable est relance depuis un autre dossier.
    registre.enregistrer(project_dir, cfg.config_root, cfg.project_name)
    path.write_text(
        t(
            "# Stack ADOPTEE : plugarr cable ces services mais ne les gere pas.\n"
            "# Aucun docker-compose.yml n'est genere, `uninstall` ne s'y "
            "applique pas.\n"
        )
        + yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    try:
        path.chmod(0o600)
    except (OSError, NotImplementedError):
        pass
    return path


def missing_for_wiring(cfg: StackConfig) -> list[str]:
    """Ce qui manque pour que le cablage ait un sens, en langage clair."""
    notes: list[str] = []
    if not any(cfg.enabled(sid) for sid in catalog.MANAGED_ARRS):
        notes.append("aucune application *arr detectee : il n'y a rien a cabler")
    if cfg.enabled("prowlarr") and not any(cfg.enabled(s) for s in catalog.MANAGED_ARRS):
        notes.append(t("Prowlarr est seul : aucune application a alimenter"))
    if not any(cfg.enabled(sid) for sid in catalog.DOWNLOAD_CLIENTS):
        notes.append(
            t("aucun client de telechargement detecte : les *arr ne seront pas rattaches")
        )
    return notes
