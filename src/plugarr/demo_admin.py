"""Console de demonstration : etat en memoire, aucune commande ni installation."""
from __future__ import annotations

import hmac
import json
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import catalog, connections, dashboard, orchestrator, wizard_graph
from .maintenance import Maintenance, stamp
from .models import VpnConfig

COOKIE = 'plugarr_demo_session'


class DemoServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, cfg, token):
        self.cfg = cfg.model_copy(deep=True)
        self.cfg.host = '192.0.2.10'
        self.cfg.username = 'demo'
        self.cfg.admin_password_hash = ''
        self.cfg.project_dir = None
        self.cfg.vpn = VpnConfig(enabled=cfg.vpn.enabled)
        self.cfg.config_root = '/demo/config'
        self.cfg.data_root = '/demo/media'
        for inst in self.cfg.services.values():
            inst.username = 'demo'
            inst.password = 'DEMO-password'
            inst.api_key = 'DEMO-api-key'
        self.token = token
        self.maintenance = Maintenance(self.cfg, Path('/demo'), persistent=False)
        self.maintenance.state['connections'] = {
            edge['id']: {'state': 'verifiee', 'checked_at': stamp(),
                         'detail': 'Test simulé après la configuration de démonstration.'}
            for edge in connections.entries(self.cfg)
        }
        self.states = {sid: True for sid in self.cfg.services if self.cfg.enabled(sid)}
        if self.cfg.vpn_enabled:
            self.states['gluetun'] = True
        self.updated = set()
        self.self_updated = False
        super().__init__(('127.0.0.1', 0), DemoHandler)
        self.origin = f'http://127.0.0.1:{self.server_port}'


class DemoHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, data, code=200, *, page=False, cookie=False):
        body = data.encode('utf-8') if page else json.dumps(data).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8' if page else 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        if cookie:
            self.send_header('Set-Cookie', f'{COOKIE}={self.server.token}; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        srv = self.server
        if (self.headers.get('Host') != urlsplit(srv.origin).netloc or
                self.headers.get('Origin', srv.origin) != srv.origin or
                self.headers.get('Sec-Fetch-Site') == 'cross-site'):
            self.send({'error': 'Origine refusee'}, 403)
            return False
        cookies = SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie', ''))
            token = cookies[COOKIE].value if COOKIE in cookies else ''
        except Exception:  # noqa: BLE001 - malformed cookies never authorise a request
            token = ''
        if self.command == 'GET' and urlsplit(self.path).path == '/':
            token = parse_qs(urlsplit(self.path).query).get('t', [token])[0]
        if not hmac.compare_digest(token.encode(), srv.token.encode()):
            self.send({'error': 'Session absente ou expiree'}, 401)
            return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
        srv, route = self.server, urlsplit(self.path).path
        with srv.maintenance.lock:
            if route == '/':
                page = dashboard.render(srv.cfg, live=True)
                page = page.replace('<title>', '<title>DEMO — ', 1)
                page = page.replace('<body>', '<body><div role="status" style="padding:18px;background:#ff9e45;color:#111;text-align:center;font-weight:bold">DÉMO — Installation simulée. Adresses, identifiants et versions fictifs. Les commandes sont simulées, sans Docker. Réglages effacés à la fermeture.</div>', 1)
                page = page.replace('</head>', '''<script>
                history.replaceState(null,'',location.pathname+location.hash);
                document.addEventListener('click',function(e){const a=e.target.closest('a');if(a&&/^(https?:|file:)/.test(a.getAttribute('href')||'')){e.preventDefault();alert('Démonstration : cette adresse est fictive.');}},true);
                </script></head>''', 1)
                self.send(page, page=True, cookie=True)
                return
            if route == '/api/status':
                data = {'engine_available': True, 'services': [
                    {'id': sid, 'name': ('Gluetun' if sid == 'gluetun' else catalog.get(sid).display_name),
                     'state': 'running' if up else 'exited', 'status': 'Simulation',
                     'health': '', 'up': up} for sid, up in srv.states.items()]}
            elif route == '/api/maintenance':
                data = srv.maintenance.snapshot()
            elif route == '/api/connections':
                data = wizard_graph.administration(srv.cfg, srv.maintenance.state['connections'])
            elif route == '/api/updates':
                data = {'services': [
                    {'id': sid, 'name': ('Gluetun' if sid == 'gluetun' else catalog.get(sid).display_name),
                     'current': '1.0.1-demo' if sid in srv.updated else '1.0.0-demo',
                     'latest': '1.0.1-demo', 'available': sid not in srv.updated,
                     'rebuilt': False, 'problems': []} for sid in srv.states]}
            elif route == '/api/self-update':
                data = {'current': '0.8.0-demo' if srv.self_updated else '0.7.0-demo',
                        'latest': '0.8.0-demo', 'available': not srv.self_updated,
                        'verified_asset': True, 'notes': 'Version fictive, aucun téléchargement.'}
            elif route == '/api/doctor':
                data = {'failed': 0, 'checks': [{'name': 'Diagnostic fictif', 'ok': True,
                        'detail': 'Aucun contrôle réel effectué.', 'blocking': False,
                        'next_step': 'Essayez les commandes simulées.'}]}
            else:
                self.send({'error': 'Route inconnue'}, 404)
                return
            self.send(data)

    def do_POST(self):
        if not self.allowed():
            return
        srv, route = self.server, urlsplit(self.path).path
        try:
            size = int(self.headers.get('Content-Length', 0))
            if not 0 <= size <= 16384 or self.headers.get('Transfer-Encoding'):
                raise ValueError('Taille invalide')
            # The existing backup button sends no body or Content-Type.
            if size and self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('Corps JSON requis')
            payload = json.loads(self.rfile.read(size) or b'{}')
            if not isinstance(payload, dict):
                raise TypeError('Objet JSON requis')
            result = {'ok': True, 'message': 'Simulation réussie. Aucune modification réelle.'}
            with srv.maintenance.lock:
                sid = payload.get('service')
                if route in ('/api/action', '/api/update', '/api/rotate') and sid not in srv.states:
                    raise ValueError('Service inconnu')
                if route == '/api/action':
                    if payload.get('action') not in ('start', 'stop', 'restart'):
                        raise ValueError('Action inconnue')
                    srv.states[sid] = payload['action'] != 'stop'
                elif route == '/api/update':
                    srv.updated.add(sid)
                elif route == '/api/rotate':
                    if sid not in srv.cfg.services:
                        raise ValueError('Service sans secret')
                    what = payload.get('what')
                    if what not in ('password', 'api_key'):
                        raise ValueError('Secret inconnu')
                    result['secret'] = 'DEMO-' + what + '-' + str(len(srv.maintenance.state['events']) + 1)
                    setattr(srv.cfg.services[sid], what, result['secret'])
                elif route == '/api/add':
                    if not isinstance(sid, str) or sid not in catalog.CATALOG:
                        raise ValueError('Service inconnu')
                    added = orchestrator.build_config(
                        services=[*srv.cfg.services, sid], config_root='/demo/config',
                        data_root='/demo/media', username='demo')
                    for name, inst in added.services.items():
                        if name not in srv.states:
                            inst.password, inst.api_key = 'DEMO-password', 'DEMO-api-key'
                            srv.cfg.services[name] = inst
                            srv.states[name] = True
                elif route == '/api/maintenance':
                    srv.maintenance.configure(payload)
                elif route in ('/api/connections/test', '/api/connections/repair'):
                    edge = next(e for e in connections.entries(srv.cfg) if e['id'] == payload.get('id'))
                    srv.maintenance.state['connections'][edge['id']] = {
                        'state': 'verifiee', 'checked_at': stamp(), 'detail': 'Test simulé réussi.'}
                elif route == '/api/backup':
                    srv.maintenance.state['last_backup'] = stamp()
                    result.update(archive='DEMO-archive.zip', mega=0, fichiers=0, volumes=[])
                elif route == '/api/self-update':
                    srv.self_updated = True
                else:
                    self.send({'error': 'Route inconnue'}, 404)
                    return
                srv.maintenance.event('Simulation ' + route.rsplit('/', 1)[-1], True, sid or '')
                self.send(result)
        except (ValueError, TypeError, KeyError, StopIteration):
            self.send({'error': 'Requête invalide'}, 400)
