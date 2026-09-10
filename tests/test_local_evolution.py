"""Regression gates for local maintenance and executable integrity."""
import hashlib
import threading
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from plugarr import admin, connections, orchestrator, selfupdate
from plugarr.maintenance import Maintenance
from plugarr.models import PlatformProfile


@pytest.fixture(autouse=True)
def no_proxy_for_mocked_http(monkeypatch):
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def cfg():
    return orchestrator.build_config(services=['sonarr', 'prowlarr', 'qbittorrent'],
        data_root='/tmp/data', config_root='/tmp/config', platform=PlatformProfile.GENERIC_LINUX)


@pytest.fixture
def live(cfg, tmp_path):
    server = admin.build_server(cfg, tmp_path, host='127.0.0.1', port=0, token='test-token')
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with httpx.Client(base_url=f'http://127.0.0.1:{server.server_address[1]}',
                      cookies={'plugarr_token': 'test-token'}, trust_env=False) as client:
        yield client, server.RequestHandlerClass.maintenance
    server.shutdown()
    server.server_close()


def test_backup_route_is_reachable(live, monkeypatch, tmp_path):
    client, maintenance = live
    archive = tmp_path / 'test.zip'
    archive.write_bytes(b'archive')
    monkeypatch.setattr(maintenance, 'backup', lambda: SimpleNamespace(archive=archive, fichiers=2, volumes=[]))
    response = client.post('/api/backup')
    assert response.status_code == 200
    assert response.json()['ok']


def test_extensions_require_auth(live):
    client, _ = live
    client.cookies.clear()
    for route in ('maintenance', 'connections', 'self-update'):
        assert client.get('/api/' + route).status_code == 401
        assert client.post('/api/' + route, json={}).status_code == 401


def test_preferences_validation_and_persistence(live, cfg, tmp_path):
    client, _ = live
    assert client.post('/api/maintenance', json={'schedule': {'keep': 0}}).status_code == 400
    assert client.post('/api/maintenance', json={'schedule': {'days': True}}).status_code == 400
    assert client.post('/api/maintenance', json=[]).status_code == 400
    assert client.post('/api/maintenance', json={'schedule': {'enabled': True, 'hour': 5}}).status_code == 200
    assert Maintenance(cfg, tmp_path).snapshot()['schedule']['hour'] == 5


def test_unknown_connection_and_unconfirmed_repair_refused(live):
    client, _ = live
    assert client.post('/api/connections/test', json={'id': '../../unknown'}).status_code == 400
    assert client.post('/api/connections/repair', json={'id': 'sonarr/downloadclient/qbittorrent'}).status_code == 400


def test_connection_unknown_until_real_test(cfg, monkeypatch):
    edges = connections.entries(cfg)
    edge = next(e for e in edges if e['id'] == 'sonarr/downloadclient/qbittorrent')
    assert edge['state'] == 'non verifiee'
    class API:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def find_by_name(self, *args): return {'id': 4}
        def test_resource(self, *args): return False, 'secret=should-never-appear'
    monkeypatch.setattr(connections, 'ArrClient', API)
    result = connections.test(cfg, edge)
    assert result['state'] == 'en echec'
    assert 'secret=' not in str(result)


def test_diagram_api_has_nodes_and_refuses_untestable_links(live):
    client, maintenance = live
    extra = orchestrator.build_config(services=['qui'], data_root='/tmp/data', config_root='/tmp/config')
    maintenance.cfg.services['qui'] = extra.services['qui']
    data = client.get('/api/connections').json()
    assert {n['id'] for n in data['nodes']} == {'sonarr', 'prowlarr', 'qbittorrent', 'qui'}
    assert not any(key in node for node in data['nodes'] for key in ('password', 'api_key', 'username'))
    edge = next(e for e in data['connections'] if e['source'] == 'qui')
    assert not edge['testable'] and not edge['repairable']
    for action in ('test', 'repair'):
        response = client.post('/api/connections/' + action, json={'id': edge['id'], 'confirmed': True})
        assert response.status_code == 400
    assert not maintenance.snapshot()['connections']
    assert "img-src 'self' data:" in client.get('/').headers['Content-Security-Policy']


