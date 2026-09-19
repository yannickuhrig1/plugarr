"""Reprise des indexeurs depuis une sauvegarde Prowlarr.

Demande a l'usage : a la selection des indexeurs, pouvoir charger la
sauvegarde d'un Prowlarr precedent — installe par PlugArr ou non — plutot que
de ressaisir chaque cle a la main.

**On ne restaure pas la base.** Prowlarr sait restaurer une sauvegarde
(`system/backup/restore`), mais il remplace alors TOUTE sa base : les
Applications qui relient Sonarr et Radarr, et le client qBittorrent que PlugArr
vient de cabler. L'installation fraiche perdrait ses liens au profit de ceux de
l'ancienne machine, avec ses anciennes adresses et ses anciens mots de passe.
Ce module lit donc la table `Indexers` et rien d'autre ; l'ajout passe ensuite
par l'API, indexeur par indexeur, comme une saisie manuelle.

Format verifie sur une vraie sauvegarde Prowlarr 2.5.2 et sur une archive
`plugarr backup` :

- la sauvegarde Prowlarr est un zip avec `prowlarr.db` et `config.xml` a la
  racine ; l'archive PlugArr porte la meme base dans
  `config/prowlarr/prowlarr.db` ;
- la colonne `Settings` est le JSON des reglages, en camelCase. Les champs
  propres a une definition Cardigann vivent sous `extraFieldData`, les autres
  sont a plat ou groupes (`baseSettings`, `torrentBaseSettings`).

L'API de Prowlarr 2.5.2 nomme ces memes champs `apikey` (pas
`extraFieldData.apikey`) et `baseSettings.limitsUnit` : c'est la
correspondance que fait `valeurs_api`.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .clients.prowlarr import IndexerDefinition, ProwlarrIndexers
from .i18n import t

#: Emplacements de la base dans les deux formats connus.
MEMBRES = ("prowlarr.db", "config/prowlarr/prowlarr.db")

#: Plafond de la base extraite. Une base Prowlarr pese quelques dizaines de Mo ;
#: le plafond protege d'une archive qui annoncerait des gigaoctets a decompresser.
TAILLE_BASE_MAX = 1024 * 1024 * 1024

ENTETE_SQLITE = b"SQLite format 3\x00"

#: Tables lues pour le rapport, jamais importees. Les nommer permet de dire a
#: l'utilisateur ce qui reste volontairement derriere.
TABLES_IGNOREES = {
    "Applications": "applications",
    "DownloadClients": "download_clients",
    "IndexerProxies": "proxies",
    "Notifications": "notifications",
}

_COLONNES = ("Name", "Implementation", "Settings", "ConfigContract", "Enable", "Priority")


@dataclass(frozen=True)
class IndexeurSauvegarde:
    """Un indexeur tel que la sauvegarde le decrit.

    `settings` contient les identifiants de l'utilisateur : il ne doit jamais
    sortir du serveur, ni partir dans un journal.
    """

    name: str
    implementation: str
    config_contract: str
    enable: bool
    priority: int
    redirect: bool
    settings: dict
    app_profile: str | None = None
    tags: tuple[str, ...] = ()
    #: (nom, implementation) du client de telechargement propre a l'indexeur,
    #: dans l'ANCIENNE base. None si l'indexeur utilise le client par defaut.
    download_client: tuple[str, str] | None = None

    @property
    def definition_file(self) -> str:
        valeur = self.settings.get("definitionFile")
        return valeur if isinstance(valeur, str) else ""

    def valeurs_api(self) -> dict[str, Any]:
        """Reglages sous les noms de champs de l'API Prowlarr."""
        valeurs: dict[str, Any] = {}
        extra = self.settings.get("extraFieldData")
        if isinstance(extra, dict):
            valeurs.update(extra)
        for cle, valeur in self.settings.items():
            if cle == "extraFieldData":
                continue
            if isinstance(valeur, dict):
                for sous_cle, sous_valeur in valeur.items():
                    valeurs[f"{cle}.{sous_cle}"] = sous_valeur
            else:
                valeurs[cle] = valeur
        return valeurs


