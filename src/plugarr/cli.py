"""Interface en ligne de commande.

Toute la logique vit dans orchestrator.py : cette couche ne fait que traduire des
options en appels et rendre les evenements. Le TUI (tui/app.py) consomme exactement
les memes fonctions, ce qui garantit qu'ils ne divergeront pas.
"""

from __future__ import annotations

from pathlib import Path

import typer

from . import (
    __version__,
    admin,
    adminauth,
    autoupdate,
    catalog,
    compose,
    dashboard,
    discovery,
    i18n,
    indexers_cli,
    journal,
    migrations,
    orchestrator,
    pack,
    report,
    sauvegarde,
    vpncheck,
)
from . import adopt as adopt_mod
from . import autostart as autostart_mod
from . import (
    reprise as reprise_mod,
)
from .clients import recyclarr as recyclarr_cfg
from .clients.arr import ArrClient
from .i18n import t
from .layout import create_tree, default_profile, path_warning
from .models import VPN_PROVIDERS, PlatformProfile, StackConfig, VpnConfig
from .orchestrator import InstallAborted, Progress
from .runner import Compose
from .wiring import Wirer


def _langue_a_l_import() -> str:
    """Langue a poser AVANT que Typer ne lise ses libelles.

    Les decorateurs `@app.command(help=...)` tournent a l'import, et `--help`
    s'affiche avant la fonction de rappel : attendre celle-ci laisserait toute
    l'aide en francais. On regarde donc `sys.argv` nous-memes, puis le systeme.

    Ce pre-decoupage ne remplace pas l'analyse de Typer, il la precede : la
    fonction de rappel repose la langue proprement ensuite.
    """
    import sys

    arguments = sys.argv[1:]
    for index, argument in enumerate(arguments):
        if argument.startswith("--lang="):
            return i18n.utiliser(argument.split("=", 1)[1])
        if argument == "--lang" and index + 1 < len(arguments):
            return i18n.utiliser(arguments[index + 1])
    return i18n.utiliser(i18n.langue_du_systeme())


_langue_a_l_import()

app = typer.Typer(
    add_completion=False,
    help=t("Deploie ET cable automatiquement une stack media *arr."),
    invoke_without_command=True,
)
console = report.console

STACK_FILE = "stack.yml"

#: `--lang` a-t-il ete donne ? Si oui il prime sur ce que porte `stack.yml` :
#: une option ecrite a la main ne doit jamais etre annulee par un fichier.
_LANGUE_EXPLICITE = False

app.add_typer(indexers_cli.app, name="indexers")


def _show_version(value: bool) -> None:
    if value:
        console.print(f"plugarr {__version__}")
        raise typer.Exit(0)


@app.callback()
def main(
    ctx: typer.Context,
    _version: bool = typer.Option(
        False, "--version", "-V", callback=_show_version, is_eager=True,
        help=t("Affiche la version et quitte."),
    ),
    lang: str = typer.Option(
        "", "--lang",
        help=t("Langue de PlugArr : fr, en. Par defaut, celle du systeme."),
    ),
) -> None:
    """Sans sous-commande, lance l'assistant interactif."""
    # La langue AVANT tout le reste : les messages de la commande en cours
    # doivent deja etre dans la bonne. Sans valeur explicite, on suit le
    # systeme, ce qui donne le francais a un francophone et l'anglais aux
    # autres sans que personne ait rien a regler.
    global _LANGUE_EXPLICITE
    _LANGUE_EXPLICITE = bool(lang)
    i18n.utiliser(lang or i18n.langue_du_systeme())
    if ctx.invoked_subcommand is not None:
        return
    from .tui.app import run_wizard

    raise typer.Exit(run_wizard())


def _annoncer_nouvelle_version() -> None:
    """Dit qu'une version plus recente de PlugArr existe, si c'est le cas.

    Signale a l'usage : « je viens de lancer la 0.6 et elle ne detecte pas la
    0.7 pour se mettre a jour ». `upgrade` alignait les images des services sur
    le catalogue du BINAIRE EN COURS, et supposait donc qu'on avait deja
    telecharge le dernier — sans jamais le dire.

    Ne bloque jamais : un NAS derriere un pare-feu ne doit pas voir une erreur
    parce qu'il ne joint pas GitHub.
    """
    sortie = autoupdate.derniere()
    if sortie.disponible:
        console.print(
            t(
                "[yellow]PlugArr {disponible} est disponible[/yellow] "
                "[dim](vous avez la {courante})[/dim]",
                disponible=sortie.disponible,
                # La version que la VERIFICATION a comparee, pas celle que ce
                # module a importee : deux lectures separees pourraient
                # diverger, et le message afficherait deux numeros incoherents.
                courante=sortie.courante,
            )
        )
        console.print(f"[dim]{sortie.url}[/dim]")
        console.print(
            t(
                "[dim]Cette commande aligne les services sur le catalogue de la "
                "version que VOUS lancez : telechargez la nouvelle d'abord.[/dim]"
            )
        )
    elif sortie.probleme:
        console.print(
            t("[dim]Version de PlugArr non verifiee : {cause}[/dim]", cause=sortie.probleme)
        )


def _load_config(project_dir: Path) -> StackConfig:
    path = project_dir / STACK_FILE
    if not path.exists():
        raise typer.BadParameter(
            t(
                "{chemin} introuvable. Lancez d'abord `plugarr install`.",
                chemin=path,
            )
        )
    try:
        cfg, notes = migrations.lire(path)
    except migrations.VersionFuture as exc:
        # On s'arrete plutot que de lire a moitie : la premiere ecriture
        # detruirait ce qu'on n'a pas su lire.
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    for note in notes:
        console.print(f"[cyan]{note}[/cyan]")
    # L'installation a retenu une langue : les commandes qui reprennent cette
    # pile la reprennent aussi. Sans cela, `plugarr serve` sur un serveur dont
    # la session est en anglais repondrait en anglais a quelqu'un qui a installe
    # en francais.
    if not _LANGUE_EXPLICITE:
        i18n.utiliser(cfg.ui_language)
    return cfg


def _announce_page(path: Path, open_page: bool) -> None:
    """Signale la page d'acces, et l'ouvre si un navigateur existe.

    L'echec d'ouverture est normal sur un NAS sans environnement graphique : le
    chemin reste affiche, c'est lui qui compte.
    """
    if not path.exists():
        return
    console.print(f"\nPage d'acces : [bold]{path}[/bold]")
    if open_page and dashboard.open_in_browser(path):
        console.print("[dim]Ouverte dans votre navigateur.[/dim]")
    elif open_page:
        console.print("[dim]Aucun navigateur disponible ici : ouvrez ce fichier a la main.[/dim]")


