"""Catalogue anglais, indexe sur la phrase francaise.

Ecrit a la main, verifie mecaniquement : `scripts/audit_traductions.py` echoue
si une phrase affichable n'a pas d'entree ici, **et** si une entree ne
correspond a aucune phrase du code. Les deux sens comptent — une entree morte
signale une phrase supprimee du code et oubliee ici, c'est-a-dire un catalogue
qui commence a mentir.

Le fichier est volontairement plat et sans logique : c'est une table de
correspondance, elle doit se relire en diagonale.

Les balises de mise en forme (`[b]`, `[dim]`, `[/green]`) sont celles de Rich.
Elles doivent etre reportees telles quelles : une balise ouverte et jamais
fermee s'affiche en clair au milieu du texte.
"""

from __future__ import annotations

EN: dict[str, str] = {
    # -- navigation et socle --------------------------------------------------
    "Retour": "Back",
    "Quitter": "Quit",
    "Continuer": "Continue",
    "Commencer": "Start",
    "Passer": "Skip",
    "Terminer": "Finish",
    "Fermer": "Close",
    "Restaurer": "Restore",
    "ECHEC": "FAILED",
    # -- accueil --------------------------------------------------------------
    "Deploie ET cable une stack media complete": (
        "Deploys AND wires a complete media stack"
    ),
    "Cet assistant va deployer les services que vous choisissez, puis "
    "[b]les cabler entre eux[/b] : cles API echangees, indexeurs synchronises, "
    "dossiers racine crees, bibliotheques scannees.\n\n"
    "Rien n'est ecrit avant l'ecran de recapitulatif.": (
        "This wizard will deploy the services you choose, then "
        "[b]wire them together[/b]: API keys exchanged, indexers synced, root "
        "folders created, libraries scanned.\n\n"
        "Nothing is written before the summary screen."
    ),
    "Langue de PlugArr": "PlugArr language",
    "Restaurer une sauvegarde": "Restore a backup",
    "Diagnostic impossible": "Diagnostic failed",
    # -- restauration ---------------------------------------------------------
    "Restaurer une installation sauvegardee": "Restore a saved installation",
    "Reposez une archive produite par [b]plugarr backup[/b] ou par le bouton "
    "[b]Sauvegarder la configuration[/b] de la page d'administration.\n\n"
    "Elle contient vos services, vos identifiants et tout ce que vous aviez "
    "saisi : indexeurs, profils, bibliotheques. [b]Vos medias ne sont pas "
    "dedans[/b] et ne seront pas touches.": (
        "Restore an archive produced by [b]plugarr backup[/b] or by the "
        "[b]Back up the configuration[/b] button on the admin page.\n\n"
        "It holds your services, your credentials and everything you entered: "
        "indexers, profiles, libraries. [b]Your media is not in it[/b] and will "
        "not be touched."
    ),
    "Fichier de sauvegarde (.zip)": "Backup file (.zip)",
    "Ou reposer la configuration [dim](vide = l'emplacement d'origine)[/dim]": (
        "Where to restore the configuration [dim](empty = its original "
        "location)[/dim]"
    ),
    "Examiner l'archive": "Inspect the archive",
    # -- selection des services ----------------------------------------------
    "Etape 1/3 - Quels services installer ?": "Step 1/3 - Which services to install?",
    "Mediatheque": "Media library",
    "Telechargement": "Downloads",
    "Serveur media": "Media server",
    "Interfaces": "Web UIs",
    "[yellow]Selectionnez au moins un service.[/yellow]": (
        "[yellow]Select at least one service.[/yellow]"
    ),
    # -- chemins et plateforme ------------------------------------------------
    "Etape 2/3 - Chemins et plateforme": "Step 2/3 - Paths and platform",
    "Profil de plateforme": "Platform profile",
    "Racine des configurations": "Configuration root",
    "Racine des donnees [dim](montee sur /data dans TOUS les conteneurs)[/dim]": (
        "Data root [dim](mounted on /data in EVERY container)[/dim]"
    ),
    "Identifiant [dim](le meme pour tous les services installes)[/dim]": (
        "Username [dim](the same one for every installed service)[/dim]"
    ),
    "Langue des services installes [dim](Sonarr, Jellyfin... ; celle de PlugArr "
    "se choisit sur l'ecran d'accueil)[/dim]": (
        "Language of the installed services [dim](Sonarr, Jellyfin...; PlugArr's "
        "own language is chosen on the welcome screen)[/dim]"
    ),
    "Nom de la pile Docker [dim](a changer pour en installer une SECONDE a "
    "cote)[/dim]": (
        "Docker stack name [dim](change it to install a SECOND one "
        "alongside)[/dim]"
    ),
    "Fuseau horaire": "Time zone",
    "Adresse de cette machine [dim](a changer si vous naviguerez depuis un "
    "autre poste)[/dim]": (
        "This machine's address [dim](change it if you will browse from another "
        "computer)[/dim]"
    ),
    "Verifier les chemins": "Check the paths",
    "[red]La racine des donnees ne peut pas etre vide.[/red]": (
        "[red]The data root cannot be empty.[/red]"
    ),
    # -- profils de qualite ---------------------------------------------------
    "Etape optionnelle - profils de qualite": "Optional step - quality profiles",
    "Sans profil de qualite, un *arr accepte [b]n'importe quel[/b] encodage : "
    "le premier resultat venu, pas le meilleur.\n"
    "[dim]Les profils viennent des TRaSH Guides. plugarr ne fait que poser "
    "l'adresse et la cle API dans le template que vous choisissez ici.[/dim]": (
        "Without a quality profile, an *arr accepts [b]any[/b] encoding: the "
        "first result that comes along, not the best one.\n"
        "[dim]The profiles come from the TRaSH Guides. plugarr only writes the "
        "URL and the API key into the template you pick here.[/dim]"
    ),
    "[dim]Chargement de la liste officielle…[/dim]": (
        "[dim]Loading the official list…[/dim]"
    ),
    # -- vpn -------------------------------------------------------------------
    "Etape optionnelle - VPN du client de telechargement": (
        "Optional step - download client VPN"
    ),
    "Sans VPN, le trafic BitTorrent sort sur [b]l'adresse IP publique de cette "
    "machine[/b], visible par tous les autres pairs.\n"
    "[dim]Avec Gluetun, le client de telechargement perd son propre reseau : il "
    "ne demarre pas tant que le tunnel n'est pas etabli, donc aucun paquet ne "
    "peut sortir en clair.[/dim]": (
        "Without a VPN, BitTorrent traffic leaves through [b]this machine's "
        "public IP address[/b], visible to every other peer.\n"
        "[dim]With Gluetun, the download client loses its own network: it does "
        "not start until the tunnel is up, so no packet can leave in the "
        "clear.[/dim]"
    ),
    "Sans VPN": "No VPN",
    "Faire passer le client par un VPN": "Route the client through a VPN",
    "Fournisseur": "Provider",
    "Protocole": "Protocol",
    "Cle privee WireGuard": "WireGuard private key",
    "Identifiant OpenVPN": "OpenVPN username",
    "Mot de passe OpenVPN": "OpenVPN password",
    "[dim]Ce fournisseur ne propose pas de filtre geographique : les serveurs "
    "viennent de votre propre configuration.[/dim]": (
        "[dim]This provider offers no geographic filter: the servers come from "
        "your own configuration.[/dim]"
    ),
    "[green]Configuration complete.[/green]": "[green]Configuration complete.[/green]",
    # -- recapitulatif ---------------------------------------------------------
    "Etape 3/3 - Recapitulatif (rien n'est encore ecrit)": (
        "Step 3/3 - Summary (nothing is written yet)"
    ),
    "Service": "Service",
    "Image": "Image",
    "URL": "URL",
    "Conserver ces configurations": "Keep these configurations",
    "Supprimer et repartir de zero": "Delete them and start over",
    "Installer et cabler": "Install and wire",
    # -- installation ----------------------------------------------------------
    "Installation et cablage": "Installing and wiring",
    "Preparation...": "Preparing...",
    # -- rapport ----------------------------------------------------------------
    "Acces": "Access",
    "Identifiant": "Username",
    "Mot de passe": "Password",
    "Cle API": "API key",
    "Ouvrir la page d'acces": "Open the access page",
    # -- indexeurs ---------------------------------------------------------------
    "Etape optionnelle - vos indexeurs": "Optional step - your indexers",
    "plugarr ne fournit et ne recommande [b]aucun[/b] indexeur. La liste "
    "ci-dessous est celle que votre propre Prowlarr embarque.\n"
    "[dim]Ajouter un indexeur le contacte pour valider vos identifiants : c'est "
    "Prowlarr qui l'impose, il n'existe pas d'enregistrement hors ligne.[/dim]": (
        "plugarr provides and recommends [b]no[/b] indexer. The list below is "
        "the one your own Prowlarr ships.\n"
        "[dim]Adding an indexer contacts it to validate your credentials: that "
        "is Prowlarr's rule, there is no offline registration.[/dim]"
    ),
    "Choisissez un indexeur a gauche.": "Pick an indexer on the left.",
    "[dim]Aucun identifiant requis.[/dim]": "[dim]No credentials required.[/dim]",
    "Ajouter cet indexeur": "Add this indexer",
    "Passer cette etape": "Skip this step",
    # -- notes du catalogue ------------------------------------------------------
    # Affichees sous chaque service a l'ecran de selection. Elles arrivent au
    # widget par une variable : c'est leur declaration dans `catalog.py` que
    # l'audit releve.
    "Pivot du cablage : alimente les autres en indexeurs.": (
        "The wiring hub: it feeds indexers to all the others."
    ),
    "Series TV.": "TV shows.",
    "Films.": "Movies.",
    "Client torrent par defaut.": "Default torrent client.",
    "Musique. Son API est en v1, pas en v3.": "Music. Its API is v1, not v3.",
    "Categories natives avec chemin dedie.": (
        "Native categories with a dedicated path."
    ),
    "Serveur media. Bibliotheques creees pour vous.": (
        "Media server. Libraries created for you."
    ),
    "Demandes de medias. Successeur de Jellyseerr et d'Overseerr.": (
        "Media requests. Successor to Jellyseerr and Overseerr."
    ),
    "Client Usenet. Complete les torrents, il ne les remplace pas.": (
        "Usenet client. It complements torrents, it does not replace them."
    ),
    "Musique, de la demande au rangement. REMPLACE Lidarr, ne le complete pas.": (
        "Music, from request to filing. REPLACES Lidarr, does not complement it."
    ),
    "Livres et livres audio. Remplit les bibliotheques books et audiobooks.": (
        "Books and audiobooks. Fills the books and audiobooks libraries."
    ),
    "Base de donnees de Silo. Installee avec lui, jamais seule.": (
        "Silo's database. Installed with it, never on its own."
    ),
    "Cache de Silo. Installe avec lui, jamais seul.": (
        "Silo's cache. Installed with it, never on its own."
    ),
    "Serveur media, API compatible Jellyfin. Meilisearch est optionnel et n'est "
    "pas installe.": (
        "Media server with a Jellyfin-compatible API. Meilisearch is optional and "
        "is not installed."
    ),
    "Ecoute les annonces IRC. Plus rapide que le sondage RSS.": (
        "Listens to IRC announces. Faster than RSS polling."
    ),
    "UI web pour qBittorrent. N'est pas un client.": (
        "Web UI for qBittorrent. Not a client."
    ),
    "Profils de qualite TRaSH. Aucune interface web.": (
        "TRaSH quality profiles. No web UI."
    ),
    "UI web pour qBittorrent ou Transmission. N'est pas un client.": (
        "Web UI for qBittorrent or Transmission. Not a client."
    ),
    # -- origine des PUID/PGID ---------------------------------------------------
    "utilisateur courant": "current user",
    "utilisateur courant (les UID DSM varient selon l'utilisateur cree)": (
        "current user (DSM UIDs vary with the user that was created)"
    ),
    "constante Unraid : nobody:users = 99:100": (
        "Unraid constant: nobody:users = 99:100"
    ),
    "sans effet sous Docker Desktop : Windows ne porte pas ces droits": (
        "no effect under Docker Desktop: Windows does not carry these permissions"
    ),
    # -- phrases a champs nommes ------------------------------------------------
    # Assemblees a l'affichage : leur valeur change a chaque appel, seul le
    # gabarit peut servir de cle. Les champs doivent etre reportes tels quels.
    '[b]{services} services[/b] - [b]{liens} liens[/b] seront cables': '[b]{services} services[/b] - [b]{liens} links[/b] will be wired',
    '\n[cyan]Ajoute automatiquement (prerequis) : {noms}[/cyan]': '\n[cyan]Added automatically (prerequisites): {noms}[/cyan]',
    "[dim]PUID/PGID = l'utilisateur Linux, a l'interieur des conteneurs, qui possedera vos fichiers.[/dim]": '[dim]PUID/PGID = the Linux user, inside the containers, that will own your files.[/dim]',
    ' [yellow]- non detectables ici, valeur de repli.[/yellow]\n': ' [yellow]- not detectable here, falling back.[/yellow]\n',
    '\n[dim]Sur un NAS, lancez `id` et corrigez ces valeurs.[/dim]': '\n[dim]On a NAS, run `id` and correct these values.[/dim]',
    '[dim]Dossier vise : {chemin}[/dim]': '[dim]Target folder: {chemin}[/dim]',
    '[red]Impossible de le creer : {erreur}[/red]': '[red]Cannot create it: {erreur}[/red]',
    'liste indisponible : {erreur}': 'list unavailable: {erreur}',
    '[dim]Les noms ne seront pas verifies ici. Les defauts restent valables.[/dim]': '[dim]Names will not be checked here. The defaults still apply.[/dim]',
    '[dim]{nombre} profils proposes par les TRaSH Guides. Cliquez pour derouler la liste.[/dim]': '[dim]{nombre} profiles offered by the TRaSH Guides. Click to open the list.[/dim]',
    '[red]Template inconnu — {noms}[/red]\n[dim]Recyclarr refuserait de generer la configuration.[/dim]': '[red]Unknown template — {noms}[/red]\n[dim]Recyclarr would refuse to generate the configuration.[/dim]',
    '[dim](facultatif)[/dim]': '[dim](optional)[/dim]',
    '[dim]{nombre} choix proposes par Gluetun {version}. Sans selection, le VPN choisit pour vous.[/dim]': '[dim]{nombre} choices offered by Gluetun {version}. With none selected, the VPN picks for you.[/dim]',
    '[yellow]Il manque {champs}.[/yellow]\n[dim]Sans cela Gluetun refuse de demarrer, et le client de telechargement reste injoignable.[/dim]': '[yellow]Missing: {champs}.[/yellow]\n[dim]Without them Gluetun refuses to start, and the download client stays unreachable.[/dim]',
    'tache de fond': 'background task',
    '[b]Configurations[/b]  {chemin}': '[b]Configuration[/b]   {chemin}',
    '[b]Donnees[/b]        {chemin}  -> /data dans tous les conteneurs': '[b]Data[/b]            {chemin}  -> /data in every container',
    '[b]Liens a cabler[/b] {nombre}': '[b]Links to wire[/b]  {nombre}',
    '[b]VPN[/b]            gluetun - {fournisseur} [dim]({protocole}) ; le client de telechargement ne demarrera pas sans le tunnel[/dim]': '[b]VPN[/b]             gluetun - {fournisseur} [dim]({protocole}); the download client will not start without the tunnel[/dim]',
    '[yellow]PUID/PGID non detectables ici : repli sur {uid}:{gid}.[/yellow]\n[dim]Des identifiants faux font ecrire toute la stack avec de mauvaises permissions. Sur un NAS, lancez `id`.[/dim]': '[yellow]PUID/PGID not detectable here: falling back to {uid}:{gid}.[/yellow]\n[dim]Wrong ids make the whole stack write with the wrong permissions. On a NAS, run `id`.[/dim]',
    "[yellow]Une configuration existe deja pour {services}.[/yellow]\n[dim]Leurs mots de passe n'y sont stockes que haches. PlugArr essaiera ceux de ses installations precedentes avant d'en annoncer un neuf ; si aucun ne convient, il faudra repartir de zero.[/dim]\n": '[yellow]A configuration already exists for {services}.[/yellow]\n[dim]Their passwords are stored hashed only. PlugArr will try those of its previous installations before announcing a new one; if none fits, you will have to start over.[/dim]\n',
    '[dim]Vos medias ne sont jamais touches.[/dim]': '[dim]Your media is never touched.[/dim]',
    '[yellow]Prise A CHAUD, conteneurs en marche : ses bases peuvent etre corrompues.[/yellow]': '[yellow]Taken HOT, with containers running: its databases may be corrupt.[/yellow]',
    '[green]Restauration terminee.[/green]\n\n{nombre} services reposes. Demarrez la pile, puis [b]plugarr wire[/b] pour verifier que tout repond.': '[green]Restore complete.[/green]\n\n{nombre} services restored. Start the stack, then run [b]plugarr wire[/b] to check that everything answers.',
    '[dim]Journal detaille : {chemin}[/dim]': '[dim]Detailed log: {chemin}[/dim]',
    '[dim]Detail complet dans {chemin}[/dim]': '[dim]Full detail in {chemin}[/dim]',
    '[green]Termine : {faits}/{total} liens etablis[/green]': '[green]Done: {faits}/{total} links established[/green]',
    '[yellow]Termine : {faits}/{total} liens etablis[/yellow]': '[yellow]Done: {faits}/{total} links established[/yellow]',
    '[red]Liens en echec :[/red]\n': '[red]Failed links:[/red]\n',
    '\n\n[dim]Diagnostic : plugarr doctor[/dim]': '\n\n[dim]Diagnostic: plugarr doctor[/dim]',
    "Prochaine etape : ouvrez chaque service depuis la page d'acces.": 'Next step: open each service from the access page.',
    '\n\n[dim]Ces identifiants sont aussi dans {chemin} (chmod 600).[/dim]': '\n\n[dim]These credentials are also in {chemin} (chmod 600).[/dim]',
    "Rouvrir la page d'acces": 'Reopen the access page',
    '[yellow]Page introuvable : {chemin}[/yellow]': '[yellow]Page not found: {chemin}[/yellow]',
    '[green]Page ouverte dans votre navigateur.[/green]\n': '[green]Page opened in your browser.[/green]\n',
    '[yellow]Aucun navigateur disponible ici.[/yellow]\n[dim]Ouvrez ce fichier depuis un autre appareil : {chemin}[/dim]': '[yellow]No browser available here.[/yellow]\n[dim]Open this file from another device: {chemin}[/dim]',
    '[red]Prowlarr injoignable : {erreur}[/red]': '[red]Prowlarr unreachable: {erreur}[/red]',
    ' - deja configures : {noms}': ' - already configured: {noms}',
    '[dim]{nombre} definitions fournies par votre Prowlarr{deja}[/dim]': '[dim]{nombre} definitions shipped by your Prowlarr{deja}[/dim]',
    '[dim]Validation de {nom} par Prowlarr...[/dim]': '[dim]Prowlarr is validating {nom}...[/dim]',
    # -- rendu console -----------------------------------------------------------
    # Ce que voit quelqu'un qui lance `plugarr install --yes` : preflight,
    # recapitulatif, etapes de cablage et rapport final.
    'Preflight': 'Preflight',
    'Controle': 'Check',
    'Detail': 'Detail',
    'ATTENTION': 'WARNING',
    "Recapitulatif - rien n'a encore ete ecrit": 'Summary - nothing written yet',
    'Chemins': 'Paths',
    'CONFIG_ROOT : {config}\nDATA_ROOT   : {data}  (monte sur /data dans TOUS les conteneurs)\nPUID:PGID   : {uid}:{gid}  ({origine})\nUMASK / TZ  : {umask}   {tz}\nPlateforme  : {plateforme}': 'CONFIG_ROOT : {config}\nDATA_ROOT   : {data}  (mounted on /data in EVERY container)\nPUID:PGID   : {uid}:{gid}  ({origine})\nUMASK / TZ  : {umask}   {tz}\nPlatform    : {plateforme}',
    'Avertissement VPN': 'VPN warning',
    "Aucun VPN n'est configure pour le client torrent.\nLe trafic BitTorrent sortira sur l'adresse IP publique de cette machine, visible par les autres pairs.\nPour ajouter un VPN, relancez avec --vpn.": "No VPN is configured for the torrent client.\nBitTorrent traffic will leave through this machine's public IP address, visible to other peers.\nTo add one, re-run with --vpn.",
    'attention': 'warning',
    'preparation': 'preparing',
    'termine': 'done',
    'Resultat': 'Result',
    '[dim]Ces identifiants sont aussi dans .env (chmod 600, deja dans .gitignore).[/dim]': '[dim]These credentials are also in .env (chmod 600, already in .gitignore).[/dim]',
    '{faits}/{total} liens etablis, {crees} crees a ce passage.': '{faits}/{total} links established, {crees} created on this pass.',
    '\nEchecs :': '\nFailures:',
    '\nDiagnostic : `plugarr doctor`': '\nDiagnostic: `plugarr doctor`',
    # -- conseil de fin d'installation -------------------------------------------
    # La derniere chose que lit quelqu'un qui vient d'installer, et la seule qui
    # lui dise quoi faire ensuite.
    'Prochaine etape : ajoutez vos indexeurs dans Prowlarr.': 'Next step: add your indexers in Prowlarr.',
    'Ils descendront automatiquement vers {noms}.': 'They will flow down to {noms} automatically.',
    'plugarr ne fournit aucun indexeur : ce choix vous appartient.': 'plugarr provides no indexer: that choice is yours.',
    'Prochaine etape : ajoutez vos indexeurs dans {noms}.': 'Next step: add your indexers in {noms}.',
    "Prowlarr les aurait distribues a votre place : il n'est pas installe.": 'Prowlarr would have distributed them for you: it is not installed.',
    'Prochaine etape : deposez vos medias sous {racine}.': 'Next step: drop your media under {racine}.',
    '{noms} les trouvera a la prochaine analyse.': '{noms} will find it on the next scan.',
    # -- page d'acces et console d'administration ---------------------------------
    # L'artefact que l'utilisateur GARDE : il la rouvre pour retrouver un port,
    # un mot de passe, ou pour arreter un service.
    'Administration': 'Administration',
    'Votre stack media': 'Your media stack',
    '{nombre} services installes et cables le {date}.': '{nombre} services installed and wired on {date}.',
    'Services': 'Services',
    'Dossiers': 'Folders',
    'Ajouter un service': 'Add a service',
    "{nombre} lien(s) n'ont pas pu etre etablis.": '{nombre} link(s) could not be established.',
    'Lancez <code>plugarr doctor</code> pour un diagnostic.': 'Run <code>plugarr doctor</code> for a diagnostic.',
    'Aucun VPN.': 'No VPN.',
    "Le trafic BitTorrent sort sur l'adresse IP publique de cette machine.": "BitTorrent traffic leaves through this machine's public IP address.",
    'Cette valeur decide de qui possede vos medias.': 'This value decides who owns your media.',
    "Cette page est un <b>fichier fige</b> : elle ne montre ni l'etat des services, ni les mises a jour disponibles, et ses boutons n'existent pas ici.<br>Pour tout cela, ouvrez <code>{lanceur}</code>, depose a cote de cette page.": 'This page is a <b>frozen file</b>: it shows neither service status nor available updates, and its buttons do not exist here.<br>For all that, open <code>{lanceur}</code>, written next to this page.',
    "Les liens utilisent {adresse}, l'adresse de cette machine sur le reseau local, et non localhost : la page reste donc valable depuis un autre appareil.": "The links use {adresse}, this machine's address on the local network, rather than localhost: the page therefore stays valid from another device.",
    "Les liens pointent vers localhost. Depuis un autre appareil, remplacez-le par l'adresse de cette machine sur le reseau.": "The links point at localhost. From another device, replace it with this machine's address on the network.",
    'tache de fond, sans interface': 'background task, no web UI',
    'Cliquer pour afficher {quoi}': 'Click to reveal {quoi}',
    'Copier': 'Copy',
    'copier': 'copy',
    'copie': 'copied',
    'pas encore installe': 'not installed yet',
    'installer et cabler': 'install and wire',
    '— tirera aussi {noms}': '— will also pull in {noms}',
    "Le service est installe puis <b>cable dans les deux sens</b> : il apprend a parler aux autres, et les autres apprennent a lui parler. Rien n'est arrete, et aucun mot de passe existant n'est touche.": 'The service is installed then <b>wired both ways</b>: it learns to talk to the others, and the others learn to talk to it. Nothing is stopped, and no existing password is touched.',
    'Contenu': 'Content',
    'Sur cette machine': 'On this machine',
    'Vu par les conteneurs': 'As seen by the containers',
    'Films': 'Movies',
    'Series': 'Shows',
    'Musique': 'Music',
    'Telechargements': 'Downloads',
    'Configurations': 'Configuration',
    'ouvrir': 'open',
    "Les liens « ouvrir » ne fonctionnent que si ce navigateur tourne sur la machine d'installation. Depuis un autre appareil, utilisez le chemin copiable, ou passez par un partage reseau.": 'The “open” links only work if this browser runs on the installation machine. From another device, use the copyable path, or go through a network share.',
    'Cette page contient vos mots de passe et vos cles API. Elle est en lecture seule pour vous (<code>chmod 600</code>) et exclue du depot git. Ne la partagez pas.': 'This page holds your passwords and API keys. It is readable by you only (<code>chmod 600</code>) and excluded from the git repository. Do not share it.',
    'Genere par plugarr {version} — donnees dans <code>{racine}</code>.': 'Generated by plugarr {version} — data in <code>{racine}</code>.',
    'diagnostic': 'diagnostic',
    'chercher les mises a jour': 'check for updates',
    'sauvegarder la configuration': 'back up the configuration',
    # -- chemins et permissions ----------------------------------------------------
    # Origine des PUID/PGID et verdict du controle de hardlink, affiches par
    # l'assistant, le preflight et la page d'acces.
    'detecte ({origine})': 'detected ({origine})',
    'valeur par defaut : detection impossible sur cette plateforme': 'default value: detection impossible on this platform',
    'lance en root : conteneurs et medias appartiendront a root': 'running as root: containers and media will belong to root',
    'hardlink OK entre torrents/ et media/': 'hardlink OK between torrents/ and media/',
    "hardlink impossible ({erreur}). Les imports recopieront les fichiers au lieu de les lier. Verifiez que {source} et {cible} sont sur le MEME systeme de fichiers, et que DATA_ROOT est monte d'un seul bloc.": 'hardlink impossible ({erreur}). Imports will copy files instead of linking them. Check that {source} and {cible} are on the SAME filesystem, and that DATA_ROOT is mounted as a single block.',
    # -- format de date --------------------------------------------------------------
    # Ce n'est pas une phrase mais un gabarit `strftime` : « 05/09 » se lit
    # « 9 mai » pour un anglophone, et le mot de liaison change aussi.
    '%d/%m/%Y a %H:%M': '%Y-%m-%d at %H:%M',
    # -- aide de la ligne de commande --------------------------------------------
    # Lue par Typer a l'IMPORT : la langue est donc resolue avant, en regardant
    # `sys.argv` puis le systeme. Voir `_langue_a_l_import` dans cli.py.
    'Deploie ET cable automatiquement une stack media *arr.': 'Deploys AND automatically wires an *arr media stack.',
    "Lance l'assistant interactif plein ecran.": 'Launches the full-screen interactive wizard.',
    'Deploie et cable la stack de bout en bout, sans interaction.': 'Deploys and wires the stack end to end, without interaction.',
    "Liste les services deja installes sur cette machine. N'ecrit rien.": 'Lists the services already installed on this machine. Writes nothing.',
    'Cable une stack DEJA installee, sans la recreer.': 'Wires an ALREADY installed stack, without recreating it.',
    'Regenere docker-compose.yml et .env depuis stack.yml, sans rien demarrer.': 'Regenerates docker-compose.yml and .env from stack.yml, starting nothing.',
    'Rejoue uniquement le cablage sur une stack deja demarree. Idempotent.': 'Replays only the wiring on an already running stack. Idempotent.',
    "Page d'administration : etat des services, demarrer / arreter / redemarrer.": 'Admin page: service status, start / stop / restart.',
    "Pose le mot de passe de la page d'administration.": 'Sets the admin page password.',
    "Lance la console d'administration a chaque ouverture de session.": 'Starts the admin console with every login session.',
    'Archive la configuration complete : projet, CONFIG_ROOT et volumes.': 'Archives the whole configuration: project, CONFIG_ROOT and volumes.',
    "Repose une sauvegarde. N'ecrit RIEN dans DATA_ROOT.": 'Restores a backup. Writes NOTHING into DATA_ROOT.',
    'Diagnostique une installation existante.': 'Diagnoses an existing installation.',
    'Arrete la stack. Ne touche JAMAIS a DATA_ROOT.': 'Stops the stack. NEVER touches DATA_ROOT.',
    "Langues d'interface acceptees.": 'Accepted interface languages.',
    'Liste les fournisseurs VPN acceptes par Gluetun.': 'Lists the VPN providers Gluetun accepts.',
    'Liste le catalogue.': 'Lists the catalogue.',
    'Liste les profils de qualite TRaSH proposables a Recyclarr.': 'Lists the TRaSH quality profiles that can be given to Recyclarr.',
    'Affiche la version et quitte.': 'Shows the version and exits.',
    'Langue de PlugArr : fr, en. Par defaut, celle du systeme.': 'PlugArr language: fr, en. Defaults to the system one.',
    'Ne pas demander confirmation.': 'Do not ask for confirmation.',
    'Montrer le plan, ne rien faire.': 'Show the plan, do nothing.',
    "N'ecrit rien, montre tout.": 'Writes nothing, shows everything.',
    'Liste separee par des virgules. Connus: ': 'Comma-separated list. Known: ',
    'Ou ecrire les artefacts.': 'Where to write the artefacts.',
    'Ou ecrire stack.yml.': 'Where to write stack.yml.',
    'Ou reposer le projet.': 'Where to restore the project.',
    'Repertoire du stack.yml.': 'Directory holding stack.yml.',
    'Racine des configurations.': 'Configuration root.',
    'Racine des configurations existantes.': 'Root of the existing configurations.',
    'Racine des configurations, pour lire le manifeste deja clone.': 'Configuration root, to read the already cloned manifest.',
    'Racine des donnees (monte sur /data).': 'Data root (mounted on /data).',
    'Racine des medias de la stack existante.': 'Media root of the existing stack.',
    'Profil de plateforme.': 'Platform profile.',
    'Identifiant commun a tous les services installes.': 'Username shared by every installed service.',
    'Hote pour les URL du rapport final.': "Host to use in the final report's URLs.",
    'Adresse de cette machine, joignable DEPUIS les conteneurs.': "This machine's address, reachable FROM the containers.",
    'Langue des interfaces (code ISO : fr, en, es...). Voir `plugarr langues`.': 'Language of the service interfaces (ISO code: fr, en, es...). See `plugarr langues`.',
    'Faire passer le client torrent par un VPN.': 'Route the torrent client through a VPN.',
    'Fournisseur VPN. Voir `plugarr vpn-providers`.': 'VPN provider. See `plugarr vpn-providers`.',
    'wireguard ou openvpn.': 'wireguard or openvpn.',
    'Cle privee WireGuard.': 'WireGuard private key.',
    'Identifiant OpenVPN.': 'OpenVPN username.',
    'Mot de passe OpenVPN.': 'OpenVPN password.',
    'Pays souhaites, separes par des virgules.': 'Wanted countries, comma-separated.',
    'Template TRaSH pour Sonarr. Voir `plugarr templates`. Vide = defaut.': 'TRaSH template for Sonarr. See `plugarr templates`. Empty = default.',
    'Template TRaSH pour Radarr. Voir `plugarr templates`. Vide = defaut.': 'TRaSH template for Radarr. See `plugarr templates`. Empty = default.',
    'Lever une ambiguite : service=conteneur. Repetable.': 'Resolve an ambiguity: service=container. Repeatable.',
    'Identifiant du client de telechargement existant.': 'Username of the existing download client.',
    'Mot de passe du client existant. Illisible depuis sa configuration.': 'Password of the existing client. Unreadable from its configuration.',
    "Adresse d'ecoute.": 'Listen address.',
    "Adresse d'ecoute de la console.": 'Console listen address.',
    "Port d'ecoute.": 'Listen port.',
    "Port d'ecoute de la console.": 'Console listen port.',
    'Ouvrir le navigateur.': 'Open the browser.',
    "Ouvrir la page d'acces a la fin.": 'Open the access page at the end.',
    "Ouvrir la page d'acces dans le navigateur.": 'Open the access page in the browser.',
    'Retirer le mot de passe.': 'Remove the password.',
    'Retirer le lancement automatique.': 'Remove the automatic startup.',
    "Fichier d'archive a ecrire.": 'Archive file to write.',
    'Archive produite par `plugarr backup`.': 'Archive produced by `plugarr backup`.',
    'Ne PAS arreter les conteneurs. Plus rapide, et la sauvegarde peut etre corrompue.': 'Do NOT stop the containers. Faster, and the backup may be corrupt.',
    "Restaurer AILLEURS que l'origine. Les chemins sont reecrits.": 'Restore SOMEWHERE ELSE than the original. Paths are rewritten.',
    'Inclure les arretes.': 'Include stopped ones.',
    'Supprime CONFIG_ROOT.': 'Deletes CONFIG_ROOT.',
    # -- messages de la ligne de commande ------------------------------------------
    # Poses par la console traduisante de `report.py`, qui joue pour la ligne de
    # commande le role de `tui/widgets.py` pour l'assistant.
    '[dim]Ouverte dans votre navigateur.[/dim]': '[dim]Opened in your browser.[/dim]',
    '[dim]Aucun navigateur disponible ici : ouvrez ce fichier a la main.[/dim]': '[dim]No browser available here: open this file by hand.[/dim]',
    "\n[dim]Vos medias ne sont jamais touches : seul l'etat ci-dessus le serait.[/dim]": '\n[dim]Your media is never touched: only the state above would be.[/dim]',
    '[dim]Configurations conservees.[/dim]': '[dim]Configurations kept.[/dim]',
    '[dim]Conservee (--yes ne supprime rien). Utilisez --reset-config pour repartir de zero.[/dim]': '[dim]Kept (--yes deletes nothing). Use --reset-config to start over.[/dim]',
    "[yellow]Un template a ete choisi mais Recyclarr n'est pas dans la selection : il ne sera pas applique.[/yellow]": '[yellow]A template was chosen but Recyclarr is not in the selection: it will not be applied.[/yellow]',
    '[yellow]--vpn sans client de telechargement : Gluetun ne protegerait rien.[/yellow]': '[yellow]--vpn with no download client: Gluetun would protect nothing.[/yellow]',
    '[cyan]--dry-run : aucune ecriture. Compose qui serait genere :[/cyan]': '[cyan]--dry-run: nothing written. The Compose that would be generated:[/cyan]',
    '[red]Des controles bloquants ont echoue.[/red]': '[red]Blocking checks failed.[/red]',
    '[dim]Diagnostic : `plugarr doctor`[/dim]': '[dim]Diagnostic: `plugarr doctor`[/dim]',
    'Aucun service connu detecte sur cette machine.': 'No known service detected on this machine.',
    "[red]Rien d'adoptable. Lancez `plugarr scan` pour comprendre.[/red]": '[red]Nothing to adopt. Run `plugarr scan` to find out why.[/red]',
    "[red]Impossible de determiner l'adresse de cette machine sur le reseau.[/red]\n[dim]Les conteneurs doivent pouvoir se joindre entre eux : `localhost` ne convient pas. Passez --host <adresse>.[/dim]": "[red]Cannot determine this machine's address on the network.[/red]\n[dim]The containers must be able to reach each other: `localhost` will not do. Pass --host <address>.[/dim]",
    '[dim]Le jeton change a chaque demarrage. Ctrl+C pour arreter.[/dim]': '[dim]The token changes on every start. Ctrl+C to stop.[/dim]',
    "[dim]Aucun navigateur : ouvrez l'URL ci-dessus.[/dim]": '[dim]No browser: open the URL above.[/dim]',
    'Serveur arrete.': 'Server stopped.',
    '[red]Huit caracteres au minimum.[/red]': '[red]Eight characters minimum.[/red]',
    'Mot de passe enregistre. La console demandera desormais ce mot de passe, et acceptera toujours le jeton affiche par `plugarr serve`.': 'Password saved. The console will now ask for it, and will still accept the token printed by `plugarr serve`.',
    'Mot de passe retire. Seul le jeton de session ouvre desormais la console.': 'Password removed. Only the session token opens the console now.',
    "[yellow]Aucun mot de passe n'est pose sur la console.[/yellow]": '[yellow]No password is set on the console.[/yellow]',
    "[dim]Lancee automatiquement, elle n'afficherait son jeton dans aucun terminal : personne ne pourrait y entrer. Posez-en un d'abord :[/dim]": '[dim]Started automatically, it would print its token in no terminal: nobody could get in. Set one first:[/dim]',
    '  plugarr admin-password': '  plugarr admin-password',
    "[dim]Une unite utilisateur s'arrete a la deconnexion. Pour qu'elle survive :[/dim]": '[dim]A user unit stops at logout. To make it survive:[/dim]',
    '  loginctl enable-linger $USER': '  loginctl enable-linger $USER',
    "[yellow]Sauvegarde a chaud.[/yellow] Une base SQLite copiee pendant qu'on ecrit dedans donne un fichier valide en apparence et inutilisable en pratique. Sans --live, PlugArr arrete les conteneurs le temps de la copie.": '[yellow]Hot backup.[/yellow] A SQLite database copied while it is being written to gives a file that looks valid and is unusable in practice. Without --live, PlugArr stops the containers for the duration of the copy.',
    '[yellow]Cette archive contient vos mots de passe et vos cles API en clair.[/yellow]\n[dim]Elle est en lecture seule pour vous (chmod 600). Rangez-la comme un secret.[/dim]': '[yellow]This archive holds your passwords and API keys in cleartext.[/yellow]\n[dim]It is readable by you only (chmod 600). Store it like a secret.[/dim]',
    '[yellow]Cette archive a ete prise A CHAUD, conteneurs en marche.[/yellow] Ses bases peuvent etre corrompues.': '[yellow]This archive was taken HOT, with containers running.[/yellow] Its databases may be corrupt.',
    '[green]Restauration terminee.[/green]': '[green]Restore complete.[/green]',
    '\nEtat des conteneurs :': '\nContainer status:',
    'Joignabilite des API :': 'API reachability:',
    '\nProtection VPN du trafic torrent :': '\nVPN protection of torrent traffic:',
    "[bold]Proposees dans l'assistant[/bold]": '[bold]Offered in the wizard[/bold]',
    '[dim]Jellyfin et Silo acceptent tout code ISO ; la liste ci-dessus est celle que les *arr savent afficher.[/dim]': '[dim]Jellyfin and Silo accept any ISO code; the list above is the one the *arr can display.[/dim]',
    '[dim]Liste obtenue de Gluetun v3.41.3 lui-meme, pas recopiee.[/dim]\n': '[dim]List obtained from Gluetun v3.41.3 itself, not copied.[/dim]\n',
    "[dim]Choix a l'installation : `plugarr install --recyclarr-sonarr <nom> --recyclarr-radarr <nom>`.[/dim]": '[dim]Chosen at install time: `plugarr install --recyclarr-sonarr <name> --recyclarr-radarr <name>`.[/dim]',
    "Aucun indexeur configure.\n[dim]plugarr n'en fournit aucun : ajoutez les votres avec `plugarr indexers add`.[/dim]": 'No indexer configured.\n[dim]plugarr provides none: add your own with `plugarr indexers add`.[/dim]',
    # -- messages a champs nommes de la ligne de commande --------------------------
    "\n[yellow]Etat existant detecte[/yellow] pour [bold]{services}[/bold].\n[dim]Leurs mots de passe ne se relisent pas : plugarr ne peut pas les reprendre, et ceux qu'il va annoncer seront refuses.[/dim]": '\n[yellow]Existing state detected[/yellow] for [bold]{services}[/bold].\n[dim]Their passwords cannot be read back: plugarr cannot take them over, and the ones it is about to announce will be refused.[/dim]',
    'Supprimer cet etat et repartir de zero ?': 'Delete this state and start over?',
    '[red]Template inconnu pour {service} : {nom}[/red]\n[dim]`plugarr templates` liste les noms acceptes.[/dim]': '[red]Unknown template for {service}: {nom}[/red]\n[dim]`plugarr templates` lists the accepted names.[/dim]',
    '[yellow]Noms de templates non verifies : {cause}[/yellow]': '[yellow]Template names not verified: {cause}[/yellow]',
    "[red]VPN active mais incomplet : il manque {champs}.[/red]\n[dim]Sans cela Gluetun refuse de demarrer, et le client torrent reste injoignable puisqu'il partage sa pile reseau.[/dim]": '[red]VPN enabled but incomplete: missing {champs}.[/red]\n[dim]Without them Gluetun refuses to start, and the torrent client stays unreachable since it shares its network stack.[/dim]',
    "[yellow]PUID/PGID {uid}:{gid} - {origine}.[/yellow]\n[dim]C'est l'utilisateur Linux, a l'interieur des conteneurs, qui possedera vos fichiers. Sur un NAS, lancez `id` en tant que l'utilisateur voulu.[/dim]": '[yellow]PUID/PGID {uid}:{gid} - {origine}.[/yellow]\n[dim]That is the Linux user, inside the containers, that will own your files. On a NAS, run `id` as the user you want.[/dim]',
    'Ecrire les fichiers et demarrer la stack ?': 'Write the files and start the stack?',
    '\n[dim]Journal detaille : {chemin}[/dim]': '\n[dim]Detailed log: {chemin}[/dim]',
    '[yellow]{service} est present {nombre} fois ({noms}).[/yellow]\n[dim]Precisez lequel cabler : --pick {identifiant}=<conteneur>[/dim]': '[yellow]{service} is present {nombre} times ({noms}).[/yellow]\n[dim]Say which one to wire: --pick {identifiant}=<container>[/dim]',
    '[dim]Adresse retenue pour le cablage : {hote}[/dim]': '[dim]Address used for the wiring: {hote}[/dim]',
    '[red]{identifiant} est ambigu : {noms}.[/red] [dim]Ajoutez --pick {identifiant}=<conteneur>[/dim]': '[red]{identifiant} is ambiguous: {noms}.[/red] [dim]Add --pick {identifiant}=<container>[/dim]',
    '[cyan]{nombre} lien(s) seraient poses sur ces conteneurs existants. Aucun ne sera recree.[/cyan]': '[cyan]{nombre} link(s) would be set up on these existing containers. None will be recreated.[/cyan]',
    'Cabler ces services ?': 'Wire these services?',
    "[yellow]Ecoute sur {hote} : la page sera joignable depuis le reseau.[/yellow]\n[dim]Elle permet d'arreter vos services et affiche vos identifiants. Le jeton est la seule protection ; ne partagez pas l'URL.[/dim]": '[yellow]Listening on {hote}: the page will be reachable from the network.[/yellow]\n[dim]It can stop your services and shows your credentials. The token is the only protection; do not share the URL.[/dim]',
    "[red]Impossible d'ecouter sur {hote}:{port} : {erreur}[/red]": '[red]Cannot listen on {hote}:{port}: {erreur}[/red]',
    'Nouveau mot de passe': 'New password',
    '[dim]Deja installe : {chemin}. Reecriture.[/dim]': '[dim]Already installed: {chemin}. Rewriting.[/dim]',
    '[dim]Console : http://{hote}:{port} — au prochain demarrage de session.[/dim]': '[dim]Console: http://{hote}:{port} — at your next login session.[/dim]',
    "[dim]Vos medias dans {racine} ne sont PAS dedans, et c'est voulu.[/dim]": '[dim]Your media in {racine} is NOT in it, and that is deliberate.[/dim]',
    'Ecraser la configuration dans {config} et le projet dans {projet} ?': 'Overwrite the configuration in {config} and the project in {projet}?',
    '[dim]Demarrez la pile, puis `plugarr wire --project-dir {repertoire}` pour verifier que tout repond.[/dim]': '[dim]Start the stack, then run `plugarr wire --project-dir {repertoire}` to check that everything answers.[/dim]',
    'Supprimer definitivement {chemin} (bases, historiques, reglages) ?': 'Permanently delete {chemin} (databases, history, settings)?',
    'Confirmez une seconde fois : cette action est irreversible.': 'Confirm a second time: this action cannot be undone.',
    "[dim]Vos medias dans {racine} n'ont pas ete touches.[/dim]": '[dim]Your media in {racine} was not touched.[/dim]',
    '[dim]Aussi acceptees par --langue : {codes}[/dim]': '[dim]Also accepted by --langue: {codes}[/dim]',
    # -- preflight ---------------------------------------------------------------
    # Le premier tableau qu'on voit, en ligne de commande comme dans l'assistant.
    'binaire `docker` introuvable dans le PATH. Installez Docker Engine ou Docker Desktop, puis relancez.': '`docker` binary not found on PATH. Install Docker Engine or Docker Desktop, then run again.',
    'trouve : {chemin}': 'found: {chemin}',
    'daemon docker': 'docker daemon',
    'le binaire repond mais le daemon est injoignable ou trop lent. Demarrez Docker (Desktop, ou `systemctl start docker`). Detail : {detail}': 'the binary answers but the daemon is unreachable or too slow. Start Docker (Desktop, or `systemctl start docker`). Detail: {detail}',
    'version serveur {version}': 'server version {version}',
    'plugin `docker compose` absent. Installez docker-compose-plugin.': '`docker compose` plugin missing. Install docker-compose-plugin.',
    'libre': 'free',
    'deja utilise. Changez le port de {service} dans stack.yml.': "already in use. Change {service}'s port in stack.yml.",
    'occupe par votre propre pile plugarr': 'used by your own plugarr stack',
    'racine des donnees': 'data root',
    'racine des configurations': 'config root',
    'existe et est inscriptible': 'exists and is writable',
    'sera cree dans {parent}, qui est inscriptible': 'will be created in {parent}, which is writable',
    "{chemin} n'est pas dans un dossier : {obstacle} existe et n'en est pas un.": '{chemin} is not inside a directory: {obstacle} exists and is not one.',
    "impossible d'ecrire dans {obstacle} ({erreur}). Choisissez un autre emplacement : --data-root et --config-root, ou l'ecran des chemins dans l'assistant.": 'cannot write into {obstacle} ({erreur}). Pick another location: --data-root and --config-root, or the paths screen in the wizard.',
    'impossible de creer {source} ou {cible} : {erreur}': 'cannot create {source} or {cible}: {erreur}',
    'espace disque': 'disk space',
    'impossible de lire {chemin} : {erreur}': 'cannot read {chemin}: {erreur}',
    '{libres:.1f} Go libres': '{libres:.1f} GB free',
    ' - moins que le minimum conseille de {minimum} Go': ' - below the recommended minimum of {minimum} GB',
    'configuration existante': 'existing configuration',
    'aucune, installation neuve': 'none, fresh installation',
    'reprise : {services}': 'taking over: {services}',
    'dans {chemin}': 'in {chemin}',
    'dans le volume Docker {volumes}': 'in the Docker volume {volumes}',
    'dans {chemin}, et dans les volumes Docker {volumes}': 'in {chemin}, and in the Docker volumes {volumes}',
    '{services} ont deja un etat {ou}. Leurs mots de passe ne se relisent pas chez eux : PlugArr essaiera ceux de ses installations precedentes, et ne generera un mot de passe neuf que si aucun ne convient.': '{services} already have state {ou}. Their passwords cannot be read back from them: PlugArr will try those of its previous installations, and will only generate a new password if none fits.',
    'nom de projet': 'project name',
    'des conteneurs nommes {nom} tournent deja depuis {ailleurs}. Installer ici les REMPLACERA : Docker identifie une pile par son nom, pas par son repertoire. Les fichiers de {ailleurs} ne seront pas touches, mais ses services repartiront sur la configuration de {ici}.': 'containers named {nom} are already running from {ailleurs}. Installing here will REPLACE them: Docker identifies a stack by its name, not by its directory. The files in {ailleurs} will not be touched, but its services will restart on the configuration in {ici}.',
    # -- resultat de chaque etape de cablage ---------------------------------------
    # Ces fragments composent chaque ligne du rapport final : ce sont les plus
    # lus de tout le catalogue.
    'cree': 'created',
    'deja present': 'already present',
    'deja configure ({dossiers}), respecte': 'already configured ({dossiers}), respected',
    'aucun dossier racine configure': 'no root folder configured',
    'identifiants inconnus': 'credentials unknown',
    'identifiants mis a jour ({champs})': 'credentials updated ({champs})',
    'realigne ({champs})': 'realigned ({champs})',
    'client existant, categories laissees telles quelles': 'existing client, categories left as they are',
    'client existant, reglages laisses tels quels': 'existing client, settings left as they are',
    'creees : {noms}': 'created: {noms}',
    'aucune (deja presentes)': 'none (already present)',
    'posees : {noms}': 'set: {noms}',
    'aucune (deja completes)': 'none (already complete)',
    'assistant execute': 'wizard run',
    'assistant deja termine': 'wizard already completed',
    'accueil execute': 'setup run',
    'accueil deja termine': 'setup already completed',
    'utilisateur existant': 'existing user',
    'compte cree': 'account created',
    'compte cree, connexion toujours refusee meme apres redemarrage': 'account created, login still refused even after a restart',
    'aucun template choisi, rien a generer': 'no template chosen, nothing to generate',
    # -- boutons de chaque service sur la console ----------------------------------
    'etat inconnu': 'status unknown',
    'verification…': 'checking…',
    'demarrer': 'start',
    'redemarrer': 'restart',
    'arreter': 'stop',
    'renouveler': 'rotate',
    'Tirer un nouveau mot de passe et recabler': 'Draw a new password and re-wire',
    'Tirer une nouvelle cle API et recabler': 'Draw a new API key and re-wire',
    # -- erreurs de cablage --------------------------------------------------------
    # Ce qu'on ne voit que quand quelque chose casse : un service qui ne repond
    # pas, une reponse illisible, une session refusee. Ces phrases finissent dans
    # le rapport final et dans plugarr.log.
    'cause': 'cause',
    'action': 'action',
    'aucun': 'none',
    '{service} pret': '{service} ready',
    "{service} n'a pas repondu en {secondes:.0f}s. Dernier retour : {dernier}": '{service} did not answer within {secondes:.0f}s. Last result: {dernier}',
    "{service} n'est jamais devenu disponible": '{service} never became available',
    'verifiez que {adresse} est joignable et que le conteneur tourne': 'check that {adresse} is reachable and that the container is running',
    'le config.xml pre-seme a peut-etre ete ecrase. Relancez `plugarr doctor`.': 'the pre-seeded config.xml may have been overwritten. Run `plugarr doctor`.',
    'le gabarit renvoye par /schema a peut-etre change de forme': 'the template returned by /schema may have changed shape',
    '{service} : implementation {implementation} absente de {ressource}/schema': '{service}: implementation {implementation} missing from {ressource}/schema',
    'implementations disponibles : {liste}': 'available implementations: {liste}',
    "la version de l'application ne propose peut-etre pas ce connecteur": 'this version of the application may not offer that connector',
    '{service} : aucun profil dans {ressource}': '{service}: no profile in {ressource}',
    'la liste est vide': 'the list is empty',
    "l'application a-t-elle fini son initialisation ?": 'has the application finished initialising?',
    '{service} : identifiants refuses': '{service}: credentials refused',
    'la WebUI a repondu "Fails."': 'the WebUI answered "Fails."',
    'le qBittorrent.conf pre-seme a peut-etre ete ecrase. Relancez `plugarr doctor`.': 'the pre-seeded qBittorrent.conf may have been overwritten. Run `plugarr doctor`.',
    'qbittorrent : reponse illisible sur les categories': 'qbittorrent: unreadable response on the categories',
    'les identifiants sont probablement refuses': 'the credentials are probably being refused',
    '{service} : creation de la categorie {categorie} refusee': '{service}: creating the category {categorie} was refused',
    'la version de qBittorrent expose-t-elle bien ces reglages ?': 'does this version of qBittorrent expose those settings?',
    'indexeur {nom} inconnu de votre Prowlarr': 'indexer {nom} unknown to your Prowlarr',
    'aucune definition de ce nom': 'no definition by that name',
    'utilisez `plugarr indexers search <terme>` pour trouver le nom exact': 'use `plugarr indexers search <term>` to find the exact name',
    'aucun detail renvoye par Prowlarr': 'no detail returned by Prowlarr',
    "l'assistant de demarrage a peut-etre deja ete termine manuellement": 'the startup wizard may already have been completed by hand',
    'aucun AccessToken dans la reponse': 'no AccessToken in the response',
    'Jellyfin : cle API introuvable apres creation': 'Jellyfin: API key not found after creation',
    'aucune entree {application} dans /Auth/Keys': 'no {application} entry in /Auth/Keys',
    "verifiez que l'utilisateur administrateur a bien ete cree": 'check that the administrator user really was created',
    "l'API d'autobrr a peut-etre change de forme": "autobrr's API may have changed shape",
    "l'API a peut-etre change de forme": 'the API may have changed shape',
    "autobrr : {service} n'est pas un type connu": 'autobrr: {service} is not a known type',
    'completez CLIENT_TYPES apres verification contre une instance': 'extend CLIENT_TYPES after verifying against a real instance',
    'qui : creation du compte initial impossible': 'qui: cannot create the initial account',
    "l'API de qui a peut-etre change de forme": "qui's API may have changed shape",
    'le mot de passe enregistre ne correspond pas au compte existant': 'the stored password does not match the existing account',
    'verifiez que qBittorrent est demarre': 'check that qBittorrent is running',
    'aucune instance a cette adresse': 'no instance at that address',
    "l'accueil a peut-etre deja ete termine manuellement": 'the setup may already have been completed by hand',
    'aucun jeton dans la reponse': 'no token in the response',
    'les identifiants annonces sont-ils bien ceux du compte ?': "are the announced credentials really the account's?",
    'completez LIBRARY_TYPES apres verification contre une instance': 'extend LIBRARY_TYPES after verifying against a real instance',
    'Audiobookshelf accepterait, mais laisserait le compte sans protection': 'Audiobookshelf would accept it, but would leave the account unprotected',
    'laissez PlugArr generer le mot de passe': 'let PlugArr generate the password',
    "le corps attendu est decrit dans /app/seerr-api.yml de l'image": "the expected body is described in the image's /app/seerr-api.yml",
    'la cle API est-elle la bonne ?': 'is the API key the right one?',
    "le nom d'hote appelant est-il dans host_whitelist ?": 'is the calling hostname in host_whitelist?',
    'depot des templates injoignable : {erreur}': 'template repository unreachable: {erreur}',
    'le depot des templates a repondu HTTP {code}': 'the template repository answered HTTP {code}',
    'manifeste des templates illisible': 'template manifest unreadable',
    # -- avertissements et echecs du cablage ---------------------------------------
    ' - introuvable a la relecture': ' - not found when read back',
    ', test OK': ', test OK',
    ' - le test de connexion a echoue': ' - the connection test failed',
    'connexion verifiee': 'login verified',
    'declaree': 'declared',
    'deja declaree': 'already declared',
    'generation impossible': 'cannot generate',
    'aucun detail': 'no detail',
    'aucun fichier rempli': 'no file filled in',
    'aucun identifiant genere, rien a verifier': 'no credentials generated, nothing to check',
    'synchronise, aucun profil a creer': 'synced, no profile to create',
    '{nombre} deja configure': '{nombre} already configured',
    '{nombre} deja configures': '{nombre} already configured',
    ', declares : {noms}': ', declared: {noms}',
    'aucun (deja presents)': 'none (already present)',
    'actif, rafraichi toutes les {minutes} min': 'on, refreshed every {minutes} min',
    ' (change : {champs})': ' (changed: {champs})',
    ' (deja actif)': ' (already on)',
    'conteneurs existants arretes avant pre-semis': 'existing containers stopped before pre-seeding',
    'aucun conteneur a arreter': 'no container to stop',
    'docker compose up (peut prendre plusieurs minutes)': 'docker compose up (may take several minutes)',
    "{service} n'a aucun dossier racine et plugarr ne peut pas deviner votre arborescence. Ajoutez-le dans {service} avant d'importer.": '{service} has no root folder and plugarr cannot guess your directory tree. Add one in {service} before importing.',
    "{service} a une configuration prealable dans {dossier}, et son mot de passe n'y est stocke que hache. PlugArr a essaye les {nombre} mots de passe qu'il connait pour ce service : aucun n'est accepte. Supprimez ce dossier pour repartir a zero — vous perdrez ce que ce service seul contenait, pas vos medias.": '{service} already has a configuration in {dossier}, and its password is stored hashed only. PlugArr tried the {nombre} passwords it knows for this service: none is accepted. Delete that folder to start over — you will lose what that service alone held, not your media.',
    "{service} a une configuration prealable dans {dossier}. Son mot de passe n'y est stocke que hache : PlugArr ne peut pas le retrouver, et celui qu'il annonce est refuse. Aucune installation precedente de PlugArr n'est connue sur cette machine — ce service a donc ete configure autrement. Supprimez ce dossier pour repartir a zero.": '{service} already has a configuration in {dossier}. Its password is stored hashed only: PlugArr cannot recover it, and the one it announces is refused. No previous PlugArr installation is known on this machine — so this service was configured some other way. Delete that folder to start over.',
    'Le mot de passe de {service} est hache dans sa configuration : plugarr ne peut pas le lire. Passez --dl-user et --dl-pass.': "{service}'s password is hashed in its configuration: plugarr cannot read it. Pass --dl-user and --dl-pass.",
    "le telechargement automatique RSS n'a pas pu etre active": 'RSS auto-downloading could not be turned on',
    '{service} -> jellyfin : cle API Jellyfin absente': '{service} -> jellyfin: Jellyfin API key missing',
    "l'etape jellyfin/setup ne s'est pas executee ou a echoue": 'the jellyfin/setup step did not run, or failed',
    'relancez `plugarr wire` : la cle est creee par cette etape': 'run `plugarr wire` again: the key is created by that step',
    "l'analyse des bibliotheques n'a pas pu etre lancee": 'the library scan could not be started',
    'categories sans repertoire : {noms}': 'categories with no directory: {noms}',
    "{fichier} ecarte : {service} etait configure par plusieurs fichiers, ce que Recyclarr refuse — il n'en synchronisait alors aucun. Le fichier est renomme, pas efface.": '{fichier} set aside: {service} was configured by several files, which Recyclarr refuses — it then synced none of them. The file is renamed, not deleted.',
    "{fichier} contient encore un marqueur : la synchronisation echouera tant qu'il est la": '{fichier} still holds a marker: the sync will fail as long as it is there',
    "Recyclarr a ecarte des instances en double : aucun profil n'a ete pose. Verifiez le contenu de configs/.": 'Recyclarr set aside duplicate instances: no profile was applied. Check the contents of configs/.',
    'premiere synchronisation echouee ({cause}). La configuration est ecrite : Recyclarr reessaiera a sa planification quotidienne.': 'first sync failed ({cause}). The configuration is written: Recyclarr will try again on its daily schedule.',
    "les identifiants annonces pour {service} n'ouvrent pas l'interface. Definissez-en depuis Settings > General.": 'the credentials announced for {service} do not open the UI. Set some from Settings > General.',
    'qui ne parvient pas a joindre {adresse} ({cause})': 'qui cannot reach {adresse} ({cause})',
    'erreur inattendue ({genre}) : {erreur}': 'unexpected error ({genre}): {erreur}',
    'ceci est un defaut de plugarr, pas de votre installation': 'this is a defect in plugarr, not in your installation',
    'le serveur de controle de Gluetun est injoignable depuis ce conteneur': "Gluetun's control server is unreachable from this container",
    'reponse illisible de Gluetun : {reponse}': 'unreadable response from Gluetun: {reponse}',
    'Gluetun ne rapporte aucune adresse publique : le tunnel est-il monte ?': 'Gluetun reports no public address: is the tunnel up?',
    'NON PROTEGE : le tunnel ressort sur VOTRE adresse publique ({pays}, {operateur}). Verifiez la configuration du fournisseur.': "NOT PROTECTED: the tunnel exits on YOUR own public address ({pays}, {operateur}). Check the provider's configuration.",
    "sortie par {pays}, {operateur} (adresse de l'hote indeterminable)": 'exits through {pays}, {operateur} (host address undeterminable)',
    'sortie par {pays}, {operateur}, differente de la votre': 'exits through {pays}, {operateur}, different from your own',
    'aucun VPN configure : {clients} sort par votre connexion': 'no VPN configured: {clients} goes out through your own connection',
    'conteneur arrete': 'container stopped',
    'NON PROTEGE : le conteneur est sur le reseau {reseau}, pas dans le tunnel. Tout torrent lance sort par votre connexion. Regenerez la pile puis redemarrez-la.': 'NOT PROTECTED: the container is on the {reseau} network, not in the tunnel. Any torrent started goes out through your own connection. Regenerate the stack and restart it.',
    "il partage la pile reseau d'un AUTRE conteneur que {attendu} ({reseau}...)": 'it shares the network stack of a DIFFERENT container than {attendu} ({reseau}...)',
    '[dim]{nombre} choix qui acceptent les connexions entrantes, sur les {total} de Gluetun {version}. Les autres sont masques : le tunnel ne demarrerait pas.[/dim]': '[dim]{nombre} choices that accept incoming connections, out of the {total} in Gluetun {version}. The others are hidden: the tunnel would not start.[/dim]',
    'Essayer la configuration': 'Try this configuration',
    "[dim]Tunnel d'essai en cours, jusqu'a {attente} secondes…[/dim]":  '[dim]Trial tunnel running, up to {attente} seconds…[/dim]',
    "[yellow]Completez d'abord : {manques}[/yellow]":  '[yellow]Fill in first: {manques}[/yellow]',
    'rien a essayer': 'nothing to try',
    "Gluetun n'a pas demarre : {cause}":  'Gluetun did not start: {cause}',
    'tunnel etabli avec {fournisseur}, sortie par {pays}': 'tunnel established with {fournisseur}, exiting through {pays}',
    'aucun tunnel etabli en {attente} secondes. La cle est peut-etre fausse, mais le fournisseur peut aussi etre indisponible.': 'no tunnel established in {attente} seconds. The key may be wrong, but the provider may also be unavailable.',
    '{fournisseur} refuse cette configuration : aucun serveur ne correspond au lieu et au port entrant demandes': '{fournisseur} rejects this configuration: no server matches the location and incoming port requested',
    "{fournisseur} refuse cette configuration : la cle privee WireGuard n'est pas valide":  '{fournisseur} rejects this configuration: the WireGuard private key is not valid',
    'aucun tunnel etabli en {attente} secondes. Les identifiants sont peut-etre faux, mais le fournisseur peut aussi etre indisponible.': 'no tunnel established in {attente} seconds. The credentials may be wrong, but the provider may also be unavailable.',
    "{fournisseur} refuse ces identifiants OpenVPN : l'identifiant ou le mot de passe n'est pas le bon": '{fournisseur} rejects these OpenVPN credentials: the username or the password is wrong',
    "Chez ProtonVPN en OpenVPN, le port entrant depend du suffixe de l'identifiant : essayez d'ajouter +pmp a la fin du votre.": 'With ProtonVPN over OpenVPN, the incoming port depends on the username suffix: try adding +pmp at the end of yours.',
    "NON PROTEGE : {conteneur} est sur le reseau {reseau}, pas dans le tunnel. plugarr ne gere pas ce conteneur et ne peut pas l'y placer : il faut le recreer vous-meme avec network_mode: container:{gluetun}.": 'NOT PROTECTED: {conteneur} is on network {reseau}, not in the tunnel. plugarr does not manage this container and cannot put it there: you have to recreate it yourself with network_mode: container:{gluetun}.',
    'aucun port obtenu aupres de {fournisseur} : le client ne recevra pas de connexions entrantes': 'no port obtained from {fournisseur}: the client will not receive incoming connections',
    'ecoute sur {port}': 'listening on {port}',
    "desynchronise : le VPN a ouvert {annonce}, le client ecoute {port}. Aucune connexion entrante n\'arrive.":  'out of sync: the VPN opened {annonce}, the client listens on {port}. No incoming connection gets through.',
    '{services} etaient accroches a un Gluetun detruit, rattaches au tunnel': '{services} were attached to a destroyed Gluetun, reconnected to the tunnel',
    'impossible de rattacher {services} au tunnel : lancez `plugarr doctor`': 'could not reattach {services} to the tunnel: run `plugarr doctor`',
    "{chemin} n'est pas sous {racine} : suppression refusee": '{chemin} is not under {racine}: deletion refused',
    'Le fichier compose genere est invalide : {cause}': 'The generated compose file is invalid: {cause}',
    'aucun service selectionne': 'no service selected',
    'le chemin ne peut pas etre vide': 'the path cannot be empty',
    'le fournisseur VPN (--vpn-provider)': 'the VPN provider (--vpn-provider)',
    'la cle privee WireGuard (--vpn-key)': 'the WireGuard private key (--vpn-key)',
    'les identifiants OpenVPN (--vpn-user et --vpn-pass)': 'the OpenVPN credentials (--vpn-user and --vpn-pass)',
    'le registre demande une authentification non geree': 'the registry demands an authentication we do not handle',
    'deja gere par plugarr': 'already managed by plugarr',
    'stack existante : plugarr ne gere pas ces conteneurs': 'existing stack: plugarr does not manage these containers',
    'Prowlarr est seul : aucune application a alimenter': 'Prowlarr is on its own: no application to feed',
    'aucun client de telechargement detecte : les *arr ne seront pas rattaches': 'no download client detected: the *arr will not be attached',
    "le volume /config n'est pas monte depuis l'hote : impossible de lire la cle API": 'the /config volume is not mounted from the host: cannot read the API key',
    'arret des conteneurs (une base copiee a chaud est corrompue)': 'stopping the containers (a database copied hot comes out corrupt)',
    'redemarrage des conteneurs': 'restarting the containers',
    "sabnzbd.ini existant, liste d'hotes deja complete": 'sabnzbd.ini already there, host list already complete',
    'Gerer vos indexeurs dans Prowlarr.': 'Manage your indexers in Prowlarr.',
    "Prowlarr n'est pas installe dans cette stack.": 'Prowlarr is not installed in this stack.',
    'Nom exact de la definition (voir `search`).': 'Exact name of the definition (see `search`).',
    'Identifiant sous la forme cle=valeur. Repetable.': 'Credential as key=value. Repeatable.',
    "[yellow]Aucun VPN n'est configure pour le client torrent.[/yellow]\n[dim]Le trafic BitTorrent sortira sur l'adresse IP publique de cette machine, visible par les autres pairs.[/dim]": "[yellow]No VPN is configured for the torrent client.[/yellow]\n[dim]BitTorrent traffic will leave through this machine's public IP address, visible to other peers.[/dim]",
    # -- derniers messages du chemin d'echec -----------------------------------------
    ' (deja posee)': ' (already set)',
    'deja configure': 'already configured',
    'introuvable a la relecture': 'not found when read back',
    'la session est-elle bien authentifiee ?': 'is the session properly authenticated?',
    'pas de profil de client de telechargement pour {service}. Connus : {liste}': 'no download client profile for {service}. Known: {liste}',
    '{chemin} introuvable depuis cette machine': '{chemin} not found from this machine',
    '{nombre} resultat(s) - source : votre Prowlarr': '{nombre} result(s) - source: your Prowlarr',
    '{service} ne repond pas : {cause}': '{service} is not answering: {cause}',
    # -- en-tetes des fichiers ecrits sur le disque ---------------------------------
    # Pas des messages a l'ecran, mais ils se lisent : on ouvre son .env pour
    # retrouver un mot de passe.
    '# Genere par plugarr - NE PAS EDITER A LA MAIN.\n# Modifiez stack.yml puis relancez `plugarr generate`.\n': '# Generated by plugarr - DO NOT EDIT BY HAND.\n# Edit stack.yml then run `plugarr generate` again.\n',
    '# Genere par plugarr. Contient des secrets : ne JAMAIS commiter.': '# Generated by plugarr. Holds secrets: NEVER commit it.',
    '# Cles API pre-semees - utilisees par le cablage automatique.': '# Pre-seeded API keys - used by the automatic wiring.',
    "# Stack ADOPTEE : plugarr cable ces services mais ne les gere pas.\n# Aucun docker-compose.yml n'est genere, `uninstall` ne s'y applique pas.\n": '# ADOPTED stack: plugarr wires these services but does not manage them.\n# No docker-compose.yml is generated, and `uninstall` does not apply.\n',
    # -- lancement automatique, console, chemins et mises a jour -------------------
    'aucun mecanisme connu sur cette plateforme': 'no known mechanism on this platform',
    'aucun mecanisme installe sur cette plateforme': 'no mechanism installed on this platform',
    'aucun lancement automatique installe': 'no automatic startup installed',
    'aucun mecanisme de lancement automatique connu sur cette plateforme. Lancez cette commande au demarrage de votre machine :\n  {commande}': 'no known automatic startup mechanism on this platform. Run this command when your machine starts:\n  {commande}',
    'Trop de tentatives. Reessayez dans {secondes} s.': 'Too many attempts. Try again in {secondes} s.',
    'service inconnu ou deja installe : {service}': 'unknown or already installed service: {service}',
    '{service} ne sait pas changer son mot de passe ici': '{service} cannot change its password here',
    "{service} n'a pas de cle API geree par plugarr": '{service} has no API key managed by plugarr',
    '{service} est deja installe': '{service} is already installed',
    'port {port} deja occupe ({service})': 'port {port} already in use ({service})',
    "aucun port de l'hote ne publie {port} : plugarr ne pourra pas le joindre": 'no host port publishes {port}: plugarr will not be able to reach it',
    'aucune cle API dans {chemin}': 'no API key in {chemin}',
    "« {chemin} » n'est pas un chemin Windows. Il sera cree dans {resolu}, ce qui n'est probablement pas voulu.": '« {chemin} » is not a Windows path. It will be created in {resolu}, which is probably not what you want.',
    "« {chemin} » est un chemin Windows, sur une machine qui ne l'est pas.": '« {chemin} » is a Windows path, on a machine that is not.',
    'aucun tag': 'no tag',
    'le tag deploye ({tag})': 'the deployed tag ({tag})',
    "{quoi} n'est pas une version comparable": '{quoi} is not a comparable version',
    'le registre a repondu HTTP {code}': 'the registry answered HTTP {code}',
    'creation de la cle API': 'creating the API key',
    '[yellow]Champs inconnus pour {indexeur}, ignores : {inconnus}[/yellow]\n[dim]Champs attendus : {attendus}[/dim]': '[yellow]Unknown fields for {indexeur}, ignored: {inconnus}[/yellow]\n[dim]Expected fields: {attendus}[/dim]',
    "{fichier} n'est pas une sauvegarde PlugArr": '{fichier} is not a PlugArr backup',
    'archive au format {trouve}, cette version lit le format {attendu}': 'archive in format {trouve}, this version reads format {attendu}',
    'identifiant invalide : {valeur}. Attendu 1 a 32 caracteres parmi lettres, chiffres, point, tiret et souligne, sans espace.': 'invalid username: {valeur}. Expected 1 to 32 characters among letters, digits, dot, dash and underscore, with no space.',
    # -- constantes portees par une variable ----------------------------------------
    'le mot de passe': 'the password',
    "Nom de la pile Docker. A changer pour installer une SECONDE pile a cote d'une premiere : Docker identifie une pile par ce nom, pas par son repertoire.": 'Docker stack name. Change it to install a SECOND stack alongside a first one: Docker identifies a stack by this name, not by its directory.',
    "Configuration existante : repartir de zero, ou la conserver. Sans l'option, la question est posee.": 'Existing configuration: start over, or keep it. Without the option, the question is asked.',
    'Silo est en pre-version : son API, sa configuration et ses migrations de base peuvent changer avant sa premiere version stable. Sauvegardez avant toute mise a jour.': 'Silo is pre-release: its API, its configuration and its database migrations may change before its first stable version. Back up before any update.',
    '# Ecrit par plugarr. Ces fichiers contiennent vos mots de passe, vos cles API\n# et, si le VPN est active, votre cle privee WireGuard. Ne les commitez pas.\n': '# Written by plugarr. These files hold your passwords, your API keys\n# and, if the VPN is on, your WireGuard private key. Do not commit them.\n',
    "Genere par plugarr. Ouvre la page d'administration : etat des|services, demarrage, arret, mises a jour.": 'Generated by plugarr. Opens the admin page: service status,|start, stop, updates.',
    "rem Genere par `plugarr autostart`. Supprimez ce fichier pour arreter\r\nrem le lancement automatique de la console d'administration.\r\n": 'rem Generated by `plugarr autostart`. Delete this file to stop\r\nrem the admin console from starting automatically.\r\n',
    # -- sauvegarde et restauration ---------------------------------------------------
    "Contenu de l'archive": 'Archive contents',
    'Date': 'Date',
    'Pile': 'Stack',
    'Volumes': 'Volumes',
    'Configuration vers': 'Configuration to',
    '[red]{fichier} introuvable.[/red]': '[red]{fichier} not found.[/red]',
    "{chemin} introuvable. Lancez d'abord `plugarr install`.": '{chemin} not found. Run `plugarr install` first.',
    "{fichier} n'est pas une archive lisible": '{fichier} is not a readable archive',
    # -- mise a jour du pack et migrations de stack.yml -----------------------------
    "stack.yml est en version {trouvee}, cette version de PlugArr lit jusqu'a la {connue}. Mettez PlugArr a jour : continuer effacerait les reglages qu'il ne sait pas lire.": 'stack.yml is at version {trouvee}, this version of PlugArr reads up to {connue}. Update PlugArr: going on would erase the settings it cannot read.',
    'stack.yml migre en version {version}': 'stack.yml migrated to version {version}',
    'version de stack.yml illisible : {valeur}': 'unreadable stack.yml version: {valeur}',
    'aucune migration de la version {depuis} vers la {vers}': 'no migration from version {depuis} to {vers}',
    'Aligne une installation ancienne sur cette version de PlugArr.': 'Brings an older installation in line with this version of PlugArr.',
    'Ne pas rejouer le cablage a la fin.': 'Do not replay the wiring at the end.',
    'Images a aligner sur le catalogue': 'Images to bring in line with the catalogue',
    'Installee': 'Installed',
    'Catalogue': 'Catalogue',
    'meme version, re-epinglee': 'same version, re-pinned',
    'ignore': 'skipped',
    '{service} : {installee} est deja plus recent que {catalogue}': '{service}: {installee} is already newer than {catalogue}',
    '{service} : {installee} et {catalogue} ne se comparent pas': '{service}: {installee} and {catalogue} cannot be compared',
    '[green]Les images sont deja celles du catalogue.[/green]': "[green]The images are already the catalogue's.[/green]",
    '[dim]Rien a faire.[/dim]': '[dim]Nothing to do.[/dim]',
    '[dim]Le cablage est rejoue quand meme : il est idempotent.[/dim]': '[dim]The wiring is replayed anyway: it is idempotent.[/dim]',
    "[cyan]--dry-run : rien n'a ete ecrit.[/cyan]": '[cyan]--dry-run: nothing was written.[/cyan]',
    'Appliquer ces {nombre} mise(s) a jour ?': 'Apply these {nombre} update(s)?',
    '[red]{service} : telechargement echoue[/red]': '[red]{service}: download failed[/red]',
    '[dim]Rejeu du cablage...[/dim]': '[dim]Replaying the wiring...[/dim]',
    # -- reprise d'une installation existante ----------------------------------------
    'Reprendre les reglages du stack.yml deja present : identifiants, VPN, profils. Actif par defaut.': 'Reuse the settings from the stack.yml already there: credentials, VPN, profiles. On by default.',
    '[cyan]Installation existante detectee : reglages repris.[/cyan]': '[cyan]Existing installation detected: settings reused.[/cyan]',
    'Reglages': 'Settings',
    'Identifiants conserves': 'Credentials kept',
    'VPN ({fournisseur})': 'VPN ({fournisseur})',
    '[dim]`--repartir-de-zero` ignore tout cela.[/dim]': '[dim]`--repartir-de-zero` ignores all of it.[/dim]',
    'identifiant': 'username',
    'fuseau horaire': 'time zone',
    'adresse de la machine': 'machine address',
    'langue des services': 'services language',
    'langue de PlugArr': 'PlugArr language',
    'mot de passe de la console': 'console password',
    'profils de qualite': 'quality profiles',
    '{chemin} est illisible : {erreur}': '{chemin} is unreadable: {erreur}',
    'Reprendre ces reglages': 'Reuse these settings',
    'Repartir de zero': 'Start over',
    '[cyan]Une installation existe deja ici : ses reglages sont repris.[/cyan]': '[cyan]An installation already exists here: its settings are reused.[/cyan]',
    "[cyan]Une installation precedente a ete retrouvee dans {dossier}[/cyan]\n[dim]Ses reglages sont repris, et c'est la que PlugArr ecrira ses fichiers : une pile Docker ne peut pas vivre dans deux repertoires a la fois.[/dim]": '[cyan]A previous installation was found in {dossier}[/cyan]\n[dim]Its settings are reused, and that is where PlugArr will write its files: a Docker stack cannot live in two directories at once.[/dim]',
    '[cyan]Installation precedente retrouvee dans {dossier}.[/cyan]\n[dim]Les fichiers du projet y seront ecrits : une pile Docker ne peut pas vivre dans deux repertoires a la fois.[/dim]': '[cyan]Previous installation found in {dossier}.[/cyan]\n[dim]The project files will be written there: a Docker stack cannot live in two directories at once.[/dim]',
    # -- mot de passe repris d'une installation precedente -------------------
    ", mot de passe repris de l'installation precedente": ', password reused from the previous installation',
    '{service} : aucun mot de passe accepte': '{service}: no password accepted',
    "ni celui qui vient d'etre genere, ni ceux des installations precedentes": 'neither the freshly generated one nor those of previous installations',
    'supprimez la configuration de ce service pour repartir a zero': "delete this service's configuration to start over",
    # -- une nouvelle version de PlugArr lui-meme ------------------------------------
    '[yellow]PlugArr {disponible} est disponible[/yellow] [dim](vous avez la {courante})[/dim]': '[yellow]PlugArr {disponible} is available[/yellow] [dim](you have {courante})[/dim]',
    "[dim]Cette commande aligne les services sur le catalogue de la version que VOUS lancez : telechargez la nouvelle d'abord.[/dim]": '[dim]This command aligns the services on the catalogue of the version YOU are running: download the new one first.[/dim]',
    '[dim]Version de PlugArr non verifiee : {cause}[/dim]': '[dim]PlugArr version not checked: {cause}[/dim]',
    'GitHub injoignable : {erreur}': 'GitHub unreachable: {erreur}',
    'GitHub a repondu HTTP {code}': 'GitHub answered HTTP {code}',
    "quota de l'API GitHub epuise, reessayez plus tard": 'GitHub API quota exhausted, try again later',
    'reponse illisible de GitHub': 'unreadable response from GitHub',
    'versions incomparables : {tag} et {courante}': 'incomparable versions: {tag} and {courante}',
    # -- sauvegarder depuis l'assistant --------------------------------------
    'Sauvegarder': 'Back up',
    'Sauvegarder une installation existante': 'Back up an existing installation',
    'Installation a sauvegarder': 'Installation to back up',
    "Fichier d'archive a ecrire (.zip)": 'Archive file to write (.zip)',
    'Sauvegarder a chaud, sans arreter les conteneurs': 'Back up live, without stopping the containers',
    'Sauvegarde en cours. Ne fermez pas cette fenetre.': 'Backup in progress. Do not close this window.',
    "Une archive contient votre [b]stack.yml[/b], la configuration de chaque service et les volumes Docker : indexeurs, profils, bibliotheques, mots de passe.\n\n[b]Vos medias n'y sont pas[/b] : ils pesent des teraoctets et ne sont pas une configuration.": "An archive holds your [b]stack.yml[/b], every service's configuration and the Docker volumes: indexers, profiles, libraries, passwords.\n\n[b]Your media are not in it[/b]: they weigh terabytes and are not a configuration.",
    "[dim]Une base SQLite copiee pendant qu'on ecrit dedans donne un fichier valide en apparence et inutilisable en pratique. Sans cette case, PlugArr arrete les conteneurs le temps de la copie puis les redemarre.[/dim]": '[dim]An SQLite database copied while it is being written to gives a file that looks valid and is unusable in practice. Without this box, PlugArr stops the containers for the duration of the copy, then restarts them.[/dim]',
    '[dim]stack.yml : {stack}\nConfigurations : {config}\nServices : {services}[/dim]': '[dim]stack.yml: {stack}\nConfigurations: {config}\nServices: {services}[/dim]',
    '[yellow]Aucune installation trouvee.[/yellow]\n[dim]Indiquez ci-dessus le dossier qui contient stack.yml, puis validez avec Entree.[/dim]': '[yellow]No installation found.[/yellow]\n[dim]Enter above the folder holding stack.yml, then confirm with Enter.[/dim]',
    '[green]Sauvegarde terminee.[/green]\n\n{archive}\n{taille} Mo, {fichiers} fichiers, volumes : {volumes}': '[green]Backup complete.[/green]\n\n{archive}\n{taille} MB, {fichiers} files, volumes: {volumes}',
}
