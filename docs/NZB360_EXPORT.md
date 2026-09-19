# Export expérimental nzb360 24.4.1

Le même paquet PlugArr propose maintenant les exports Arr Control (JSON) et
nzb360 (ZIP) dans « Configurer mon téléphone », ainsi que dans le HTML téléchargé.

## Essai

1. Faire une sauvegarde complète dans nzb360 avant tout essai. Utiliser de préférence
   une installation séparée de l'application : le traitement des réglages existants
   par la restauration n'a pas été vérifié.
2. Choisir **nzb360**, puis le profil local ou distant dans le bloc d'export.
3. Cocher la confirmation après avoir sauvegardé ses réglages.
4. Télécharger le ZIP et le sélectionner dans la fonction de sauvegarde/restauration
   de nzb360 **24.4.1**. Ne pas décompresser ce ZIP pour l'import.
5. Tester Sonarr, Radarr, qBittorrent et SABnzbd. Pour Tailscale, connecter aussi le téléphone.

Un fichier contient toutes les applications compatibles dont l'adresse et les
identifiants sont disponibles pour le réseau choisi. Les exclusions sont affichées.
Prowlarr et Seerr restent réservés à l'export Arr Control : leur format nzb360
n'est pas établi par l'échantillon fourni.

### Un seul fichier pour la maison et l'extérieur

En profil distant, un nom de Wi-Fi facultatif remplit, pour chaque service, les
trois champs relevés dans l'échantillon : `*_server_primary_connectionstring_preference`
(adresse distante), `*_server_local_connectionstring_preference` (adresse locale)
et `*_server_SSID_preference` (nom du Wi-Fi). Sans nom de Wi-Fi, le profil
distant ne retombe pas sur les adresses locales.

Ces trois champs ne suffisent pas : nzb360 a aussi un interrupteur « Enable Local
Connection Switching », désactivé par défaut. Ses clés ont été lues dans une
sauvegarde faite après l'avoir activé : `nzbdrone_localconnectionswitch_preference`,
`radarr_localconnectionswitch_preference`, `torrent_localconnectionswitch_preference`
(booléens). L'export le met à `true` quand une adresse locale est remplie.

### SABnzbd

Clés relevées : `sabnzbd_server_primary_connectionstring_preference`,
`sabnzbd_server_local_connectionstring_preference` et `sabapi_preference`.
L'échantillon n'a pas de `sabnzbd_server_enabled_preference` ; l'activation
passe par `server_enabled_preference` et le Wi-Fi par `server_SSID_preference`,
clés génériques que nous attribuons à SABnzbd (nzb360 est né client SABnzbd).
**C'est une déduction, pas un constat** : à vérifier en premier sur le téléphone.
PlugArr ne gère pas d'accès distant pour SABnzbd : il n'entre que dans le profil local.

En démonstration, le nom du fichier comporte `demo` et les accès sont fictifs.
Une restauration de cette démonstration ne donne pas une installation fonctionnelle.

## Construction et confidentialité

Le ZIP contient trois flux de sérialisation Java HashMap, conformément à la structure
observée dans la sauvegarde 24.4.1 fournie :

- `com.kevinforeman.nzb360_preferences.xml` : version, activation des trois services,
  adresses principales et identifiants de la stack concernée ; champs locaux/SSID
  remplis seulement en profil distant avec un nom de Wi-Fi, vides sinon.
- `nzb360prefs.xml` : version 24.4.1 uniquement.
- `servers.xml` : map vide, comme dans l'échantillon du serveur par défaut.

C'est un export minimal généré de zéro, pas une copie de la sauvegarde personnelle.
Aucune préférence de licence, d'achat, aucun historique ni secret du fichier utilisateur
n'est inclus. Aucun déchiffrement, aucun téléchargement de bibliothèque externe.
Le ZIP n'est pas chiffré : le conserver comme un mot de passe.

## Validation et limites

Les tests couvrent les trois services, les profils réseau, les identifiants absents,
les champs trop longs, les accents, les caractères nuls et les caractères Unicode
supplémentaires, l'absence de préférences de licence, les CRC du ZIP et sa lecture
par `ObjectInputStream` dans une JVM indépendante (données synthétiques seulement).
Le téléchargement est également testé dans l'assistant et le HTML hors ligne.

### Validé sur téléphone (18 septembre 2026)

Xiaomi 13T Pro, Android 16, nzb360 24.4.1, piloté par adb. Adresses distantes
volontairement injoignables (`.invalid`), adresses locales vers le banc d'essai.

- **Restauration acceptée** (« Restored backup successfully! »), champs repris à
  l'identique : adresses, clés API, identifiants qBittorrent, adresse locale, SSID.
- **La restauration remplace tous les réglages** : un service absent du fichier
  (Tautulli dans l'essai) disparaît. Une sauvegarde nzb360 préalable est indispensable.
- **Bascule** : avec les interrupteurs posés par l'export, Sonarr, Radarr et
  qBittorrent se connectent par l'adresse locale sans aucun réglage manuel.
  nzb360 demande lui-même l'autorisation de localisation, sans laquelle Android
  ne donne pas le nom du Wi-Fi.
- **SABnzbd n'a pas été testé** : il n'est pas installé sur le banc. Sa clé
  d'activation reste une déduction.

Références : [analyse de l'échantillon](NZB360_FORMAT_RESEARCH.md),
[protocole Java](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/protocol.html),
[format ZIP PKWARE](https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT).
