# Export pour restauration dans Arr Control

PlugArr propose **Arr Control** dans « Configurer mon téléphone », à la fin de
l'assistant web et dans la page HTML privée téléchargée. Cliquer sur
**Télécharger pour Arr Control** génère un JSON de serveur, sans appel à un service externe.

## Utilisation

1. Choisir Arr Control dans les fiches mobiles.
2. Choisir le profil **Réseau local** ou **À distance** dans le bloc d'export.
3. Télécharger le JSON et le transférer de manière privée au téléphone.
4. Sauvegarder les réglages Arr Control actuels, puis utiliser son import/restauration
   de serveur pour sélectionner ce fichier. Les libellés exacts du menu et la
   conservation des serveurs existants restent à confirmer sur l'application réelle.
5. Tester la connexion dans Arr Control. Pour le profil Tailscale, connecter aussi
   Tailscale sur le téléphone.

Le fichier inclut toutes les applications prises en charge pour le profil choisi,
pas seulement celle dont la fiche est affichée. Les services sans adresse ou sans
identifiants disponibles sont exclus et listés avant téléchargement. Aucun bouton
d'export n'est actif si le profil est vide. Un export distant ne se rabat jamais
silencieusement sur une adresse locale.

Chaque fichier correspond à un seul réseau. L'adresse choisie est enregistrée
dans `url` et `config.fields.localUrl`, avec `remoteAccess: false`, comme dans
l'échantillon fourni. Un profil distant peut donc utiliser une URL HTTPS ou
Tailscale dans ces deux champs. Cette version n'essaie pas de configurer une
bascule Wi-Fi automatique dont le comportement n'a pas été vérifié.

## Format et périmètre

Source primaire du format : export `default-server-export.json` fourni le
16 septembre 2026, inspecté localement sans afficher ni réutiliser ses secrets.
Schéma version **1** : `version`, `exportedAt` (millisecondes), `server`, `services`.
Les catégories et champs sont reproduits uniquement pour les services observés :

| Service | Catégorie Arr Control | Authentification |
|---|---|---|
| Sonarr, Radarr | `library` | clé API |
| Prowlarr | `indexers` | clé API |
| Seerr | `requests` | clé API |
| qBittorrent | `downloads` | utilisateur et mot de passe |

Les autres services de PlugArr ne sont pas exportés tant que leur format n'est pas
établi. Le choix HTTPS actuel de PlugArr expose uniquement Sonarr, Radarr et
qBittorrent : cet ajout ne publie pas Prowlarr ou Seerr sur Internet.

Le [descriptif officiel d'Arr Control](https://play.google.com/store/apps/details?id=com.mpolat3.arrstackv3)
présente la gestion de plusieurs serveurs et des applications de cette famille,
mais n'est pas une spécification du fichier d'import.

## Confidentialité et validation

Le JSON n'est pas chiffré et contient les identifiants de l'installation concernée.
Le conserver comme un mot de passe. Le fichier utilisateur d'origine n'est ni
embarqué ni copié dans les sources ou dans l'EXE. Les exports de démonstration
portent `DEMO` dans le nom du serveur et `demo` dans le nom de fichier.

Tests automatisés : schéma, correspondances des cinq services, exclusions,
absence de lien d'association Tailscale dans le JSON, téléchargement depuis
l'assistant et depuis le HTML hors ligne. Aucune restauration sur Android n'a
été réalisée : compatibilité à valider dans Arr Control avant usage habituel.

Cet export n'ajoute pas une fonction de restauration de la stack dans PlugArr.
Il prépare un fichier destiné à l'import/restauration du serveur dans Arr Control.
