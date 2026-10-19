"""Read existing evidence only. Private OCR stays in the local evidence folder."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from farm_observations import WindowsOcr

run = Path(__file__).resolve().parent
source = ROOT / 'analysis/farm-platform-drafts-20261017'
selected = {7, 31, 51, 84, 87, 107, 108, 111, 124, 125, 132, 147, 149, 154, 164, 165, 166, 168}
results = []
for folder in sorted(source.iterdir()):
    if not folder.is_dir() or not folder.name.split('-')[0].isdigit() or int(folder.name.split('-')[0]) not in selected:
        continue
    result = WindowsOcr().read((folder / 'after.png').read_bytes())
    (run / (folder.name + '-ocr.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    results.append({'step': folder.name, 'lines': [line['text'] for line in result['lines']]})
(run / 'saved-frame-text.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'framesRead': len(results), 'phoneRequests': 0}))
