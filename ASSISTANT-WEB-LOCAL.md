# PlugArr — assistant web local

Branche : `feature/local-web-wizard`.
Base : PlugArr v0.8.0, commit officiel `ff58ee7`.
Cette branche conserve les travaux de la console, de la carte V2 et de
l'assistant web, puis les applique à la version 0.8.0. Elle est distribuée comme
préversion `v0.8.0-web-preview.1`, distincte de la release stable `v0.8.0`.

## Essayer sans installer de services

1. Extraire **toute** l'archive dans un nouveau dossier.
2. Sous Windows, double-cliquer sur **TESTER-ASSISTANT-WEB.cmd**.
3. Laisser le terminal ouvert et suivre l'assistant dans le navigateur.

Python 3.11 ou plus récent est nécessaire. Le lanceur accepte `py -3` ou
`python`, crée un environnement `.venv-web-local` et installe les dépendances
au premier lancement (Internet nécessaire). Il importe toujours les sources
à côté du lanceur, même si une ancienne version de PlugArr est installée.

Le bandeau orange **Mode démonstration** identifie la simulation. La sélection,
les chemins, les options VPN, le récapitulatif et la progression sont testables.
Aucun appel à Docker, aucune lecture de votre `stack.yml`, aucune création de
stack et aucune modification des préférences d'interface dans ce mode.
Les contrôles et l'installation sont **simulés** : la réussite de la démo ne
prouve pas que Docker est prêt. La démo embarque le catalogue officiel des profils Recyclarr récupéré le
7 septembre 2026, sans connexion réseau lors de son utilisation.

Si le navigateur ne s'ouvre pas, copier **l'adresse complète** affichée dans le
terminal. Elle contient un jeton de session après `#token=`. Chaque lancement
utilise un port libre et un nouveau jeton. Un ancien onglet ne se reconnecte pas
à un nouveau processus. Ctrl+C ferme le serveur local.

## Lancement réel et choix de l'interface

**LANCER-PLUGARR.cmd** ouvre le choix web/TUI sur une session graphique Windows
avec terminal interactif. La préférence peut être mémorisée sur cet ordinateur.
**LANCER-TUI.cmd** force le terminal, même après avoir mémorisé le mode web.

L'installation réelle exige Docker accessible. Elle ne démarre qu'après
vérification et confirmation du récapitulatif. Utiliser une pile de test avec
un nom et des dossiers distincts de la pile habituelle. Sur une pile existante,
le moteur arrête les conteneurs, prépare la configuration, puis les relance.

Commandes, depuis le dossier du code après installation des dépendances :

```powershell
python -m plugarr --interface web
python -m plugarr --interface tui
python -m plugarr wizard --interface web --project-dir "C:\PlugArr-Test"
python -m plugarr web --demo
python -m plugarr web --no-open --port 7375 --project-dir "C:\PlugArr-Test"
```

Remplacer `python` par `.\.venv-web-local\Scripts\python.exe` si l'environnement
a été préparé par les lanceurs Windows. Sous Linux : installer avec
`python -m pip install -e .` dans un environnement virtuel, puis utiliser les
mêmes commandes avec un chemin Linux.

`--interface auto` lit la préférence locale, sinon propose web/TUI en session
graphique interactive, ou utilise le TUI en terminal sans bureau. Sans terminal
ni bureau détecté, il explique comment lancer explicitement le mode web.
Les sous-commandes existantes (`install --yes`, `doctor`, `serve`…) restent
indépendantes de ce choix.

La préférence se trouve dans `%APPDATA%\plugarr\interface.json` sur Windows,
ou `$XDG_CONFIG_HOME/plugarr/interface.json` (à défaut `~/.config/plugarr/`) sur
Linux. Valeurs : `auto`, `web`, `tui`. Retirer ce fichier réactive le choix initial.
La préférence de lancement ne modifie pas `stack.yml`.

## Fonctionnement de cette première version

- Applications et logos issus du catalogue existant. Dépendances résolues par
  `catalog.resolve_dependencies`, puis affichées au récapitulatif.
