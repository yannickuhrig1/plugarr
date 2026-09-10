# Tester la branche locale PlugArr

Prérequis : Python 3.11 ou plus récent sous Windows, avec la commande `py`.
Extraire toute l’archive dans un nouveau dossier. Les fichiers ne sont pas encore
sur GitHub. Les lanceurs ci-dessous n’utilisent ni GitHub Actions ni Vercel.

## Le plus simple : double-cliquer

- `plugarr\TESTER-DEMO.cmd` prépare un environnement Python isolé lors du premier
  lancement (connexion Internet nécessaire pour les dépendances), puis ouvre la
  console de démonstration dans le navigateur.
- `plugarr-site\TESTER-SITE.cmd` ouvre le site local sur le port 8080.

Garder la fenêtre de terminal ouverte pendant les essais. Utiliser Ctrl+C pour
fermer. Si un lancement échoue, conserver le message affiché pour le diagnostic.

## 1. Tester le site vitrine manuellement

Depuis le dossier `plugarr-site` :

```powershell
py -m http.server 8080 --bind 127.0.0.1
```

Ouvrir ensuite http://localhost:8080 dans le navigateur.

## 2. Tester la démo de console sans Docker

Depuis le dossier `plugarr` :

```powershell
py -m venv .venv-local-demo
.\.venv-local-demo\Scripts\python.exe -m pip install -e .
.\.venv-local-demo\Scripts\python.exe scripts/preview_console.py --open
```

Le navigateur ouvre directement la carte sur une adresse locale choisie au
lancement. Si l’ouverture automatique échoue, copiez l’adresse affichée dans
le terminal. N’utilisez pas un ancien onglet sur le port 7374.

Le titre doit afficher **Carte des connexions · V2 (démo)**, avec le fond sombre
et les logos ronds. Chaque lancement utilise un port libre et les sources du
dossier extrait, même si une ancienne démo ou installation Python existe encore.
Les pages de démonstration ne sont pas mises en cache.

Cette démo utilise uniquement des données fictives. Les boutons simulent leurs
résultats : une sauvegarde affichée dans la démo n’est pas une archive réelle et
la planification n’exécute aucune tâche. Les réglages sont effacés à la fermeture.

## 3. Tester PlugArr avec Docker

Installer Docker Desktop, puis ouvrir PowerShell dans `plugarr` :

```powershell
.\.venv-local-demo\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv-local-demo\Scripts\python.exe -m pytest -q
.\.venv-local-demo\Scripts\python.exe -m plugarr --help
.\.venv-local-demo\Scripts\python.exe -m plugarr serve --project-dir "C:\CHEMIN\VERS\PROJET-TEST"
```

Remplacer le chemin par le dossier contenant le `stack.yml` de votre installation
de test. Le dossier du code source ne contient pas à lui seul une installation.
La console réelle s’ouvre sur l’adresse affichée dans PowerShell. Elle nécessite
Docker accessible et ses actions modifient réellement les services concernés.
Pour installer une stack de test, lancer `python -m plugarr` avec le Python de
l’environnement ci-dessus et choisir des dossiers et ports dédiés dans l’assistant.

Les sauvegardes planifiées sont désactivées par défaut. La console doit rester
en fonctionnement pour les exécuter. Les conteneurs sont arrêtés pendant la
copie puis relancés par le mécanisme de sauvegarde. La rétention ne concerne que
les archives créées par ce centre de maintenance.

## Mise à jour automatique de plugarr.exe

Le code est intégré, mais la validation du remplacement réel reste à faire sous
Windows. Aucun nouvel exécutable compilé n’est fourni dans cette archive.

Les compilations locales sont protégées contre leur remplacement automatique
par une release publique. La recherche GitHub reste accessible dans la console.
Les builds de release activent l’auto-mise à jour au lancement interactif :
contrôle de la version stable, de l’URL attendue, de la taille, de l’en-tête MZ et
du SHA-256 fourni par GitHub. Ce contrôle d’intégrité n’est pas une signature
Authenticode. Le remplacement attend la fermeture, conserve une copie
`.previous` et prend effet au prochain lancement. Les réglages de stack restent
dans leur dossier ; seul l’exécutable est remplacé.

Pour compiler un binaire de test protégé, dans PowerShell sous Windows :

```powershell
.\.venv-local-demo\Scripts\python.exe -m pip install pyinstaller
.\.venv-local-demo\Scripts\python.exe -m PyInstaller packaging/plugarr.spec --noconfirm
```

Le résultat sera `plugarr\dist\plugarr.exe`. Une installation réelle de Docker
et le remplacement d’un binaire Windows n’ont pas été validés dans l’environnement
de développement Linux utilisé pour préparer ce paquet.

## Périmètre de cette version locale

La carte reprend le modèle visuel fourni : fond sombre, logos des services dans
des cercles et câbles courbes orange, rose et violet. Cliquez sur un service pour
isoler ses liaisons, puis sur un câble pour lire son rôle, son sens et son état.
Sur un petit écran, le schéma défile horizontalement ; la liste en dessous donne
aussi accès à chaque liaison au clavier ou au toucher.

Seuls les services de `stack.yml` apparaissent, y compris ceux sans liaison API.
Les relations prévues incluent Prowlarr, les *arr, les clients de téléchargement,
Jellyfin, Seerr, autobrr, Recyclarr, qui, Flood, DroppedNeedle, les dépendances de
Silo et Gluetun lorsque le VPN est activé. Flood ne pilote qu’un client ; les
services adoptés ne sont pas placés derrière le VPN géré. Les dossiers partagés
ne sont pas présentés comme des câbles API.

La carte décrit le câblage **attendu**, pas une découverte des réglages ajoutés
manuellement dans chaque application. Seules les liaisons *arr de téléchargement,
synchronisation Prowlarr et notification Jellyfin ont un bouton de test réel et
un résultat daté. La réparation est désactivée pour les sources adoptées. Les
autres câbles sont explicitement marqués « Configuration · sans test disponible ».
Dans la démonstration, les tests sont fictifs, comme annoncé par le bandeau.
Rechargez la page après une modification de la sélection des services.

Les logos sont embarqués : leur affichage ne nécessite aucun accès à Internet.
Ils proviennent des assets de la vitrine PlugArr, copie locale du commit
`4ee6786`. Aucun logo ni aucune connexion imaginaire de la capture n’a été ajouté.

Les alertes sont affichées dans la console, pas envoyées par mail ou Discord.
Le VPN est vérifié lors du diagnostic ; les services pendant l’ouverture de la page.
Les nouveaux panneaux de console sont pour le moment en français. La vitrine
conserve ses parcours FR/EN. Un retour arrière automatique des données des
services Docker n’est pas implémenté.
