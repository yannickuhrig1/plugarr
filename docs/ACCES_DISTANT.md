# Accès distant intégré : version de test

L'assistant web contient maintenant une étape **Accès à distance**, après Qualité
et avant Vérification. Ce n'est plus la maquette HTML séparée.

## Parcours

1. Choisir **Sur cet ordinateur** ou **Sur un serveur ou un NAS**. En SSH,
   tester la connexion puis confirmer l'empreinte présentée.
2. Choisir les applications et les dossiers comme auparavant. Les chemins SSH
   sont ceux du serveur, jamais ceux du PC qui affiche l'assistant.
3. À l'étape 5 sur 7, choisir **Chez moi**, **Tailscale**, **Mon domaine** ou
   **Tunnel Cloudflare**.
4. Confirmer l'installation de la stack.
5. Pour une installation locale, activer ensuite l'accès distant. Pour une
   installation SSH, PlugArr tente l'activation sur le serveur après la stack ;
   son échec ne remet pas en cause l'installation des applications.
6. Consulter **Configurer mon téléphone** : nzb360 ou qbRemote, application,
   connexion locale ou distante. Copier URL, port et clé API ou identifiants.
7. Télécharger le fichier d'accès. Les fiches restent utilisables hors ligne.

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

## Sous-domaines

Pour **Mon domaine** comme pour **Tunnel Cloudflare**, chaque application reçoit un
sous-domaine, modifiable dans l'assistant web comme dans la TUI : `series` au lieu de
`sonarr` par exemple, si `sonarr.mondomaine.fr` sert déjà à autre chose. Lettres,
chiffres et tirets, un seul niveau, deux applications jamais sur le même nom. Les
noms par défaut ne sont pas écrits dans `stack.yml`.

## Tunnel Cloudflare

Le serveur ouvre une connexion **sortante** vers Cloudflare : aucun port à rediriger,
IP de la box non publiée, et le CGNAT n'y change rien. Il faut un domaine dont le DNS
est géré par Cloudflare.

1. Dans Cloudflare : **Networking**, **Tunnels**, **Create a tunnel**. Choisir Docker
   et copier la commande affichée. La coller telle quelle dans PlugArr : seul le jeton
   est gardé, après vérification de sa forme.
2. Créer un tunnel **réservé à PlugArr**. Un jeton qui tourne déjà sur une autre
   machine en ferait une réplique : Cloudflare enverrait une partie du trafic à
   l'autre machine, qui ne connaît pas ces applications.
3. Indiquer le domaine de la zone Cloudflare (`mondomaine.fr`). Le certificat gratuit
   de Cloudflare ne couvre qu'un niveau de sous-domaine : `series.maison.mondomaine.fr`
   n'aurait pas de certificat.
4. Après l'installation, activer l'accès distant. PlugArr démarre `cloudflared`
   (image épinglée par version et empreinte) à côté des applications, puis affiche
   les routes à créer : onglet **Routes** du tunnel, **Add route**, **Published
   application**, avec le sous-domaine, le domaine et l'URL du service à recopier
   (`http://sonarr:8989`, ou `http://gluetun:8080` pour qBittorrent derrière le VPN).
5. Si Cloudflare répond « An A, AAAA, or CNAME record with that host already exists »,
   le nom est déjà pris : choisir un autre sous-domaine dans PlugArr, ou supprimer
   l'ancien enregistrement.
6. **Actualiser l'état** : PlugArr lit le journal du connecteur, puis interroge chaque
   adresse publique. L'API doit refuser un accès anonyme **et** accepter la clé API de
   cette installation : une adresse qui mène à une autre instance (ancien `sonarr.`
   relié à un autre tunnel) est signalée comme telle. Sont aussi reconnus : adresse
   absente du DNS, aucun connecteur actif (erreur 1033), route vers une mauvaise URL
   (502), Cloudflare Access ou vérification anti-robot devant l'adresse.

Ne pas placer Cloudflare Access devant ces adresses : nzb360 et qbRemote ne
passeraient plus, et PlugArr le signale. Si une application Access couvre tout le
domaine (`*.mondomaine.fr`), ajouter ces adresses à une application Access en
**Bypass** : Access évalue le Bypass en premier (essai réel du 27/09/2026). L'authentification des applications reste
exigée comme en mode domaine. Le jeton est un secret : il est gardé dans `stack.yml`
et dans `.plugarr-remote/tunnel.env` (droits 600), jamais renvoyé au navigateur ni
écrit dans le rapport. À la reprise, un champ vide conserve le jeton enregistré.
Désactiver arrête le connecteur ; le tunnel et ses routes restent dans le compte
Cloudflare.

Sur un serveur SSH, l'activation tourne dans l'image d'administration PlugArr
épinglée (`catalog.CONSOLE_IMAGE`), tout comme la console en conteneur. Cette image
est en 0.12.2 et connaît le tunnel et les sous-domaines personnalisés
(`catalog.CONSOLE_IMAGE_TUNNEL_CLOUDFLARE`). Si on épingle un jour une image plus
ancienne, remettre ce drapeau à `False` : l'assistant refusera alors ces choix
plutôt que de laisser l'image refuser toute la pile.

## Sécurité et limites de cette livraison

- Le fichier HTML contient les vrais secrets en installation réelle, même lorsque
  les champs sont masqués. Ne pas le publier ni le partager. Caddy ne le sert pas.
- La passerelle est stockée dans `.plugarr-remote`, séparément de la stack principale.
  Ses données persistantes se trouvent dans le dossier de configuration des applications.
- L'arrêt de la passerelle Docker ne déconnecte pas un client Tailscale natif.
- Le choix distant est enregistré dans `stack.yml`. Après un redémarrage du parcours,
  l'état de connexion doit être vérifié à nouveau.
- Les identifiants SSH et sudo restent uniquement en mémoire dans l'assistant.
  Ils ne sont pas copiés dans la pile, les journaux ou le rapport final.
- La cible SSH V1 est Linux ou NAS avec Docker déjà installé et accessible au
  compte fourni. Aucun Python ni PlugArr préalable n'est requis sur la cible.
- L'empreinte affichée lors du diagnostic doit être confirmée et elle est
  revérifiée à chaque opération distante.
- Le mode `web --demo` simule l'installation et l'activation, sans Docker ni modification réseau.
- Aucun déploiement réel Caddy/Tailscale ni test sur téléphone n'a été effectué pour
  cette livraison. Ce sont les prochains essais d'intégration à faire sur un serveur de test.
- La reprise automatique d'une ancienne pile distante n'est pas encore exposée
  dans cette première version SSH. Si un `stack.yml` différent existe déjà dans
  le dossier choisi, PlugArr refuse de l'écraser. Une relance du même plan après
  un échec reste possible car son empreinte est identique.

## Vérifications reproductibles

- Tests Python : `tests/test_remote_install.py`, `tests/test_remote_access.py`,
  `tests/test_remote_cloudflare.py`,
  tests du webwizard, du dashboard,
  de la reprise et de l'empaquetage.
- Test navigateur Chromium : `tests/js/wizard_remote.cjs`, avec Playwright disponible.
  Il teste les trois choix, le rejet d'un domaine mal formé, la confirmation
  d'activation, les fiches et la réouverture du HTML à 390 pixels de largeur.
  `PLUGARR_TEST_EXE` permet d'exécuter le même parcours sur l'EXE compilé.
