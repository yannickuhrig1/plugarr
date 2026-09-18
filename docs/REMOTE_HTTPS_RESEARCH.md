# Faisabilité de l'accès distant HTTPS pour PlugArr

Recherche documentaire du 15 septembre 2026. Aucun déploiement ni test mobile réalisé.

## Conclusion

Faisable comme option explicite, avec un sous-domaine par application et un reverse proxy Caddy. L'utilisateur pourrait saisir une URL HTTPS permanente dans son client mobile. L'activation dépend d'un domaine, de la connectivité entrante et de l'authentification effective des services. Un simple export HTML ne suffit pas.

## Intégration dans le projet

Constats de code transmis par l'analyse principale :

- `models.py:294` construit actuellement `ServiceInstance.url` en HTTP avec hôte et port. Ajouter un champ `external_url` indépendant ; préserver les adresses internes pour les communications entre services.
- `models.py:298` fournit `internal_url`, qui connaît déjà le passage par Gluetun. Caddy pourrait rejoindre le réseau `plugarr` hors de Gluetun ; pour qBittorrent sous VPN, la cible serait Gluetun et le port WebUI interne correspondant.
- Aucun proxy n'est actuellement généré dans Compose.
- `compose.py:68` démarre Flood avec `--auth=none`. Exclure Flood du périmètre distant initial tant qu'une authentification appropriée n'est pas fournie.
- `seed.py:285-286` désactive les protections Host Header et CSRF de qBittorrent. Revoir ce réglage avant exposition Internet et vérifier les en-têtes du proxy avec protections actives.
- `seed.py:455` et suivantes configurent la liste d'hôtes SABnzbd. Intégrer les domaines externes à sa validation si SABnzbd entre ultérieurement dans le périmètre.
- Le fichier HTML contenant les mots de passe et clés API doit rester un document privé récupéré sur le PC. Aucun hébergement de ce fichier par Caddy.

## DNS, certificats et connexion entrante

Caddy obtient et renouvelle les certificats de domaines publics automatiquement. Le parcours standard suppose un DNS A/AAAA correct et une redirection des ports 80/443 vers Caddy. Le challenge HTTP utilise 80, TLS-ALPN utilise 443. Le challenge DNS permet d'obtenir le certificat sans connexion entrante, mais ne fournit aucun chemin réseau pour les clients. Il nécessite des droits chez le fournisseur DNS et le support correspondant dans Caddy. [Caddy, Automatic HTTPS](https://caddyserver.com/docs/automatic-https)

Un CGNAT opérateur empêche normalement la redirection entrante IPv4 depuis la box. Vérifier une IP publique utilisable, ou envisager une passerelle publique avec tunnel sortant. Un DNS dynamique résout le changement d'IP, pas le CGNAT. [TP-Link, diagnostic officiel des redirections de ports](https://www.tp-link.com/us/support/faq/785/)

Inférence d'architecture : commencer par le cas domaine et IP publique avec ports disponibles ; traiter le tunnel public comme un second mode, car son authentification et ses dépendances changent le parcours. Détecter aussi un proxy existant, notamment un conflit avec les ports d'administration du NAS, et proposer l'intégration à celui-ci.

## Compatibilité mobile et authentification

Le site officiel de nzb360 annonce SSL/TLS, HTTP Auth, en-têtes personnalisés, reverse proxies et bascule locale/distante. Sonarr, Radarr, Prowlarr et qBittorrent figurent parmi les services pris en charge. La compatibilité de principe est donc documentée. [nzb360](https://www.nzb360.com/)

Le guide maintenu par son développeur documente aussi Cloudflare Access avec des en-têtes de service. Une couche d'authentification supplémentaire est donc possible pour nzb360, à condition de la configurer pour les requêtes du client ; une simple redirection vers une connexion interactive n'est pas une preuve de compatibilité API. [Guide distant nzb360](https://github.com/Kev1000000/nzb360Guides/blob/main/remoteaccessguide.html)

La fiche de qbRemote par fengmlo confirme l'utilisation de la WebUI API de qBittorrent. Elle ne suffit pas à garantir la prise en charge d'une deuxième authentification HTTP, de jetons Cloudflare Access, de SSO ou de toutes les réécritures de chemin. Ne pas confondre qbRemote Android avec qRemote pour iOS, une autre application. [Fiche officielle qbRemote](https://play.google.com/store/apps/details?id=me.fengmlo.qbRemote&hl=en)

Proposition initiale : sous-domaines distincts, HTTPS et authentification native toujours requise. Les clients Arr utilisent leur clé API ; qBittorrent conserve sa connexion utilisateur/mot de passe selon le client. Ne pas ajouter automatiquement une page SSO devant les API. Ne jamais désactiver toute authentification sur les chemins API pour faire fonctionner un client.

La documentation Sonarr recommande de limiter les réseaux de proxies de confiance et décrit le risque des exceptions d'authentification pour adresses locales. Configurer une authentification requise et valider les en-têtes transmis. [Paramètres officiels Sonarr](https://github.com/Servarr/Wiki/blob/master/sonarr/settings.md)

## Particularités qBittorrent

Le wiki officiel documente le reverse proxy et les en-têtes Host, X-Forwarded-For, X-Forwarded-Host et X-Forwarded-Proto. Il marque les manipulations supprimant Origin/Referer comme obsolètes et déconseillées pour les versions récentes. Les cookies Secure dépendent aussi de la version du serveur. Transposer le comportement à Caddy et vérifier la version réellement utilisée avant d'écrire la configuration finale. [Reverse proxy officiel qBittorrent](https://github.com/qbittorrent/qBittorrent/wiki/NGINX-Reverse-Proxy-for-Web-UI)

Inférence : la connexion venant du proxy peut apparaître comme locale au backend. Il faut vérifier que les exceptions d'authentification locales ou par sous-réseau ne permettent jamais à un utilisateur distant de contourner le login.

## Validation requise avant annonce de support

1. Génération correcte avec et sans VPN de téléchargement, en conservant les URL internes existantes.
2. Résolution DNS et certificat valide depuis une connexion extérieure ; renouvellement persistant après redémarrage.
3. Rejet des accès anonymes et des identifiants incorrects, y compris avec des en-têtes d'adresse locale falsifiés.
4. Connexion API Sonarr/Radarr/Prowlarr et session qBittorrent par HTTPS.
5. Lecture réelle depuis nzb360 et qbRemote en réseau mobile, puis action contrôlée sur un élément de test.
6. Vérification que la page HTML privée, l'administration du NAS et les services non sélectionnés ne sont pas publiés.

Les documents Servarr Radarr/Prowlarr consacrés au proxy existent, mais leur contenu n'a pas été extrait par l'outil web pendant cette recherche. Aucune configuration exacte n'en est déduite ici. La configuration finale et la compatibilité qbRemote doivent être prouvées expérimentalement.
