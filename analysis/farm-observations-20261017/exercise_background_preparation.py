"""Real render through a disposable HTTP backend; no desktop, phones or external network."""
import hashlib
import argparse
import json
from pathlib import Path
import sys
import threading
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from farm_test_network import allowed_ports
import imouse_farm_server as server

RUN = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--final', action='store_true')
args = parser.parse_args()
suffix = '-final' if args.final else ''
data = RUN / ('background-render' + suffix)
data.mkdir(exist_ok=False)
runtime = server.FarmBackendRuntime(data / 'farm.db', data / 'stage')
runtime.db.update_persona('C24C', account_day=5, paused_zero_view=False)
server.RUNTIME = runtime
httpd = server.FarmControlServer(('127.0.0.1', 0), server.FarmRequestHandler)
allowed_ports.add(httpd.server_port)
worker = threading.Thread(target=httpd.serve_forever, daemon=True); worker.start()
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def request(path, body=None):
    payload = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(f'http://127.0.0.1:{httpd.server_port}' + path, payload, {'Content-Type': 'application/json'})
    with opener.open(req, timeout=5) as response: return json.load(response)

try:
    config = dict(id=str(uuid.uuid4()), device_id='C24C', action='create-content', interval_minutes=60, max_runs=1)
    request('/api/farm/preparation-schedule', config)
    runtime.preparation.start()
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        status = request('/api/farm/preparation-schedule')['preparationSchedule']
        if status['config']['state'] in ('complete', 'held', 'needs_review'): break
        time.sleep(.2)
    assert status['config']['state'] == 'complete', status
    assert len(status['runs']) == 1 and status['runs'][0]['state'] == 'succeeded'
    assert len(status['runs'][0]['contentItems']) == 5
    manifest = json.loads((data / 'stage/C24C/manifest.json').read_text(encoding='utf-8'))
    for asset in manifest['assets']:
        file = data / 'stage/C24C' / asset['url'].rsplit('/', 1)[-1]
        assert hashlib.sha256(file.read_bytes()).hexdigest() == asset['sha256']
    assert not runtime.mock_kernel.commands_dispatched
    (RUN / ('background-preparation-result' + suffix + '.json')).write_text(json.dumps({'schedule': status, 'assetsChecked': len(manifest['assets']),
        'phoneCommands': 0, 'externalNetworkAllowed': False}, indent=2), encoding='utf-8')
    print(json.dumps({'state': status['config']['state'], 'assetsChecked': len(manifest['assets']), 'phoneCommands': 0}))
finally:
    runtime.preparation.close(); runtime.transfers.close()
    httpd.shutdown(); httpd.server_close(); worker.join(2); allowed_ports.discard(httpd.server_port)
