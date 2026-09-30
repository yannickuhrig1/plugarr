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
from .clients.arr import ArrClient
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


def write_stack(cfg: StackConfig, project_dir: Path, *, replace: bool = False) -> Path:
    """Ecrit stack.yml SEUL.

    Surtout pas de docker-compose.yml : ces conteneurs ne nous appartiennent pas,
    et en generer un donnerait a `uninstall` le pouvoir de detruire la stack de
    l'utilisateur.
    """
    import yaml

    project_dir.mkdir(parents=True, exist_ok=True)
    path = project_dir / "stack.yml"
    if path.is_symlink():
        raise FileExistsError(path)
    if replace and not path.read_text(encoding="utf-8").startswith(
        ("# Stack ADOPTEE", "# ADOPTED stack")
    ):
        raise FileExistsError(path)
    content = (
        t(
            "# Stack ADOPTEE : plugarr cable ces services mais ne les gere pas.\n"
            "# Aucun docker-compose.yml n'est genere, `uninstall` ne s'y "
            "applique pas.\n"
        )
        + yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False)
    )
    # Exclusive creation protects a stack written by someone else between the
    # CLI preflight and this operation.
    with path.open("w" if replace else "x", encoding="utf-8") as handle:
        handle.write(content)
    # Une stack adoptee se retrouve comme les autres : c'est ce qui permet de la
    # reprendre quand l'executable est relance depuis un autre dossier.
    registre.enregistrer(project_dir, cfg.config_root, cfg.project_name)
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


def compatibility_notes(plan: Plan, data_root: str) -> list[str]:
    """Report risks visible in Docker mounts without changing any container.

    A mount inventory cannot prove existing files are hardlinked. The real
    hardlink probe remains a separate check on the user's data root.
    """
    notes: list[str] = []
    relevant = {
        sid: entry for sid, entry in plan.chosen.items()
        if sid in (*catalog.MANAGED_ARRS, *catalog.DOWNLOAD_CLIENTS)
    }
    downloads_by_source: dict[str, list[str]] = {}
    for sid, entry in relevant.items():
        source = entry.data_mounts.get("/downloads")
        if source:
            downloads_by_source.setdefault(source.rstrip("/\\"), []).append(sid)
    shared_downloads = {
        source: services for source, services in downloads_by_source.items()
        if any(sid in catalog.MANAGED_ARRS for sid in services)
        and any(sid in catalog.DOWNLOAD_CLIENTS for sid in services)
    }
    for sid, entry in relevant.items():
        source = entry.data_mounts.get("/data")
        if not entry.data_mounts:
            notes.append(t("{service} : aucun montage /data, /downloads ou /media visible ; chemins a verifier.", service=sid))
        elif source is None:
            downloads = entry.data_mounts.get("/downloads", "").rstrip("/\\")
            if downloads not in shared_downloads:
                notes.append(t(
                    "{service} : aucun montage de telechargements commun avec un client et un *arr ; "
                    "verifiez les chemins d'import et les hardlinks avant tout cablage.",
                    service=sid,
                ))
        elif source.rstrip("/") != data_root.rstrip("/"):
            notes.append(
                t("{service} : /data pointe vers {source}, different de la racine annoncee ({racine}).", service=sid, source=source, racine=data_root)
            )
    for source, services in shared_downloads.items():
        notes.append(t(
            "Montage /downloads commun a {services} ({source}) ; les chemins actifs "
            "dans les applications et les hardlinks restent a verifier avant cablage.",
            services=", ".join(services), source=source,
        ))
        root = data_root.replace("\\", "/").rstrip("/")
        mounted = source.replace("\\", "/")
        if mounted != root and not mounted.startswith(root + "/"):
            notes.append(t(
                "Le montage de telechargements {source} est hors de la racine declaree {racine} ; "
                "verifiez les chemins et le systeme de fichiers avant cablage.",
                source=source, racine=data_root,
            ))
    if plan.ambiguous:
        notes.append(t("Instances en double : choisissez explicitement le conteneur a cabler."))
    return notes


def minimal_steps(steps: list[str]) -> list[str]:
    """Only inter-service links belong to the initial adoption proposal.

    Root folders, UI settings, RSS, categories and service onboarding require
    separate intent; they are never inferred from Docker metadata.
    """
    return [
        step for step in steps
        if "/downloadclient/" in step or "/application/" in step
    ]


def link_inventory(cfg: StackConfig, steps: list[str]) -> list[dict[str, str]]:
    """GET existing *arr link records; presence is not a connection test."""
    resources = {"downloadclient": "downloadclient", "application": "applications"}
    results: list[dict[str, str]] = []
    for step in steps:
        source, kind, target = step.split("/")
        spec, inst = catalog.get(source), cfg.services[source]
        try:
            with ArrClient(
                inst.url(cfg.host), inst.api_key or "", api_version=spec.api_version,
                name=source,
            ) as client:
                records = client.get(resources[kind])
            if not isinstance(records, list):
                state = "unknown"
            elif any(
                isinstance(record, dict)
                and record.get("name") == catalog.get(target).display_name
                for record in records
            ):
                state = "present"
            else:
                # A differently named existing entry may target the same app.
                # Do not create a duplicate based on its name alone.
                state = "unknown" if records else "absent"
        except Exception:  # noqa: BLE001 - never expose API errors or credentials
            state = "unknown"
        results.append({"step": step, "state": state})
    return results


