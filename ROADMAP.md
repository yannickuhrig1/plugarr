***Français** · [English](ROADMAP.en.md)*

# Feuille de route

Où en est PlugArr, ce qui vient ensuite, et pourquoi. Tenue à jour à chaque
séance de travail.

**Dernière mise à jour : 13 septembre 2026** — version publiée : **0.9.0**

---

## Ce qui marche aujourd'hui

Seize services installés et **câblés** en une passe, vérifiés contre des
instances réelles à chaque livraison.

| | |
|---|---|
| **Téléchargement** | Transmission, qBittorrent, **SABnzbd** *(Usenet)* |
| **Bibliothèque** | Sonarr, Radarr, Lidarr |
| **Indexeurs** | Prowlarr |
| **Média** | Jellyfin, Silo *(expérimental)* |
| **Livres** | Audiobookshelf |
| **Musique** | DroppedNeedle *(remplace Lidarr)* |
| **Demandes** | Seerr |
| **Automatisation** | autobrr, Recyclarr |
| **Interfaces** | Flood, qui |
| **Réseau** | Gluetun *(VPN optionnel)* |

L'assistant couvre **toutes** les options de la ligne de commande : un test
compare la signature d'`install` à ce que l'assistant sait poser, et échoue si
un écart apparaît.

**PlugArr parle français et anglais**, et les deux langues en jeu ne se
confondent plus. Celle de PlugArr — assistant, ligne de commande, rapport,
page d'accès — se choisit sur l'écran d'accueil ou par `--lang`, et part de
celle du système : un francophone le trouve en français sans rien régler, tout
le monde d'autre en anglais. Celle des **services** se demande à part, sur
l'écran des chemins, et s'applique à chaque application qui sait la recevoir.
On peut vouloir l'outil en anglais et sa médiathèque en français.

Une phrase ajoutée en français et oubliée dans le catalogue ne casse rien :
elle s'afficherait simplement en français à quelqu'un qui a demandé l'anglais,
sans erreur ni avertissement. `scripts/audit_traductions.py` relève donc les
639 phrases affichables et **échoue s'il en manque une**, ou si le catalogue
porte une entrée morte. Il tourne en CI.

**Huit bibliothèques** sont créées et rangées : films, séries, **anime**,
musique, spectacles, livres, livres audio et logiciels. Chacune a son dossier de
téléchargement, son dossier de rangement et sa catégorie qBittorrent qui envoie
l'un vers l'autre. Sonarr reçoit un dossier racine séparé pour l'anime, comme le
recommandent les TRaSH Guides. Livres et livres audio sont désormais pilotés par
Audiobookshelf ; spectacles et logiciels rangent encore les téléchargements
manuels, en attendant Shelfarr, Shelfmark et les autres.

**La configuration complète se sauvegarde et se restaure.** `plugarr backup`
archive le répertoire du projet, `CONFIG_ROOT` et **les volumes Docker** — la
base de Silo n'est pas sous `CONFIG_ROOT` et une sauvegarde qui n'archive que
des dossiers la manquerait en silence. Les conteneurs sont arrêtés pendant la
copie : une base SQLite copiée à chaud donne un fichier valide en apparence et
inutilisable en pratique. `DATA_ROOT` n'est jamais touché. `plugarr restore`
repose le tout, y compris ailleurs, en réécrivant les chemins. **Les deux sens vivent aussi dans l'assistant**, sur son premier écran : c'est le seul endroit que voit quelqu'un qui double-clique l'exécutable, et l'installation à archiver y est trouvée toute seule.

Le **lecteur RSS de qBittorrent** est activé, téléchargement automatique
compris. PlugArr n'ajoute ni flux ni règle : ils dépendent de vos traqueurs,
exactement comme les indexeurs.

**Une installation ancienne se rattrape en une commande.** `plugarr upgrade`
migre `stack.yml` si son schéma a changé, aligne les images sur le catalogue
de cette version — **sans jamais redescendre** une version que vous auriez
choisie vous-même — régénère les artefacts, puis rejoue le câblage.

La page d'administration (`plugarr serve`) donne l'état des services, les
démarre, les arrête, les redémarre, signale les mises à jour et les applique,
affiche les identifiants, **renouvelle un mot de passe ou une clé API en
recâblant tout ce qui en dépend**, et **installe un service absent de
l'installation initiale**.

---

## Empreintes relevées pour les services à venir

Vérifiées contre les registres le 4 septembre 2026, prêtes à être épinglées. Ce
n'est pas le travail, c'en est la condition préalable : un service n'entre au
catalogue que **câblé et vérifié** contre une instance réelle. Trois des cinq
empreintes relevées ce jour-là sont désormais au catalogue : Seerr,
Audiobookshelf et DroppedNeedle.

| | image épinglée |
|---|---|
| Shelfarr | `ghcr.io/pedro-revez-silva/shelfarr:2026.08.31.1@sha256:08e06f5b…` |
| Shelfmark | `ghcr.io/calibrain/shelfmark:v1.3.15@sha256:96022903…` |

---

## Prochaine étape

**La 0.10.0 : la veille et les thèmes de qBittorrent.** Deux demandes faites à
l'usage, étudiées plus bas, et chacune a un premier point à trancher avant
d'écrire une ligne :

- **la veille** : tranché, la console d'abord. Son panneau « Veille » est prêt
  (disques, débits, sortie du VPN) ; le conteneur viendra ensuite, avec
  l'image. Pour mémoire : le niveau 1 peut vivre dans la console, sur
  l'hôte, sans image. Voir « Une veille en continu, dans un conteneur » ;
- **les thèmes de qBittorrent** : VueTorrent est prêt, épinglé et proposé dans
  l'assistant. theme.park est écarté pour la 0.10.0 : mesuré, il ne survit pas
  à un redémarrage sans Internet. Voir « Personnalisation des interfaces ».

**Shelfarr et Shelfmark** suivent : leurs empreintes sont déjà relevées, et
Audiobookshelf les débloque, puisqu'ils livrent dans ses bibliothèques.

### Ce que la mise à jour du pack a réglé — livré en 0.6.0

`stack.yml` portait un champ `version: 1` depuis la première ligne du projet,
et **rien ne le lisait**. Ce n'était pas un détail d'hygiène : pydantic ignore
les champs qu'il ne connaît pas, donc une version ancienne lisant un `stack.yml`
récent en jetait une partie — et la **première écriture la détruisait**,
`install`, `generate` et la rotation d'un mot de passe réécrivant tous ce
fichier.

La perte a été reproduite avant d'être corrigée :

    version lue          : 2
    champ futur garde ?  : False
    champ futur reecrit ?: False

| | |
|---|---|
| Migrations de `stack.yml`, indexées sur son numéro de version | ✅ 0.6.0 |
| Appliquer les digests épinglés d'un nouveau catalogue à une installation ancienne | ✅ 0.6.0 |
| Rejouer les étapes de câblage qui ont changé depuis la version installée | ✅ par `wire`, voir ci-dessous |

**Le troisième point ne demandait pas ce qu'il annonçait.** Tenir un registre
des « étapes qui ont changé depuis la version X » supposait de versionner
chaque étape de câblage et de maintenir cette table à chaque modification —
pour ne gagner que du temps d'exécution, puisque `wire` est **idempotent** par
construction et qu'une étape déjà posée se contente de le relire. `upgrade`
rejoue donc tout, et le dit.

**Pas de fichier de secrets chiffré**, et la raison est mécanique plutôt que
philosophique : c'est **Docker Compose** qui lit le `.env`, pas plugarr.
`POSTGRES_PASSWORD`, `SILO_SECRET_KEY` et les identifiants VPN doivent être en
clair sur le disque au moment du `up`, sinon la stack ne démarre pas. Chiffrer
`stack.yml` pendant que `.env` est en clair à côté serait décoratif. Un vrai
chiffrement suppose une phrase de passe tapée à chaque démarrage, ce qui
supprime le démarrage automatique livré en 0.1.9. Ce qui protège aujourd'hui :
`chmod 600`, `.gitignore` généré, et masquage des secrets dans le journal.

---

## Livré récemment

