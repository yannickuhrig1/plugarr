"""Rendu console : recapitulatif, progression, rapport final."""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from . import catalog, journal
from .discovery import Found
from .i18n import t
from .models import StackConfig
from .runner import Check
from .wiring import StepResult


class _ConsoleTraduisante(Console):
    """Console Rich qui fait passer ses chaines par le catalogue.

    Meme raison que pour les widgets de l'assistant (`tui/widgets.py`) :
    envelopper soixante appels a la main aurait pose la question a chaque
    ligne ecrite, et une phrase oubliee ne casse rien — elle s'affiche
    simplement en francais a quelqu'un qui a demande l'anglais.

    Ce qui n'est pas une chaine passe intact : `console.print(table)` et
    `console.print(panel)` doivent arriver a Rich tels quels.
    """

    def print(self, *objets: object, **kw: object) -> None:  # type: ignore[override]
        super().print(*(t(o) if isinstance(o, str) else o for o in objets), **kw)


console = _ConsoleTraduisante()


def print_checks(checks: list[Check]) -> bool:
    """Affiche le preflight. Renvoie False si un controle BLOQUANT a echoue."""
    table = Table(title=t("Preflight"), show_lines=False)
    table.add_column(t("Controle"), style="bold")
    table.add_column("")
    table.add_column(t("Detail"), overflow="fold")
    blocked = False
    for check in checks:
        if check.ok:
            mark, style = "OK", "green"
        elif check.blocking:
            mark, style, blocked = t("ECHEC"), "red", True
        else:
            mark, style = t("ATTENTION"), "yellow"
        table.add_row(check.name, f"[{style}]{mark}[/{style}]", check.detail)
    console.print(table)
    return not blocked


def print_summary(cfg: StackConfig, adopted_sources: dict[str, Found] | None = None) -> None:
    table = Table(title=t("Recapitulatif - rien n'a encore ete ecrit"))
    for col in ("Service", "Image", "URL", "Config"):
        table.add_column(t(col), overflow="fold")
    for sid in catalog.STARTUP_ORDER:
        if not cfg.enabled(sid):
            continue
        spec, inst = catalog.get(sid), cfg.services[sid]
        source = adopted_sources.get(sid) if adopted_sources is not None else None
        table.add_row(
            spec.display_name,
            source.image if source is not None else inst.image or spec.image,
            inst.url(cfg.host) if inst.has_web_ui else t("tache de fond"),
            (source.config_dir or t("inconnu")) if source is not None else cfg.config_path(sid),
        )
    console.print(table)

    if adopted_sources is None:
        paths = t(
            "CONFIG_ROOT : {config}\n"
            "DATA_ROOT   : {data}  (monte sur /data dans TOUS les conteneurs)\n"
            "PUID:PGID   : {uid}:{gid}  ({origine})\n"
            "UMASK / TZ  : {umask}   {tz}\n"
            "Plateforme  : {plateforme}",
            config=cfg.config_root,
            data=cfg.data_root,
            uid=cfg.puid,
            gid=cfg.pgid,
            origine=t(cfg.ids_source),
            umask=cfg.umask,
            tz=cfg.timezone,
            plateforme=cfg.platform.value,
        )
    else:
        paths = t(
            "CONFIG_ROOT : {config}\n"
            "DATA_ROOT   : {data}  (chemin declare ; montages reels dans l'inventaire)\n"
            "PUID:PGID   : {uid}:{gid}  ({origine})\n"
            "UMASK / TZ  : {umask}   {tz}\n"
            "Plateforme  : {plateforme}",
            config=cfg.config_root,
            data=cfg.data_root,
            uid=cfg.puid,
            gid=cfg.pgid,
            origine=t(cfg.ids_source),
            umask=cfg.umask,
            tz=cfg.timezone,
            plateforme=cfg.platform.value,
        )
    console.print(Panel(paths, title=t("Chemins"), border_style="blue"))

    if cfg.enabled("sabnzbd"):
        trajet = (
            t("via Gluetun ; SSL/TLS reste necessaire")
            if cfg.vpn.protects("sabnzbd")
            else t("connexion directe ; SSL/TLS recommande vers le fournisseur Usenet")
        )
        console.print(Panel(trajet, title="SABnzbd", border_style="cyan"))

    torrents = [s for s in catalog.TORRENT_CLIENTS if cfg.enabled(s)]
    if adopted_sources is not None and torrents:
        details = []
        for sid in torrents:
            owner = adopted_sources[sid].network_owner
            if owner:
                details.append(
                    t("{service} partage le reseau du conteneur {conteneur}.",
                      service=catalog.get(sid).display_name, conteneur=escape(owner))
                )
        details.append(t(
            "Le VPN, la route de sortie et l'etancheite des clients torrent adoptes "
            "n'ont pas ete verifies. Aucun changement de reseau n'est propose."
        ))
        console.print(Panel("\n".join(details), title=t("VPN de la pile existante"), border_style="yellow"))
    elif not cfg.vpn_enabled and torrents:
        console.print(
            Panel(
                t(
                    "Aucun VPN n'est configure pour le client torrent.\n"
                    "Le trafic BitTorrent sortira sur l'adresse IP publique de "
                    "cette machine, visible par les autres pairs.\n"
                    "Pour ajouter un VPN, relancez avec --vpn."
                ),
                title=t("Avertissement VPN"),
                border_style="yellow",
            )
        )


