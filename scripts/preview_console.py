"""Preview the actual console UI with fictional data. Never invokes Docker."""
from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

# A copied virtualenv can retain an editable install pointing at an older folder.
# This preview always imports the sources beside this script, even when started
# from another working directory or with a stale PYTHONPATH.
SOURCE_ROOT = Path(__file__).resolve().parents[1] / 'src'
if not (SOURCE_ROOT / 'plugarr' / 'connection_map.py').is_file():
    raise RuntimeError('Archive incomplete : extrayez tout le dossier plugarr avant de lancer la demo.')
sys.path.insert(0, str(SOURCE_ROOT))

from plugarr import catalog, connections, dashboard, orchestrator, wizard_graph
from plugarr.maintenance import Maintenance, stamp


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--open', action='store_true', help='Ouvrir le navigateur')
    options = parser.parse_args()
    cfg = orchestrator.build_config(services=['prowlarr', 'sonarr', 'radarr', 'qbittorrent', 'jellyfin', 'seerr', 'flood'],
                                   data_root='/demo/media', config_root='/demo/config')
    for inst in cfg.services.values():
        inst.password = 'DEMO-password'
        inst.api_key = 'DEMO-api-key'
    states = {sid: True for sid in cfg.services if cfg.enabled(sid)}
    with TemporaryDirectory(prefix='plugarr-demo-') as directory:
        maintenance = Maintenance(cfg, Path(directory))

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def end_headers(self):
                self.send_header('Cache-Control', 'no-store')
                super().end_headers()

            def send(self, data, code=200):
                body = json.dumps(data).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                route = urlparse(self.path).path
                if route == '/':
                    page = dashboard.render(cfg, live=True)
                    page = page.replace('<title>', '<title>Démo carte V2 — ', 1)
                    page = page.replace('<h2>Carte des connexions</h2>', '<h2>Carte des connexions · V2 (démo)</h2>', 1)
                    page = page.replace('<body>', '<body><p style="padding:20px;background:#ff9e45;color:#111;text-align:center;font-weight:bold">DÉMO LOCALE — CARTE V2 — toutes les données et opérations sont fictives. Aucun accès à Docker. Réglages effacés à la fermeture.</p>')
                    page = page.replace('target="_blank" rel="noopener"', 'target="_blank" rel="noopener" onclick="return false"')
                    body = page.encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif route == '/api/status':
                    self.send({'engine_available': True, 'services': [
                        {'id': sid, 'name': catalog.get(sid).display_name, 'state': 'running' if up else 'exited',
                         'status': 'Simulation', 'health': '', 'up': up} for sid, up in states.items()]})
                elif route == '/api/maintenance':
                    self.send(maintenance.snapshot())
                elif route == '/api/connections':
                    saved = maintenance.snapshot()['connections']
                    self.send(wizard_graph.administration(cfg, saved))
                elif route == '/api/doctor':
                    self.send({'failed': 0, 'checks': [{'name': 'Diagnostic fictif', 'ok': True, 'detail': 'Aucun contrôle réel effectué.', 'blocking': False, 'next_step': 'Testez les autres commandes de la démonstration.'}]})
                elif route == '/api/updates':
                    self.send({'services': [{'id': sid, 'name': catalog.get(sid).display_name, 'current': '1.0.0-demo', 'latest': '1.0.1', 'available': True, 'rebuilt': False, 'problems': []} for sid in states]})
                elif route == '/api/self-update':
                    self.send({'current': '0.7.0-demo', 'latest': '0.8.0-demo', 'available': True, 'verified_asset': True, 'notes': 'Release fictive : aucun fichier ne sera téléchargé.'})
                else:
                    self.send({'error': 'Route inconnue'}, 404)

            def do_POST(self):
                try:
                    size = int(self.headers.get('Content-Length', 0))
                    if not 0 <= size <= 16384:
                        raise ValueError('Taille invalide')
                    payload = json.loads(self.rfile.read(size) or b'{}')
                    route = urlparse(self.path).path
                    with maintenance.lock:
                        if route == '/api/maintenance':
                            maintenance.configure(payload)
                        elif route.startswith('/api/connections/'):
                            edge = next(e for e in connections.entries(cfg) if e['id'] == payload.get('id'))
                            maintenance.state['connections'][edge['id']] = {'state': 'verifiee', 'checked_at': stamp(), 'detail': 'Test simulé réussi.'}
                        elif route == '/api/action':
                            if payload.get('service') in states:
                                states[payload['service']] = payload.get('action') != 'stop'
                        elif route == '/api/backup':
                            maintenance.state['last_backup'] = stamp()
                        elif route not in ('/api/rotate', '/api/update', '/api/add', '/api/self-update'):
                            self.send({'error': 'Route inconnue'}, 404)
                            return
                        maintenance.event('Simulation ' + route.rsplit('/', 1)[-1], True, payload.get('service', ''))
                    self.send({'ok': True, 'message': 'Simulation réussie. Aucune modification réelle.', 'archive': 'DEMO-archive.zip', 'mega': 0, 'fichiers': 0, 'volumes': [], 'secret': 'DEMO-secret'})
                except (ValueError, TypeError, StopIteration):
                    self.send({'error': 'Requête invalide'}, 400)

        # Ask the OS for an available port: another preview may still be running.
        # Never reuse its URL or stop a process that belongs to a different copy.
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        url = f'http://127.0.0.1:{server.server_port}/#connections'
        print(f'Demo carte V2 : {url}', flush=True)
        print(f'Sources : {SOURCE_ROOT}', flush=True)
        print('Gardez cette fenetre ouverte. Ctrl+C pour fermer.', flush=True)
        if options.open:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == '__main__':
    main()