def test_scheduler_disabled_and_one_attempt_per_window(cfg, tmp_path, monkeypatch):
    maintenance = Maintenance(cfg, tmp_path)
    now = datetime(2026, 9, 6, 3, 0, tzinfo=UTC)
    calls = []
    def backup():
        calls.append(1)
        maintenance.state['last_attempt'] = now.timestamp()
    monkeypatch.setattr(maintenance, 'backup', backup)
    maintenance.tick(now)
    assert not calls
    maintenance.configure({'schedule': {'enabled': True}})
    maintenance.tick(now)
    maintenance.tick(now)
    assert len(calls) == 1


def test_repeated_alerts_are_deduplicated_and_recovery_recorded(cfg, tmp_path):
    maintenance = Maintenance(cfg, tmp_path)
    maintenance.alert('services:sonarr', True, 'Sonarr unavailable')
    maintenance.alert('services:sonarr', True, 'Sonarr unavailable')
    maintenance.alert('services:sonarr', False, 'Sonarr unavailable')
    assert len(maintenance.snapshot()['events']) == 2
    assert not maintenance.snapshot()['alerts']['services:sonarr']['active']


def test_download_rejects_corruption_without_touching_existing_exe(tmp_path, httpx_mock):
    executable = tmp_path / 'plugarr.exe'
    executable.write_bytes(b'MZ-original')
    candidate = tmp_path / 'candidate.exe'
    url = 'https://github.com/yannickuhrig1/plugarr/releases/download/v0.8.0/plugarr.exe'
    httpx_mock.add_response(url=url, content=b'MZ-corrupt')
    info = {'verified_asset': True, 'available': True, 'url': url, 'size': 10,
            'digest': 'sha256:' + '0' * 64}
    with pytest.raises(ValueError): selfupdate.download(info, candidate)
    assert not candidate.exists()
    assert executable.read_bytes() == b'MZ-original'


def test_download_accepts_verified_binary(tmp_path, httpx_mock):
    binary = b'MZ-test-executable'
    url = 'https://github.com/yannickuhrig1/plugarr/releases/download/v0.8.0/plugarr.exe'
    httpx_mock.add_response(url=url, content=binary)
    destination = tmp_path / 'candidate.exe'
    selfupdate.download({'verified_asset': True, 'available': True, 'url': url,
        'size': len(binary), 'digest': 'sha256:' + hashlib.sha256(binary).hexdigest()}, destination)
    assert destination.read_bytes() == binary


@pytest.mark.parametrize('tag', ['v0.8.1', 'v0.10.0'])
def test_check_uses_stable_asset_with_digest(tag, httpx_mock):
    httpx_mock.add_response(url=selfupdate.API, json={'tag_name':tag, 'assets':[{
        'name':'plugarr.exe', 'browser_download_url':f'https://github.com/{selfupdate.REPOSITORY}/releases/download/{tag}/plugarr.exe',
        'digest':'sha256:'+'1'*64, 'size':100}]})
    result = selfupdate.check()
    assert result['available'] and result['verified_asset']


def test_check_refuses_untrusted_download_url(httpx_mock):
    httpx_mock.add_response(url=selfupdate.API, json={'tag_name':'v0.8.0', 'assets':[{
        'name':'plugarr.exe', 'browser_download_url':'https://example.org/plugarr.exe',
        'digest':'sha256:'+'1'*64, 'size':100}]})
    assert not selfupdate.check()['verified_asset']


def test_source_execution_never_stages(monkeypatch):
    monkeypatch.setattr(selfupdate, 'check', lambda: pytest.fail('Source startup must not query GitHub'))
    selfupdate.startup()


def test_local_binary_protection(monkeypatch):
    monkeypatch.setenv('PLUGARR_NO_SELF_UPDATE', '1')
    with pytest.raises(ValueError, match='desactivee'):
        selfupdate._stage({})


