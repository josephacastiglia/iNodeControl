"""Build tools/farm_tiktok_controls.json from retained C24C frames. Offline only.

Each template is a small crop of a TikTok UI control (icon or button), taken
from a frame where the on-screen pointer is elsewhere. Crops contain no
account, caption or personal content. Every template is checked against other
retained frames that show the same control, and refused on frames that do not.
The private frames stay outside Git; this script records their SHA-256.
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


def f(step, which='after'):
    return R / step / (which + '.png')


# name: (source frame, box, frames that must match, frames that must not)
SPEC = {
    'tt_nav_create': (f('107-tiktok-video-profile'), (226, 991, 275, 1028),
                      [f('108-tiktok-video-library', 'before')], [f('106-tiktok-save-video-draft'), f('95-tiktok-loaded')]),
    'tt_picker_close': (f('100-tiktok-settled-gallery-click'), (20, 76, 50, 106),
                        [f('101-tiktok-select-test-video'), f('101-tiktok-select-test-video', 'before')],
                        [f('103-tiktok-video-details'), f('108-tiktok-video-library')]),
    'tt_next_disabled': (f('100-tiktok-settled-gallery-click'), (258, 984, 482, 1032),
                         [f('101-tiktok-select-test-video', 'before')], [f('101-tiktok-select-test-video')]),
    'tt_picker_next': (f('101-tiktok-select-test-video'), (258, 984, 482, 1032),
                       [f('102-tiktok-video-editor', 'before')],
                       [f('100-tiktok-settled-gallery-click'), f('110-tiktok-remove-suggested-sound')]),
    'tt_editor_next': (f('110-tiktok-remove-suggested-sound'), (258, 984, 482, 1032),
                       [f('109-tiktok-video-reopen'), f('111-tiktok-video-caption-verify', 'before')],
                       [f('101-tiktok-select-test-video'), f('103-tiktok-video-details')]),
    'tt_editor_back': (f('110-tiktok-remove-suggested-sound'), (22, 98, 50, 132),
                       [f('109-tiktok-video-reopen'), f('102-tiktok-video-editor')], [f('103-tiktok-video-details')]),
    'tt_sound_note': (f('110-tiktok-remove-suggested-sound'), (194, 104, 212, 126),
                      [f('111-tiktok-video-caption-verify', 'before')],
                      [f('102-tiktok-video-editor'), f('109-tiktok-video-reopen')]),
    'tt_sound_remove': (f('109-tiktok-video-reopen'), (328, 104, 352, 128),
                        [f('110-tiktok-remove-suggested-sound', 'before')],
                        [f('110-tiktok-remove-suggested-sound'), f('102-tiktok-video-editor')]),
    # The same white-page back chevron on details (fresh or reopened) and on the drafts list.
    'tt_back': (f('103-tiktok-video-details'), (16, 70, 44, 100),
                [f('104-tiktok-video-caption-focus'), f('105-tiktok-video-caption'), f('106-tiktok-save-video-draft', 'before'),
                 f('108-tiktok-video-library'), f('111-tiktok-video-caption-verify'), f('112-tiktok-resave-silent-video')],
                [f('102-tiktok-video-editor'), f('107-tiktok-video-profile'), f('100-tiktok-settled-gallery-click')]),
    'tt_details_drafts': (f('111-tiktok-video-caption-verify'), (18, 979, 244, 1032),
                          [f('103-tiktok-video-details'), f('104-tiktok-video-caption-focus'), f('105-tiktok-video-caption')],
                          [f('101-tiktok-select-test-video'), f('110-tiktok-remove-suggested-sound')]),
    # Settled numeral-1 badge at the selected tile's circle; translated by the recognizer.
    'tt_badge_one': (f('101-tiktok-select-test-video'), (466, 665, 492, 691),
                     [f('102-tiktok-video-editor', 'before')], [f('100-tiktok-settled-gallery-click')]),
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
    out, report, failures = {}, {}, []
    for name, (source, box, positives, negatives) in SPEC.items():
        reference = crop(source, box)
        buffer = io.BytesIO(); reference.save(buffer, 'PNG'); raw = buffer.getvalue()
        out[name] = dict(box=list(box), sha256=hashlib.sha256(raw).hexdigest(), png=base64.b64encode(raw).decode('ascii'),
                         sourceFrameSha256=hashlib.sha256(source.read_bytes()).hexdigest())
        rows = []
        for path, expected in [(p, True) for p in positives] + [(p, False) for p in negatives]:
            mean, changed = matches(path, box, reference)
            accepted = mean < .02 and changed < .04  # Same rule as farm_tiktok_layout.control.
            rows.append(dict(frame=path.parent.name + '/' + path.name, mean=round(mean, 4), changed=round(changed, 4),
                             accepted=accepted, expected=expected))
            if accepted != expected: failures.append(f'{name}: {path.parent.name}/{path.name} gave {accepted} (mean {mean:.4f}, changed {changed:.4f})')
        report[name] = rows
    if failures: raise SystemExit('\n'.join(failures))
    (ROOT / 'tools/farm_tiktok_controls.json').write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    (Path(__file__).with_name('tiktok-controls-check.json')).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({name: [r['accepted'] == r['expected'] for r in rows] for name, rows in report.items()}))


if __name__ == '__main__':
    sys.exit(main())
