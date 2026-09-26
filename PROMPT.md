# PROMPT DE DÉMARRAGE — Auto-installeur / auto-configurateur de stack média *arr

> Document de cadrage à donner à un agent (ou à suivre soi-même) pour démarrer le projet.
> Objectif secondaire assumé : un dépôt GitHub attractif, qui gagne des étoiles.

---

## 1. Vision en une phrase

Un outil qui **déploie ET câble automatiquement** une stack média self-hosted complète
(*arr + client de téléchargement + serveur média + demandes utilisateurs + livres),
avec choix à la carte des services et des chemins, de sorte qu'à la fin du wizard
**tout se parle déjà** : clés API échangées, indexeurs synchronisés, dossiers racine
créés, clients de download rattachés, bibliothèques scannées.

Le « produit » n'est pas le `docker-compose.yml`. Des dizaines de dépôts font ça.
Le produit est **le moteur de configuration croisée**.

---

## 2. Positionnement / concurrence (à lire avant d'écrire du code)

Analyse obligatoire de l'existant avant de coder, pour ne pas refaire :

| Projet | Ce qu'il fait | Ce qu'il ne fait PAS |
|---|---|---|
| DockSTARTer | déploie beaucoup de conteneurs, menu ncurses | ne câble quasiment rien entre apps |
| Saltbox / Cloudbox | stack Ansible très complète | lourd, opinionated, Linux/serveur only |
| geekau/mediastack | compose files bien documentés | config manuelle après coup |
| Recyclarr / Configarr | sync des profils qualité TRaSH | ne déploie rien, ne câble pas les clés API |
| Wikis Servarr / TRaSH Guides | la référence doc | 100 % manuel |

**Le trou dans le marché = déploiement + câblage complet + profils qualité, en un seul wizard.**
C'est ça le pitch du README. Il doit être visible dans les 5 premières lignes.

Action attendue : produire un fichier `docs/PRIOR-ART.md` avec ce comparatif,
vérifié réellement (lire les README, pas de mémoire), avant la phase 1.

---

## 3. Catalogue des services (périmètre)

### Cœur *arr
- **Prowlarr** — gestionnaire d'indexeurs, pivot du câblage
- **Sonarr** — séries
- **Radarr** — films
- **Lidarr** — musique
- **Bazarr** — sous-titres
- **Whisparr** — (optionnel, opt-in explicite)
- ~~Readarr~~ — **RETIRÉ le 27 juin 2025**, projet archivé, métadonnées mortes.
  Ne pas l'inclure. Le mentionner dans la doc avec la liste des remplaçants.

### Clients de téléchargement
- **Transmission** — client par défaut (décision actée). Daemon léger, RPC stable et
  documenté, image LinuxServer mature.
