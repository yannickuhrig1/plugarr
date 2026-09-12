# Parité fonctionnelle TUI / assistant web local

Inventaire vérifié sur les écrans Textual de PlugArr 0.8.0 et sur l’exécutable
de préversion `v0.8.0-web-preview.1`. Cette table décrit où se trouve chaque
fonction dans l’assistant web local après la mise à niveau du 11 septembre 2026.

| Parcours TUI | Fonction | Équivalent web local |
| --- | --- | --- |
| Accueil | choix FR/EN | sélecteur FR/EN permanent dans l’en-tête |
| Accueil | contrôle Docker | carte « Disponibilité de Docker » avant de continuer |
| Accueil | démarrer, quitter, revenir au TUI | boutons Continuer, Quitter et Ouvrir le terminal TUI |
| Sauvegarde | détecter une pile, choisir source/destination, arrêt sûr ou copie à chaud | panneau « Sauvegarder une installation », copie à chaud décochée par défaut |
| Restauration | choisir l’archive et une nouvelle racine, lire le manifeste, avertir pour une copie à chaud, confirmer | panneau « Restaurer une sauvegarde » avec examen obligatoire et confirmation distincte |
| Services | 16 applications sélectionnables, dépendances automatiques | cartes du catalogue, compte brut/effectif et nombre de liens prévus |
| Chemins | plateforme, racines, nom de pile, utilisateur, hôte, fuseau et langue | étape Dossiers, avec les sept langues de service |
| Chemins | PUID/PGID et essai des liens physiques | résumé des identifiants détectés et bouton de test manuel |
| VPN | aucun VPN ou Gluetun, fournisseur, protocole et identifiants | étape VPN avec les mêmes champs WireGuard/OpenVPN |
| VPN | fournisseurs avec redirection de port en premier, alias PIA masqué | liste ordonnée ; `pia` remplacé par `private internet access` |
| VPN | choix multiples de pays/régions et filtre compatible port entrant | sélecteur multiple filtrable, limité aux emplacements compatibles si nécessaire |
| VPN | essai réel dans un conteneur jetable | bouton « Tester le tunnel jetable » ; résultat non bloquant |
| VPN | trajet SABnzbd direct + SSL/TLS recommandé, ou via Gluetun sur demande | choix explicite identique ; activer le trajet VPN active aussi Gluetun |
| Recyclarr | profil par défaut ou modèle officiel pour Sonarr/Radarr | catalogue complet, recherche native du sélecteur et ordre de grandeur de taille |
| Récapitulatif | services, images, URL, chemins, IDs, UMASK/TZ, VPN et nombre de liens | cartes de synthèse et lignes de services avant confirmation |
| Récapitulatif | reprendre une pile ou repartir de zéro | choix explicite quand une installation a été trouvée |
| Récapitulatif | garder ou supprimer les configurations aux secrets illisibles | choix affiché uniquement pour les services concernés ; suppression après confirmation |
| Installation | phases, progression, journal et résultats de câblage | flux SSE authentifié, événements, journal et carte de connexions en direct |
| Indexeurs | charger les définitions du Prowlarr installé, rechercher, saisir les champs/mirroirs, ajouter ou passer | panneau post-installation, recherche à partir de deux caractères, 40 résultats maximum, champs secrets masqués et bouton Terminer pour passer |
| Rapport | URL, identifiants, clés API, échecs, étapes suivantes et `.env` | tableau final, actions suivantes et chemin du fichier `.env` |
| Rapport | ouvrir la page d’accès et fermer | boutons « Ouvrir la page d’accès » et « Terminer et fermer » |

## Garde-fous propres au web local

- Le serveur reste lié à `127.0.0.1` et toutes les API exigent le jeton de la
  session, un hôte local valide et une origine compatible.
- Une restauration exige d’abord l’examen du même fichier (chemin, taille et
  date de modification), puis une confirmation. Les sorties de racine ZIP,
  les liens symboliques sortants et les noms de volumes injectés sont refusés.
- La remise à zéro ne peut viser que les identifiants de services du catalogue
  signalés par le moteur. Elle n’est exécutée qu’après validation du plan et
  confirmation de l’installation ; `DATA_ROOT` n’est jamais concerné.
- Le mode démonstration expose tout le parcours, y compris les indexeurs et le
  rapport, mais ne contacte ni Docker, ni Prowlarr, ni les fichiers utilisateur.

## Limite de validation dans l’environnement de développement

`plugarr.exe` est un binaire Windows PE x86-64 et ne peut pas être exécuté
nativement dans l’environnement Linux utilisé pour cette modification. Son
empreinte a été comparée à l’asset GitHub, son archive PyInstaller a été lue, et
les modules TUI ainsi que leurs données embarquées ont été confirmés. Le test
Windows natif et le rendu visuel final doivent être refaits sur un PC Windows.
