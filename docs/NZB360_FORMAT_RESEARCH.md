# Recherche sur le format des sauvegardes nzb360

Recherche documentaire du 16 septembre 2026, complétée par une inspection locale de la sauvegarde fournie. Aucun secret reproduit dans cette note, aucun essai de restauration effectué.

## Résultats établis

- **Sauvegarde et restauration natives : oui.** Dans son annonce de la version 13.8.7 du 18 octobre 2020, Kev1000000 décrit la réécriture du mécanisme et annonce que les anciennes sauvegardes ZIP restent utilisables. Cela établit une compatibilité historique, pas une spécification actuelle du format. [Annonce du développeur](https://www.reddit.com/r/nzb360/comments/jda5m1/new_release_v1387/).
- **Édition externe : aucun format public exploitable trouvé dans les sources primaires consultées.** Le 12 février 2024, à une question sur des XML apparemment malformés dans une sauvegarde ZIP, Kev1000000 répond que ces fichiers ne sont pas destinés à être lisibles par un humain. Il conseille de préparer une configuration dans l'application puis d'en faire une sauvegarde, et enfin de restaurer la sauvegarde originale. [Réponse du développeur, « Edit backup file? »](https://www.reddit.com/r/nzb360/comments/1ap7do3/edit_backup_file/).
- **Supprimer un service ne supprime pas ses données.** Dans le même échange, Kev1000000 précise qu'il faut vider les champs pour exclure leur contenu d'une sauvegarde. Une sauvegarde préparée simplement en désactivant ou retirant des services ne doit donc pas être présumée dépourvue de leurs identifiants. [Précision du développeur](https://www.reddit.com/r/nzb360/comments/1ap7do3/edit_backup_file/).

## Points non établis

- **Chiffrement : non confirmé.** L'absence de lisibilité ne démontre pas un chiffrement. Les sources consultées ne fournissent ni algorithme, ni schéma de sérialisation, ni contrat de génération externe. Ne pas présenter « sauvegarde chiffrée » comme un fait acquis.
- **Génération par un logiciel tiers : support officiel non établi.** Aucun schéma, SDK ou point d'import de configuration générée extérieurement n'a été trouvé dans cette recherche bornée. Ce constat ne prouve pas qu'une telle interface n'existe pas.
- **Fusion ou remplacement à la restauration : non établi.** Le conseil de restaurer une sauvegarde complète ne décrit pas précisément le traitement des services déjà présents, des champs absents ou des paramètres globaux. Ne pas promettre un import additif et ne pas affirmer un remplacement intégral sans vérification supplémentaire.

## Conséquence pour PlugArr

Les preuves disponibles permettent de documenter une configuration manuelle et le mécanisme natif de sauvegarde/restauration. Elles ne suffisent pas à garantir un générateur de sauvegarde nzb360 ni un import préservant les autres services. Toute implémentation dépendant du format exige une spécification du développeur ou un test isolé avec des données fictives et une version explicitement identifiée.

Le [site officiel](https://nzb360.com/) et le [guide officiel d'accès distant](https://github.com/Kev1000000/nzb360Guides/blob/main/remoteaccessguide.html) ont également été consultés. L'import de fichier décrit dans ce guide concerne WireGuard, pas une sauvegarde nzb360.

## Inspection locale de l'échantillon 24.4.1

Source : `nzb360_backup_2026_09_16.zip`, fourni par l'utilisateur, inspecté en lecture
seule sans extraction ni exécution Java. La version 24.4.1 déclarée par l'utilisateur
est aussi présente dans les deux ensembles de préférences.

L'archive contient trois entrées :

| Entrée | Octets décompressés | Contenu constaté |
|---|---:|---|
| `com.kevinforeman.nzb360_preferences.xml` | 6297 | 132 préférences |
| `nzb360prefs.xml` | 515 | 10 préférences internes |
| `servers.xml` | 82 | Map vide |

Les trois flux commencent par `AC ED 00 05` et représentent des `java.util.HashMap`,
pas du XML textuel. Les valeurs rencontrées sont des chaînes et des objets Java
Boolean, Integer ou Long. L'ensemble des trois flux a été parcouru par un lecteur
passif limité à ces types, avec contrôle de fin de flux et du nombre de paires.
Leur structure correspond au [protocole de sérialisation Java documenté par Oracle](https://docs.oracle.com/en/java/javase/21/docs/specs/serialization/protocol.html).
Les adresses et secrets sont récupérables sans mot de passe de déchiffrement :
ce fichier doit être traité comme une sauvegarde sensible, pas comme un coffre chiffré.

Champs pertinents constatés, valeurs volontairement non reproduites :

| Service | Adresse principale | Adresse locale | Authentification |
|---|---|---|---|
| Sonarr | `nzbdrone_server_primary_connectionstring_preference` | `nzbdrone_server_local_connectionstring_preference` | `nzbdrone_apikey_preference` |
| Radarr | `radarr_server_primary_connectionstring_preference` | `radarr_server_local_connectionstring_preference` | `radarr_apikey_preference` |
| qBittorrent | `torrent_server_primary_connectionstring_preference` | `torrent_server_local_connectionstring_preference` | `torrent_username`, `torrent_password` |

Le champ `torrent_client_preference` désigne bien qBittorrent dans cet échantillon.
Les trois indicateurs d'activation sont présents. Les champs d'adresse locale sont
vides : cet exemple ne permet pas à lui seul de valider la bascule automatique Wi-Fi.

L'archive contient également d'autres identifiants de services et des préférences
internes de licence. Ne pas incorporer cette archive dans PlugArr, dans les tests,
dans un EXE ou dans un modèle distribué. Un éventuel export doit être construit
avec une liste explicite de champs autorisés et les accès de la stack concernée,
sans copie des préférences de licence ni des secrets de l'échantillon.

Conclusion actualisée : un générateur expérimental ciblé sur 24.4.1 est techniquement
envisageable à partir du format identifié. Sa compatibilité applicative, les valeurs
par défaut requises, le comportement multi-serveur et les effets d'une restauration
restent à tester dans une installation nzb360 isolée avant de l'annoncer fonctionnel.
Cette inspection n'a pas modifié le programme ni généré une nouvelle sauvegarde.
