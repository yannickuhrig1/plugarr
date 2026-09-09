***Français** · [English](COMPATIBILITY.en.md)*

# Compatibilité

Tout ce qui figure ici a été **vérifié contre une instance réelle**, pas déduit de la
documentation. Les tags d'image sont épinglés dans `src/plugarr/catalog.py`.

Dernière campagne de vérification : **2026-08-31**, Docker Engine 29.6.1,
Docker Compose v5.3.0, Docker Desktop sous Windows 11 (backend WSL2).

## Versions testées

| Service | Image | Tag | Version rapportée par l'API |
|---|---|---|---|
| Sonarr | `lscr.io/linuxserver/sonarr` | `4.0.19` | 4.0.19.2979 |
| Radarr | `lscr.io/linuxserver/radarr` | `6.3.0` | vérifié au démarrage |
| Prowlarr | `lscr.io/linuxserver/prowlarr` | `2.5.2` | vérifié au démarrage |
| Transmission | `lscr.io/linuxserver/transmission` | `4.1.3` | — |
| Jellyfin | `lscr.io/linuxserver/jellyfin` | `10.11.11` | 10.11.11 |
| Lidarr | `lscr.io/linuxserver/lidarr` | `3.1.0` | 3.1.0.4875 |
| qBittorrent | `lscr.io/linuxserver/qbittorrent` | `5.2.3` | v5.2.3 |
| Flood | `jesec/flood` | `4.16.1` | pas encore testé |

## Constats vérifiés expérimentalement

### Le pré-semis de `config.xml` fonctionne

Un `config.xml` écrit **avant** le premier démarrage est adopté par l'application.
Sonarr conserve nos champs et se contente d'ajouter les siens (`EnableSsl`).
Notre clé API répond immédiatement sur `/api/v3/system/status`.