@dataclass
class SauvegardeProwlarr:
    source: str  # "prowlarr", "plugarr" ou "base"
    indexeurs: list[IndexeurSauvegarde]
    ignores: dict[str, int] = field(default_factory=dict)


def lire(chemin: Path) -> SauvegardeProwlarr:
    """Lit les indexeurs d'une sauvegarde Prowlarr, d'une archive PlugArr ou
    d'un `prowlarr.db` seul. Leve ValueError si le fichier n'en est pas un."""
    dossier = Path(tempfile.mkdtemp(prefix="plugarr-prowlarr-"))
    try:
        base, source = _extraire(chemin, dossier)
        return _lire_base(base, source)
    finally:
        shutil.rmtree(dossier, ignore_errors=True)


def _extraire(chemin: Path, dossier: Path) -> tuple[Path, str]:
    with open(chemin, "rb") as fichier:
        entete = fichier.read(len(ENTETE_SQLITE))
    base = dossier / "prowlarr.db"
    if entete == ENTETE_SQLITE:
        shutil.copyfile(chemin, base)
        return base, "base"
    if not zipfile.is_zipfile(chemin):
        raise ValueError(
            "Ce fichier n'est ni une sauvegarde Prowlarr, ni une archive PlugArr."
        )
    try:
        with zipfile.ZipFile(chemin) as archive:
            noms = set(archive.namelist())
            membre = next((nom for nom in MEMBRES if nom in noms), None)
            if membre is None:
                raise ValueError(
                    "Aucune base Prowlarr dans cette archive "
                    "(prowlarr.db ou config/prowlarr/prowlarr.db attendu)."
                )
            # Le journal WAL porte les dernieres ecritures quand la sauvegarde a
            # ete prise a chaud : sans lui, les indexeurs ajoutes en dernier
            # manqueraient sans que rien ne le signale.
            for suffixe in ("", "-wal", "-shm"):
                if membre + suffixe in noms:
                    _copier_membre(archive, membre + suffixe, dossier / ("prowlarr.db" + suffixe))
    except zipfile.BadZipFile as exc:
        raise ValueError("Archive zip illisible ou incomplete.") from exc
    source = "plugarr" if PurePosixPath(membre).parent.name == "prowlarr" else "prowlarr"
    return base, source


def _copier_membre(archive: zipfile.ZipFile, membre: str, cible: Path) -> None:
    """Copie bornee : on compte les octets reellement decompresses plutot que de
    croire la taille annoncee par l'archive."""
    if archive.getinfo(membre).file_size > TAILLE_BASE_MAX:
        raise ValueError("Base Prowlarr trop volumineuse pour etre lue.")
    ecrits = 0
    with archive.open(membre) as source, open(cible, "wb") as destination:
        while morceau := source.read(1024 * 1024):
            ecrits += len(morceau)
            if ecrits > TAILLE_BASE_MAX:
                raise ValueError("Base Prowlarr trop volumineuse pour etre lue.")
            destination.write(morceau)


