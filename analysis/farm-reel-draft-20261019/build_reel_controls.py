"""Build tools/farm_reel_controls.json from retained C24C frames. Offline only.

Each template is a small crop of a UI control (icon or button), taken from a
frame where the on-screen pointer is elsewhere. Crops contain no account,
caption or personal content. Every template is checked against at least one
other retained frame that shows the same control, and refused on frames that
do not show it. The private frames stay outside Git; this script records their
SHA-256 so a rebuild can be audited.
"""
import base64
import hashlib
import io
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
R = ROOT / 'analysis/farm-platform-drafts-20261017'
P1 = ROOT.parent / 'iMouseXP-2.0-evidence-archive/20261019-farm-new-draft/backend/draft-creations/b8c155e2-1670-4f60-a090-aeff921e162e'

# name: (source frame, box, frames that must match, frames that must not)
SPEC = {
    'reel_row_icon': (R/'155-instagram-create-menu/after.png', (18, 559, 52, 593),
                      [P1/'33-create.png', P1/'verification/02-create.png'], [R/'154-instagram-account-confirm/after.png']),
    'picker_close': (R/'156-instagram-reel-picker/after.png', (26, 82, 58, 115),
                     [R/'157-instagram-select-test-mp4/after.png', R/'163-instagram-save-reel-draft/after.png'],
                     [R/'159-instagram-reel-details/after.png']),
    'drafts_close': (R/'164-instagram-reel-drafts-library/after.png', (22, 66, 57, 102),
                     [R/'167-instagram-keep-verified-reel/after.png'], [R/'166-instagram-reel-playback/after.png']),
    'preview_back': (R/'166-instagram-reel-playback/after.png', (29, 66, 54, 102),
                     [], [R/'164-instagram-reel-drafts-library/after.png', R/'159-instagram-reel-details/after.png']),
    'details_back': (R/'159-instagram-reel-details/after.png', (17, 66, 42, 102),
                     [R/'162-instagram-reel-caption-ok/after.png'], [R/'165-instagram-reel-reopen/after.png']),
    'caption_placeholder': (R/'160-instagram-reel-caption-focus/after.png', (24, 128, 160, 156),
                            [], [R/'161-instagram-reel-caption/after.png']),
    'quicklook_share': (R/'89-video-test-home/before.png', (24, 993, 57, 1031),
                        [R/'83-local-video-share-sheet/before.png'], [R/'81-file-preview-controls/before.png']),
    'safari_download': (R/'78-downloads-menu/before.png', (76, 940, 107, 971),
                        [], [R/'76-video-link-menu/before.png']),
    'next_pill': (R/'157-instagram-select-test-mp4/after.png', (403, 968, 485, 1019),
                  [R/'163-instagram-save-reel-draft/after.png'], [R/'156-instagram-reel-picker/after.png']),
    # Inner disk of a settled selection numeral 1 at Recents cell (0, 1). The
    # recognizer translates it to the chosen cell's circle. 157 is mid-animation.
    'selection_one': (R/'163-instagram-save-reel-draft/after.png', (300, 269, 323, 292),
                      [], [R/'156-instagram-reel-picker/after.png', R/'157-instagram-select-test-mp4/after.png']),
}


def crop(path, box):
    with Image.open(path) as image:
        if image.size != (500, 1080): raise SystemExit(f'{path} is not a 500x1080 frame.')
        return image.convert('RGB').crop(box)


def matches(path, box, reference):
    observed = np.asarray(crop(path, box), dtype=float) / 255
    delta = np.abs(observed - np.asarray(reference, dtype=float) / 255)
    return float(delta.mean()), float((delta.max(axis=2) > 35/255).mean())


def main():
    out, report = {}, {}
    for name, (source, box, positives, negatives) in SPEC.items():
        reference = crop(source, box)
        buffer = io.BytesIO(); reference.save(buffer, 'PNG'); raw = buffer.getvalue()
        out[name] = dict(box=list(box), sha256=hashlib.sha256(raw).hexdigest(), png=base64.b64encode(raw).decode('ascii'),
                         sourceFrameSha256=hashlib.sha256(source.read_bytes()).hexdigest())
        rows = []
        for path, expected in [(p, True) for p in positives] + [(p, False) for p in negatives]:
            mean, changed = matches(path, box, reference)
            accepted = mean < .02 and changed < .04  # Same rule as farm_reel_layout.reel_control.
            rows.append(dict(frame=path.parent.name + '/' + path.name, mean=round(mean, 4), changed=round(changed, 4),
                             accepted=accepted, expected=expected))
            if accepted != expected:
                raise SystemExit(f'{name}: {path} gave {accepted}, expected {expected} (mean {mean:.4f}, changed {changed:.4f}).')
        report[name] = rows
    target = ROOT / 'tools/farm_reel_controls.json'
    target.write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    (Path(__file__).with_name('reel-controls-check.json')).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({name: [r['accepted'] == r['expected'] for r in rows] for name, rows in report.items()}))


if __name__ == '__main__':
    sys.exit(main())