- Chemins et profil de plateforme, identifiant et langues.
- VPN Gluetun pour les clients de téléchargement du catalogue, WireGuard ou
  OpenVPN ; liste des localisations issue des données embarquées existantes.
- Profils Recyclarr/Sonarr/Radarr chargés sur demande par le client existant.
- Contrôles existants du moteur (Docker, ports, espace, liens physiques,
  configuration et collision de pile). Les contrôles de liens physiques peuvent
  utiliser des fichiers temporaires, comme dans le TUI.
- Confirmation obligatoire, jeton de récapitulatif à usage unique et expiration
  après cinq minutes. Une modification de `stack.yml` invalide les contrôles.
- Installation en arrière-plan via `orchestrator.install`, avec progression et
  messages masquant les secrets connus. Rechargement de page possible pour
  retrouver la progression ; les saisies non validées ne sont pas persistées.
- Après installation réelle, ouverture de la console d'administration existante.
  Garder le processus PlugArr ouvert pour continuer à utiliser la console.
- Retour au TUI avant l'installation si le terminal est interactif. Les saisies
  web non enregistrées ne sont pas transférées au TUI.
- Reprise d'une pile : secrets, ports, images et droits existants conservés.
  Les chemins, plateforme, nom et identifiant restent verrouillés dans cette
  première version. Retirer un service existant est refusé par cet assistant.

## Périmètre et limites

Le serveur écoute **uniquement sur 127.0.0.1**. La consultation directe depuis
un autre ordinateur/NAS n'est pas encore proposée. Un tunnel SSH peut servir
au test avancé en conservant le même port local et distant. Il n'y a pas de
publication web, ni de serveur cloud.

Une seule installation à la fois est permise par session de l'assistant.
Ne pas lancer simultanément plusieurs processus PlugArr sur la même pile.
Fermer l'onglet ne tue pas l'installation ; fermer le processus de force peut
l'interrompre. Ctrl+C attend la fin du travail engagé.

L'interface possède des libellés FR/EN. Certains messages du moteur et des
panneaux hérités restent en français ; la traduction complète de cette nouvelle
surface n'est pas revendiquée. Le choix des indexeurs après l'installation
reste disponible par les commandes existantes et les interfaces des services.

Les ressources HTML/CSS/JS sont déclarées dans le paquet Python et dans la
recette PyInstaller. **Aucun nouvel exécutable Windows compilé n'est fourni.**
Les fichiers `.cmd` et l'installation Docker réelle restent à essayer sur
Windows. Les tests effectués ici utilisent Linux et des moteurs simulés.

## Vérifications réalisées le 6 septembre 2026

- Suite complète : **927 tests réussis, 5 ignorés**. Les variables de proxy ont
  été retirées uniquement du processus de test, les services étant simulés.
- Après les derniers contrôles de chemins et de champs VPN : **54 tests ciblés
  réussis**, couvrant le serveur web, la sélection d'interface, les ressources
  des deux empaquetages et le catalogue de traduction existant.
- Ruff et syntaxe JavaScript : réussis.
- HTML : identifiants uniques, fichiers liés présents, correspondance des
  identifiants utilisés par le JavaScript avec les éléments déclarés.
- Audit existant : 589 phrases / 589 traductions. Cet audit ne couvre pas les
  chaînes HTML/JavaScript ni tous les messages du nouvel assistant.

Aucune session de vérification visuelle dans un navigateur, aucun lancement
Windows et aucune installation réelle de services Docker n'ont été effectués.

## Récupérer également la branche Git sur votre PC

L'archive contient les sources immédiatement utilisables et
`plugarr-local-web-wizard.bundle`, une copie transportable de la branche Git.
Avec Git installé, depuis le dossier extrait :

```powershell
git clone --branch feature/local-web-wizard ./plugarr-local-web-wizard.bundle ../plugarr-web-git
```

Cette commande crée un **nouveau dossier** contenant la branche locale et son
historique, sans contacter GitHub et sans modifier un dépôt déjà présent.

## Graphe dynamique — 7 septembre 2026

Le dessin SVG, les pastilles rondes, les prises et les câbles en dégradé reprennent
le fichier **apercugraphe.html** fourni. Son scénario préenregistré est remplacé
par les données de PlugArr. Le fichier original fourni n'a pas été modifié.

