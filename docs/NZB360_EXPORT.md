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
5. Tester Sonarr, Radarr et qBittorrent. Pour Tailscale, connecter aussi le téléphone.

Un fichier contient toutes les applications compatibles dont l'adresse et les
identifiants sont disponibles pour le réseau choisi. Les exclusions sont affichées.
Le profil distant ne retombe pas sur les adresses locales. Pas de bascule automatique
Wi-Fi dans cette première version. Prowlarr et Seerr restent réservés à l'export
Arr Control : leur format nzb360 n'est pas établi par l'échantillon fourni.

En démonstration, le nom du fichier comporte `demo` et les accès sont fictifs.
Une restauration de cette démonstration ne donne pas une installation fonctionnelle.

## Construction et confidentialité

Le ZIP contient trois flux de sérialisation Java HashMap, conformément à la structure
observée dans la sauvegarde 24.4.1 fournie :

- `com.kevinforeman.nzb360_preferences.xml` : version, activation des trois services,
  adresses principales et identifiants de la stack concernée, champs locaux/SSID vides.
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

Le format binaire est valide, mais la restauration Android et les préférences
minimales attendues par nzb360 restent à confirmer. Ne pas présumer que cet import
fusionne avec les serveurs existants ou conserve les réglages globaux.

Références : [analyse de l'échantillon](NZB360_FORMAT_RESEARCH.md),
[protocole Java](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/protocol.html),
[format ZIP PKWARE](https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT).