| | État | Note |
|---|---|---|
| **Rotation des mots de passe** | ✅ livré en 0.1.7 | qBittorrent, Transmission et les *arr. Vérifié sur une stack de onze services : 25 liaisons sur 25 réalignées. |
| **Rotation des clés API** | ✅ livré en 0.1.8 | Sur les *arr. Piège vérifié contre Sonarr 4.0.19 : `PUT config/host` répond **202 Accepted** et ne change rien — la clé relue vaut toujours l'ancienne une minute plus tard. Seule la réécriture de `config.xml` suivie d'un redémarrage fonctionne. |
| **Ajouter un service après coup** | ✅ livré en 0.1.8 | Section « Ajouter un service » sur la page d'administration. Vérifié en vrai : stack Sonarr seul, puis ajout de Prowlarr — 4 liaisons câblées, clé et mot de passe de Sonarr intacts. |
| **Silo** | ✅ livré en 0.1.11 | Serveur média compatible API Jellyfin, **marqué expérimental**. Trois conteneurs — `pgvector/pgvector:pg18`, `redis:alpine` et `silo-server`, épinglés au digest ; Meilisearch est optionnel et n'est pas installé. Compte, **profil** et trois bibliothèques posés et relus. Deux pièges mesurés, pas supposés : sa base doit vivre dans un **volume Docker** (montage vers l'hôte : migrations en **2935 s** contre **5 s**), et son mot de passe de base doit être alphanumérique — un `?` dans une `postgres://` et le conteneur redémarre en boucle. |
| **Langue des interfaces** | ✅ livré en 0.1.11 | Demandée une fois dans l'assistant, appliquée partout. Chaque application exprime la même idée autrement : Sonarr et Radarr veulent un entier, **Prowlarr veut le code** (`fr`), Jellyfin une culture et un pays, Silo un code **par bibliothèque**. La table des 29 langues des *arr n'est publiée nulle part : relevée valeur par valeur contre un Sonarr 4.0.19. Au passage, une incohérence corrigée — PlugArr imposait le français à Jellyfin, en dur, et laissait tout le reste en anglais. |
| **Liste des pays du VPN** | ✅ livré en 0.1.8 | Liste cliquable, extraite de l'image **épinglée**. Piège trouvé au passage : cinq fournisseurs n'exposent aucun pays — quatre classent par région, un par ville. `SERVER_COUNTRIES` ne filtrait rien chez eux. |
| **Port entrant du VPN** | ✅ livré en 0.8.0 | Quatre fournisseurs sur vingt-cinq le permettent, et PlugArr l'active alors sans rien demander : sans lui, le client télécharge très bien mais ne partage qu'à moitié. Trois pièges traités, aucun supposé — l'assistant n'offre que les lieux qui en offrent un (Gluetun refuse de **démarrer** sinon : chez PIA, ce sont les 55 régions des États-Unis qui sont écartées), un script suit le port quand le fournisseur en change (Proton est passé de 45270 à 48406 entre deux journées, sans que rien ne le dise), et le contrôle **relit** la valeur chez le client. Verdict séparé de celui de la protection : un port désynchronisé coûte du partage, pas de l'exposition. |
| **Essayer la configuration VPN** | ✅ livré en 0.8.0 | Un Gluetun jetable monté avec exactement ce qui a été saisi, avant de bâtir la stack. Il n'accepte qu'**une preuve de sortie** : une clé bien formée mais fausse « s'établit » sans qu'un paquet ne passe, et Gluetun rend alors une adresse publique vide. Jamais bloquant, mais trois refus sont certains et nommés — lieu sans serveur, clé illisible, identifiants OpenVPN rejetés. |
| **Mode OpenVPN éprouvé** | ✅ livré en 0.8.0 | Jusque-là, seul WireGuard avait été essayé en vrai. Vérifié le 2026-09-09 contre un compte ProtonVPN réel : tunnel en 14 s, port entrant obtenu. Trois défauts trouvés à cette occasion — `AUTH_FAILED` n'était pas reconnu, l'attente de 45 s était mesurée sur WireGuard alors qu'OpenVPN patiente 60 s fermes sur un serveur muet, et le message d'expiration parlait d'une « clé » dans un mode où l'on saisit un identifiant. |
| **Assistant web local** | ✅ livré en 0.9.0 | Le parcours complet du terminal, dans le navigateur : sauvegarde et restauration, chemins, VPN et essai du tunnel, profils de qualité, récapitulatif, indexeurs après l'installation. La carte des connexions montre ce qui sera câblé, puis chaque liaison en direct. Serveur sur `127.0.0.1` derrière un jeton de session. Éprouvé dans un vrai navigateur et par une installation réelle de bout en bout sous Windows : 6 services, 18 liaisons sur 18. |
| **Console de maintenance** | ✅ livré en 0.9.0 | Sauvegardes planifiées avec rotation, historique, alertes, test et réparation d'une liaison précise, mise à jour automatique de `plugarr.exe` vérifiée par son empreinte SHA-256. |
| **Choisir le client de téléchargement** | ✅ livré en 0.9.0 | Deux clients torrent installés, et les *arr **alternaient** entre eux : tous étaient déclarés à `priority: 1`, et Sonarr applique alors un round-robin. Le client préféré passe à 1, les autres descendent et restent en secours ; qBittorrent par défaut, comme pour le port entrant. Question posée dans l'assistant web, le TUI et par `--client-prefere`, seulement quand elle a un sens. Une installation existante n'est corrigée que dans l'état fautif, jamais par-dessus un réglage manuel. Vérifié en CI sur un vrai Sonarr après le second passage de câblage : qBittorrent à 1, Transmission à 2. `stack.yml` passe en version 3, pour qu'une version plus ancienne refuse le fichier au lieu d'effacer ce choix. |
| **Ports en double dans la pile** | ✅ livré en 0.9.0 | Le préflight sondait l'**hôte**, et ne voyait donc pas deux services de PlugArr sur le même port : tous deux « libres », puis `docker compose up` échouait pour la pile entière. Reproduit avec une pile Silo puis Jellyfin ajouté par l'assistant web, qui publiait 8096 deux fois. La cause est corrigée, et un contrôle bloquant compare désormais le plan à lui-même. |
| **Téléchargement des images** | ✅ livré en 0.9.0 | Trois tentatives au lieu d'une. Relevé en CI : une coupure du registre (`read: connection reset by peer` chez lscr.io) faisait échouer toute l'installation. `pull` est idempotent, et une erreur définitive remonte toujours avec son message. |
| **Indexeurs repris d'une sauvegarde Prowlarr** | ✅ prêt pour la 0.10.0 | Dans le panneau indexeurs de l'assistant, après l'installation, ou par `plugarr indexers import`. Seule la table des indexeurs est lue ; chacun est ajouté par l'API, sans toucher au client de téléchargement ni aux applications. Vérifié sur le banc : empreintes du client et des applications identiques avant et après. Prowlarr met jusqu'à 100 s à refuser un tracker hors ligne : il a désormais 150 s. |
| **Configurer le téléphone par fichier** | ✅ prêt pour la 0.10.0 | Sauvegardes à restaurer dans **nzb360** 24.4.1 (Sonarr, Radarr, Lidarr, Seerr, qBittorrent ou Transmission, SABnzbd) et **qbRemote** 1.8.0 (chiffrée AES-256). Un seul fichier pour la maison et l'extérieur : l'appli bascule sur l'adresse locale sur le Wi-Fi de la maison. Formats relevés dans de vraies sauvegardes, puis chaque service validé sur un vrai téléphone Android, dont l'interrupteur de bascule de nzb360 sans lequel l'adresse locale ne sert jamais. |
| **Garder les réglages du téléphone** | ✅ prêt pour la 0.10.0 | La restauration remplace tout. PlugArr part donc de la sauvegarde de l'utilisateur et n'y ajoute que ses services : serveur PlugArr ajouté à qbRemote ; dans nzb360, un **profil « PlugArr » séparé**, sans rien remplacer. Validé sur le téléphone avec de vraies sauvegardes : autres serveurs, Tautulli et profils intacts. |
| **Envoi au téléphone par QR code** | ✅ prêt pour la 0.10.0 | Un lien à usage unique, dix minutes au plus, sur l'adresse privée du serveur. Validé en scannant avec l'appareil photo du téléphone. Sous Windows, le pare-feu demande une autorisation à la première ouverture, et l'assistant le signale. |
| **Veille dans la console** | ✅ prêt pour la 0.10.0 | Panneau en lecture seule, rafraîchi toutes les 5 s : place libre par disque (un disque partagé par plusieurs dossiers n'est compté qu'une fois), débits de qBittorrent, Transmission et SABnzbd par leurs propres API, sortie du VPN lue au serveur de contrôle de Gluetun. Débits vérifiés sur le banc avec un vrai téléchargement (l'image Debian) : les chiffres suivent ceux de qBittorrent. Sortie du VPN relevée sur un vrai tunnel ProtonVPN (WireGuard), différente de l'adresse de la maison ; un échec n'est gardé que 10 s, car Gluetun annonce une adresse vide quelques secondes au démarrage. |
| **VueTorrent pour qBittorrent** | ✅ prêt pour la 0.10.0 | En option dans l'assistant web, le TUI et `--qbittorrent-ui`. Mod épinglé par tag et condensat, cache `/modcache` en volume : VueTorrent survit aux redémarrages sans Internet. Essayé sur le banc dans les deux sens : VueTorrent servi et câblage intact, puis retour à l'interface d'origine. |
| **Seerr démarre et se connecte** | ✅ prêt pour la 0.10.0 | Première installation réelle : Seerr redémarrait en boucle (`EACCES`). Son image ignore PUID/PGID : il tourne maintenant sous PUID:PGID et reçoit son dossier. Sa clé API, qu'il crée lui-même, est lue au câblage pour les applications du téléphone. |

---

## Services à venir

Un service n'entre au catalogue que lorsqu'il est **câblé et vérifié** contre
une instance réelle. L'ordre ci-dessous est celui de l'étude.

| | Ce qu'il reste à faire |
|---|---|
| **Plex** | Second serveur média. Son jeton s'obtient par `plex.tv`, pas par l'API locale : c'est le point à vérifier avant de l'inscrire. |
| **Notifiarr** | Notifications centralisées. Chaque *arr s'y déclare par une clé API. |
| **Bazarr** | Sous-titres. Sa configuration passe par un fichier YAML et non par une API — rien n'est encore vérifié. |
| **Wizarr** | Invitations et gestion des comptes pour Jellyfin, Plex et Emby. Le plus autonome de la liste : un conteneur, et le câblage se réduit au serveur média et à sa clé. |
| **Tautulli** | Suivi et statistiques **Plex**. Ne peut pas précéder Plex. |
| **Jellystat** | Statistiques Jellyfin. Exige une base **PostgreSQL** dans un second conteneur, là où tout le catalogue tient en un seul. |
| **Tracearr** | Suivi des lectures et détection de partage de comptes. L'image `latest` réclame une base et un Redis externes ; le tag `supervised` réunit le tout en un conteneur. |
| **Shelfarr** | `ghcr.io/pedro-revez-silva/shelfarr`, **2026.08.31.1**. Demandes de livres pour l'écosystème *arr — un Seerr des livres. Cherche dans Prowlarr, télécharge par qBittorrent, livre à Audiobookshelf. Comble le trou laissé par Readarr, archivé depuis le 27 juin 2025. |
| **Shelfmark** | `ghcr.io/calibrain/shelfmark`, **v1.3.15**, 60 versions. Interface de recherche et de demande de livres, sources et clients apportés par vous. |
| **Whisparr v2 et v3** | Demandé par un utilisateur, en opt-in explicite. **Deux applications distinctes sous un même nom**, pas deux versions : la v2 dérive de Sonarr (un site est une série, une scène un épisode, métadonnées ThePornDB), la v3 « Eros » de Radarr (une scène est un film, métadonnées StashDB). La v3 ne reprend pas une bibliothèque rangée par la v2, d'où l'intérêt d'offrir les deux. Images relevées chez hotio : `ghcr.io/hotio/whisparr`, tags `v2` (2.2.0) et `v3` (3.5.0), **toutes deux sur le port 6969** : il faut en décaler un pour qu'ils cohabitent. Leurs API diffèrent comme celles de Sonarr et Radarr : deux câblages, pas un. À vérifier contre une instance réelle avant d'y croire : que Prowlarr câble les deux (son connecteur vise `/api/v3`, qui est la version de l'API et non celle de Whisparr), que le type `WHISPARR` d'autobrr accepte la v3, et que le pré-semis de `config.xml` tient pour l'une et l'autre. |
| **Deluge** | Demandé à l'usage. Troisième client BitTorrent, à côté de Transmission et de qBittorrent. Image relevée chez linuxserver : `lscr.io/linuxserver/deluge`, tag `2.2.0` (24/08/2026), avec une **seconde ligne `libtorrentv1`** (`libtorrentv1-2.2.0-ls62`, 07/09/2026) : deux bibliothèques libtorrent pour la même version de Deluge, il faudra choisir laquelle on épingle et écrire pourquoi. Interface web sur **8112**, mot de passe par défaut `deluge` — aucun heurt de port avec les clients déjà au catalogue. Le piège est ailleurs : les *arr exigent que **les greffons WebUI ET Label soient actifs**, et sans Label il n'y a aucune catégorie, donc aucun suivi des téléchargements. C'est le même angle mort que les répertoires vides des catégories SABnzbd, et il se traite au pré-semis, pas dans une note de README. À vérifier contre une instance réelle avant d'y croire : que le connecteur *arr s'authentifie par mot de passe SEUL, sans identifiant, contrairement à Transmission et qBittorrent ; que le greffon Label s'active depuis un fichier de configuration et pas seulement depuis l'interface ; et ce que Deluge fait du port entrant, car `port_sync_clients` ne rend aujourd'hui qu'**un** client (qBittorrent prioritaire) et Deluge devra soit y entrer, soit être explicitement exclu du port entrant plutôt que de l'être par omission. |

**Readarr n'est pas au programme** : le projet est archivé depuis le 27 juin 2025.

### Distribution à étudier

- [ ] **Proxmox VE Helper-Scripts / Community Scripts** — Étudier l’ajout de PlugArr au catalogue des scripts communautaires Proxmox afin de simplifier son installation. Vérifier les critères d’admission, le mode de déploiement adapté et la maintenance du script avant toute proposition.

---

## La console PlugArr

Le seul chantier qui ne soit pas un service de plus. Aujourd'hui l'assistant
installe puis s'efface ; `plugarr serve` comble une partie du manque, mais
reste une commande à lancer.

