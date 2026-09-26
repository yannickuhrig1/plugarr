"""PlugArr Administration : les installations de ce poste, et ce qu'on en fait.

L'assistant installe puis s'efface, et chaque installation a sa propre console
(`plugarr serve`). Il manquait l'endroit qui les rassemble : quelqu'un qui a une
pile sur son PC et une autre sur son NAS devait retrouver deux dossiers, deux
lanceurs, et retaper une commande SSH pour joindre la seconde.

Le gestionnaire liste ce que ce poste connait :

- les installations **locales**, lues dans le registre (`registre.py`) ;
- les installations **distantes** posees d'ici par SSH (`distantes.py`).

Pour chacune : son etat, sa console, la mise a jour du pack, la sauvegarde, le
diagnostic. Les commandes longues (`upgrade`, `backup`, `doctor`) passent par
`plugarr` lui-meme en sous-processus : ce sont les chemins deja eprouves, et le
gestionnaire se contente d'afficher leur sortie.

**Une seule instance locale par Docker Desktop.** Deux piles sur le meme moteur
se disputent les noms de conteneurs et les ports du catalogue. Le gestionnaire
n'en propose donc pas une seconde : « Nouvelle installation » ouvre l'assistant,
qui retrouve la pile existante et propose de la reprendre.

Modele de securite, le meme que l'assistant web :

- ecoute sur 127.0.0.1, port tire au hasard ;
- jeton aleatoire passe dans le FRAGMENT de l'adresse (`#jeton=`), donc jamais
  dans une requete ; la page le renvoie en en-tete `Authorization` ;
- `Host` et `Origin` verifies : une page tierce ne peut pas piloter le
  gestionnaire par rebond DNS ;
- politique de contenu stricte, aucun script en ligne.

Le gestionnaire se ferme seul quand plus rien ne lui parle depuis deux minutes :
ni sa fenetre, ni les consoles qu'il heberge, ni une tache en cours.
"""

from __future__ import annotations

import contextlib
import hmac
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml

from . import (
    __version__,
    admin,
    catalog,
    chemins,
    coffre,
    compose,
    dashboard,
    distantes,
    fenetre,
    i18n,
    journal,
    migrations,
    pack,
    registre,
    remote_install,
    selfupdate,
)
from .i18n import phrase, t
from .models import StackConfig
from .runner import Compose, running_project_dir
from .tunnel import Tunnel

WEB = Path(__file__).resolve().parent / "web"

#: Ou le gestionnaire en cours note son adresse, pour qu'un second lancement
#: rouvre la fenetre au lieu de demarrer un second serveur.
FICHIER_VERROU = "gestionnaire.json"
#: Noms donnes aux installations locales. Le registre, lui, ne porte que des
#: chemins et reste lisible par les versions precedentes.
FICHIER_NOMS = "noms.yml"

#: Secondes sans aucune requete avant de se fermer.
INACTIVITE = 120.0
#: Intervalle de releve de l'etat des piles.
RAFRAICHISSEMENT = 10.0
#: Lignes gardees par tache : une sauvegarde bavarde ne doit pas remplir la
#: memoire, et la page n'affiche de toute facon que la fin.
MAX_LIGNES = 4000

ACTIONS_LOCALES = ("demarrer", "arreter", "pack", "sauvegarder", "diagnostic", "deplacer")
ACTIONS_DISTANTES = ("demarrer", "arreter", "pack")

#: Fichiers d'un dossier de projet, deplaces ensemble. Tout le reste du dossier
#: (l'executable lui-meme, les telechargements de l'utilisateur) reste en place.
FICHIERS_PROJET = (
    "docker-compose.yml",
    ".env",
    "stack.yml",
    ".gitignore",
    dashboard.FILENAME,
    dashboard.LAUNCHER_NAME,
    journal.FILENAME,
    ".plugarr-maintenance.json",
)
DOSSIERS_PROJET = ("backups", ".plugarr-remote")


# ----------------------------------------------------------------------- textes

#: Textes de la page. Poses cote Python et traduits au rendu : la console avait
#: accumule des libelles francais ecrits en dur dans son JavaScript, que
#: `scripts/audit_traductions.py` ne pouvait pas voir.
_TEXTES = {
    "rail": phrase("ADMINISTRATION"),
    "plus": phrase("Plus"),
    "titre": phrase("Mes installations"),
    "sousTitre": phrase(
        "Chaque installation PlugArr connue de ce poste, sur cet ordinateur ou sur un serveur."
    ),
    "nouvelle": phrase("Nouvelle installation"),
    "nouvelleLancee": phrase("L'assistant s'ouvre dans une nouvelle fenetre."),
    "actualiser": phrase("Actualiser"),
    "quitter": phrase("Fermer PlugArr"),
    "local": phrase("Cet ordinateur"),
    "ssh": phrase("Serveur"),
    "etat-en-marche": phrase("En marche"),
    "etat-partielle": phrase("En partie arretee"),
    "etat-arretee": phrase("Arretee"),
    "etat-docker-absent": phrase("Docker ne repond pas"),
    "etat-introuvable": phrase("Dossier introuvable"),
    "etat-illisible": phrase("stack.yml illisible"),
    "etat-version-future": phrase("Ecrite par une version plus recente de PlugArr"),
    "etat-deconnectee": phrase("Connexion requise"),
    "etat-injoignable": phrase("Docker refuse ou injoignable"),
    "etat-verification": phrase("Verification..."),
    "etat-autre-dossier": phrase("Pile lancee depuis un autre dossier"),
    "autreDossier": phrase(
        "Les conteneurs de cette pile tournent depuis {chemin}. Ils ne sont pas pilotes d'ici."
    ),
    "services": phrase("{n} sur {total} services en marche"),
    "packAJour": phrase("Pack a jour"),
    "packEcarts": phrase("{n} image(s) peuvent avancer"),
    "packInconnu": phrase("Pack inconnu"),
    "console": phrase("Console"),
    "demarrer": phrase("Demarrer"),
    "arreter": phrase("Arreter"),
    "pack": phrase("Mettre a jour le pack"),
    "sauvegarder": phrase("Sauvegarder"),
    "diagnostic": phrase("Diagnostiquer"),
    "dossier": phrase("Ouvrir le dossier"),
    "deplacer": phrase("Ranger dans le dossier PlugArr"),
    "renommer": phrase("Renommer"),
    "oublier": phrase("Retirer de la liste"),
    "connexion": phrase("Se connecter"),
    "deconnexion": phrase("Se deconnecter"),
    "oublierSecret": phrase("Oublier le mot de passe garde"),
    "packTitre": phrase("Mise a jour du pack"),
    "packIntro": phrase(
        "Les images que le catalogue de PlugArr {version} fait avancer. Rien ne redescend : "
        "une image deja plus recente est laissee telle quelle."
    ),
    "colService": phrase("Service"),
    "colInstallee": phrase("Installee"),
    "colCatalogue": phrase("Catalogue"),
    "ecartes": phrase("Laissees telles quelles"),
    "rienAFaire": phrase("Rien a mettre a jour : les images sont celles du catalogue, ou plus recentes."),
    "appliquer": phrase("Appliquer"),
    "annuler": phrase("Annuler"),
    "confirmer": phrase("Confirmer"),
    "enregistrer": phrase("Enregistrer"),
    "confirmerArreter": phrase("Arreter tous les services de {nom} ?"),
    "confirmerDeplacer": phrase(
        "Deplacer les fichiers de {nom} dans le dossier de PlugArr ? La pile est arretee le "
        "temps du deplacement, puis relancee. Vos medias ne bougent pas."
    ),
    "confirmerOublier": phrase(
        "Retirer {nom} de la liste ? Rien n'est supprime, ni sur le disque ni sur le serveur."
    ),
    "confirmerPack": phrase("Appliquer {n} mise(s) a jour a {nom} ? Les services concernes redemarrent."),
    "confirmerMaj": phrase(
        "Installer PlugArr {version} ? Les consoles ouvertes depuis ce gestionnaire se "
        "fermeront, puis PlugArr redemarrera."
    ),
    "connexionTitre": phrase("Connexion a {nom}"),
    "connexionIntro": phrase(
        "L'empreinte SSH confirmee a l'installation est verifiee avant tout echange."
    ),
    "empreinte": phrase("Empreinte attendue"),
    "motDePasse": phrase("Mot de passe SSH"),
    "clePrivee": phrase("Fichier de cle privee"),
    "phraseDePasse": phrase("Phrase de passe de la cle"),
    "sudo": phrase("Mot de passe sudo (facultatif)"),
    "seSouvenir": phrase("Se souvenir sur ce PC (chiffre par Windows pour votre compte)"),
    "renommerTitre": phrase("Nouveau nom"),
    "tache-en-cours": phrase("En cours"),
    "tache-reussie": phrase("Terminee"),
    "tache-echouee": phrase("Echec"),
    "journal": phrase("Journal"),
    "fermer": phrase("Fermer"),
    "majDispo": phrase("PlugArr {version} est disponible."),
    "majInstaller": phrase("Installer la mise a jour"),
    "majTelecharger": phrase("Voir la version"),
    "majLancee": phrase("Installation lancee : PlugArr va se fermer puis redemarrer."),
    "vide": phrase("Aucune installation connue sur ce poste."),
    "videAide": phrase(
        "Lancez l'assistant pour installer PlugArr sur cet ordinateur ou sur un serveur."
    ),
    "horsDossier": phrase("Fichiers hors du dossier de PlugArr"),
    "donnees": phrase("Donnees"),
    "erreurSession": phrase("Session absente ou expiree. Relancez PlugArr."),
    "erreurReseau": phrase("Le gestionnaire ne repond plus. Relancez PlugArr."),
    "fermeture": phrase("PlugArr est ferme. Vous pouvez fermer cette fenetre."),
}


