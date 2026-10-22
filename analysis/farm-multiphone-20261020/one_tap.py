"""One supervised navigation tap on a window's phone, for backing out of a screen an earlier run left.

A fresh frame must contain every --require label (whole OCR lines, case-insensitive); the
start-screen tap guard then refuses points near publish/share/delete labels and decides on a
newer frame matching the recognized one in the --only regions. A fresh after-frame is saved and
its text printed. One lease, released at the end. Never use it for an app's own workflow step.

  python one_tap.py --config windows/x-slot17/creation-config.json --folder windows/x-slot17/nav-1 \
      --x 57 --y 85 --purpose cancel-empty-composer --require "Cancel|Everyone can reply" --only "0,60,500,110"
"""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'tools'))
from farm_carousel_inspection import InspectionStopped  # noqa: E402
from farm_draft_runs import phone_of  # noqa: E402
from farm_start_screen import StartScreen  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', required=True); p.add_argument('--folder', required=True)
    p.add_argument('--x', type=int, required=True); p.add_argument('--y', type=int, required=True)
    p.add_argument('--purpose', required=True); p.add_argument('--require', required=True, help='labels, | separated')
    p.add_argument('--only', default='0,60,500,110|0,960,500,1030', help='compared regions, | separated')
    a = p.parse_args()
    config = json.loads(Path(a.config).read_text(encoding='utf-8'))
    s = StartScreen(a.folder, phone=phone_of(config))
    only = tuple(tuple(int(v) for v in part.split(',')) for part in a.only.split('|'))
    s.tokens = s.kernel.acquire([s.phone.board], 30000)
    try:
        s.command('/mouse/reset', 'initial_pointer_reset')
        raw, text, _, _ = s.fresh('before')
        lines = {l['text'].strip().casefold() for l in text.get('lines', [])}
        missing = [label for label in a.require.split('|') if label.casefold() not in lines]
        if missing: raise InspectionStopped(f'Required labels missing: {missing}; nothing was tapped.')
        s.tap(raw, text, (a.x, a.y), 'supervised', a.purpose, only=only)
        s.pause(1.5)
        raw, text, _, _ = s.fresh('after')
        s.record['state'] = 'tapped'
        print(json.dumps(dict(state='tapped', after=[l['text'] for l in text.get('lines', [])][:30])))
    except InspectionStopped as stop:
        s.record['state'] = 'stopped'; print(json.dumps(dict(state='stopped', error=str(stop))))
    finally:
        s.kernel.release(s.tokens); s.save()


if __name__ == '__main__':
    main()
