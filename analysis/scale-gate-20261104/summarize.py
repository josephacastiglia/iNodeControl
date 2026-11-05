"""Turn a run's record.json (under output/, not committed) into a committed summary without frames.

The summary keeps slots, codes, timings, landing errors and isolation results; it never carries
device IDs (records name phones by slot) or frames.

  python summarize.py ../../output/scale-gate-20261104/gate8-run1 results/gate8-run1.json
"""
import json
import re
import sys
from pathlib import Path

KEEP = ('acquire', 'lease_tests', 'home_1', 'reset', 'screens_start', 'screens_mid', 'screens_end', 'home_2',
        'screens_after_home', 'release', 'dropped', 'calls', 'frames_saved', 'error', 'refused')


def main(folder, target):
    record = json.loads((Path(folder) / 'record.json').read_text(encoding='utf-8'))
    res = record.get('result') or {}
    blob = json.dumps(record)
    if re.search(r'\b[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}\b', blob):
        raise SystemExit('A device-ID-shaped value is in the record; not summarised.')
    out = dict(tool=record['tool'], started=record['started'], finished=record.get('finished'),
               slots=record['slots'], group=record['group'], controls=record['controls'],
               clicks_sent=record['clicks_sent'], swipes_sent=record['swipes_sent'], other_keys_sent=record['other_keys_sent'],
               events=record['events'], preflight=record.get('preflight'), metrics=record.get('metrics'),
               **{k: res[k] for k in KEEP if k in res},
               per_phone=res.get('per_phone'), group_rounds=res.get('group_rounds'),
               renewals=res.get('renewals'), samples=res.get('samples'))
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    Path(target).write_text(json.dumps(out, indent=1), encoding='utf-8')
    print('wrote', target)


if __name__ == '__main__':
    main(*sys.argv[1:3])