def textes() -> dict[str, str]:
    return {cle: t(valeur) for cle, valeur in _TEXTES.items()}


# ------------------------------------------------------------------------ noms


def _lire_noms() -> dict[str, str]:
    try:
        brut = yaml.safe_load((chemins.racine() / FICHIER_NOMS).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(brut, dict):
        return {}
    return {str(k): str(v) for k, v in brut.items() if isinstance(v, str)}


def _ecrire_nom(ident: str, nom: str) -> None:
    noms = _lire_noms()
    if nom:
        noms[ident] = nom
    else:
        noms.pop(ident, None)
    fichier = chemins.racine() / FICHIER_NOMS
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text(yaml.safe_dump(noms, allow_unicode=True), encoding="utf-8")


def _nettoyer_nom(nom: str) -> str:
    return " ".join(str(nom).split())[:60]


# ----------------------------------------------------------------------- etats


def vue_pack(cfg: StackConfig) -> dict:
    retenus, ecartes = pack.ecarts(cfg)
    return {
        "retenus": [
            {
                "service": e.service,
                "nom": catalog.get(e.service).display_name,
                "installee": e.tag_installe,
                "catalogue": e.tag_catalogue,
                "meme_tag": e.meme_tag,
            }
            for e in retenus
        ],
        "ecartes": ecartes,
    }


def _resume(services: list[dict], moteur_ok: bool) -> str:
    en_marche = sum(1 for s in services if s["up"])
    if not moteur_ok:
        return "docker-absent"
    if services and en_marche == len(services):
        return "en-marche"
    if en_marche == 0:
        return "arretee"
    return "partielle"


def etat_local(inst: registre.Installation, dossiers: dict[str, str | None] | None = None) -> dict:
    """Etat d'une installation locale : pile, services, pack.

    `dossiers` garde, le temps d'un releve, le dossier d'ou tourne chaque nom
    de pile : le registre porte souvent plusieurs entrees nommees `plugarr`, et
    une seule question a Docker suffit pour toutes.
    """
    if not inst.vivante:
        return {"etat": "introuvable"}
    try:
        cfg, _notes = migrations.lire(inst.stack)
    except migrations.VersionFuture:
        return {"etat": "version-future"}
    except (ValueError, OSError):
        return {"etat": "illisible"}
    # Docker range les conteneurs par NOM de pile. Une ancienne installation
    # restee au registre, meme nom, autre dossier, afficherait sinon comme les
    # siens les conteneurs d'une autre - et ses boutons les piloteraient.
    # Constate le 26/09/2026 : une pile d'essai lancee depuis `dist\` montrait
    # « 5 sur 5 en marche » sur une entree qui n'avait jamais demarre.
    if dossiers is None:
        dossiers = {}
    if cfg.project_name not in dossiers:
        dossiers[cfg.project_name] = running_project_dir(cfg.project_name)
    ailleurs = dossiers[cfg.project_name]
    if ailleurs and _normaliser(ailleurs) != _normaliser(inst.project_dir):
        return {"etat": "autre-dossier", "ailleurs": ailleurs, "project_name": cfg.project_name}
    payload = admin.status_payload(cfg, Compose(inst.project_dir, cfg.project_name))
    services = [
        {"id": s["id"], "nom": s["name"], "up": s["up"], "statut": s["status"]}
        for s in payload["services"]
    ]
    return {
        "etat": _resume(services, payload["engine_available"]),
        "services": services,
        "pack": vue_pack(cfg),
        "project_name": cfg.project_name,
    }


def _service_du_label(labels: str) -> str:
    for morceau in str(labels or "").split(","):
        cle, _, valeur = morceau.partition("=")
        if cle.strip() == "com.docker.compose.service":
            return valeur.strip()
    return ""


def etat_distant(session, cfg: StackConfig) -> dict:
    """Etat d'une pile distante, lu par `docker ps` en lecture seule."""
    commande = (
        "docker ps --all --filter "
        + shlex.quote(f"label=com.docker.compose.project={cfg.project_name}")
        + " --format '{{json .}}'"
    )
    code, sortie, _erreur = session.run(commande)
    attendus = [sid for sid in catalog.STARTUP_ORDER if cfg.enabled(sid)]
    if cfg.vpn_enabled:
        attendus.append("gluetun")
    if code:
        return {"etat": "injoignable", "services": [], "pack": vue_pack(cfg)}
    vus: dict[str, dict] = {}
    for ligne in sortie.splitlines():
        try:
            entree = json.loads(ligne)
        except json.JSONDecodeError:
            continue
        if isinstance(entree, dict):
            nom = _service_du_label(entree.get("Labels", ""))
            if nom:
                vus[nom] = entree
    services = []
    for sid in attendus:
        entree = vus.get(sid) or {}
        statut = str(entree.get("Status", "")).lower()
        up = (
            str(entree.get("State", "")).lower() == "running"
            and "unhealthy" not in statut
            and "health: starting" not in statut
        )
        services.append(
            {
                "id": sid,
                "nom": "Gluetun" if sid == "gluetun" else catalog.get(sid).display_name,
                "up": up,
                "statut": str(entree.get("Status", "")) or "conteneur absent",
            }
        )
    return {"etat": _resume(services, True), "services": services, "pack": vue_pack(cfg)}


# ----------------------------------------------------------------------- taches


@dataclass
class Tache:
    ident: str
    instance: str
    action: str
    statut: str = "en-cours"
    lignes: list[str] = field(default_factory=list)
    message: str = ""
    debut: float = field(default_factory=time.time)
    fin: float | None = None

    def ecrire(self, ligne: str) -> None:
        ligne = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", str(ligne)).rstrip()
        if not ligne:
            return
        self.lignes.append(ligne)
        if len(self.lignes) > MAX_LIGNES:
            del self.lignes[: len(self.lignes) - MAX_LIGNES]

    def vue(self, *, lignes: int = 200) -> dict:
        return {
            "id": self.ident,
            "instance": self.instance,
            "action": self.action,
            "statut": self.statut,
            "message": self.message,
            "lignes": self.lignes[-lignes:],
            "debut": self.debut,
            "fin": self.fin,
        }


class _SansFermeture:
    """Prete une session ouverte aux fonctions de `remote_install`, qui ferment
    la leur a la fin. La session du gestionnaire doit leur survivre."""

    def __init__(self, session):
        self._session = session
        self.fingerprint = session.fingerprint

    def run(self, command, *, stdin=None):
        return self._session.run(command, stdin=stdin)

    def run_stream(self, command, on_line):
        return self._session.run_stream(command, on_line)

    def upload(self, path, data, *, mode=0o600):
        return self._session.upload(path, data, mode=mode)

    def close(self) -> None:
        return None


@dataclass
class Connexion:
    """Une installation distante ouverte : session SSH, pile lue, tunnel."""

    distante: distantes.Distante
    session: object
    identifiants: remote_install.RemoteCredentials
    cfg: StackConfig | None = None
    stack_sha: str = ""
    tunnel: Tunnel | None = None

    @property
    def cible(self) -> remote_install.RemoteTarget:
        return remote_install.RemoteTarget(
            host=self.distante.host,
            port=self.distante.port,
            username=self.distante.user,
            expected_fingerprint=self.distante.empreinte or self.session.fingerprint,
        )

    def pretee(self, _target=None, _credentials=None):
        return _SansFermeture(self.session)

    def fermer(self) -> None:
        if self.tunnel is not None:
            self.tunnel.fermer()
            self.tunnel = None
        # Une session deja morte se ferme sans bruit.
        with contextlib.suppress(Exception):
            self.session.close()


class ActionRefusee(ValueError):
    """Demande impossible dans l'etat present, dite a l'utilisateur telle quelle."""


# ------------------------------------------------------------------ gestionnaire


class Gestionnaire:
    def __init__(
        self,
        *,
        ouvrir: Callable[[str], bool] = fenetre.ouvrir,
        popen: Callable = subprocess.Popen,
        connecter: remote_install.Connector = remote_install.connect_paramiko,
        verifier_maj: bool = True,
    ):
        self.jeton = secrets.token_urlsafe(24)
        self._ouvrir = ouvrir
        self._popen = popen
        self._connecter = connecter
        self._verifier_maj = verifier_maj
        self.verrou = threading.RLock()
        self.taches: dict[str, Tache] = {}
        self.consoles: dict[str, tuple[ThreadingHTTPServer, str]] = {}
        self.connexions: dict[str, Connexion] = {}
        self.etats: dict[str, dict] = {}
        self.maj: dict = {"etat": "inconnu"}
        self.activite = time.monotonic()
        self.arret = threading.Event()
        self._reveil = threading.Event()
        self.serveur: ThreadingHTTPServer | None = None

    # -- demarrage et arret ---------------------------------------------------

    @property
    def url(self) -> str:
        assert self.serveur is not None
        return f"http://127.0.0.1:{self.serveur.server_port}/#jeton={self.jeton}"

    def demarrer(self, port: int = 0) -> ThreadingHTTPServer:
        gestion = self

        class Lie(_Gestion):
            pass

        Lie.gestion = gestion
        self.serveur = _Serveur(("127.0.0.1", port), Lie)
        self.serveur.origine = f"http://127.0.0.1:{self.serveur.server_port}"
        self._suivre(self.serveur)
        threading.Thread(target=self.serveur.serve_forever, name="gestionnaire", daemon=True).start()
        threading.Thread(target=self._releve, name="releve", daemon=True).start()
        threading.Thread(target=self._veille, name="inactivite", daemon=True).start()
        if self._verifier_maj:
            threading.Thread(target=self._chercher_maj, name="maj", daemon=True).start()
        return self.serveur

    def _suivre(self, serveur: ThreadingHTTPServer) -> None:
        """Toute requete, au gestionnaire ou a une console hebergee, compte
        comme une activite : fermer la fenetre du gestionnaire ne doit pas
        couper une console encore ouverte."""
        origine = serveur.finish_request

        def finish_request(request, client_address):
            self.activite = time.monotonic()
            origine(request, client_address)

        serveur.finish_request = finish_request

    def _occupe(self) -> bool:
        with self.verrou:
            return any(tache.statut == "en-cours" for tache in self.taches.values())

    def _veille(self) -> None:
        while not self.arret.wait(5):
            if time.monotonic() - self.activite > INACTIVITE and not self._occupe():
                self.arreter()

    def arreter(self) -> None:
        if self.arret.is_set():
            return
        self.arret.set()
        self._reveil.set()
        with self.verrou:
            consoles = list(self.consoles.values())
            connexions = list(self.connexions.values())
            self.consoles.clear()
            self.connexions.clear()
        for serveur, _url in consoles:
            _fermer_serveur(serveur)
        for connexion in connexions:
            connexion.fermer()
        if self.serveur is not None:
            threading.Thread(target=_fermer_serveur, args=(self.serveur,), daemon=True).start()

    def attendre(self) -> None:
        try:
            while not self.arret.wait(1):
                pass
        except KeyboardInterrupt:
            self.arreter()

    # -- mise a jour de PlugArr ----------------------------------------------

    def _chercher_maj(self) -> None:
        try:
            info = selfupdate.check()
        except Exception:  # noqa: BLE001 - hors ligne ou quota : on ne sait pas, c'est tout
            with self.verrou:
                self.maj = {"etat": "inconnu"}
            return
        with self.verrou:
            self.maj = {
                "etat": "disponible" if info["available"] else "a-jour",
                "version": str(info["latest"]).removeprefix("v"),
                "installable": bool(info["available"] and info["verified_asset"]
                                    and info.get("installateur")),
                "page": info["release_url"],
                "_info": info,
            }

    def installer_maj(self) -> Tache:
        with self.verrou:
            info = self.maj.get("_info")
            if not self.maj.get("installable") or not info:
                raise ActionRefusee(t("Aucune mise a jour installable pour cette version."))

        def travail(tache: Tache) -> None:
            tache.ecrire(t("Telechargement de {nom}...", nom=info["asset"]))
            setup = selfupdate.telecharger_installateur(info)
            tache.ecrire(t("Empreinte SHA256 verifiee."))
            tache.ecrire(t("Fermeture des consoles, puis lancement de l'installateur."))
            with self.verrou:
                consoles = list(self.consoles.values())
                self.consoles.clear()
            for serveur, _url in consoles:
                _fermer_serveur(serveur)
            selfupdate.lancer_installateur(setup)
            threading.Timer(1.5, self.arreter).start()

        return self._lancer("plugarr", "maj", travail)

    # -- instances ------------------------------------------------------------

    def _locales(self) -> list[registre.Installation]:
        return registre.lire()

    def _locale(self, ident: str) -> registre.Installation:
        for inst in self._locales():
            if inst.ident == ident:
                return inst
        raise ActionRefusee(t("Installation inconnue."))

    def _distante(self, ident: str) -> distantes.Distante:
        distante = distantes.trouver(ident)
        if distante is None:
            raise ActionRefusee(t("Installation inconnue."))
        return distante

    def instances(self) -> list[dict]:
        noms = _lire_noms()
        locales = self._locales()
        dossier_plugarr = _normaliser(chemins.instances())
        vues: list[dict] = []
        with self.verrou:
            etats = dict(self.etats)
            en_cours = {
                tache.instance: tache.ident
                for tache in self.taches.values()
                if tache.statut == "en-cours"
            }
            consoles = set(self.consoles)
            connexions = dict(self.connexions)
        for inst in locales:
            etat = etats.get(inst.ident) or {"etat": "verification"}
            dossier = str(inst.project_dir)
            vues.append(
                {
                    "id": inst.ident,
                    "type": "local",
                    "nom": noms.get(inst.ident) or inst.project_name,
                    "lieu": dossier,
                    "range": _normaliser(inst.project_dir).startswith(dossier_plugarr + "/"),
                    "console": inst.ident in consoles,
                    "tache": en_cours.get(inst.ident),
                    **etat,
                }
            )
        for distante in distantes.lire():
            connexion = connexions.get(distante.ident)
            etat = etats.get(distante.ident) if connexion else None
            vues.append(
                {
                    "id": distante.ident,
                    "type": "ssh",
                    "nom": distante.libelle,
                    "lieu": f"{distante.user}@{distante.host}:{distante.project_dir}",
                    "empreinte": distante.empreinte,
                    "connecte": connexion is not None,
                    "secret_garde": coffre.garde(distante.ident),
                    "coffre": coffre.disponible(),
                    "a_console": distante.console_port > 0,
                    "console": bool(connexion and connexion.tunnel),
                    "tache": en_cours.get(distante.ident),
                    **(etat or {"etat": "deconnectee" if not connexion else "verification"}),
                }
            )
        return vues

    def vue(self) -> dict:
        with self.verrou:
            maj = {k: v for k, v in self.maj.items() if not k.startswith("_")}
            taches = [tache.vue(lignes=0) for tache in self.taches.values()]
        return {
            "version": __version__,
            "installe": chemins.installe(),
            "donnees": str(chemins.racine()),
            "maj": maj,
            "instances": self.instances(),
            "taches": taches,
        }

    def _releve(self) -> None:
        """Releve l'etat de chaque pile, hors des requetes de la page.

        `docker compose ps` prend une demi-seconde par pile ; le faire dans la
        requete ferait attendre la page a chaque rafraichissement.
        """
        while not self.arret.is_set():
            dossiers: dict[str, str | None] = {}
            for inst in self._locales():
                if self.arret.is_set():
                    return
                try:
                    etat = etat_local(inst, dossiers)
                except Exception:  # noqa: BLE001 - un releve rate ne fait pas tomber les autres
                    etat = {"etat": "docker-absent"}
                with self.verrou:
                    self.etats[inst.ident] = etat
            with self.verrou:
                connexions = list(self.connexions.items())
            for ident, connexion in connexions:
                self._relever_distante(ident, connexion)
            self._reveil.wait(RAFRAICHISSEMENT)
            self._reveil.clear()

    def _relever_distante(self, ident: str, connexion: Connexion) -> None:
        if connexion.cfg is None:
            return
        try:
            etat = etat_distant(connexion.session, connexion.cfg)
        except Exception:  # noqa: BLE001 - session coupee : on le montre, on ne plante pas
            etat = {"etat": "injoignable", "services": [], "pack": vue_pack(connexion.cfg)}
        with self.verrou:
            self.etats[ident] = etat

    def relever(self) -> None:
        self._reveil.set()

    # -- taches ---------------------------------------------------------------

    def _lancer(self, instance: str, action: str, travail: Callable[[Tache], None]) -> Tache:
        with self.verrou:
            if any(
                tache.instance == instance and tache.statut == "en-cours"
                for tache in self.taches.values()
            ):
                raise ActionRefusee(t("Une operation est deja en cours sur cette installation."))
            tache = Tache(ident=uuid.uuid4().hex[:12], instance=instance, action=action)
            self.taches[tache.ident] = tache

        def fil() -> None:
            try:
                travail(tache)
                tache.statut = "reussie"
            except Exception as exc:  # noqa: BLE001 - l'erreur est montree dans la page
                tache.statut = "echouee"
                tache.message = _message(exc)
                tache.ecrire(tache.message)
            finally:
                tache.fin = time.time()
                self.activite = time.monotonic()
                self.relever()

        threading.Thread(target=fil, name=f"tache-{action}", daemon=True).start()
        return tache

    def _sous_processus(self, tache: Tache, arguments: list[str]) -> None:
        """Lance `plugarr <arguments>` et recopie sa sortie dans la tache."""
        options: dict = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "env": chemins.environnement_moteur(),
        }
        if sys.platform == "win32":
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        processus = self._popen([*chemins.moteur(), *arguments], **options)
        assert processus.stdout is not None
        for brut in iter(processus.stdout.readline, b""):
            ligne = brut.decode("utf-8", errors="replace") if isinstance(brut, bytes) else str(brut)
            tache.ecrire(ligne)
        code = processus.wait()
        if code:
            raise RuntimeError(t("La commande s'est terminee avec le code {code}.", code=code))

    def action(self, ident: str, action: str) -> Tache:
        if ident.startswith("ssh-"):
            if action not in ACTIONS_DISTANTES:
                raise ActionRefusee(t("Action inconnue."))
            return self._action_distante(ident, action)
        if action not in ACTIONS_LOCALES:
            raise ActionRefusee(t("Action inconnue."))
        inst = self._locale(ident)
        _pile_ici(inst)
        dossier = str(inst.project_dir)
        if action == "demarrer":
            return self._lancer(ident, action, lambda tache: self._compose(tache, inst, "up"))
        if action == "arreter":
            return self._lancer(ident, action, lambda tache: self._compose(tache, inst, "stop"))
        if action == "pack":
            return self._lancer(
                ident,
                action,
                lambda tache: self._apres_pack_local(
                    tache, inst, ["upgrade", "--project-dir", dossier, "--yes"]
                ),
            )
        if action == "sauvegarder":
            return self._lancer(
                ident, action, lambda tache: self._sous_processus(
                    tache, ["backup", "--project-dir", dossier]
                )
            )
        if action == "diagnostic":
            return self._lancer(
                ident, action, lambda tache: self._sous_processus(
                    tache, ["doctor", "--project-dir", dossier]
                )
            )
        return self._lancer(ident, action, lambda tache: self._deplacer(tache, inst))

    def _apres_pack_local(self, tache: Tache, inst: registre.Installation, arguments) -> None:
        self._sous_processus(tache, arguments)
        # La console hebergee lit la configuration a son demarrage : apres un
        # changement d'images, elle afficherait les anciennes.
        self._fermer_console(inst.ident)

    def _compose(self, tache: Tache, inst: registre.Installation, quoi: str) -> None:
        cfg, _notes = migrations.lire(inst.stack)
        runner = Compose(inst.project_dir, cfg.project_name)
        if quoi == "up":
            tache.ecrire(t("Demarrage de la pile {nom}...", nom=cfg.project_name))
            ok, sortie = runner.up()
        else:
            tache.ecrire(t("Arret de la pile {nom}...", nom=cfg.project_name))
            try:
                _arrete, sortie = runner.stop()
                ok = True
            except OSError as exc:
                ok, sortie = False, str(exc)
        for ligne in (sortie or "").splitlines():
            tache.ecrire(ligne)
        if not ok:
            raise RuntimeError(t("Docker a refuse l'operation."))
        tache.ecrire(t("Termine."))

    # -- console locale -------------------------------------------------------

    def ouvrir_console(self, ident: str) -> str:
        if ident.startswith("ssh-"):
            return self._console_distante(ident)
        with self.verrou:
            if ident in self.consoles:
                url = self.consoles[ident][1]
                self._ouvrir(url)
                return url
        inst = self._locale(ident)
        cfg = _pile_ici(inst)
        jeton = admin.generate_token()
        serveur = admin.build_server(cfg, inst.project_dir, host="127.0.0.1", port=0, token=jeton)
        # Pas de travailleur de maintenance ici : les sauvegardes planifiees
        # appartiennent a la console permanente (`plugarr autostart`). Deux
        # consoles sur la meme pile les declencheraient deux fois.
        self._suivre(serveur)
        threading.Thread(target=serveur.serve_forever, name="console", daemon=True).start()
        url = f"http://127.0.0.1:{serveur.server_port}/?t={jeton}"
        with self.verrou:
            self.consoles[ident] = (serveur, url)
        self._ouvrir(url)
        return url

    def _fermer_console(self, ident: str) -> None:
        with self.verrou:
            ouverte = self.consoles.pop(ident, None)
        if ouverte is not None:
            _fermer_serveur(ouverte[0])

    def ouvrir_dossier(self, ident: str) -> None:
        inst = self._locale(ident)
        if not inst.project_dir.is_dir():
            raise ActionRefusee(t("Le dossier de cette installation n'existe plus."))
        if sys.platform == "win32":
            os.startfile(str(inst.project_dir))
        else:
            ouvreur = shutil.which("xdg-open") or shutil.which("open")
            if not ouvreur:
                raise ActionRefusee(t("Aucun explorateur de fichiers disponible."))
            self._popen([ouvreur, str(inst.project_dir)])

    def nouvelle(self) -> None:
        """Ouvre l'assistant dans sa propre fenetre de terminal.

        Le dossier propose est celui des instances de PlugArr. Si une pile
        existe deja ailleurs, l'assistant la retrouve par le registre et
        propose de la reprendre : il n'en cree pas une seconde a cote.
        """
        options: dict = {"env": chemins.environnement_moteur(), "close_fds": True}
        if sys.platform == "win32":
            options["creationflags"] = subprocess.CREATE_NEW_CONSOLE
        self._popen(
            [*chemins.moteur(), "web", "--project-dir", str(chemins.instance_par_defaut())],
            **options,
        )

    def renommer(self, ident: str, nom: str) -> None:
        nom = _nettoyer_nom(nom)
        if ident.startswith("ssh-"):
            if not distantes.renommer(ident, nom):
                raise ActionRefusee(t("Installation inconnue."))
            return
        self._locale(ident)
        _ecrire_nom(ident, nom)

    def oublier(self, ident: str) -> None:
        """Retire de la liste. Ne supprime rien, nulle part."""
        if ident.startswith("ssh-"):
            self.deconnecter(ident)
            coffre.oublier(ident)
            if not distantes.oublier(ident):
                raise ActionRefusee(t("Installation inconnue."))
            return
        inst = self._locale(ident)
        self._fermer_console(ident)
        registre.oublier(inst.project_dir)
        _ecrire_nom(ident, "")
        with self.verrou:
            self.etats.pop(ident, None)

    # -- deplacement ----------------------------------------------------------

    def _deplacer(self, tache: Tache, inst: registre.Installation) -> None:
        """Range une installation posee ailleurs dans le dossier de PlugArr.

        Dans cet ordre, et chaque etape a sa raison :

        1. `down` depuis l'ANCIEN dossier : Docker range les conteneurs par nom
           de projet mais note le dossier d'origine sur chacun. Des conteneurs
           restes en place porteraient l'ancien chemin, et le garde-fou contre
           les piles en double le prendrait pour une seconde installation ;
        2. les fichiers sont DEPLACES, jamais copies puis effaces : aucun
           exemplaire des secrets ne reste derriere, et rien n'est supprime ;
        3. `write_artifacts` reecrit le compose et `.env` avec le nouveau
           chemin, et inscrit le nouveau dossier au registre ;
        4. la pile repart depuis le nouveau dossier. Les donnees vivent dans
           CONFIG_ROOT et DATA_ROOT, qui ne bougent pas.
        """
        from . import autostart as autostart_mod

        ancien = inst.project_dir
        cfg, _notes = migrations.lire(inst.stack)
        nouveau = _dossier_libre(chemins.instances(), cfg.project_name)
        tache.ecrire(t("Destination : {chemin}", chemin=nouveau))
        self._fermer_console(inst.ident)

        tache.ecrire(t("Arret et retrait des conteneurs depuis l'ancien dossier..."))
        ok, sortie = Compose(ancien, cfg.project_name).down()
        for ligne in (sortie or "").splitlines():
            tache.ecrire(ligne)
        if not ok:
            raise RuntimeError(t("Docker a refuse l'arret : rien n'a ete deplace."))

        nouveau.mkdir(parents=True, exist_ok=True)
        a_deplacer = [ancien / nom for nom in (*FICHIERS_PROJET, *DOSSIERS_PROJET)]
        a_deplacer += list(compose.historique(ancien))
        for source in a_deplacer:
            if source.exists():
                shutil.move(str(source), str(nouveau / source.name))
                tache.ecrire(t("deplace : {nom}", nom=source.name))

        cfg, _notes = migrations.lire(nouveau / "stack.yml")
        compose.write_artifacts(cfg, nouveau)
        dashboard.write_admin_launcher(nouveau, cfg)
        registre.oublier(ancien)
        nom = _lire_noms().get(inst.ident)
        if nom:
            _ecrire_nom(registre.Installation(nouveau.resolve(), "", "", "").ident, nom)
            _ecrire_nom(inst.ident, "")

        etat = autostart_mod.status(ancien)
        if etat.actif and etat.chemin is not None:
            try:
                contenu = etat.chemin.read_text(encoding="utf-8", errors="replace")
            except OSError:
                contenu = ""
            if str(ancien.resolve()) in contenu:
                hote = re.search(r"--host (\S+)", contenu)
                port = re.search(r"--port (\d+)", contenu)
                _ok, message = autostart_mod.enable(
                    nouveau,
                    host=hote.group(1) if hote else "127.0.0.1",
                    port=int(port.group(1)) if port else 7373,
                )
                tache.ecrire(message)

        tache.ecrire(t("Redemarrage depuis le nouveau dossier..."))
        ok, sortie = Compose(nouveau, cfg.project_name).up()
        for ligne in (sortie or "").splitlines():
            tache.ecrire(ligne)
        if not ok:
            raise RuntimeError(
                t("Fichiers deplaces, mais la pile n'a pas redemarre. Utilisez Demarrer.")
            )
        tache.ecrire(t("Termine."))

    # -- distantes ------------------------------------------------------------

    def connecter(self, ident: str, champs: dict) -> None:
        distante = self._distante(ident)
        secrets_saisis = {
            cle: str(champs.get(cle) or "") for cle in coffre.CHAMPS if champs.get(cle)
        }
        garde = coffre.lire(ident) if not secrets_saisis else {}
        valeurs = secrets_saisis or garde
        if not valeurs.get("password") and not valeurs.get("private_key"):
            raise ActionRefusee(t("Mot de passe ou cle privee SSH requis."))
        identifiants = remote_install.RemoteCredentials(
            password=valeurs.get("password", ""),
            private_key=valeurs.get("private_key", ""),
            passphrase=valeurs.get("passphrase", ""),
            sudo_password=valeurs.get("sudo_password", ""),
        )
        cible = remote_install.RemoteTarget(
            host=distante.host,
            port=distante.port,
            username=distante.user,
            expected_fingerprint=distante.empreinte,
        )
        try:
            session = remote_install.open_verified_session(
                cible, identifiants, connect=self._connecter
            )
        except remote_install.FingerprintMismatch as exc:
            raise ActionRefusee(
                t(
                    "L'empreinte SSH du serveur a change depuis l'installation : connexion "
                    "refusee. Si le serveur a ete reinstalle, retirez-le de la liste puis "
                    "reinstallez PlugArr dessus."
                )
            ) from exc
        connexion = Connexion(distante, session, identifiants)
        try:
            self._lire_pile(connexion)
        except Exception:
            connexion.fermer()
            raise
        if champs.get("se_souvenir") and secrets_saisis and coffre.disponible():
            coffre.garder(ident, secrets_saisis)
        with self.verrou:
            ancienne = self.connexions.pop(ident, None)
            self.connexions[ident] = connexion
            self.etats[ident] = {"etat": "verification"}
        if ancienne is not None:
            ancienne.fermer()
        self.relever()

    def _lire_pile(self, connexion: Connexion) -> None:
        etat = remote_install.inspect_project(
            connexion.cible,
            connexion.identifiants,
            connexion.distante.project_dir,
            connect=connexion.pretee,
        )
        if not etat.exists or not etat.managed or not etat.stack_yaml:
            raise ActionRefusee(
                t("Aucune pile PlugArr lisible dans {dossier} sur ce serveur.",
                  dossier=connexion.distante.project_dir)
            )
        connexion.cfg, _notes = migrations.lire_texte(etat.stack_yaml)
        connexion.stack_sha = etat.stack_sha

    def deconnecter(self, ident: str) -> None:
        with self.verrou:
            connexion = self.connexions.pop(ident, None)
            self.etats.pop(ident, None)
        if connexion is not None:
            connexion.fermer()

    def oublier_secret(self, ident: str) -> None:
        self._distante(ident)
        coffre.oublier(ident)

    def _connexion(self, ident: str) -> Connexion:
        with self.verrou:
            connexion = self.connexions.get(ident)
        if connexion is None:
            raise ActionRefusee(t("Connectez-vous d'abord a ce serveur."))
        return connexion

    def _console_distante(self, ident: str) -> str:
        connexion = self._connexion(ident)
        if connexion.distante.console_port <= 0:
            raise ActionRefusee(t("Cette installation n'a pas de console en conteneur."))
        if connexion.tunnel is None or not connexion.tunnel.actif:
            if connexion.tunnel is not None:
                connexion.tunnel.fermer()
            transport = connexion.session.transport()
            if transport is None:
                raise ActionRefusee(t("La session SSH est fermee. Reconnectez-vous."))
            connexion.tunnel = Tunnel(transport, connexion.distante.console_port)
        url = f"http://127.0.0.1:{connexion.tunnel.port}/"
        self._ouvrir(url)
        return url

    def _action_distante(self, ident: str, action: str) -> Tache:
        connexion = self._connexion(ident)
        if connexion.cfg is None:
            raise ActionRefusee(t("Connectez-vous d'abord a ce serveur."))
        if action == "pack":
            return self._lancer(ident, action, lambda tache: self._pack_distant(tache, connexion))
        commande = "up -d" if action == "demarrer" else "stop"

        def travail(tache: Tache) -> None:
            dossier = shlex.quote(connexion.distante.project_dir)
            nom = shlex.quote(connexion.cfg.project_name)
            tache.ecrire(f"docker compose -p {connexion.cfg.project_name} {commande}")
            code, sortie, erreur = connexion.session.run(
                f"cd {dossier} && docker compose -p {nom} {commande}"
            )
            for ligne in (sortie + erreur).splitlines():
                tache.ecrire(ligne)
            if code:
                raise RuntimeError(t("Docker a refuse l'operation."))
            tache.ecrire(t("Termine."))

        return self._lancer(ident, action, travail)

    def _pack_distant(self, tache: Tache, connexion: Connexion) -> None:
        """Mise a jour du pack sur un serveur : on relit, on aligne, on redeploie.

        C'est le catalogue de CET executable qui decide, comme pour une pile
        locale. Le redeploiement passe par le chemin deja eprouve de
        l'installation distante : il garde l'ancien `stack.yml`, reprend les
        comptes existants, puis rejoue le cablage.
        """
        self._lire_pile(connexion)
        cfg = connexion.cfg
        assert cfg is not None
        retenus, ecartes = pack.ecarts(cfg)
        for raison in ecartes:
            tache.ecrire(t("ignore : {raison}", raison=raison))
        if not retenus:
            tache.ecrire(t("Rien a mettre a jour."))
            return
        for ecart in retenus:
            tache.ecrire(f"{ecart.service} : {ecart.tag_installe} -> {ecart.tag_catalogue}")
        pack.appliquer(cfg, retenus)
        uid, gid = connexion.distante.uid, connexion.distante.gid
        if uid < 0 or gid < 0:
            sonde = remote_install.probe(
                connexion.cible, connexion.identifiants, connect=connexion.pretee
            )
            uid, gid = sonde.uid, sonde.gid
        deploiement = remote_install.RemoteDeployment(
            project_dir=connexion.distante.project_dir,
            config_root=cfg.config_root,
            data_root=cfg.data_root,
            uid=uid,
            gid=gid,
            stack_yaml=compose.render_stack(cfg),
            image=catalog.CONSOLE_IMAGE,
            veille_image=catalog.VEILLE_IMAGE,
            replace_existing=True,
            expected_existing_sha=connexion.stack_sha,
        )

        def evenement(event: dict) -> None:
            genre = event.get("kind")
            if genre in ("progress", "check", "log"):
                texte = event.get("message") or event.get("detail") or ""
                phase = event.get("phase") or event.get("name") or ""
                tache.ecrire(f"{phase} : {texte}" if phase else str(texte))
            elif genre == "step":
                marque = "OK" if event.get("ok") else t("ECHEC")
                tache.ecrire(f"{marque}  {event.get('name', '')}")

        resultat = remote_install.deploy(
            connexion.cible,
            connexion.identifiants,
            deploiement,
            connect=connexion.pretee,
            on_event=evenement,
        )
        self._lire_pile(connexion)
        if resultat.status != "done":
            raise RuntimeError(t("Mise a jour appliquee, mais une etape du cablage a echoue."))
        tache.ecrire(t("Termine."))