| | État |
|---|---|
| État des services | ✅ |
| Démarrer, arrêter, redémarrer | ✅ |
| Voir et appliquer les mises à jour | ✅ |
| Lancer le diagnostic | ✅ 0.1.11 |
| Forcer la recherche de mises à jour | ✅ 0.1.11 |
| Renouveler un mot de passe, avec recâblage | ✅ |
| Renouveler une clé API, avec recâblage | ✅ |
| Ajouter un service absent de l'installation | ✅ |
| Démarrage automatique, sans lancer de commande | ✅ 0.1.9 |
| Veille dans la console : disques, débits, sortie du VPN | ✅ 0.10.0 |
| Veille en continu, en conteneur, en lecture seule | ⬜ après la console |
| Gluetun sur la page : état, redémarrage, mise à jour, changement de serveur | ⬜ à faire |
| Console traduite en anglais | ⬜ à faire |

**Gluetun manque à la page, et pas de la même façon selon la fonction.** Demandé
à l'usage. Le relevé, avant d'écrire quoi que ce soit :

- **Son état est déjà là.** `status_payload` l'ajoute quand le VPN est actif, et
  le diagnostic le sonde comme les autres. Ce qui manque, c'est la **carte** :
  `dashboard.py` construit ses cartes depuis `cfg.services`, où Gluetun n'entre
  pas. Il n'est au catalogue d'aucune façon — il n'existe que dans le document
  compose, écrit par `_gluetun_block`.
- **Le redémarrer est refusé.** `/api/action` vérifie `cfg.enabled(service)`, qui
  répond non pour Gluetun. Le bouton n'existe pas, et s'il existait il serait
  rejeté. C'est la partie la moins chère du lot.
- **Le mettre à jour n'a rien à lire.** Son tag est en dur dans `compose.py`
  (`GLUETUN_TAG = "v3.41.3"`), pas dans une `ServiceInstance.image`. Or
  `apply_update` lit précisément cette image. Il faut donc d'abord donner à
  Gluetun une image épinglée dans le modèle, sinon la console n'a aucune version
  à comparer ni à remplacer.
- **Changer de serveur ne passe pas par son API.** Son serveur de contrôle
  expose `GET/PUT /v1/vpn/status`, `GET /v1/vpn/settings`, `GET/PUT
  /v1/portforward`, `GET/PUT /v1/dns/status`, `GET/PUT /v1/updater/status` et
  `GET /v1/publicip/ip` — **aucune route ne change le pays ou le serveur**. Il
  faut réécrire l'environnement (`SERVER_COUNTRIES` et ses variantes selon le
  fournisseur) puis **recréer le conteneur**.

Et c'est là le piège à ne pas emballer joliment : recréer Gluetun emporte tout
ce qui tourne en `network_mode: service:gluetun`. Les clients protégés tombent
avec lui. « Changer de serveur » n'est donc pas un bouton anodin à côté de
« redémarrer » : c'est une interruption de tous les téléchargements, et la page
doit le dire avant, pas après.

Deux fonctions distinctes se cachent d'ailleurs derrière la demande, et les
confondre dans l'interface serait une erreur :

- **se reconnecter** — `PUT /v1/vpn/status {"status":"stopped"}` puis
  `{"status":"running"}` remonte le tunnel sans recréer le conteneur. Quand
  plusieurs localisations sont configurées, c'est le moyen de changer de serveur
  DANS la liste déjà choisie, sans toucher au compose et sans emporter les
  clients ;
- **changer de localisation** — réécriture de `stack.yml`, régénération du
  compose, recréation du conteneur. Coûteux, et à confirmer.

Deux contraintes de mise en œuvre, enfin. Le port 8000 du serveur de contrôle
**n'est jamais publié sur l'hôte**, volontairement : c'est ce qui rend le
contrôle de fuite concluant. La console devra donc l'atteindre par `exec_in`,
comme `vpncheck` le fait déjà, et non par une requête HTTP depuis l'hôte. Et
après tout changement de serveur il faut rejouer le contrôle de fuite ET la
synchronisation du port entrant : `VPN_PORT_FORWARDING_UP_COMMAND` n'est appelé
que lorsque Gluetun obtient un port, donc un client recréé entre deux
attributions garde l'ancien.

**La console vivante parle français, en dur.** `_LIVE_SCRIPT`, dans
`dashboard.py`, écrit ses libellés directement dans le JavaScript : « en
marche », « arrêté », « tout est en ordre », « N contrôle(s) en échec ». Le
HTML autour, lui, passe bien par le catalogue. Quelqu'un qui a choisi l'anglais
obtient donc une page anglaise dont les états de service et le résumé du
diagnostic restent français.

Le garde-fou ne peut pas le voir : `scripts/audit_traductions.py` relève les
appels à `t()`, et ces phrases-là n'en sont pas. C'est précisément pour ça
qu'elles ont pu s'accumuler sans que rien ne le signale — le mécanisme qui
protège tout le reste ne s'applique pas ici.

Ce n'est pas une phrase à envelopper mais un script à faire traverser le
catalogue : les libellés doivent être posés côté Python, au rendu, puis lus par
le JavaScript, sinon chaque ligne ajoutée au script reposera la question.

**Pourquoi pas un conteneur.** La question a été tranchée en la mesurant. La
console doit créer, démarrer et recréer des conteneurs — soit
`POST /containers/create` puis `/start` dans l'API Docker. Or un conteneur qu'on
crée peut monter la racine de l'hôte et tourner en root : un proxy de socket qui
autorise ces deux appels n'enferme rien, et sans eux la console ne sert plus à
rien. L'y enfermer reviendrait donc à exposer sur le réseau un service aux
pleins pouvoirs, sans rien gagner. Cela vaut pour l'ÉCRITURE ; la lecture,
elle, tient sans risque dans un conteneur — voir « Une veille en continu, dans
un conteneur » plus bas.

Elle tourne donc sur l'hôte, sous le compte de l'utilisateur, sur `127.0.0.1`,
et démarre toute seule avec `plugarr autostart`. Le confort recherché est le
même. Et parce qu'une console qui change des mots de passe doit s'authentifier
sérieusement, `plugarr admin-password` pose un mot de passe : empreinte seule
dans `stack.yml`, sessions expirables, tentatives limitées.

**Administrer une machine distante.** Demandé à l'usage. Le trou n'était pas
l'écoute — `plugarr serve --host` existait — mais le DÉMARRAGE : le lancement
automatique ne connaissait que Windows et systemd *utilisateur*, qui attend
une ouverture de session. Sur un serveur ou un LXC où personne ne se connecte,
il n'y avait rien.

- [x] `plugarr autostart --systeme` : une unité systemd SYSTÈME, qui démarre
      avec la machine. Elle tourne sous le compte qui possède `stack.yml`, pas
      sous root par commodité, et la commande refuse d'écouter hors de
      `127.0.0.1` sans mot de passe posé. Vérifié sur le banc le 2026-09-20 :
      unité installée, console jointe **depuis une autre machine** en 401 avec
      son formulaire, puis **le LXC redémarré pour de vrai** — sans aucune
      session, la console est revenue et les 9 conteneurs avec elle.
- [x] Au passage, un défaut ancien : la commande écrite dans l'unité résolvait
      le lien symbolique de l'interpréteur, ce qui fait sortir d'un
      environnement virtuel. Le service lançait `/usr/bin/python3 -m plugarr`
      et répondait « No module named plugarr », en boucle. Il touchait aussi le
      lancement automatique par session.
- [x] Conteneur d'administration, en option explicite (`--console-conteneur`,
      question dédiée dans les deux assistants). L'image gagne une **seconde
      cible** : par défaut celle de la veille, **sans aucun client Docker** —
      même avec le socket elle ne saurait pas s'en servir, et le workflow le
      vérifie — et `--target admin`, publiée sous un tag distinct, qui ajoute
      le client Docker 29.8.1 et le greffon compose 5.5.1 (dépôt apt signé,
      versions épinglées, empreinte de clé vérifiée). 263 Mo contre 393 Mo.
      Le conteneur tourne en **root** et c'est dit partout : avec le socket on
      crée un conteneur privilégié, donc lui donner un compte sans privilège
      serait du théâtre. Vérifié sur le banc le 2026-09-20, contre la vraie
      installation : console jointe en 401, connexion, état réel des 9
      services lu depuis le conteneur, puis **Lidarr redémarré à travers le
      socket**. Banc remis dans son état d'avant l'essai.
- [x] Marche à suivre écrite : `docs/ADMIN_DISTANTE.md`, trois routes, de la
      plus sûre à la plus permissive. Elle dit AUSSI ce qui n'est pas vérifié :
      ni Unraid ni Synology ne sont sur le banc, donc leurs mécanismes propres
      y figurent comme pistes sourcées, pas comme marche à suivre essayée. Sur
      ces machines, la route vérifiée reste la console en conteneur.
- [ ] Essayer la route Unraid sur un vrai Unraid : l'utilisateur en a un. Ce
      jour-là, le greffon User Scripts passe de piste sourcée à marche à suivre
      vérifiée, ou disparaît du document.

---

## Une veille en continu, dans un conteneur

Demandé à l'usage : « pour monitorer PlugArr, un conteneur toujours actif, en
temps réel », avec l'espace disque, la RAM, le CPU, le GPU et la bande passante
sur la page.

**Prévu pour la 0.10.0.** Le premier point à trancher est le périmètre : un
conteneur exige d'abord une image publiée, alors que le niveau 1 tient sans
elle dans la console, sur l'hôte. Le premier sert les NAS où personne n'ouvre
de session, le second ne demande aucune image.

**Surveiller n'est pas administrer, et c'est toute la différence.** Le refus
ci-dessus porte sur l'écriture : créer, démarrer, recréer. La lecture ne demande
aucun de ces droits, et peut donc, elle, tenir dans un conteneur. La console
garde ses boutons sur l'hôte ; la veille serait un second service, en lecture
seule, incapable d'arrêter quoi que ce soit.

**Ce que le conteneur apporte vraiment.** Pas « toujours actif » : `plugarr
autostart` lance déjà la console à chaque ouverture de session, et la page se
rafraîchit toutes les 5 secondes (`dashboard.py`, `setInterval(rafraichir,
5000)`). Le gain est ailleurs, et il est réel : `mecanisme()` ne connaît que
Windows et systemd utilisateur, et renvoie « aucun » partout ailleurs. Sur un NAS
où personne n'ouvre de session — Unraid, Synology, un BSD — il n'y a aujourd'hui
rien du tout. Un conteneur en `restart: unless-stopped` survit au redémarrage
sans session, et se consulte depuis un téléphone.

### Les mesures demandées, une par une

Relevés du 12 septembre 2026, sur Docker Desktop 29.7.2 (Windows, moteur Linux).
Linux natif est le cas normal et reste à remesurer sur le banc.

- **L'espace disque : oui, et exact.** `df` sur un montage lié rend les chiffres
  du disque hôte, pas ceux de l'image : `C:\ 952,2G, 326,7G disponibles` vu
  depuis le conteneur, contre 326,7 Go libres rapportés par Windows au même
  instant. Il faut monter en lecture seule chaque racine surveillée ; PlugArr les
  connaît déjà (`layout.py` : torrents, usenet, médiathèque, configuration).
  Plusieurs disques veulent plusieurs montages, rien ne se devine de l'intérieur.
- **La RAM : le chiffre serait faux sous Windows.** `/proc/meminfo` n'est pas
  cloisonné, donc un conteneur y lit les valeurs de l'hôte — sur Linux. Sur
  Docker Desktop, cet hôte est la machine virtuelle WSL2 : 15,2 Gio mesurés dans
  le conteneur contre 31,1 Gio sur la machine, soit la moitié. À afficher sur
  Linux, à taire ou à annoncer comme tel ailleurs.