def test_existing_download_destination_is_preserved(tmp_path, httpx_mock):
    target = tmp_path / 'candidate.exe'
    target.write_bytes(b'original-file')
    url = 'https://github.com/yannickuhrig1/plugarr/releases/download/v0.8.0/plugarr.exe'
    httpx_mock.add_response(url=url, content=b'MZ-new')
    with pytest.raises(FileExistsError):
        selfupdate.download({'verified_asset': True, 'available': True, 'url': url,
                             'size': 6, 'digest': 'sha256:' + '1' * 64}, target)
    assert target.read_bytes() == b'original-file'


def test_backup_retention_leaves_unmanaged_archives(cfg, tmp_path, monkeypatch):
    maintenance = Maintenance(cfg, tmp_path)
    directory = tmp_path / 'backups'
    directory.mkdir()
    unrelated = directory / 'plugarr-my-manual-archive.zip'
    unrelated.write_bytes(b'manual')
    old = directory / 'plugarr-old.zip'
    old.write_bytes(b'old')
    maintenance.state['archives'] = [old.name]
    maintenance.configure({'schedule': {'keep': 1}})

    def backup(cfg, project_dir, destination):
        destination.write_bytes(b'new-archive')
        return SimpleNamespace(archive=destination)

    monkeypatch.setattr('plugarr.maintenance.sauvegarde.sauvegarder', backup)
    report = maintenance.backup()
    assert report.archive.exists()
    assert unrelated.read_bytes() == b'manual'
    assert not old.exists()
    assert maintenance.snapshot()['last_backup']


def test_backup_failure_does_not_prune(cfg, tmp_path, monkeypatch):
    maintenance = Maintenance(cfg, tmp_path)
    directory = tmp_path / 'backups'
    directory.mkdir()
    old = directory / 'plugarr-old.zip'
    old.write_bytes(b'old')
    maintenance.state['archives'] = [old.name]

    def fail(*args):
        raise OSError('test failure')

    monkeypatch.setattr('plugarr.maintenance.sauvegarde.sauvegarder', fail)
    with pytest.raises(OSError):
        maintenance.backup()
    assert old.read_bytes() == b'old'
    assert maintenance.snapshot()['alerts']['backup']['active']
    assert maintenance.snapshot()['last_backup'] is None


def test_windows_staging_keeps_original_and_paths_as_data(tmp_path, monkeypatch):
    executable = tmp_path / "Plug Arr 'test'.exe"
    executable.write_bytes(b'MZ-original')
    monkeypatch.delenv('PLUGARR_NO_SELF_UPDATE', raising=False)
    monkeypatch.setattr(selfupdate.sys, 'platform', 'win32')
    monkeypatch.setattr(selfupdate.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(selfupdate.sys, 'executable', str(executable))
    monkeypatch.setattr(selfupdate, 'download', lambda info, target: target.write_bytes(b'MZ-new'))
    calls = []
    monkeypatch.setattr(selfupdate.subprocess, 'Popen', lambda args, **kwargs: calls.append((args, kwargs)))
    directory = selfupdate._stage({'digest': 'sha256:' + '1' * 64})
    assert executable.read_bytes() == b'MZ-original'
    script = (directory / 'install.ps1').read_text(encoding='utf-8-sig')
    assert script.index('Wait-Process') < script.index('[System.IO.File]::Replace')
    assert str(executable) not in script
    assert calls[0][1]['env']['PLUGARR_UPDATE_DIRECTORY'] == str(directory)


def test_console_vpn_node_gets_actual_container_state(cfg, monkeypatch):
    cfg.vpn.enabled = True
    monkeypatch.setattr(admin, 'read_states', lambda _: {
        'gluetun': admin.ServiceState(service='gluetun', state='running', status='Up', health='healthy')})
    result = admin.status_payload(cfg, None)
    node = next(n for n in result['services'] if n['id'] == 'gluetun')
    assert node['up'] and node['health'] == 'healthy'
