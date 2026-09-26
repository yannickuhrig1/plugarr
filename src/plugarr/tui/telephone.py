"""Ecran « Configurer mon telephone » : parite avec l'assistant web.

Demande du 26/09/2026. Memes fichiers que la page web (nzb360, qbRemote, Arr
Control), fabriques par `plugarr.telephone`, dont les sorties sont comparees a
celles de la page. Le fichier s'enregistre dans le dossier du projet, ou part
vers le telephone par un lien a usage unique, affiche en QR code dans le
terminal.
"""

from __future__ import annotations

from pathlib import Path

from rich.markup import escape
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Select, SelectionList
from textual.widgets.selection_list import Selection

from .. import telephone
from ..i18n import t
from .screens import WizardScreen
from .widgets import Button, Checkbox, Input, Static

TAILLE_MAX_SAUVEGARDE = 1024 * 1024


class PhoneScreen(WizardScreen):
    SUB_TITLE = "Configurer mon telephone"

    def __init__(self) -> None:
        super().__init__()
        self._base_nzb: dict | None = None
        self._base_erreur = ""
        self._chemin_base = ""
        #: Applications listees dans le choix des fiches, pour ne le refaire qu'au besoin.
        self._fiches_ids: list[str] = []
        #: Derniers choix vus : Textual signale aussi des changements sans
        #: changement de valeur, qui ne doivent pas decocher le consentement.
        self._choix: dict[str, str] = {}
        #: Dernier lien publie vers le telephone.
        self.dernier_lien = ""

    def content(self) -> ComposeResult:
        with VerticalScroll(id="phone"):
            yield Static(
                "Choisissez votre application : PlugArr prepare le fichier a restaurer, ou "
                "les champs a recopier. [dim]Un test depuis le serveur ne remplace pas le "
                "test du telephone.[/dim]",
                id="ph-intro",
            )
            with Horizontal(classes="ph-row"):
                yield Select(
                    [("nzb360", "nzb360"), ("qbRemote (Android)", "qbremote"), ("Arr Control", "arrcontrol"),
                     (t("Autre (champs a recopier)"), "other")],
                    value="nzb360", allow_blank=False, id="ph-client",
                )
                yield Select(
                    [(t("Reseau local"), "local"), (t("A distance"), "remote")],
                    value="local", allow_blank=False, id="ph-network",
                )
            yield Select([], id="ph-service", classes="hidden", prompt="Application")
            yield Static(id="ph-fields", classes="hidden")
            yield Checkbox("Afficher les secrets", id="ph-show", classes="hidden")
            yield Input(placeholder="Nom du Wi-Fi de la maison (facultatif)", id="ph-ssid", classes="hidden")
            yield Input(placeholder="Sauvegarde a completer (facultatif, .zip)", id="ph-base", classes="hidden")
            yield Select(
                [(t("Dans un profil separe « PlugArr » (rien n'est remplace)"), "profile"),
                 (t("Dans mon profil Default, service par service"), "default")],
                value="profile", allow_blank=False, id="ph-target", classes="hidden",
            )
            yield SelectionList(id="ph-replace", classes="hidden")
            yield Input(placeholder="Mot de passe du fichier (demande par qbRemote)", password=True, id="ph-password", classes="hidden")
            yield Checkbox("J'ai sauvegarde mes reglages : la restauration les remplace.", id="ph-confirm", classes="hidden")
            yield Static(id="ph-notice")
            yield Static(id="ph-qr")
        yield Horizontal(
            Button("Enregistrer le fichier", variant="primary", id="ph-save", disabled=True),
            Button("Envoyer au telephone (QR code)", id="ph-send", disabled=True),
            Button("Retour", id="back"),
            classes="actions",
        )

    def on_mount(self) -> None:
        self._rafraichir()

    # -- donnees ---------------------------------------------------------------

    def _donnees(self) -> dict:
        return telephone.donnees_rapport(
            self.app.stack_config, resultat_distant=getattr(self.app, "remote_result", None)
        )

    def _valeur(self, selecteur: str) -> str:
        valeur = self.query_one(selecteur, Select).value
        return "" if valeur is Select.BLANK else str(valeur)

    def _ssid(self) -> str:
        return self.query_one("#ph-ssid", Input).value.strip() if self._valeur("#ph-network") == "remote" else ""

    # -- affichage -------------------------------------------------------------

    def _visible(self, selecteur: str, oui: bool) -> None:
        self.query_one(selecteur).set_class(not oui, "hidden")

    @on(Select.Changed)
    @on(Input.Changed)
    @on(Checkbox.Changed)
    @on(SelectionList.SelectedChanged)
    def _change(self, event) -> None:
        cible = getattr(getattr(event, "control", None), "id", None)
        if cible in ("ph-client", "ph-network", "ph-target"):
            valeur = self._valeur(f"#{cible}")
            if self._choix.get(cible, valeur) != valeur:
                self.query_one("#ph-confirm", Checkbox).value = False
            self._choix[cible] = valeur
        if cible == "ph-base":
            self._charger_base()
        self._rafraichir()

    def _rafraichir(self) -> None:
        if self.app.stack_config is None:
            return
        client, reseau = self._valeur("#ph-client"), self._valeur("#ph-network")
        data = self._donnees()
        distant_possible = any(s.get("remote_url") for s in data["services"])
        if reseau == "remote" and not distant_possible:
            self.query_one("#ph-network", Select).value = "local"
            reseau = "local"
        fichier = client in ("nzb360", "qbremote", "arrcontrol")
        self._visible("#ph-service", client == "other")
        self._visible("#ph-fields", client == "other")
        self._visible("#ph-show", client == "other")
        self._visible("#ph-ssid", client in ("nzb360", "qbremote") and reseau == "remote")
        self._visible("#ph-base", client in ("nzb360", "qbremote"))
        self._visible("#ph-target", client == "nzb360" and self._base_nzb is not None)
        self._visible(
            "#ph-replace",
            client == "nzb360" and self._base_nzb is not None and self._valeur("#ph-target") == "default"
            and bool(self._base_nzb["configured"]),
        )
        self._visible("#ph-password", client == "qbremote")
        self._visible("#ph-confirm", client in ("nzb360", "qbremote"))
        self.query_one("#ph-confirm", Checkbox).label = (
            t("J'ai sauvegarde mes reglages nzb360. La restauration de ce ZIP remplace tous mes reglages nzb360.")
            if client == "nzb360"
            else t("J'ai sauvegarde mes reglages qbRemote. La restauration remplace tous mes serveurs qbRemote.")
        )
        if client == "other":
            self._fiches(data, reseau)
            self._boutons(False)
            return
        try:
            message, possible = self._apercu(data, client, reseau)
        except ValueError:
            message, possible = t("Export impossible : un champ depasse la taille prise en charge."), False
        self.query_one("#ph-notice", Static).update(message)
        self._boutons(fichier and possible)

    def _boutons(self, actifs: bool) -> None:
        self.query_one("#ph-save", Button).disabled = not actifs
        self.query_one("#ph-send", Button).disabled = not actifs

    def _apercu(self, data: dict, client: str, reseau: str) -> tuple[str, bool]:
        confirme = self.query_one("#ph-confirm", Checkbox).value
        if client == "arrcontrol":
            payload, omis = telephone.arr_control(data, reseau)
            message = t("{nombre} application(s) incluse(s) pour Arr Control.", nombre=len(payload["services"]))
            if omis:
                message += " " + t("Non incluses (adresse ou identifiants indisponibles) : {noms}.", noms=", ".join(omis))
            message += " " + t("Un profil utilise un seul reseau. Ce fichier contient vos secrets : gardez-le prive.")
            return message, bool(payload["services"])
        if client == "nzb360":
            resultat = self._resultat_nzb(data, reseau)
            message = t("nzb360 24.4.1 : {nombre} application(s).", nombre=resultat["count"])
            if resultat.get("switching"):
                message += " " + t(
                    "Sur le Wi-Fi « {ssid} », {nombre} application(s) passent sur l'adresse locale.",
                    ssid=self._ssid(), nombre=resultat["switching"],
                )
            if resultat["omitted"]:
                message += " " + t("Exclues (adresse ou identifiants indisponibles) : {noms}.", noms=", ".join(resultat["omitted"]))
            if resultat.get("merge"):
                message += " " + resultat["merge"]
            if self._base_erreur:
                message += " " + self._base_erreur
            return message, bool(resultat["count"]) and confirme
        serveur = telephone.qbremote_serveur(data, reseau, self._ssid())
        mot = self.query_one("#ph-password", Input).value
        if not serveur:
            return t("Export impossible : adresse ou identifiants de qBittorrent indisponibles pour ce reseau."), False
        message = t(
            "qbRemote 1.8.0 : serveur « {nom} » vers {schema}://{hote}:{port}.",
            nom=serveur["name"], schema=serveur["scheme"], hote=serveur["host"], port=serveur["port"],
        )
        if serveur["localHost"]:
            message += " " + t(
                "Sur le Wi-Fi « {ssid} », qbRemote utilisera {hote}.", ssid=serveur["localSsid"], hote=serveur["localHost"]
            )
        if len(mot) < telephone.QB_PASSWORD_MIN:
            message += " " + t(
                "Choisissez un mot de passe d'au moins {nombre} caracteres : qbRemote le demandera.",
                nombre=telephone.QB_PASSWORD_MIN,
            )
        if self._chemin_base:
            message += " " + t("Fusion : saisissez le mot de passe de votre sauvegarde ; le fichier produit utilise le meme.")
        return message, confirme and len(mot) >= telephone.QB_PASSWORD_MIN

    def _fiches(self, data: dict, reseau: str) -> None:
        """Champs a recopier, comme la fiche du web (mobile())."""
        choix = self.query_one("#ph-service", Select)
        services = [s for s in data["services"] if s["id"] in telephone.MOBILE_IDS]
        options = [(s["name"], s["id"]) for s in services]
        if self._fiches_ids != [o[1] for o in options]:
            self._fiches_ids = [o[1] for o in options]
            choix.set_options(options)
            if options:
                choix.value = options[0][1]
        sid = self._valeur("#ph-service")
        service = next((s for s in services if s["id"] == sid), None)
        zone = self.query_one("#ph-fields", Static)
        if service is None:
            zone.update(t("Aucune application compatible selectionnee."))
            self.query_one("#ph-notice", Static).update("")
            return
        brut = service.get("remote_url") if reseau == "remote" else (service.get("local_url") or service.get("url"))
        lu = telephone._url(brut)
        if lu is None:
            zone.update(t("Adresse indisponible pour ce reseau."))
            return
        morceaux, port = lu
        https = morceaux.scheme.lower() == "https"
        montrer = self.query_one("#ph-show", Checkbox).value
        cache = lambda valeur: escape(valeur) if montrer else "••••••••"
        lignes = [
            f"[b]{t('Nom')}[/b]  {escape(service['name'])}",
            f"[b]{t('URL complete')}[/b]  {escape(brut)}",
            f"[b]{t('Hote')}[/b]  {escape(morceaux.hostname)}",
            f"[b]Port[/b]  {port or (443 if https else 80)}",
            f"[b]HTTPS / SSL[/b]  {t('Active') if https else t('Desactive')}",
        ]
        if morceaux.path and morceaux.path != "/":
            lignes.append(f"[b]{t('Chemin de base')}[/b]  {escape(morceaux.path)}")
        if service["id"] in ("qbittorrent", "transmission"):
            lignes += [f"[b]{t('Utilisateur')}[/b]  {escape(service['username'])}",
                       f"[b]{t('Mot de passe')}[/b]  {cache(service['password'])}"]
        else:
            lignes.append(f"[b]{t('Cle API')}[/b]  {cache(service['api_key'])}")
        zone.update("\n".join(lignes))
        self.query_one("#ph-notice", Static).update(
            t("Connectez le telephone au meme reseau que le serveur.") if reseau == "local"
            else t("Testez depuis le telephone en 4G/5G.")
        )

    # -- sauvegarde de depart ------------------------------------------------

    def _charger_base(self) -> None:
        chemin = self.query_one("#ph-base", Input).value.strip().strip('"')
        self._base_nzb, self._base_erreur, self._chemin_base = None, "", ""
        if not chemin or not Path(chemin).is_file():
            return
        self._chemin_base = chemin
        if self._valeur("#ph-client") != "nzb360":
            return
        try:
            if Path(chemin).stat().st_size > TAILLE_MAX_SAUVEGARDE:
                raise ValueError("Too large")
            self._base_nzb = telephone.nzb360_examiner(Path(chemin).read_bytes())
        except (OSError, ValueError):
            self._base_nzb = None
            self._base_erreur = t("Ce fichier n'est pas une sauvegarde nzb360 lisible : export sans fusion.")
            return
        liste = self.query_one("#ph-replace", SelectionList)
        liste.clear_options()
        for service in self._base_nzb["configured"]:
            liste.add_option(Selection(
                t("Remplacer {nom} ({adresse}) par celui de PlugArr", nom=self._nom_slot(service["id"]), adresse=service["url"]),
                service["id"],
            ))

    def _nom_slot(self, slot: str) -> str:
        if slot != "torrent":
            return telephone.NZB360_NAMES.get(slot, slot)
        client = (self._base_nzb or {}).get("preferences", {}).get("torrent_client_preference")
        return telephone.NZB360_NAMES.get(client, t("Client torrent"))

    def _resultat_nzb(self, data: dict, reseau: str) -> dict:
        """nzbResult : export neuf, ou fusion dans la sauvegarde chargee."""
        ssid = self._ssid()
        if self._base_nzb is None:
            return telephone.nzb360_export(data, reseau, ssid)
        if self._valeur("#ph-target") == "profile":
            resultat = telephone.nzb360_fusion_profil(self._base_nzb, data, reseau, ssid)
            profil = resultat["profile"]
            resultat["count"] = len(resultat["added"])
            resultat["merge"] = t(
                "Profil « {nom} » {etat} (n° {id}), a cote de vos profils. Rien n'est remplace. "
                "Dans nzb360, choisissez « {nom} » en bas du menu.",
                nom=profil["name"], etat=t("mis a jour") if profil["updated"] else t("ajoute"), id=profil["id"],
            )
            return resultat
        remplacer = list(self.query_one("#ph-replace", SelectionList).selected)
        resultat = telephone.nzb360_fusion(self._base_nzb, data, reseau, ssid, remplacer)
        resultat["count"] = len(resultat["added"]) + len(resultat["replaced"])
        noms = lambda ids: ", ".join(telephone.NZB360_NAMES.get(i, i) for i in ids) or t("aucune")
        resultat["merge"] = t(
            "Fusion avec votre sauvegarde : ajoutees : {ajoutees} ; remplacees : {remplacees} ; gardees : {gardees}. "
            "Tout le reste de votre sauvegarde est conserve.",
            ajoutees=noms(resultat["added"]), remplacees=noms(resultat["replaced"]),
            gardees=", ".join(self._nom_slot(s) for s in resultat["kept"]) or t("aucune"),
        )
        return resultat

    # -- fabrication, enregistrement, envoi --------------------------------------

    def _fabriquer(self) -> tuple[bytes, str]:
        client, reseau = self._valeur("#ph-client"), self._valeur("#ph-network")
        data = self._donnees()
        if client == "arrcontrol":
            payload, _omis = telephone.arr_control(data, reseau)
            return telephone.arr_control_json(payload), f"plugarr-arr-control-{reseau}.json"
        if client == "nzb360":
            resultat = self._resultat_nzb(data, reseau)
            nom = (f"nzb360_backup_plugarr-fusion-{reseau}.zip" if self._base_nzb is not None
                   else f"plugarr-nzb360-24.4.1-{reseau}.zip")
            return resultat["bytes"], nom
        mot = self.query_one("#ph-password", Input).value
        if self._chemin_base:
            fusion = telephone.qbremote_fusion(Path(self._chemin_base).read_bytes(), mot, data, reseau, self._ssid())
            if fusion is None:
                raise ValueError(t("Adresse ou identifiants de qBittorrent indisponibles."))
            return fusion["bytes"], f"qbRemote_plugarr-fusion-{reseau}.backup.zip"
        octets = telephone.qbremote_export(data, reseau, self._ssid(), mot)
        if octets is None:
            raise ValueError(t("Adresse ou identifiants de qBittorrent indisponibles."))
        return octets, f"qbRemote_plugarr-{reseau}.backup.zip"

    def _erreur(self, exc: Exception) -> str:
        if isinstance(exc, telephone.ErreurMotDePasse):
            return t("Mot de passe incorrect pour cette sauvegarde qbRemote.")
        if self._chemin_base:
            return t("Ce fichier n'est pas une sauvegarde lisible pour cette application.")
        return t("Fichier impossible a produire : {erreur}", erreur=exc)

    @on(Button.Pressed, "#ph-save")
    def enregistrer(self) -> None:
        try:
            octets, nom = self._fabriquer()
        except (OSError, ValueError) as exc:
            self.query_one("#ph-qr", Static).update(f"[red]{escape(self._erreur(exc))}[/red]")
            return
        chemin = Path(self.app.project_dir) / nom
        chemin.write_bytes(octets)
        chemin.chmod(0o600)
        self.query_one("#ph-qr", Static).update(
            t("[green]Fichier enregistre : {chemin}[/green]\n[dim]Il contient vos secrets : gardez-le prive.[/dim]", chemin=escape(str(chemin)))
        )

    @on(Button.Pressed, "#ph-send")
    def envoyer(self) -> None:
        from .. import dashboard
        from ..phone_share import PartageTelephone

        try:
            octets, nom = self._fabriquer()
        except (OSError, ValueError) as exc:
            self.query_one("#ph-qr", Static).update(f"[red]{escape(self._erreur(exc))}[/red]")
            return
        hote = dashboard.resolve_host(self.app.stack_config)[0]
        partage = getattr(self.app, "phone_share", None)
        if partage is None or partage.hote != hote:
            if partage is not None:
                partage.arreter()
            partage = PartageTelephone(hote)
            self.app.phone_share = partage
        lien = partage.publier(octets, nom)
        self.dernier_lien = lien["url"]
        minutes = max(1, lien["expires_in"] // 60)
        texte = t(
            "Scannez avec l'appareil photo du telephone, connecte au meme Wi-Fi que ce serveur. "
            "Le lien sert une seule fois, pendant {minutes} min. Le fichier arrive dans "
            "Telechargements : restaurez-le ensuite dans l'application.",
            minutes=minutes,
        )
        if lien.get("firewall_prompt"):
            texte += " " + t("Windows peut afficher une fenetre du pare-feu pour PlugArr : cliquez « Autoriser ».")
        from rich.console import Group
        from rich.text import Text

        self.query_one("#ph-qr", Static).update(
            Group(telephone.qr_terminal(lien["url"]), Text(texte), Text(lien["url"], style="dim"))
        )

    @on(Button.Pressed, "#back")
    def back(self) -> None:
        self.app.pop_screen()
