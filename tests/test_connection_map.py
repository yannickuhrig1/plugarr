"""The diagram must reflect the configured topology without inventing success."""

import base64
import json
import re
import shutil
import subprocess
from pathlib import Path
from xml.etree import ElementTree

import pytest

from plugarr import catalog, connection_map, connections, dashboard, orchestrator


def config(*services):
    return orchestrator.build_config(services=list(services), data_root='/demo/data', config_root='/demo/config')


def pairs(data, kind):
    return {(e['source'], e['target']) for e in data['connections'] if e['kind'] == kind}


def test_all_nodes_are_selected_including_services_without_api_links():
    cfg = config('audiobookshelf', 'silo', 'sonarr', 'radarr', 'lidarr', 'jellyfin', 'qbittorrent')
    data = connections.topology(cfg)
    ids = {n['id'] for n in data['nodes']}
    assert ids == set(cfg.services)
    assert 'audiobookshelf' in ids and 'silo-postgres' in ids
    assert pairs(data, 'notification') == {('sonarr', 'jellyfin'), ('radarr', 'jellyfin')}
    assert pairs(data, 'dependency') == {('silo', 'silo-postgres'), ('silo', 'silo-redis')}
    assert all(e['source'] in ids and e['target'] in ids for e in data['connections'])
    assert not any(e['source'] == 'audiobookshelf' or e['target'] == 'audiobookshelf' for e in data['connections'])


def test_flood_has_one_actual_backend_and_no_invented_adopted_configuration():
    cfg = config('flood', 'transmission', 'qbittorrent')
    assert pairs(connections.topology(cfg), 'control') == {('flood', 'qbittorrent')}
    del cfg.services['qbittorrent']
    assert pairs(connections.topology(cfg), 'control') == {('flood', 'transmission')}
    cfg.services['flood'].adopted = True
    assert not pairs(connections.topology(cfg), 'control')


def test_vpn_only_carries_managed_download_clients():
    cfg = config('sonarr', 'qbittorrent', 'transmission', 'sabnzbd')
    assert 'gluetun' not in {n['id'] for n in connections.topology(cfg)['nodes']}
    cfg.vpn.enabled = True
    cfg.services['transmission'].adopted = True
    data = connections.topology(cfg)
    assert 'gluetun' in {n['id'] for n in data['nodes']}
    assert pairs(data, 'vpn') == {('qbittorrent', 'gluetun'), ('sabnzbd', 'gluetun')}
    assert all(not e['testable'] for e in data['connections'] if e['kind'] == 'vpn')


def test_optional_integrations_follow_the_wiring_conditions():
    cfg = config('seerr', 'recyclarr', 'sonarr', 'radarr', 'lidarr', 'autobrr', 'droppedneedle', 'qui')
    cfg.recyclarr_templates = {'radarr': ''}
    cfg.services['jellyfin'].api_key = None
    data = connections.topology(cfg)
    assert pairs(data, 'profiles') == {('recyclarr', 'sonarr')}
    assert pairs(data, 'request') == {('seerr', 'sonarr'), ('seerr', 'radarr')}
    assert pairs(data, 'authentication') == {('seerr', 'jellyfin')}
    assert pairs(data, 'control') == {('qui', 'qbittorrent')}
    assert pairs(data, 'music') == {('droppedneedle', 'sabnzbd')}
    assert not pairs(data, 'library')
    assert pairs(data, 'dispatch') == {('autobrr', sid) for sid in ('sonarr', 'radarr', 'lidarr', 'qbittorrent', 'sabnzbd')}
    cfg.services['jellyfin'].api_key = 'not-in-api-response'
    data = connections.topology(cfg)
    assert pairs(data, 'library') == {('droppedneedle', 'jellyfin')}
    assert 'not-in-api-response' not in json.dumps(data)


def test_only_supported_links_accept_saved_test_results():
    cfg = config('sonarr', 'qbittorrent', 'qui')
    cfg.services['sonarr'].adopted = True
    saved = {'sonarr/downloadclient/qbittorrent': {'state': 'verifiee', 'checked_at': '2026-09-06T00:00:00+00:00', 'target': 'invented'},
             'qui/control/qbittorrent': {'state': 'verifiee'}}
    edges = {e['id']: e for e in connections.topology(cfg, saved)['connections']}
    edge = edges['sonarr/downloadclient/qbittorrent']
    assert edge['state'] == 'verifiee' and edge['testable'] and not edge['repairable']
    assert edge['target'] == 'qbittorrent'
    assert edges['qui/control/qbittorrent']['state'] == 'non verifiee'


