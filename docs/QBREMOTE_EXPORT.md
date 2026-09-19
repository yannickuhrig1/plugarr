# Export expérimental qbRemote 1.8.0

« Configurer mon téléphone » propose, pour qbRemote, un fichier de sauvegarde
à restaurer dans l'application. Il est aussi disponible dans le HTML téléchargé.

## Format constaté

Source : une sauvegarde faite par qbRemote 1.8.0 (73) le 18 septembre 2026,
fournie par l'utilisateur avec son mot de passe. Inspectée en local, mots de
passe masqués, rien n'est copié dans le dépôt.

- ZIP chiffré WinZip AES : AE-1, AES-256, contenu en deflate, CRC réel.
  En-têtes : version 20, drapeaux `0x801` (chiffré, noms UTF-8).
- Huit fichiers JSON. `manifest.json` (`version: 1`, `createdAt`,
  `appVersion`) et `servers.json` (liste des serveurs) portent la connexion ;
  les autres sont des préférences d'affichage et des historiques.
- Chaque serveur a une adresse principale (`scheme`, `host`, `port` en texte,
  `path`) et une adresse locale facultative (`localSsid`, `localScheme`,
  `localHost`, `localPort`, `localPath`), plus `username` et `password`.

La fonction de sauvegarde est annoncée dans les nouveautés de la 1.8.0
(« Encrypted ZIP backup (AES-256), credentials included »,
[fiche Play Store](https://play.google.com/store/apps/details?id=me.fengmlo.qbRemote)).
Le format lui-même n'est pas documenté publiquement.

## Ce que PlugArr écrit

`manifest.json` et `servers.json` seulement, avec un serveur « PlugArr » vers
qBittorrent. Les préférences d'affichage ne sont pas imposées.

- Profil local : l'adresse du réseau local.
- Profil distant : l'adresse HTTPS ou Tailscale. Si le nom du Wi-Fi de la
  maison est saisi, l'adresse locale est ajoutée dans les champs `local*` pour
  que qbRemote bascule seul à la maison.
- Le mot de passe du fichier est choisi dans l'assistant (4 caractères au
  moins) ; qbRemote le demande à la restauration.

Le chiffrement se fait dans le navigateur (WebCrypto, `CompressionStream`),
y compris depuis la page HTML ouverte en `file://`.

## Validé sur téléphone (18 septembre 2026)

Xiaomi 13T Pro, Android 16, qbRemote 1.8.0 (73), piloté par adb. Fichier
généré par la page d'accès, adresse distante volontairement injoignable
(`.invalid`), adresse locale vers le qBittorrent 5.2.3 du banc d'essai.

- **Fichier accepté** : qbRemote demande le mot de passe, déchiffre, puis
  propose les parties présentes. Seule « Serveurs » est cochable : une
  sauvegarde partielle est un cas prévu par l'application, qui sait aussi en
  produire (cases Paramètres, Serveurs, Certificats, Historique ; mot de passe
  facultatif).
- **La restauration remplace tous les serveurs** existants. Les préférences
  d'affichage, absentes du fichier, restent.
- **Champs repris à l'identique**, y compris « Réseau local » :
  SSID, schéma, hôte, port. `apiVersion: null` est accepté.
- **La bascule fonctionne** : après une coupure puis un retour du Wi-Fi,
  qbRemote passe sur l'adresse locale (icône Wi-Fi à côté du nom du serveur)
  et affiche les torrents du banc.
- **Condition** : l'autorisation de localisation. Sans elle, Android ne donne
  pas le nom du Wi-Fi et qbRemote reste sur l'adresse distante. qbRemote ne la
  demande qu'à l'ouverture de la fiche « Réseau local » du serveur : la notice
  de l'assistant le dit.

Faire une sauvegarde qbRemote avant toute restauration.

## Validation

`tests/js/qbremote_export.cjs` relit le fichier avec un déchiffreur WinZip AES
écrit à part (`node:crypto`) : vérificateur de mot de passe, HMAC, CRC,
contenu JSON, et absence de secret lisible sans le mot de passe. Il est lancé
par `tests/test_remote_access.py`. Le fichier a aussi été relu par `pyzipper`
lors de la mise au point.
