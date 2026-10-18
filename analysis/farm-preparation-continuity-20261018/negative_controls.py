"""Show the corrected failures on HEAD's preserved source, without editing it."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import types
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[2]; RUN = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools'))
import farm_jobs, farm_drafts
from PIL import Image

def old_module(name):
    raw = subprocess.check_output(['git', '-c', 'safe.directory=' + ROOT.as_posix(), 'show', '91dfda8:tools/' + name + '.py'], cwd=ROOT)
    module = types.ModuleType('previous_' + name); sys.modules[module.__name__] = module
    exec(compile(raw, name + '-previous.py', 'exec'), module.__dict__)
    return module

def cancelled_before_arrival(module, folder):
    jobs = module.FarmJobs(journal_path=folder / 'jobs.db'); request_id = str(uuid.uuid4())
    try: jobs.cancel(request_id)
    except KeyError: return False
    restarted = module.FarmJobs(journal_path=folder / 'jobs.db')
    calls = []
    result = restarted.submit(request_id, 'test', {}, lambda cancel: calls.append('ran'))
    return result['status'] == 'cancelled' and not calls

def terminal_race(module):
    jobs = module.FarmJobs(); entered, release = threading.Event(), threading.Event()
    class Delayed(threading.Event):
        def wait(self, timeout=None): entered.set(); release.wait(2); return False
    job = module.Job(str(uuid.uuid4()), 'test', 'test', heartbeat=0); job.done = Delayed()
    worker = threading.Thread(target=jobs._watch, args=(job,)); worker.start(); assert entered.wait(1)
    with jobs._lock: job.status = 'succeeded'; job.done.set()
    release.set(); worker.join(2)
    assert not worker.is_alive()
    return job.status == 'succeeded'

def stable_export(module, folder):
    import base64
    drafts = module.CarouselDrafts(folder / 'drafts.db', folder / 'stage')
    draft = drafts.create(str(uuid.uuid4()))
    for color in ('red', 'blue'):
        raw = io.BytesIO(); Image.new('RGB', (40, 50), color).save(raw, 'PNG')
        draft = drafts.import_image(draft['id'], draft['revision'], color + '.png', base64.b64encode(raw.getvalue()).decode())
    with patch('zipfile.time.localtime', return_value=(2026, 1, 1, 12, 0, 0, 0, 0, 0)): first = drafts.export(draft['id'], draft['revision'])
    with patch('zipfile.time.localtime', return_value=(2030, 1, 1, 12, 0, 0, 0, 0, 0)): second = drafts.export(draft['id'], draft['revision'])
    return hashlib.sha256(first).digest() == hashlib.sha256(second).digest()

results = []
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    for name, check, previous, current in (
        ('cancel before admission', cancelled_before_arrival, old_module('farm_jobs'), farm_jobs),
        ('terminal monitor race', lambda module, folder: terminal_race(module), old_module('farm_jobs'), farm_jobs),
        ('same revision package checksum', stable_export, old_module('farm_drafts'), farm_drafts)):
        rows = []
        for index, module in enumerate((previous, current)):
            folder = root / str(len(results)) / str(index); folder.mkdir(parents=True)
            rows.append(check(module, folder))
        assert rows == [False, True], (name, rows)
        results.append(dict(check=name, previousPass=rows[0], currentPass=rows[1]))
(RUN / 'negative-controls.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results))