def test_complete_catalog_has_no_dangling_or_duplicate_links():
    cfg = config(*[s.id for s in catalog.CATALOG.values() if not s.internal])
    cfg.vpn.enabled = True
    data = connections.topology(cfg)
    ids = {n['id'] for n in data['nodes']}
    assert len(ids) == len(data['nodes'])
    assert len({e['id'] for e in data['connections']}) == len(data['connections'])
    assert all(e['source'] in ids and e['target'] in ids for e in data['connections'])
    assert all(e['state'] == 'non verifiee' for e in data['connections'])
    assert connections.topology(config()) == {'nodes': [], 'connections': []}


def test_embedded_icons_are_complete_and_self_contained():
    icons = json.loads((Path(connection_map.__file__).parent / 'data' / 'connection_icons.json').read_text())
    assert set(catalog.CATALOG) | {'gluetun', 'plugarr'} <= set(icons)
    for uri in icons.values():
        header, body = uri.split(',', 1)
        content = base64.b64decode(body, validate=True)
        if header.startswith('data:image/svg+xml'):
            root = ElementTree.fromstring(content)
            for node in root.iter():
                assert node.tag.rsplit('}', 1)[-1] not in ('script', 'foreignObject')
                for key, value in node.attrib.items():
                    assert not key.lower().startswith('on')
                    if key.endswith('href'):
                        assert value.startswith(('#', 'data:'))
        else:
            assert content.startswith(b'\x89PNG\r\n\x1a\n')


def test_all_embedded_scripts_parse_as_javascript(tmp_path):
    if not shutil.which('node'):
        pytest.skip('Node is used for JavaScript syntax validation')
    page = dashboard.render(config('sonarr', 'qbittorrent'), live=True)
    assert page.count('id="graph"') == 1
    assert '__ICONS__' not in page
    for index, code in enumerate(re.findall(r'<script>(.*?)</script>', page, re.DOTALL)):
        path = tmp_path / f'console-{index}.js'
        path.write_text(code, encoding='utf-8')
        subprocess.run(['node', '--check', str(path)], check=True, capture_output=True)


def test_admin_uses_wizard_layout_but_only_real_link_test_results():
    from plugarr import wizard_graph

    cfg = config('sonarr', 'qbittorrent', 'flood', 'jellyfin')
    cfg.vpn.enabled = True
    data = wizard_graph.administration(cfg)
    wizard = wizard_graph.build(cfg)
    assert data['graph']['colonnes'] == wizard['colonnes']
    assert {(n['id'], n['colonne']) for n in data['graph']['noeuds']} == {
        (n['id'], n['colonne']) for n in wizard['noeuds']}
    assert {e['etape'] for e in data['graph']['liens'] if not e['structure']} == {
        e['id'] for e in data['connections'] if e['testable']}
    assert all(n['reglages'] == [] for n in data['graph']['noeuds'])
    saved = {'sonarr/downloadclient/qbittorrent': {'state': 'en echec', 'checked_at': '2026-09-07T00:00:00Z'}}
    tested = wizard_graph.administration(cfg, saved)
    assert tested['graph'] == data['graph']  # preserve the drawing/focus on polling
    assert next(e for e in tested['connections'] if e['id'] in saved)['state'] == 'en echec'
    for inst in cfg.services.values():
        inst.api_key = 'private-value-not-to-serialize'
        inst.password = 'private-value-not-to-serialize'
    assert 'private-value-not-to-serialize' not in json.dumps(wizard_graph.administration(cfg))


def test_console_embeds_shared_renderer_and_admin_adapter():
    page = dashboard.render(config('sonarr'), live=True)
    shared = (Path(connection_map.__file__).parent / 'web' / 'graph.js').read_text()
    assert shared in page
    assert page.count('id="wiring-graph"') == 1
    assert 'id="map-expand"' not in page
    assert 'function draw(){\n  svg.replaceChildren()' not in page


def test_torrent_interfaces_are_in_downloads_in_both_graphs():
    from plugarr import wizard_graph

    cfg = config('flood', 'qui', 'jellyfin')
    cfg.vpn.enabled = True
    for graph in (wizard_graph.build(cfg), wizard_graph.administration(cfg)['graph']):
        nodes = {n['id']: n for n in graph['noeuds']}
        assert nodes['flood']['colonne'] == nodes['qui']['colonne'] == 'telechargement'
        assert nodes['jellyfin']['colonne'] == 'media'
        assert not any(e['source'] in ('flood', 'qui') and e['cible'] == 'gluetun' for e in graph['liens'])