def _traiter_config_existante(
    cfg: StackConfig, reset: bool | None, *, assume_yes: bool, repris: set[str] | None = None
) -> None:
    """Propose de repartir de zero quand une configuration inutilisable est la.

    « Inutilisable » a un sens precis : qBittorrent, Transmission, Jellyfin,
    autobrr et qui ne stockent leur mot de passe que hache. Il ne se relit pas
    dans LEUR configuration.

    **Mais il se relit dans la notre.** `repris` nomme les services dont les
    identifiants viennent d'etre repris du `stack.yml` precedent : pour
    ceux-la, il n'y a plus rien a craindre ni rien a effacer. L'avertissement
    sortait quand meme, deux lignes sous « Identifiants conserves », et se
    contredisait mot pour mot. Constate en lancant une reinstallation reelle
    sur une pile de cinq services.

    Sans reponse explicite, on CONSERVE : effacer la configuration de quelqu'un
    par defaut serait inacceptable.
    """
    repris = repris or set()
    concernes = [sid for sid in orchestrator.unusable_configs(cfg) if sid not in repris]
    if not concernes:
        return

    console.print(
        t(
            "\n[yellow]Etat existant detecte[/yellow] pour "
            "[bold]{services}[/bold].\n"
            "[dim]Leurs mots de passe ne se relisent pas : plugarr ne peut "
            "pas les reprendre, et ceux qu'il va annoncer seront "
            "refuses.[/dim]",
            services=", ".join(concernes),
        )
    )
    for sid in concernes:
        # La base de Silo n'a pas de dossier : montrer un chemin qui n'existe
        # pas enverrait l'utilisateur chercher pour rien, et lui ferait douter
        # de l'avertissement entier.
        console.print(f"  [dim]{orchestrator.emplacement_etat(cfg, sid)}[/dim]")

    if reset is None:
        if assume_yes:
            # `--yes` repond oui aux questions, pas aux suppressions.
            console.print(
                "[dim]Conservee (--yes ne supprime rien). Utilisez --reset-config pour "
                "repartir de zero.[/dim]"
            )
            return
        console.print(
            "\n[dim]Vos medias ne sont jamais touches : seul l'etat ci-dessus le "
            "serait.[/dim]"
        )
        reset = typer.confirm(
            t("Supprimer cet etat et repartir de zero ?"), default=False
        )

    if not reset:
        console.print("[dim]Configurations conservees.[/dim]")
        return

    efface = orchestrator.reset_configs(cfg, concernes)
    for chemin in efface:
        console.print(f"  [green]supprime[/green] {chemin}")
    journal.finish(f"configurations supprimees : {', '.join(concernes)}")


def _echo(progress: Progress) -> None:
    mark = "[green]OK[/green]" if progress.ok else "[red]ECHEC[/red]"
    console.print(f"  {mark} {progress.phase} : {progress.message}")


# ---------------------------------------------------------------------- commands


@app.command(help=t("Lance l'assistant interactif plein ecran."))
def wizard(
    # Deux reglages qui n'ont pas leur place DANS l'assistant : ils decident de
    # son lancement, pas de la stack. Ils vivent donc sur la commande, comme
    # leurs homologues de `install`.
    project_dir: Path = typer.Option(Path("."), help=t("Ou ecrire les artefacts.")),
    open_page: bool = typer.Option(
        True, "--open/--no-open", help=t("Ouvrir la page d'acces a la fin.")
    ),
) -> None:
    """Lance l'assistant interactif plein ecran."""
    from .tui.app import run_wizard

    raise typer.Exit(run_wizard(project_dir, open_page=open_page))


