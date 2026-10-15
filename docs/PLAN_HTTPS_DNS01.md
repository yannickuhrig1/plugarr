# Adresses HTTPS privées par DNS-01

Plan du 15 octobre 2026. L'étape 0 est en place (recette et CI, image pas encore
publiée). Le reste n'est pas implémenté, et aucun essai réel n'a été fait.
Idée reprise de [Caretakarr](https://github.com/caretakarr/caretakarr) (MIT, Go) :
on reprend des idées, pas du code.

## Le principe

Une option du mode Tailscale plutôt qu'un cinquième mode : « Adresses HTTPS sur
mon domaine Cloudflare ». Un téléphone sur lequel Tailscale est actif obtient
`https://sonarr.mondomaine.fr` au lieu de `http://100.101.102.103:8989`, avec un
vrai certificat. Aucun port n'est ouvert sur la box, et le CGNAT ne change rien.

Pourquoi le rattacher à Tailscale : les enregistrements A doivent pointer vers
l'IP Tailscale du serveur, et seul ce mode la connaît
(`remote_access._tailscale_result`). L'activation sait déjà gérer Tailscale
installé sur la machine ou en conteneur. Pour l'utilisateur, c'est Tailscale en
mieux, pas une nouvelle notion à apprendre.

Hors première version (voir « Ensuite ») : la création automatique des
enregistrements DNS, une cible réseau local sans Tailscale, et le wildcard pour
le mode « Mon domaine ».

## Étape 0 : une image Caddy avec le module Cloudflare

L'image officielle `caddy:2.11.4-alpine` (`remote_access.CADDY_IMAGE`) ne
contient pas le module `caddy-dns/cloudflare`. PlugArr construit donc la sienne.

**En place :**

- `packaging/caddy/Dockerfile` : Caddy v2.11.4 (la version déjà épinglée par
  PlugArr) avec `caddy-dns/cloudflare` v0.2.4. Les deux images de base sont
  épinglées par tag et digest. La compilation est croisée sur la machine qui
  construit, sans émulation, puis le binaire remplace celui de l'image officielle
  avec le même `setcap`.
- `.github/workflows/caddy.yml` : construit et essaie l'image quand sa recette
  change. La publication sur ghcr se fait à la demande, depuis `main`
  uniquement, sous le tag `2.11.4-cloudflare-0.2.4`, et refuse d'écraser un tag
  existant. Le résumé du job donne la référence à épingler.
- Essais de la CI, tous passés en local le 15 octobre 2026, en amd64 et en arm64
  (émulé) :
  - les versions de Caddy et du module sont celles annoncées ;
  - le module est enregistré, et le binaire peut écouter 443 sans root ;
  - `packaging/caddy/essai.Caddyfile` (le Caddyfile de l'étape 2) est accepté
    avec un jeton de bonne forme ;
  - il est refusé sans jeton, ce qui prouve que le module est bien chargé.

**Reste à faire :**

1. Pousser, puis lancer le workflow avec `publier` coché.
2. Rendre public le paquet `plugarr-caddy` dans ses réglages GitHub : un nouveau
   paquet ghcr naît privé, et personne ne pourrait le tirer.
3. Épingler la référence donnée par le job dans `remote_access.py` (étape 2).

**Écarté :**

- Compiler à l'activation sur la machine de l'utilisateur : il faut télécharger
  Go, c'est lent sur un NAS ARM, et le résultat n'est pas reproductible.
- Prendre une image communautaire : même épinglée, elle dépend d'une chaîne de
  publication que le projet ne contrôle pas.

Caddy 2.11.7 est sorti le 3 octobre 2026. La 2.11.6 a apporté des changements
incompatibles, et la 2.11.7 corrige des régressions de la 2.11.6. Monter de
version se décidera pour tout PlugArr à la fois, pas seulement pour cette image.

## Étape 1 : le modèle (`remote_models.py`)

- En mode `tailscale`, `domain` devient facultatif. S'il est rempli, il faut
  aussi `services` et un nouveau champ `dns_token`. C'est un jeton d'API
  Cloudflare avec les droits `Zone:Zone:Read` et `Zone:DNS:Edit`, limité à la
  zone.
- `dns_token` est traité exactement comme `tunnel_token` :
  - `repr=False` et forme validée avec les deux formes qu'accepte le module :
    `^[A-Za-z0-9_-]{35,50}$` (jetons classiques) et
    `^cf(ut|at)_[A-Za-z0-9_-]{32,256}$` (jetons d'utilisateur et de compte). Le
    module recopie un jeton mal formé dans son message d'erreur, donc dans le
    journal de Caddy : PlugArr doit le refuser avant ;
  - vidé hors de ce mode, et omis par `_compatible` quand il est vide ;
  - jamais renvoyé au navigateur (un indicateur `dns_token_saved` suffit) ;
  - un champ laissé vide conserve le jeton enregistré.
- Pas besoin de changer la version de `stack.yml`, pour la même raison que
  `names` et `tunnel_token`.
- Nouveau champ `https_port`, à 443 par défaut. DNS-01 n'a besoin ni du port 80
  ni du port 443 pour obtenir le certificat. Si 443 est déjà occupé (c'est
  souvent le cas sur un Synology), on propose 8443. Les fiches téléphone gèrent
  déjà un port HTTPS non standard (`telephone.py`).

## Étape 2 : Caddyfile et compose (`remote_access.py`)

Un nouveau rendu à côté de `caddyfile()`, avec un seul bloc wildcard. Le jeton
est lu dans l'environnement et n'est jamais écrit dans le fichier :

```caddyfile
{
	admin off
	auto_https disable_redirects
	servers {
		protocols h1 h2
	}
}

*.mondomaine.fr {
	tls {
		dns cloudflare {env.CLOUDFLARE_API_TOKEN}
		resolvers 1.1.1.1 1.0.0.1
		propagation_delay 2m
		propagation_timeout 10m
	}
	@hors_reseau not remote_ip private_ranges 100.64.0.0/10
	handle @hors_reseau {
		abort
	}
	@sonarr host sonarr.mondomaine.fr
	handle @sonarr {
		reverse_proxy http://sonarr:8989
	}
	@qbittorrent host qb.mondomaine.fr
	handle @qbittorrent {
		reverse_proxy http://gluetun:8080
	}
	handle {
		abort
	}
}
```

Ce Caddyfile est validé par l'image de l'étape 0 : c'est
`packaging/caddy/essai.Caddyfile`, essayé par la CI. Ce que fait chaque partie :

- **Wildcard.** Un seul certificat `*.mondomaine.fr` : aucun nom d'application
  n'apparaît dans les journaux Certificate Transparency.
- **`protocols h1 h2`** : seul le TCP est publié. Sans cette ligne, Caddy
  annoncerait HTTP/3 sur un port UDP fermé. HTTP/3 à travers Tailscale ne
  fonctionne d'ailleurs qu'à partir de Caddy 2.11.6.
- **`resolvers`** évite qu'un DNS local (la box, un Pi-hole) fausse la recherche
  de la zone.
- **`propagation_*`** reprend les valeurs qui ont marché pour Caretakarr (son
  commit 3bc96b9). Ça ne repose que sur un essai, à confirmer.
- **Le filtre `remote_ip`** n'accepte que les réseaux privés et la plage CGNAT
  de Tailscale (`private_ranges` n'inclut pas 100.64/10). C'est une protection
  de plus si la box redirige encore le port 443 depuis un ancien mode « Mon
  domaine ».
  - Il doit être le premier `handle`. Un `abort` posé à côté passerait après les
    `handle`, à cause de l'ordre des directives de Caddy : vérifié avec
    `caddy adapt`, où le filtre arrive alors en dernier et ne protège plus rien.
  - Sous Docker Desktop, l'IP source n'est probablement pas conservée. Le filtre
    ne bloquerait alors rien, sans rien casser.
- **Le `handle { abort }` final** fait qu'un sous-domaine inconnu ne mène nulle
  part.

Côté compose :

- Image épinglée, `env_file: ./caddy.env` en 0600 comme `tunnel.env`, réseau
  `applications`, et un seul port publié : `<https_port>:443`. Pas de port 80.
- Quand Tailscale tourne en conteneur, les deux services sont dans le même
  compose. Or `_check_owned` ne regarde que `services.gateway`. Il faut lui
  faire vérifier l'étiquette `plugarr.remote` sur chaque service.
- `caddy.env` est supprimé dès qu'on quitte ce mode, comme `tunnel.env`
  aujourd'hui.

## Étape 3 : activation et diagnostic

Dans `activate()` :

1. Connecter Tailscale et relever l'IP 100.x, avec le code existant.
   Aujourd'hui, la branche « Tailscale déjà installé » s'arrête là
   (`return _tailscale_result`). Elle doit continuer quand un domaine est
   choisi.
2. Vérifier le jeton : la zone doit se trouver. On remonte les étiquettes du
   domaine, comme Caretakarr.
3. Appeler `_protect_applications()`. qBittorrent doit accepter le nouveau nom
   d'hôte, et Sonarr/Radarr doivent toujours exiger une authentification, parce
   que les requêtes arrivent de Caddy, donc d'une adresse que ces applications
   considèrent comme locale.
4. Écrire le Caddyfile et `caddy.env`, puis démarrer.
5. Afficher les enregistrements à créer, comme les routes du tunnel
   aujourd'hui : `sonarr`, type `A`, valeur `100.x.y.z`, **DNS only (nuage
   gris)**.

Dans `inspect()`, on garde `_check_public` (l'accès anonyme doit être refusé et
la clé API acceptée) et on ajoute trois causes d'échec, chacune avec son
explication dans `_explain` :

- **`wrong_address`** : le nom résout vers autre chose que l'IP Tailscale. Le
  nuage orange est activé, ou un ancien enregistrement traîne.
- **`certificate`** : le certificat n'est pas encore valide. On lit le journal de
  Caddy comme `_tunnel_state` lit celui de cloudflared, en ne cherchant que
  quelques lignes connues.
- **`rebind`** : le résolveur du système ne répond pas, alors qu'une requête DoH
  à Cloudflare (via `httpx`, donc sans nouvelle dépendance) renvoie la bonne IP.
  C'est le piège principal de ce mode : beaucoup de box et de résolveurs
  suppriment les réponses publiques qui pointent vers une IP privée. Le serveur
  n'utilise pas forcément le même résolveur que le téléphone : ce test donne un
  indice, pas une preuve.

## Étape 4 : interfaces web et TUI

- Dans l'assistant web (`web/wizard.html`, `web/remote.js`) et la TUI
  (`tui/screens.py`, écran d'accès distant) : une case sous la carte Tailscale.
  Cochée, elle affiche le domaine, les sous-domaines (blocs existants), le jeton
  et le port.
- Une aide pour créer le jeton : où aller dans Cloudflare, quels droits, limité
  à la zone. Préciser que ce n'est pas le jeton du tunnel.
- Récapitulatif « Tailscale · HTTPS · mondomaine.fr » (`web/wizard.js` et
  `tui/screens.py`).
- Le jeton est ajouté à la liste des valeurs masquées par `redact`
  (`webwizard.py`).
- Toutes les nouvelles phrases vont dans le catalogue anglais (sinon
  `scripts/audit_traductions.py` échoue) et dans le dictionnaire `english` de
  `remote.js`.

## Étape 5 : l'image d'administration

Sur un serveur SSH, c'est l'image admin épinglée qui lit `stack.yml`. La 0.12.2
refuserait le champ `dns_token`, puisque le modèle interdit les champs inconnus
(`extra="forbid"`).

On reprend la méthode du tunnel : un indicateur `CONSOLE_IMAGE_DNS01 = False`
dans `catalog.py`, lu par `admin_image_ready()`. Ce choix reste refusé tant que
l'image admin n'a pas été republiée et réépinglée.

## Tests

Dans le style de `tests/test_remote_cloudflare.py` :

- Le jeton n'apparaît ni dans `repr`, ni dans la page, ni dans le récapitulatif,
  ni dans les erreurs, ni dans le Caddyfile, ni dans le compose. Il n'existe que
  dans `caddy.env`, en 0600.
- Une pile sans cette option reste lisible par l'image admin actuelle.
- Le Caddyfile contient un seul bloc wildcard, respecte les noms personnalisés,
  passe par `gluetun` derrière le VPN et se termine par `abort`.
- Le compose utilise l'image épinglée par digest, ne publie pas le port 80, et
  `caddy.env` disparaît quand on quitte le mode.
- Chaque nouvelle cause d'échec a son explication.
- La parité web/TUI est vérifiée par `tests/test_parite_assistant.py`.
- **Faire valider les Caddyfile générés par la vraie image dans la CI**
  (`caddy adapt --validate`). Un test qui ne fait que comparer du texte ne
  verrait pas une erreur d'ordre comme celle du filtre.

## Essais réels avant de l'annoncer

D'abord avec l'environnement de staging de Let's Encrypt, via une option
réservée aux essais, pour ne pas épuiser les quotas.

1. Linux avec Tailscale installé et une vraie zone Cloudflare : le certificat
   est obtenu, puis conservé après un redémarrage sans être redemandé.
2. NAS avec Tailscale en conteneur : les deux services tournent dans le même
   compose.
3. Windows avec Docker Desktop et Tailscale : le port 443 répond sur l'IP
   Tailscale.
4. Téléphone en 4G avec Tailscale : nzb360 et qbRemote fonctionnent en HTTPS.
5. Téléphone en Wi-Fi à la maison : on vérifie si la box bloque les réponses DNS
   vers des IP privées.
6. Port 443 occupé : le passage à 8443 se répercute jusqu'aux fiches du
   téléphone.

## Ensuite

- **Phase 2 : PlugArr crée lui-même les enregistrements A.** Le jeton a déjà le
  droit `DNS:Edit`, et PlugArr connaît l'IP Tailscale. On reprend les règles de
  Caretakarr :
  - marquer ses propres enregistrements dans le champ commentaire ;
  - adopter un enregistrement identique déjà présent ;
  - signaler un conflit sans rien écraser ;
  - ne supprimer que ses propres enregistrements à la désactivation.
- **Phase 3 :**
  - proposer le même wildcard au mode « Mon domaine » : plus besoin du port 80,
    et les noms disparaissent des journaux de certificats ;
  - ajouter une cible réseau local sans Tailscale.

## Décisions ouvertes

1. Une option du mode Tailscale (recommandé), ou une cinquième carte séparée ?
2. Des enregistrements DNS créés à la main en première version, comme les
   routes du tunnel (recommandé), ou automatiques tout de suite ?
3. Publier une deuxième image sur ghcr, `plugarr-caddy` ?
