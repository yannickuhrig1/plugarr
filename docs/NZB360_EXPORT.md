# Export expérimental nzb360 24.4.1

Le même paquet PlugArr propose maintenant les exports Arr Control (JSON) et
nzb360 (ZIP) dans « Configurer mon téléphone », ainsi que dans le HTML téléchargé.

## Essai

1. Faire une sauvegarde complète dans nzb360 avant tout essai : la restauration
   remplace tous les réglages (constaté sur téléphone). Pour garder les siens,
   partir de cette sauvegarde (voir « Fusion » plus bas).
2. Choisir **nzb360**, puis le profil local ou distant dans le bloc d'export.
3. Cocher la confirmation après avoir sauvegardé ses réglages.
4. Télécharger le ZIP et le sélectionner dans la fonction de sauvegarde/restauration
   de nzb360 **24.4.1**. Ne pas décompresser ce ZIP pour l'import.
5. Tester Sonarr, Radarr, Lidarr, Seerr, qBittorrent ou Transmission, et SABnzbd. Pour Tailscale, connecter aussi le téléphone.

Un fichier contient toutes les applications compatibles dont l'adresse et les
identifiants sont disponibles pour le réseau choisi. Les exclusions sont affichées.
Prowlarr reste réservé à l'export Arr Control : nzb360 le range parmi les
indexeurs, dans un objet Java qui lui est propre (voir « Relevé du 19 septembre »).

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

### Lidarr, Seerr et Transmission

Clés relevées le 19 septembre 2026 dans une sauvegarde faite après avoir
configuré ces services, avec de fausses adresses, dans un second profil :

- Lidarr : préfixe `lidarr_`, même modèle que Radarr (`_server_enabled_preference`,
  adresses principale et locale, `_server_SSID_preference`,
  `_localconnectionswitch_preference`, `_apikey_preference`) ;
- Seerr : préfixe `overseerr_`, même modèle ;
- Transmission : les clés `torrent_` de qBittorrent, avec
  `torrent_client_preference` à `transmission`. nzb360 n'a qu'un client
  torrent par profil : qBittorrent passe avant Transmission quand les deux
  sont installés.

Comme SABnzbd, PlugArr ne leur donne pas d'accès distant : ils n'entrent que
dans le profil local. Seerr crée lui-même sa clé API : PlugArr la lit au câblage
(`GET /api/v1/settings/main`, réservé à l'administrateur, vérifié sur un Seerr
3.4.1 jetable : clé égale à celle de son `settings.json`). Une installation
câblée avant cet ajout n'a pas la clé : relancer le câblage. Aucun de ces trois services n'a encore été essayé en connexion réelle
sur le téléphone.

En démonstration, le nom du fichier comporte `demo` et les accès sont fictifs.
Une restauration de cette démonstration ne donne pas une installation fonctionnelle.

## Fusion avec la sauvegarde de l'utilisateur

« Partir de ma sauvegarde nzb360 » : le navigateur relit les trois flux Java de
la sauvegarde (chaînes, booléens, Integer, Long, Float, Double ; références
Java comprises), puis n'écrit que les clés des services PlugArr. nzb360 n'a
qu'un Sonarr, un Radarr, etc. par profil : un service déjà présent dans la
sauvegarde (il a une adresse, même désactivé) est **gardé par défaut**, une
case permet de le remplacer. Tout le reste est recopié : autres services,
préférences, et `nzb360prefs.xml` (licence) à l'octet près. Un type Java inconnu
fait refuser le fichier plutôt que de le réécrire au hasard.

Vérifié sur une vraie sauvegarde 24.4.1 (132 + 10 clés) : relue puis réécrite,
elle est égale à l'originale pour `ObjectInputStream` (mêmes clés, valeurs et
types) ; en remplaçant Sonarr, seules ses 4 clés changent, plus l'interrupteur
de bascule.

Validé sur le téléphone le 19 septembre 2026 : sauvegarde fraîche fusionnée par
l'interface (Radarr remplacé, le reste gardé), restauration acceptée. Le tiroir
garde Torrents, Sonarr, Radarr et Tautulli ; Radarr passe sur celui du banc par
l'adresse locale, Sonarr et Tautulli restent ceux de l'utilisateur.

Un Transmission ou un qBittorrent déjà présent occupe le même emplacement
torrent : la case de remplacement nomme le client de la sauvegarde.

### Relevé du 19 septembre : profils et indexeurs

- `servers.xml` est une `HashMap` dont la clé `servers` contient un
  `java.util.HashSet` de chaînes : `"000Default*"`, `"001test"`. Chaque profil
  autre que Default a ses réglages dans `NNN.xml` (`001.xml`), avec les mêmes
  noms de clés ; Default reste dans `com.kevinforeman.nzb360_preferences.xml`.
- `nzb360prefs.xml` note le profil en cours dans `lastActiveProfile` : `*` pour
  Default, `001` pour le profil de `001.xml`.
- Prowlarr est un indexeur : `nzb360indexers.bkp`, liste Java de
  `com.kevinforeman.sabconnect.searchproviders.NewznabIndexer` (clé API, date
  Joda, propriétés de serveur). Trop fragile à produire, PlugArr ne l'écrit pas.
- La restauration ne supprime pas un indexeur absent de la sauvegarde.

La fusion n'écrit que le profil Default et recopie `servers.xml`, les `NNN.xml`
et les indexeurs à l'octet près. Si la sauvegarde est sur un autre profil,
l'assistant le signale. Piste suivante : écrire un profil « PlugArr » à part
(`002.xml` et une entrée dans le `HashSet`), ce qui demande d'écrire ce type Java.

## Construction et confidentialité

Le ZIP contient trois flux de sérialisation Java HashMap, conformément à la structure
observée dans la sauvegarde 24.4.1 fournie :

- `com.kevinforeman.nzb360_preferences.xml` : version, activation des services,
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
