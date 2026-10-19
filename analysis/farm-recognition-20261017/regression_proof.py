"""Compare the prior committed observer with the candidate using only synthetic data."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import farm_observations as new
from test_farm_observations import ReadOnlyKernel, PROFILE

old = types.ModuleType('prior_observer')
source = subprocess.check_output(['git', '-c', 'safe.directory=' + ROOT.as_posix(), 'show', 'aac6089:tools/farm_observations.py'])
exec(compile(source, 'aac6089:tools/farm_observations.py', 'exec'), old.__dict__)
report = {}
for name, module in [('prior', old), ('candidate', new)]:
    with tempfile.TemporaryDirectory(prefix='observer-regression-') as directory:
        now = [1000.0]
        class Ocr:
            def read(self, raw): now[0] += 2; return PROFILE
        options = dict(clock=lambda: now[0])
        if name == 'candidate': options['monotonic'] = lambda: now[0]
        store = module.ObservationStore(Path(directory) / 'store.db', Ocr(), **options)
        request = dict(id=str(uuid.uuid4()), device_id='C24C', platform='tiktok', account='test.account', caption='')
        result = store.capture(request, ReadOnlyKernel())
        restart = module.ObservationStore(store.path, Ocr(), **options).get(request['id'])
        report[name] = dict(afterTwoSecondRecognition=result['freshness'], restartFreshness=restart['freshness'], restartExpired=restart['expired'])
assert report['prior']['afterTwoSecondRecognition'] == 'recent'
assert report['candidate']['afterTwoSecondRecognition'] == 'stale'
assert report['prior']['restartExpired'] is False
assert report['candidate']['restartExpired'] is True
(Path(__file__).parent / 'regression-proof.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))