Le premier démarrage prend **environ 110 s** (extraction de l'image + initialisation).
C'est ce qui fixe le délai d'attente par défaut à 300 s.

### `Forms` + `Enabled` est le bon réglage d'authentification

Trois comportements confirmés sur Sonarr 4.0.19.2979 :

| Requête | Résultat |
|---|---|
| `GET /` sans session | `302` vers `/login` — l'UI est protégée |
| `GET /api/v3/system/status` sans clé | `401` |
| `GET /api/v3/system/status` avec `X-Api-Key` | `200`, `"authentication": "forms"` |

L'alternative `External` + `DisabledForLocalAddresses` câble aussi bien mais laisse
les interfaces web ouvertes à tout le réseau local. **Rejetée.**

Bonus : l'application consomme `<Username>`/`<Password>` au premier démarrage, les
migre en base, puis les **efface du fichier**. Le mot de passe en clair ne survit pas
sur le disque.

### `Category` et `Directory` sont mutuellement exclusifs

Renseigner les deux fait échouer la création du client de téléchargement :

```
HTTP 400 — propertyName: "TvCategory", errorMessage: "Cannot use Category and Directory"
```

**Piège** : le gabarit renvoyé par `/schema` arrive avec une catégorie **par défaut
déjà remplie** (`tv-sonarr` pour Sonarr, `radarr` pour Radarr). Il ne suffit pas
d'omettre le champ, il faut le **vider explicitement**.

PlugArr retient `Directory`, qui pointe vers un chemin explicite sous
`/data/torrents` et garde les hardlinks possibles.

### La notification Jellyfin exige une clé API

L'implémentation `MediaBrowser` de Sonarr et Radarr refuse un `apiKey` vide :

```
HTTP 400 — propertyName: "ApiKey", errorMessage: "'Api Key' must not be empty."
```

PlugArr crée donc une clé Jellyfin via `POST /Auth/Keys?app=plugarr` (répond `204`)
pendant l'étape d'assistant, puis la relit par `GET /Auth/Keys`, et l'injecte dans les
notifications. C'est ce qui impose l'ordre : Jellyfin avant les notifications.

### Assistant de démarrage Jellyfin 10.11.11

| Appel | Code |
|---|---|
| `POST /Startup/Configuration` | `204` |
| `GET /Startup/User` | `200` |
| `POST /Startup/User` | `204` |
| `POST /Startup/RemoteAccess` | `204` |
| `POST /Startup/Complete` | `204` |
| `POST /Users/AuthenticateByName` | `200` + `AccessToken` |
| `POST /Library/VirtualFolders` | `204` |

Après quoi `StartupWizardCompleted` passe à `true` et la bibliothèque apparaît avec le
bon `CollectionType` et le bon chemin.

Jellyfin démarre en **environ 25 s**, nettement plus vite que les *arr.

## Vérification finale du câblage

Chaque lien est validé par le bouton **Test** de l'application concernée, pas par le
code de retour du POST :

| Test | Résultat |
|---|---|
| `POST /api/v3/downloadclient/test` (Sonarr → Transmission) | `200` |
| `POST /api/v1/applications/test` (Prowlarr → Sonarr) | `200` |
| `POST /api/v3/notification/test` (Sonarr → Jellyfin) | `200` |
| `GET /api/v3/rootfolder` | `accessible: true` |

Installation propre depuis zéro : **10/10 liens établis**.

## Phase 2 — constats vérifiés

Campagne du **2026-08-31**, même environnement. Installation propre à 7 services
avec **les deux clients de téléchargement en parallèle** : **18/18 liens établis**.

### Le pré-semis du mot de passe qBittorrent fonctionne

Depuis la 4.6.1, qBittorrent génère au premier démarrage un mot de passe temporaire
aléatoire écrit sur sa sortie standard — impossible à câbler automatiquement.

Écrire `WebUI\Password_PBKDF2` dans `/config/qBittorrent/qBittorrent.conf` avant le
premier démarrage résout le problème. Format confirmé contre 5.2.3 :

```
@ByteArray(<sel base64>:<empreinte base64>)
PBKDF2-HMAC-SHA512, 100000 itérations, clé 64 octets, sel 16 octets
```

Résultat : `POST /api/v2/auth/login` répond `204` avec un cookie `QBT_SID`, et aucun
mot de passe temporaire n'apparaît dans les logs.

**Attention au code de retour** : qBittorrent 5.x renvoie `204` en cas de succès et
`200` avec le corps `Fails.` en cas d'échec. C'est donc la présence du cookie qui fait
foi, jamais le code HTTP seul.

### `HostHeaderValidation` doit être désactivé

Sonarr et Radarr appellent qBittorrent par son nom de conteneur
(`http://qbittorrent:8080`), pas par une adresse IP. Sans
`WebUI\HostHeaderValidation=false`, qBittorrent rejette ces requêtes.

### qBittorrent route par catégorie, Transmission par répertoire

Transmission n'a pas de vraies catégories : on lui passe un `Directory`.
qBittorrent a des catégories natives avec chemin de sauvegarde par catégorie : on lui
passe une `Category`, créée en amont via `POST /api/v2/torrents/createCategory`.

Ordre imposé : les catégories doivent exister **avant** que les *arr n'y pointent,
sinon qBittorrent les crée lui-même sans chemin de sauvegarde. Prowlarr fait de même
avec une catégorie `prowlarr` : elle est donc pré-créée aussi.

Vérifié après installation :

```
movies   -> /data/torrents/movies
music    -> /data/torrents/music
prowlarr -> /data/torrents
tv       -> /data/torrents/tv
```

### Lidarr n'est pas un Sonarr comme les autres

Trois différences qui cassent le code écrit pour Sonarr et Radarr :

1. **Son API est en `v1`**, pas `v3`.
2. **Son dossier racine exige plus de champs.** Là où Sonarr accepte `{"path": ...}`,
   Lidarr répond `400` :

   ```
   Name                     : 'Name' must not be empty.
   DefaultQualityProfileId  : must be greater than '0'.
   DefaultMetadataProfileId : must be greater than '0'.
   ```

   Il n'existe pas de `/schema` pour `rootfolder`. Les identifiants de profils ne sont
   pas stables entre versions : ils sont résolus **par nom** (`Standard`), avec repli
   sur le premier profil disponible.

3. Lidarr n'expose **pas** l'implémentation de notification `MediaBrowser` : aucun lien
   Lidarr vers Jellyfin n'est tenté.

## PUID / PGID par plateforme — vérifié

Le point de départ était un `TODO(verify)`. La vérification a montré que **la question
était mal posée** : ce ne sont pas les mêmes valeurs qu'il fallait trouver, mais deux
comportements différents.

| Profil | Comportement | Pourquoi |
|---|---|---|
| `generic-linux` | détection (`os.getuid`) | l'utilisateur courant est le bon |
| `unraid` | **constante 99:100** | Unraid fait tourner ses conteneurs en `nobody:users` à l'échelle de la plateforme, et son `appdata` appartient à 99:100 |
| `synology` | détection | **les UID DSM varient selon l'ordre de création des utilisateurs** : 1026 pour le premier, mais on rencontre couramment bien plus haut |

Coder `1026` en dur pour Synology était donc **faux par conception**, pas seulement non
vérifié. Une constante ne peut pas être juste quand la valeur dépend de l'installation.

Deux conséquences dans le code :

- `detect_ids()` renvoie `None` quand la plateforme n'expose pas `os.getuid` (Windows),
  au lieu d'inventer `1000:1000` en silence. Une valeur fabriquée sans le dire empêche
  d'avertir l'utilisateur.
- `StackConfig` porte `ids_source` et `ids_certain`. Le récapitulatif affiche d'où
  viennent les valeurs (« détecté », « constante Unraid », « repli »), et l'assistant
  avertit explicitement quand la détection a échoué.

Sources : [forums Unraid](https://forums.unraid.net/topic/117661-docker-user-puid-and-group-pgid-settings/)
· [Marius Hosting, UID/GID sur Synology](https://mariushosting.com/synology-how-to-find-uid-userid-and-gid-groupid/)

## Coexistence avec une stack existante — vérifié

Observation faite sur un Unraid réel faisant tourner 75 conteneurs, dont un
`sonarr` sur le port 8989 avec `/mnt/user/appdata/sonarr` en configuration :
**PlugArr codait `container_name` en dur**, donc il ne pouvait ni cohabiter avec une
stack existante, ni être déployé deux fois sur la même machine.

Les noms de conteneurs sont désormais préfixés par le nom de projet
(`plugarr-sonarr`). Vérifié contre Docker Compose v5.3 que cela ne casse rien :

```
depuis le service "sonarr" :
  getent hosts prowlarr           -> 172.18.0.3  prowlarr
  getent hosts dnsprobe-prowlarr  -> 172.18.0.3  dnsprobe-prowlarr
```

Le **nom de service** résout indépendamment de `container_name`. Le câblage vise le
service (`http://sonarr:8989`), il n'est donc pas affecté.

Les collisions de **ports** restent possibles (8989 est un défaut très répandu) : le
préflight les détecte et refuse avant toute écriture.

## Linux natif — vérifié le 2026-08-31

Toutes les campagnes précédentes tournaient sous Docker Desktop / WSL2, où les
permissions sont plus permissives qu'un vrai serveur. Vérification faite sur un **LXC
Proxmox Debian 12.2** (PVE 9.2.6), ext4, Docker 29.7.2.

| | |
|---|---|
| Installation complète (5 services) | **11/11 liens établis**, tous validés par le bouton Test |
| Second passage | aucune création, tout « déjà présent » |
| Hardlink `/data/torrents/tv` → `/data/media/tv`, **depuis l'intérieur du conteneur Sonarr** | `stat -c %h` = **2** |

Le hardlink est la preuve qui manquait : sous Windows, seul `os.link` côté hôte avait
été testé. Ici c'est Sonarr lui-même, dans son conteneur, sur ext4, qui partage l'inode
entre les téléchargements et la médiathèque. C'est exactement ce que le montage `/data`
unique doit garantir.

### Docker dans un LXC : `nesting=1` suffit

Contrairement à ce qui est souvent écrit, `keyctl=1` n'a pas été nécessaire — et il
n'est de toute façon pas réglable via un jeton d'API Proxmox, seulement en `root@pam`
direct. Avec `nesting=1` seul, `docker run hello-world` et la stack complète
fonctionnent.

### Le bug que seul Linux pouvait révéler

`sudo plugarr install` détectait `0:0` et faisait tourner **toute la stack en root**,
en silence. Les médias téléchargés appartiennent alors à root, et l'utilisateur ne peut
plus y toucher sans `sudo`.

`resolve_ids` signale désormais explicitement le cas root, au même titre qu'une
détection impossible. La valeur reste proposée — c'est un choix légitime sur certains
NAS — mais elle n'est plus silencieuse.

## Non vérifié à ce jour

- Bazarr est **volontairement absent du catalogue** : sa configuration passe par un
  fichier YAML et non par une API, et rien n'a encore été vérifié. Le projet ne livre
  pas de service qu'il ne sait pas câbler.
- Flood n'a pas encore été démarré dans une campagne de test.

## Indexeurs — constats vérifiés (Prowlarr 2.5.2)

### Ce que Prowlarr embarque

`GET /api/v1/indexer/schema` renvoie **626 définitions**, soit **5,7 Mo** — à charger une
seule fois et à mettre en cache, jamais à chaque frappe.

| | |
|---|---|
| privées | 475 |
| publiques | 88 |
| semi-privées | 63 |
| torrent / usenet | 605 / 21 |

### Repérer les champs d'identifiants

Le marqueur `privacy` au niveau champ (`apiKey`, `password`, `userName`) ne couvre que
**115 champs sur plus de 9500** : la majorité des définitions Cardigann laissent leurs
clés en `privacy: normal`. Une heuristique combinée est nécessaire :

1. `privacy` ∈ (`apiKey`, `password`, `userName`)
2. ou `type == "password"`
3. ou nom connu (`apikey`, `passkey`, `cookie`, `rsskey`, …)
4. ou — **règle structurelle** — `type == "textbox"` avec une valeur par défaut vide
5. en excluant les préfixes de réglage (`baseSettings.`, `torrentBaseSettings.`,
   `usenetBaseSettings.`), les 882 champs `type: "info"` purement décoratifs, et une
   courte liste de zones de texte libres qui n'en sont pas (`vipExpiration`,
   `additionalParameters`, préférences de langue)

### L'audit qui a produit la règle 4

Les règles 1 à 3 ont été confrontées aux **626 définitions** par
[`scripts/audit_indexers.py`](../scripts/audit_indexers.py). Elles laissaient passer
six identifiants : `mamId` (MyAnonamouse), `twoFactorAuthCode`, `alt2fatoken`, `passan`,
`staffpass`, `csrf_token`.

Tous étaient des **zones de texte sans valeur par défaut**. D'où la règle structurelle,
qui vaut mieux qu'une liste de noms à rallonge : une textbox vide est, par construction,
quelque chose que seul l'utilisateur peut fournir. Les réglages de comportement sont des
cases à cocher ou des listes, jamais des textbox vides.

Effet mesuré : **58 champs** rattrapés sur les 626 définitions, tous de vrais
identifiants (26 codes 2FA, 17 `useragent`, 8 `pin`, `mamId`, `passan`, `staffpass`…).
Aucun formulaire ne dépasse **3 identifiants**.

Deux familles de cas ont été examinées puis jugées correctes :

- **4 index privés sans aucun identifiant** — `BitMagnet (Local DHT)`, `comicat`,
  `MioBT`, `ConCen`. Ce sont des moteurs de recherche qui n'exigent pas de compte.
- **6 champs au nom trompeur** — `useFreeleechToken`, `usetoken`, `passid`… tous des
  cases à cocher ou des listes, donc des réglages.

L'audit tourne en CI contre le Prowlarr de la stack de test : **il échoue si une future
version introduit un champ d'identifiant d'une forme non prévue.**

### Les URL ne sont pas dans le champ `baseUrl`

**600 des 626** définitions exposent un `baseUrl` de type `select` **sans valeur et sans
`selectOptions`**. Les adresses vivent au niveau de la définition, dans `indexerUrls`.
Sans cette reprise, l'utilisateur devrait deviner l'adresse du tracker. Seules 3
définitions n'ont légitimement aucune URL : les génériques (`Generic Newznab`,
`Generic Torznab`, `Torrent RSS Feed`).

### L'ajout contacte forcément l'indexeur

`appProfileId` doit être `> 0`, comme le dossier racine de Lidarr. Résolu par nom
(`Standard`), jamais codé en dur.

Surtout : **`forceSave=true` ne saute pas la validation.** Vérifié sur deux cas d'échec :

| Situation | Résultat |
|---|---|
| indexeur injoignable | `400 — Unable to connect to indexer` |
| recherche de test sans résultat | `400 — Query successful, but no results were returned` |
| faux indexeur Torznab local renvoyant un résultat | enregistré |

Il n'existe donc **aucun moyen d'enregistrer un indexeur hors ligne**. Ce n'est pas un
choix de plugarr. La contrepartie est utile : la validation *est* le test, donc un ajout
réussi prouve que les identifiants fonctionnent.

Vérification menée contre un **faux serveur Torznab local**, jamais contre un vrai
tracker.

## Seerr remplace Jellyseerr et Overseerr — vérifié le 2026-08-31

Signalé par un utilisateur, vérifié plutôt que supposé. Ce n'est pas un renommage mais
une **fusion des deux projets**, annoncée le 10 février 2026.

| | |
|---|---|
| Dépôt canonique | `seerr-team/seerr` — 12 440 étoiles, actif |
| Image | `seerr/seerr`, dernière version stable **v3.4.1** (30/07/2026) |
| `sct/overseerr` | **archivé**, dernier push le 15/02/2026 |
| `fallenbagel/jellyseerr` | redirige (HTTP 301) vers `seerr-team/seerr` |

Seerr couvre Jellyfin, Emby **et** Plex — les deux projets d'origine se partageaient
ces cibles — et migre automatiquement les données au premier démarrage.

Conséquence pour PlugArr : la feuille de route ne vise plus qu'un seul service de
demandes utilisateurs. Prévoir la reprise d'une installation Jellyseerr ou Overseerr
existante est inutile : Seerr le fait lui-même.

## Reprise d'une stack existante — vérifié le 2026-08-31

Testé contre une stack **que PlugArr n'a pas créée** : quatre conteneurs aux noms
libres, répartis sur **deux réseaux Docker différents**, dont deux Sonarr.

Résultat : `prowlarr → sonarr` établi et validé par le bouton Test, sur des conteneurs
étrangers, avec des clés API lues dans leurs `config.xml`.

Trois erreurs de conception que seul le test réel a révélées.

### Ne pas imposer son arborescence

Le premier essai a échoué : `Path '/data/media/tv' does not exist`. PlugArr appliquait
sa propre arborescence à une stack qui a la sienne.

**Adopter, c'est câbler des services entre eux, pas réorganiser les dossiers de
quelqu'un.** Les dossiers racine existants sont désormais lus et respectés ; quand il
n'y en a aucun, PlugArr le signale au lieu d'en inventer un. Même règle pour les
catégories qBittorrent : les écraser déplacerait des téléchargements en cours.

### `localhost` ne veut rien dire entre conteneurs

Deuxième échec : `Unable to complete application test, cannot connect to Sonarr`. Les
services adoptés vivent sur leurs propres réseaux — le nom de service compose n'y résout
pas — et **depuis l'intérieur d'un conteneur, `localhost` désigne ce conteneur**, pas la
machine.

`adopt` détecte donc l'adresse de la machine sur le réseau local, et refuse de continuer
s'il n'y arrive pas plutôt que de câbler des URL mortes.

### Un nom de conteneur ne prouve rien

`looks_like_plugarr` reconnaissait ses propres conteneurs à leur nom
(`<projet>-<service>`). Un test a montré que `mon-sonarr` correspondait : PlugArr
**sautait en silence un conteneur qui ne lui appartenait pas**.

Les services générés portent maintenant un libellé `plugarr.managed=true`, et la
détection le lit au lieu de deviner.

### Ce qui reste hors de portée

Le mot de passe d'un client de téléchargement existant est haché dans sa configuration :
illisible. `--dl-user` et `--dl-pass` le demandent explicitement, et l'étape échoue avec
un message clair plutôt qu'une erreur technique.

## autobrr et qui — vérifiés le 2026-08-31

Signalés par un utilisateur depuis [github.com/autobrr](https://github.com/autobrr).

| | |
|---|---|
| autobrr | `ghcr.io/autobrr/autobrr:v1.85.0`, port **7474** |
| qui | `ghcr.io/autobrr/qui:v1.27.0`, port **7476** |

### Quatre particularités d'autobrr, aucune devinable

**L'en-tête d'authentification est `X-API-Token`**, pas `X-Api-Key` comme les *arr. Le
mauvais en-tête donne un `403` sans explication. Vérifié en essayant les trois.

**Une clé API exige un champ `scopes`.** Sans lui, la création échoue en `500` sur une
contrainte SQL : `NOT NULL constraint failed: api_key.scopes`. Le message d'erreur est
d'ailleurs ce qui a permis de trouver le champ manquant.

**Sonarr, Radarr et Lidarr sont des « clients de téléchargement ».** autobrr ne distingue
pas les applications des clients : même endpoint `POST /api/download_clients`, seul le
`type` change. Types confirmés un par un : `SONARR`, `RADARR`, `LIDARR`, `QBITTORRENT`,
`TRANSMISSION`, `DELUGE_V2`, `SABNZBD`, `WHISPARR`, `READARR`.

**L'accueil n'est jouable qu'une fois.** `GET /api/auth/onboard` renvoie `204` tant
qu'aucun compte n'existe, puis `503 — user already registered`. C'est ce qui rend
l'étape rejouable.

### Une mise en garde qui ne s'applique pas au conteneur

La documentation avertit qu'autobrr écoute sur `127.0.0.1` par défaut, ce qui rendrait un
conteneur injoignable. **Vérifié : l'image génère `host = "0.0.0.0"`.** La mise en garde
vaut pour une installation hors conteneur.

### Résultat

Installation réelle avec Sonarr et qBittorrent : autobrr créé, compte initialisé, clé API
générée, les deux services déclarés — et **les deux tests de connexion déclenchés par
autobrr lui-même répondent `204`**.

`qui` écoute bien sur 7476, confirmé par ses propres journaux. C'est une interface : elle
découvre ses instances qBittorrent par son écran de configuration, aucun câblage
automatique n'est possible.

## Gluetun — vérifié le 2026-08-31

| | |
|---|---|
| Image | `qmcgaw/gluetun:v3.41.3` |
| Dépôt | `qdm12/gluetun` **redirige vers `passteque/gluetun`** — 15 356 étoiles, actif |
| Healthcheck | fourni par l'image : `/gluetun-entrypoint healthcheck`, 5 s, 3 essais |

### La liste des fournisseurs vient de Gluetun

Plutôt que de recopier une liste d'article, on lui a passé un nom invalide. Il répond
avec l'énumération exacte : `airvpn, cyberghost, expressvpn, fastestvpn, giganews,
hidemyass, ipvanish, ivpn, mullvad, nordvpn, perfect privacy, privado, private internet
access, privatevpn, protonvpn, purevpn, slickvpn, surfshark, torguard, vpnsecure, vpn
unlimited, vyprvpn, windscribe, custom, pia`.

C'est cette liste qui est dans `models.py`, et `plugarr vpn-providers` l'affiche.

### Les deux modes n'exigent pas les mêmes champs

Constaté en lançant Gluetun à vide et en lisant ce qu'il réclame :

| Mode | Ce qu'il exige |
|---|---|
| `wireguard` | `WIREGUARD_PRIVATE_KEY`, et une **vraie clé base64** — il refuse toute autre chaîne |
| `openvpn` | `OPENVPN_USER` et `OPENVPN_PASSWORD` |

### Deux pièges du `network_mode: service:`

**Les ports du client doivent migrer vers Gluetun.** Un conteneur qui partage la pile
réseau d'un autre n'a plus de pile propre : il *ne peut plus* publier de port. Sans ce
transfert, l'interface du client devient injoignable — panne silencieuse et déroutante.

**Le client perd son alias DNS.** Vérifié contre Docker Compose 5.3 avec deux conteneurs
factices :

```
depuis un tiers :
  getent hosts client    -> rien
  getent hosts faux-vpn  -> 172.18.0.2
```

`http://qbittorrent:8080` ne résout donc plus : le câblage doit viser `http://gluetun:8080`.
Sans cette correction, activer le VPN cassait tout le câblage en silence.

### La propriété qui compte : aucune fuite possible

Testé avec des identifiants volontairement faux :

```
gluetun      running  Up 47 seconds (unhealthy)
qbittorrent  created  Created
dependency failed to start: container plugarr-gluetun is unhealthy
```

**Le client de téléchargement ne démarre pas tant que le tunnel n'est pas établi.** Ce
n'est pas une intention, c'est le comportement observé : `depends_on` sur le healthcheck
de Gluetun ferme la porte avant qu'un seul paquet puisse sortir hors du VPN.


## Port entrant et mode OpenVPN — vérifiés le 2026-09-09

Tout ce qui suit a été provoqué contre `qmcgaw/gluetun:v3.41.3`, l'image épinglée,
avec un compte ProtonVPN réel et des serveurs suisses.

### `VPN_PORT_FORWARDING=on` restreint déjà la sélection

`PORT_FORWARD_ONLY` n'a pas besoin d'être posé. Avec le seul
`VPN_PORT_FORWARDING=on`, Gluetun affiche dans son résumé de démarrage :

```
|   |   |   ├── Port forwarding only servers: yes
```

Une sonde sur un pays sans port entrant échoue donc de la même façon avec ou sans
le drapeau, et c'est un refus **définitif** :

```
ERROR [vpn] finding a VPN server: filtering servers: no server found:
for VPN wireguard; protocol udp; country macedonia; port forwarding only
```

C'est pourquoi l'assistant n'offre que les lieux qui en proposent un : le tunnel
ne démarrerait pas du tout.

### Le mode OpenVPN fonctionne, port entrant compris

| | |
|---|---|
| Tunnel | établi en **14 s** par `vpnessai`, sortie `Switzerland`, `AS209103 Proton AG` |
| Port entrant | `[port forwarding] port forwarded is 47878` |
| Identifiant | tel que saisi, **sans** suffixe |

### Le suffixe `+pmp` n'est pas requis, contrairement à ce que Gluetun laisse croire

Le binaire porte cette chaîne, rendue par
`internal/provider/protonvpn/portforward.go` :

```
%w - make sure you have +pmp at the end of your OpenVPN username
```

Le code **ne vérifie pas** le suffixe : il le suggère après un `connection
refused` sur NAT-PMP. Les deux variantes ont été essayées sur le même compte, à
quelques minutes d'intervalle :

| Identifiant | Tunnel | Port obtenu |
|---|---|---|
| `<user>` | oui | 47878 |
| `<user>+pmp` | oui | 44793 |

PlugArr ne modifie donc **pas** l'identifiant saisi : ce serait un pari, et un
compte où Proton refuserait ce suffixe se retrouverait sans tunnel du tout. Le
suffixe n'est mentionné que là où il répond à quelque chose — quand le contrôle
constate qu'aucun port n'a été obtenu.

### OpenVPN est structurellement plus lent à rendre son verdict

Le délai de négociation TLS est de **soixante secondes fermes** par serveur muet,
décidé par OpenVPN 2.6 et non configurable ici :

```
WARN [openvpn] TLS Error: TLS key negotiation failed to occur within 60 seconds
```

Tomber sur un serveur muet n'a rien d'exceptionnel : la liste embarquée dans
l'image portait l'horodatage **2025-11-18** alors que l'image a été bâtie le
2026-07-30, et un des neuf serveurs suisses à port entrant (`node-ch-03`,
`62.169.136.3`) ne répondait plus.

Chronologie mesurée avec un mot de passe volontairement faux :

```
00 s  premier serveur, muet
60 s  TLS Error: TLS key negotiation failed
75 s  second serveur
93 s  ERROR [openvpn] AUTH: Received control message: AUTH_FAILED
```

À quarante-cinq secondes, l'essai expirait **avant** que Gluetun ait dit quoi que
ce soit et rendait « peut-être » sur une réponse certaine. D'où deux minutes en
OpenVPN, quarante-cinq secondes en WireGuard.

### Une authentification refusée se reconnaît

`AUTH_FAILED` est l'équivalent OpenVPN de la clé WireGuard illisible : le serveur
a lu les identifiants et les a rejetés, aucune attente ne les rendra bons. Le
marqueur porte le souligné (`auth_failed`) et non le mot seul, parce que le
journal contient `AUTH: Received control message` et `Authentication file path`
dans des lignes parfaitement normales.

### Les artefacts et leurs droits

Relevé sur le banc, et confirmé en cherchant chaque secret dans le texte généré :

| Fichier | Droits | Secrets en clair |
|---|---|---|
| `.env` | 600 | tous |
| `stack.yml` (et son historique) | 600 | tous |
| `docker-compose.yml` | 644 | **aucun** — il ne porte que des `${REFERENCES}` |
| `${CONFIG_ROOT}/gluetun/port-sync.sh` | 755 | aucun — il lit `$QBT_PASS` depuis l'environnement |

## Détection des mises à jour — vérifié le 2026-08-31

### Deux choses différentes s'appellent « mise à jour »

| | Comment on la voit | Ce qu'elle demande |
|---|---|---|
| **Reconstruction** | digest local != digest distant, même tag | `pull` + recréation |
| **Nouvelle version** | un tag plus récent existe | changer le tag, donc réécrire `stack.yml` |

LinuxServer republie ses images très souvent. Confondre les deux rendrait l'information
inutile.

### Le tag déployé devait sortir du code

PlugArr épinglait ses tags dans `catalog.py`. Conséquence non voulue : **personne
n'aurait pu mettre Sonarr à jour sans attendre une nouvelle version de l'outil.**
Le tag vit désormais dans `stack.yml` ; le catalogue ne fournit que la valeur initiale.

### Lister les tags : la pagination n'est pas un détail

Le protocole registry v2 renvoie les tags dans l'ordre de **publication** — les plus
anciens d'abord, par pages de 200. Mesuré sur `linuxserver/sonarr` : 25 pages et
**6,2 secondes** ne suffisaient pas à atteindre la version courante ; le listage
s'arrêtait encore sur des tags de Sonarr 3.x.

Solution retenue : quand le dépôt est aussi sur Docker Hub, son API accepte
`ordering=last_updated` et donne les plus récents d'abord — une page suffit. Le protocole
générique reste le repli pour les autres registres.

**`lscr.io` est bien un miroir de Docker Hub**, vérifié par comparaison de digests :
`lscr.io/linuxserver/sonarr:4.0.19` et `linuxserver/sonarr:4.0.19` renvoient le même
sha256. C'est ce qui autorise ce raccourci.

Mesures après correction, sur les trois registres :

| Image | Temps | Résultat |
|---|---|---|
| `lscr.io/linuxserver/sonarr:4.0.15` | 1,3 s | 4.0.19 |
| `qmcgaw/gluetun:v3.40.0` | 0,9 s | v3.41.3 |
| `ghcr.io/autobrr/autobrr:v1.80.0` | 2,1 s | v1.85.0 |

### Comparer des versions, pas des chaînes

`4.9.5` vient **avant** `4.16.1`, ce que le tri alphabétique inverse. Les tags sont
convertis en tuples d'entiers, et seuls ceux de la même convention sont comparés — un
dépôt mélange `v1.85.0`, `1.85`, `version-1.85.0` et `latest`.

### Le bug qui rendait la page muette

Un retour à la ligne mal échappé dans le source Python s'est retrouvé **au milieu d'une
chaîne JavaScript**. La chaîne n'était pas terminée : le script entier mourait, la page
se chargeait normalement et plus rien ne se mettait à jour — ni l'état, ni les versions.

Un test vérifie désormais qu'aucune chaîne du script servi ne franchit une ligne.

### Deux serveurs sur le même port, en silence

`HTTPServer` active `allow_reuse_address`. Sous Linux, `SO_REUSEADDR` n'autorise pas deux
écoutes simultanées ; **sous Windows, si** : un second `bind` réussit sans un mot, et les
requêtes partent au hasard vers l'un ou l'autre processus. Chacun ayant tiré son propre
jeton, la page répondait « jeton invalide » une fois sur deux.

Le serveur refuse désormais de partager son port. Vérifié : le second démarrage échoue
avec `WinError 10048`, et il ne reste qu'une écoute.

---

## Recyclarr 8.7.1 — vérifié le 2026-09-01

Image `ghcr.io/recyclarr/recyclarr:8.7.1`. Recyclarr synchronise les profils de qualité
et les *custom formats* des TRaSH Guides vers Sonarr et Radarr. PlugArr ne
réimplémente rien : il demande à Recyclarr de générer sa configuration à partir d'un
template **officiel**, puis n'y écrit que l'adresse et la clé API.

### Le conteneur n'a pas d'interface web

Il tourne sur une planification, `CRON_SCHEDULE=@daily` par défaut, et
`RECYCLARR_CONFIG_DIR=/config`. Trois conséquences dans le code :

- son `internal_port` vaut `0` et **aucun port n'est publié** ;
- le préflight ne contrôle pas son port : la ligne « port 0 : libre » n'apprenait rien
  et faisait douter du reste du tableau ;
- la page d'accès ne lui donne **pas** de lien. Elle en proposait un vers
  `http://192.168.1.10:0`, juste sous une note disant « Aucune interface web ». Un lien
  mort au milieu d'une page de raccourcis fait conclure que l'installation a échoué.

L'entrypoint est `/sbin/tini -- /entrypoint.sh` et prend les sous-commandes
directement : `--version`, pas `recyclarr --version`.

### `config create` ignore `--path`

`config create --template X --template Y` écrit **un fichier par template** dans
`/config/configs/X.yml`, quel que soit `--path`. Recyclarr charge ensuite tout le
dossier. La génération se fait donc par `docker compose run --rm --no-deps`, un
conteneur jetable : la configuration existe avant que le service planifié n'ait tourné
une seule fois.

22 templates officiels Sonarr, 25 Radarr, dont des profils français
(`french-multi-vf-hd-bluray-web`). La liste est lue sur le disque, dans les ressources
que Recyclarr clone au premier démarrage — pas recopiée dans le code, où elle
vieillirait.

### Les templates portent des marqueurs en clair

```yaml
sonarr:
  web-1080p:
    base_url: Put your Sonarr URL here
    api_key: Put your API key here
```

Ce sont les deux seules lignes que PlugArr remplace. Tout le reste vient du guide et
doit rester intact — c'est la garantie centrale du module.

### Deux défauts trouvés par les tests, pas par la lecture

**`\s` matche aussi le retour à la ligne.** Le motif se terminait par `\s*$` : gourmand,
il avalait les lignes vides qui suivaient le marqueur. Le fichier restait valide et la
synchronisation réussissait, mais PlugArr reformatait au passage un fichier qu'il
s'était engagé à ne pas toucher. Les motifs sont désormais bornés à l'espace
**horizontal**, `[^\S\n]`.

Vérifié sur les **47 templates officiels** : chacun est rempli, aucune autre ligne
modifiée, aucune ligne perdue.

**Une chaîne de remplacement n'est pas un texte.** `re.sub` interprète les antislashs
dans le remplacement. Une `url_base` saisie à la main en contenant un aurait levé
`bad escape` au lieu d'écrire le fichier. Le remplacement passe maintenant par une
fonction.

### Un nom de fichier n'est pas un identifiant

Première version : lister `official/<service>/templates/*.yml` et proposer les noms de
fichiers. Faux, et sur deux plans à la fois.

C'est `templates.json`, à la racine du dépôt cloné, qui fait foi. Il associe à chaque
fichier l'`id` que `config create --template` accepte, et les deux diffèrent souvent :

| Fichier | Identifiant |
|---|---|
| `sonarr/templates/german-hd-bluray-web.yml` | `sonarr-german-hd-bluray-web` |
| `radarr/templates/german-hd-bluray-web.yml` | `radarr-german-hd-bluray-web` |

11 des 22 templates Sonarr et 11 des 35 Radarr portent ce préfixe — il lève l'ambiguïté
entre deux fichiers homonymes. Le glob aurait donc proposé des noms que Recyclarr
refuse. Il ratait en plus les **10 templates rangés dans `radarr/templates/sqp/`**, qu'un
`glob("*.yml")` ne voit pas : 25 trouvés au lieu de 35.

`scripts/audit_templates.py` confronte les deux noms par défaut au manifeste publié et
sort non nul si l'un disparaît.

### Le manifeste est lisible sans télécharger l'image

Le premier démarrage du conteneur clone les dépôts de templates : **59 secondes**,
mesurées. Imposer cela avant même le récapitulatif de l'assistant serait absurde.

`https://raw.githubusercontent.com/recyclarr/config-templates/master/templates.json`
répond en 0,3 s, et son contenu est **identique octet pour octet** (sha256 comparé) à ce
que Recyclarr clone. L'assistant lit donc le disque quand Recyclarr a déjà tourné — c'est
ce que cette installation-là connaît — et interroge le dépôt sinon. Sans réseau, les
noms restent saisissables, simplement non vérifiés : ne pas pouvoir lister n'est pas une
raison d'arrêter quelqu'un qui sait ce qu'il veut.

Vérifié de bout en bout avec un profil français : `french-multi-vf-hd-bluray-web` →
57 custom formats et le profil `[French MULTi.VF] HD Bluray + WEB` créés dans Radarr.

### Recyclarr refuse d'écraser, et `wire` doit rester idempotent

`config create` s'arrête sur `The file /config/configs/hd-bluray-web.yml already
exists`. Le refus est légitime : le fichier a pu être modifié à la main. Mais
`plugarr wire` est documenté comme rejouable, et il échouait donc au second passage.

PlugArr ne demande désormais que les templates **absents**. `--force` existe, mais
l'employer détruirait les réglages de l'utilisateur à chaque câblage.

Corollaire dans la lecture du résultat : un fichier déjà renseigné n'a plus de marqueur
à remplacer. Ce n'est pas un échec, c'est un second passage. Seul un marqueur *restant*
est un problème. Vérifié : trois `wire` d'affilée, tous `OK`, un seul appel à
`config create`.

### Le service visé est lu dans le YAML, pas dans le nom du fichier

`hd-bluray-web` est un titre de template, pas un nom de service. Se fier au nom de
fichier enverrait la clé de Radarr dans un fichier Sonarr. La clé racine du YAML fait
foi.

Un fichier laissé par une installation précédente — l'utilisateur avait Radarr, il l'a
retiré — garde ses marqueurs et fait échouer `recyclarr sync` avec un message obscur.
PlugArr le signale par son nom à la fin du câblage.

### Résultat, confirmé par Sonarr et Radarr eux-mêmes

Installation `sonarr,radarr,recyclarr` puis `recyclarr sync` :

| Vérification | Sonarr | Radarr |
|---|---|---|
| Custom formats créés | 37 | 40 |
| Tailles de qualité synchronisées | 14 | 14 |
| Profil créé | `WEB-1080p` | `HD Bluray + WEB` |
| Formats **notés** dans ce profil | 37 | 25 |

Les chiffres viennent de `GET /api/v3/qualityprofile` et `GET /api/v3/customformat`
interrogés avec la clé de chaque instance, pas des journaux de Recyclarr. Un profil dont
les formats seraient tous à zéro ne trierait rien : c'est le score qui compte, et il est
là.

### Détection de mise à jour sur ghcr.io

Le dépôt n'est pas sur Docker Hub : la voie générique du protocole registry v2
s'applique. Elle répond en ~1 s. Vérifié dans les deux sens, sans quoi « aucune mise à
jour » ne prouve rien :

- `8.7.1` → aucune plus récente (c'est bien la dernière) ;
- `7.4.1` → propose `8.6.0`, `8.7.0`, `8.7.1`.

---

## Docker Desktop sous Windows — vérifié le 2026-09-01

Le README oriente les utilisateurs Windows vers Docker. Restait à savoir si la promesse
centrale du projet — **le montage `/data` unique qui rend les hardlinks possibles** —
tient à travers un bind mount Docker Desktop. Elle n'avait été vérifiée que sur Linux
natif.

Elle tient. Dans un conteneur montant un chemin Windows (`-v C:/tmp/hltest:/data`) :

```
/data/torrents/film.mkv : 2 liens, inode 1970324838307120
/data/media/film.mkv    : 2 liens, inode 1970324838307120
```

Même inode, et une écriture par l'un des deux noms est visible par l'autre : c'est un
vrai lien, pas une copie. Un import *arr ne recopiera donc pas 40 Go.

Une réserve, cosmétique : côté Windows, la **taille** affichée pour le second nom peut
rester en retard (17 octets contre 23) alors que le contenu lu est bien le même. C'est
la couche de traduction de fichiers de Docker Desktop, pas le lien.

### L'emballage tient aussi

Installation depuis GitHub dans un environnement neuf, comme le ferait un inconnu :
`app.tcss` est bien embarqué dans le paquet, l'assistant démarre et sa feuille de style
est chargée. Sans cet artefact déclaré dans `pyproject.toml`, le wizard s'ouvrirait sans
aucun style chez tous les utilisateurs.

Le README indiquait `pipx install plugarr`. Le paquet n'est pas sur PyPI (HTTP 404) :
la commande échouait pour tout le monde. Corrigé en `pipx install git+https://…`.

---

## qui v1.27.0 et le câblage complet — vérifiés le 2026-09-01

Une installation du **catalogue entier** (11 services) sur Docker Desktop, suivie d'une
vérification service par service via leurs API. Elle a trouvé deux liens manquants ou
faux que le rapport annonçait pourtant comme posés.

### autobrr ne joignait pas Transmission

Le rapport affichait **19/20**. La cause :

```
error getting rpc info: http://transmission:9091: can't get session values:
'session-get' rpc method failed: can't unmarshal request answer body: invalid cha…
```

Transmission n'expose pas son RPC à la racine. Mesuré depuis le réseau de la pile :

| Adresse | Réponse |
|---|---|
| `http://transmission:9091/` | **301**, corps HTML |
| `http://transmission:9091/transmission/rpc` | **409** — la réponse normale, « il me faut un jeton de session » |

autobrr attend du JSON et s'étrangle sur le `<` du HTML. Confirmé contre son propre
endpoint de test : racine → **HTTP 500**, `/transmission/rpc` → **HTTP 204**.

Les *arr n'ont pas ce problème : leur gabarit de client de téléchargement porte un champ
`urlBase` distinct, rempli séparément.

### qui était installée sans être reliée

Plus gênant, parce qu'invisible dans le rapport : `qui` était déployée avec un simple
`depends_on: qbittorrent` et **aucune connexion**. L'utilisateur ouvrait une interface
qui lui redemandait l'adresse et les identifiants que PlugArr venait de générer. Flood,
lui, recevait bien son `--qburl` et ses identifiants au démarrage.

Quatre relevés sur l'instance, aucun devinable :

- **tout répond 428** tant que le premier compte n'existe pas, y compris la page de
  connexion. C'est le signal « installation à terminer », pas une panne ;
- le point d'entrée de cette création est `POST /api/auth/setup`, et il répond
  **400 « Setup already completed »** une fois joué. C'est ce qui rend l'étape rejouable ;
- une instance se déclare avec son **URL complète**. Passer `host` et `port` séparément
  est accepté avec un 201 rassurant, mais le port est perdu : qui enregistre
  `http://qbittorrent` et ne se connecte jamais. Vérifié dans les deux cas :

  | Forme envoyée | Enregistré | `connected` | `GET /torrents` |
  |---|---|---|---|
  | `host` + `port` | `http://qbittorrent` | **false** | 500 |
  | URL complète | `http://qbittorrent:8080` | **true** | 200 |

- **les doublons ne sont pas refusés.** Déclarer deux fois la même instance donne deux
  entrées. Sans vérification préalable, chaque `plugarr wire` en ajouterait une.

`GET /api/instances` expose `connected` et `connectionStatus` : le lien est donc validé
par qui elle-même, comme les *arr le sont par leur bouton *Test*.

### Recyclarr synchronise dès l'installation

La configuration était écrite mais la synchronisation attendait la planification
quotidienne. Juste après l'installation, Sonarr n'avait aucun profil TRaSH : celui qui
allait vérifier concluait que rien n'avait marché. Le câblage lance désormais la
première synchronisation et annonce les profils créés, lus dans la sortie de Recyclarr.

L'échec de cette synchronisation reste un **avertissement**, pas un échec : les fichiers
sont écrits et la planification réessaiera. Faire échouer le câblage afficherait
« 20/21 liens » alors que les vingt-et-un sont posés.

### Résultat : 21/21, et 27 vérifications indépendantes

| Lien | Vérifié par |
|---|---|
| Prowlarr → Sonarr, Radarr, Lidarr | `syncLevel=fullSync` dans `/api/v1/applications` |
| Prowlarr → Transmission, qBittorrent | `/api/v1/downloadclient` |
| Sonarr, Radarr, Lidarr → les deux clients | `enable=true` dans `/downloadclient` |
| Sonarr, Radarr, Lidarr → dossier racine | `/rootfolder` |
| Sonarr, Radarr → Jellyfin | `/notification` |
| Recyclarr → Sonarr, Radarr | profils et custom formats dans `/qualityprofile` |
| autobrr → 5 services | `/api/download_clients` |
| qui → qBittorrent | `connected: true` |
| Jellyfin | trois bibliothèques dans `/Library/VirtualFolders` |
| Flood → qBittorrent | arguments de démarrage du conteneur |

Un piège pour qui referait cette vérification : **Lidarr expose `v1`**, pas `v3`. Mon
premier script l'interrogeait en v3, recevait 404 et rapportait trois faux échecs.
`catalog.py` avait raison depuis le début.

---

## Prowlarr laissait son interface inaccessible — corrigé le 2026-09-01

Signalé par un utilisateur : « j'ai voulu me connecter à Prowlarr, identifiants
incorrects ». Le rapport annonçait pourtant un identifiant et un mot de passe, et le
câblage affichait tous ses liens en vert.

### Ce qui se passait

Le pré-semis écrit `<Username>`, `<Password>` et `<PasswordConfirmation>` dans
`config.xml`. Sonarr 4.0.19, Radarr 6.3.0 et Lidarr 3.1.0 les consomment au premier
démarrage, créent le compte en base, puis effacent ces lignes du fichier.

**Prowlarr 2.5.2 les efface aussi — sans créer personne.** Reproduit sur un conteneur
jetable, configuration neuve :

| | `Users` en base | `POST /login` |
|---|---|---|
| Sonarr, Radarr, Lidarr | `[('plugarr', …)]` | 302 vers `/` |
| Prowlarr | **`[]`** | 302 vers `/login?loginFailed=true` |

Et sa page de connexion n'offre **aucune création de compte**. Avec
`AuthenticationRequired=Enabled`, l'interface devenait donc définitivement
inaccessible.

Le plus gênant : rien ne le signalait. Le câblage passe par la clé API, qui fonctionnait
parfaitement. Les vingt-et-un liens étaient réellement posés. La seule façon de voir la
panne était d'essayer de se connecter — ce qu'aucune vérification ne faisait.

### La correction

Une étape de câblage par *arr, qui **poste le formulaire de connexion comme un
navigateur**. Un succès redirige vers la racine, un échec vers
`/login?...loginFailed=true`.

Si la connexion échoue, le compte est créé par la voie supportée :
`PUT /api/v1/config/host/{id}` avec `username`, `password` et `passwordConfirmation` —
l'application hache le mot de passe elle-même. Vérifié : **202**, la ligne apparaît dans
`Users` avec ses 10 000 itérations, et la connexion aboutit.

Si elle fonctionne déjà, **rien n'est écrit** : réécrire un mot de passe correct serait
une modification pour rien.

Sur une installation neuve de six services :

```
OK sonarr: acces web - connexion verifiee
OK radarr: acces web - connexion verifiee
OK lidarr: acces web - connexion verifiee
OK prowlarr: acces web - compte cree
```

Les quatre identifiants annoncés ouvrent ensuite réellement leur interface.

### Ce que cet épisode dit de la méthode

La règle du projet est de faire valider chaque lien par l'application cible. Elle était
appliquée aux liens entre services, pas à l'accès de l'utilisateur lui-même. Une
vérification qui n'emprunte pas le chemin de l'utilisateur ne prouve rien sur ce
chemin-là.

---

## Mots de passe : caractères spéciaux — vérifié le 2026-09-01

Demandé à l'usage : des mots de passe aléatoires d'au moins 12 caractères, mêlant
lettres, chiffres et caractères spéciaux.

Ils étaient déjà aléatoires — `secrets.choice`, 20 caractères, différents à chaque
installation — mais **uniquement alphanumériques**.

### Pourquoi l'alphabet spécial est court

Ces valeurs traversent un `.env` lu par Docker Compose, une ligne de commande de
conteneur, un XML, un INI et plusieurs charges JSON. Le danger a été mesuré, pas
supposé :

```
.env :        PASS_NU=abc$HOME!def
compose voit : abcC:\Users\darkl!def
```

Compose interprète `$` comme une interpolation de variable **dans le fichier `.env`
lui-même**. Un mot de passe en contenant arriverait déformé dans le conteneur, et
l'utilisateur ne pourrait jamais se connecter.

Sont donc exclus : `$`, l'apostrophe (elle fermerait la valeur), le guillemet,
l'antislash, le backtick, `#`, et tout métacaractère de shell — le `.env` est parfois
sourcé par un script, y compris dans la CI de ce dépôt.

Restent 13 caractères spéciaux, soit 75 possibles au total : environ **125 bits**
d'entropie sur 20 positions.

Les valeurs du `.env` sont désormais écrites entre apostrophes. Vérifié : une valeur
protégée contenant `$` arrive **intacte** dans le conteneur, là où la même valeur nue
était interpolée. Les chemins sont protégés de la même façon — par cohérence, pas par
nécessité : un chemin contenant une espace fonctionnait déjà.

### La vérification qui compte : le pire cas

Un tirage au hasard aurait probablement fonctionné. Une installation des dix services a
donc été faite avec, pour **tous** les comptes, le mot de passe le plus hostile possible :

```
Aa1!@%^*-_=+.,:?zZ9
```

24 liens sur 24, puis douze vérifications indépendantes :

| Vérification | Résultat |
|---|---|
| `.env` protégé et relisible | valeur exacte |
| `docker compose config` | valide |
| Sonarr, Radarr, Lidarr, Prowlarr | connexion web, redirection vers `/` |
| qBittorrent | HTTP 204 + cookie de session |
| Transmission | authentification RPC, HTTP 200 |
| autobrr, qui | HTTP 204 / 200 |
| Jellyfin | HTTP 200 |
| Flood | mot de passe transmis intact en argument |

Une seule ligne a d'abord échoué : celle de qBittorrent. C'était **le test qui avait
tort**. L'ancienne API répondait `200 Ok.` ; la 5.2.3 répond **204** et pose un cookie
`SID`, et refuse par un **401**. L'empreinte PBKDF2 stockée correspondait bien au mot de
passe, recalcul à l'appui.

### Les installations existantes ne changent pas

Les mots de passe vivent dans `stack.yml`. Une stack déjà installée garde les siens :
seules les nouvelles installations reçoivent le nouvel alphabet.

---

## Exécutable Windows — vérifié le 2026-09-01

Objectif : retirer le dernier prérequis qui restait à un utilisateur Windows, installer
Python. PyInstaller 6.22.2, un seul fichier, mode console.

### Trois obstacles, aucun devinable

**Le point d'entrée évident ne marche pas.** `src/plugarr/__main__.py` fait un import
relatif (`from .cli import app`), et PyInstaller exécute son script d'entrée comme un
module de premier niveau, sans paquet parent :

```
ImportError: attempted relative import with no known parent package
```

D'où `packaging/launcher.py`, qui ne fait rien d'autre qu'un import absolu.

**`app.tcss` doit être embarqué explicitement.** Sans lui, Textual lève
`StylesheetError` au démarrage et l'assistant ne s'ouvre pas. Vérifié en construisant
volontairement sans le fichier : l'exécutable s'arrête, code de sortie 1.

**Le chemin de `--add-data` est relatif au fichier `.spec`**, pas au répertoire courant.
Avec `--specpath`, un chemin relatif fait échouer la construction sur un
`Unable to find … when adding binary and data files` déroutant.

### Ce qui a été vérifié sur le binaire produit

| Vérification | Résultat |
|---|---|
| Catalogue, aide, liste des templates (réseau) | conformes |
| Préflight Docker | daemon et compose détectés |
| Assistant Textual | **137 règles** de style, 11 services affichés |
| Installation complète | **14/14 liens**, 168 secondes |
| Autonomie | fonctionne avec `PATH` vidé et `PYTHONHOME` invalide |
| Taille et démarrage | 20,5 Mo, ~1,5 s |

### Ce qui est publié, et comment

`.github/workflows/windows-exe.yml` construit le binaire sur `windows-latest` à chaque
poussée, le contrôle, puis l'attache à la release sur un tag `v*`.

Le contrôle ne se contente pas de vérifier que le fichier existe : il construit un
second exécutable jetable à partir de `packaging/smoke_tui.py`, qui démarre réellement
l'assistant et compte les règles de style chargées. C'est la seule façon d'attraper une
feuille de style oubliée, panne invisible tant que personne ne lance le binaire.

Le binaire n'est pas signé. Windows SmartScreen affichera donc un avertissement au
premier lancement, ce que le README annonce plutôt que de le laisser surprendre.

---

## Windows n'avait aucun profil — corrigé le 2026-09-01

Signalé à l'usage, capture à l'appui : l'assistant, lancé depuis l'exécutable sur
Windows, ne proposait que `generic-linux`, `unraid` et `synology`. L'utilisateur avait
choisi **unraid**, et se retrouvait donc avec `/mnt/user/appdata/plugarr` et
`/mnt/user/data` sur une machine Windows.

### Ce que faisaient ces chemins

Rien de visible, et c'est le problème. Docker Desktop les crée à la racine du disque
courant : `/mnt/user/data` devient `C:\mnt\user\data`. L'installation réussit, les
conteneurs démarrent, et les fichiers atterrissent dans un dossier que personne n'a
voulu.

Le bouton *Vérifier les chemins* répondait même « hardlink OK » — techniquement vrai,
puisqu'il venait de créer ce dossier parasite.

### Trois corrections

**Un profil `windows`**, avec `C:/plugarr/config` et `C:/plugarr/data`. Le profil
présélectionné est désormais celui de la machine, dans l'assistant comme en ligne de
commande (`--platform` prend la même valeur par défaut).

**PUID/PGID expliqué.** « 1000:1000 » ne dit rien à qui n'a jamais administré un système
Unix, et cette valeur décide pourtant de qui possédera les fichiers téléchargés. Une
ligne le dit maintenant. Sur le profil Windows, l'avertissement jaune « non détectables »
disparaît : sous Docker Desktop ces identifiants n'ont aucun effet, et l'écrire
inquiétait pour rien.

**La vérification dit où le dossier atterrit.** Elle affiche le chemin résolu, et
signale un chemin incohérent avec la machine :

```
« /mnt/user/data » n'est pas un chemin Windows. Il sera cree dans
C:\mnt\user\data, ce qui n'est probablement pas voulu.
```

### Un défaut trouvé par les tests

La première version de ce contrôle utilisait `[\/]` au lieu de `[\/]`. Dans une classe
de caractères, `\/` ne vaut que la barre oblique : la forme fautive ne reconnaissait
**aucun** chemin à antislash, pas même `C:\Users\...`, et les signalait tous comme « pas
un chemin Windows ». Deux tests l'ont attrapée avant toute publication.

---

## Réinstaller sur une configuration existante — corrigé le 2026-09-01

Signalé à l'usage, capture à l'appui : une installation relancée sur un `config_root`
déjà utilisé donnait 19 liens sur 25, avec des messages incompréhensibles — « réponse
illisible sur les catégories », « HTTP 401 », « l'API d'autobrr a peut-être changé de
forme », « qui n'est jamais devenu disponible ».

Une seule cause de départ, et quatre défauts qu'elle a révélés.

### La cause : des mots de passe annoncés mais jamais appliqués

Les dossiers de configuration dataient de la veille, l'installation était de l'heure.
PlugArr conservait les configurations existantes **mais générait de nouveaux mots de
passe**, qu'il affichait dans son rapport. Les services refusaient donc les identifiants
montrés à l'utilisateur. Vérifié : l'empreinte PBKDF2 stockée dans `qBittorrent.conf` ne
correspondait pas au mot de passe du `stack.yml`.

qBittorrent et Transmission sont désormais **réalignés** : seules les deux lignes
d'identification sont réécrites, le reste du fichier appartient à l'utilisateur.

### Écrire pendant qu'un conteneur tourne ne sert à rien

qBittorrent garde sa configuration en mémoire, et Transmission **réécrit son
`settings.json` en s'arrêtant** — notre correction aurait été effacée quelques minutes
plus tard. L'installation arrête donc les conteneurs existants *avant* le pré-semis.

### Le préflight refusait nos propres ports

Une pile en marche occupe ses ports. Le préflight les déclarait « déjà utilisés » et
bloquait — c'est-à-dire exactement le cas le plus courant, réinstaller après un premier
essai. Les ports publiés par le projet en cours sont maintenant reconnus comme siens.

### Le bannissement d'adresse de qBittorrent

Après cinq échecs d'authentification, qBittorrent bannit l'adresse pour une heure. Une
installation qui s'est trompée de mot de passe fait donc bannir l'adresse de Sonarr. La
suite est cruelle : le mot de passe redevient correct, mais le *arr reçoit un 403 et
répond « Authentication Failure », en accusant les identifiants.

Mesuré au même instant, avec le même mot de passe :

| Depuis | Réponse |
|---|---|
| l'hôte | **204** |
| le conteneur Sonarr | **403** |

Le seuil est relevé à 100 dans la configuration semée — la protection contre une force
brute reste utile, elle ne doit simplement pas viser nos propres conteneurs.

Une réparation subsiste en secours (redémarrage puis nouvel essai), **strictement
limitée aux refus d'authentification**. L'avoir élargie à tout échec de test a fabriqué
la panne suivante : le redémarrage invalidait l'adresse mise en cache par Sonarr, qui
échouait alors sur « Unable to connect ». Le remède créait le symptôme.

### Ce qui reste impossible, et qui est maintenant dit

Jellyfin, autobrr et qui ne stockent leur mot de passe que **haché**, et aucune API ne
permet de le réinitialiser sans lui. PlugArr ne peut donc pas reprendre ces trois
services. Le préflight l'annonce avant de commencer, et chaque échec porte désormais la
phrase utile : supprimez ce dossier, ou reprenez l'installation d'origine avec
`--project-dir`.

### Résultat

| Scénario | Avant | Après |
|---|---|---|
| Installation neuve, 8 services | — | **19/19** |
| Réinstallation, mêmes dossiers | 19/25 | tous les clients de téléchargement câblés, seuls les trois services à mot de passe haché refusent, avec l'explication |

### Un plantage, aussi

Saisir un tracker puis cliquer sur *Ajouter* fermait la fenêtre. `add` protégeait son
appel HTTP, mais pas `configured()` ni `app_profile_id()`, qui interrogent Prowlarr eux
aussi : une exception dans un worker Textual arrête l'application, et l'utilisateur perd
sa saisie **et** l'explication. Les quatre workers de l'assistant sont désormais
étanches, et la trace part dans le journal.

---

## Trois demandes d'utilisateur — 2026-09-01

### « Demander si on garde ou si on supprime »

La détection d'une configuration héritée ne servait qu'à afficher un
avertissement. L'assistant propose désormais le choix, et la ligne de commande
pose la question (`--reset-config` / `--keep-config` pour y répondre d'avance).

Sans réponse explicite, **on conserve** : effacer la configuration de quelqu'un
par défaut serait inacceptable. `--yes` répond aux questions, pas aux
suppressions.

La suppression est bornée par trois verrous, écrits pour être lisibles d'un coup
d'œil : seuls des services du catalogue sont acceptés, le dossier doit se
trouver sous `config_root` **après résolution des liens symboliques**, et
`data_root` n'est jamais parcouru. Un test crée un lien qui sort de la racine et
vérifie que la suppression est refusée, le fichier visé toujours là.

### « Un menu avec des choix sélectionnables par clic »

L'écran des profils de qualité demandait de **taper** un nom, en n'en montrant
que six sur vingt-deux. Personne ne peut deviner les seize autres.

Une liste déroulante cliquable les remplace, remplie depuis le manifeste :
22 profils pour Sonarr, 35 pour Radarr. Le contrôle de nom reste, mais il ne
peut plus se déclencher par une faute de frappe.

### « Ouvrir automatiquement la page HTML à la fin »

La ligne de commande le faisait déjà ; l'assistant se contentait d'un bouton.
C'est pourtant là que la page sert : elle porte les adresses et les identifiants
qui viennent d'être annoncés. Elle s'ouvre maintenant seule, et le bouton reste
pour les machines sans navigateur — un NAS en ligne de commande, par exemple.

Deux garde-fous : rien ne s'ouvre si le fichier n'existe pas, et le générateur
de captures comme les tests désactivent l'ouverture. Lancer un navigateur
pendant une CI n'aurait aucun sens.

---

## L'identifiant se choisit — 2026-09-01

Demandé à l'usage : « pas tout le monde veut mettre PlugArr comme username ».

Un seul endroit du code fixait ce nom ; tout le reste n'était qu'un repli. Il est
maintenant porté par `StackConfig`, exposé par `--username` et par un champ de
l'assistant, et il atteint les cinq familles de services.

### La contrainte de forme, et ce qu'elle vaut vraiment

Première version : minimum trois caractères, « parce que qBittorrent les exige ».
**C'était faux.** Vérifié sur qBittorrent 5.2.3 avec une configuration semée pour
l'identifiant `ab` : la connexion répond **204**. La règle a été ramenée à un
caractère, et le commentaire corrigé.

Ce qui reste contraint, en revanche, l'est pour une raison réelle : ce nom finit dans un
XML, un INI, un JSON, un formulaire de connexion et une ligne de commande de conteneur.
Espaces, accents et ponctuation exotique y passeraient peut-être — mais « peut-être » ne
convient pas pour une valeur qu'on ne peut plus changer sans tout réinstaller. D'où
`[A-Za-z0-9._-]{1,32}`.

### Vérifié sur une installation réelle

`--username yannick`, six services, 17 liens sur 17, puis connexion à chacun avec ce
nom :

| Service | Connexion |
|---|---|
| Prowlarr, Sonarr, Radarr | redirection vers `/` |
| qBittorrent | HTTP 204 |
| Transmission | RPC 200 |
| Jellyfin | HTTP 200 |

---

## La page figée et les versions épinglées — 2026-09-01

Deux remarques d'usage le même jour : « quand je me suis connecté à qui, je n'avais pas
la dernière version », et « la page ne me dit pas s'il y a une mise à jour, et ne me
permet pas d'arrêter ou relancer une instance ».

### Le catalogue vieillit, et il faut le mesurer

Chaque tag du catalogue a été confronté à son registre. Dix services sur onze étaient à
jour ; **`qui` accusait une version de retard**, v1.27.0 contre v1.28.0.

La nouvelle version a été vérifiée avant d'être épinglée, comme le veut la règle du
projet : 428 avant création du compte, 201 sur `POST /api/auth/setup`, 200 à la
connexion, 201 sur la déclaration d'instance, relecture correcte. Comportement
identique.

Le contrôle complet tient en une commande et mérite d'être rejoué avant chaque
publication :

```
for sid in catalog.STARTUP_ORDER: updates.newer_tags(catalog.get(sid).image)
```

### « La page ne me permet pas d'arrêter une instance »

C'était exact, et voulu : la page d'accès est un fichier figé, sans serveur derrière.
L'état des services, les boutons et les mises à jour viennent de `plugarr serve`.

Le défaut n'était donc pas dans la page, mais dans le chemin pour y arriver. Elle
affichait « lancez `plugarr serve` » — une commande inutile pour quelqu'un qui vient de
double-cliquer un exécutable absent du PATH.

Un lanceur `administration.cmd` (`administration.sh` ailleurs) est désormais déposé à
côté des artefacts. Il porte le chemin réel de l'exécutable utilisé pour cette
installation, et `--project-dir` pointant sur le bon dossier — sans quoi `serve`
chercherait un `stack.yml` là où le double-clic a eu lieu.

Vérifié en le lançant comme le ferait un double-clic : la page d'administration répond,
HTTP 401 sans jeton, ce qui est exactement le comportement attendu.
