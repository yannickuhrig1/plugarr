# Vérifications de la préversion web — 10 septembre 2026

## Sauvegarde, versions, santé et trajet SABnzbd — 11 septembre 2026

Branche locale : `feature/backup-update-health-vpn`.

La console affiche désormais la version installée et la version cible, même
lorsqu'aucune mise à jour n'est proposée. Une mise à jour de Silo impose une
sauvegarde complète avant le téléchargement ou la recréation. Le diagnostic
combine l'état Docker et les sondes API : un conteneur absent, arrêté, en
redémarrage, `starting` ou `unhealthy` ne peut plus produire « tout est en
ordre », et une panne Silo reçoit une action déduite de ses journaux sans les
recopier dans la page.

Le TUI et l'assistant web demandent séparément le trajet de SABnzbd. Le choix
par défaut est direct avec SSL/TLS chez le fournisseur Usenet ; Gluetun reste
disponible sur demande. Les configurations antérieures sont migrées en
conservant leur ancien trajet.

Validation Linux : **1 183 tests réussis, 5 ignorés** en 94,70 secondes ; Ruff
sur `src`, `tests` et `scripts`, audit des 663 traductions, syntaxe JavaScript
et contrôle des différences Git réussis. Aucun essai Windows ou Docker réel
n'est revendiqué pour cette modification.

## Parité TUI ajoutée — 11 septembre 2026

L’assistant web d’installation reprend désormais les fonctions exposées par le
TUI : contrôle Docker, sauvegarde et restauration inspectée, sélection et
dépendances des 16 services, chemins/PUID/PGID/liens physiques, VPN multi-lieux
avec test jetable, profils Recyclarr, reprise ou remise à zéro, rapport final,
page d’accès et ajout d’indexeurs depuis le Prowlarr installé. La correspondance
écran par écran est détaillée dans `docs/WEB_TUI_PARITY.md`.

Validation Linux de cet état après intégration du correctif de ports :
**1 168 tests réussis, 5 ignorés** en 92,20
secondes ; Ruff, syntaxe JavaScript, contrat JavaScript de fin de parcours et
contrôle des différences Git réussis. Le smoke test Textual charge 177 règles
CSS, les 16 services, 7 langues et 125 lieux VPN. La roue 0.8.0 a été reconstruite
et contient notamment `wizard-parity.css`, `wizard.html`, `wizard.js`, le TUI et
les données VPN.

Le lanceur `TESTER-INSTALLATION-REELLE.cmd` force le serveur web sans
`--demo` et isole les artefacts dans `installation-test-reelle`. Un test dédié
vérifie ce contrat ; le fichier CMD n’a pas été exécuté sous Windows ici.

Le commit source `3ef13759c126cbef0212d43d5f152486894ad253` a été appliqué
sur cette branche sous l’identifiant `e49591f`. SABnzbd écoute maintenant sur
le port interne 8085, Gluetun publie `8085:8085`, le câblage utilise
`http://gluetun:8085` et les configurations 0.8.0 existantes sont migrées. Un
seul client torrent reçoit le port entrant du tunnel : qBittorrent en priorité,
ou Transmission lorsque qBittorrent n’est pas géré par la pile.

L’asset `plugarr.exe` de la préversion a une empreinte SHA-256
`0ef42bd428ce9bb02b5f24ab62a7b9c1d31779079fec0d7fd1c3b5ad8c6d5962`, identique
à celle publiée. Son archive PyInstaller contient les modules TUI, assistant
web, sauvegarde, essai VPN et indexeurs attendus. Comme l’environnement de
validation est Linux et ne possède pas Wine, le PE Windows n’y a pas été lancé
nativement. Le workflow Windows publié avait, lui, réussi ses contrôles de
`plugarr.exe`; cela ne remplace pas un essai interactif du nouveau code sur le
PC Windows cible. Le navigateur de contrôle n’a pas non plus pu atteindre le
serveur local du conteneur ; aucun contrôle visuel final n’est donc revendiqué.