def _lire_base(base: Path, source: str) -> SauvegardeProwlarr:
    try:
        # `closing` et non `with connect()` : ce dernier ne ferme pas la base,
        # et Windows refuse ensuite de supprimer le dossier temporaire.
        with closing(sqlite3.connect(base)) as db:
            tables = {ligne[0] for ligne in db.execute("select name from sqlite_master where type='table'")}
            if "Indexers" not in tables:
                raise ValueError("Cette base ne contient pas de table d'indexeurs Prowlarr.")
            colonnes = {ligne[1] for ligne in db.execute("PRAGMA table_info(Indexers)")}
            manquantes = [c for c in _COLONNES if c not in colonnes]
            if manquantes:
                raise ValueError(
                    "Format de base Prowlarr inconnu (colonnes absentes : "
                    + ", ".join(manquantes) + ")."
                )
            profils = _correspondance(db, tables, "AppSyncProfiles", "Name")
            etiquettes = _correspondance(db, tables, "Tags", "Label")
            clients = (
                {i: (n, impl) for i, n, impl in db.execute("select Id, Name, Implementation from DownloadClients")}
                if "DownloadClients" in tables
                else {}
            )
            optionnelles = [c for c in ("Redirect", "AppProfileId", "Tags", "DownloadClientId") if c in colonnes]
            requete = "select " + ", ".join(_COLONNES + tuple(optionnelles)) + " from Indexers order by Id"
            indexeurs = [
                _indexeur(dict(zip(_COLONNES + tuple(optionnelles), ligne, strict=True)), profils, etiquettes, clients)
                for ligne in db.execute(requete)
            ]
            ignores = {
                cle: db.execute(f"select count(*) from {table}").fetchone()[0]
                for table, cle in TABLES_IGNOREES.items()
                if table in tables
            }
    except sqlite3.DatabaseError as exc:
        raise ValueError("Base Prowlarr illisible ou corrompue.") from exc
    return SauvegardeProwlarr(source=source, indexeurs=indexeurs, ignores=ignores)


def _correspondance(db, tables: set[str], table: str, colonne: str) -> dict[int, str]:
    if table not in tables:
        return {}
    return dict(db.execute(f"select Id, {colonne} from {table}"))


def _indexeur(ligne: dict, profils: dict, etiquettes: dict, clients: dict) -> IndexeurSauvegarde:
    try:
        settings = json.loads(ligne["Settings"] or "{}")
    except (TypeError, ValueError):
        settings = {}
    try:
        tags = json.loads(ligne.get("Tags") or "[]")
    except (TypeError, ValueError):
        tags = []
    return IndexeurSauvegarde(
        name=str(ligne["Name"] or "?"),
        implementation=str(ligne["Implementation"] or ""),
        config_contract=str(ligne["ConfigContract"] or ""),
        enable=bool(ligne["Enable"]),
        priority=int(ligne["Priority"] or 25),
        redirect=bool(ligne.get("Redirect") or False),
        settings=settings if isinstance(settings, dict) else {},
        app_profile=profils.get(ligne.get("AppProfileId")),
        tags=tuple(etiquettes[t] for t in tags if isinstance(t, int) and t in etiquettes),
        download_client=clients.get(ligne.get("DownloadClientId") or 0),
    )


# -- confrontation avec le Prowlarr installe ----------------------------------

IMPORTABLE = "importable"
CONFIGURE = "configure"
INCONNU = "inconnu"


def _definition_file(raw: dict) -> str:
    for champ in raw.get("fields", []):
        if champ.get("name") == "definitionFile":
            return str(champ.get("value") or "")
    return ""


def definition_pour(entree: IndexeurSauvegarde, indexers: ProwlarrIndexers) -> IndexerDefinition | None:
    """Definition du Prowlarr installe qui correspond a l'indexeur sauvegarde.

    Cardigann : par `definitionFile`, unique pour chacune des 547 definitions
    de Prowlarr 2.5.2. Le nom ne suffit pas, l'utilisateur a pu le changer.
    Les autres (Newznab, Torznab...) : plusieurs preselections partagent une
    implementation ; le nom departage, sinon la premiere convient, puisque les
    reglages de la sauvegarde remplacent ceux de la preselection.
    """
    candidates = [d for d in indexers.definitions() if d.implementation == entree.implementation]
    if entree.definition_file:
        return next((d for d in candidates if _definition_file(d.raw) == entree.definition_file), None)
    nom = entree.name.casefold()
    return next((d for d in candidates if d.name.casefold() == nom), candidates[0] if candidates else None)


def deja_configure(entree: IndexeurSauvegarde, configures: list[dict]) -> bool:
    """Meme nom, ou meme definition Cardigann sous un autre nom. Un indexeur
    existant n'est jamais remplace : ses reglages actuels priment."""
    nom = entree.name.casefold()
    for existant in configures:
        if str(existant.get("name", "")).casefold() == nom:
            return True
        if entree.definition_file and _definition_file(existant) == entree.definition_file:
            return True
    return False