- La carte apparaît directement dans les étapes de l'assistant, sans bouton Agrandir.
  Échap réduit la carte. Sur un petit écran, le défilement reste dans la carte.
- Cocher/décocher une application ou activer/désactiver le VPN actualise le plan
  après un bref regroupement des clics (100 ms), sans attendre une installation.
- Les dépendances ajoutées par PlugArr sont incluses. Les colonnes vides
  disparaissent. Flood utilise le client réellement choisi par Compose.
- Avant confirmation, les câbles sont **prévus** ; rien n'est affiché comme un
  succès d'installation ou comme une vérification réseau.
- Pendant l'installation, les événements sont poussés au navigateur par un flux
  SSE authentifié. Un identifiant stable relie chaque début/résultat à son étape,
  indépendamment du nom traduit affiché dans les journaux.
- Les câbles et pastilles distinguent étape en cours, réussite, échec et
  avertissement. Le compteur mesure les **étapes traitées**, y compris les échecs ;
  il ne mesure pas un nombre de liaisons réseau vérifiées.
- Une étape qui configure plusieurs liens (Seerr, Recyclarr, autobrr…) met à jour
  ses câbles ensemble et compte une seule fois. Son résultat est global : il ne
  prouve pas que chacune de ces liaisons a passé un test indépendant.
- Les liaisons définies par Compose (VPN, Flood, dépendances) sont indiquées
  **configurées, non testées** après la fin de `docker compose up`. Elles ne sont
  jamais assimilées à une preuve de bon fonctionnement du tunnel VPN.
- Une coupure de connexion affiche les derniers états reçus, suspend les effets
  de flux et déclenche une reconnexion. Un instantané complet restitue les états
  sans doubler les compteurs ni perdre les échecs déjà reçus.
- Le mode démonstration suit le plan sélectionné, étape par étape. Les résultats
  restent explicitement **simulés**, sans Docker ni installation réelle.

Pour essayer cette version : extraire la **nouvelle** archive, puis ouvrir
`TESTER-ASSISTANT-WEB.cmd`. Le titre de l'onglet affiche « PlugArr — Assistant et
graphe en direct ». Conserver les sources du dossier extrait ensemble.

Ces données décrivent l'installation. Ce n'est pas un moniteur permanent de
l'état des conteneurs après fermeture de l'assistant, et l'animation des câbles
ne mesure pas le trafic réseau.

Vérifications de cette intégration : **948 tests réussis, 5 ignorés** dans la
suite complète ; contrôles Ruff, syntaxe des deux scripts JavaScript et audit
existant des traductions réussis. Les tests couvrent le plan dynamique, les
identifiants des étapes, les événements SSE, la reconnexion et les états du
composant SVG (sans navigateur). Le rendu visuel dans un navigateur ainsi que
l'installation réelle Windows/Docker restent à valider sur la machine de test.

## Fin de démonstration : console d'administration

La fin réussie de la simulation ouvre automatiquement la console d'administration
locale dans un nouvel onglet, en conservant le récapitulatif de configuration. Le bouton d'ouverture reste accessible si la navigation
échoue. Les installations réelles gardent leur bouton d'ouverture habituel.

La console de démo reprend les applications sélectionnées et leurs dépendances.
Elle affiche une adresse fictive (`192.0.2.10`), l'utilisateur `demo`, des mots de
passe et des clés API portant le préfixe `DEMO-`. Les liens vers ces adresses sont
interceptés pour signaler qu'aucun service réel n'est installé.

Les commandes démarrer, arrêter, redémarrer, mettre à jour, renouveler un secret,
ajouter une application et sauvegarder sont simulées. Les statuts, versions et
identifiants affichés évoluent dans la session. Les réglages de maintenance et
l'historique restent en mémoire ; aucun planificateur de sauvegarde ne démarre.
Garder le terminal ouvert pour utiliser la console. Tout est oublié à sa fermeture.

Vérification de cette correction : tests HTTP du parcours démo → console et des
commandes simulées, contrôle des sessions/origines et test JavaScript de l'ouverture
unique après succès. Aucun essai visuel en navigateur ni sous Windows/Docker réel.


