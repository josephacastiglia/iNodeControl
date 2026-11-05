"""Print a run's headline numbers from output/scale-gate-20261104/<run>/record.json (no frames)."""
import json
import sys
from pathlib import Path

folder = Path(sys.argv[1])
r = json.loads((folder / 'record.json').read_text(encoding='utf-8'))
res, m = r['result'], r['metrics']
print('events', r['events'])
for k in ('acquire', 'lease_tests', 'home_1', 'reset', 'home_2', 'release', 'dropped', 'error'):
    print(k, res.get(k))
for k in ('screens_start', 'screens_mid', 'screens_end', 'screens_after_home'):
    if res.get(k):
        print(k, 'max changed', max(v['changed'] for v in res[k].values()), 'max age', max(v['age_ms'] for v in res[k].values()))
for k in ('per_phone', 'group'):
    print(k, json.dumps(m[k]))
for k in ('frame_age_ms', 'frame_age_over_1500', 'cpu', 'kernel_status_ms', 'kernel_errors', 'sampled_age_ms', 'other_receivers_live', 'renewals'):
    print(k, m[k])
for row in (res.get('per_phone') or []) + (res.get('group_rounds') or []):
    t = row['target']
    bad = ' '.join(f"{s}:{(p['dot'][0] - t[0], p['dot'][1] - t[1]) if p.get('dot') else None}/{p.get('visible_ms')}"
                   for s, p in row['phones'].items() if not p.get('control') and not p.get('landed'))
    if bad:
        print('MISS', row['label'], t, row['rtt_ms'], bad)
print(r['started'], r.get('finished'))
