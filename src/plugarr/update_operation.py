"""Read-only update plan and post-operation evidence shared by CLI and console."""

from __future__ import annotations

import time
from pathlib import Path

from . import catalog
from .i18n import t


def affected_services(cfg) -> list[str]:
    """Cold backup stops the whole managed stack, including the VPN container."""
    return [
        *(sid for sid, inst in cfg.services.items() if not inst.adopted),
        *(["gluetun"] if cfg.vpn_enabled else []),
    ]


def plan(cfg, services: list[str], *, wiring: bool, recreate: list[str] | None = None) -> dict:
    """Describe effects without registry, Docker, filesystem writes or secrets."""
    recreated = services if recreate is None else recreate
    return {
        "services": services,
        "recreation": recreated,
        "impact": t("Services concernés : {services}", services=", ".join(services) or t("aucun")),
        "recreation_detail": t(
            "Conteneurs recréés : {services}", services=", ".join(recreated) or t("aucun")
        ),
        "interruption": t(
            "La sauvegarde à froid arrête temporairement la pile ; chaque service "
            "recréé subit aussi une interruption."
        ),
        "compatibility": t(
            "Versions comparables uniquement ; compatibilité applicative et migrations non vérifiées."
        ),
        "backup": t(
            "Sauvegarde à froid du projet, des configurations et des volumes ; "
            "lecture et contrôle d'intégrité avant modification. Les médias et "
            "configurations des services adoptés sont exclus."
        ),
        "checks": t(
            "État et santé Docker des services impactés, API disponibles et liaisons essentielles."
        ),
        "wiring": wiring,
        "rollback": t(
            "Aucun retour automatique : les migrations de bases et données créées après "
            "la mise à jour ne sont pas restaurables sans risque démontré."
        ),
    }


def verify(cfg, project_dir: Path, runner, services: list[str], *, attempts: int = 12) -> dict:
    """Read live Compose and application links after recreation."""
    from . import admin

    selected = set(services)
    last = []
    for attempt in range(attempts):
        # doctor_payload also probes APIs and connection resources, without writing.
        try:
            result = admin.doctor_payload(cfg, project_dir, runner)
        except Exception as exc:  # noqa: BLE001 - turn probe failures into a failed verdict
            last = [{
                "name": t("Contrôles après mise à jour"),
                "ok": False,
                "detail": type(exc).__name__,
            }]
            if attempt + 1 < attempts:
                time.sleep(5)
            continue
        last = [
            c for c in result["checks"]
            if c["name"].startswith(("Etat ", "API ", "Liaison "))
            and (
                not c["name"].startswith("Etat ")
                or any(
                    c["name"] == f"Etat {catalog.get(s).display_name}"
                    for s in selected if s != "gluetun"
                )
                or ("gluetun" in selected and c["name"] == "Etat Gluetun")
            )
        ]
        # The runtime probe itself must fail closed if Compose is unavailable.
        last += [c for c in result["checks"] if c["name"] == "Etat Docker"]
        if last and all(c["ok"] for c in last):
            return {"ok": True, "checks": last}
        if attempt + 1 < attempts:
            time.sleep(5)
    return {"ok": False, "checks": last}
