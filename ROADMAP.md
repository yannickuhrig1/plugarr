***Français** · [English](ROADMAP.en.md)*

# Feuille de route

Où en est PlugArr, ce qui vient ensuite, et pourquoi. Tenue à jour à chaque
séance de travail.

**Dernière mise à jour : 9 septembre 2026** — version publiée : **0.8.0**

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
637 phrases affichables et **échoue s'il en manque une**, ou si le catalogue
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

**Shelfarr et Shelfmark**, les deux derniers services de la liste. Leurs
empreintes sont déjà relevées, et Audiobookshelf les débloque : ils livrent
dans ses bibliothèques.

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
| Console traduite en anglais | ⬜ à faire |

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
pleins pouvoirs, sans rien gagner.

Elle tourne donc sur l'hôte, sous le compte de l'utilisateur, sur `127.0.0.1`,
et démarre toute seule avec `plugarr autostart`. Le confort recherché est le
même. Et parce qu'une console qui change des mots de passe doit s'authentifier
sérieusement, `plugarr admin-password` pose un mot de passe : empreinte seule
dans `stack.yml`, sessions expirables, tentatives limitées.

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
