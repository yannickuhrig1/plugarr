"""Connections from the wiring plan. Verification invokes real source API tests."""
from . import catalog
from .clients.arr import ArrClient
from .clients.recyclarr import DEFAULT_TEMPLATES
from .compose import flood_client
from .maintenance import stamp
from .models import Category
from .wiring import Wirer

RESOURCES = {'downloadclient': 'downloadclient', 'application': 'applications', 'notification': 'notification'}

LABELS = {
    'downloadclient': ('Téléchargements', 'Envoie les téléchargements au client et suit leur progression.'),
    'application': ('Indexeurs', 'Synchronise les indexeurs Prowlarr vers cette application.'),
    'notification': ('Bibliothèque', 'Notifie Jellyfin après un import ; les médias restent dans les dossiers partagés.'),
}
ROLES = {
    'prowlarr': (0, 'Indexeurs'), 'autobrr': (0, 'Annonces IRC'),
    'seerr': (0, 'Demandes'), 'recyclarr': (0, 'Profils de qualité'),
    'qui': (0, 'Interface torrent'), 'flood': (0, 'Interface torrent'),
    'sonarr': (1, 'Séries et anime'), 'radarr': (1, 'Films'),
    'lidarr': (1, 'Musique'), 'droppedneedle': (1, 'Musique Usenet'),
    'qbittorrent': (2, 'Torrents'), 'transmission': (2, 'Torrents'),
    'sabnzbd': (2, 'Usenet'), 'jellyfin': (3, 'Serveur multimédia'),
    'audiobookshelf': (3, 'Livres audio et podcasts'), 'silo': (3, 'Serveur multimédia'),
    'silo-postgres': (3, 'Base de Silo'), 'silo-redis': (3, 'Cache de Silo'),
}


def topology(cfg, saved=None):
    """Expected topology from StackConfig, never a claim of runtime discovery.

    Only the three *arr resources have per-link API tests. Other relationships
    mirror wiring.py / compose.py and remain explicitly untested. No shared
    volume is misrepresented as a service-to-service API connection.
    """
    nodes = []
    for sid in catalog.STARTUP_ORDER:
        if not cfg.enabled(sid):
            continue
        spec = catalog.get(sid)
        group, role = ROLES.get(sid, (3, 'Service'))
        nodes.append({'id': sid, 'name': spec.display_name, 'group': group,
                      'role': role, 'adopted': cfg.services[sid].adopted})
    edges = []
    for edge in entries(cfg):
        label, description = LABELS[edge['kind']]
        result = (saved or {}).get(edge['id'], {})
        edges.append({**edge, **{k: result[k] for k in ('state', 'checked_at', 'detail') if k in result},
                      'label': label, 'description': description, 'basis': 'Plan de câblage',
                      'testable': True, 'repairable': not cfg.services[edge['source']].adopted})

    def add(source, target, kind, label, description, basis='Plan de câblage'):
        if not cfg.enabled(source) or not cfg.enabled(target):
            return
        edges.append({'id': f'{source}/{kind}/{target}', 'source': source, 'target': target,
                      'kind': kind, 'label': label, 'description': description, 'basis': basis,
                      'state': 'non verifiee', 'checked_at': None, 'testable': False, 'repairable': False})

    for sid in (*catalog.MANAGED_ARRS, *catalog.DOWNLOAD_CLIENTS):
        add('autobrr', sid, 'dispatch', 'Annonces', 'Transmet les annonces aux applications et clients sélectionnés.')
    for sid in ('sonarr', 'radarr'):
        add('seerr', sid, 'request', 'Demandes', 'Envoie les demandes ; le câblage nécessite un profil de qualité disponible.')
        if cfg.recyclarr_templates.get(sid, DEFAULT_TEMPLATES.get(sid, '')):
            add('recyclarr', sid, 'profiles', 'Profils', 'Synchronise les profils du modèle TRaSH choisi.')
    add('seerr', 'jellyfin', 'authentication', 'Compte et bibliothèque', 'Utilise Jellyfin pour la connexion et la bibliothèque.')
    add('qui', 'qbittorrent', 'control', 'Pilotage', 'Pilote cette instance qBittorrent.')
    target = flood_client(cfg)
    if target and not cfg.services['flood'].adopted:
        add('flood', target, 'control', 'Pilotage', 'Flood pilote un seul client ; qBittorrent est prioritaire si les deux sont sélectionnés.', 'Configuration Compose')
    add('droppedneedle', 'sabnzbd', 'music', 'Musique Usenet', 'Envoie les téléchargements à la catégorie musique de SABnzbd.')
    if cfg.enabled('jellyfin') and cfg.services['jellyfin'].api_key:
        add('droppedneedle', 'jellyfin', 'library', 'Bibliothèque', 'Déclare Jellyfin avec la clé disponible dans la configuration.')
    for sid in catalog.STARTUP_ORDER:
        if not cfg.enabled(sid) or cfg.services[sid].adopted:
            continue
        spec = catalog.get(sid)
        for dependency in spec.depends_on_healthy:
            add(sid, dependency, 'dependency', 'Dépendance', 'Attend cette dépendance saine au démarrage.', 'Configuration Compose')
        if cfg.vpn_enabled and spec.category is Category.DOWNLOAD:
            edges.append({'id': f'{sid}/vpn/gluetun', 'source': sid, 'target': 'gluetun',
                          'kind': 'vpn', 'label': 'Réseau VPN', 'description': 'Partage le réseau de Gluetun. Ce lien ne prouve pas que le tunnel VPN fonctionne.',
                          'basis': 'Configuration Compose', 'state': 'non verifiee', 'checked_at': None,
                          'testable': False, 'repairable': False})
    if cfg.vpn_enabled:
        nodes.append({'id': 'gluetun', 'name': 'Gluetun', 'group': 2, 'role': 'Passerelle VPN', 'adopted': False})
    return {'nodes': nodes, 'connections': edges}


def entries(cfg):
    wirer = Wirer(cfg)
    try:
        result = []
        for step in wirer.build_plan():
            parts = step.name.split('/')
            if len(parts) == 3 and parts[1] in RESOURCES and cfg.enabled(parts[2]):
                result.append({'id': step.name, 'source': parts[0], 'target': parts[2],
                               'kind': parts[1], 'state': 'non verifiee', 'checked_at': None})
        return result
    finally:
        wirer.close()


def test(cfg, edge):
    source = edge['source']
    spec, inst = catalog.get(source), cfg.services[source]
    try:
        with ArrClient(inst.url(cfg.host), inst.api_key or '', api_version=spec.api_version, name=source) as client:
            resource = RESOURCES[edge['kind']]
            item = client.find_by_name(resource, catalog.get(edge['target']).display_name)
            if item is None:
                return {'state': 'en echec', 'checked_at': stamp(), 'detail': 'Connexion absente dans le service source.'}
            ok, _ = client.test_resource(resource, item)
            return {'state': 'verifiee' if ok else 'en echec', 'checked_at': stamp(),
                    'detail': 'Test reussi.' if ok else 'Test refuse. Verifiez adresse, port et identifiants dans le service source.'}
    except Exception:  # noqa: BLE001 - keep API/worker failures contained and secrets out of responses
        return {'state': 'en echec', 'checked_at': stamp(),
                'detail': 'Verification impossible. Controlez le service source et son acces API.'}


def repair(cfg, edge):
    wirer = Wirer(cfg)
    try:
        step = next(s for s in wirer.build_plan() if s.name == edge['id'])
        return step.run().ok
    finally:
        wirer.close()
