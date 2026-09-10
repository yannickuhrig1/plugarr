"""Authenticated maintenance routes; called under the console operation lock."""
from http import HTTPStatus

from . import connections, selfupdate, wizard_graph

GET_ROUTES = {'/api/maintenance', '/api/connections', '/api/self-update'}
POST_ROUTES = {'/api/maintenance', '/api/connections/test', '/api/connections/repair', '/api/self-update'}


def get(handler, route):
    if route == '/api/maintenance':
        handler._json(handler.maintenance.snapshot())
    elif route == '/api/connections':
        saved = handler.maintenance.snapshot()['connections']
        handler._json(wizard_graph.administration(handler.cfg, saved))
    else:
        try:
            handler._json(selfupdate.check())
        except Exception:  # noqa: BLE001 - keep API/worker failures contained and secrets out of responses
            handler._json({'error': 'Recherche GitHub indisponible. Reessayez plus tard.'}, HTTPStatus.BAD_GATEWAY)


def post(handler, route, payload):
    maintenance = handler.maintenance
    if route == '/api/maintenance':
        try:
            maintenance.configure(payload)
            handler._json({'ok': True})
        except (ValueError, TypeError) as exc:
            handler._json({'error': str(exc)}, HTTPStatus.BAD_REQUEST)
        return
    if route == '/api/self-update':
        try:
            selfupdate.stage(selfupdate.check())
            maintenance.event('mise a jour PlugArr preparee', True)
            handler._json({'ok': True, 'message': 'Installation a la fermeture de PlugArr, activation au prochain lancement.'})
        except Exception:  # noqa: BLE001 - keep API/worker failures contained and secrets out of responses
            handler._json({'error': 'Mise a jour impossible : binaire local protege, plateforme incompatible ou release non verifiable.'}, HTTPStatus.BAD_REQUEST)
        return
    edge = next((e for e in connections.entries(handler.cfg) if e['id'] == payload.get('id')), None)
    if edge is None:
        handler._json({'error': 'Liaison inconnue'}, HTTPStatus.BAD_REQUEST)
        return
    if route.endswith('/repair'):
        if payload.get('confirmed') is not True:
            handler._json({'error': 'Confirmez la reapplication du cablage de cette liaison.'}, HTTPStatus.BAD_REQUEST)
            return
        if handler.cfg.services[edge['source']].adopted:
            handler._json({'error': 'Reparation automatique refusee pour un service adopte.'}, HTTPStatus.BAD_REQUEST)
            return
        try:
            ok = connections.repair(handler.cfg, edge)
        except Exception:  # noqa: BLE001 - keep API/worker failures contained and secrets out of responses
            ok = False
        maintenance.event('reparation connexion', ok, edge['id'])
    result = connections.test(handler.cfg, edge)
    maintenance.state['connections'][edge['id']] = result
    maintenance.event('test connexion', result['state'] == 'verifiee', edge['id'])
    handler._json({'ok': result['state'] == 'verifiee', **result})