# --------------------------------------------------------------------- utilitaires


def _normaliser(chemin) -> str:
    return registre._normaliser(str(chemin))


def _pile_ici(inst: registre.Installation) -> StackConfig:
    """La configuration de l'installation, si c'est bien SA pile qui tourne.

    Refuse quand des conteneurs du meme nom de pile viennent d'un autre
    dossier : les commandes Compose visent un nom, pas un dossier, et
    piloteraient l'autre installation.
    """
    if not inst.vivante:
        raise ActionRefusee(t("Le dossier de cette installation n'existe plus."))
    cfg, _notes = migrations.lire(inst.stack)
    ailleurs = running_project_dir(cfg.project_name)
    if ailleurs and _normaliser(ailleurs) != _normaliser(inst.project_dir):
        raise ActionRefusee(
            t(
                "La pile {nom} tourne depuis un autre dossier : {dossier}. Rien n'est lance d'ici.",
                nom=cfg.project_name,
                dossier=ailleurs,
            )
        )
    return cfg


def _dossier_libre(parent: Path, nom: str) -> Path:
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", nom).strip("-.") or chemins.NOM_PAR_DEFAUT
    candidat = parent / base
    rang = 2
    while candidat.exists() and any(candidat.iterdir()):
        candidat = parent / f"{base}-{rang}"
        rang += 1
    return candidat