- **Le CPU : le nombre est juste, le taux ne l'est qu'à moitié.** `nproc` rend 24
  dans le conteneur, exactement les 24 processeurs logiques de la machine. Mais
  l'occupation lue dans `/proc/stat` est celle de la VM sous Docker Desktop :
  elle ignore ce que Windows fait en dehors.
- **Par service, sans socket : possible, à un détail près.** En montant
  `/sys/fs/cgroup` en lecture seule, un conteneur non privilégié lit
  `docker/<id>/memory.current` et `cpu.stat` de TOUS les conteneurs — vérifié.
  Ce que le cgroup ne donne pas, c'est le nom : il n'y a que des identifiants, et
  les relier aux services demande soit le socket, soit un fichier de
  correspondance écrit par l'hôte, qui vieillit à chaque recréation. C'est
  l'argument le plus solide en faveur du niveau 2 : `docker stats` rend le nom
  d'emblée.
- **La bande passante : pas là où on la cherche.** `/proc/net/dev`, lui, EST
  cloisonné par espace réseau. En réseau bridge, le conteneur ne voit que `lo` et
  son propre `eth0` — vérifié. En `network_mode: host` il voit l'`eth0` de l'hôte
  et tous les `veth`, donc le total machine ; mais il sort alors du réseau du
  stack, et un `veth` ne dit pas à quel conteneur il appartient : même problème
  de correspondance. La bande passante utile ici est ailleurs — les clients la
  publient eux-mêmes, et PlugArr leur parle déjà. Routes à confirmer contre une
  instance réelle avant d'y croire : `/api/v2/transfer/info` chez qBittorrent,
  `session-stats` chez Transmission, la file chez SABnzbd.
- **Le GPU : trois implémentations, aucune portable, et rien à mesurer
  aujourd'hui.** NVIDIA exige `nvidia-container-toolkit` sur l'hôte et une
  réservation de périphérique, puis NVML dans le conteneur. AMD est le moins
  cher : `gpu_busy_percent` dans sysfs, un fichier à lire. Intel est le plus dur,
  l'occupation passant par le PMU `i915`, donc `CAP_PERFMON` ; sysfs ne donne que
  la fréquence. Sous Docker Desktop, rien. Surtout : **PlugArr ne configure aucun
  accès GPU** — `compose.py` n'expose que `/dev/net/tun`, pour Gluetun. Mesurer un
  matériel que le stack n'utilise pas, ce serait poser la jauge avant le moteur.
  Le transcodage matériel de Jellyfin vient d'abord, sa mesure ensuite.

### Le coût d'entrée, qui n'est pas dans la page

**Il n'existe aucune image PlugArr.** Le paquet s'installe par
`pipx install git+https://…`, il n'est pas sur PyPI, et `packaging/` ne produit
qu'un exécutable PyInstaller. Une veille en conteneur veut donc d'abord une image
publiée, construite par la CI, en deux architectures — `amd64` et `arm64`, sans
quoi les NAS ARM restent dehors — et épinglée comme tout le reste. C'est le
premier poste de dépense, avant la moindre ligne de veille.

L'autre voie est de n'écrire aucune veille : entrer au catalogue un outil qui
existe et le câbler, ce qui est le métier de PlugArr. À vérifier avant de s'y
engager : Uptime Kuma n'expose pas d'API REST documentée pour créer des sondes,
donc le câblage passerait par socket.io ou par l'écriture directe de son SQLite,
deux voies fragiles. Dozzle, lui, lit les journaux et demande le socket.

### Ce qu'il reste à faire

- [x] Trancher le périmètre de la 0.10.0 : le niveau 1 d'abord, dans la
      console, sur l'hôte. Le conteneur suit, avec l'image.
- [x] Construire une image `plugarr` multi-architecture, épinglée
      (`Dockerfile`, `.github/workflows/docker.yml`) : base Python par tag et
      condensat, compte sans privilège, amd64 et arm64 construits à chaque
      poussée, essai de démarrage avant tout. Publication sur
      `ghcr.io/yannickuhrig1/plugarr` au premier tag de version, jamais en
      `latest`. Essayée sur le banc : 262 Mo, démarre, rapporte sa version.
- [x] Une commande `plugarr veille` servant une page en LECTURE SEULE
      (`veille_serveur.py`) : aucune route qui modifie quoi que ce soit, seul
      bouton « Se déconnecter ». `--interne` dans un conteneur de la pile : les
      services par leur nom sur le réseau Docker, Gluetun par HTTP, **sans
      socket Docker**. L'état des services se lit par leur propre adresse
      (toute réponse sous 500 prouve qu'il tourne). Essayée sur le banc dans
      l'image, réseau `plugarr_plugarr`, racines montées en lecture seule : 9
      services, 3 débits et le disque relevés.
- [x] Niveau 1, sans socket, dans la console (`veille.py`, `/api/veille`) :
      état des services (déjà là), sortie du VPN par le serveur de contrôle de
      Gluetun, place libre par disque, débits par les clients de
      téléchargement. Sortie du VPN relevée sur un vrai tunnel ProtonVPN. Reste
      à monter les racines en lecture seule le jour où la veille passera en
      conteneur.
- [x] Niveau 2 sur l'HÔTE, par la ligne de commande Docker (`runner.py`,
      `veille.conteneurs`) : processeur, mémoire, compteur de redémarrages,
      kill OOM, code de sortie et santé, par conteneur. Des CHAMPS choisis,
      jamais `docker inspect` entier : il rend les variables d'environnement
      RÉSOLUES — vérifié — donc la clé privée WireGuard, les clés API et les
      mots de passe que `.env` est censé garder. Relevé sur le banc le
      2026-09-20 : 9 conteneurs, 2,1 s par lecture (`docker stats` prend deux
      mesures espacées), d'où un cache de 10 s pour une page rafraîchie toutes
      les 5 s. Tableau vérifié dans un vrai navigateur, console et page
      autonome.
- [ ] Niveau 2 dans un CONTENEUR : socket en lecture seule derrière un proxy
      (POST refusé), en option explicite, pour la veille qui tourne dans la
      pile. Sans lui, elle reste sans socket et la section disparaît au lieu de
      mentir. Attend que la veille soit branchée dans le compose.
- [ ] Journaux des conteneurs dans la veille : à peser à part, un journal peut
      porter des identifiants (Gluetun écrit sa configuration au démarrage).
- [x] N'exposer la veille qu'authentifiée : même mot de passe que la console
      (`adminauth`), mêmes sessions limitées. Sans mot de passe, elle refuse
      d'écouter ailleurs que sur 127.0.0.1 (vérifié dans le conteneur).
- [x] Poser un fichier d'authentification pour le serveur de contrôle de
      Gluetun (`gluetun_auth.py`). Mesuré sur v3.41.3 : `GET /v1/publicip/ip`
      répondait encore sans authentification, mais Gluetun prévenait à chaque
      appel que la route deviendrait protégée, et sa documentation les dit
      toutes privées. PlugArr pose un rôle à clé d'API sur les deux routes qu'il
      lit (adresse publique, port entrant) dans `CONFIG_ROOT/gluetun/auth/`,
      déjà monté : aucun changement de compose. Le fichier appartient à
      PUID:PGID pour que la veille le lise ; ce qui tourne dans Gluetun y relit
      la clé sur place. L'essai de tunnel jetable reçoit sa propre clé. Essayé
      sur le banc : 401 sans clé, 200 pour la veille (hôte et conteneur) et le
      port entrant.
