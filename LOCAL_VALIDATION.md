# Vérifications du paquet local — 6 septembre 2026

Base de l’application : v0.7.0, commit `f5582fc`.
Branche : `feature/local-console-site-autoupdate`.
Site : branche `feature/local-discovery-demo`, à partir d’une copie des fichiers
du commit distant `4ee6786` (le clone Git privé n’était pas disponible).

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

Aucun push GitHub, aucune pull request, aucune release et aucun déploiement
Vercel ou Sites n’ont été effectués pour ce travail local.
