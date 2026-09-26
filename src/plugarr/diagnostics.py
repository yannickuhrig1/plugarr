"""Read-only checks shared by the CLI and the administration console."""

from __future__ import annotations

from os import stat_result
from pathlib import Path

import yaml

from . import compose, connections
from .i18n import t
from .models import StackConfig


def connection_checks(cfg: StackConfig) -> list[dict]:
    """Test actual *arr links without replaying their wiring."""
    checks: list[dict] = []
    for edge in connections.entries(cfg):
        outcome = connections.test(cfg, edge)
        ok = outcome["state"] == "verifiee"
        source, target = edge["source"], edge["target"]
        checks.append(
            {
                "name": t("Liaison {source} -> {target}", source=source, target=target),
                "ok": ok,
                "detail": outcome["detail"],
                "blocking": False,
                "partage": False,
                "edge_id": edge["id"],
                "next_step": (
                    t("Aucune action necessaire.")
                    if ok
                    else (
                        t("Examinez la liaison dans {source}. Apres verification de l'adresse et des identifiants, confirmez la reapplication de {liaison}.", source=source, liaison=edge["id"])
                        if not cfg.services[source].adopted
                        else t("Service adopte : corrigez la liaison {liaison} dans {source}.", liaison=edge["id"], source=source)
                    )
                ),
            }
        )
    return checks


def compose_drift(cfg: StackConfig, project_dir: Path) -> dict | None:
    """Compare the effective Compose structure with PlugArr's saved model.

    An adopted stack has no PlugArr-owned Compose file. Never print the diff:
    environment values and service settings can contain credentials.
    """
    if cfg.services and all(inst.adopted for inst in cfg.services.values()):
        return None
    path = project_dir / "docker-compose.yml"
    env_path = project_dir / ".env"
    if not (project_dir / "stack.yml").is_file() and not path.is_file():
        return None
    try:
        actual = yaml.safe_load(path.read_text(encoding="utf-8"))
        expected = yaml.safe_load(compose.render_compose(cfg))
        expected_env = _env_entries(compose.render_env(cfg, project_dir))
        actual_env = _env_entries(env_path.read_text(encoding="utf-8"))
        ok = actual == expected and actual_env == expected_env
        detail = (
            t("Les fichiers Compose et .env correspondent au modele PlugArr.")
            if ok
            else t("Les fichiers Compose ou .env divergent de la configuration PlugArr.")
        )
    except (OSError, yaml.YAMLError, ValueError) as exc:
        ok = False
        detail = t("Comparaison impossible ({erreur}).", erreur=type(exc).__name__)
    return {
        "name": t("Derive des fichiers Docker"),
        "ok": ok,
        "detail": detail,
        "blocking": False,
        "partage": False,
        "next_step": (
            t("Aucune action necessaire.")
            if ok
            else t("Sauvegardez le fichier, comparez-le a stack.yml, puis validez toute regeneration.")
        ),
    }


def _env_entries(text: str) -> dict[str, str]:
    """Ignore comment language while comparing secret-bearing values in memory."""
    return {
        key: value
        for line in text.splitlines()
        if line and not line.lstrip().startswith("#") and "=" in line
        for key, _, value in (line.partition("="),)
    }


def existing_hardlinks(data_root: str | Path, *, max_files: int = 20000) -> dict:
    """Read-only, bounded evidence of existing torrent-to-media hardlinks.

    A lack of matching inodes is inconclusive: media may come from Usenet, or
    matching files may be beyond the scan limit. Never claim all links are OK.
    """
    if max_files < 2:
        raise ValueError("max_files must be at least 2")
    root = Path(data_root)
    sources = root / "torrents"
    targets = root / "media"
    if not sources.is_dir() or not targets.is_dir():
        return {"checked": 0, "matched": 0, "partial": False, "available": False}

    checked = 0
    partial = False
    source_inodes: set[tuple[int, int]] = set()
    matched = 0
    for directory, is_source in ((sources, True), (targets, False)):
        directory_count = 0
        try:
            paths = directory.rglob("*")
            for path in paths:
                if directory_count >= max_files // 2:
                    partial = True
                    break
                try:
                    if not path.is_file() or path.is_symlink():
                        continue
                    info: stat_result = path.stat()
                except OSError:
                    continue
                checked += 1
                directory_count += 1
                if info.st_nlink < 2:
                    continue
                inode = (info.st_dev, info.st_ino)
                if is_source:
                    source_inodes.add(inode)
                elif inode in source_inodes:
                    matched += 1
        except OSError:
            partial = True
    return {"checked": checked, "matched": matched, "partial": partial, "available": True}
