"""Sous-commandes `plugarr indexers`.

Parite avec l'ecran de l'assistant : ce que l'on peut faire au clavier dans le
wizard doit rester scriptable. Les deux passent par ProwlarrIndexers.

plugarr ne fournit aucun indexeur : `search` interroge les definitions
embarquees par le Prowlarr de l'utilisateur.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from . import catalog, import_prowlarr, migrations, report
from .clients.arr import ArrClient
from .clients.prowlarr import ProwlarrIndexers
from .i18n import t

app = typer.Typer(help=t("Gerer vos indexeurs dans Prowlarr."), no_args_is_help=True)
console = report.console


def _open(project_dir: Path) -> tuple[ArrClient, ProwlarrIndexers]:
    path = project_dir / "stack.yml"
    if not path.exists():
        raise typer.BadParameter(f"{path} introuvable. Lancez d'abord `plugarr install`.")
    cfg, _notes = migrations.lire(path)
    if not cfg.enabled("prowlarr"):
        raise typer.BadParameter(t("Prowlarr n'est pas installe dans cette stack."))
    spec, inst = catalog.get("prowlarr"), cfg.services["prowlarr"]
    client = ArrClient(
        inst.url(cfg.host), inst.api_key or "", api_version=spec.api_version, name="prowlarr"
    )
    return client, ProwlarrIndexers(client)


@app.command()
def search(
    term: str = typer.Argument(..., help="Fragment du nom recherche."),
    project_dir: Path = typer.Option(Path("."), help="Repertoire du stack.yml."),
    limit: int = typer.Option(25, help="Nombre maximum de resultats."),
) -> None:
    """Cherche parmi les definitions embarquees par votre Prowlarr."""
    client, indexers = _open(project_dir)
    try:
        matches = indexers.search(term, limit)
        if not matches:
            console.print(f"Aucune definition ne correspond a {term!r}.")
            raise typer.Exit(1)
        table = Table(
            title=t(
                "{nombre} resultat(s) - source : votre Prowlarr",
                nombre=len(matches),
            )
        )
        for column in ("Nom", "Type", "Protocole", "Identifiants a fournir"):
            table.add_column(column, overflow="fold")
        for definition in matches:
            fields = [f.name for f in definition.editable_fields() if f.name != "baseUrl"]
            table.add_row(
                definition.name,
                definition.privacy,
                definition.protocol,
                ", ".join(fields) or "aucun",
            )
        console.print(table)
    finally:
        client.close()


@app.command("list")
def list_configured(
    project_dir: Path = typer.Option(Path("."), help="Repertoire du stack.yml."),
) -> None:
    """Liste les indexeurs deja configures dans Prowlarr."""
    client, indexers = _open(project_dir)
    try:
        configured = indexers.configured()
        if not configured:
            console.print(
                "Aucun indexeur configure.\n"
                "[dim]plugarr n'en fournit aucun : ajoutez les votres avec "
                "`plugarr indexers add`.[/dim]"
            )
            return
        table = Table(title=f"{len(configured)} indexeur(s) configure(s)")
        for column in ("id", "Nom", "Protocole", "Actif"):
            table.add_column(column)
        for entry in configured:
            table.add_row(
                str(entry.get("id", "?")),
                entry.get("name", "?"),
                entry.get("protocol", "?"),
                "oui" if entry.get("enable") else "non",
            )
        console.print(table)
    finally:
        client.close()


@app.command()
def add(
    name: str = typer.Argument(..., help=t("Nom exact de la definition (voir `search`).")),
    field: list[str] = typer.Option(
        [], "--field", "-f", help=t("Identifiant sous la forme cle=valeur. Repetable.")
    ),
    project_dir: Path = typer.Option(Path("."), help="Repertoire du stack.yml."),
) -> None:
    """Ajoute un indexeur avec VOS identifiants.

    Prowlarr contacte l'indexeur pour valider : sans reponse valide, rien n'est
    enregistre. Il n'existe pas d'ajout hors ligne.
    """
    client, indexers = _open(project_dir)
    try:
        definition = indexers.find(name)
        values: dict[str, str] = {}
        for pair in field:
            if "=" not in pair:
                raise typer.BadParameter(f"attendu cle=valeur, recu {pair!r}")
            key, _, value = pair.partition("=")
            values[key.strip()] = value

        expected = {f.name for f in definition.editable_fields()}
        unknown = sorted(set(values) - expected)
        if unknown:
            console.print(
                t(
                    "[yellow]Champs inconnus pour {indexeur}, ignores : "
                    "{inconnus}[/yellow]\n"
                    "[dim]Champs attendus : {attendus}[/dim]",
                    indexeur=definition.name,
                    inconnus=", ".join(unknown),
                    attendus=", ".join(sorted(expected)),
                )
            )

        missing = [
            f.name
            for f in definition.editable_fields()
            if f.name not in values and not f.prefill and f.secret
        ]
        if missing:
            console.print(
                f"[red]Identifiants manquants : {', '.join(missing)}[/red]\n"
                f"[dim]Exemple : plugarr indexers add \"{definition.name}\" "
                f"-f {missing[0]}=VOTRE_CLE[/dim]"
            )
            raise typer.Exit(1)

        console.print(f"Validation de {definition.name} par Prowlarr...")
        ok, message = indexers.add(definition, values)
        if ok:
            console.print(f"[green]{definition.name} : {message}[/green]")
        else:
            console.print(f"[red]{definition.name} : {message}[/red]")
            raise typer.Exit(2)
    finally:
        client.close()


@app.command("import")
def import_backup(
    backup: Path = typer.Argument(
        ..., exists=True, dir_okay=False, help=t("Sauvegarde Prowlarr (.zip), archive PlugArr ou prowlarr.db.")
    ),
    project_dir: Path = typer.Option(Path("."), help="Repertoire du stack.yml."),
    dry_run: bool = typer.Option(False, "--dry-run", help=t("Afficher ce qui serait importe, sans rien ecrire.")),
) -> None:
    """Reprend les indexeurs d'une sauvegarde, sans toucher aux liens existants.

    Seuls les indexeurs sont importes. Les applications et les clients de
    telechargement de la sauvegarde sont ignores : ceux cables par PlugArr
    restent en place. Un indexeur deja present n'est jamais remplace.
    """
    try:
        sauvegarde = import_prowlarr.lire(backup)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    client, indexers = _open(project_dir)
    echecs = 0
    try:
        for entree, statut in import_prowlarr.examiner(sauvegarde, indexers):
            if statut == import_prowlarr.INCONNU:
                console.print(t("[yellow]{nom} : definition absente de ce Prowlarr, ignore[/yellow]", nom=entree.name))
                continue
            if statut == import_prowlarr.CONFIGURE:
                console.print(t("[dim]{nom} : deja configure[/dim]", nom=entree.name))
                continue
            if dry_run:
                console.print(t("{nom} : serait importe", nom=entree.name))
                continue
            ok, message, avertissements = import_prowlarr.importer(entree, indexers)
            couleur = "green" if ok else "red"
            console.print(f"[{couleur}]{entree.name} : {message}[/{couleur}]")
            for avertissement in avertissements:
                console.print(f"  [yellow]{avertissement}[/yellow]")
            echecs += not ok
        ignores = ", ".join(f"{nom}={nombre}" for nom, nombre in sauvegarde.ignores.items() if nombre)
        if ignores:
            console.print(t("[dim]Non importes, volontairement : {liste}[/dim]", liste=ignores))
    finally:
        client.close()
    if echecs:
        raise typer.Exit(2)