@app.command(help=t("Deploie et cable la stack de bout en bout, sans interaction."))
def install(
    services: str = typer.Option(
        ",".join(catalog.DEFAULT_SELECTION),
        "--services",
        "-s",
        help=t("Liste separee par des virgules. Connus: ")
        + ", ".join(sorted(s.id for s in catalog.selectable())),
    ),
    config_root: str | None = typer.Option(None, help=t("Racine des configurations.")),
    data_root: str | None = typer.Option(None, help=t("Racine des donnees (monte sur /data).")),
    # Defaut : le profil de la machine. Imposer generic-linux sous Windows
    # proposait des chemins Linux, crees ensuite a la racine du disque courant.
    platform: PlatformProfile = typer.Option(default_profile(), help=t("Profil de plateforme.")),
    host: str | None = typer.Option(None, help=t("Hote pour les URL du rapport final.")),
    username: str | None = typer.Option(
        None, help=t("Identifiant commun a tous les services installes.")
    ),
    project_name: str = typer.Option(
        "plugarr",
        help=t(
            "Nom de la pile Docker. A changer pour installer une SECONDE pile "
            "a cote d'une premiere : Docker identifie une pile par ce nom, pas "
            "par son repertoire."
        ),
    ),
    language: str | None = typer.Option(
        None,
        "--langue",
        help=t("Langue des interfaces (code ISO : fr, en, es...). Voir `plugarr langues`."),
    ),
    timezone: str | None = typer.Option(None, "--tz"),
    project_dir: Path = typer.Option(Path("."), help=t("Ou ecrire les artefacts.")),
    dry_run: bool = typer.Option(False, "--dry-run", help=t("N'ecrit rien, montre tout.")),
    yes: bool = typer.Option(False, "--yes", "-y", help=t("Ne pas demander confirmation.")),
    open_page: bool = typer.Option(
        True, "--open/--no-open", help=t("Ouvrir la page d'acces dans le navigateur.")
    ),
    vpn: bool = typer.Option(False, "--vpn", help=t("Faire passer le client torrent par un VPN.")),
    vpn_provider: str = typer.Option(
        "", help=t("Fournisseur VPN. Voir `plugarr vpn-providers`.")
    ),
    vpn_type: str = typer.Option("wireguard", help=t("wireguard ou openvpn.")),
    vpn_user: str = typer.Option("", help=t("Identifiant OpenVPN.")),
    vpn_pass: str = typer.Option("", help=t("Mot de passe OpenVPN.")),
    vpn_key: str = typer.Option("", help=t("Cle privee WireGuard.")),
    vpn_countries: str = typer.Option("", help=t("Pays souhaites, separes par des virgules.")),
    recyclarr_sonarr: str = typer.Option(
        "",
        help=t("Template TRaSH pour Sonarr. Voir `plugarr templates`. Vide = defaut."),
    ),
    recyclarr_radarr: str = typer.Option(
        "",
        help=t("Template TRaSH pour Radarr. Voir `plugarr templates`. Vide = defaut."),
    ),
    reprendre: bool = typer.Option(
        True,
        "--reprendre/--repartir-de-zero",
        help=t(
            "Reprendre les reglages du stack.yml deja present : identifiants, "
            "VPN, profils. Actif par defaut."
        ),
    ),
    reset_config: bool | None = typer.Option(
        None,
        "--reset-config/--keep-config",
        help=t(
            "Configuration existante : repartir de zero, ou la conserver. "
            "Sans l'option, la question est posee."
        ),
    ),
) -> None:
    """Deploie et cable la stack de bout en bout, sans interaction."""
    selection = [s.strip() for s in services.split(",") if s.strip()]
    for sid in selection:
        catalog.get(sid)  # leve une erreur lisible si inconnu

    cfg = orchestrator.build_config(
        services=selection,
        config_root=config_root,
        data_root=data_root,
        platform=platform,
        host=host or "localhost",
        timezone=timezone or "Etc/UTC",
        username=username or "plugarr",
        # Sans `--langue`, les services suivent la langue de PlugArr : c'est le
        # cas courant, et les deux restent separables.
        language=language or i18n.langue(),
        project_name=project_name,
    )

    chosen = {"sonarr": recyclarr_sonarr.strip(), "radarr": recyclarr_radarr.strip()}
    chosen = {sid: name for sid, name in chosen.items() if name}
    if chosen and not cfg.enabled("recyclarr"):
        console.print(
            "[yellow]Un template a ete choisi mais Recyclarr n'est pas dans la "
            "selection : il ne sera pas applique.[/yellow]"
        )
    if chosen:
        # Un nom invalide ne se voit qu'a la toute fin, quand `config create`
        # echoue apres le demarrage de la stack. Le dire avant d'ecrire quoi que
        # ce soit coute une requete.
        known, problem = recyclarr_cfg.available_templates()
        for sid, name in chosen.items():
            if not problem and name not in known.get(sid, []):
                console.print(
                    t(
                        "[red]Template inconnu pour {service} : {nom}[/red]\n"
                        "[dim]`plugarr templates` liste les noms "
                        "acceptes.[/dim]",
                        service=sid,
                        nom=name,
                    )
                )
                raise typer.Exit(1)
        if problem:
            console.print(
                t("[yellow]Noms de templates non verifies : {cause}[/yellow]", cause=problem)
            )
        cfg.recyclarr_templates = chosen

    if vpn:
        cfg.vpn = VpnConfig(
            enabled=True,
            provider=vpn_provider,
            vpn_type=vpn_type,
            openvpn_user=vpn_user,
            openvpn_password=vpn_pass,
            wireguard_private_key=vpn_key,
            countries=vpn_countries,
        )
        gaps = cfg.vpn.missing()
        if gaps:
            console.print(
                t(
                    "[red]VPN active mais incomplet : il manque {champs}.[/red]\n"
                    "[dim]Sans cela Gluetun refuse de demarrer, et le client "
                    "torrent reste injoignable puisqu'il partage sa pile "
                    "reseau.[/dim]",
                    champs=", ".join(gaps),
                )
            )
            raise typer.Exit(1)

        # Cet avertissement vivait sous `if reprendre:`, pas ici. Il sortait
        # donc a CHAQUE reinstallation sans client de telechargement, en
        # parlant d'une option `--vpn` que personne n'avait passee — et il
        # restait muet dans le seul cas ou il sert : `--vpn` sans client.
        if not any(cfg.enabled(sid) for sid in catalog.DOWNLOAD_CLIENTS):
            console.print(
                "[yellow]--vpn sans client de telechargement : Gluetun ne protegerait "
                "rien.[/yellow]"
            )

    # Reprendre AVANT le recapitulatif : c'est lui qui doit montrer ce qui sera
    # reellement pose. Reprendre apres reviendrait a annoncer une chose et a en
    # ecrire une autre.
    #
    # Une option donnee a la main prime toujours sur ce qu'on herite, sinon
    # elle serait sans effet et personne ne comprendrait pourquoi.
    #: Services dont les identifiants viennent d'une installation precedente.
    #: Ils ne sont plus « inutilisables » : l'avertissement qui suit ne les
    #: concerne pas, et effacer leur configuration serait une perte seche.
    services_repris: set[str] = set()
    if reprendre:
        try:
            trouvee = reprise_mod.trouver(project_dir, cfg.config_root)
        except migrations.VersionFuture as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(1) from exc
        ancienne = trouvee.cfg if trouvee else None
        # Une installation retrouvee AILLEURS impose son repertoire : deux
        # repertoires de projet portant le meme nom de pile Docker se
        # partagent les memes conteneurs, et le second recree ceux du premier.
        if trouvee is not None and trouvee.project_dir != Path(project_dir):
            console.print(
                t(
                    "[cyan]Installation precedente retrouvee dans {dossier}.[/cyan]\n"
                    "[dim]Les fichiers du projet y seront ecrits : une pile Docker "
                    "ne peut pas vivre dans deux repertoires a la fois.[/dim]",
                    dossier=trouvee.project_dir,
                )
            )
            project_dir = trouvee.project_dir
        if ancienne is not None:
            imposes = {
                nom
                for nom, donne in (
                    ("username", username is not None),
                    ("timezone", timezone is not None),
                    ("host", host is not None),
                    ("language", language is not None),
                    ("vpn", vpn),
                    ("recyclarr_templates", bool(chosen)),
                )
                if donne
            }
            reprise = reprise_mod.appliquer(cfg, ancienne, imposes=imposes)
            services_repris = set(reprise.services)
            if reprise:
                console.print(
                    t("[cyan]Installation existante detectee : reglages repris.[/cyan]")
                )
                if reprise.reglages:
                    console.print("  " + t("Reglages") + " : " + ", ".join(reprise.reglages))
                if reprise.services:
                    console.print(
                        "  "
                        + t("Identifiants conserves")
                        + " : "
                        + ", ".join(sorted(reprise.services))
                    )
                console.print(t("[dim]`--repartir-de-zero` ignore tout cela.[/dim]"))

    if not cfg.ids_certain:
        console.print(
            t(
                "[yellow]PUID/PGID {uid}:{gid} - {origine}.[/yellow]\n"
                "[dim]C'est l'utilisateur Linux, a l'interieur des "
                "conteneurs, qui possedera vos fichiers. Sur un NAS, lancez "
                "`id` en tant que l'utilisateur voulu.[/dim]",
                uid=cfg.puid,
                gid=cfg.pgid,
                origine=t(cfg.ids_source),
            )
        )

    # Un chemin Linux saisi sous Windows est cree a la racine du disque courant,
    # sans que rien ne le signale : `/mnt/user/data` devient `C:\mnt\user\data`.
    for label, chemin in (("--data-root", cfg.data_root), ("--config-root", cfg.config_root)):
        avertissement = path_warning(chemin)
        if avertissement:
            console.print(f"[yellow]{label} : {avertissement}[/yellow]")

    console.print(f"[dim]plugarr {__version__}[/dim]")
    chemin_journal = journal.start(project_dir, "install")
    journal.config(cfg)
    _traiter_config_existante(cfg, reset_config, assume_yes=yes, repris=services_repris)

    controles = orchestrator.preflight(cfg, project_dir)
    journal.checks(controles)
    if not report.print_checks(controles):
        journal.failure("preflight bloquant : installation abandonnee")
        console.print(f"[dim]Journal : {chemin_journal}[/dim]")
        raise typer.Exit(1)

    report.print_summary(cfg)

    if dry_run:
        console.print("[cyan]--dry-run : aucune ecriture. Compose qui serait genere :[/cyan]")
        console.print(compose.render_compose(cfg))
        raise typer.Exit(0)

    if not yes and not typer.confirm(
        t("Ecrire les fichiers et demarrer la stack ?"), default=True
    ):
        raise typer.Exit(0)

    try:
        results = report.install_with_progress(cfg, project_dir, orchestrator.install)
    except InstallAborted as exc:
        journal.failure(str(exc))
        console.print(f"[red]{exc}[/red]")
        console.print(f"[dim]Journal : {chemin_journal}[/dim]")
        raise typer.Exit(1) from exc
    except Exception as exc:
        journal.LOGGER.exception("installation")
        console.print(f"[red]{type(exc).__name__} : {exc}[/red]")
        console.print(
            t("[dim]Detail complet dans {chemin}[/dim]", chemin=chemin_journal)
        )
        raise typer.Exit(1) from exc

    report.print_final(cfg, results)
    echecs = [r for r in results if not r.ok]
    journal.finish(f"{len(results) - len(echecs)}/{len(results)} liens etablis")
    _announce_page(project_dir / dashboard.FILENAME, open_page)
    # Le journal n'est signale que s'il sert a quelque chose : tout annoncer a
    # chaque fois finit par n'etre plus lu.
    if echecs:
        console.print(
            t("\n[dim]Journal detaille : {chemin}[/dim]", chemin=chemin_journal)
        )
    raise typer.Exit(0 if not echecs else 2)


