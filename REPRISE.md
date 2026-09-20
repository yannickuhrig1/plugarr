# Reprise de session - 20 septembre 2026, fin d'apres-midi

Document de passation. A supprimer une fois le travail repris.

## Ou en est le depot

- Branche de travail : `roadmap-0.10.0`, commit `4d3985f`.
- `main` est a `1983129` et porte la **0.10.0**. C'est la branche que la
  commande d'installation du README utilise, donc ce qui est sur `main` est ce
  que les utilisateurs recoivent.
- **`main` n'a pas encore le profil UGREEN** (`4d3985f`), ni les deux derniers
  correctifs de tests. Fusionner en avance rapide quand la CI de la branche est
  verte : `git checkout main && git merge --ff-only roadmap-0.10.0 && git push`.
- Tags d'avant-premiere poses : jusqu'a `v0.10.0-veille-preview.4`. Pas de tag
  `v0.10.0` : la 0.10.0 n'est pas declaree publiee.

## Ce qui a ete fait aujourd'hui

1. **Veille en conteneur, vue Docker en lecture seule** derriere
   `tecnativa/docker-socket-proxy` sur un reseau interne. Le proxy n'empeche PAS
   `GET /containers/{id}/json`, qui rend les secrets : la retenue est dans
   `veille.py`, prouvee par le journal du proxy (12 appels statistiques, 1
   liste, zero inspection).
2. **Un defaut de lenteur** : les releves partaient en file, 21,2 s pour onze
   conteneurs, page vide pendant ce temps. Passes en parallele : 2,1 s.
3. **Quatre defauts remontes par un membre (ticket Discord 0002, Cousto)**, tous
   lies a une installation en `sudo` sur NAS UGREEN. Voir les commits
   `ee0f98c`, `8f9e509`, `1983129`.
4. **Profil UGREEN**, marque experimental (`4d3985f`). A decouvert au passage
   que macOS manquait dans le `<select>` de l'assistant web.

## Ce qui reste a faire

- [ ] **Fusionner `4d3985f` vers `main`** (voir ci-dessus).
- [ ] **Canal Discord pour les retours** sur les profils NAS. Demande par
      l'utilisateur, PAS commence. Le serveur se gere par le kit
      `C:\tmp\plugarr-discord` : ajouter le salon dans `discord_setup.py` et
      `content.py`, puis l'utilisateur lance `LANCER.cmd` et colle le jeton
      lui-meme. **Ne jamais creer le salon par l'interface Discord.**
- [ ] **Essayer le profil UGREEN** sur un vrai NAS : il vient d'une seule
      installation, celle de Cousto.
- [ ] Roadmap 0.10.0, points ouverts : choix des racines a surveiller, journaux
      des conteneurs dans la veille (a peser, un journal peut porter des
      identifiants), tout remesurer sur Linux natif, essayer la route Unraid.

## Un test encore instable

`tests/test_adminauth.py` fait tomber un test de loin en loin en passe
COMPLETE, sur une `ConnectionAbortedError`, et repasse isolement. Une fuite
reelle a ete trouvee et corrigee aujourd'hui (`shutdown()` sans
`server_close()`, prouve : le port refuse un nouveau `bind` sans lui). Cela n'a
pas suffi. **Ne pas le declarer regle.**

## Regles du projet a respecter

- Verifier avant d'affirmer. Trois fois aujourd'hui une explication plausible
  s'est revelee fausse a la mesure.
- Le JavaScript se teste dans un VRAI navigateur, les artefacts publies contre
  une VRAIE installation.
- Banc d'essai : LXC 199 (192.168.1.186) via
  `ssh -i ~/.ssh/proxmox_mcp root@192.168.1.134 'pct exec 199 -- ...'`.
  **Le LXC 103 est la production, ne pas y toucher.**
- Avant un push : `ruff`, `pytest`, `scripts/audit_traductions.py`,
  `scripts/screenshots.py` puis `git diff --exit-code docs/screenshots`.
- Toute option d'installation doit exister dans l'assistant web ET le TUI
  (`tests/test_parite_assistant.py` le verifie).
- Commit et push seulement sur demande. Pas d'emoji, pas de tiret cadratin.