def _message(exc: Exception) -> str:
    """Premiere ligne de l'erreur, sans la pile d'appels."""
    texte = next(iter(str(exc).splitlines()), "") or type(exc).__name__
    return texte[:400]


def _fermer_serveur(serveur: ThreadingHTTPServer) -> None:
    # Un serveur deja ferme n'est pas une erreur.
    with contextlib.suppress(Exception):
        serveur.shutdown()
        serveur.server_close()


# -------------------------------------------------------------------------- http


class _Serveur(ThreadingHTTPServer):
    """Refuse de partager son port, comme la console (voir `admin._Server`)."""

    allow_reuse_address = sys.platform != "win32"
    daemon_threads = True
    origine = ""


_STATIQUES = {
    "/": ("gestionnaire.html", "text/html; charset=utf-8"),
    "/gestionnaire.css": ("gestionnaire.css", "text/css; charset=utf-8"),
    "/gestionnaire.js": ("gestionnaire.js", "text/javascript; charset=utf-8"),
    "/wizard.css": ("wizard.css", "text/css; charset=utf-8"),
}

#: Corps de requete accepte. Une cle privee RSA de 4 096 bits fait environ
#: 3,3 Ko : 64 Ko laisse de la marge sans inviter a l'abus.
CORPS_MAX = 65536