def examiner(sauvegarde: SauvegardeProwlarr, indexers: ProwlarrIndexers) -> list[tuple[IndexeurSauvegarde, str]]:
    configures = indexers.configured()
    resultat = []
    for entree in sauvegarde.indexeurs:
        if definition_pour(entree, indexers) is None:
            statut = INCONNU
        elif deja_configure(entree, configures):
            statut = CONFIGURE
        else:
            statut = IMPORTABLE
        resultat.append((entree, statut))
    return resultat


def charge_utile(
    entree: IndexeurSauvegarde, definition: IndexerDefinition, indexers: ProwlarrIndexers
) -> tuple[dict, list[str]]:
    """Requete d'ajout, et avertissements (noms seulement, jamais de valeurs).

    Les identifiants numeriques de la sauvegarde (profil, etiquettes, client de
    telechargement) designent des lignes de l'ANCIENNE base. Les recopier tels
    quels rattacherait l'indexeur a n'importe quoi — au pire a un client qui
    n'est pas le qBittorrent cable par PlugArr. Ils sont donc resolus par nom
    dans le Prowlarr installe, et abandonnes s'ils n'y existent pas.
    """
    valeurs = entree.valeurs_api()
    champs = definition.raw.get("fields", [])
    payload = dict(definition.raw)
    payload.pop("id", None)
    payload["fields"] = [
        {**champ, "value": valeurs[champ["name"]]}
        if champ.get("name") in valeurs and champ.get("type") != "info"
        else dict(champ)
        for champ in champs
    ]
    avertissements = []
    orphelins = sorted(set(valeurs) - {champ.get("name") for champ in champs})
    if orphelins:
        avertissements.append(
            t("reglages absents de cette version de la definition, ignores : {noms}", noms=", ".join(orphelins))
        )

    profils = {str(p.get("name", "")).casefold(): int(p["id"]) for p in indexers.app_profiles() if "id" in p}
    profil = profils.get((entree.app_profile or "").casefold())
    if profil is None:
        profil = indexers.app_profile_id()

    etiquettes = {str(e.get("label", "")).casefold(): int(e["id"]) for e in indexers.tags() if "id" in e}
    tags = [etiquettes[e.casefold()] for e in entree.tags if e.casefold() in etiquettes]
    absentes = [e for e in entree.tags if e.casefold() not in etiquettes]
    if absentes:
        avertissements.append(t("etiquettes absentes de ce Prowlarr, retirees : {noms}", noms=", ".join(absentes)))

    client = 0
    if entree.download_client:
        nom, implementation = entree.download_client
        client = next(
            (
                int(c["id"])
                for c in indexers.download_clients()
                if str(c.get("name", "")).casefold() == nom.casefold()
                and c.get("implementation") == implementation
                and "id" in c
            ),
            0,
        )
        if not client:
            avertissements.append(
                t("client de telechargement {nom} absent : client par defaut de Prowlarr", nom=nom)
            )

    payload.update(
        name=entree.name,
        enable=entree.enable,
        priority=entree.priority,
        redirect=entree.redirect,
        appProfileId=profil,
        tags=tags,
        downloadClientId=client,
    )
    return payload, avertissements


def importer(entree: IndexeurSauvegarde, indexers: ProwlarrIndexers) -> tuple[bool, str, list[str]]:
    """Ajoute un indexeur de la sauvegarde. Renvoie (succes, message, avertissements).

    Seul appel en ecriture : `POST indexer`. Prowlarr contacte l'indexeur pour
    valider, comme pour une saisie manuelle : un tracker ferme ou une cle
    revoquee echoue ici, sans empecher les suivants.
    """
    definition = definition_pour(entree, indexers)
    if definition is None:
        return False, t("definition absente de ce Prowlarr"), []
    if deja_configure(entree, indexers.configured()):
        return True, t("deja configure"), []
    payload, avertissements = charge_utile(entree, definition, indexers)
    ok, message = indexers.create(payload)
    return ok, message, avertissements
