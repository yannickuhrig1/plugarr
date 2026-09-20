# Administrer une machine distante

La console d'administration de PlugArr écoute sur `127.0.0.1` par défaut. Pour
la joindre depuis un autre poste, il faut deux choses : qu'elle écoute sur le
réseau, et que **quelque chose la lance**. La seconde est le vrai sujet.

Trois routes, de la plus sûre à la plus permissive.

## 1. Service système (recommandé, Linux avec systemd)

```bash
plugarr admin-password              # obligatoire hors de 127.0.0.1
sudo plugarr autostart --systeme --host 0.0.0.0
```

La console démarre **avec la machine**, sans qu'une session s'ouvre. L'unité
est écrite dans `/etc/systemd/system/plugarr-console.service` et tourne sous le
compte qui possède `stack.yml`, pas sous root par commodité. Sans mot de passe
posé, la commande refuse d'écouter hors de `127.0.0.1` : le jeton tiré à chaque
démarrage ne serait lu par personne.

`sudo plugarr autostart --systeme --disable` retire tout.

**Vérifié** le 2026-09-20 sur le banc (LXC Debian, systemd) : unité installée,
console jointe depuis une autre machine avec son formulaire de connexion, puis
la machine redémarrée pour de vrai — sans aucune session, la console est
revenue et les neuf conteneurs avec elle.

## 2. Console dans un conteneur (machines sans systemd)

À l'installation, dans l'assistant, ou :

```bash
plugarr install --console-conteneur --console-port 7373 ...
```

Ce conteneur reçoit le **socket Docker**. Il faut le dire franchement : avec le
socket, on crée un conteneur privilégié qui monte la racine de l'hôte. Ce
conteneur a donc, en pratique, tous les droits sur la machine, et il tourne en
root — lui donner un compte sans privilège pendant qu'il tient le socket
n'aurait rien protégé, cela aurait seulement donné le change.

Il utilise une image distincte, `...-admin`, la seule à contenir un client
Docker. Celle de la veille n'en a aucun : même en lui tendant le socket, elle
ne saurait pas s'en servir.

**Vérifié** le 2026-09-20 sur le banc, contre une vraie installation : console
jointe, connexion, état réel des neuf services lu depuis l'intérieur du
conteneur, puis un service redémarré à travers le socket.

À n'activer que là où la route 1 est impossible.

## 3. Mécanismes propres aux NAS

Unraid et Synology n'ont pas systemd, mais ont chacun leur façon de lancer une
commande au démarrage. **Ces deux chemins ne sont pas vérifiés par PlugArr** :
nous n'avons ni l'un ni l'autre sur le banc, et une marche à suivre écrite de
mémoire vaudrait moins que rien. Ce qui suit dit seulement où chercher.

- **Unraid** : le greffon *User Scripts* garde ses scripts dans
  `/boot/config/plugins/user.scripts/scripts/` et sait les lancer selon une
  planification. La commande à y coller est celle que PlugArr affiche quand il
  ne connaît pas de mécanisme :
  `plugarr autostart` la rend sur la sortie standard.
- **Synology** : le *Planificateur de tâches* de DSM lance des tâches
  déclenchées par un événement, avec un script défini par l'utilisateur.

Dans les deux cas, la route 2 reste disponible et, elle, essayée.

## Ce que la console expose

Quelle que soit la route, une console jointe depuis le réseau montre les
identifiants des services et peut les arrêter. Elle exige donc un mot de passe
(`plugarr admin-password`, PBKDF2 à 600 000 itérations, empreinte seule dans
`stack.yml`), limite les tentatives, et expire ses sessions au bout de douze
heures. Pour la sortir de votre réseau local, voir `docs/ACCES_DISTANT.md`.

## Sources

- Unraid, greffon User Scripts, emplacement des scripts :
  <https://plugin-docs.mstrhakr.com/docs/advanced/user-scripts-integration.html>
- Synology, Planificateur de tâches et tâches déclenchées :
  <https://kb.synology.com/en-global/DSM/help/DSM/AdminCenter/system_taskscheduler>