## Administration : nouvel onglet et graphe partagé

L'administration s'ouvre dans un nouvel onglet, en démo comme après une installation
réelle. Une ouverture automatique bloquée par le navigateur laisse un lien direct
« Ouvrir l'administration dans un nouvel onglet ». Le récapitulatif et le graphe
d'installation restent dans l'onglet de configuration.

La console utilise maintenant les mêmes fichiers de dessin `graph.js` et de style
`graph.css` que l'assistant : pastilles avec logos, prises, câbles et animations.
Elle conserve la sélection au clavier ou à la souris, la liste des liaisons, leurs
tests et leurs réparations. Le bouton Agrandir a été retiré à la demande utilisateur.

Les états des conteneurs et les derniers résultats enregistrés sont actualisés
toutes les 5 secondes. Le dessin reste en place lors de ces actualisations.
Un service arrêté ou inaccessible suspend l'animation de ses liaisons, même si
leur dernier test avait réussi. Les tests individuels restent déclenchés par
l'utilisateur ; leur date et leur résultat sont affichés. Les liaisons sans test,
dont le réseau Gluetun, restent indiquées comme issues de la configuration.
Le compteur concerne les tests de connexion, pas les étapes d'installation.

La démo commence avec des conteneurs et des tests initiaux explicitement simulés.
Les commandes continuent à modifier uniquement la session de démonstration.
Les états et secrets réels ne sont jamais chargés par ce parcours.

Vérification de cette correction : **92 tests ciblés réussis**, couvrant les
API HTTP de l'assistant et de l'administration, le comportement du
composant SVG partagé et de son adaptateur, contrôle du nouvel onglet et du lien
après blocage d'ouverture, validation de syntaxe JavaScript et de l'empaquetage.
Le rendu visuel en navigateur et l'installation Windows/Docker restent à vérifier.


## Corrections après les captures utilisateur

- Les listes Qualité se chargent automatiquement et proposent tous les identifiants
  du catalogue retenu. En démo : 22 profils Sonarr et 35 profils Radarr, accessibles
  hors ligne. La validation accepte ces mêmes choix, au-delà du profil par défaut.
  En installation réelle : le manifeste de Recyclarr installé reste prioritaire,
  puis le manifeste distant est consulté en l'absence de catalogue local.
- Le bouton Agrandir est retiré de la configuration et de l'administration.
- Flood et Qui sont rangés dans Téléchargements dans les deux graphes. Cela ne
  modifie ni leurs dépendances ni leur configuration réseau.
- L'administration utilise par défaut le thème Site PlugArr : fond #0c1116,
  panneaux #151d26, orange #ff9e45, rose #ec5794 et violet #ad64e5. Les couleurs
  viennent du code du site. Les thèmes clair/système restent sélectionnables.
- Les cartes d'accès ont plus de largeur. Les libellés des identifiants sont
  séparés de leurs valeurs ; copier, renouveler et les commandes de service
  gardent leur texte entier et passent à la ligne par bouton si nécessaire.

Source du catalogue : Recyclarr, [templates.json](https://github.com/recyclarr/config-templates/blob/master/templates.json),
récupéré le 7 septembre 2026. SHA du blob : `2f58aa27f2758f85c5760fa10bf6004079436e2b`.
Copie exacte et provenance incluses dans `src/plugarr/data/recyclarr_templates*.json`.

Les trois captures fournies ont été examinées. La vérification visuelle de la
version corrigée n'a pas pu être effectuée : le navigateur de contrôle refuse
l'accès à l'adresse locale (`ERR_BLOCKED_BY_CLIENT`). Les essais automatisés
restent distincts d'une validation de rendu sur le PC Windows de l'utilisateur.

Validation de ces corrections : **134 tests ciblés réussis** (assistant,
profils Recyclarr, graphes, console, page d’accès et empaquetage). Après fusion
avec la v0.8.0 : **1 147 tests réussis, 5 ignorés** et Ruff réussi. Aucun essai
réel Windows/Docker n'est revendiqué par cette validation Linux.
