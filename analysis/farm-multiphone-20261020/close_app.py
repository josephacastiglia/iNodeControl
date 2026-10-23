"""Closes one app from the iOS app switcher on a window's phone: a stuck screen no tap can leave.

YouTube on slot 16 stayed on its reopened draft's 'Processing' overlay for over half an hour and
ignored its back arrow (23 Oct). Closing the app leaves the saved draft in YouTube's Drafts; nothing
is saved, discarded or posted. Steps: App Switcher (Fn+Up); a fresh frame must show the app's own
name once in the card label row (the app last used is the front card, at the right); one swipe up
on that card; a fresh frame must no longer show that name; Home. One lease, released at the end.

The farm's creation transport allows only Home, Enter, Escape and bounded text, so the switcher key
and the swipe go to the kernel directly under the same lease, as auto_connect.py sends ControlBar.

  python close_app.py --config windows/youtube-slot16/creation-config.json --folder windows/youtube-slot16/close-1 --app YouTube
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
from identify_phone import post  # noqa: E402

BASE = 'http://127.0.0.1:9916/api'

LABELS = (95, 160)   # The switcher's card labels (icon and app name) sit in this band (slot 16, 23 Oct).


def labels(text):
    """(name, left x) of each card label in the label band."""
    return [(line['text'].strip(), min(w['x'] for w in line['words'])) for line in text.get('lines', [])
            if line.get('words') and LABELS[0] <= min(w['y'] for w in line['words']) <= LABELS[1]]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', required=True); p.add_argument('--folder', required=True); p.add_argument('--app', required=True)
    a = p.parse_args()
    config = json.loads(Path(a.config).read_text(encoding='utf-8'))
    s = StartScreen(a.folder, phone=phone_of(config))
    s.record.update(purpose='close-stuck-app', app=a.app)
    s.tokens = s.kernel.acquire([s.phone.board], 30000)
    def raw(fun, purpose, **data):
        item = dict(fun=fun, purpose=purpose, data=data, state='outcome_unknown', direct=True)
        s.record['commands'].append(item); s.record['phoneInput'] = True; s.save()
        got = post(BASE, fun, dict(id=s.phone.device_id, token=s.tokens[s.phone.board], **data))
        item['state'] = 'answered' if got.get('code') == 0 else 'failed'; s.save()
        if got.get('code') != 0: raise InspectionStopped(f'{purpose}: {got}')
    try:
        raw('/key/sendkey', 'open-app-switcher', fn_key='AppSwitch')
        s.pause(1.5)
        _, text, _, _ = s.fresh('switcher')
        found = [x for name, x in labels(text) if name == a.app]
        s.record['labels'] = [name for name, _ in labels(text)]
        if len(found) != 1: raise InspectionStopped(f'{a.app} is not one switcher card ({s.record["labels"]}); nothing was swiped.')
        x = max(60, min(440, found[0] + 45))   # The card's middle, right of its icon and name.
        raw('/mouse/swipe', 'close-' + a.app.casefold(), x1=x, y1=650, x2=x, y2=120, duration=250)
        s.pause(1.5)
        _, text, _, _ = s.fresh('after-swipe')
        s.record['after'] = [name for name, _ in labels(text)]
        if a.app in s.record['after']: raise InspectionStopped(f'{a.app} is still the middle card; no further input.')
        s.command('/key/sendkey', 'home-after-close', fn_key='Home')
        s.record['state'] = 'closed'
        print(json.dumps(dict(state='closed', after=s.record['after'])))
    except InspectionStopped as stop:
        s.record['state'] = 'stopped'; print(json.dumps(dict(state='stopped', error=str(stop))))
        if any(c['purpose'] == 'open-app-switcher' for c in s.record['commands']):
            s.command('/key/sendkey', 'home-leaves-switcher', fn_key='Home')   # Leaves the switcher; closes nothing.
    finally:
        s.kernel.release(s.tokens); s.save()


if __name__ == '__main__':
    main()
