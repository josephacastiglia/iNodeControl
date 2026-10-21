"""Build tools/farm_youtube_controls.json from retained C24C frames, then check it. Offline only.

Each template is a small crop of a YouTube control (icon, button or badge) from a
retained 17 Oct frame where the supervised pointer is elsewhere. Crops contain
no account, title or personal content (the channel avatar is never cropped).
After writing, every template is checked with the production comparison in
tools/farm_youtube_layout.py: it must accept the other retained frames that
show the control and refuse frames that do not. The private frames stay
outside Git; this script records their SHA-256.
"""
import base64
import hashlib
import io
import json
from pathlib import Path
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
R = ROOT / 'analysis/farm-platform-drafts-20261017'
sys.path.insert(0, str(ROOT / 'tools'))


def f(step, which='after'):
    return R / step / (which + '.png')


HOME, HOME_SAVED, HOME_KEPT, HOME_FINAL = (f('136-youtube-after-operator'), f('145-youtube-save-video-draft'),
                                           f('150-youtube-resave-verified-video'), f('151-final-home', 'before'))
OLD_HOME, YOU = f('50-youtube-loaded'), f('51-youtube-account')
CAMERA = [f('137-youtube-create-video'), f('146-youtube-draft-route'), f('147-youtube-video-draft-library', 'before'), f('52-youtube-create')]
PICKER, SELECTED = f('138-youtube-mp4-picker'), f('139-youtube-select-mp4')
# The supervised pointer sat on the selection badge in 139/after and 140/before; it
# had moved to Next when 140/pointer and 140/immediate were captured.
SELECTED_CLEAN = [f('140-youtube-mp4-trim-review', 'pointer'), f('140-youtube-mp4-trim-review', 'immediate')]
TRIM = [f('140-youtube-mp4-trim-review'), f('141-youtube-mp4-editor', 'before')]
EDITOR = [f('141-youtube-mp4-editor'), f('142-youtube-video-details', 'before'), f('148-youtube-video-draft-reopen'),
          f('149-youtube-reopened-caption', 'before')]
DETAILS = [f('142-youtube-video-details'), f('143-youtube-video-caption-focus'), f('144-youtube-video-caption'),
           f('145-youtube-save-video-draft', 'before'), f('149-youtube-reopened-caption')]
DRAFTS = [f('147-youtube-video-draft-library'), f('148-youtube-video-draft-reopen', 'before')]

# name: (source frame, box, frames that must match, frames that must not)
SPEC = {
    'yt_home_logo': (HOME, (18, 70, 136, 100), [HOME_SAVED, HOME_KEPT, HOME_FINAL], [EDITOR[0], DETAILS[0], DRAFTS[0], PICKER]),
    'yt_home_actions': (HOME, (395, 65, 490, 105), [HOME_SAVED, HOME_KEPT, HOME_FINAL], [DETAILS[0], DRAFTS[0], CAMERA[0]]),
    'yt_nav_home': (HOME, (42, 999, 85, 1042), [HOME_SAVED, HOME_KEPT, HOME_FINAL], [OLD_HOME, YOU, DETAILS[0], CAMERA[0]]),
    'yt_nav_create': (HOME, (290, 999, 333, 1042), [HOME_SAVED, HOME_KEPT, HOME_FINAL], [OLD_HOME, YOU, DETAILS[0], CAMERA[0]]),
    'yt_camera_record': (CAMERA[0], (228, 823, 272, 867), CAMERA[1:], [PICKER, HOME, EDITOR[0]]),
    'yt_badge_one': (SELECTED_CLEAN[0], (126, 305, 157, 336), SELECTED_CLEAN[1:], [PICKER, SELECTED, TRIM[0]]),
    'yt_picker_next': (SELECTED, (255, 968, 480, 1025), [f('140-youtube-mp4-trim-review', 'before')], [PICKER, EDITOR[0], TRIM[0]]),
    'yt_trim_done': (TRIM[0], (412, 985, 486, 1027), TRIM[1:], [SELECTED, EDITOR[0], DETAILS[0]]),
    # Left of the pill's end, where the supervised pointer rested after Done.
    'yt_editor_next': (EDITOR[2], (262, 984, 425, 1028), [EDITOR[0], EDITOR[1], EDITOR[3]], [SELECTED, TRIM[0], DETAILS[0]]),
    'yt_details_save': (DETAILS[1], (18, 968, 242, 1024), [DETAILS[0], *DETAILS[2:]], [EDITOR[0], HOME_SAVED, SELECTED]),
    'yt_details_upload': (DETAILS[1], (258, 968, 484, 1024), [DETAILS[0], *DETAILS[2:]], [EDITOR[0], HOME_SAVED, SELECTED]),
    'yt_details_back': (DETAILS[1], (12, 70, 40, 100), [DETAILS[0], *DETAILS[2:]], [EDITOR[0], HOME, DRAFTS[0]]),
    'yt_drafts_header': (DRAFTS[0], (28, 60, 145, 95), DRAFTS[1:], [DETAILS[0], HOME, CAMERA[0]]),
}


def crop(path, box):
    with Image.open(path) as image:
        if image.size != (500, 1080): raise SystemExit(f'{path} is not a 500x1080 frame.')
        return image.convert('RGB').crop(box)


def main():
    out = {}
    for name, (source, box, _, _) in SPEC.items():
        buffer = io.BytesIO(); crop(source, box).save(buffer, 'PNG'); raw = buffer.getvalue()
        out[name] = dict(box=list(box), sha256=hashlib.sha256(raw).hexdigest(), png=base64.b64encode(raw).decode('ascii'),
                         sourceFrameSha256=hashlib.sha256(source.read_bytes()).hexdigest())
    target = ROOT / 'tools/farm_youtube_controls.json'
    target.write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    import farm_youtube_layout as yl   # Checks below use the production comparison and modes.
    report, failures = {}, []
    for name, (source, box, positives, negatives) in SPEC.items():
        rows = []
        for path, expected in [(source, True)] + [(p, True) for p in positives] + [(p, False) for p in negatives]:
            accepted = yl.present(path.read_bytes(), name)
            rows.append(dict(frame=path.parent.name + '/' + path.name, accepted=accepted, expected=expected))
            if accepted != expected: failures.append(f'{name}: {path.parent.name}/{path.name} gave {accepted}')
        report[name] = dict(mode=yl.MODES[name], checks=rows)
    (Path(__file__).with_name('youtube-controls-check.json')).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if failures:
        target.unlink()
        raise SystemExit('\n'.join(failures))
    print(json.dumps({name: all(r['accepted'] == r['expected'] for r in value['checks']) for name, value in report.items()}))


if __name__ == '__main__':
    sys.exit(main())
