"""A new demo must serve its own source even if an older demo is still open."""

import os
import queue
import re
import subprocess
import sys
import threading
from pathlib import Path

import httpx


def test_two_previews_use_local_sources_and_distinct_addresses(tmp_path):
    stale = tmp_path / 'old-installation' / 'plugarr'
    stale.mkdir(parents=True)
    (stale / '__init__.py').write_text("raise RuntimeError('OLD INSTALLATION WAS IMPORTED')\n")
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'preview_console.py'
    environment = {**os.environ, 'PYTHONPATH': str(stale.parent), 'PLUGARR_NO_SELF_UPDATE': '1',
                   'PYTHONIOENCODING': 'utf-8'}
    processes = []
    addresses = []
    try:
        for _ in range(2):
            process = subprocess.Popen(
                [sys.executable, '-u', str(script)], cwd=tmp_path, env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8',
            )
            processes.append(process)
            output = queue.Queue()
            threading.Thread(target=lambda p=process, q=output: q.put(p.stdout.readline()), daemon=True).start()
            line = output.get(timeout=20)
            match = re.search(r'http://127\.0\.0\.1:\d+/', line)
            assert match, f'Demo did not announce its URL: {line!r}; exit={process.poll()}'
            addresses.append(match[0])
            assert '#connections' in line
            with httpx.Client(base_url=addresses[-1], trust_env=False) as client:
                response = client.get('/')
                assert response.status_code == 200
                assert response.headers['cache-control'] == 'no-store'
                assert 'Carte des connexions · V2 (démo)' in response.text
                assert 'id="map-logo"' in response.text and 'map-brand-gradient' in response.text
                assert 'Les autres intégrations ne sont pas encore représentées.' not in response.text
                data = client.get('/api/connections').json()
                assert {'seerr', 'flood'} <= {n['id'] for n in data['nodes']}
                assert all(e['state'] == 'non verifiee' for e in data['connections'])
        assert len(set(addresses)) == 2
        assert all(process.poll() is None for process in processes)
    finally:
        for process in processes:
            process.terminate()
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=10)
