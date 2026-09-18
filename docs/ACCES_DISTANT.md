# Accès distant intégré : version de test

L'assistant web contient maintenant une étape **Accès à distance**, après Qualité
et avant Vérification. Ce n'est plus la maquette HTML séparée.

## Parcours

1. Choisir les applications et les dossiers comme auparavant.
2. À l'étape 5 sur 7, choisir **Chez moi**, **Tailscale** ou **Mon domaine**.
3. Confirmer l'installation de la stack.
4. Pour un accès distant, confirmer puis cliquer sur **Activer l'accès distant**.
5. Consulter **Configurer mon téléphone** : nzb360 ou qbRemote, application,
   connexion locale ou distante. Copier URL, port et clé API ou identifiants.
6. Télécharger le fichier d'accès. Les fiches restent utilisables hors ligne.

L'activation distante est séparée : un problème de DNS ou de Tailscale ne transforme
pas une installation locale réussie en échec. Une passerelle Docker déjà créée par
PlugArr peut être arrêtée avec **Désactiver la passerelle PlugArr** et confirmation.
Choisir Local lors d'une réinstallation ne désactive pas automatiquement une
ancienne passerelle : l'écran final le signale.

## Tailscale

- Linux avec Docker et `/dev/net/tun` : création d'un conteneur Tailscale et lien
  d'association au compte, puis actualisation de l'état.
- Si Tailscale est déjà installé sur le serveur, réutilisation de la connexion native.
- Windows : installer et connecter Tailscale sur le PC qui héberge les applications,
  puis actualiser dans PlugArr. L'EXE n'installe pas le client Windows à votre place.
- Installer et connecter également Tailscale sur le téléphone avec les autorisations
  adaptées. Les règles du réseau Tailscale peuvent autoriser d'autres ports du serveur.
- Aucune clé d'authentification Tailscale à copier dans un formulaire PlugArr.

## Domaine HTTPS

PlugArr génère une passerelle Caddy séparée. Les services proposés sont Sonarr,
Radarr et qBittorrent, uniquement lorsqu'ils sont gérés par PlugArr et sans
sous-chemin personnalisé. Exemples : `sonarr.mondomaine.fr`, `radarr.mondomaine.fr`,
`qb.mondomaine.fr`.

L'utilisateur reste responsable de l'achat du domaine, du DNS des sous-domaines
et de la redirection des ports TCP 80 et 443 vers le serveur. Pas de configuration
automatique de la box, du fournisseur DNS ou de contournement du CGNAT.
Les ports 80 et 443 doivent être disponibles pour Caddy.

Avant démarrage, PlugArr contrôle l'authentification Sonarr/Radarr et renforce
les protections WebUI qBittorrent. Les anciennes préférences qB concernées sont
sauvegardées dans `.plugarr-remote/qbittorrent-web-before.json`. Elles ne sont pas
réappliquées automatiquement lors d'une désactivation, pour ne pas rétablir des
réglages moins sûrs. Un échec avant démarrage peut donc laisser ces protections
renforcées, sans passerelle active.

La vérification HTTPS contrôle le certificat et le refus de l'API anonyme depuis
le serveur. Elle ne prouve pas l'accessibilité depuis Internet : tester sur le
téléphone en 4G/5G reste nécessaire. Les URL proposées pendant un état « à vérifier »
ne constituent pas une confirmation de connexion.

## Sécurité et limites de cette livraison

- Le fichier HTML contient les vrais secrets en installation réelle, même lorsque
  les champs sont masqués. Ne pas le publier ni le partager. Caddy ne le sert pas.
- La passerelle est stockée dans `.plugarr-remote`, séparément de la stack principale.
  Ses données persistantes se trouvent dans le dossier de configuration des applications.
- L'arrêt de la passerelle Docker ne déconnecte pas un client Tailscale natif.
- Le choix distant est enregistré dans `stack.yml`. Après un redémarrage du parcours,
  l'état de connexion doit être vérifié à nouveau.
- Le mode `web --demo` simule l'installation et l'activation, sans Docker ni modification réseau.
- Aucun déploiement réel Caddy/Tailscale ni test sur téléphone n'a été effectué pour
  cette livraison. Ce sont les prochains essais d'intégration à faire sur un serveur de test.
- Cette étape configure l'accès aux applications. Elle n'ajoute pas de formulaire
  SSH permettant à l'EXE d'installer la stack sur une autre machine : l'assistant
  s'exécute sur la machine qui héberge la stack.

## Vérifications reproductibles

- Tests Python : `tests/test_remote_access.py`, tests du webwizard, du dashboard,
  de la reprise et de l'empaquetage.
- Test navigateur Chromium : `tests/js/wizard_remote.cjs`, avec Playwright disponible.
  Il teste les trois choix, le rejet d'un domaine mal formé, la confirmation
  d'activation, les fiches et la réouverture du HTML à 390 pixels de largeur.
  `PLUGARR_TEST_EXE` permet d'exécuter le même parcours sur l'EXE compilé.
