"""Replay earlier private OCR and production frame evidence; no network or desktop."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from farm_observations import classify
from farm_frame_evidence import delivery_evidence

RUN = Path(__file__).resolve().parent
PRIOR = ROOT / 'analysis/farm-observations-20261017'
results = []
for group, file_name in [('development', 'saved-state-results.json'), ('additional', 'holdout-results.json')]:
    for item in json.loads((PRIOR / file_name).read_text(encoding='utf-8')):
        if group == 'development':
            file, expected = item['frame'], item['expectedState']
        else:
            file, expected = item['step'] + '-holdout-ocr.json', item['expected']
            if item['step'].startswith('23-'): expected = 'draft_library'
            if item['step'].startswith('161-'): expected = 'caption_editor'
        text = json.loads((PRIOR / file).read_text(encoding='utf-8'))
        result = classify(text, {'platform': 'instagram', 'account': 'unrelated.test.account', 'caption': ''})
        results.append({'group': group, 'file': file, 'expected': expected, 'actual': result['screen'],
                        'matched': expected == result['screen'], 'accountAccepted': result['accountStatus'] == 'exact_text_match',
                        'automaticInputAllowed': result['automaticInputAllowed']})
(RUN / 'recognition-replay.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
frames = []
for row in json.loads((RUN / 'production-frame-evidence.json').read_text(encoding='utf-8')):
    evidence = delivery_evidence(row['before'], row['headers'], row['after'], row['elapsedMs'])
    frames.append({'name': row['name'], 'expected': row['expected'], 'actual': evidence['freshness'], 'evidence': evidence})
    assert row['expected'] == evidence['freshness'], row['name']
(RUN / 'production-frame-results.json').write_text(json.dumps(frames, indent=2), encoding='utf-8')
print(json.dumps({'recognized': sum(r['matched'] for r in results), 'total': len(results),
                  'mismatches': [r for r in results if not r['matched']], 'wrongAccountsAccepted': sum(r['accountAccepted'] for r in results),
                  'productionFrameCases': len(frames), 'phoneCalls': 0}))