@app.command(help=t("Liste les services deja installes sur cette machine. N'ecrit rien."))
def scan(include_stopped: bool = typer.Option(False, "--all", help=t("Inclure les arretes."))) -> None:
    """Liste les services deja installes sur cette machine. N'ecrit rien."""
    from rich.table import Table

    found = discovery.scan(include_stopped=include_stopped)
    if not found:
        console.print("Aucun service connu detecte sur cette machine.")
        raise typer.Exit(0)

    table = Table(title=f"{len(found)} service(s) detecte(s)")
    for column in ("Service", "Conteneur", "Port", "Cle API", "Etat"):
        table.add_column(column, overflow="fold")
    for entry in found:
        if discovery.looks_like_plugarr(entry):
            state = "[dim]gere par plugarr[/dim]"
        elif entry.usable:
            state = "[green]adoptable[/green]"
        else:
            state = "[yellow]" + (entry.problems[0] if entry.problems else "inutilisable") + "[/yellow]"
        table.add_row(
            catalog.get(entry.service_id).display_name,
            entry.container,
            str(entry.host_port or "-"),
            discovery.mask_key(entry.api_key),
            state,
        )
    console.print(table)

    doubles = discovery.duplicates([e for e in found if e.usable])
    for service_id, items in doubles.items():
        names = ", ".join(i.container for i in items)
        console.print(
            t(
                "[yellow]{service} est present {nombre} fois ({noms}).[/yellow]\n"
                "[dim]Precisez lequel cabler : --pick {identifiant}="
                "<conteneur>[/dim]",
                service=catalog.get(service_id).display_name,
                nombre=len(items),
                noms=names,
                identifiant=service_id,
            )
        )