def compatibility_report(
    found: list[Found], plan: Plan, data_root: str,
    api_results: list[dict[str, str | bool]] | None = None,
    steps: list[str] | None = None,
    link_results: list[dict[str, str]] | None = None,
) -> dict[str, list[str]]:
    """Separate Docker facts, API evidence, blockers and untested hypotheses."""
    result: dict[str, list[str]] = {
        "observed": [], "verified_api": [], "incompatible": [], "indeterminate": [],
    }
    results_by_service = {str(item["service"]): item for item in api_results or []}
    for entry in found:
        mounts = ", ".join(
            f"{target}={source}" for target, source in sorted(entry.mounts.items())
        ) or t("aucun montage visible")
        networks = ", ".join(entry.networks) or t("aucun réseau nommé observé")
        result["observed"].append(
            t(
                "{service} ({conteneur}) : image {image} (version applicative non déduite du tag), "
                "port hôte {port}{adresse}, état {etat}, montages {montages}, "
                "mode réseau {mode}, réseaux {reseaux}{partage}.",
                service=entry.service_id, conteneur=entry.container, image=entry.image,
                port=entry.host_port or "-",
                adresse=t(" sur {ip}", ip=entry.host_ip) if entry.host_ip else "",
                etat=t("actif") if entry.running else t("arrêté"),
                montages=mounts, mode=entry.network_mode or t("inconnu"),
                reseaux=networks,
                partage=t(", espace réseau de {conteneur}", conteneur=entry.network_owner)
                if entry.network_owner else "",
            )
        )
        if entry.managed_by_us:
            result["incompatible"].append(
                t("{conteneur} : déjà géré par PlugArr, exclu de l'adoption.",
                  conteneur=entry.container)
            )
        elif not entry.usable:
            reason = "; ".join(entry.problems) or (
                t("conteneur arrêté") if not entry.running else t("port ou clé API manquant")
            )
            result["incompatible"].append(t(
                "{conteneur} : adoption bloquée : {raison}.",
                conteneur=entry.container, raison=reason,
            ))
        if entry.host_ip in ("127.0.0.1", "::1"):
            result["indeterminate"].append(
                t("{conteneur} : port publié sur la boucle locale ; accès via l'adresse LAN à vérifier.",
                  conteneur=entry.container)
            )
        if entry.service_id in catalog.TORRENT_CLIENTS:
            result["indeterminate"].append(
                t("{conteneur} : topologie Docker observée ; tunnel VPN et sortie effective non vérifiés.",
                  conteneur=entry.container)
            )
        if catalog.get(entry.service_id).api_family != "arr":
            result["indeterminate"].append(
                t("{conteneur} : version et accès applicatif non vérifiés via API.",
                  conteneur=entry.container)
            )
    for sid, item in results_by_service.items():
        entry = plan.chosen.get(sid)
        if entry is None:
            continue
        if item["ok"]:
            result["verified_api"].append(
                t("{service} ({conteneur}) : API accessible avec la clé lue, version {version}.",
                  service=sid, conteneur=entry.container, version=item["version"])
            )
        else:
            result["incompatible"].append(
                t("{service} ({conteneur}) : API ou version non vérifiable ; adoption bloquée.",
                  service=sid, conteneur=entry.container)
            )
    for link in link_results or []:
        step, state = link["step"], link["state"]
        if state == "present":
            result["verified_api"].append(t(
                "{etape} : entrée présente dans l'API source ; connexion non testée.",
                etape=step,
            ))
        elif state == "absent":
            result["verified_api"].append(t(
                "{etape} : aucune entrée de ce nom dans l'API source.", etape=step,
            ))
        else:
            result["indeterminate"].append(t(
                "{etape} : liaison non identifiable (lecture impossible ou nom personnalisé) ; "
                "aucune application automatique.",
                etape=step,
            ))
    for sid, entries in plan.ambiguous.items():
        result["indeterminate"].append(
            t("{service} : plusieurs instances ({conteneurs}) ; --pick requis.",
              service=sid, conteneurs=", ".join(e.container for e in entries))
        )
    if data_root:
        result["indeterminate"].extend(compatibility_notes(plan, data_root))
    if steps:
        result["indeterminate"].extend(
            t("Liaison {etape} : proposée, état réel non vérifié avant le câblage.",
              etape=step)
            for step in steps
        )
    result["indeterminate"].append(
        t("Montages seuls : chemins actifs, système de fichiers et hardlinks non prouvés.")
    )
    return result


def api_inventory(cfg: StackConfig) -> list[dict[str, str | bool]]:
    """Read-only version and API-key check for adopted *arr services.

    Do not include exception text: HTTP errors may echo sensitive URLs or
    response bodies. The detailed key remains in memory only.
    """
    results: list[dict[str, str | bool]] = []
    for sid, inst in cfg.services.items():
        spec = catalog.get(sid)
        if spec.api_family != "arr":
            continue
        try:
            with ArrClient(
                inst.url(cfg.host), inst.api_key or "", api_version=spec.api_version,
                name=sid,
            ) as client:
                version = client.version
            if not version or version == "?":
                raise ValueError("missing version")
            results.append({"service": sid, "ok": True, "version": version})
        except Exception:  # noqa: BLE001 - un diagnostic doit continuer pour les autres services
            results.append({"service": sid, "ok": False, "version": ""})
    return results
