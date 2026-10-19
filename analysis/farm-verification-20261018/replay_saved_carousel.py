"""Compare earlier C24C captures with the exact earlier export; no phone/network calls."""
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools'))
from farm_observations import WindowsOcr, classify
from farm_draft_verification import media_comparison, caption_comparison

prior = ROOT / 'analysis/farm-phone-transfer-20261017'
with zipfile.ZipFile(prior / 'test-carousel.zip') as files:
    draft = json.loads(files.read('manifest.json'))
    assets = [files.read(asset['file']) for asset in draft['assets']]
assert all(hashlib.sha256(raw).hexdigest() == asset['sha256'] for raw, asset in zip(assets, draft['assets']))
results = []
for step in ('05-instagram-profile', '43-caption-ok', '47-open-drafts-library', '50-reopened-caption'):
    frame = (prior / step / 'after.png').read_bytes()
    text = WindowsOcr().read(frame)
    (RUN / (step + '-ocr.json')).write_text(json.dumps(text, indent=2), encoding='utf-8')
    # Exact handle authorized for the earlier supervised test; raw OCR stays outside Git.
    result = classify(text, dict(platform='instagram', account='xs.halle.xo', caption=draft['caption']))
    layout = 'draft_library_candidate' if step.startswith('47-') else result.get('layout')
    media = media_comparison(frame, assets, layout)
    caption = caption_comparison(text, draft['caption']) if layout == 'carousel_details' else {'status': 'not_applicable'}
    results.append(dict(step=step, frameSha256=hashlib.sha256(frame).hexdigest(), screen=result['screen'],
                        accountStatus=result['accountStatus'], media=media, caption=caption))
(RUN / 'saved-carousel-results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
for row in results:
    print(json.dumps(dict(step=row['step'], screen=row['screen'], account=row['accountStatus'], media=row['media'], caption=row['caption']['status'])))
assert results[-1]['media']['matchedIndex'] == 1
assert results[-1]['caption']['status'] == 'exact_visible_lines'
assert results[2]['media']['matchedIndex'] is None  # The real library preview is not a sufficiently close full-image match.
print('Historical partial evidence only: remaining slide views, account-after and paired freshness are absent. No saved-draft acceptance.')