- **qBittorrent** — alternative recommandée, WebUI API v2 bien documentée.
- **Deluge**
- **SABnzbd** (usenet)
- **NZBGet** (usenet)
- **Flood** ([jesec/flood](https://github.com/jesec/flood)) — vérifié actif au 30/08/2026,
  2,8k étoiles, TypeScript, image Docker officielle `jesec/flood`.
  ⚠️ **Flood n'est PAS un client de téléchargement**, c'est une **UI web** posée sur un
  client existant. Supporte rTorrent, qBittorrent et Transmission (testés) + Deluge
  (expérimental). Conséquence pour l'architecture : les *arr continuent de parler au
  **RPC Transmission**, jamais à Flood. Flood est une couche cosmétique → un conteneur
  de plus, une tuile de plus dans le dashboard, **zéro impact sur la matrice de câblage**.
  Option peu coûteuse et très visible : case à cocher « jolie UI pour Transmission ».
- ~~µTorrent~~ — **HORS PÉRIMÈTRE (décision actée)**. Closed-source, Windows-only, pas
  d'image Docker officielle, historique d'adware, API WebUI non documentée. Documenter
  ce refus dans la FAQ et rediriger vers Transmission.

### Serveurs média
- **Jellyfin** (le mieux automatisable : API de wizard de démarrage)
- **Plex** (nécessite un claim token plex.tv/claim, TTL ~4 min → étape interactive)
- **Emby** (optionnel)
- **Audiobookshelf** (livres audio / podcasts)

### Demandes utilisateurs
- **Seerr** ([`seerr-team/seerr`](https://github.com/seerr-team/seerr)) — Jellyfin, Emby
  et Plex. Image `seerr/seerr`.
- ~~Jellyseerr~~ et ~~Overseerr~~ — **fusionnes dans Seerr le 10 fevrier 2026**, tous
  deux deprecies. `sct/overseerr` est archive ; `fallenbagel/jellyseerr` redirige vers
  `seerr-team/seerr`. Seerr migre automatiquement les donnees au premier demarrage.
  Ne pas les inclure.

### Livres / audiobooks (remplaçants de Readarr)
- **Shelfmark** — `calibrain/shelfmark`. Interface de recherche/demande de livres et
  audiobooks, sources web/torrent/usenet/IRC configurables, métadonnées Hardcover /
  Open Library / Google Books. Évolution de Calibre-Web-Automated-Book-Downloader.
- **Shelfarr** — [`Pedro-Revez-Silva/shelfarr`](https://github.com/Pedro-Revez-Silva/shelfarr)
  (**cible confirmée**). « Jellyseerr pour les livres » :
  demandes utilisateurs → recherche via indexeurs **Prowlarr** / Jackett / Newznab →
  download via Transmission / qBittorrent / SABnzbd / Deluge / NZBGet →
  livraison dans **Audiobookshelf**.
  L'image officielle persiste ses bases SQLite et sa clé générée sous
  `/rails/storage`. Son Compose courant inclut un compagnon Libation interne,
  sans port hôte, pour la sauvegarde Audible optionnelle. Voir §11.2. Le fork
  `presswizards/abs-shelfarr` est abandonné, l'ignorer.
  ⚠️ Intègre une source « Anna's Archive » : **ne jamais la préactiver**, voir §11.3.
- Optionnel : **Calibre-Web**, **LazyLibrarian**.

**Note d'intégration importante** : Shelfarr consomme Prowlarr et un client de download.
C'est donc un **nœud de câblage de premier plan**, pas un simple conteneur à poser.
Shelfmark est plus autonome. Lire leur documentation d'API réelle avant d'écrire l'intégration.

### Support / infra (optionnel mais gros différenciateur)
- **Gluetun** — VPN pour isoler le client torrent (kill-switch)
- **FlareSolverr** — contournement Cloudflare pour certains indexeurs
- **Traefik** / **Caddy** / **Nginx Proxy Manager** — reverse proxy + TLS
- **Homepage** ou **Homarr** — dashboard listant tous les services déployés,
  **généré automatiquement** à partir de la sélection de l'utilisateur (effet « wow »)
- **Tautulli** — stats Plex
- **Recyclarr** — sync des profils qualité TRaSH Guides
- **Watchtower** / **Diun** — mises à jour

---

## 4. Décisions d'architecture à acter

### 4.1 Docker en premier, natif jamais (ou presque)
L'installation native multi-OS de la suite *arr avec configuration automatique est
ingérable. **Docker Compose est la cible unique de la v1.**
Le « chemin d'installation » demandé par l'utilisateur devient :
- un **chemin de config** (`${CONFIG_ROOT}`) — un sous-dossier par service
- un **chemin de données** (`${DATA_ROOT}`) — médias + téléchargements

### 4.2 Layout de données : LE point critique
Erreur n°1 de 90 % des stacks média : les hardlinks ne fonctionnent pas et
chaque import recopie les fichiers. Cause : montages Docker séparés
(`/downloads` et `/media` = deux systèmes de fichiers vus par le conteneur).

**Imposer un montage unique `/data` dans TOUS les conteneurs concernés** :

```
${DATA_ROOT}/
├── torrents/
│   ├── movies/  tv/  music/  books/
├── usenet/
│   ├── incomplete/
│   └── complete/{movies,tv,music,books}/
└── media/
    ├── movies/  tv/  music/  books/
```

Montage : `- ${DATA_ROOT}:/data` partout. Rien d'autre.
Ceci doit être **documenté dans le README avec un schéma** — c'est un argument de vente.
Ajouter une **commande de diagnostic** `doctor` qui teste réellement qu'un hardlink
est possible entre `/data/torrents` et `/data/media`.

### 4.3 PUID / PGID / UMASK
Un seul couple UID/GID pour toute la stack (convention LinuxServer.io),
détecté automatiquement sur Linux/macOS, avec valeur par défaut sur Windows/WSL.
`UMASK=002`. Vérifier les permissions avant de démarrer, pas après.

### 4.4 Le coup de génie du câblage : pré-semer les clés API
Ne **pas** démarrer les conteneurs puis aller lire la clé générée.
À la place :

1. Générer une clé API (32 hex) par app côté installeur.
2. Écrire un `config.xml` minimal dans `${CONFIG_ROOT}/<app>/` **avant** le premier
   démarrage, contenant `<ApiKey>`, `<Port>`, `<UrlBase>`, `<AuthenticationMethod>`.
3. Démarrer. L'app adopte la clé que l'on connaît déjà.

→ Le câblage devient **déterministe et rejouable**, plus de course au démarrage.
S'applique à Sonarr, Radarr, Lidarr, Prowlarr (et Whisparr).
**À vérifier expérimentalement pour chaque app avant de s'y fier.**

Même logique pour qBittorrent : pré-écrire `qBittorrent.conf` avec un hash de mot de
passe PBKDF2 plutôt que subir le mot de passe temporaire aléatoire généré au premier
démarrage depuis la 4.6.x.

### 4.5 Appeler les API via leur endpoint `/schema`
Ne jamais hardcoder le payload JSON d'un download client ou d'une application.
Les *arr exposent des endpoints de schéma qui renvoient le gabarit exact de champs
pour chaque implémentation. Le flux robuste est :

```
GET  /api/v3/downloadclient/schema   → trouver l'implémentation voulue
     remplir les champs du gabarit
POST /api/v3/downloadclient          → créer
```

Cela rend l'outil résistant aux changements de version des *arr.
C'est ce qui différenciera ce projet des scripts qui cassent à chaque release.

### 4.6 Attente de disponibilité
Chaque app est considérée prête uniquement quand son endpoint de statut répond
avec la bonne clé API. Backoff exponentiel, timeout, message d'erreur exploitable.
Pas de `sleep 30`.

---

## 5. Matrice de câblage à implémenter

À traiter comme un graphe de dépendances, résolu dans l'ordre topologique.

| Source | Cible | Ce qui est configuré |
|---|---|---|
| Prowlarr | Sonarr / Radarr / Lidarr | ajout en « Application », sync des indexeurs, catégories |
| Prowlarr | client download | ajout du client, catégories |
| Prowlarr | FlareSolverr | proxy indexeur |
| Sonarr / Radarr / Lidarr | client download | host/port/user/pass/catégorie |
| Sonarr / Radarr / Lidarr | système de fichiers | dossier racine `/data/media/...` |
| Sonarr / Radarr | Jellyfin / Plex / Emby | notification « rafraîchir la bibliothèque » |
| Bazarr | Sonarr / Radarr | via son fichier de config (ip, port, apikey) |
| Seerr | Sonarr / Radarr | serveurs + profils qualité + dossiers |
| Seerr | Jellyfin / Plex | serveur média + bibliothèques |
| Jellyfin | système de fichiers | création des bibliothèques via l'API de wizard |
| Plex | système de fichiers | claim token + bibliothèques |
| Audiobookshelf | système de fichiers | bibliothèques livres / podcasts |
| Shelfarr | Prowlarr + client download + Audiobookshelf + Libation interne | volumes et topologie générés ; réglages applicatifs manuels jusqu'à vérification d'une API publique |
| Flood | Transmission (RPC) | UI seule, aucun impact sur le reste du câblage |
| Shelfmark | sources + client download | à établir depuis sa doc réelle |
| Recyclarr | Sonarr / Radarr | profils qualité + custom formats TRaSH |
| Homepage / Homarr | tous | widgets générés avec les clés API |
| Gluetun | client torrent | `network_mode: service:gluetun`, ports remappés |

**Règle absolue : ne rien deviner.** Pour chaque intégration, vérifier l'endpoint réel
contre la doc/swagger de la version ciblée, ou contre une instance qui tourne.
Épingler les versions d'images. Documenter la version testée dans `docs/COMPATIBILITY.md`.

---

## 6. Stack technique — DÉCISION ACTÉE

**Python 3.12+.** Décision prise, à consigner dans `docs/adr/0001-stack.md`.

```
core/   moteur : modèle de services, génération compose, clients API, graphe de câblage
        → testable sans Docker, entièrement mockable. Le vrai actif du projet.
cli/    Typer   — mode non interactif, CI-friendly, --config stack.yml
tui/    Textual — wizard interactif (c'est le GIF du README)
web/    phase 5 — wizard navigateur, optionnel
```

**Pourquoi Python plutôt que Go**, malgré l'avantage du binaire statique :
1. Le travail réel est de l'orchestration HTTP / JSON / YAML. Aucun besoin de performance.
2. La communauté homelab et *arr contribue en Python et en shell, pas en Go.
   Plus de contributeurs potentiels = plus d'étoiles. C'est l'objectif déclaré.
3. Textual donne un wizard terminal spectaculaire pour un coût très faible.
4. L'argument « pas de Python sur un NAS » est neutralisé par la distribution ci-dessous.

**Distribution — deux chemins, aucun n'installe Python sur l'hôte :**
- `uvx <nom>` pour ceux qui ont `uv` (exécution à la volée, environnement isolé)
- une **image installeur** qui pilote le Docker de l'hôte via le socket monté.
  C'est le chemin par défaut documenté pour Unraid et Synology, où l'on ne veut
  rien installer sur le système.

Le fichier d'état canonique est un **`stack.yml` versionnable** décrivant la sélection,
les chemins et les ports. `docker-compose.yml` et `.env` en sont des **artefacts générés**,
jamais édités à la main. C'est ce qui rend l'outil idempotent et diffable.

---

## 6bis. Profils de plateforme — cible NAS / Linux (DÉCISION ACTÉE)

Cible prioritaire : **NAS et serveur Linux**. Windows n'est pas une cible native ;
les utilisateurs Windows passent par Docker Desktop + WSL2, documenté mais non optimisé.

Introduire dès la v1 une notion de **profil de plateforme**, qui ne fait que fixer des
valeurs par défaut. Peu coûteux, très visible :

| Profil | PUID / PGID par défaut | Racines par défaut | Notes |
|---|---|---|---|
| `generic-linux` | UID/GID de l'utilisateur courant | `/opt/mediastack`, `/srv/data` | défaut |
| `unraid` | `TODO(verify)` | `/mnt/user/appdata`, `/mnt/user/data` | Compose via le plugin Docker Compose Manager |
| `synology` | `TODO(verify)` | `/volume1/docker`, `/volume1/data` | Compose via Container Manager (DSM 7.2+) |

**Ne pas deviner les UID/GID ni les chemins.** Les vérifier dans la documentation
officielle de chaque plateforme, prévoir une détection automatique quand elle est
fiable, et toujours faire confirmer par l'utilisateur à l'étape récapitulatif.

**Hors v1** : soumettre un template Community Applications à Unraid. Cela demande une
PR modérée sur un dépôt communautaire — à faire en phase 4/5, une fois le projet stable.
Un template soumis trop tôt et cassé nuit plus qu'il n'aide.

---

## 7. Parcours utilisateur cible

```
1.  Préflight      Docker présent ? version ? permissions ? ports libres ?
                   espace disque ? hardlink possible ?
                   → rapport clair, refus propre si bloquant
2.  Profil         « Débutant tout-en-un » | « Sur mesure » | « Importer un stack.yml »
3.  Sélection      cases à cocher par catégorie, dépendances auto-résolues
                   (Bazarr → propose Sonarr/Radarr ; Shelfarr → exige Prowlarr)
4.  Chemins        CONFIG_ROOT, DATA_ROOT, validation live + aperçu de l'arborescence
5.  Options        VPN ? reverse proxy + domaine ? fuseau ? PUID/PGID ? profils TRaSH ?
6.  Récapitulatif  tableau services / ports / URLs / volumes — AVANT toute écriture
7.  Génération     arborescence, .env, docker-compose.yml, config.xml pré-semés
8.  Démarrage      up, attente de disponibilité, progression par service
9.  Câblage        exécution du graphe, une ligne de log lisible par lien créé
10. Vérification   chaque lien est relu depuis l'API pour confirmation
11. Rapport        tableau final : URLs cliquables, identifiants, prochaines étapes
```

Toute étape doit être ré-exécutable. `install` lancé deux fois = même état, zéro doublon.

---

## 8. Contraintes non négociables

1. **Idempotence.** Vérifier l'existence avant chaque création. Jamais de doublon de
   download client, d'application Prowlarr ou de dossier racine.
2. **Dry-run.** `--dry-run` affiche tout ce qui serait fait, n'écrit rien.
3. **Sauvegarde.** Snapshot de `${CONFIG_ROOT}` avant toute modification destructive.
4. **Secrets.** `.env` en `chmod 600`, `.gitignore` généré, masquage systématique des
   clés dans les logs, jamais de secret commité.
5. **Erreurs exploitables.** Chaque échec dit : quoi, pourquoi, comment corriger.
   Une commande `doctor` diagnostique une installation existante.
6. **Désinstallation propre.** `uninstall` avec choix : conteneurs seuls / + config /
   + données (triple confirmation sur les données).
7. **Cross-platform.** Linux, macOS, Windows (Docker Desktop + WSL2). Les chemins
   Windows sont un piège : normaliser et tester réellement, pas en théorie.
8. **Zéro indexeur préconfiguré.** Le projet ne fournit ni tracker, ni indexeur, ni
   contenu. Position légale nette dans le README et dans `DISCLAIMER.md` : outil
   d'automatisation de médiathèque personnelle, usage légal uniquement.
   Ce point protège le dépôt et sa visibilité.
9. **Tests.** Le moteur de câblage doit être testé contre des serveurs API mockés.
   Un job CI qui monte une stack minimale (Prowlarr + Sonarr + qBittorrent) et vérifie
   le câblage de bout en bout est le meilleur badge possible du README.

---

## 9. Feuille de route

**Phase 0 — Cadrage (jour 1)**
`docs/PRIOR-ART.md`, choix de la stack technique, nom du projet, schéma d'architecture.

**Phase 1 — MVP démontrable**
Sonarr + Radarr + Prowlarr + qBittorrent + Jellyfin.
Génération compose, pré-semis des clés, câblage complet, vérification. CLI uniquement.
**C'est cette version qui doit déjà impressionner.**

**Phase 2 — Largeur**
Lidarr, Bazarr, SABnzbd / NZBGet, Transmission / Deluge, Plex, Emby,
Seerr, Audiobookshelf, Shelfmark, Shelfarr.

**Phase 3 — TUI Textual**
Le wizard. Enregistrer le GIF de démo ici. C'est lui qui fait les étoiles.

**Phase 4 — Avancé**
Gluetun, reverse proxy + TLS, dashboard Homepage auto-généré, profils qualité TRaSH
via Recyclarr, `doctor`, `backup` / `restore`.

**Phase 5 — Optionnel**
Wizard web, presets communautaires, support Podman / Docker Swarm / Unraid / Synology.

---

## 10. Hygiène de dépôt (l'objectif étoiles)

- **README** : GIF de démo dans les 10 premières lignes, avant tout paragraphe.
  Puis un « avant / après » : 3 h de configuration manuelle → une commande.
  Puis un quickstart en 3 lignes. Puis le schéma du layout `/data`.
- **Licence MIT**, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, templates d'issues.
- **CI GitHub Actions** : lint, tests unitaires, test d'intégration réel.
- **Releases sémantiques** + changelog automatique.
- **`docs/` sérieux**, avec une page de dépannage nourrie par les vraies erreurs
  rencontrées pendant le développement.
- **Nom** : à trancher. Pistes — `PlugArr`, `Orchestrarr`, `Nestarr`, `Arrsembly`,
  `Stackarr`. Vérifier la disponibilité sur GitHub, PyPI et Docker Hub avant de choisir.
- Créditer explicitement TRaSH Guides, Servarr et LinuxServer.io. La communauté le rend bien.

---

## 11. Décisions actées (2026-08-31)

Toutes les questions ouvertes ont été tranchées. Ne pas les rouvrir sans raison.

| # | Question | Décision | Conséquence technique |
|---|---|---|---|
| 1 | µTorrent | **Abandonné.** Remplacé par Transmission par défaut, + Flood en UI optionnelle | Aucun code Windows natif. Un seul chemin : Docker |
| 2 | Langage | **Python 3.12 + Typer + Textual** | Voir §6. ADR à écrire |
| 3 | Cible | **NAS / serveur Linux.** Windows via Docker Desktop + WSL2, documenté non optimisé | Profils de plateforme, §6bis |
| 4 | Unraid / Synology | **Profils de plateforme en v1**, template Community Applications en phase 4/5 | Coût faible en v1, PR communautaire modérée plus tard |
| 5 | VPN | **Optionnel, avec avertissement explicite** | Voir ci-dessous — impact structurel sur la génération du compose |
| 6 | Shelfarr | **Amont `Pedro-Revez-Silva/shelfarr`** | Le fork est mort, voir ci-dessous |

### 11.1 VPN optionnel : ce n'est pas une simple case à cocher

Décision : Gluetun est optionnel. Mais l'activer **change la structure du compose** :
le client torrent perd son propre réseau (`network_mode: service:gluetun`) et ses ports
publiés migrent vers le service gluetun. Ses `depends_on` et son healthcheck changent aussi.

→ **Le générateur de compose doit être conçu dès le départ avec cette bascule**,
pas la recevoir en rustine phase 4. Prévoir deux formes de rendu pour le service torrent
et les tester toutes les deux en CI.

→ Quand le VPN est **désactivé**, afficher un avertissement clair et non contournable
à l'étape récapitulatif (§7 étape 6) : le trafic torrent sortira sur l'IP publique de
l'utilisateur. Avertir, ne pas moraliser, ne pas bloquer.

### 11.2 Shelfarr : le fork est mort, viser l'amont

Vérifié via l'API GitHub le 2026-08-31 :

| Dépôt | Étoiles | Fork ? | Dernier push | Verdict |
|---|---|---|---|---|
| `Pedro-Revez-Silva/shelfarr` | 326 | non | 2026-08-30 | **cible** |
| `presswizards/abs-shelfarr` | 0 | oui | 2026-03-22 | abandonné, ignorer |

Le fork n'a reçu aucun commit depuis sa création. Question close.

Shelfarr est écrit en **Ruby on Rails**, mais son déploiement officiel courant
persiste ses bases SQLite, Active Storage, ses journaux et sa clé générée sous
`/rails/storage` : aucun PostgreSQL séparé n'est requis. Le Compose officiel
2026.09.18.1 inclut en revanche `shelfarr-libation`, compagnon interne sans port
hôte. Ses volumes privés `/config`, `/data` et `/control` doivent être sauvegardés
avec l'état principal, et les deux images doivent toujours être mises à jour
ensemble.

### 11.3 Anna's Archive : point de vigilance juridique

Shelfarr intègre nativement le téléchargement direct depuis **Anna's Archive**, une
bibliothèque parallèle au statut juridique contesté. Notre outil peut parfaitement
**déployer** Shelfarr — déployer un logiciel libre est neutre. En revanche :

- **ne jamais préactiver cette source** dans la configuration générée
- rester cohérent avec la contrainte §8.8 « zéro indexeur préconfiguré »
- mentionner le fait dans la fiche du service, laisser l'utilisateur décider

C'est aussi ce qui protège la visibilité du dépôt à long terme.

## 12. Instruction finale à l'agent qui implémente

> Ne devine aucun endpoint d'API, aucun nom d'image Docker, aucun numéro de port,
> aucune version. Vérifie chaque fait dans la documentation officielle ou contre une
> instance réelle avant de l'écrire dans le code. Quand une information n'est pas
> vérifiable, marque-la `TODO(verify)` et signale-la, plutôt que d'écrire du code
> plausible mais faux.
> La fiabilité du câblage est l'unique raison d'être de ce projet.

---

## Sources vérifiées le 2026-08-31

- Shelfmark : https://github.com/calibrain/shelfmark
- Shelfarr : https://github.com/Pedro-Revez-Silva/shelfarr — https://shelfarr.org/
- Fork Shelfarr (abandonné, 0 étoile, mort depuis mars 2026) : https://github.com/presswizards/abs-shelfarr
- Flood (actif, 2,8k étoiles) : https://github.com/jesec/flood
- Readarr retiré (27 juin 2025) : https://docs.linuxserver.io/deprecated_images/docker-readarr/
