"""Persistent local maintenance. Events never contain credentials or raw API errors."""
import json
import logging
import re
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from . import sauvegarde


def stamp():
    return datetime.now(UTC).isoformat()


class Maintenance:
    def __init__(self, cfg, project_dir: Path, *, persistent=True):
        self.persistent = persistent
        self.cfg, self.project_dir = cfg, project_dir
        #: Prises COURTES, autour des seules mutations de `state`. Rien de long
        #: ne doit s'executer dessous : la console lit `state` a chaque
        #: rafraichissement.
        self.lock = threading.RLock()
        #: Une seule operation longue a la fois (sauvegarde manuelle,
        #: sauvegarde planifiee). Ce verrou-la peut etre tenu des minutes, mais
        #: il n'empeche aucune lecture d'etat.
        self.operation = threading.RLock()
        #: Leve pendant qu'une sauvegarde a froid arrete volontairement la pile.
        #: Sans lui, la console sonnait l'alarme sur SA PROPRE sauvegarde.
        self.arret_pour_sauvegarde = threading.Event()
        self.stop = threading.Event()
        self.path = project_dir / '.plugarr-maintenance.json'
        self.state = {'events': [], 'connections': {}, 'alerts': {}, 'last_backup': None,
                      'schedule': {'enabled': False, 'days': 1, 'hour': 3, 'keep': 7},
                      'notifications': {'services': True, 'backup': True, 'vpn': True},
                      'last_attempt': None, 'last_backup_error': None,
                      'intentional_stops': [], 'archives': []}
        if persistent and self.path.exists():
            loaded = json.loads(self.path.read_text(encoding='utf-8'))
            self.state.update({k: loaded[k] for k in self.state if k in loaded})

    def save(self):
        if not self.persistent:
            return
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.state, ensure_ascii=False), encoding='utf-8')
        tmp.chmod(0o600)
        tmp.replace(self.path)

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.state))

    def event(self, action, ok, service=''):
        with self.lock:
            self.state['events'].append({'at': stamp(), 'action': action, 'ok': bool(ok),
                                         'service': service})
            self.state['events'] = self.state['events'][-300:]
            self.save()

    def record_connection(self, edge_id, result):
        """Resultat d'un test de liaison, sous le verrou d'etat.

        L'ecriture se faisait directement dans `state['connections']` depuis le
        gestionnaire HTTP. Tant que chaque requete tenait le verrou d'etat, elle
        etait couverte par accident ; elle ne l'est plus depuis que les lectures
        passent en parallele, et `snapshot()` serialise ce meme dictionnaire.
        """
        with self.lock:
            self.state['connections'][edge_id] = result
            self.save()

    def alert(self, key, active, title):
        with self.lock:
            previous = self.state['alerts'].get(key)
            if previous and previous['active'] == active:
                return
            if not previous and not active:
                return
            self.state['alerts'][key] = {'active': active, 'title': title, 'at': stamp()}
            self.event('alerte' if active else 'retour a la normale', not active, key)

    def configure(self, payload):
        schedule, notifications = payload.get('schedule', {}), payload.get('notifications', {})
        if not isinstance(schedule, dict) or not isinstance(notifications, dict):
            raise TypeError('Parametres invalides')
        if set(schedule) - {'enabled', 'days', 'hour', 'keep'}:
            raise ValueError('Parametre de planification inconnu')
        for key, low, high in [('days', 1, 30), ('hour', 0, 23), ('keep', 1, 90)]:
            if key in schedule and (type(schedule[key]) is not int or not low <= schedule[key] <= high):
                raise ValueError(f'{key}: valeur hors limites')
        if 'enabled' in schedule and type(schedule['enabled']) is not bool:
            raise ValueError('enabled doit etre un booleen')
        if set(notifications) - {'services', 'backup', 'vpn'} or any(type(v) is not bool for v in notifications.values()):
            raise ValueError('Preferences de notification invalides')
        with self.lock:
            self.state['schedule'].update(schedule)
            self.state['notifications'].update(notifications)
            self.save()

    def safe_error(self, exc: Exception) -> str:
        """Detail local et actionnable, sans laisser passer un identifiant."""
        detail = next(iter(str(exc).splitlines()), "cause inconnue").strip()
        secrets = []
        for inst in self.cfg.services.values():
            secrets.extend(
                getattr(inst, key, "") for key in ("password", "api_key", "secret_key")
            )
        secrets.extend(
            getattr(self.cfg.vpn, key, "")
            for key in ("wireguard_private_key", "openvpn_password", "openvpn_user")
        )
        for secret in sorted(filter(None, secrets), key=len, reverse=True):
            detail = detail.replace(secret, "<masque>")
        detail = re.sub(
            r"(?i)((?:api_?key|token|password|passkey)=)[^&\s]+",
            r"\1<masque>",
            detail,
        )
        return f"{type(exc).__name__} : {detail}"[:300]

    def backup(self):
        """Archive la pile. L'ecriture se fait HORS du verrou d'etat.

        Panne mesuree : `do_GET` et `do_POST` s'executaient tous les deux sous
        `self.lock`, et `backup()` le gardait pendant toute la duree de
        l'archivage. Un `/api/status` demande pendant une sauvegarde attendait
        donc la fin de celle-ci — huit secondes sur une pile de test, des
        minutes sur un CONFIG_ROOT reel. La console entiere paraissait figee :
        ni etat des services, ni graphe, ni historique, ni bouton utilisable.
        """
        with self.operation:
            directory = self.project_dir / 'backups'
            directory.mkdir(exist_ok=True)
            destination = directory / ('plugarr-' + datetime.now(UTC).strftime('%Y%m%d-%H%M%S-%f') + '.zip')
            with self.lock:
                self.state['last_attempt'] = time.time()
                self.save()
            self.arret_pour_sauvegarde.set()
            try:
                report = sauvegarde.sauvegarder(self.cfg, self.project_dir, destination)
            except Exception as exc:
                with self.lock:
                    self.state['last_backup_error'] = self.safe_error(exc)
                    self.save()
                self.event('sauvegarde', False)
                self.alert('backup', True, 'Sauvegarde echouee')
                raise
            finally:
                self.arret_pour_sauvegarde.clear()
            with self.lock:
                self.state['last_backup'] = stamp()
                self.state['last_backup_error'] = None
                self.state['archives'].append(destination.name)
                expired = self.state['archives'][:-self.state['schedule']['keep']]
                for name in expired:
                    old = directory / name
                    if old.parent.resolve() == directory.resolve() and old.name.startswith('plugarr-'):
                        try:
                            old.unlink(missing_ok=True)
                        except OSError:
                            self.event('suppression ancienne archive', False, name)
                            continue
                        self.state['archives'].remove(name)
                self.save()
            self.event('sauvegarde', True)
            self.alert('backup', False, 'Sauvegarde echouee')
            return report

    def tick(self, now=None):
        now = now or datetime.now().astimezone()
        with self.lock:
            schedule, last = dict(self.state['schedule']), self.state['last_attempt']
            due = (schedule['enabled'] and now.hour == schedule['hour'] and
                   (last is None or (now.date() - datetime.fromtimestamp(last, now.tzinfo).date()).days >= schedule['days']))
        # Hors du verrou d'etat : une sauvegarde planifiee ne doit pas plus
        # figer la console qu'une sauvegarde demandee a la main.
        if due:
            self.backup()

    def run(self):
        while not self.stop.wait(30):
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - keep API/worker failures contained and secrets out of responses
                logging.getLogger(__name__).warning('Scheduled maintenance failed; see console history')
