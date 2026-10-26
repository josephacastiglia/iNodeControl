"""Supervised probe: why does the switcher swipe not close an app on one phone? (slot 16, 26 Oct)

close_app.py's swipe (x 390, y 650 -> 120, 250 ms) closed YouTube on check 4 but did nothing on
checks 6-7 after a kernel restart. This tries one variant per call: optional pointer reset right
before the swipe, a duration, and a start y. It opens the switcher, requires the app's card label,
swipes once, reads a fresh frame, and always leaves with Home. Closing an app loses nothing saved.

  python switcher_probe.py --config windows/youtube-slot16/creation-config.json --folder windows/youtube-slot16/swipe-1 \
      --app YouTube --reset --duration 400
"""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'tools'))
from close_app import BASE, card_by_content, labels, named  # noqa: E402
from farm_carousel_inspection import InspectionStopped  # noqa: E402
from farm_draft_runs import phone_of  # noqa: E402
from farm_start_screen import StartScreen  # noqa: E402
from identify_phone import post  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', required=True); p.add_argument('--folder', required=True); p.add_argument('--app', required=True)
    p.add_argument('--reset', action='store_true', help='/mouse/reset right before the swipe')
    p.add_argument('--duration', type=int, default=250); p.add_argument('--y1', type=int, default=650)
    p.add_argument('--y2', type=int, default=120)
    a = p.parse_args()
    s = StartScreen(a.folder, phone=phone_of(json.loads(Path(a.config).read_text(encoding='utf-8'))))
    s.record.update(purpose='switcher-swipe-probe', app=a.app, variant=dict(reset=a.reset, duration=a.duration, y1=a.y1, y2=a.y2))
    s.tokens = s.kernel.acquire([s.phone.board], 30000)
    out = {}

    def raw(fun, purpose, **data):
        item = dict(fun=fun, purpose=purpose, data=data, state='outcome_unknown', direct=True)
        s.record['commands'].append(item); s.record['phoneInput'] = True; s.save()
        got = post(BASE, fun, dict(id=s.phone.device_id, token=s.tokens[s.phone.board], **data))
        item['state'] = 'answered' if got.get('code') == 0 else 'failed'; s.save()
        if got.get('code') != 0: raise InspectionStopped(f'{purpose}: {got}')
    try:
        s.command('/mouse/reset', 'initial_pointer_reset')
        raw('/key/sendkey', 'open-app-switcher', fn_key='AppSwitch')
        s.pause(1.5)
        _, text, _, _ = s.fresh('switcher')
        found = [x for name, x in labels(text) if named(name, a.app)] or card_by_content(text, a.app)
        s.record['labels'] = [name for name, _ in labels(text)]
        if len(found) != 1: raise InspectionStopped(f'{a.app} is not one switcher card ({s.record["labels"]}); nothing was swiped.')
        x = max(60, min(440, found[0] + 45))
        if a.reset: s.command('/mouse/reset', 'reset-before-swipe')
        raw('/mouse/swipe', 'close-' + a.app.casefold(), x1=x, y1=a.y1, x2=x, y2=a.y2, duration=a.duration)
        s.pause(1.5)
        _, text, _, _ = s.fresh('after-swipe')
        after = [name for name, _ in labels(text)]
        closed = not any(named(name, a.app) for name in after) and not card_by_content(text, a.app)
        out = dict(state='closed' if closed else 'not_closed', x=x, before=s.record['labels'], after=after)
    except InspectionStopped as stop:
        out = dict(state='stopped', error=str(stop))
    finally:
        try: s.command('/key/sendkey', 'home-leaves-switcher', fn_key='Home')
        finally: s.kernel.release(s.tokens); s.record.update(result=out); s.save()
    print(json.dumps(out))


if __name__ == '__main__':
    main()
