"""One read-only C24C observation; retain raw metadata and ownership for the audit."""
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
before = kernel.kernel_status()
ownership = kernel.input_status()
store = ObservationStore(RUN / 'readonly.db')
result = store.capture(dict(id=str(uuid.uuid4()), device_id='C24C', platform='instagram', account='unrelated.test.account', caption=''), kernel)
after = kernel.kernel_status()
end = kernel.input_status()
record = dict(before=before, after=after, inputBefore=ownership, inputAfter=end, audit=kernel.audit_log)
(RUN / 'live-observation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
(RUN / 'live-audit.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
if result['state'] == 'observed': (RUN / 'live-frame.png').write_bytes(store.frame(result['id']))
assert all(event['fun'] == '/input/status' for event in kernel.audit_log)
assert all(ownership[k]['generation'] == end[k]['generation'] for k in ownership)
print(json.dumps({'state': result['state'], 'screen': result.get('result', {}).get('screen'), 'freshness': result.get('freshness'),
                  'deliveryAdvanced': result.get('frameEvidence', {}).get('deliveryAdvanced'), 'inputSent': False,
                  'inputGenerationsUnchanged': True, 'review': result['workflowReview']['status']}))