_ROUTE_INSTANCE = re.compile(r"^/api/instances/([a-z0-9-]{4,40})/([a-z-]+)$")


class _Gestion(BaseHTTPRequestHandler):
    gestion: Gestionnaire
    server_version = "plugarr"
    sys_version = ""

    def log_message(self, fmt: str, *args: object) -> None:
        """Silence : rien a journaliser dans un programme sans console."""

    def _repondre(self, corps, statut: int = 200, type_: str = "application/json; charset=utf-8"):
        donnees = corps if isinstance(corps, bytes) else json.dumps(corps, ensure_ascii=False).encode()
        self.send_response(statut)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(donnees)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
        )
        self.end_headers()
        self.wfile.write(donnees)

    def _permis(self, *, authentifie: bool = True) -> bool:
        origine = self.server.origine
        if self.headers.get("Host") != origine.removeprefix("http://"):
            self._repondre({"erreur": "Hote refuse."}, 403)
            return False
        if self.headers.get("Origin") not in (None, origine):
            self._repondre({"erreur": "Origine refusee."}, 403)
            return False
        if authentifie and not hmac.compare_digest(
            self.headers.get("Authorization", "").encode("utf-8"),
            ("Bearer " + self.gestion.jeton).encode("utf-8"),
        ):
            self._repondre({"erreur": t("Session absente ou expiree. Relancez PlugArr.")}, 401)
            return False
        return True

    def _corps(self) -> dict:
        try:
            longueur = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            longueur = 0
        if longueur > CORPS_MAX:
            admin.vider_corps_requete(self)
            raise ActionRefusee(t("Requete trop volumineuse."))
        if longueur <= 0:
            return {}
        try:
            donnees = json.loads(self.rfile.read(longueur).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ActionRefusee(t("Requete illisible.")) from exc
        return donnees if isinstance(donnees, dict) else {}

    def do_GET(self) -> None:
        route = urlsplit(self.path).path
        if route in _STATIQUES:
            if not self._permis(authentifie=False):
                return
            nom, type_ = _STATIQUES[route]
            self._repondre((WEB / nom).read_bytes(), type_=type_)
            return
        if route == "/api/textes":
            # Sans jeton : ce sont des libelles, et la page doit pouvoir dire
            # dans la bonne langue que sa session manque.
            if not self._permis(authentifie=False):
                return
            icones = json.loads((WEB.parent / "data" / "connection_icons.json").read_text("utf-8"))
            self._repondre(
                {"langue": i18n.langue(), "textes": textes(), "icone": icones.get("plugarr", "")}
            )
            return
        if not self._permis():
            return
        if route == "/api/ping":
            self._repondre({"version": __version__})
        elif route == "/api/etat":
            self._repondre(self.gestion.vue())
        elif route.startswith("/api/taches/"):
            ident = unquote(route.removeprefix("/api/taches/"))
            with self.gestion.verrou:
                tache = self.gestion.taches.get(ident)
            if tache is None:
                self._repondre({"erreur": t("Tache inconnue.")}, 404)
            else:
                self._repondre(tache.vue(lignes=400))
        else:
            self._repondre({"erreur": "Introuvable."}, 404)

    def do_POST(self) -> None:
        route = urlsplit(self.path).path
        if not self._permis():
            admin.vider_corps_requete(self)
            return
        gestion = self.gestion
        try:
            corps = self._corps()
            if route == "/api/nouvelle":
                gestion.nouvelle()
                self._repondre({"ok": True})
            elif route == "/api/actualiser":
                gestion.relever()
                self._repondre({"ok": True})
            elif route == "/api/maj":
                self._repondre({"tache": gestion.installer_maj().vue()})
            elif route == "/api/quitter":
                self._repondre({"ok": True})
                threading.Timer(0.3, gestion.arreter).start()
            else:
                correspondance = _ROUTE_INSTANCE.match(route)
                if not correspondance:
                    self._repondre({"erreur": "Introuvable."}, 404)
                    return
                ident, quoi = correspondance.groups()
                self._repondre(self._instance(ident, quoi, corps))
        except ActionRefusee as exc:
            self._repondre({"erreur": str(exc)}, 409)
        except Exception as exc:  # noqa: BLE001 - l'erreur est dite, le serveur continue
            self._repondre({"erreur": _message(exc)}, 500)

    def _instance(self, ident: str, quoi: str, corps: dict) -> dict:
        gestion = self.gestion
        if quoi == "console":
            return {"url": gestion.ouvrir_console(ident)}
        if quoi == "dossier":
            gestion.ouvrir_dossier(ident)
            return {"ok": True}
        if quoi == "renommer":
            gestion.renommer(ident, str(corps.get("nom") or ""))
            return {"ok": True}
        if quoi == "oublier":
            gestion.oublier(ident)
            return {"ok": True}
        if quoi == "connexion":
            gestion.connecter(ident, corps)
            return {"ok": True}
        if quoi == "deconnexion":
            gestion.deconnecter(ident)
            return {"ok": True}
        if quoi == "oublier-secret":
            gestion.oublier_secret(ident)
            return {"ok": True}
        return {"tache": gestion.action(ident, quoi).vue()}


# ------------------------------------------------------------------ point d'entree


def _chemin_verrou() -> Path:
    return chemins.racine() / FICHIER_VERROU


def deja_ouvert() -> str | None:
    """Adresse du gestionnaire deja lance par ce compte, s'il repond."""
    import httpx

    try:
        donnees = json.loads(_chemin_verrou().read_text(encoding="utf-8"))
        port, jeton = int(donnees["port"]), str(donnees["jeton"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    try:
        reponse = httpx.get(
            f"http://127.0.0.1:{port}/api/ping",
            headers={"Authorization": f"Bearer {jeton}", "Host": f"127.0.0.1:{port}"},
            timeout=2,
        )
    except httpx.HTTPError:
        return None
    if reponse.status_code != 200:
        return None
    try:
        if reponse.json().get("version") != __version__:
            return None
    except ValueError:
        return None
    return f"http://127.0.0.1:{port}/#jeton={jeton}"


def fermer_ouvert(*, delai: float = 10.0) -> bool:
    """Ferme le gestionnaire ouvert par ce compte. Vrai s'il n'en reste aucun.

    Appele par l'installateur (`plugarr manager --quitter`) : ses fichiers
    doivent etre libres avant d'etre remplaces ou retires. Il ferme aussi les
    consoles qu'il heberge et ses tunnels SSH.
    """
    import httpx

    adresse = deja_ouvert()
    if adresse is None:
        return True
    base, _, fragment = adresse.partition("/#jeton=")
    # Une reponse perdue n'empeche pas la fermeture : on la constate ci-dessous.
    with contextlib.suppress(httpx.HTTPError):
        httpx.post(
            base + "/api/quitter", headers={"Authorization": f"Bearer {fragment}"}, timeout=5
        )
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        if deja_ouvert() is None:
            return True
        time.sleep(0.2)
    return False


def _ecrire_verrou(gestion: Gestionnaire) -> None:
    fichier = _chemin_verrou()
    fichier.parent.mkdir(parents=True, exist_ok=True)
    temporaire = fichier.with_suffix(".tmp")
    temporaire.write_text(
        json.dumps(
            {"pid": os.getpid(), "port": gestion.serveur.server_port, "jeton": gestion.jeton}
        ),
        encoding="utf-8",
    )
    os.replace(temporaire, fichier)


def _retirer_verrou(gestion: Gestionnaire) -> None:
    try:
        donnees = json.loads(_chemin_verrou().read_text(encoding="utf-8"))
        if donnees.get("jeton") == gestion.jeton:
            _chemin_verrou().unlink()
    except (OSError, ValueError):
        return


def principal(*, ouvrir: bool = True, port: int = 0, afficher: Callable[[str], None] = print) -> int:
    """Lance le gestionnaire, ou rouvre sa fenetre s'il tourne deja."""
    i18n.utiliser(i18n.langue_du_systeme())
    existant = deja_ouvert()
    if existant:
        if ouvrir:
            fenetre.ouvrir(existant)
        afficher(existant)
        return 0
    gestion = Gestionnaire()
    gestion.demarrer(port)
    _ecrire_verrou(gestion)
    afficher(gestion.url)
    if ouvrir and not fenetre.ouvrir(gestion.url):
        afficher(t("Ouvrez cette adresse dans votre navigateur."))
    try:
        gestion.attendre()
    finally:
        _retirer_verrou(gestion)
    return 0
