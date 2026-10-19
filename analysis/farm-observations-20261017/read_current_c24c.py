"""One read-only C24C capture. Never invokes input, ownership or navigation methods."""
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from imouse_social_automation import IMouseKernel
from farm_observations import ObservationStore

RUN = Path(__file__).resolve().parent
kernel = IMouseKernel()
store = ObservationStore(RUN / 'read-only-check.db')
request = {'id': str(uuid.uuid4()), 'device_id': 'C24C', 'platform': 'instagram', 'account': 'unrelated.test.account', 'caption': ''}
before = kernel.input_status()
result = store.capture(request, kernel)
after = kernel.input_status()
(RUN / 'live-observation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
(RUN / 'live-ownership.json').write_text(json.dumps({'before': before, 'after': after, 'audit': kernel.audit_log}, indent=2), encoding='utf-8')
if result['state'] == 'observed': (RUN / 'live-frame.png').write_bytes(store.frame(request['id']))
assert all(entry['fun'] == '/input/status' for entry in kernel.audit_log)
assert all(before[key]['generation'] == after[key]['generation'] for key in before)
print(json.dumps({'state': result['state'], 'screen': result.get('result', {}).get('screen'),
                  'freshness': result.get('freshness'), 'phoneInputSent': False,
                  'allGenerationsUnchanged': True, 'reason': result['reason']}))