Base de l’application : v0.8.0, commit officiel `ff58ee7`.
Branche : `feature/local-web-wizard`.
Préversion : `v0.8.0-web-preview.1`.

Validation finale sous Linux : **1 147 tests réussis, 5 ignorés** en 94,15
secondes. Ruff et le contrôle des différences Git réussissent. L’arbre Git
transféré sur GitHub correspond exactement à l’arbre local. La compilation et
l’exécution réelles sous Windows restent confiées au workflow GitHub Actions ;
aucun test réel Docker n’est revendiqué ici.

Les résultats datés ci-dessous retracent les validations intermédiaires qui ont
précédé cette fusion avec la v0.8.0.

## Carte des connexions — modification du 6 septembre

### Correction du lancement après la capture montrant l’ancienne carte

- Le script importe désormais les sources du dossier extrait, avant toute
  installation Python déjà présente, et demande un port libre à chaque lancement.
- Vérification réelle par HTTP de deux processus de démo simultanés, depuis un
  autre dossier et avec une ancienne installation simulée dans `PYTHONPATH` :
  adresses distinctes, nouvelle carte V2 et nouveaux services servis correctement.
- Les réponses portent `Cache-Control: no-store`. Le navigateur est ouvert
  directement sur la carte, et le titre identifie explicitement la démo V2.
- **9 tests réussis** pour cette correction et la carte ; syntaxe et Ruff validés.
- Le lanceur `.cmd` doit encore être essayé sous Windows. Le contrôle HTTP a
  tourné sous Linux, sans navigateur et sans Docker.

### Vérifications de la carte

- Tests ciblés : topologie des services sélectionnés, Flood avec deux clients,
  VPN et services adoptés, conditions de Seerr / Recyclarr / DroppedNeedle,
  absence de liens orphelins, statuts non vérifiés et absence de secrets.
- Logos SVG/PNG embarqués contrôlés et inclus dans les deux empaquetages.
- Syntaxe réelle de tous les blocs JavaScript validée avec Node.
- **68 tests ciblés réussis en 10,59 secondes**, y compris les routes
  authentifiées, le refus des opérations indisponibles et les en-têtes de page.
- Ruff : réussi sur `src`, `tests` et `scripts`.
- Aucune validation visuelle dans un navigateur ni exécution Windows/Docker
  réelle pour cette modification. Ces essais restent à effectuer localement.

## Résultats avant la modification de la carte

- Suite Python complète : **893 tests réussis, 5 ignorés**, en 63,49 secondes.
- Les variables de proxy de cet environnement ont été retirées uniquement du
  processus de test pour permettre aux doubles HTTP de fonctionner.
- Contrôle Ruff : réussi depuis la racine du projet.
- Audit du catalogue de traduction existant : 585 phrases / 585 entrées.
- Syntaxe JavaScript du site et des scripts embarqués de la console : contrôlée.
- Les références locales aux images et aux scripts de la vitrine sont contrôlées.

Les tests couvrent notamment l’authentification, les refus de réparation non
confirmée, la sauvegarde, la rétention des seules archives gérées, l’intégrité du
téléchargement, la préservation d’un fichier déjà présent et la protection des
binaires de test local.

## Vérifications restant à effectuer sur la machine de test

- Compiler et lancer le binaire sous Windows.
- Valider le remplacement réel de l’exécutable, sa copie `.previous` et la
  reprise au lancement suivant. Les appels système Windows ont été simulés
  dans les tests Python ; ce n’est pas une validation du mécanisme Windows réel.
- Tester une stack Docker dédiée, ses liaisons réelles et une restauration.
- Vérifier visuellement les pages sur PC et mobile. Aucune session de test
  navigateur n’a été effectuée pour ce paquet.

Les nouveaux panneaux de console restent en français. L’audit du catalogue
existant ne constitue pas une validation de traduction de ces nouveaux panneaux.
Les limites fonctionnelles sont détaillées dans `LOCAL_TESTING.md`.

La branche de préversion est publiée séparément de `main`. Aucun déploiement
Vercel ou Sites n’est nécessaire pour cette version locale de l’assistant.
