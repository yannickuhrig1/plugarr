# Tester le parcours d'accès distant et mobile

> Document de l'ancienne maquette autonome. Pour la version désormais intégrée à
> l'assistant web, consulter [ACCES_DISTANT.md](ACCES_DISTANT.md).

Cette livraison est un prototype interactif autonome, pas une version capable de
déployer Tailscale ou Caddy. Aucun compte, DNS, serveur ou port n'est modifié.
Le programme d'installation actuel n'est pas modifié.

## Ouvrir

Double-cliquer sur `TESTER-ACCES-DISTANT.cmd`, à la racine du projet, ou ouvrir
`previews/acces-distant.html` dans un navigateur. Aucun serveur ni dépendance à installer.

## Scénarios

1. **Tailscale** : Continuer, Simuler la connexion du compte, Continuer, confirmer
   la génération. Ouvrir une fiche mobile. Vérifier les champs et la mention Tailscale.
2. **Domaine** : choisir HTTPS et conserver `maison.example`. Sélectionner les
   applications, simuler la vérification, générer les accès. Les fiches distantes
   utilisent HTTPS et le port 443 ; les fiches locales utilisent les ports locaux.
3. **Blocages** : dans « Scénarios à essayer », choisir DNS, box, CGNAT ou proxy
   existant. Vérifier les explications et les replis Tailscale / local.
4. **Local** : aucune association ni domaine demandé ; aucun accès distant proposé.
5. **Mobile** : nzb360 permet les trois services, qbRemote uniquement qBittorrent.
   Changer la connexion locale/distante et contrôler les champs. Afficher/copier
   les secrets fictifs. Les résultats de connexion sont des simulations explicites.
6. **Export** : télécharger la page puis ouvrir le fichier téléchargé. Les choix,
   les cartes et les fiches mobiles sont conservés, sans fichier annexe requis.
7. **Retour** : modifier la méthode ou le domaine. Une nouvelle validation est
   nécessaire avant de générer les accès correspondants.

Les adresses et secrets sont fictifs. Les boutons de copie et de téléchargement
fonctionnent, mais aucune connexion à un service n'est tentée. Ne pas saisir de
vrais identifiants. Les intitulés des champs mobiles restent à vérifier sur les
versions réelles des clients avant intégration en production.

## Vérifications réalisées

Test navigateur Chromium automatisé : les trois parcours, les quatre cas de
blocage HTTPS, le rejet d'un domaine mal formé, l'invalidation après modification,
la sélection des champs mobiles, le masquage des secrets, l'export puis la
réouverture autonome et les largeurs mobiles 390/320 pixels passent. Aucun appel
HTTP externe ni erreur JavaScript observé. Le rendu mobile a également été relu
sur capture. Script : `tests/js/remote_access_preview.cjs` (Playwright requis).

Cela valide la démonstration, pas la connexion des applications réelles.

## À réaliser pour une version fonctionnelle

- Intégrer les écrans aux assistants et persister la configuration.
- Associer réellement Tailscale et vérifier son réseau sur le serveur cible.
- Générer Caddy, vérifier DNS/ports/certificats et renouvellement.
- Corriger et tester les protections des applications avant exposition publique.
- Générer les fiches depuis les identifiants réels et récupérer le HTML par SSH.
- Tester nzb360 et qbRemote sur téléphone en réseau mobile.