@app.command(help=t("Cable une stack DEJA installee, sans la recreer."))
def adopt(
    data_root: str = typer.Option(..., help=t("Racine des medias de la stack existante.")),
    config_root: str = typer.Option(..., help=t("Racine des configurations existantes.")),
    pick: list[str] = typer.Option(
        [], "--pick", help=t("Lever une ambiguite : service=conteneur. Repetable.")
    ),
    host: str | None = typer.Option(
        None, help=t("Adresse de cette machine, joignable DEPUIS les conteneurs.")
    ),
    dl_user: str | None = typer.Option(
        None, help=t("Identifiant du client de telechargement existant.")
    ),
    dl_pass: str | None = typer.Option(
        None, help=t("Mot de passe du client existant. Illisible depuis sa configuration.")
    ),
    project_dir: Path = typer.Option(Path("."), help=t("Ou ecrire stack.yml.")),
    dry_run: bool = typer.Option(False, "--dry-run", help=t("Montrer le plan, ne rien faire.")),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Cable une stack DEJA installee, sans la recreer.

    Aucun conteneur n'est demarre, arrete ou recree, et aucun docker-compose.yml
    n'est genere : ces services ne sont pas geres par plugarr.
    """
    picks: dict[str, str] = {}
    for item in pick:
        if "=" not in item:
            raise typer.BadParameter(f"attendu service=conteneur, recu {item!r}")
        key, _, value = item.partition("=")
        picks[key.strip()] = value.strip()

    # Les services adoptes vivent sur des reseaux Docker differents. Le cablage
    # les fait se joindre par l'hote — et depuis l'INTERIEUR d'un conteneur,
    # `localhost` designe ce conteneur, pas la machine. Il faut donc une vraie
    # adresse. Constate en conditions reelles : Prowlarr repondait "cannot connect
    # to Sonarr" sur une URL en localhost.
    if host in (None, "localhost", "127.0.0.1"):
        detected = dashboard.primary_lan_ip()
        if detected is None:
            console.print(
                "[red]Impossible de determiner l'adresse de cette machine sur le "
                "reseau.[/red]\n"
                "[dim]Les conteneurs doivent pouvoir se joindre entre eux : "
                "`localhost` ne convient pas. Passez --host <adresse>.[/dim]"
            )
            raise typer.Exit(1)
        host = detected
        console.print(t("[dim]Adresse retenue pour le cablage : {hote}[/dim]", hote=host))

    plan = adopt_mod.build_plan(discovery.scan(), picks)

    for entry, why in plan.skipped:
        console.print(f"[dim]ignore  {entry.container} ({why})[/dim]")
    for service_id, items in plan.ambiguous.items():
        names = ", ".join(i.container for i in items)
        console.print(
            t(
                "[red]{identifiant} est ambigu : {noms}.[/red] "
                "[dim]Ajoutez --pick {identifiant}=<conteneur>[/dim]",
                identifiant=service_id,
                noms=names,
            )
        )
    if not plan.chosen:
        console.print("[red]Rien d'adoptable. Lancez `plugarr scan` pour comprendre.[/red]")
        raise typer.Exit(1)
    if plan.ambiguous:
        raise typer.Exit(1)

    cfg = adopt_mod.config_from_plan(
        plan, data_root=data_root, config_root=config_root, host=host
    )
    for sid in catalog.DOWNLOAD_CLIENTS:
        if cfg.enabled(sid) and (dl_user or dl_pass):
            cfg.services[sid].username = dl_user or ""
            cfg.services[sid].password = dl_pass or ""
    for note in adopt_mod.missing_for_wiring(cfg):
        console.print(f"[yellow]{note}[/yellow]")

    console.print()
    report.print_summary(cfg)
    console.print(
        t(
            "[cyan]{nombre} lien(s) seraient poses sur ces conteneurs "
            "existants. Aucun ne sera recree.[/cyan]",
            nombre=orchestrator.planned_links(cfg),
        )
    )

    if dry_run:
        raise typer.Exit(0)
    if not yes and not typer.confirm(t("Cabler ces services ?"), default=True):
        raise typer.Exit(0)

    adopt_mod.write_stack(cfg, project_dir)
    wirer = Wirer(cfg)
    try:
        results = wirer.execute(on_step=report.print_step)
    finally:
        wirer.close()
    adopt_mod.write_stack(cfg, project_dir)
    report.print_final(cfg, results)
    raise typer.Exit(0 if all(r.ok for r in results) else 2)


@app.command(help=t("Regenere docker-compose.yml et .env depuis stack.yml, sans rien demarrer."))
def generate(project_dir: Path = typer.Option(Path("."), help=t("Repertoire du stack.yml."))) -> None:
    """Regenere docker-compose.yml et .env depuis stack.yml, sans rien demarrer."""
    written = compose.write_artifacts(_load_config(project_dir), project_dir)
    console.print("Regenere : " + ", ".join(p.name for p in written))


@app.command(help=t("Rejoue uniquement le cablage sur une stack deja demarree. Idempotent."))
def wire(project_dir: Path = typer.Option(Path("."), help=t("Repertoire du stack.yml."))) -> None:
    """Rejoue uniquement le cablage sur une stack deja demarree. Idempotent."""
    cfg = _load_config(project_dir)
    cfg.project_dir = project_dir

    # DEMARREE n'est pas PRETE, et la nuance coute cher. Un Sonarr neuf passe
    # une minute ou plus dans ses migrations de base ; pendant ce temps son port
    # est publie mais rien n'ecoute derriere. Le cablage tombait alors sur
    # « Server disconnected without sending a response », un message qui envoie
    # chercher une panne reseau la ou il n'y a qu'une attente. `install`
    # attendait deja ; `wire` non, alors que c'est LA commande qu'on lance pour
    # reparer un cablage incomplet.
    # L'arborescence AVANT le cablage. Une bibliotheque ajoutee au catalogue
    # n'avait aucun effet sur une installation existante : `install` cree les
    # dossiers, `wire` non, et Sonarr refuse net un dossier racine absent —
    # « Path '/data/media/anime' does not exist ». Constate en reparant une pile
    # reelle apres l'ajout de l'anime. `create_tree` est idempotent : sur une
    # installation a jour il ne cree rien et ne dit rien.
    nouveaux = create_tree(cfg.data_root, cfg.config_root, list(cfg.services))
    if nouveaux:
        console.print(f"  [dim]arborescence[/dim] {len(nouveaux)} dossier(s) cree(s)")

    def _attente(etape: orchestrator.Progress) -> None:
        console.print(f"  [dim]{etape.phase}[/dim] {etape.message}")

    # Une attente qui expire, une cle refusee : ces echecs se RACONTENT, ils ne
    # se jettent pas. `wire` rendait une trace Python et « Failed to execute
    # script 'launcher' », ce qui n'apprend rien a qui vient reparer sa stack.
    # `install` traitait deja le cas ; `wire` non.
    try:
        orchestrator.wait_for_arrs(cfg, _attente)
        orchestrator.wait_for_download_clients(cfg, _attente)
    except Exception as exc:
        journal.LOGGER.exception("attente des services")
        console.print(f"[red]{exc}[/red]")
        console.print("[dim]Diagnostic : `plugarr doctor`[/dim]")
        raise typer.Exit(1) from exc

    wirer = Wirer(cfg)
    try:
        results = wirer.execute(on_step=report.print_step)
    except Exception as exc:
        journal.LOGGER.exception("cablage")
        console.print(f"[red]{type(exc).__name__} : {exc}[/red]")
        console.print("[dim]Diagnostic : `plugarr doctor`[/dim]")
        raise typer.Exit(1) from exc
    finally:
        wirer.close()
    compose.write_artifacts(cfg, project_dir)
    report.print_final(cfg, results)
    raise typer.Exit(0 if all(r.ok for r in results) else 2)


@app.command(help=t("Aligne une installation ancienne sur cette version de PlugArr."))
def upgrade(
    project_dir: Path = typer.Option(Path("."), help=t("Repertoire du stack.yml.")),
    yes: bool = typer.Option(False, "--yes", "-y", help=t("Ne pas demander confirmation.")),
    dry_run: bool = typer.Option(False, "--dry-run", help=t("Montrer le plan, ne rien faire.")),
    skip_wire: bool = typer.Option(
        False, "--skip-wire", help=t("Ne pas rejouer le cablage a la fin.")
    ),
) -> None:
    """Aligne une installation ancienne sur cette version de PlugArr.

    Quatre choses, dans cet ordre, parce qu'il compte : migrer `stack.yml`,
    aligner les images sur le catalogue, regenerer les artefacts, puis rejouer
    le cablage.

    Le cablage passe en DERNIER : une etape de cablage ajoutee depuis peut
    dependre d'une image plus recente, l'inverse jamais.

    Rien n'est ecrit avant le recapitulatif, comme pour `install`.
    """
    cfg = _load_config(project_dir)
    cfg.project_dir = project_dir

    # En premier, avant meme de parler des images : aligner les services sur le
    # catalogue d'un binaire perime n'a qu'un interet limite, et l'utilisateur
    # doit le savoir avant de lire le reste.
    _annoncer_nouvelle_version()

    retenus, ecartes = pack.ecarts(cfg)

    from rich.table import Table

    if retenus:
        table = Table(title=t("Images a aligner sur le catalogue"))
        for col in (t("Service"), t("Installee"), t("Catalogue")):
            table.add_column(col, overflow="fold")
        for ecart in retenus:
            table.add_row(
                catalog.get(ecart.service).display_name,
                ecart.tag_installe,
                ecart.tag_catalogue + (f" [dim]({t('meme version, re-epinglee')})[/dim]"
                                       if ecart.meme_tag else ""),
            )
        console.print(table)
    else:
        console.print(t("[green]Les images sont deja celles du catalogue.[/green]"))

    # Ce qui est ECARTE compte autant : sans cette liste, un service saute en
    # silence et l'utilisateur croit tout aligne.
    for raison in ecartes:
        console.print(f"[dim]{t('ignore')} : {raison}[/dim]")

    if not retenus:
        if skip_wire:
            console.print(t("[dim]Rien a faire.[/dim]"))
            raise typer.Exit(0)
        console.print(t("[dim]Le cablage est rejoue quand meme : il est idempotent.[/dim]"))

    if dry_run:
        console.print(t("[cyan]--dry-run : rien n'a ete ecrit.[/cyan]"))
        raise typer.Exit(0)

    if retenus and not yes and not typer.confirm(
        t("Appliquer ces {nombre} mise(s) a jour ?", nombre=len(retenus)), default=True
    ):
        raise typer.Exit(1)

    chemin_journal = journal.start(project_dir, "upgrade")
    journal.config(cfg)

    runner = Compose(project_dir, cfg.project_name)
    if retenus:
        pack.appliquer(cfg, retenus)
        compose.write_artifacts(cfg, project_dir)
        for ecart in retenus:
            ok, message = runner.pull(ecart.service)
            if not ok:
                console.print(
                    t(
                        "[red]{service} : telechargement echoue[/red]",
                        service=ecart.service,
                    )
                )
                console.print(f"[dim]{message[:300]}[/dim]")
                continue
            ok, message = runner.recreate(ecart.service)
            marque = "[green]OK[/green]" if ok else "[red]" + t("ECHEC") + "[/red]"
            console.print(
                f"  {marque}  {ecart.service} "
                f"{ecart.tag_installe} -> {ecart.tag_catalogue}"
            )
            if not ok:
                console.print(f"[dim]{message[:300]}[/dim]")

    if skip_wire:
        console.print(t("[dim]Journal detaille : {chemin}[/dim]", chemin=chemin_journal))
        raise typer.Exit(0)

    # Le cablage rejoue TOUT, et c'est voulu : il est idempotent, et une etape
    # ajoutee depuis l'installation d'origine n'est visible qu'en la rejouant.
    # Tenir un registre des « etapes qui ont change depuis la version X »
    # coutrait cher pour ne gagner que du temps d'execution.
    console.print(t("[dim]Rejeu du cablage...[/dim]"))
    cfg.project_dir = project_dir
    wirer = Wirer(cfg)
    try:
        results = wirer.run(on_step=report.print_step)
    finally:
        wirer.close()
    report.print_final(cfg, results)
    console.print(t("[dim]Journal detaille : {chemin}[/dim]", chemin=chemin_journal))
    raise typer.Exit(0 if all(r.ok for r in results) else 2)


@app.command(help=t("Page d'administration : etat des services, demarrer / arreter / redemarrer."))
def serve(
    project_dir: Path = typer.Option(Path("."), help=t("Repertoire du stack.yml.")),
    host: str = typer.Option("127.0.0.1", help=t("Adresse d'ecoute.")),
    port: int = typer.Option(7373, help=t("Port d'ecoute.")),
    open_page: bool = typer.Option(True, "--open/--no-open", help=t("Ouvrir le navigateur.")),
) -> None:
    """Page d'administration : etat des services, demarrer / arreter / redemarrer.

    Ecoute sur 127.0.0.1 par defaut. L'acces exige un jeton tire au hasard a
    chaque demarrage : il est dans l'URL affichee ci-dessous.
    """
    cfg = _load_config(project_dir)
    token = admin.generate_token()

    if host not in ("127.0.0.1", "localhost"):
        console.print(
            t(
                "[yellow]Ecoute sur {hote} : la page sera joignable depuis le "
                "reseau.[/yellow]\n"
                "[dim]Elle permet d'arreter vos services et affiche vos "
                "identifiants. Le jeton est la seule protection ; ne partagez "
                "pas l'URL.[/dim]",
                hote=host,
            )
        )

    def ready(url: str, _token: str) -> None:
        console.print(f"\nAdministration : [bold]{url}[/bold]")
        console.print("[dim]Le jeton change a chaque demarrage. Ctrl+C pour arreter.[/dim]")
        if open_page:
            import webbrowser

            try:
                webbrowser.open(url)
            except Exception:  # noqa: BLE001
                # Pas de navigateur ici : cas normal sur un NAS. L'URL est affichee.
                console.print("[dim]Aucun navigateur : ouvrez l'URL ci-dessus.[/dim]")

    try:
        admin.serve(cfg, project_dir, host=host, port=port, token=token, on_ready=ready)
    except OSError as exc:
        console.print(
            t(
                "[red]Impossible d'ecouter sur {hote}:{port} : {erreur}[/red]",
                hote=host,
                port=port,
                erreur=exc,
            )
        )
        raise typer.Exit(1) from exc
    console.print("Serveur arrete.")


@app.command("admin-password", help=t("Pose le mot de passe de la page d'administration."))
def admin_password(
    project_dir: Path = typer.Option(Path("."), help=t("Repertoire du stack.yml.")),
    clear: bool = typer.Option(False, "--clear", help=t("Retirer le mot de passe.")),
) -> None:
    """Pose le mot de passe de la page d'administration.

    Sans mot de passe, la console n'accepte que le jeton tire a chaque
    demarrage : c'est parfait pour un lancement a la main, ou le jeton s'affiche
    juste au-dessus de l'URL. Cela ne convient plus des qu'elle tourne en
    permanence — personne n'ira lire un journal pour retrouver un jeton.

    Le mot de passe n'est JAMAIS ecrit en clair : seule son empreinte rejoint
    `stack.yml`, avec PBKDF2 et 600 000 iterations.
    """
    cfg = _load_config(project_dir)

    if clear:
        cfg.admin_password_hash = ""
        compose.write_artifacts(cfg, project_dir)
        console.print("Mot de passe retire. Seul le jeton de session ouvre desormais la console.")
        return

    mot_de_passe = typer.prompt(
        t("Nouveau mot de passe"), hide_input=True, confirmation_prompt=True
    )
    if len(mot_de_passe) < 8:
        console.print("[red]Huit caracteres au minimum.[/red]")
        raise typer.Exit(1)

    cfg.admin_password_hash = adminauth.hash_password(mot_de_passe)
    compose.write_artifacts(cfg, project_dir)
    console.print(
        "Mot de passe enregistre. La console demandera desormais ce mot de passe, "
        "et acceptera toujours le jeton affiche par `plugarr serve`."
    )


@app.command(help=t("Lance la console d'administration a chaque ouverture de session."))
def autostart(
    project_dir: Path = typer.Option(Path("."), help=t("Repertoire du stack.yml.")),
    disable: bool = typer.Option(False, "--disable", help=t("Retirer le lancement automatique.")),
    host: str = typer.Option("127.0.0.1", help=t("Adresse d'ecoute de la console.")),
    port: int = typer.Option(7373, help=t("Port d'ecoute de la console.")),
) -> None:
    """Lance la console d'administration a chaque ouverture de session.

    Sur l'HOTE, pas dans un conteneur. La console doit creer et demarrer des
    conteneurs : un conteneur qui en est capable peut monter la racine de la
    machine et tourner en root. L'y enfermer reviendrait a exposer sur le reseau
    un service aux pleins pouvoirs, sans rien gagner.

    Ici elle tourne sous votre compte, ecoute sur 127.0.0.1, et reste hors du
    reseau Docker.
    """
    cfg = _load_config(project_dir)
    etat = autostart_mod.status(project_dir)

    if disable:
        ok, message = autostart_mod.disable(project_dir)
        console.print(message if ok else f"[red]{message}[/red]")
        raise typer.Exit(0 if ok else 1)

    # Verrou : sans mot de passe, la console n'accepte que le jeton tire a chaque
    # demarrage. Lancee toute seule, ce jeton n'est lu par personne — la console
    # serait donc strictement inutilisable. Autant le dire avant de l'installer.
    if not cfg.admin_password_hash:
        console.print("[yellow]Aucun mot de passe n'est pose sur la console.[/yellow]")
        console.print(
            "[dim]Lancee automatiquement, elle n'afficherait son jeton dans aucun "
            "terminal : personne ne pourrait y entrer. Posez-en un d'abord :[/dim]"
        )
        console.print("  plugarr admin-password")
        raise typer.Exit(1)

    if etat.actif:
        console.print(
            t("[dim]Deja installe : {chemin}. Reecriture.[/dim]", chemin=etat.chemin)
        )

    ok, message = autostart_mod.enable(project_dir, host=host, port=port)
    if not ok:
        console.print(f"[yellow]{message}[/yellow]")
        raise typer.Exit(1)

    console.print(message)
    console.print(
        t(
            "[dim]Console : http://{hote}:{port} — au prochain demarrage "
            "de session.[/dim]",
            hote=host,
            port=port,
        )
    )
    if autostart_mod.mecanisme() == "systemd-utilisateur":
        console.print(
            "[dim]Une unite utilisateur s'arrete a la deconnexion. Pour qu'elle "
            "survive :[/dim]"
        )
        console.print("  loginctl enable-linger $USER")


@app.command(help=t("Archive la configuration complete : projet, CONFIG_ROOT et volumes."))
def backup(
    project_dir: Path = typer.Option(Path("."), help=t("Repertoire du stack.yml.")),
    out: Path | None = typer.Option(None, "--out", "-o", help=t("Fichier d'archive a ecrire.")),
    live: bool = typer.Option(
        False,
        "--live",
        help=t("Ne PAS arreter les conteneurs. Plus rapide, et la sauvegarde peut etre corrompue."),
    ),
) -> None:
    """Archive la configuration complete : projet, CONFIG_ROOT et volumes."""
    cfg = _load_config(project_dir)
    destination = Path(out) if out else project_dir / sauvegarde.nom_par_defaut(cfg)

    if live:
        console.print(
            "[yellow]Sauvegarde a chaud.[/yellow] Une base SQLite copiee pendant qu'on "
            "ecrit dedans donne un fichier valide en apparence et inutilisable en "
            "pratique. Sans --live, PlugArr arrete les conteneurs le temps de la copie."
        )

    rapport = sauvegarde.sauvegarder(
        cfg,
        project_dir,
        destination,
        live=live,
        on_progress=lambda m: console.print(f"  [dim]{m}[/dim]"),
    )

    from rich.table import Table

    table = Table(title="Sauvegarde")
    for col in ("", ""):
        table.add_column(col, overflow="fold")
    table.add_row("Archive", str(rapport.archive))
    table.add_row("Taille", f"{rapport.archive.stat().st_size / 1_048_576:.1f} Mo")
    table.add_row("Fichiers", str(rapport.fichiers))
    table.add_row("Services", ", ".join(rapport.services))
    table.add_row("Volumes", ", ".join(rapport.volumes) or "aucun")
    console.print(table)
    console.print(
        "[yellow]Cette archive contient vos mots de passe et vos cles API en clair.[/yellow]\n"
        "[dim]Elle est en lecture seule pour vous (chmod 600). Rangez-la comme un secret.[/dim]"
    )
    console.print(
        t(
            "[dim]Vos medias dans {racine} ne sont PAS dedans, et c'est "
            "voulu.[/dim]",
            racine=cfg.data_root,
        )
    )


@app.command(help=t("Repose une sauvegarde. N'ecrit RIEN dans DATA_ROOT."))
def restore(
    archive: Path = typer.Argument(..., help=t("Archive produite par `plugarr backup`.")),
    project_dir: Path = typer.Option(Path("."), help=t("Ou reposer le projet.")),
    config_root: str | None = typer.Option(
        None, help=t("Restaurer AILLEURS que l'origine. Les chemins sont reecrits.")
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help=t("Ne pas demander confirmation.")),
) -> None:
    """Repose une sauvegarde. N'ecrit RIEN dans DATA_ROOT."""
    archive = Path(archive)
    if not archive.is_file():
        console.print(t("[red]{fichier} introuvable.[/red]", fichier=archive))
        raise typer.Exit(1)
    try:
        manifeste = sauvegarde.lire_manifeste(archive)
    except (ValueError, OSError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc

    cible = config_root or manifeste["config_root"]
    from rich.table import Table

    table = Table(title=t("Contenu de l'archive"))
    for col in ("", ""):
        table.add_column(col, overflow="fold")
    table.add_row(t("Date"), manifeste["date"])
    table.add_row(t("Pile"), manifeste["project_name"])
    table.add_row(t("Services"), ", ".join(manifeste["services"]))
    table.add_row(t("Volumes"), ", ".join(manifeste["volumes"]) or t("aucun"))
    table.add_row(t("Configuration vers"), cible)
    console.print(table)
    if manifeste.get("a_chaud"):
        console.print(
            "[yellow]Cette archive a ete prise A CHAUD, conteneurs en marche.[/yellow] "
            "Ses bases peuvent etre corrompues."
        )

    if not yes and not typer.confirm(
        t(
            "Ecraser la configuration dans {config} et le projet dans "
            "{projet} ?",
            config=cible,
            projet=project_dir,
        ),
        default=False,
    ):
        raise typer.Exit(0)

    sauvegarde.restaurer(
        archive,
        project_dir,
        config_root=config_root,
        on_progress=lambda m: console.print(f"  [dim]{m}[/dim]"),
    )
    console.print("[green]Restauration terminee.[/green]")
    console.print(
        t(
            "[dim]Demarrez la pile, puis `plugarr wire --project-dir "
            "{repertoire}` pour verifier que tout repond.[/dim]",
            repertoire=project_dir,
        )
    )


@app.command(help=t("Diagnostique une installation existante."))
def doctor(project_dir: Path = typer.Option(Path("."), help=t("Repertoire du stack.yml."))) -> None:
    """Diagnostique une installation existante."""
    cfg = _load_config(project_dir)
    _annoncer_nouvelle_version()
    if not report.print_checks(orchestrator.preflight(cfg, project_dir)):
        console.print("[red]Des controles bloquants ont echoue.[/red]")

    # La protection du trafic torrent AVANT l'etat des conteneurs : c'est la
    # reponse la plus attendue de ce diagnostic.
    fuites = vpncheck.verifier(cfg)
    if fuites:
        console.print("\nProtection VPN du trafic torrent :")
        report.print_checks(fuites)

    console.print("\nEtat des conteneurs :")
    console.print(Compose(project_dir, cfg.project_name).ps())

    console.print("Joignabilite des API :")
    for sid, inst in orchestrator.iter_selected(cfg):
        spec = catalog.get(sid)
        if spec.api_family != "arr":
            continue
        try:
            with ArrClient(
                inst.url(cfg.host), inst.api_key or "", api_version=spec.api_version, name=sid
            ) as client:
                console.print(f"  [green]OK[/green] {sid} {client.version}")
        except Exception as exc:  # noqa: BLE001
            console.print(f"  [red]ECHEC[/red] {sid} : {exc}")


@app.command(help=t("Arrete la stack. Ne touche JAMAIS a DATA_ROOT."))
def uninstall(
    project_dir: Path = typer.Option(Path("."), help=t("Repertoire du stack.yml.")),
    remove_config: bool = typer.Option(False, "--remove-config", help=t("Supprime CONFIG_ROOT.")),
) -> None:
    """Arrete la stack. Ne touche JAMAIS a DATA_ROOT."""
    cfg = _load_config(project_dir)
    if not remove_config:
        ok, message = Compose(project_dir, cfg.project_name).down()
        console.print(message if not ok else "Conteneurs arretes et supprimes.")
    else:
        if not typer.confirm(
            t(
                "Supprimer definitivement {chemin} (bases, historiques, "
                "reglages) ?",
                chemin=cfg.config_root,
            ),
            default=False,
        ):
            raise typer.Exit(0)
        if not typer.confirm(
            t("Confirmez une seconde fois : cette action est irreversible."),
            default=False,
        ):
            raise typer.Exit(0)
        # `-v` emporte AUSSI les volumes Docker. Sans lui, la base de Silo
        # survivrait a une desinstallation demandee comme totale : elle ne vit
        # pas sous CONFIG_ROOT mais dans un volume, pour des raisons de vitesse
        # (voir compose.PG_VOLUME). L'utilisateur qui demande tout doit tout
        # obtenir, pas presque tout.
        ok, message = Compose(project_dir, cfg.project_name).down(volumes=True)
        console.print(message if not ok else "Conteneurs et volumes supprimes.")

        import shutil

        shutil.rmtree(cfg.config_root, ignore_errors=True)
        console.print(f"{cfg.config_root} supprime.")
    console.print(
        t(
            "[dim]Vos medias dans {racine} n'ont pas ete touches.[/dim]",
            racine=cfg.data_root,
        )
    )


@app.command("langues", help=t("Langues d'interface acceptees."))
def langues_cmd() -> None:
    """Langues d'interface acceptees.

    Les *arr en connaissent 28 ; l'assistant n'en propose que sept, les plus
    courantes. Les autres restent accessibles par `--langue`.
    """
    from . import langues as langues_mod

    proposees = {lang.code for lang in langues_mod.PROPOSEES}
    console.print("[bold]Proposees dans l'assistant[/bold]")
    for lang in langues_mod.PROPOSEES:
        console.print(f"  {lang.code:4} {lang.nom}")
    autres = sorted(set(langues_mod.ARR_UI_LANGUAGE) - proposees)
    console.print("")
    console.print(
        t("[dim]Aussi acceptees par --langue : {codes}[/dim]", codes=", ".join(autres))
    )
    console.print(
        "[dim]Jellyfin et Silo acceptent tout code ISO ; la liste ci-dessus est "
        "celle que les *arr savent afficher.[/dim]"
    )


@app.command("vpn-providers", help=t("Liste les fournisseurs VPN acceptes par Gluetun."))
def vpn_providers() -> None:
    """Liste les fournisseurs VPN acceptes par Gluetun."""
    console.print("[dim]Liste obtenue de Gluetun v3.41.3 lui-meme, pas recopiee.[/dim]\n")
    for name in VPN_PROVIDERS:
        console.print(f"  {name}")


@app.command("list", help=t("Liste le catalogue."))
def list_services() -> None:
    """Liste le catalogue."""
    from rich.table import Table

    table = Table(title="Catalogue")
    for col in ("id", "Nom", "Categorie", "Image", "Port", "Notes"):
        table.add_column(col, overflow="fold")
    for sid in catalog.STARTUP_ORDER:
        spec = catalog.get(sid)
        table.add_row(
            spec.id,
            spec.display_name,
            spec.category.value,
            spec.image,
            # Un service sans interface web ne publie rien : « 0 » se lirait comme
            # un port, pas comme une absence.
            str(spec.default_host_port or "-"),
            spec.notes,
        )
    console.print(table)


@app.command("templates", help=t("Liste les profils de qualite TRaSH proposables a Recyclarr."))
def list_templates(
    config_root: str | None = typer.Option(
        None, help=t("Racine des configurations, pour lire le manifeste deja clone.")
    ),
) -> None:
    """Liste les profils de qualite TRaSH proposables a Recyclarr."""
    from rich.table import Table

    config_dir = Path(config_root) / "recyclarr" if config_root else None
    names, problem = recyclarr_cfg.available_templates(config_dir)
    if problem:
        console.print(f"[red]{problem}[/red]")
        raise typer.Exit(1)

    table = Table(title="Templates officiels Recyclarr")
    table.add_column("Service")
    table.add_column("Template", overflow="fold")
    table.add_column("Defaut")
    for service in sorted(names):
        default = recyclarr_cfg.DEFAULT_TEMPLATES.get(service, "")
        for name in names[service]:
            table.add_row(service, name, "oui" if name == default else "")
    console.print(table)
    console.print(
        "[dim]Choix a l'installation : "
        "`plugarr install --recyclarr-sonarr <nom> --recyclarr-radarr <nom>`.[/dim]"
    )


if __name__ == "__main__":
    app()