- [x] La veille est dans le compose (`veille_config.py`, `compose._veille_block`).
      `stack.yml` est en 600 pour le compte qui installe : la veille, sous
      PUID:PGID, ne pouvait pas le lire (`PermissionError` constatée sur le banc
      le 2026-09-20, en lançant l'image publiée). Plutôt que d'ouvrir ce fichier
      ou de faire tourner ce conteneur en root, PlugArr écrit une configuration
      **réduite** dans `CONFIG_ROOT/veille/`, qui lui appartient : ni clé privée
      WireGuard, ni identifiants OpenVPN, ni clés API des services dont la
      veille ne lit que l'état. Le service dit ses limites : `user: PUID:PGID`,
      montages et racine en lecture seule, `no-new-privileges`, aucun socket,
      image épinglée par tag et condensat. Vérifié sur le banc contre la vraie
      installation : page 200, 401 sans session, 9 services sur 9, les trois
      clients lus par le réseau de la pile, un disque, et zéro conteneur, faute
      de socket. Au passage, la protection de version a fait son travail :
      l'image de la première avant-première lisait `stack.yml` jusqu'à la 4 et a
      refusé la 5, d'où une seconde image.
- [x] Entrée dans l'assistant : la question et le port dans l'assistant web et
      dans le TUI, `--veille/--sans-veille` et `--veille-port` en ligne de
      commande, la ligne au récapitulatif des deux, et la reprise à la
      réinstallation. Chaîne vérifiée dans un vrai navigateur, en pilotant
      Chrome : la case cochée et le port saisi arrivent au récapitulatif. Le
      choix des racines à surveiller reste à faire : aujourd'hui, ce sont celles
      de l'installation.
- [x] Rafraîchissement tranché : **5 secondes, en interrogeant**, pas de flux
      SSE. Mesuré sur le banc le 2026-09-20 : une réponse fait 3,3 Ko, et le
      relevé coûte 0,3 s quand les conteneurs sont en cache, 2,1 s sinon — dont
      presque tout en attente, `docker stats` ne consommant que 30 ms de
      processeur par appel (mesure `times`, 10 appels en 0,31 s). Un flux SSE
      n'économiserait donc pas de calcul : derrière, il faudrait interroger les
      mêmes API, qui ne poussent rien. Le seul vrai temps réel côté Docker
      reste `/events`, et il exige le socket. Ce qui a été corrigé, en
      revanche : un relevé peut durer plus que l'intervalle, et la page en
      lançait un second par-dessus. Le serveur accepte bien les appels
      simultanés (mesuré : 3 à la fois), donc c'est à la page d'attendre la fin
      du relevé en cours ; console et page autonome le font désormais.
- [ ] Tout remesurer sur Linux natif : les relevés ci-dessus viennent de Docker
      Desktop.

---

## Choisir le client de téléchargement

Demandé à l'usage : « lorsqu'on met plusieurs logiciels de téléchargement,
demander vers lequel on crée le lien ».

PlugArr ne demandait rien, et ce n'était pas neutre. Le plan de câblage
déclarait **chaque** client dans **chaque** *arr, tous avec `priority: 1`. Or la
documentation de Sonarr est explicite : « Round-Robin is used for clients of the
same type (torrent/usenet) that have the same priority ». Deux clients torrent
installés, et les épisodes partaient donc **alternativement** dans l'un et dans
l'autre. Personne ne l'avait demandé, et rien ne le disait.

Le cas se présente précisément quand quelqu'un installe qBittorrent pour son
interface `qui` ou Flood tout en gardant Transmission, ou l'inverse : il a un
client principal en tête, et PlugArr en fabrique deux à égalité.

**Livré en 0.9.0.** Vérifié en CI sur un vrai Sonarr,
après le second passage de câblage : qBittorrent à 1, Transmission à 2.

Où en est chaque point :

- [x] Demander le client **préféré** dans l'assistant, seulement quand plusieurs
      clients du même protocole sont cochés. Une question qui ne se pose que
      lorsqu'elle a un sens.
- [x] Le traduire en priorités plutôt qu'en suppressions : le client choisi passe
      à `priority: 1`, les autres descendent. Ils restent déclarés et
      fonctionnels, ce qui préserve le repli et n'efface rien d'une installation
      existante.
- [ ] Poser la même question pour l'Usenet dès que Deluge ou un second client
      Usenet entrera : le round-robin ne joue qu'entre clients de même protocole,
      donc SABnzbd à côté de qBittorrent ne pose pas ce problème. La règle
      regroupe déjà par protocole : il suffira d'inscrire le nouveau client dans
      `downloadclients.ORDRE_AUTO`. Reste ouvert tant qu'aucun second client
      Usenet n'existe pour le vérifier.
- [ ] Étudier l'affectation **par indexeur**, que Prowlarr et les *arr offrent en
      option avancée (« Download Client - Select and specify which download
      client is used for grabs from this indexer »). C'est plus fin que le choix
      global, et c'est la seule voie officielle pour router par source.

**Une précision sur la demande.** Seerr n'entre pas dans ce choix : il ne
connaît aucun client de téléchargement. Il déclare Sonarr et Radarr, et c'est
eux qui téléchargent. Le réglage porte donc sur les *arr et sur Prowlarr, et le
poser ailleurs n'aurait rien à régler.

---

## Personnalisation des interfaces

Demandé à l'usage : pouvoir remplacer l'interface web d'un service, ou lui poser
un thème, sans sortir de PlugArr.

**Livré pour la 0.10.0 : VueTorrent sur qBittorrent.** theme.park n'est pas
proposé : mesuré ci-dessous, il retélécharge les sources de qBittorrent depuis
GitHub à chaque création du conteneur, disparaît au premier redémarrage sans
Internet même avec le cache, et fait charger ses feuilles de style depuis
`theme-park.dev` à chaque page. Les autres services ne suivront que si un mod
tient ces conditions.

Deux mécanismes, tous deux portés par les mods linuxserver.io — donc limités aux
images `lscr.io/...` du catalogue. Gluetun, Recyclarr, Seerr et Silo n'en sont
pas et resteront à l'écart.

| | Ce qu'il reste à faire |
|---|---|
| **VueTorrent** | Interface de remplacement pour qBittorrent, **v2.35.0** (24/08/2026). Mod relevé : `ghcr.io/vuetorrent/vuetorrent-lsio-mod:latest`, qui ne fonctionne **qu'avec** `lscr.io/linuxserver/qbittorrent`. Le mod ne suffit pas : deux réglages doivent suivre DANS qBittorrent, `WebUI\AlternativeUIEnabled=true` et `WebUI\RootFolder=/vuetorrent`. Bonne nouvelle, c'est exactement la forme que le pré-semis écrit déjà dans `qBittorrent.conf` — ça se pose donc là, et pas à la main après coup. |
| **theme.park** | Thèmes pour les interfaces existantes, sans les remplacer. Mod relevé : `ghcr.io/themepark-dev/theme.park:<app>`, réglé par `TP_THEME` et, au besoin, `TP_DOMAIN`, `TP_SCHEME`, `TP_ADDON`, `TP_COMMUNITY_THEME`. Couvre Sonarr, Radarr, Lidarr, Prowlarr, Bazarr, Jellyfin, qBittorrent, Deluge et SABnzbd, entre autres — un mod par application, donc une valeur par service et non un réglage global. |

**Ce que ça coûte, et c'est le point à trancher avant d'écrire une ligne.** Un
mod est une archive téléchargée et extraite **au démarrage du conteneur**, avant
son init. Trois conséquences, aucune anodine :

- `DOCKER_MODS` vise `:latest`. Tout le catalogue est épinglé par tag, et Silo
  par condensat, précisément pour qu'une installation soit reproductible. Un mod
  en `latest` rouvre la porte qu'on a fermée : deux démarrages du même compose
  peuvent ne pas donner la même interface, et une régression du mod arrive sans
  qu'on ait rien changé ;
- le démarrage réclame alors le réseau. Un conteneur qui redémarre sans accès à
  GitHub perd son thème, ou échoue, selon le mod. Une pile média doit pouvoir
  redémarrer hors ligne ;
- plusieurs mods sur un même service se séparent par `|` dans une seule
  variable. VueTorrent et theme.park sur qBittorrent, c'est donc `mod1|mod2`
  dans `DOCKER_MODS`, et il faudra vérifier ce que font deux mods qui touchent
  la même interface.

La voie honnête est probablement d'épingler le mod par tag comme le reste, de le
proposer en option explicite plutôt que par défaut, et d'écrire dans l'assistant
ce que ça implique. Pas de l'activer en silence pour que ce soit joli.

### Mesuré le 19 septembre 2026

Sur un qBittorrent 5.2.3 jetable du banc, `lscr.io/linuxserver/qbittorrent`,
avec un réseau Docker interne pour simuler l'absence d'Internet.

- **Épinglage : possible pour les deux.** Le chargeur de mods de linuxserver
  (`docker-mods.v3`) accepte `dépôt:tag@sha256:…` et télécharge alors cette
  version précise. VueTorrent publie des tags versionnés (`2.35.0`), theme.park
  seulement des tags flottants par application (`qbittorrent`) : pour lui, seul
  le condensat fige la version. Vérifié : `vuetorrent-lsio-mod:2.35.0@sha256:f644…`
  est téléchargé, installé, et qBittorrent sert VueTorrent.
- **Sans Internet, qBittorrent ne casse pas, mais perd VueTorrent pour de bon.**
  Conteneur recréé hors ligne : le mod est sauté (« not found in modcache,
  skipping »), qBittorrent sert son interface d'origine, et **réécrit
  `WebUI\AlternativeUIEnabled=false`** faute de trouver `/vuetorrent`. Le réseau
  revenu, le mod est de nouveau là mais l'interface reste celle d'origine : une
  seule coupure suffit.
- **Parade mesurée : monter `/modcache` en volume.** Le chargeur y garde
  l'archive du mod ; recréé hors ligne, le conteneur l'applique depuis ce cache
  (« OFFLINE: … found in modcache ») et VueTorrent reste affiché, réglage intact.
- **VueTorrent et theme.park s'excluent.** Ensemble sur une configuration propre,
  qBittorrent sert son interface d'origine, thémée : theme.park l'emporte. C'est
  l'un **ou** l'autre, pas les deux.
- **Pourquoi theme.park l'emporte.** Son script réécrit à chaque démarrage
  `WebUI\AlternativeUIEnabled=true` et `WebUI\RootFolder=/themepark`, après une
  copie `qBittorrent.conf.bak` faite une seule fois. Il n'embarque pas
  d'interface : il **clone à chaque création du conteneur les sources de
  qBittorrent depuis GitHub** (branche `release-<version>`, version lue dans
  l'index d'Alpine edge, pas dans l'image) et y ajoute deux feuilles de style
  chargées par le navigateur depuis `theme-park.dev` à chaque page.
- **Sans Internet, theme.park est perdu même avec `/modcache`.** Le mod est bien
  repris du cache, mais le clonage échoue : `/themepark` n'existe pas,
  qBittorrent sert son interface d'origine et réécrit
  `WebUI\AlternativeUIEnabled=false`. Le cache ne protège que VueTorrent.
- **Retirer theme.park rend l'interface d'origine.** Relancé sans le mod,
  qBittorrent passe lui-même `AlternativeUIEnabled` à `false`. Restent
  `WebUI\RootFolder=/themepark`, inerte, et `qBittorrent.conf.bak`.

### Ce qu'il reste à faire pour la 0.10.0

- [x] Trouver une version épinglable de chaque mod : par condensat pour les
      deux, et par tag versionné en plus pour VueTorrent.
- [x] Mesurer ce que devient qBittorrent quand il redémarre sans accès à
      GitHub : voir ci-dessus. Règle retenue : `/modcache` en volume sous
      `CONFIG_ROOT`, pour que VueTorrent survive à un redémarrage hors ligne
      (theme.park n'y survit pas, voir ci-dessus).
- [x] Vérifier VueTorrent et theme.park ensemble : ils s'excluent, l'assistant
      proposera l'un ou l'autre.
- [x] Relever ce que theme.park change dans `qBittorrent.conf` pour l'emporter,
      et si le retrait du mod rend l'interface d'origine : oui, voir ci-dessus.
- [x] Poser `WebUI\AlternativeUIEnabled` et `WebUI\RootFolder` au pré-semis de
      `qBittorrent.conf`. Une installation qui abandonne VueTorrent repasse
      `AlternativeUIEnabled` à `false` ; une interface posée à la main n'est
      pas touchée.
- [x] Le proposer dans l'assistant web et le TUI, en option explicite, avec ce
      que ça implique écrit à l'écran, et `--qbittorrent-ui` en ligne de
      commande. VueTorrent seul : theme.park est écarté, voir plus haut.

---

## Ce qu'on ne fera pas

**Choisir plusieurs profils Recyclarr par service.** Recyclarr groupe ses
instances par `base_url` et **écarte tout groupe qui en compte plus d'une** —
c'est `SplitInstancesFilter`, lu dans son code source. Deux profils visant le
même Sonarr, et ce ne sont pas deux profils posés : c'est **zéro**. Les
templates racine sont autonomes et ne se composent pas ; la seule voie serait de
fusionner leur YAML nous-mêmes, exactement ce que le projet refuse — tout
l'intérêt est que le contenu vienne des TRaSH Guides et pas de nous.

PlugArr détecte désormais cette situation et n'en garde qu'un, en renommant les
autres plutôt qu'en les effaçant.

---

## Journal des corrections notables

| Version | |
|---|---|
| **0.9.0** | **Le préflight gelait plus de dix minutes sur le chemin proposé par défaut.** `check_writable` sondait par `tempfile.NamedTemporaryFile`, qui sous Windows rattrape `PermissionError` et recommence jusqu'à dix mille fois dès qu'`os.access` répond oui — ce qu'il fait à tort pour `C:\`. Or `C:/plugarr/data` a la racine du disque pour premier ancêtre existant à la toute première installation. Rendu immédiat, le sondage refusait ensuite ce même chemin : un compte standard ne peut pas créer un **fichier** à la racine, mais crée très bien le **dossier**. Le contrôle reproduit maintenant la vraie suite d'opérations. **Trouvé parce que la suite de tests elle-même ne rendait plus la main.** |
| **0.9.0** | **La console se figeait pendant une sauvegarde.** `do_GET` et `do_POST` s'exécutaient sous le verrou que `backup()` gardait pendant tout l'archivage. Deux verrous désormais : l'état par prises courtes, les opérations longues à part. Mesuré sur une vraie pile : `/api/status` en 574 ms contre 9 935 ms pendant une sauvegarde de 49,8 Mo. |
| **0.9.0** | **Chaque sauvegarde déclenchait six fausses alertes.** Une sauvegarde à froid arrête la pile ; le sondage d'état voyait les conteneurs arrêtés et criait « indisponible » sur l'opération que la console venait de lancer. Six alertes et douze événements par sauvegarde, contre zéro. |
| **0.9.0** | **Deux clients torrent se partageaient les téléchargements en alternance.** Tous étaient déclarés à `priority: 1`, et Sonarr applique alors un round-robin. Le client préféré passe à 1, les autres restent en secours ; un réglage manuel n'est jamais écrasé. Vérifié en CI sur un vrai Sonarr. |
| **0.9.0** | **Un port publié deux fois par la pile passait le préflight.** Le contrôle sondait l'hôte, où personne n'écoute encore. Reproduit en ajoutant Jellyfin à une pile Silo : l'assistant web restaurait le 8096 de Silo par-dessus le décalage déjà calculé. |
| **0.9.0** | **Un refus de requête arrivait comme une coupure réseau.** Les serveurs locaux répondaient sans lire le corps, et Windows coupait la connexion : « [WinError 10053] » au lieu du 400, « Failed to fetch » dans le navigateur. **Trouvé en cherchant pourquoi la suite échouait une fois sur trois**, sur un test différent à chaque fois. |
| **0.8.0** | **Un port entrant désynchronisé était constaté et jamais corrigé.** `doctor` disait « le VPN a ouvert 48406, le client écoute 45270 », et l'utilisateur restait avec le problème et sans le remède. Le cas existe parce que la pose est un **événement** : Gluetun appelle `VPN_PORT_FORWARDING_UP_COMMAND` au moment où il obtient un port — vérifié le 2026-09-10, appel une seconde après l'attribution. Un client recréé **entre deux attributions** ne reçoit donc aucun appel. `doctor` rejoue maintenant le script que Gluetun lance lui-même — pas une seconde pose, qui finirait par diverger — puis **relit** avant de conclure. Idée reprise de la [proposition de brumatheus](https://github.com/yannickuhrig1/plugarr/issues/1), dont la sonde périodique couvrait ce cas. |
| **0.8.0** | **Un fournisseur VPN mal tapé faisait planter l'exécutable.** `--vpn-provider zorglub` remontait une `ValidationError` nue : traceback pydantic, lien vers `errors.pydantic.dev`, et une dernière ligne « Failed to execute script 'launcher' » qui annonce un plantage à quelqu'un qui a simplement fait une faute de frappe. La phrase utile était pourtant déjà écrite par le validateur — « fournisseur VPN inconnu de Gluetun … Choix possibles : … » — elle était seulement noyée. **Trouvé en éprouvant l'exécutable de la 0.8.0 avant de la publier**, pas en relisant le code. |
| **0.8.0** | **Les captures dépendaient du poste qui les produit.** L'assistant cherche une installation précédente, dans le répertoire de lancement et dans le registre de l'utilisateur : le récapitulatif généré ici affichait donc le chemin local d'une vraie installation — parti tel quel dans un SVG publié — et la reprise en tirait aussi son fuseau horaire. La CI, qui regénère les captures et les compare à celles du dépôt, ne pouvait pas coïncider. `freeze_environment()` neutralise désormais cette recherche, et un test refuse toute capture portant la trace de la machine qui l'a faite. Vérifié : Windows et Linux rendent des fichiers identiques à l'octet. |
| **0.8.0** | **Un client de téléchargement adopté était déclaré protégé sans qu'on ait rien vérifié.** Le contrôle cherchait `{projet}-{service}` ; un conteneur adopté garde le sien. Il ne trouvait donc rien, `network_mode` rendait `None`, et `None` veut dire « conteneur arrêté » — c'est-à-dire un contrôle **vert** sur un client qui tourne hors du tunnel. Aucun chemin ne produit cette combinaison aujourd'hui : `adopt` n'écrit jamais de VPN et `reprise` ne reporte ni `adopted` ni `container`. Mais `stack.yml` se lit et s'édite, et un verdict de protection ne doit pas dépendre de ce qu'aucun chemin ne l'atteigne. Le remède affiché diffère aussi désormais : « régénérez la pile » n'avance à rien pour un conteneur dont `adopt` ne génère volontairement aucun compose. |
| **0.8.0** | **La console comptait un port désynchronisé comme une protection perdue.** L'installation sépare depuis toujours ses deux verdicts — un port désynchronisé coûte du partage, pas de l'exposition — mais `/api/doctor` additionnait tout dans un seul « N contrôle(s) en échec ». Lire ça à côté d'un tunnel tombé fait craindre une fuite là où il n'y en a aucune. Les deux totaux sont maintenant distincts, et le rapport écrit `PORT` plutôt que `ECHEC` sur ces lignes-là. |
| **0.7.3** | **L'historique de `stack.yml` etait trop court d'un facteur quatre.** Cinq versions semblaient couvrir « une serie de relances rapprochees » ; une installation reelle de cinq services en a consomme QUATRE a elle seule. `write_artifacts` est appele trois fois par `install` — avant le pre-semis, apres l'adoption des cles API, apres le cablage — puis une fois de plus par `wire`. A cinq entrees, deux installations ratees de suite chassaient le mot de passe qui fonctionnait, c'est-a-dire exactement ce que cet historique existe pour empecher. Porte a douze, soit trois installations completes. Le test verrouille le rapport entre les deux. |
| **0.7.3** | **L'avertissement sur les mots de passe haches se contredisait deux lignes plus bas.** PlugArr annoncait « Identifiants conserves : jellyfin, qbittorrent », puis « leurs mots de passe ne se relisent pas : ceux qu'il va annoncer seront refuses ». Les deux ne peuvent pas etre vrais, et le second proposait d'EFFACER la configuration de services qui marchaient — une perte seche pour reparer un probleme inexistant. Le controle ne regarde plus que les services dont les identifiants n'ont PAS ete repris. Trouve en lancant une reinstallation reelle sur une pile de cinq services, dans un LXC Proxmox. |
| **0.7.3** | Un test de langue rendait un verdict different selon la machine. `test_la_langue_par_defaut_vient_du_systeme` remplacait les variables d'environnement mais laissait `locale.getlocale()` repondre ce qu'il voulait : le cas `de_DE` passait sur un poste francais et echouait sur un poste anglais. La CI ne le voyait pas, sa locale etant vide. La locale de la machine est desormais simulee comme le reste, et deux cas de plus disent ce qu'on attend d'un systeme anglais et d'un systeme francais. |
| **0.7.3** | L'avertissement « --vpn sans client de telechargement » vivait sous `if reprendre:` et non sous `if vpn:`. Il sortait donc a CHAQUE reinstallation sans client de telechargement, en parlant d'une option que personne n'avait passee — et restait muet dans le seul cas ou il sert, puisque `--repartir-de-zero` sautait le bloc entier. **Trouve en lancant l'executable produit**, pas en relisant le code. Le test porte sur la structure de la fonction, pas sur le texte du message. |
| **0.7.3** | **PlugArr detruisait le seul exemplaire en clair de ses propres mots de passe.** Constate sur une machine reelle : compte Jellyfin cree le 4 septembre, `stack.yml` reecrit les jours suivants, et plus aucun moyen d'entrer dans Jellyfin. Jellyfin, autobrr et qui ne gardent leur mot de passe que HACHE — ni relisible, ni reinitialisable sans lui. Il n'existait donc qu'a un endroit, et `write_artifacts` l'ecrasait **trois fois par installation**, dont une avant meme le `docker compose up` : une installation qui echouait emportait le mot de passe qui, lui, fonctionnait. `stack.yml` tourne desormais sur cinq versions, et le cablage ESSAIE les mots de passe des installations passees avant de declarer un refus. |
| **0.7.3** | **`stack.yml` n'etait cherche que dans le repertoire courant.** Quelqu'un qui lance `plugarr.exe` depuis son bureau apres l'avoir lance depuis `Telechargements` repartait de zero, sans un mot, avec des mots de passe neufs que ses services refusaient ensuite. Le message d'erreur renvoyait vers `--project-dir` — une option en ligne de commande, inutilisable pour qui n'ouvre jamais de terminal. Un registre par utilisateur, qui ne porte QUE des chemins, retrouve l'installation d'origine ou qu'elle soit ; l'assistant dit ou il l'a trouvee et y ecrit ses fichiers, parce qu'une pile Docker ne peut pas vivre dans deux repertoires a la fois. |
| **0.7.3** | **L'assistant savait restaurer, pas sauvegarder.** `plugarr backup` et la console d'administration archivaient depuis longtemps ; l'assistant, non. Or c'est lui, et lui seul, que voit quelqu'un qui double-clique un executable : il n'avait donc de sauvegarde que s'il en avait deja une. Le bouton est sur le premier ecran, a cote de « Restaurer », et l'installation a archiver est trouvee seule. Les conteneurs sont arretes par defaut : une base SQLite copiee a chaud est corrompue sans le dire. |
| **0.7.2** | **macOS n'avait aucun profil, et heritait de `/srv/data` — que macOS REFUSE de creer.** Signale par un utilisateur sur r/FrancePirate, capture a l'appui : `[Errno 30] Read-only file system: '/srv'`. Depuis Catalina la racine de macOS est un volume systeme signe, monte en lecture seule. `default_profile()` ne connaissait que `win32` et « tout le reste » : **tout** utilisateur Mac se prenait le mur au premier lancement. Le profil `macos` pose ses chemins sous le dossier personnel — seul endroit a la fois inscriptible ET partage par defaut par Docker Desktop. `/opt` aurait ete pire que `/srv` : inscriptible, donc `mkdir` passe, mais pas partage — l'echec ne serait apparu qu'au `compose up`. |
| **0.7.2** | **Le preflight ne verifiait NULLE PART qu'on peut ecrire.** Il ne testait que les hardlinks, en non bloquant : une condition fatale sortait en avertissement jaune, sur une ligne qui parle d'autre chose, l'installation partait quand meme et mourait sur sa premiere ecriture avec un errno nu. Rien dans `OSError : [Errno 30]` ne dit quoi changer. `check_writable` est **bloquant**, porte sur les deux racines, essaie reellement d'ecrire plutot que de croire `os.access`, et nomme le remede. Reproduit avant correction sur un tmpfs monte en lecture seule. |
| **0.7.2** | `--dry-run` annoncait « rien n'a encore ete ecrit » et **ecrivait quand meme**. Trouve en verifiant le correctif precedent. Le controle des hardlinks ne devine pas, il essaie — mais essayer demande deux vrais dossiers, et il les laissait derriere lui avec toute leur chaine de parents. Or `--dry-run` est PRECISEMENT la commande qu'on lance pour regarder sans s'engager : comparer trois emplacements en laissait trois, et une faute de frappe creait une arborescence a l'endroit de la faute. Le menage ne retire que ce que le test a cree, et seulement si c'est reste vide. |
| **0.7.2** | Un `t()` manquait dans `hardlink_supported`, et lui seul de ses trois sorties : la capture de l'utilisateur montrait un tableau anglais avec **une** ligne en francais. L'audit des traductions ne pouvait pas le voir — il releve les `t("...")` presents, jamais un absent. Un test le voit desormais. |
| **0.7.1** | **PlugArr ne savait pas qu'une version plus recente de LUI-MEME existait.** Signale a l'usage : « je viens de lancer la 0.6 et elle ne detecte pas la 0.7 ». C'etait juste, et le trou etait beant : la 0.6.0 a livre `plugarr upgrade`, qui aligne les IMAGES des services sur le catalogue **du binaire en cours** — elle supposait donc qu'on avait deja telecharge le dernier, et rien nulle part ne le disait. `__version__` n'etait qu'affiche. `upgrade`, `doctor` et le bouton « chercher les mises a jour » de la console interrogent desormais la derniere release, en **une** requete. |
| **0.7.1** | **La verification est un CONFORT, et se comporte comme tel.** Elle ne leve jamais : PlugArr marche parfaitement hors ligne, et un NAS derriere un pare-feu ne doit pas voir une erreur parce qu'il ne joint pas GitHub. Nuance qui compte : un echec rend « on ne sait pas », **jamais** « pas de mise a jour » — les confondre laisserait quelqu'un sur une version perimee en croyant etre a jour. Le quota horaire epuise a son propre message. |
| **0.7.1** | Le message annoncait « vous avez la 0.7.0 » a quelqu'un en 0.6.0 : `cli` et `autoupdate` lisaient chacun leur propre `__version__`. Le resultat porte maintenant la version a laquelle la comparaison a ete faite, et c'est elle qu'on affiche. **Trouve en lisant le message produit**, pas en relisant le code. |
| **0.7.0** | **Reinstaller par-dessus une installation existante ne perd plus tout.** Demande a l'usage — « il faudrait proposer de garder les parametres deja existants ». C'etait pire que « pas propose » : `install` construisait sa configuration de zero et **ne lisait jamais le `stack.yml` present**. Mesure : identifiant `yannick` -> `plugarr`, profils Recyclarr vides, mot de passe de console perdu, et surtout **VPN desactive en silence** — l'installation affichait meme « Aucun VPN n'est configure ». Quelqu'un qui reinstalle pour reparer autre chose se retrouvait avec son trafic torrent en clair. |
| **0.7.0** | **La reprise repare un defaut bien plus ancien.** qBittorrent, Jellyfin, autobrr et les autres ne stockent leur mot de passe que HACHE : PlugArr ne pouvait pas le relire, en generait un nouveau, l'annoncait, et le service le refusait — c'est la panne aux messages incomprehensibles de la 0.1.11. Mais quand c'est PlugArr qui a installe, le mot de passe est dans SON `stack.yml`, et il n'a jamais eu besoin de le relire ailleurs. Reprendre les identifiants precedents fait donc coincider ce qui est annonce et ce qui est en place. Les ports decales a la main suivent aussi. |
| **0.7.0** | Reprise **active par defaut** — perdre un VPN en silence est pire que reprendre sans demander — mais jamais silencieuse : le recapitulatif liste ce qui a ete repris, service par service, et un choix « Repartir de zero » le refuse. Une option donnee a la main prime toujours sur l'heritage, sinon elle serait sans effet. `--repartir-de-zero` en ligne de commande. |
| **0.7.0** | **Un troisieme piege d'heritage d'exceptions**, apres `BadZipFile` en 0.5.2 : `yaml.YAMLError` herite d'`Exception`, pas de `ValueError`. Un `stack.yml` corrompu faisait donc remonter l'erreur brute au lieu d'etre traite comme « illisible, on repart de zero ». Converti a la source dans `migrations.lire`, comme la fois precedente. Trouve par un test ecrit avant le correctif. |
| **0.7.0** | **L'identifiant a son bouton de copie**, sur la page d'acces et la console. Demande a l'usage : on le recopie autant que le mot de passe — dans un formulaire de connexion, juste avant lui — et lui seul n'en avait pas. Il reste affiche en clair : ce n'est pas un secret, c'est le bouton qui manquait. Verifie dans un navigateur, pas seulement dans le HTML. |
| **0.6.0** | **`plugarr upgrade` : une installation ancienne se rattrape en une commande.** Jusqu'ici PlugArr savait mettre a jour UN service ; il ne savait pas mettre a jour **sa propre installation** quand c'est lui qui change. Quatre etapes, dans cet ordre parce qu'il compte : migrer `stack.yml`, aligner les images, regenerer les artefacts, rejouer le cablage. Le cablage passe **en dernier** — une etape ajoutee depuis peut dependre d'une image plus recente, l'inverse jamais. |
| **0.6.0** | **On ne redescend jamais une version.** Le tag deploye vit dans `stack.yml` et non dans le code, precisement pour qu'on puisse mettre Sonarr a jour sans attendre PlugArr, ou rester delibrement en arriere. `upgrade` ne propose donc que ce qui AVANCE, compare des nombres et non des chaines — `4.9.5` vient avant `4.16.1` — et **affiche ce qu'il ecarte avec sa raison** : un service saute en silence donne l'impression d'avoir tout aligne. |
| **0.6.0** | **`stack.yml` porte une version depuis toujours, et rien ne la lisait.** Ce n'etait pas un detail d'hygiene : pydantic ignore les champs qu'il ne connait pas, donc une version ancienne lisant un `stack.yml` recent en jetait une partie, et la **premiere ecriture la detruisait**. La perte a ete **reproduite avant d'etre corrigee** — champ futur pose, relu, disparu — et PlugArr refuse desormais de lire un fichier plus recent que lui plutot que de le lire a moitie. Les migrations tournent sur le dictionnaire BRUT : apres pydantic, « absent » et « valeur par defaut » sont indistinguables. |
| **0.5.2** | **`plugarr restore` plantait sur un fichier qui n'est pas une archive**, et sortait sur une trace Python brute suivie de « Failed to execute script 'launcher' ». `zipfile.BadZipFile` herite d'`Exception`, **pas** de `ValueError` ni d'`OSError` : les deux appelants, qui attrapaient ces deux-la, la laissaient passer. La conversion se fait desormais dans `lire_manifeste`, une fois, plutot que dans chaque appelant — un troisieme en beneficiera. Trouve en lancant l'EXECUTABLE PUBLIE sur un fichier texte renomme en `.zip` ; tous les tests passaient. |
| **0.5.2** | Deux messages restaient francais et ne se voyaient que la : `stack.yml introuvable. Lancez d'abord plugarr install`, et le tableau du contenu d'une archive. Meme methode, meme resultat : lancer le binaire plutot que relire le code. |
| **0.5.1** | **Le chemin d'ECHEC parle anglais aussi.** La 0.5.0 couvrait tout le chemin nominal ; restaient les messages qu'on ne voit que quand quelque chose casse — « qBittorrent n'est jamais devenu disponible », « le config.xml pre-seme a peut-etre ete ecrase », « NON PROTEGE : le tunnel ressort sur VOTRE adresse publique ». Ils vivaient dans quinze modules clients, `wiring.py`, `vpncheck.py` et l'orchestrateur, sous forme de `WiringError` levees profondement dans le code. Le catalogue les dedoublonne : le meme « X n'est jamais devenu disponible » servait neuf fois. **540 phrases** au total, contre 377 a la 0.5.0. |
| **0.5.1** | **Les fichiers ecrits sur le disque aussi.** `docker-compose.yml`, `.env`, `.gitignore`, `administration.cmd` et le script de demarrage automatique portaient un en-tete francais. Ce ne sont pas des messages a l'ecran, mais ils se lisent : on ouvre son `.env` pour retrouver un mot de passe. Restent en francais deux gabarits HTML et un bloc JavaScript — ce sont des structures, pas des phrases, et les traduire reviendrait a maintenir deux copies d'une page. |
| **0.5.1** | **Un pluriel perdu, rattrape par un test.** Envelopper « 2 deja configures » avait fait disparaitre l'accord francais. Deux cles plutot qu'une : le francais accorde, l'anglais ne change pas, et une cle unique aurait force l'une des deux langues a etre fausse. |
| **0.5.0** | **PlugArr parle anglais**, et deux langues cessent de se confondre. Celle de PlugArr — assistant, ligne de commande, rapport, page d'accès, preflight — se choisit sur l'écran d'accueil ou par `--lang`, et part de celle du système. Celle des **services** se demande à part : on peut vouloir l'outil en anglais et sa médiathèque en français. Le second réglage existait depuis la 0.1.11, mais il était **seul**, donc ambigu — l'écran annonçait « langue des interfaces » sans dire lesquelles. La clé de traduction est la phrase française elle-même : une phrase absente retombe sur le français, compréhensible au pire, là où une clé mal orthographiée s'afficherait telle quelle. |
| **0.5.0** | **Les widgets traduisent au passage.** Envelopper cent-cinquante phrases à la main aurait posé la question à chaque ligne écrite, et une phrase oubliée ne casse rien : elle s'afficherait en français à quelqu'un qui a demandé l'anglais, sans erreur ni avertissement. `tui/widgets.py` et la console de `report.py` font passer leurs libellés par le catalogue ; les écrans continuent d'écrire leurs phrases en clair. Le garde-fou est mécanique : `scripts/audit_traductions.py` relève les **540 phrases affichables** et échoue s'il en manque une, **ou** si le catalogue porte une entrée morte. Il tourne en CI, et il a déjà attrapé une entrée posée deux fois. |
| **0.5.0** | **Un défaut que seul un vrai montage pouvait révéler.** `Select` attend `(libellé, valeur)` et recevait `(valeur, libellé)` : le code `fr` devenait alors illégal, et l'assistant mourait au montage de l'écran d'accueil. Les tests passaient tous. |
| **0.5.0** | **Les captures existent dans les deux langues**, et la console d'administration en a enfin une. Elle n'est pas un écran du terminal — c'est du HTML servi par `plugarr serve` — donc `screenshots.py` ne pouvait pas la produire : c'était la seule partie visible du produit dont il n'existait aucune image. `scripts/captures_administration.py` écrit la page ET la photographie, avec les mêmes précautions que les autres captures : secrets d'illustration, adresse fixe, **date figée** — celle du jour rendrait le fichier différent à chaque exécution. |
| **0.4.0** | **DroppedNeedle entre au catalogue**, débloqué par SABnzbd comme prévu. Il **remplace** Lidarr : la musique de la demande au rangement. Une note de cette feuille de route affirmait que son premier compte se créait par l'interface web — **c'était faux**, `POST /api/v1/auth/setup` existe. Deux défauts trouvés en l'intégrant, aucun visible autrement : sa table `auth_users` vit dans `/app/cache`, que le compose amont ne monte pas, si bien que l'accueil réussissait puis la connexion échouait après un simple redémarrage ; et sa base SQLite **refuse de démarrer** sur un montage Windows — « The upgraded library database could not be verified ». Même remède que la base de Silo. |
| **0.4.0** | **Les volumes Docker nommés sont déduits du catalogue.** Ils étaient codés en dur en **cinq endroits** pour le seul PostgreSQL de Silo — compose, détection d'état existant, remise à zéro, message d'emplacement, sauvegarde. Le deuxième cas a rendu la dispersion intenable : un `named_volumes` sur la fiche du service suffit désormais, et tout le reste en découle. |
| **0.4.0** | **SABnzbd entre au catalogue.** Demandé comme « remplaçant pour DroppedNeedle », la prémisse méritait correction : DroppedNeedle n'est pas un mauvais choix, il est bloqué par son client de téléchargement, et **tous** les chemins vers l'acquisition automatisée de musique passent par slskd ou SABnzbd. Ajouter le client le débloque sans le remplacer, et sert toute la pile : Sonarr, Radarr et Lidarr y gagnent l'Usenet à côté des torrents. L'Usenet reçoit sa **propre arborescence** sous `/data/usenet` — un torrent doit rester en partage après l'import, un NZB non, et les mélanger fait effacer par l'un ce que l'autre partage encore. Quatre pièges enchaînés, chacun muet : sa liste blanche d'hôtes refuse `http://sabnzbd:8080` ; sa clé API n'était pas générée ; son pré-semis ne tournait pas ; et ses catégories d'usine ont un répertoire **vide**, si bien que « créer si absente » les laissait inutilisables. Prowlarr, lui, refuse de se déclarer sans sa propre catégorie. |
| **0.3.0** | **Seerr entre au catalogue.** Successeur commun de Jellyseerr et d'Overseerr. Son compte administrateur **est** le compte Jellyfin — PlugArr ne lui en génère aucun, ce serait mentir. Il déclare Sonarr et Radarr, dossier anime compris, puis ferme son accueil **en dernier** : l'inverse laisserait une instance qui se croit prête et ne peut rien demander. Sa spécification OpenAPI embarquée **ment par omission** : `hostname` est l'hôte seul et `port`, `useSsl`, `urlBase` ne sont pas déclarés alors que l'implémentation les lit ; `serverType` est obligatoire alors qu'elle le donne pour facultatif ; et `minimumAvailability` n'existe que pour Radarr. Trois essais réels pour les trouver, chacun derrière un message trompeur. |
| **0.3.0** | **Les identifiants des *arr n'étaient pas appliqués sans redémarrage.** `PUT config/host` répond **202**, accuse réception, et ne change rien avant que l'application reparte — le même piège que pour la clé API. Écarté au passage : ce n'est pas une question de caractères spéciaux, un mot de passe purement alphanumérique était refusé de la même façon. L'étape redémarre désormais le conteneur et revérifie. |
| **0.3.0** | **Audiobookshelf entre au catalogue.** Il remplit `books` et `audiobooks`, les deux bibliothèques que PlugArr rangeait depuis la 0.1.12 sans que personne ne les lise. Trois pièges relevés contre une instance réelle : il met **quarante secondes** à démarrer et répond 404 avant, ce qui fait croire à une image cassée ; sa base SQLite se lit **avec son journal `-wal`** ou pas du tout, sans quoi la table `users` paraît vide pendant que `/status` annonce `isInit: true` ; et `POST /init` répond 200 **avec un corps vide**, sans jeton — là où l'accueil de Silo en renvoie deux. Ce dernier a donné 0 liaison sur 1 au premier essai réel. |
| **0.2.1** | **La restauration se fait depuis l'assistant.** Elle avait d'abord été laissée en ligne de commande, au motif qu'un bouton serait dangereux — argument faible, la ligne de commande a le même pouvoir. La vraie raison désigne le bon endroit : la console d'administration commence par lire un `stack.yml`, et sur une machine fraîchement formatée il n'y en a pas, puisque c'est ce que l'archive contient. Un bouton là-bas aurait été inutilisable dans le seul cas où il sert. L'assistant, lui, démarre sans rien. Un bouton **Examiner l'archive** montre ce qu'elle contient avant d'écraser quoi que ce soit, et remplace la confirmation. |
| **0.2.1** | **Sauvegarde et restauration complètes.** Vérifié sur une pile réelle et non simulé : un témoin posé dans Sonarr, sauvegarde, **destruction totale** — conteneurs, volumes, dossiers — puis restauration ailleurs. Le témoin est revenu, Silo est reparti *healthy* du premier coup, et le recâblage a compté **12 liaisons sur 12, zéro créée** : tout existait déjà. Un bouton sur la console ; la restauration reste en ligne de commande, car elle écrase une configuration en place. |
| **0.2.0** | **arrsenal devient PlugArr.** Le nom disait « un tas d'outils », ce que propose n'importe quel dépôt de compose *arr ; ce qui distingue ce projet est qu'il les **branche ensemble**. 125 fichiers. Le point dur n'était aucun des noms visibles : `discovery.py` reconnaît les piles installées par un **label**, jamais par leur nom, et renommer ce label aurait rendu invisible chaque installation existante — donc candidate à être recréée par-dessus. Les deux marqueurs sont lus, `plugarr.managed` et `arrsenal.managed` ; seul le premier est écrit. Le renommage mécanique avait aussi cassé vingt-cinq élisions françaises : « qu'arrsenal sait faire » devenait « qu'PlugArr sait faire ». |
| **0.2.0** | **L'exécutable n'avait aucune icône** — Windows lui collait celle, générique, de tout binaire console. Sept tailles de 16 à 256 px, engendrées par `scripts/icone.py` plutôt que commitées en binaire opaque : fond transparent, car une tuile sombre gravée devient une tache noire sur une barre des tâches claire ; canal alpha tiré de la **chroma** et non de la luminosité, qui mangeait le bas du jambage violet. L'assistant porte les couleurs de la marque. |
| **0.1.12** | **Une bibliothèque ajoutée au catalogue n'atteignait pas les installations existantes.** `install` crée l'arborescence, `wire` non — et Sonarr refuse net un dossier racine absent : « Path '/data/media/anime' does not exist ». Trouvé en réparant une pile réelle juste après l'ajout de l'anime. `wire` garantit désormais les dossiers avant de câbler ; l'opération est idempotente et silencieuse sur une installation à jour. |
| **0.1.12** | **`plugarr wire` n'attendait pas que les services soient prêts, et répondait par une trace Python.** Un Sonarr neuf passe une minute ou plus dans ses migrations : son port est publié mais rien n'écoute derrière, et le câblage tombait sur « Server disconnected without sending a response » — un message qui envoie chercher une panne réseau là où il n'y a qu'une attente. Quand l'attente expirait, la commande finissait sur « Failed to execute script 'launcher' ». `install` traitait déjà les deux cas ; `wire`, qui est la commande qu'on lance justement pour réparer un câblage incomplet, non. |
| **0.1.12** | **Flood ne pouvait pas joindre son client de téléchargement sous VPN.** Même cause que Prowlarr : Flood n'est pas dans le tunnel, le client y est et perd son alias DNS. Son mot de passe quitte au passage `docker-compose.yml`, où il était en clair — dernier secret à y rester après la clé WireGuard. |
| **0.1.12** | **Un tunnel qui ressort chez vous est maintenant détecté.** Les deux premiers contrôles le déclaraient bon — le conteneur *est* dans le tunnel. Trouvé sur le banc d'essai : un serveur WireGuard local qui traduisait les adresses vers la sortie du domicile passait au vert. L'adresse du tunnel est donc comparée à celle de la machine. Aucune des deux n'est journalisée. |
| **0.1.12** | **PlugArr vérifie désormais que le trafic torrent sort par le tunnel.** Il écrivait `network_mode: service:gluetun` et considérait l'affaire close ; or ce réglage se perd, et rien ne l'aurait signalé. Deux contrôles dans `doctor` et sur le bouton diagnostic : la structure du conteneur, puis la sortie réelle, demandée au serveur de contrôle de Gluetun **depuis l'intérieur du client**. Ce test ne peut pas réussir par accident — seul un conteneur partageant la pile réseau de Gluetun voit ce `127.0.0.1`, vérifié dans les deux sens. Aucun service extérieur n'est contacté, et l'adresse IP n'est jamais journalisée. |
| **0.1.12** | **Prowlarr ne pouvait pas joindre les clients de téléchargement quand le VPN était actif.** Un client torrent sous VPN passe en `network_mode: service:gluetun` et perd son nom sur le réseau : c'est `gluetun` qu'il faut viser. `step_download_client` le savait, `step_prowlarr_download_client` posait le nom du service en dur. Sonarr, Radarr et Lidarr se câblaient très bien sur les mêmes clients au même instant, ce qui rendait la panne illisible. **Troisième divergence** entre ces deux étapes après le mot de passe et la clé : elles lisent désormais la même fonction. |
| **0.1.11** | **La console d'administration n'avait plus aucun JavaScript depuis la 0.1.8.** Le message de confirmation de « ajouter un service » contenait une chaine ouverte sur deux lignes et trois apostrophes francaises non echappees — du JavaScript invalide, qui emportait le script entier. Demarrer, arreter, redemarrer, faire tourner une cle, appliquer une mise a jour : rien ne repondait. Le HTML etait pourtant parfaitement bien forme, et tous les tests Python passaient. Trouve en ouvrant la page dans un vrai navigateur ; un test verifie desormais que chaque bloc `<script>` a ses apostrophes appariees. |
| **0.1.11** | **Diagnostic et recherche de mises a jour depuis la console.** Deux boutons, demandes a l'usage. La verification des mises a jour tournait deja toutes les quinze minutes, mais en silence : impossible de la declencher ni de savoir quand elle avait eu lieu. Le diagnostic, lui, n'existait qu'en ligne de commande. |
| **0.1.11** | **Une seconde installation ecrasait la premiere.** Docker identifie une pile par son nom, jamais par son repertoire, et ce nom etait fige a `plugarr` : installer une pile d'essai a cote d'une pile en service recreait les six conteneurs de celle-ci en les pointant ailleurs. Le preflight rassurait meme — « port occupe par votre propre pile PlugArr » — ce qui etait vrai du nom et faux de l'installation. `--project-name` existe maintenant, l'assistant le demande, et le preflight avertit. |
| **0.1.11** | **Le volume de la base de Silo survivait a une reinstallation.** PostgreSQL n'applique `POSTGRES_PASSWORD` qu'a la creation de sa base ; sur un volume deja rempli il l'ignore en silence. Reinstaller generait un nouveau mot de passe, le volume gardait l'ancien, et Silo redemarrait en boucle sur « password authentication failed ». La verification ne regardait que le disque. |
| **0.1.11** | **PlugArr promettait un `.gitignore` qu'il n'ecrivait pas.** Le rapport et la page d'acces annoncaient que les identifiants etaient « deja dans .gitignore » ; aucun fichier n'etait depose. Il l'est desormais. |
| **0.1.11** | **La cle privee WireGuard etait ecrite en clair dans `docker-compose.yml`**, seul secret a echapper au `.env` protege. Elle passe par le `.env` comme les autres. |
| **0.1.11** | **Le conseil de fin citait Prowlarr meme absent.** « Ajoutez vos indexeurs dans Prowlarr, ils descendront vers Sonarr et Radarr » s'affichait apres une installation de Silo seul, ou aucune des trois applications n'existait. Il depend maintenant de ce qui est installe. |
| **0.1.11** | La base de Silo passait par un montage vers le disque Windows : ses migrations de premier démarrage prenaient **49 minutes** au lieu de 5 secondes, et l'installation abandonnait au bout de 300 s alors que PostgreSQL fonctionnait très bien. Un volume Docker règle les deux. Au passage, `config/silo-redis` restait vide à côté du `config/silo/redis` que Docker fabriquait lui-même. |
| **0.1.10** | **0.1.8 et 0.1.9 etaient ininstallables** : le fichier des pays VPN n'entrait ni dans l'exécutable ni dans le paquet, et l'assistant mourait sur l'écran VPN. Un test compare désormais les fichiers non-Python réels aux deux déclarations d'empaquetage, et le contrôle de l'exe parcourt l'assistant au lieu de l'ouvrir. |
| **0.1.9** | La console démarre toute seule, sur l'hôte, et se protège par un mot de passe. Un cookie contenant un caractère accentué tuait la requête sans authentification. |
| **0.1.8** | Rotation des clés API, ajout d'un service depuis la page d'administration, et filtre géographique du VPN en liste cliquable. Un même défaut trouvé trois fois : un service qui garde l'ancien secret sans que rien ne le dise — autobrr, puis l'entrée Application de Prowlarr. |
| **0.1.7** | Recyclarr ne posait plus aucun profil, silencieusement, dès qu'un service se retrouvait avec deux fichiers de configuration. Renouvellement d'un mot de passe depuis la page d'administration. autobrr gardait l'ancien mot de passe d'un client de téléchargement. |
| **0.1.6** | Trois plantages de l'assistant : deuxième indexeur sélectionné (`DuplicateIds`), message d'erreur d'un indexeur contenant un crochet ouvert, et champs devenus inaccessibles sur une fenêtre courte. La clé d'un indexeur ne fuit plus à l'écran ni au journal. |
| **0.1.5** | Le VPN et l'adresse de la machine entrent dans l'assistant. Jellyfin gardait un index vide : rien ne lançait d'analyse après la création des bibliothèques. Une étape qui plante n'emporte plus tout le câblage. |
| **0.1.4** | Identifiant au choix, page d'administration accessible. |
| **0.1.3** | Choix explicite sur une configuration existante, page d'accès ouverte automatiquement. |

Le détail complet est dans les [notes de version](https://github.com/yannickuhrig1/plugarr/releases).
