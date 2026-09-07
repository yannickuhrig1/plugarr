"""Le graphe de cablage. C'est la raison d'etre du projet.

Chaque etape est idempotente et verifiable. Une etape se declare :
  - `run`    : execute le cablage, renvoie un libelle de resultat
  - `verify` : RELIT depuis l'API cible pour confirmer, plutot que de faire
               confiance au code de retour du POST

Toutes les URL de cablage sont des URL INTERNES au reseau compose
(http://sonarr:8989), jamais localhost : c'est un conteneur qui parle a un autre.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from . import catalog, journal, langues, reprise
from .clients import recyclarr as recyclarr_cfg
from .clients.arr import ArrClient
from .clients.autobrr import AutobrrClient
from .clients.base import WiringError
from .clients.jellyfin import JellyfinClient
from .clients.qbittorrent import QBittorrentClient
from .clients.qui import QuiClient
from .downloadclients import profile_for
from .i18n import t
from .layout import BIBLIOTHEQUES, CONTAINER_PATHS
from .models import Category, StackConfig

#: Categories d'indexeurs Prowlarr poussees vers chaque application (conventions Newznab).
#: 2000 = Movies, 3000 = Audio, 5000 = TV.
SYNC_CATEGORIES = {
    "sonarr": [5000, 5010, 5020, 5030, 5040, 5045, 5050],
    "radarr": [2000, 2010, 2020, 2030, 2040, 2045, 2050],
    "lidarr": [3000, 3010, 3030, 3040, 3050, 3060],
}

#: Chemins des medias VUS PAR SILO. Il monte `${DATA_ROOT}/media` sur
#: `/mnt/media`, et non `/data` comme les images LinuxServer : sa configuration
#: amont l'appelle `MEDIA_CONTAINER_ROOT`. Reutiliser CONTAINER_PATHS ici
#: donnerait des chemins que Silo ne trouverait pas.
SILO_MEDIA = {
    "movies": "/mnt/media/movies",
    "tv": "/mnt/media/tv",
    "music": "/mnt/media/music",
}

#: Dossiers racine de chaque application, dans l'ordre ou ils sont poses.
#:
#: Sonarr en recoit DEUX : les series et l'anime. Ce n'est pas un detail de
#: rangement — Sonarr traite l'anime comme un type de serie a part, avec ses
#: propres conventions de nommage et de numerotation. Melanger les deux dans un
#: seul dossier racine fait renommer les series normales selon des regles anime.
#: C'est la disposition que recommandent les TRaSH Guides.
ROOT_FOLDERS = {
    b.arr: [x.mediatheque for x in BIBLIOTHEQUES if x.arr == b.arr and x.media]
    for b in BIBLIOTHEQUES
    if b.arr
}


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str
    created: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class WiringStep:
    name: str
    run: Callable[[], StepResult]
    requires: tuple[str, ...] = ()


class Wirer:
    """Construit et execute le graphe pour une StackConfig donnee."""

    def __init__(self, cfg: StackConfig, *, run_tests: bool = True):
        self.cfg = cfg
        #: Declenche le bouton "Test" de l'application apres chaque lien. C'est la
        #: difference entre "le POST est passe" et "la connexion fonctionne".
        self.run_tests = run_tests
        self._arr_cache: dict[str, ArrClient] = {}
        #: Services dont le mot de passe annonce a ete remplace par celui d'une
        #: installation precedente. Sert a le DIRE : un mot de passe change en
        #: silence est un mot de passe qu'on ne retrouvera pas.
        self.recuperations: list[str] = []

    def _connexion_rattrapee(
        self, service_id: str, instance: object, connexion: Callable[[str], object]
    ) -> bool:
        """Se connecte, en essayant les mots de passe des installations passees.

        **Le cas qu'elle repare.** Jellyfin, autobrr et qui ne gardent leur mot
        de passe que HACHE. Quand leur configuration vient d'une installation
        precedente, celui que PlugArr vient de generer est refuse — un HTTP 401
        que rien n'expliquait, et dont la seule sortie documentee etait
        d'effacer la configuration du service.

        Or ce mot de passe n'est pas introuvable : c'est PlugArr qui l'a ecrit,
        il est dans un `stack.yml` precedent. Les essayer coute quelques
        requetes ; les ignorer coute a l'utilisateur ses bibliotheques.

        Renvoie True si un mot de passe herite a pris la place de celui qui
        etait annonce. Leve la derniere erreur si aucun ne passe.
        """
        annonce = getattr(instance, "password", "") or ""
        candidats = [annonce]
        for ancien in reprise.mots_de_passe_connus(self.cfg.project_dir, service_id):
            if ancien not in candidats:
                candidats.append(ancien)

        derniere: Exception | None = None
        for rang, mot in enumerate(candidats):
            try:
                connexion(mot)
            except WiringError as exc:
                derniere = exc
                continue
            if rang == 0:
                return False
            # Le mot de passe herite devient celui de la configuration : il sera
            # repersiste dans stack.yml et .env apres le cablage, et c'est lui
            # que la page d'acces affichera. Annoncer l'autre serait mentir.
            instance.password = mot
            self.recuperations.append(service_id)
            journal.LOGGER.info(
                "%s : mot de passe repris d'une installation precedente", service_id
            )
            return True
        if derniere is not None:
            raise derniere
        raise WiringError(
            t("{service} : aucun mot de passe accepte", service=service_id),
            t("ni celui qui vient d'etre genere, ni ceux des installations precedentes"),
            t("supprimez la configuration de ce service pour repartir a zero"),
        )

    def _verify(
        self,
        client: ArrClient,
        resource: str,
        name: str,
        result: StepResult,
        on_auth_failure: Callable[[], bool] | None = None,
    ) -> StepResult:
        """Fait valider le lien par l'application elle-meme.

        `on_auth_failure` permet de tenter UNE reparation quand le refus vient
        d'un bannissement plutot que d'un mauvais mot de passe : les deux se
        presentent a l'identique, « Authentication Failure ».
        """
        if not self.run_tests:
            return result
        obj = client.find_by_name(resource, name)
        if obj is None:
            result.ok = False
            result.detail += t(" - introuvable a la relecture")
            return result
        ok, message = client.test_resource(resource, obj)
        # La reparation ne vaut que pour un refus d'AUTHENTIFICATION. L'avoir
        # elargie a tout echec redemarrait qBittorrent sur un simple defaut de
        # connexion — et ce redemarrage cassait a son tour l'adresse mise en
        # cache par Sonarr, qui echouait alors sur « Unable to connect ». Le
        # remede fabriquait la panne suivante.
        refus = not ok and "Authentication Failure" in message
        if refus and on_auth_failure and on_auth_failure():
            ok, message = client.test_resource(resource, obj)
        if ok:
            result.detail += t(", test OK")
        else:
            result.ok = False
            result.detail += t(" - le test de connexion a echoue")
            result.warnings.append(message.splitlines()[0])
        return result

    # -- fabriques de clients -----------------------------------------------

    def arr(self, service_id: str) -> ArrClient:
        """Client vers un *arr, vu depuis l'HOTE (c'est nous qui appelons)."""
        if service_id not in self._arr_cache:
            spec = catalog.get(service_id)
            inst = self.cfg.services[service_id]
            self._arr_cache[service_id] = ArrClient(
                f"http://{self.cfg.host}:{inst.host_port}",
                inst.api_key or "",
                api_version=spec.api_version,
                name=service_id,
            )
        return self._arr_cache[service_id]

    def internal_url(self, service_id: str) -> str:
        """URL du service vue par un AUTRE conteneur.

        Delegue a ServiceInstance : un service adopte n'est pas sur le reseau
        compose et doit etre joint par l'hote.
        """
        spec = catalog.get(service_id)
        behind_vpn = self.cfg.vpn.enabled and spec.category is Category.DOWNLOAD
        return self.cfg.services[service_id].internal_url(
            spec, self.cfg.host, behind_vpn=behind_vpn
        )

    def close(self) -> None:
        for client in self._arr_cache.values():
            client.close()
        self._arr_cache.clear()

    # -- etapes --------------------------------------------------------------

    def step_root_folder(self, arr_id: str, path: str) -> StepResult:
        client = self.arr(arr_id)

        if self.cfg.services[arr_id].adopted:
            # Une stack adoptee a DEJA son arborescence, et ce n'est pas la notre.
            # Constate en conditions reelles : imposer /data/media/tv a un Sonarr
            # existant echoue avec "Path does not exist", et ce serait de toute
            # facon une intrusion. Adopter, c'est cabler des services entre eux,
            # pas reorganiser les dossiers de quelqu'un.
            existing = [f.get("path", "") for f in client.get("rootfolder") or []]
            if existing:
                return StepResult(
                    f"{arr_id}: dossier racine",
                    ok=True,
                    detail=t("deja configure ({dossiers}), respecte", dossiers=", ".join(existing)),
                )
            return StepResult(
                f"{arr_id}: dossier racine",
                ok=True,
                detail=t("aucun dossier racine configure"),
                warnings=[
                    t(
                        "{service} n'a aucun dossier racine et plugarr ne peut pas "
                        "deviner votre arborescence. Ajoutez-le dans {service} "
                        "avant d'importer.",
                        service=arr_id,
                    )
                ],
            )

        extra: dict[str, object] = {}
        if arr_id == "lidarr":
            # Lidarr refuse un dossier racine sans nom ni profils par defaut, la ou
            # Sonarr et Radarr se contentent du chemin. Les identifiants de profils
            # ne sont pas stables entre versions : on les resout par nom.
            extra = {
                "name": "Musique",
                "defaultQualityProfileId": client.profile_id("qualityprofile", "Standard"),
                "defaultMetadataProfileId": client.profile_id("metadataprofile", "Standard"),
            }
        _folder, created = client.ensure_root_folder(path, extra)
        present = any(
            f.get("path", "").rstrip("/") == path.rstrip("/")
            for f in client.get("rootfolder") or []
        )
        return StepResult(
            f"{arr_id}: dossier racine {path}",
            ok=present,
            detail=t("cree") if created else t("deja present"),
            created=created,
        )

    def _conseil_config_existante(self, sid: str) -> str:
        """Explication a joindre quand un service refuse nos identifiants.

        Trois services ne stockent leur mot de passe que HACHE : Jellyfin,
        autobrr et qui. Si leur configuration vient d'une installation
        precedente, plugarr ne peut ni le relire ni le reinitialiser — aucune
        API ne le permet sans le mot de passe actuel.

        Le message brut (« connexion a echoue », « HTTP 401 ») envoyait chercher
        une panne reseau. La cause est ailleurs, et la solution tient en une
        ligne.
        """
        from pathlib import Path

        dossier = Path(self.cfg.config_path(sid))
        if not (dossier.is_dir() and any(dossier.iterdir())):
            return ""
        connus = len(reprise.mots_de_passe_connus(self.cfg.project_dir, sid))
        if connus:
            return t(
                "{service} a une configuration prealable dans {dossier}, et son mot "
                "de passe n'y est stocke que hache. PlugArr a essaye les {nombre} "
                "mots de passe qu'il connait pour ce service : aucun n'est accepte. "
                "Supprimez ce dossier pour repartir a zero — vous perdrez ce que ce "
                "service seul contenait, pas vos medias.",
                service=sid,
                dossier=dossier,
                nombre=connus,
            )
        return t(
            "{service} a une configuration prealable dans {dossier}. Son mot de "
            "passe n'y est stocke que hache : PlugArr ne peut pas le retrouver, et "
            "celui qu'il annonce est refuse. Aucune installation precedente de "
            "PlugArr n'est connue sur cette machine — ce service a donc ete "
            "configure autrement. Supprimez ce dossier pour repartir a zero.",
            service=sid,
            dossier=dossier,
        )

    def _unban_download_client(self, dl_id: str) -> bool:
        """Redemarre un client de telechargement pour lever un bannissement.

        qBittorrent bannit une adresse apres cinq echecs d'authentification, une
        heure durant. Le bannissement est PAR ADRESSE : sonde depuis l'hote, tout
        va bien ; depuis le conteneur Sonarr, c'est un 403. Le *arr traduit ce
        403 en « Authentication Failure » et accuse les identifiants, alors
        qu'ils sont corrects.

        Vu en conditions reelles : 204 depuis l'hote et 403 depuis Sonarr, au
        meme instant, avec le meme mot de passe. Un redemarrage vide la liste des
        bannis.
        """
        from pathlib import Path

        from .runner import Compose

        if dl_id != "qbittorrent" or self.cfg.project_dir is None:
            return False
        runner = Compose(Path(str(self.cfg.project_dir)), self.cfg.project_name)
        ok, _ = runner.control("restart", dl_id)
        if not ok:
            return False
        with QBittorrentClient(
            self.cfg.services[dl_id].url(self.cfg.host),
            self.cfg.services[dl_id].username or "",
            self.cfg.services[dl_id].password or "",
        ) as client:
            client.wait_ready(timeout=120.0)
        return True

    def adresse_client(self, dl_id: str) -> tuple[str, int]:
        """Ou joindre un client de telechargement DEPUIS un conteneur.

        S'appuie sur `internal_url`, qui porte deja les trois cas — service
        adopte, client sous VPN, cas ordinaire — et n'ajoute que la
        decomposition en hote et port, parce que les *arr et Prowlarr veulent
        deux champs la ou Flood ou qui veulent une URL.

        Cette resolution a ete recopiee en clair a plusieurs endroits, et chaque
        copie a fini par diverger. Constate le 2026-09-03, VPN active :

            ECHEC prowlarr/downloadclient/transmission
              Unknown exception: Name does not resolve (transmission:9091)

        pendant que Sonarr, Radarr et Lidarr se cablaient tres bien sur les
        MEMES clients, ce qui rendait la panne illisible. Une seule source.
        """
        url = self.internal_url(dl_id)
        reste = url.split("://", 1)[1]
        hote, _, port = reste.partition(":")
        return hote, int(port.split("/", 1)[0])

    def step_download_client(self, arr_id: str, dl_id: str) -> StepResult:
        """Rattache un client de telechargement a un *arr.

        Les noms de champs et le mode de routage varient selon le client et selon
        l'application : toute cette variabilite est isolee dans downloadclients.py,
        pour que cette etape reste identique quel que soit le couple.
        """
        client = self.arr(arr_id)
        profile = profile_for(dl_id)
        dl_spec = catalog.get(dl_id)
        dl = self.cfg.services[dl_id]

        # Le mot de passe d'un client ADOPTE est hache dans sa configuration,
        # donc illisible : il doit venir de l'utilisateur.
        if dl.adopted and not dl.password:
            return StepResult(
                f"{arr_id}: client de telechargement {dl_spec.display_name}",
                ok=False,
                detail=t("identifiants inconnus"),
                warnings=[
                    t(
                        "Le mot de passe de {service} est hache dans sa "
                        "configuration : plugarr ne peut pas le lire. Passez "
                        "--dl-user et --dl-pass.",
                        service=dl_spec.display_name,
                    )
                ],
            )
        host, port = self.adresse_client(dl_id)

        values = profile.arr_values(
            host=host,
            port=port,
            username=dl.username or "",
            password=dl.password or "",
            arr_id=arr_id,
        )
        if dl.adopted:
            # Ne pas imposer notre arborescence a une stack existante : on laisse
            # le routage par categorie et on efface tout repertoire que le profil
            # aurait pose.
            values = {k: ("" if k.endswith("Directory") else v) for k, v in values.items()}
        obj, created, skipped = client.ensure_resource(
            "downloadclient",
            name=dl_spec.display_name,
            implementation=profile.implementation,
            values=values,
            extra={"enable": True, "protocol": profile.protocol, "priority": 1},
        )
        warnings = (
            [f"champs absents du gabarit {arr_id}, ignores: {', '.join(skipped)}"]
            if skipped
            else []
        )

        etat = t("cree") if created else t("deja present")
        if not created:
            # Une entree existante garde les identifiants d'alors. Si le mot de
            # passe du client a change depuis — une reinstallation suffit — elle
            # reste en place et son test echoue, sans que rien ne l'explique. On
            # realigne les seuls champs d'identification.
            identifiants = {nom: values[nom] for nom in ("username", "password") if nom in values}
            try:
                modifies = client.sync_fields("downloadclient", obj, identifiants)
            except WiringError:
                # Un bannissement se presente comme un refus d'identifiants. On
                # le leve une fois, puis on reessaie : si l'echec persiste, c'est
                # bien le mot de passe qui est en cause.
                if not self._unban_download_client(dl_id):
                    raise
                modifies = client.sync_fields("downloadclient", obj, identifiants)
            if modifies:
                etat = t("identifiants mis a jour ({champs})", champs=", ".join(modifies))

        result = StepResult(
            f"{arr_id}: client de telechargement {dl_spec.display_name}",
            ok=client.find_by_name("downloadclient", dl_spec.display_name) is not None,
            detail=etat + f" (id={obj.get('id', '?')})",
            created=created,
            warnings=warnings,
        )
        return self._verify(
            client,
            "downloadclient",
            dl_spec.display_name,
            result,
            on_auth_failure=lambda: self._unban_download_client(dl_id),
        )

    def step_qbittorrent_categories(self) -> StepResult:
        """Cree les categories qBittorrent avec leur chemin de sauvegarde."""
        inst = self.cfg.services["qbittorrent"]
        if inst.adopted:
            # Meme raison que pour les dossiers racine : un client existant a deja
            # ses categories et ses chemins. Les ecraser deplacerait les
            # telechargements en cours de quelqu'un.
            return StepResult(
                "qbittorrent: categories",
                ok=True,
                detail=t("client existant, categories laissees telles quelles"),
            )
        url = f"http://{self.cfg.host}:{inst.host_port}"
        with QBittorrentClient(url, inst.username or "", inst.password or "") as qb:
            qb.wait_ready()
            # TOUTES les bibliotheques, pas seulement celles qu'une application
            # pilote. Une categorie « livres » qui range dans /data/torrents/books
            # sert des le premier telechargement manuel, et elle sera deja la le
            # jour ou Shelfarr ou Audiobookshelf entrent au catalogue. Sans elle,
            # tout finit en vrac a la racine des torrents.
            wanted = {
                b.id: b.torrents
                for b in BIBLIOTHEQUES
                if b.arr is None or self.cfg.enabled(b.arr)
            }
            if self.cfg.enabled("prowlarr"):
                # Prowlarr cree sinon lui-meme une categorie "prowlarr" SANS chemin
                # de sauvegarde. On la pose d'abord, avec le bon chemin : nos etapes
                # Prowlarr passent apres celle-ci dans le plan.
                wanted["prowlarr"] = CONTAINER_PATHS["torrents_root"]
            made = [c for c, path in wanted.items() if qb.ensure_category(c, path)]
            present = set(qb.categories())
        expected = set(wanted)
        return StepResult(
            "qbittorrent: categories avec chemin de sauvegarde",
            ok=expected <= present,
            detail=t("creees : {noms}", noms=", ".join(made) or t("aucune (deja presentes)")),
            created=bool(made),
        )

    def step_qbittorrent_rss(self) -> StepResult:
        """Allume le lecteur RSS de qBittorrent et son telechargement auto.

        Demande a l'usage. qBittorrent livre le moteur RSS actif mais le
        telechargement automatique ETEINT : une regle ecrite ne se declenche
        jamais, et rien ne l'explique. Constate sur une instance 5.2.3 installee
        par plugarr.

        plugarr n'ajoute aucun flux ni aucune regle : ils dependent de vos
        traqueurs, comme les indexeurs de Prowlarr. Il pose l'interrupteur.
        """
        inst = self.cfg.services["qbittorrent"]
        if inst.adopted:
            return StepResult(
                "qbittorrent: lecteur RSS",
                ok=True,
                detail=t("client existant, reglages laisses tels quels"),
            )
        url = f"http://{self.cfg.host}:{inst.host_port}"
        with QBittorrentClient(url, inst.username or "", inst.password or "") as qb:
            # `wait_ready` ouvre la session au passage. Sans elle, la premiere
            # lecture des preferences repond 403 et l'etape echoue en annoncant
            # « preferences illisibles » — constate au premier essai reel.
            qb.wait_ready()
            changes = qb.ensure_rss()
            relu = qb.preferences()
        actif = relu.get("rss_auto_downloading_enabled") is True
        return StepResult(
            "qbittorrent: lecteur RSS",
            # Relu depuis l'application : `setPreferences` repond 200 meme pour
            # un reglage qu'il ignore ensuite.
            ok=actif,
            detail=(
                t(
                    "actif, rafraichi toutes les {minutes} min",
                    minutes=relu.get("rss_refresh_interval"),
                )
                + (
                    t(" (change : {champs})", champs=", ".join(changes))
                    if changes
                    else t(" (deja actif)")
                )
            ),
            created=bool(changes),
            warnings=(
                []
                if actif
                else [t("le telechargement automatique RSS n'a pas pu etre active")]
            ),
        )

    def step_prowlarr_application(self, arr_id: str) -> StepResult:
        """Enregistre Sonarr/Radarr comme Application dans Prowlarr.

        C'est le lien qui fait descendre automatiquement tous les indexeurs de
        Prowlarr vers les *arr. `syncLevel=fullSync` maintient la synchronisation.
        """
        prowlarr = self.arr("prowlarr")
        target = self.cfg.services[arr_id]
        implementation = catalog.get(arr_id).display_name  # "Sonarr" / "Radarr"

        values = {
            "prowlarrUrl": self.internal_url("prowlarr"),
            "baseUrl": self.internal_url(arr_id),
            "apiKey": target.api_key,
            "syncCategories": SYNC_CATEGORIES[arr_id],
        }
        obj, created, skipped = prowlarr.ensure_resource(
            "applications",
            name=implementation,
            implementation=implementation,
            values=values,
            extra={"syncLevel": "fullSync"},
        )
        warnings = (
            [f"champs absents du gabarit Prowlarr, ignores: {', '.join(skipped)}"]
            if skipped
            else []
        )
        etat = t("cree") if created else t("deja present")
        if not created:
            # Prowlarr garde la cle API du *arr DANS son entree Application.
            # `ensure_resource` ne touche jamais a l'existant : apres une
            # rotation de cle, Prowlarr continuait donc a presenter l'ancienne
            # et ne poussait plus aucun indexeur — sans que rien ne le dise.
            # Meme angle mort que pour les clients de telechargement et autobrr,
            # a ceci pres que celui-la se declare « deja present » et vert.
            modifies = prowlarr.sync_fields("applications", obj, values)
            if modifies:
                etat = t("realigne ({champs})", champs=", ".join(modifies))
        result = StepResult(
            f"prowlarr -> {arr_id} (Application, fullSync)",
            ok=prowlarr.find_by_name("applications", implementation) is not None,
            detail=etat + f" (id={obj.get('id', '?')})",
            created=created,
            warnings=warnings,
        )
        return self._verify(prowlarr, "applications", implementation, result)

    def step_prowlarr_download_client(self, dl_id: str) -> StepResult:
        prowlarr = self.arr("prowlarr")
        profile = profile_for(dl_id)
        dl_spec = catalog.get(dl_id)
        dl = self.cfg.services[dl_id]
        hote, port = self.adresse_client(dl_id)

        obj, created, skipped = prowlarr.ensure_resource(
            "downloadclient",
            name=dl_spec.display_name,
            implementation=profile.implementation,
            values=profile.prowlarr_values(
                # La MEME adresse que pour les *arr. La poser en dur ici
                # cassait tout cablage sous VPN.
                host=hote,
                port=port,
                username=dl.username or "",
                password=dl.password or "",
            ),
            extra={"enable": True, "protocol": profile.protocol, "priority": 1},
        )
        warnings = [f"champs ignores: {', '.join(skipped)}"] if skipped else []

        etat = t("cree") if created else t("deja present")
        if not created:
            # Meme raison que pour les *arr : une entree existante garde les
            # identifiants d'alors, et son test echoue apres un changement de mot
            # de passe. Prowlarr passe par une etape distincte, il avait donc
            # ete oublie — 13 liens sur 14 au lieu de 14.
            identifiants = {"username": dl.username or "", "password": dl.password or ""}
            try:
                modifies = prowlarr.sync_fields("downloadclient", obj, identifiants)
            except WiringError:
                if not self._unban_download_client(dl_id):
                    raise
                modifies = prowlarr.sync_fields("downloadclient", obj, identifiants)
            if modifies:
                etat = t("identifiants mis a jour ({champs})", champs=", ".join(modifies))

        result = StepResult(
            f"prowlarr: client de telechargement {dl_spec.display_name}",
            ok=prowlarr.find_by_name("downloadclient", dl_spec.display_name) is not None,
            detail=etat + f" (id={obj.get('id', '?')})",
            created=created,
            warnings=warnings,
        )
        return self._verify(
            prowlarr,
            "downloadclient",
            dl_spec.display_name,
            result,
            on_auth_failure=lambda: self._unban_download_client(dl_id),
        )

    def step_jellyfin_notification(self, arr_id: str) -> StepResult:
        """Fait rafraichir la bibliotheque Jellyfin apres chaque import."""
        client = self.arr(arr_id)
        jf_spec = catalog.get("jellyfin")
        jf_key = self.cfg.services["jellyfin"].api_key
        if not jf_key:
            raise WiringError(
                t("{service} -> jellyfin : cle API Jellyfin absente", service=arr_id),
                t("l'etape jellyfin/setup ne s'est pas executee ou a echoue"),
                t("relancez `plugarr wire` : la cle est creee par cette etape"),
            )
        values = {
            "host": jf_spec.id,
            "port": jf_spec.internal_port,
            "useSsl": False,
            "apiKey": jf_key,
            "updateLibrary": True,
            "notify": False,
        }
        obj, created, skipped = client.ensure_resource(
            "notification",
            name="Jellyfin",
            implementation="MediaBrowser",
            values=values,
            extra={
                "onDownload": True,
                "onUpgrade": True,
                "onRename": True,
                "onMovieDelete": True,
                "onEpisodeFileDelete": True,
            },
        )
        warnings = [f"champs ignores: {', '.join(skipped)}"] if skipped else []
        result = StepResult(
            f"{arr_id} -> jellyfin (rafraichissement de bibliotheque)",
            ok=client.find_by_name("notification", "Jellyfin") is not None,
            detail=(t("cree") if created else t("deja present")) + f" (id={obj.get('id', '?')})",
            created=created,
            warnings=warnings,
        )
        return self._verify(client, "notification", "Jellyfin", result)

    def step_jellyfin_setup(self) -> StepResult:
        inst = self.cfg.services["jellyfin"]
        url = f"http://{self.cfg.host}:{inst.host_port}"
        with JellyfinClient(url) as jf:
            jf.wait_ready()
            choisie = langues.resoudre(self.cfg.language)
            ran = jf.run_startup_wizard(
                admin_user=inst.username or "plugarr",
                admin_password=inst.password or "",
                ui_culture=choisie.code,
                country=choisie.pays,
                metadata_language=choisie.code,
            )
            repris = self._connexion_rattrapee(
                "jellyfin",
                inst,
                lambda mot: jf.authenticate(inst.username or "plugarr", mot),
            )
            # La cle API alimente les notifications Sonarr/Radarr -> Jellyfin,
            # qui refusent un apiKey vide. Elle est reinjectee dans la config
            # pour etre persistee dans .env et stack.yml.
            inst.api_key = jf.ensure_api_key("plugarr")
            wanted = [
                (arr_id, name, ctype, path)
                for arr_id, name, ctype, path in (
                    ("radarr", "Films", "movies", CONTAINER_PATHS["media_movies"]),
                    ("sonarr", "Series", "tvshows", CONTAINER_PATHS["media_tv"]),
                    ("lidarr", "Musique", "music", CONTAINER_PATHS["media_music"]),
                )
                if self.cfg.enabled(arr_id)
            ]
            made = [
                name for _a, name, ctype, path in wanted if jf.ensure_library(name, ctype, path)
            ]
            names = {lib.get("Name") for lib in jf.libraries()}
            # Les bibliotheques sont creees sans analyse, pour ne pas bloquer
            # l'installation. Encore faut-il en lancer une : sans elle Jellyfin
            # garde un index VIDE, et les notifications d'import de Sonarr — qui
            # repondent pourtant 200 — n'y changent rien. Constate sur une stack
            # reelle, deux episodes sur le disque et zero dans Jellyfin.
            analyse = jf.refresh_libraries()
        ok = {name for _a, name, _c, _p in wanted} <= names
        detail = t("assistant execute") if ran else t("assistant deja termine")
        if repris:
            detail += t(", mot de passe repris de l'installation precedente")
        detail += f", bibliotheques creees: {', '.join(made) or 'aucune (deja presentes)'}"
        detail += ", analyse lancee" if analyse else ""
        return StepResult(
            "jellyfin: assistant + bibliotheques",
            ok=ok,
            detail=detail,
            created=ran,
            warnings=[]
            if analyse
            else [t("l'analyse des bibliotheques n'a pas pu etre lancee")],
        )

    def step_langue(self, arr_id: str) -> StepResult:
        """Pose la langue de l'interface d'un *arr.

        Sans elle, plugarr livrait une stack dont Jellyfin parlait francais —
        impose en dur — et dont Sonarr, Radarr et Prowlarr parlaient anglais.
        Une incoherence que personne n'avait choisie.
        """
        valeur = langues.arr_ui_language(self.cfg.language)
        if valeur is None:
            return StepResult(
                f"{arr_id}: langue de l'interface",
                ok=True,
                detail=f"{self.cfg.language} inconnue de {arr_id}, interface laissee telle quelle",
            )
        change = self.arr(arr_id).set_ui_language(self.cfg.language, valeur)
        relu = self.arr(arr_id).get("config/ui").get("uiLanguage")
        return StepResult(
            f"{arr_id}: langue de l'interface",
            # Relu depuis l'application : « le PUT est passe » ne prouve rien.
            # La valeur attendue depend du type expose — entier ou code.
            ok=relu in (valeur, self.cfg.language),
            detail=f"{self.cfg.language}" + ("" if change else t(" (deja posee)")),
            created=change,
        )

    def _hote_port(self, service_id: str) -> tuple[str, int]:
        """Hote et port d'un service, separes.

        Seerr recompose l'URL lui-meme a partir de trois champs : lui en passer
        une toute faite rend « INVALID_URL ».
        """
        reste = self.internal_url(service_id).split("://", 1)[1]
        hote, _, port = reste.partition(":")
        return hote, int(port.split("/", 1)[0])

    def _redemarrer(self, service_id: str) -> bool:
        """Redemarre UN conteneur. Renvoie False si on ne peut pas.

        Certaines applications accusent reception d'un changement et ne
        l'appliquent qu'au demarrage suivant : les *arr le font pour leur cle
        API et pour les identifiants de leur interface web.
        """
        if not self.cfg.project_dir:
            return False
        from pathlib import Path

        from .runner import Compose

        ok, _message = Compose(
            Path(str(self.cfg.project_dir)), self.cfg.project_name
        ).control("restart", service_id)
        return ok

    def step_seerr_setup(self) -> StepResult:
        """Accueil de Seerr et declaration des *arr.

        Seerr n'a pas de mot de passe a lui : son administrateur EST le compte
        Jellyfin. C'est sa specification qui le dit — s'authentifier contre le
        serveur media cree le premier compte avec les pleins droits. PlugArr
        n'en genere donc aucun pour lui, et ne pretend pas le contraire.

        L'ordre est impose. `settings/initialize` ferme l'accueil : l'appeler
        avant d'avoir declare les *arr laisse une instance qui se croit prete
        et ne peut rien demander.
        """
        from .clients.seerr import SeerrClient

        inst = self.cfg.services["seerr"]
        jellyfin = self.cfg.services["jellyfin"]
        identifiant = jellyfin.username or self.cfg.username

        declares: list[str] = []
        with SeerrClient(inst.url(self.cfg.host)) as seerr:
            seerr.wait_ready()
            deja = seerr.initialized
            # L'hote et le port SEPAREMENT : Seerr les recompose lui-meme, et
            # lui passer une URL complete rend « INVALID_URL ».
            hote_jf, port_jf = self._hote_port("jellyfin")
            seerr.login_jellyfin(
                username=identifiant,
                password=jellyfin.password or "",
                hostname=hote_jf,
                port=port_jf,
            )

            for arr_id, genre, dossier, anime in (
                ("sonarr", "sonarr", CONTAINER_PATHS["media_tv"], CONTAINER_PATHS["media_anime"]),
                ("radarr", "radarr", CONTAINER_PATHS["media_movies"], None),
            ):
                if not self.cfg.enabled(arr_id):
                    continue
                client = self.arr(arr_id)
                profils = client.get("qualityprofile") or []
                if not profils:
                    continue
                # Le profil par NOM, jamais par identifiant : ils ne sont pas
                # stables d'une version a l'autre.
                profil = profils[0]
                hote, port = self._hote_port(arr_id)
                if seerr.ensure_servarr(
                    genre,
                    name=catalog.get(arr_id).display_name,
                    hostname=hote,
                    port=port,
                    api_key=self.cfg.services[arr_id].api_key or "",
                    profile_id=int(profil["id"]),
                    profile_name=str(profil["name"]),
                    directory=dossier,
                    anime_directory=anime,
                ):
                    declares.append(arr_id)

            # EN DERNIER, une fois les *arr declares.
            if not deja:
                seerr.initialize()
            pret = seerr.initialized

        detail = t("accueil deja termine") if deja else t("accueil execute")
        detail += f", identifiant Jellyfin ({identifiant})"
        if declares:
            detail += f", declares : {', '.join(declares)}"
        return StepResult(
            "seerr: accueil + applications",
            # Relu depuis l'application : « initialise » est son propre verdict.
            ok=pret,
            detail=detail,
            created=not deja or bool(declares),
        )

    def step_sabnzbd_categories(self) -> StepResult:
        """Pose les categories de SABnzbd, avec leur repertoire.

        Ce sont elles qui font atterrir un telechargement de Sonarr dans
        `/data/usenet/tv` : les *arr n'envoient qu'un NOM de categorie, jamais
        un chemin.

        SABnzbd en livre d'usine — `movies`, `tv`, `audio`, `software` — avec un
        repertoire VIDE. Se contenter de les creer si absentes les laisserait
        inutilisables : le nom existe, Sonarr l'accepte, et tout atterrit dans
        le repertoire par defaut. Voir `ensure_category`.
        """
        from .clients.sabnzbd import SabnzbdClient

        inst = self.cfg.services["sabnzbd"]
        if inst.adopted:
            return StepResult(
                "sabnzbd: categories",
                ok=True,
                detail=t("client existant, categories laissees telles quelles"),
            )

        url = f"http://{self.cfg.host}:{inst.host_port}"
        with SabnzbdClient(url, inst.password or "") as sab:
            sab.wait_ready()
            voulues = {
                b.id: b.usenet
                for b in BIBLIOTHEQUES
                if b.arr is None or self.cfg.enabled(b.arr)
            }
            if self.cfg.enabled("prowlarr"):
                # Prowlarr envoie sa propre categorie et REFUSE de se declarer
                # si elle n'existe pas cote client : « The category you entered
                # doesn't exist in Sabnzbd. Go to Sabnzbd to create it. » Meme
                # exigence que pour qBittorrent, et meme remede.
                voulues["prowlarr"] = CONTAINER_PATHS["usenet_root"]

            posees = [nom for nom, chemin in voulues.items() if sab.ensure_category(nom, chemin)]

            # SABnzbd reecrit tout son fichier de configuration a chaque
            # `set_config`. Une pose peut se perdre quand elles s'enchainent —
            # constate sur la premiere de la serie, restee sans repertoire
            # pendant que les six suivantes passaient. On relit et on repose ce
            # qui manque, une fois : c'est moins couteux qu'une temporisation
            # posee au juge.
            for nom, chemin in voulues.items():
                if sab.categories().get(nom) != chemin and sab.ensure_category(nom, chemin):
                    posees.append(nom)
            relues = sab.categories()

        manquantes = [n for n, c in voulues.items() if relues.get(n) != c]
        return StepResult(
            "sabnzbd: categories avec repertoire",
            # Relu depuis l'application : un `set_config` accepte ne prouve rien.
            ok=not manquantes,
            detail=t("posees : {noms}", noms=", ".join(posees) or t("aucune (deja completes)")),
            created=bool(posees),
            warnings=(
                []
                if not manquantes
                else [
                    t(
                        "categories sans repertoire : {noms}",
                        noms=", ".join(manquantes),
                    )
                ]
            ),
        )

    def step_droppedneedle_setup(self) -> StepResult:
        """Accueil de DroppedNeedle, serveur media et client de telechargement.

        Il REMPLACE Lidarr plutot qu'il ne le complete : il gere la musique de
        la demande au rangement. Il est reste hors du catalogue tant qu'aucun
        client de telechargement ne l'accompagnait — c'est SABnzbd qui l'a
        debloque, et c'est pourquoi il le tire comme prerequis.

        Jellyfin est declare s'il est present, sans etre exige : DroppedNeedle
        sait tenir une bibliotheque locale seul, et forcer un serveur media a
        qui ne veut que de la musique n'aurait pas de sens.
        """
        from .clients.droppedneedle import DroppedNeedleClient

        inst = self.cfg.services["droppedneedle"]
        identifiant = inst.username or self.cfg.username
        faits: list[str] = []

        with DroppedNeedleClient(inst.url(self.cfg.host)) as dn:
            dn.wait_ready()
            cree = dn.setup(username=identifiant, password=inst.password or "")
            # TOUJOURS se connecter : l'accueil pose bien un cookie, mais un
            # second passage n'appelle pas l'accueil et resterait sans session.
            dn.login(identifiant, inst.password or "")

            # L'etape `jellyfin/setup`, qui precede celle-ci dans le plan, a
            # deja cree une cle API et l'a rangee dans la configuration. En
            # demander une seconde en creerait une de plus a chaque passage, et
            # Jellyfin les accumule sans jamais les nettoyer.
            jf = self.cfg.services.get("jellyfin")
            if (
                jf is not None
                and jf.api_key
                and dn.ensure_jellyfin(url=self.internal_url("jellyfin"), api_key=jf.api_key)
            ):
                faits.append("Jellyfin")

            sab = self.cfg.services["sabnzbd"]
            if dn.ensure_sabnzbd(
                url=self.internal_url("sabnzbd"),
                api_key=sab.api_key or sab.password or "",
                # La categorie que l'etape SABnzbd vient de creer, avec son
                # repertoire : sans elle, tout atterrirait a la racine.
                categorie="music",
                # Les deux conteneurs montent ${DATA_ROOT} sur /data : rien a
                # remapper, et l'import lie au lieu de recopier.
                montage=CONTAINER_PATHS["usenet_root"],
            ):
                faits.append("SABnzbd")

            teste, detail_test = dn.test_sabnzbd() if self.run_tests else (True, "")

        detail = t("accueil execute") if cree else t("accueil deja termine")
        if faits:
            detail += f", declares : {', '.join(faits)}"
        if self.run_tests:
            detail += f", test SABnzbd : {'OK' if teste else detail_test[:80]}"
        return StepResult(
            "droppedneedle: accueil + client de telechargement",
            ok=teste,
            detail=detail,
            created=cree or bool(faits),
        )

    def step_audiobookshelf_setup(self) -> StepResult:
        """Accueil d'Audiobookshelf et creation de ses deux bibliotheques.

        Il ne se cable a personne : il lit des dossiers. Ce sont justement les
        deux bibliotheques `books` et `audiobooks` que PlugArr cree depuis la
        0.1.12 et que rien ne pilotait encore.

        Deux fausses pistes consignees dans le client, parce qu'elles coutent
        cher : il met QUARANTE SECONDES a demarrer, et sa base SQLite se lit
        avec son journal `-wal` ou pas du tout.
        """
        from .clients.audiobookshelf import PROVIDERS, AudiobookshelfClient

        inst = self.cfg.services["audiobookshelf"]
        identifiant = inst.username or self.cfg.username
        with AudiobookshelfClient(inst.url(self.cfg.host)) as abs_client:
            abs_client.wait_ready()
            cree = abs_client.setup(username=identifiant, password=inst.password or "")
            # TOUJOURS se connecter, meme apres avoir cree le compte a l'instant.
            # `POST /init` repond 200 avec un corps VIDE : il ne rend aucun
            # jeton, contrairement a Silo dont l'accueil en renvoie deux. Sans
            # cette connexion, l'appel suivant repond « HTTP 401 Unauthorized »
            # et le message d'aide envoie chercher un accueil deja fait qui
            # n'existe pas. Constate au premier essai reel.
            abs_client.login(identifiant, inst.password or "")

            faites = [
                nom
                for nom, chemin, genre in (
                    ("Livres audio", "/audiobooks", "audiobooks"),
                    ("Livres", "/books", "books"),
                )
                if abs_client.ensure_library(nom, chemin, provider=PROVIDERS[genre])
            ]
            existantes = abs_client.libraries()
            # Une bibliotheque creee ne s'analyse pas toute seule : sans cela
            # elle reste vide jusqu'a la prochaine analyse planifiee, et
            # l'utilisateur croit que rien n'a fonctionne.
            analyses = sum(1 for b in existantes if abs_client.scan(b["id"]))

        detail = t("accueil execute") if cree else t("accueil deja termine")
        if faites:
            detail += f", bibliotheques creees: {', '.join(faites)}"
        detail += f", {analyses} analyse(s) lancee(s)"
        return StepResult(
            "audiobookshelf: accueil + bibliotheques",
            # Relu depuis l'application : deux bibliotheques doivent exister.
            ok=len(existantes) >= 2,
            detail=detail,
            created=cree or bool(faites),
        )

    def step_silo_setup(self) -> StepResult:
        """Accueil de Silo et creation de ses bibliotheques.

        Meme forme que Jellyfin, et pour la meme raison : creer un compte, s'y
        connecter avec les identifiants ANNONCES, puis poser les bibliotheques.

        Silo monte les medias en LECTURE SEULE. Il lit ce que les *arr
        organisent, il n'y touche pas : les deux cohabitent sans se marcher
        dessus, et c'est verifie par le montage lui-meme, pas espere.
        """
        from .clients.silo import SiloClient

        inst = self.cfg.services["silo"]
        identifiant = inst.username or self.cfg.username
        with SiloClient(inst.url(self.cfg.host)) as silo:
            # Silo redemarre en boucle tant que sa base n'est pas prete :
            # trente secondes observees au premier demarrage. Attendre son API
            # plutot que son conteneur evite de cabler dans le vide.
            silo.wait_ready()
            cree = silo.setup(username=identifiant, password=inst.password or "")
            if not cree:
                # Accueil deja fait : on se connecte, ce qui VERIFIE au passage
                # que les identifiants annonces ouvrent bien la porte.
                silo.login(identifiant, inst.password or "")

            # Le compte ne suffit pas : sans PROFIL, Silo affiche « You need a
            # profile before you can enter the app » et bloque l'entree.
            profil = silo.ensure_profile(identifiant)

            voulues = [
                (nom, genre, chemin)
                for nom, genre, chemin in (
                    ("Films", "movie", SILO_MEDIA["movies"]),
                    ("Series", "show", SILO_MEDIA["tv"]),
                    ("Musique", "music", SILO_MEDIA["music"]),
                )
            ]
            faites = [
                nom
                for nom, genre, chemin in voulues
                if silo.ensure_library(nom, genre, chemin, language=self.cfg.language)
            ]
            existantes = silo.libraries()
            noms = {lib.get("name") for lib in existantes}
            # Comme Jellyfin : une bibliotheque creee ne s'analyse pas toute
            # seule, et une mediatheque vide donne l'impression que rien n'a
            # marche.
            analysees = sum(1 for lib in existantes if silo.refresh_metadata(lib["id"]))

        ok = {nom for nom, _g, _c in voulues} <= noms
        detail = t("accueil execute") if cree else t("accueil deja termine")
        detail += ", profil cree" if profil else ""
        detail += f", bibliotheques creees: {', '.join(faites) or 'aucune (deja presentes)'}"
        detail += f", {analysees} analyse(s) lancee(s)" if analysees else ""
        return StepResult(
            "silo: accueil + bibliotheques",
            ok=ok,
            detail=detail,
            created=cree,
            # L'avertissement du projet est repris a CHAQUE installation, pas
            # seulement dans le catalogue : celui qui lit le rapport doit le
            # voir, meme s'il n'a pas lu la page d'acces.
            warnings=[t(catalog.get("silo").experimental)],
        )

    def step_autobrr(self) -> StepResult:
        """Declare les applications et le client de telechargement dans autobrr.

        autobrr ne distingue pas les deux : Sonarr et qBittorrent passent par le
        meme endpoint, seul le `type` change.
        """
        inst = self.cfg.services["autobrr"]
        url = f"http://{self.cfg.host}:{inst.host_port}"
        created: list[str] = []
        warnings: list[str] = []

        with AutobrrClient(url) as brr:
            brr.wait_ready()
            first = brr.onboard(inst.username or "plugarr", inst.password or "")
            repris = self._connexion_rattrapee(
                "autobrr",
                inst,
                lambda mot: brr.login(inst.username or "plugarr", mot),
            )
            inst.api_key = brr.ensure_api_key("plugarr")

            targets = [
                sid
                for sid in (*catalog.MANAGED_ARRS, *catalog.DOWNLOAD_CLIENTS)
                if self.cfg.enabled(sid)
            ]
            for sid in targets:
                spec, target = catalog.get(sid), self.cfg.services[sid]
                added, _ = brr.ensure_client(
                    name=spec.display_name,
                    service_id=sid,
                    host=self.internal_url(sid),
                    api_key=target.api_key,
                    username=target.username or "",
                    password=target.password or "",
                )
                if added:
                    created.append(spec.display_name)
                if self.run_tests:
                    ok, message = brr.test_client(spec.display_name)
                    if not ok:
                        warnings.append(f"{spec.display_name} : {message.splitlines()[0]}")

        detail = t("accueil execute") if first else t("utilisateur existant")
        if repris:
            detail += t(", mot de passe repris de l'installation precedente")
        detail += t(
            ", declares : {noms}",
            noms=", ".join(created) or t("aucun (deja presents)"),
        )
        return StepResult(
            "autobrr: applications et client de telechargement",
            ok=not warnings,
            detail=detail,
            created=bool(created),
            warnings=warnings,
        )

    def step_recyclarr(self) -> StepResult:
        """Genere la configuration Recyclarr et y ecrit adresses et cles.

        plugarr ne reimplemente pas les TRaSH Guides : il demande a Recyclarr de
        generer sa configuration a partir de templates OFFICIELS, puis remplace
        les marqueurs `Put your ... here`. Tout le contenu des profils reste
        celui du guide.
        """
        from pathlib import Path

        from .runner import Compose

        config_dir = Path(self.cfg.config_path("recyclarr"))
        runner = Compose(self.cfg.project_dir or Path("."), self.cfg.project_name)

        wanted = {
            sid: self.cfg.recyclarr_templates.get(sid, recyclarr_cfg.DEFAULT_TEMPLATES.get(sid, ""))
            for sid in ("sonarr", "radarr")
            if self.cfg.enabled(sid)
        }
        wanted = {sid: name for sid, name in wanted.items() if name}
        if not wanted:
            return StepResult(
                "recyclarr: profils de qualite",
                ok=True,
                detail=t("aucun template choisi, rien a generer"),
            )

        # Recyclarr REFUSE d'ecraser un fichier existant, et il a raison : celui-ci
        # a pu etre modifie a la main. On ne demande donc que ce qui manque. Sans
        # cela, rejouer `wire` echouait sur « File already exists », alors que la
        # commande est censee etre idempotente.
        #
        # `--force` existe, mais l'employer detruirait les reglages de
        # l'utilisateur a chaque passage.
        args = []
        for name in wanted.values():
            if not (config_dir / "configs" / f"{name}.yml").exists():
                args += ["--template", name]

        if args:
            ok, message = runner.run_once("recyclarr", ["config", "create", *args])
            if not ok:
                return StepResult(
                    "recyclarr: profils de qualite",
                    ok=False,
                    detail=t("generation impossible"),
                    warnings=[
                        message.splitlines()[-1][:200] if message else t("aucun detail")
                    ],
                )

        filled, kept, warnings = [], [], []

        # Un service configure par PLUSIEURS fichiers est une panne muette :
        # Recyclarr groupe ses instances par `base_url` et ecarte tout groupe qui
        # en compte plus d'une. Deux profils vises pour un meme Sonarr, et c'est
        # ZERO profil pose — Recyclarr sortant malgre tout en code 0. Le cas
        # arrive tout seul : deux installations avec des choix differents
        # laissent deux fichiers, l'ancien n'etant jamais efface.
        for path, service in recyclarr_cfg.resolve_split_instances(config_dir, wanted):
            warnings.append(
                t(
                    "{fichier} ecarte : {service} etait configure par plusieurs "
                    "fichiers, ce que Recyclarr refuse — il n'en synchronisait "
                    "alors aucun. Le fichier est renomme, pas efface.",
                    fichier=path.name,
                    service=service,
                )
            )

        for path in sorted((config_dir / "configs").glob("*.yml")):
            service = recyclarr_cfg.target_service(path)
            if service is None or not self.cfg.enabled(service):
                continue
            result = recyclarr_cfg.fill(
                path,
                self.internal_url(service),
                self.cfg.services[service].api_key or "",
                service,
            )
            # Un fichier deja renseigne n'a plus de marqueur a remplacer : ce n'est
            # pas un echec, c'est un second passage. Seul un marqueur RESTANT est
            # un probleme, et `pending_markers` le voit.
            (filled if (result.url_written or result.key_written) else kept).append(
                f"{path.stem} -> {service}"
            )

        # Un marqueur restant EMPECHE la synchronisation : c'est bloquant. Un
        # fichier ecarte plus haut ne l'est pas, il a justement ete repare.
        bloquants = [
            t(
                "{fichier} contient encore un marqueur : la synchronisation "
                "echouera tant qu'il est la",
                fichier=leftover.name,
            )
            for leftover in recyclarr_cfg.pending_markers(config_dir)
        ]
        warnings.extend(bloquants)

        parts = list(filled)
        if kept:
            # Deux cles plutot qu'une : le francais accorde « configures »
            # au pluriel, l'anglais ne change pas. Une cle unique aurait
            # force l'une des deux langues a etre fausse.
            parts.append(
                t("{nombre} deja configure", nombre=len(kept))
                if len(kept) == 1
                else t("{nombre} deja configures", nombre=len(kept))
            )

        # Premiere synchronisation immediate. Sans elle, Recyclarr n'ecrit rien
        # avant son reveil planifie : l'utilisateur ouvre Sonarr juste apres
        # l'installation, ne voit aucun profil TRaSH et en conclut que rien n'a
        # marche. La fonctionnalite doit etre visible a la fin du cablage, pas
        # vingt-quatre heures plus tard.
        # L'echec de cette synchronisation ne remet pas en cause le cablage : les
        # fichiers sont ecrits et la planification quotidienne reessaiera. C'est un
        # avertissement, pas un echec — d'ou ce `ok` calcule avant.
        # Un fichier ecarte est un probleme REPARE : le signaler ne doit pas faire
        # echouer l'etape, sinon reparer reviendrait a echouer.
        wired = not bloquants and bool(filled or kept)
        if wired:
            synced, message = runner.run_once("recyclarr", ["sync"])
            if synced:
                groups = re.findall(r"Created \d+ Profiles: \[([^\]]*)\]", message)
                names = sorted({n.strip('" ') for group in groups for n in group.split(",")})
                if names:
                    parts.append(f"synchronise : {', '.join(names)}")
                elif "Split instances" in message:
                    # Ne devrait plus arriver, la reparation passe avant. Si le cas
                    # revient, il ne doit surtout pas se lire comme un succes.
                    warnings.append(
                        t(
                            "Recyclarr a ecarte des instances en double : aucun "
                            "profil n'a ete pose. Verifiez le contenu de configs/."
                        )
                    )
                    wired = False
                else:
                    # Recyclarr sort en code 0 sans rien faire quand il n'a rien a
                    # poser. « synchronise » tout court se lisait comme un succes.
                    parts.append(t("synchronise, aucun profil a creer"))
            else:
                last = (
                    message.strip().splitlines()[-1][:200]
                    if message.strip()
                    else t("aucun detail")
                )
                warnings.append(
                    t(
                        "premiere synchronisation echouee ({cause}). La "
                        "configuration est ecrite : Recyclarr reessaiera a sa "
                        "planification quotidienne.",
                        cause=last,
                    )
                )

        return StepResult(
            "recyclarr: profils de qualite",
            ok=wired,
            detail=", ".join(parts) or t("aucun fichier rempli"),
            created=bool(filled),
            warnings=warnings,
        )

    def step_web_login(self, arr_id: str) -> StepResult:
        """Garantit que les identifiants annonces ouvrent vraiment l'interface.

        Le pre-semis ecrit `<Username>` et `<Password>` dans config.xml. Sonarr et
        Radarr les consomment au premier demarrage et creent le compte. **Prowlarr
        2.5.2 les EFFACE sans creer personne** : son interface devient
        definitivement inaccessible, puisque sa page de connexion n'offre aucune
        creation de compte. Le cablage, lui, continuait de fonctionner par cle
        API — la panne ne se voyait donc nulle part, sauf en essayant de se
        connecter.

        On teste la connexion comme un navigateur, et on ne repare que si elle
        echoue : reecrire un mot de passe deja bon serait une modification pour
        rien.
        """
        inst = self.cfg.services[arr_id]
        username, password = inst.username or "", inst.password or ""
        client = self.arr(arr_id)

        if not username or not password:
            return StepResult(
                f"{arr_id}: acces web",
                ok=True,
                detail=t("aucun identifiant genere, rien a verifier"),
            )

        if client.web_login_works(username, password):
            return StepResult(
                f"{arr_id}: acces web", ok=True, detail=t("connexion verifiee")
            )

        client.ensure_web_user(username, password)
        repaired = client.web_login_works(username, password)
        redemarre = False
        if not repaired:
            # `PUT config/host` repond 202 et n'applique les identifiants qu'au
            # REDEMARRAGE. Verifie sur Sonarr 4.0.19 : methode d'authentification
            # relue a « forms », mot de passe pose, et pourtant le formulaire
            # refusait — y compris avec un mot de passe purement alphanumerique,
            # ce qui ecarte la piste des caracteres speciaux. Un redemarrage, et
            # la connexion passe.
            #
            # C'est le meme piege que pour la cle API, ou seule la reecriture du
            # config.xml suivie d'un redemarrage fonctionnait. L'application
            # accepte, accuse reception, et ne change rien avant de repartir.
            redemarre = self._redemarrer(arr_id)
            if redemarre:
                client.wait_ready()
                repaired = client.web_login_works(username, password)

        detail = t("compte cree")
        if redemarre:
            detail += " (redemarrage necessaire)"
        if not repaired:
            detail = t("compte cree, connexion toujours refusee meme apres redemarrage")
        return StepResult(
            f"{arr_id}: acces web",
            ok=repaired,
            detail=detail,
            created=repaired,
            warnings=[]
            if repaired
            else [
                t(
                    "les identifiants annonces pour {service} n'ouvrent pas "
                    "l'interface. Definissez-en depuis Settings > General.",
                    service=arr_id,
                )
            ],
        )

    def step_qui(self) -> StepResult:
        """Relie l'interface qui a l'instance qBittorrent de la stack.

        qui ne sert a rien seule : c'est une interface pour qBittorrent. Elle
        etait installee sans lien, et redemandait a l'utilisateur une adresse et
        des identifiants que plugarr venait de generer.
        """
        inst = self.cfg.services["qui"]
        qb = self.cfg.services["qbittorrent"]
        host = self.internal_url("qbittorrent")

        with QuiClient(inst.url(self.cfg.host)) as client:
            client.wait_ready()
            client.setup(inst.username or "plugarr", inst.password or "")
            repris = self._connexion_rattrapee(
                "qui",
                inst,
                lambda mot: client.login(inst.username or "plugarr", mot),
            )
            rattrapage = t(", mot de passe repris de l'installation precedente") if repris else ""
            created = client.ensure_instance(
                name=catalog.get("qbittorrent").display_name,
                host=host,
                username=qb.username or "",
                password=qb.password or "",
            )

            if not self.run_tests:
                return StepResult(
                    "qui: instance qBittorrent",
                    ok=True,
                    detail=(t("declaree") if created else t("deja declaree")) + rattrapage,
                    created=created,
                )

            # C'est qui elle-meme qui dit si la connexion tient. Un 201 ne prouve
            # rien : une adresse sans port est acceptee puis ne se connecte jamais.
            linked, detail = client.connected(host)
            return StepResult(
                "qui: instance qBittorrent",
                ok=linked,
                detail=(t("declaree") if created else t("deja declaree"))
                + rattrapage
                + f", {detail}",
                created=created,
                warnings=[]
                if linked
                else [
                    t(
                        "qui ne parvient pas a joindre {adresse} ({cause})",
                        adresse=host,
                        cause=detail,
                    )
                ],
            )

    # -- graphe --------------------------------------------------------------

    def build_plan(self) -> list[WiringStep]:
        """Construit le graphe a partir de la selection, sans liste codee en dur.

        Ajouter un *arr ou un client de telechargement au catalogue suffit a le
        faire apparaitre ici : c'est ce qui rend la phase 2 peu couteuse.
        """
        cfg = self.cfg
        steps: list[WiringStep] = []
        arrs = [a for a in catalog.MANAGED_ARRS if cfg.enabled(a)]
        clients = [d for d in catalog.DOWNLOAD_CLIENTS if cfg.enabled(d)]

        # Prowlarr compris : c'est LUI qui n'ouvrait pas. La verification passe par
        # la page de connexion, donc elle vaut pour toute la famille.
        for arr_id in (a for a in catalog.STARTUP_ORDER if cfg.enabled(a) and _is_arr(a)):
            steps.append(WiringStep(f"{arr_id}/acces-web", lambda a=arr_id: self.step_web_login(a)))

        # La langue APRES l'acces web : les deux ecrivent dans la configuration
        # de l'application, et `config/host` d'abord evite une relecture perimee.
        if langues.arr_ui_language(cfg.language) is not None:
            for arr_id in (a for a in catalog.STARTUP_ORDER if cfg.enabled(a) and _is_arr(a)):
                steps.append(WiringStep(f"{arr_id}/langue", lambda a=arr_id: self.step_langue(a)))

        for arr_id in arrs:
            for chemin in ROOT_FOLDERS.get(arr_id, []):
                steps.append(
                    WiringStep(
                        f"{arr_id}/rootfolder/{chemin.rsplit('/', 1)[1]}",
                        lambda a=arr_id, c=chemin: self.step_root_folder(a, c),
                    )
                )

        if cfg.enabled("sabnzbd"):
            # Avant que les *arr ne le declarent : ils n'envoient qu'un nom de
            # categorie, qui doit deja porter son repertoire.
            steps.append(WiringStep("sabnzbd/categories", self.step_sabnzbd_categories))

        if cfg.enabled("qbittorrent"):
            steps.append(WiringStep("qbittorrent/rss", self.step_qbittorrent_rss))
            # Les categories doivent exister avant que les *arr n'y envoient quoi
            # que ce soit : sinon qBittorrent les cree sans chemin de sauvegarde.
            steps.append(WiringStep("qbittorrent/categories", self.step_qbittorrent_categories))

        for dl_id in clients:
            for arr_id in arrs:
                steps.append(
                    WiringStep(
                        f"{arr_id}/downloadclient/{dl_id}",
                        lambda a=arr_id, d=dl_id: self.step_download_client(a, d),
                    )
                )
            if cfg.enabled("prowlarr"):
                steps.append(
                    WiringStep(
                        f"prowlarr/downloadclient/{dl_id}",
                        lambda d=dl_id: self.step_prowlarr_download_client(d),
                    )
                )

        if cfg.enabled("prowlarr"):
            for arr_id in arrs:
                steps.append(
                    WiringStep(
                        f"prowlarr/application/{arr_id}",
                        lambda a=arr_id: self.step_prowlarr_application(a),
                    )
                )

        if cfg.enabled("recyclarr"):
            steps.append(WiringStep("recyclarr/profils", self.step_recyclarr))

        if cfg.enabled("autobrr"):
            steps.append(WiringStep("autobrr/clients", self.step_autobrr))

        # qui n'a d'interet que reliee a une instance. Sans cette etape, elle etait
        # installee puis laissee vide : l'utilisateur ouvrait une interface qui lui
        # redemandait tout ce que plugarr savait deja.
        if cfg.enabled("qui") and cfg.enabled("qbittorrent"):
            steps.append(WiringStep("qui/qbittorrent", self.step_qui))

        if cfg.enabled("jellyfin"):
            steps.append(WiringStep("jellyfin/setup", self.step_jellyfin_setup))
            for arr_id in arrs:
                if arr_id == "lidarr":
                    continue  # la notification MediaBrowser n'existe pas dans Lidarr
                steps.append(
                    WiringStep(
                        f"{arr_id}/notification/jellyfin",
                        lambda a=arr_id: self.step_jellyfin_notification(a),
                    )
                )

        if cfg.enabled("silo"):
            steps.append(WiringStep("silo/setup", self.step_silo_setup))

        # DroppedNeedle APRES les categories de SABnzbd, qu'il cite, et apres
        # Jellyfin, dont il reprend la cle API.
        if cfg.enabled("droppedneedle"):
            steps.append(
                WiringStep("droppedneedle/setup", self.step_droppedneedle_setup)
            )

        if cfg.enabled("audiobookshelf"):
            steps.append(
                WiringStep("audiobookshelf/setup", self.step_audiobookshelf_setup)
            )

        # Seerr en DERNIER : il declare les *arr et s'authentifie contre
        # Jellyfin. Les deux doivent etre cables avant lui.
        if cfg.enabled("seerr"):
            steps.append(WiringStep("seerr/setup", self.step_seerr_setup))
        return steps

    def execute(self, *, on_step: Callable[[StepResult], None] | None = None) -> list[StepResult]:
        results: list[StepResult] = []
        for step in self.build_plan():
            try:
                result = step.run()
            except WiringError as exc:
                result = StepResult(step.name, ok=False, detail=str(exc))
                # Un refus d'identifiants sur un service au mot de passe hache a
                # presque toujours la meme cause : une configuration heritee d'une
                # installation precedente. Le dire ici evite d'envoyer l'
                # utilisateur chercher une panne reseau.
                service = step.name.split("/")[0]
                if service in _HASHED_ONLY and any(
                    mot in str(exc).lower() for mot in ("401", "refus", "echoue", "unauthorized")
                ):
                    conseil = self._conseil_config_existante(service)
                    if conseil:
                        result.warnings.append(conseil)
            except Exception as exc:  # noqa: BLE001
                # Un bug dans UNE etape ne doit pas emporter tout le cablage.
                # Vu en integration : une erreur de programmation a l'avant-
                # derniere etape a fait echouer l'installation apres 40 etapes
                # reussies, sans rapport ni page d'acces — alors que tout le
                # reste etait correctement cable et fonctionnel.
                journal.LOGGER.exception("etape %s", step.name)
                result = StepResult(
                    step.name,
                    ok=False,
                    detail=t(
                        "erreur inattendue ({genre}) : {erreur}",
                        genre=type(exc).__name__,
                        erreur=exc,
                    ),
                    warnings=[
                        t("ceci est un defaut de plugarr, pas de votre installation")
                    ],
                )
            results.append(result)
            if on_step:
                on_step(result)
        return results


def _is_arr(service_id: str) -> bool:
    """Un service de la famille *arr, Prowlarr compris."""
    return catalog.get(service_id).api_family == "arr"


#: Services dont le mot de passe n'existe que hache : plugarr ne peut ni le
#: relire ni le reinitialiser sans lui.
_HASHED_ONLY = ("jellyfin", "autobrr", "qui")
