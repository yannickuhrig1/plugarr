"""Plan du graphe de l'assistant, derive des operations reelles de PlugArr.

Le dessin utilisateur est conserve ; ses exemples et ses succes preenregistres
ne le sont pas. Les liens Compose sont structurels, pas une preuve de sante VPN.
"""

from __future__ import annotations

import hashlib
import json

from . import catalog, connections
from .wiring import Wirer

COLUMNS = ["indexeurs", "arr", "telechargement", "vpn", "media"]
GROUPS = {
    "prowlarr": ("indexeurs", "primaire"),
    "recyclarr": ("arr", "secondaire"),
    "autobrr": ("arr", "secondaire"),
    "gluetun": ("vpn", "succes"),
    "flood": ("telechargement", "accent"),
    "qui": ("telechargement", "accent"),
}
COMPOSITE_STEPS = {
    "dispatch": "autobrr/clients",
    "request": "seerr/setup",
    "authentication": "seerr/setup",
    "profiles": "recyclarr/profils",
    "music": "droppedneedle/setup",
    "library": "droppedneedle/setup",
}


def build(cfg):
    wirer = Wirer(cfg)
    try:
        steps = [s.name for s in wirer.build_plan()]
    finally:
        wirer.close()
    topology = connections.topology(cfg)
    nodes = _nodes(topology, steps)
    edges = []
    for edge in topology["connections"]:
        structural = edge["basis"] == "Configuration Compose"
        step = edge["id"] if edge["id"] in steps else COMPOSITE_STEPS.get(edge["kind"])
        if edge["source"] == "qui":
            step = "qui/qbittorrent"
        if not structural and step not in steps:
            continue
        edges.append(
            {
                "id": edge["id"],
                "source": edge["source"],
                "cible": edge["target"],
                "etape": step,
                "structure": structural,
                "permanent": False,
                "verbe": edge["label"],
                "description": edge["description"],
            }
        )
    # A neuf, la cle Jellyfin arrive seulement apres son setup. Cette liaison
    # figure bien dans l'etape DroppedNeedle qui sera executee ensuite.
    if (
        cfg.enabled("droppedneedle")
        and cfg.enabled("jellyfin")
        and not any(e["source"] == "droppedneedle" and e["cible"] == "jellyfin" for e in edges)
    ):
        edges.append(
            {
                "id": "droppedneedle/library/jellyfin",
                "source": "droppedneedle",
                "cible": "jellyfin",
                "etape": "droppedneedle/setup",
                "structure": False,
                "permanent": False,
                "verbe": "Bibliotheque",
                "description": "Declaration de Jellyfin apres obtention de sa cle API.",
            }
        )
    result = {
        "colonnes": COLUMNS,
        "noeuds": nodes,
        "liens": edges,
        "etapes": steps,
        "cable": [[0, "#F79B45"], [0.52, "#E4638A"], [1, "#8B36C9"]],
    }
    result["id"] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:16]
    return result


def _nodes(topology, steps=()):
    nodes = []
    for node in topology["nodes"]:
        sid = node["id"]
        if sid in GROUPS:
            column, tint = GROUPS[sid]
        elif catalog.get(sid).category.value == "download":
            column, tint = "telechargement", "accent"
        elif catalog.get(sid).category.value == "arr":
            column, tint = "arr", "secondaire"
        else:
            column, tint = "media", "primaire"
        nodes.append(
            {
                "id": sid,
                "nom": node["name"],
                "colonne": column,
                "teinte": tint,
                "pastille": node["name"][:2].upper(),
                "reglages": [step for step in steps if step.startswith(sid + "/")],
            }
        )
    return nodes


def administration(cfg, saved=None):
    """The same layout with per-link tests instead of installation step results."""
    topology = connections.topology(cfg, saved)
    graph = {
        "colonnes": COLUMNS,
        "noeuds": _nodes(topology),
        "liens": [
            {"id": edge["id"], "source": edge["source"], "cible": edge["target"],
             "etape": edge["id"], "structure": not edge["testable"],
             "permanent": False, "verbe": edge["label"], "description": edge["description"]}
            for edge in topology["connections"]
        ],
        "etapes": [e["id"] for e in topology["connections"] if e["testable"]],
        "cable": [[0, "#F79B45"], [0.52, "#E4638A"], [1, "#8B36C9"]],
    }
    graph["id"] = hashlib.sha256(json.dumps(graph, sort_keys=True).encode()).hexdigest()[:16]
    return {**topology, "graph": graph}
