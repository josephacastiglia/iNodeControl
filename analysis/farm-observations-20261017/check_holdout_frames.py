"""Evaluate additional previously captured frames after freezing the UI rules."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from farm_observations import WindowsOcr, classify

RUN = Path(__file__).resolve().parent
SOURCE = ROOT / 'analysis/farm-platform-drafts-20261017'
# Editor canvases/gallery do not yet have accepted identifying patterns.
labels = {23: 'profile', 24: 'draft_details', 43: 'draft_details', 60: 'draft_details', 64: 'unknown', 65: 'draft_details',
          90: 'unknown', 102: 'unknown', 109: 'unknown', 110: 'unknown', 127: 'draft_details',
          140: 'unknown', 141: 'unknown', 148: 'unknown', 158: 'unknown', 159: 'draft_details', 161: 'draft_details', 162: 'draft_details'}
records = []
for folder in sorted(SOURCE.iterdir()):
    prefix = folder.name.split('-')[0]
    if not folder.is_dir() or not prefix.isdigit() or int(prefix) not in labels: continue
    number = int(prefix); text = WindowsOcr().read((folder / 'after.png').read_bytes())
    (RUN / (folder.name + '-holdout-ocr.json')).write_text(json.dumps(text, ensure_ascii=False, indent=2), encoding='utf-8')
    result = classify(text, {'platform': 'instagram', 'account': 'unrelated.test.account', 'caption': ''})
    records.append({'step': folder.name, 'expected': labels[number], 'actual': result['screen'], 'matched': result['screen'] == labels[number],
                    'inputAllowed': result['automaticInputAllowed'], 'accountAccepted': result['accountStatus'] == 'exact_text_match'})
(RUN / 'holdout-results.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
print(json.dumps({'matched': sum(r['matched'] for r in records), 'total': len(records), 'mismatches': [r for r in records if not r['matched']],
                  'inputsAllowed': sum(r['inputAllowed'] for r in records)}))