def print_step(result: StepResult) -> None:
    mark = "[green]OK   [/green]" if result.ok else f"[red]{t('ECHEC')}[/red]"
    console.print(f"  {mark} {result.name} - {result.detail}")
    for warning in result.warnings:
        console.print(f"         [yellow]{t('attention')}[/yellow] {warning}")


def install_with_progress(cfg: StackConfig, project_dir, install) -> list[StepResult]:
    """Deroule l'installation sous une barre de progression.

    L'installation dure plusieurs minutes, dont un `docker compose up` muet le
    temps de telecharger les images. Sans barre, l'utilisateur ne sait pas si le
    programme travaille ou s'il est bloque.

    Les lignes de detail continuent d'etre imprimees AU-DESSUS de la barre :
    c'est Rich qui s'en charge, a condition de lui passer la meme console.
    """
    from rich.progress import BarColumn, TextColumn, TimeElapsedColumn
    from rich.progress import Progress as RichProgress

    from . import orchestrator

    total = orchestrator.expected_events(cfg)
    with RichProgress(
        TextColumn("[bold]{task.description}"),
        BarColumn(bar_width=None),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as bar:
        task = bar.add_task(t("preparation"), total=total)

        def advance(description: str) -> None:
            # Borne l'avancement : le total est une estimation, et une barre qui
            # depasse 100 % ferait douter du reste de l'affichage.
            done = min(bar.tasks[0].completed + 1, total)
            bar.update(task, completed=done, description=description[:28])

        def on_progress(progress: orchestrator.Progress) -> None:
            mark = (
                "[cyan]…[/cyan]"
                if progress.started
                else "[green]OK[/green]"
                if progress.ok
                else f"[red]{t('ECHEC')}[/red]"
            )
            journal.progress(progress.phase, progress.message, progress.ok)
            console.print(f"  {mark} {progress.phase} : {progress.message}")
            if not progress.started:
                advance(progress.phase)

        def on_step(result: StepResult) -> None:
            journal.step(result)
            print_step(result)
            advance(result.name.split(":")[0])

        try:
            return install(cfg, project_dir, on_progress=on_progress, on_step=on_step)
        finally:
            # Une barre laissee a 94 % apres un succes se lit comme un echec.
            bar.update(task, completed=total, description=t("termine"))


def print_final(cfg: StackConfig, results: list[StepResult]) -> None:
    failed = [r for r in results if not r.ok]
    created = sum(1 for r in results if r.created)

    table = Table(title=t("Acces"))
    for col in ("Service", "URL", "Identifiant", "Mot de passe", "Cle API"):
        table.add_column(t(col), overflow="fold")
    for sid in catalog.STARTUP_ORDER:
        if not cfg.enabled(sid):
            continue
        spec, inst = catalog.get(sid), cfg.services[sid]
        table.add_row(
            spec.display_name,
            inst.url(cfg.host) if inst.has_web_ui else t("tache de fond"),
            inst.username or "-",
            inst.password or "-",
            inst.api_key or "-",
        )
    console.print(table)
    console.print(
        t(
            "[dim]Ces identifiants sont aussi dans .env "
            "(chmod 600, deja dans .gitignore).[/dim]"
        )
        + "\n"
    )

    style = "green" if not failed else "red"
    headline = t(
        "{faits}/{total} liens etablis, {crees} crees a ce passage.",
        faits=len(results) - len(failed),
        total=len(results),
        crees=created,
    )
    body = [headline]
    if failed:
        body.append(t("\nEchecs :"))
        body += [f"  - {r.name}: {r.detail}" for r in failed]
        body.append(t("\nDiagnostic : `plugarr doctor`"))
    else:
        from .orchestrator import prochaine_etape

        body.append("\n" + "\n".join(prochaine_etape(cfg)))
    console.print(Panel("\n".join(body), title=t("Resultat"), border_style=style))
