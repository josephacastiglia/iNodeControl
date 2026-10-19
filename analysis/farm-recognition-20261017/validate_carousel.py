"""Saved C24C carousel regression frames; no live capture or phone command."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools'))
from farm_observations import WindowsOcr, classify

results = []
for step, expected, caption in [
    ('39-caption-review', 'draft_details', 'DRAFT ONLY'),
    ('47-open-drafts-library', 'unknown', ''),
    ('50-reopened-caption', 'draft_details', 'iMouse carousel draft test.'),
]:
    file = ROOT / 'analysis/farm-phone-transfer-20261017' / step / 'after.png'
    raw = file.read_bytes()
    text = WindowsOcr().read(raw)
    (RUN / (step + '-ocr.json')).write_text(json.dumps(text, indent=2), encoding='utf-8')
    result = classify(text, dict(platform='instagram', account='unrelated.test.account', caption=caption))
    results.append(dict(step=step, frameSha256=hashlib.sha256(raw).hexdigest(), expected=expected,
                        actual=result['screen'], matched=result['screen'] == expected,
                        captionStatus=result['captionStatus'], accountStatus=result['accountStatus'],
                        automaticInputAllowed=result['automaticInputAllowed']))
(RUN / 'carousel-recognition.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results))
assert all(row['matched'] and not row['automaticInputAllowed'] and row['accountStatus'] != 'exact_text_match' for row in results)
assert results[0]['captionStatus'] == 'needs_review', 'Media lettering must not stand in for the caption.'
