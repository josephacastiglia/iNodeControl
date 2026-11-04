"""Discards one unsaved edit a stopped run left, on the operator's explicit approval for that phone.

The tap guards refuse 'Discard' everywhere, which is right inside a workflow. Leaving a stopped
run's unsaved editor or composer still needs it (the Reel equivalent is 'Start over', 22 Oct).
The operator approved this on 23 Oct ("Discard both", then "you can discard whatever you like");
nothing saved or posted is affected and the test video stays in Photos.

Only these recognized dialogs are accepted, each from its exact labels in order:
  tiktok   the editor's back menu:   Discard, Save draft
  x        the composer's Cancel sheet: Save to drafts, Discard, Keep editing; or, as slot 17's X shows it
           since 4 Nov, only Save to drafts above Discard
  youtube  Add details' back prompt: 'Discard changes?' over Cancel and Discard side by side
The target is the centre of the one 'Discard' line, decided on a newer fresh frame that matches.

  python discard_leftover.py --config windows/tiktok-slot20/creation-config.json --folder windows/tiktok-slot20/nav-3 \
      --dialog tiktok --approval "operator 23 Oct: Discard both"
"""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'tools'))
from farm_carousel_inspection import InspectionStopped  # noqa: E402
from farm_draft_runs import phone_of  # noqa: E402
from farm_start_screen import MAX_AGE_MS, StartScreen  # noqa: E402

DIALOGS = {'tiktok': ('discard', 'save draft'), 'x': ('save to drafts', 'discard', 'keep editing'),
           'youtube': ('discard changes?', 'cancel', 'discard')}
# Shorter layouts of the same dialog, used only when the longer one's extra label is absent.
SHORT = {'x': (('save to drafts', 'discard'), 'keep editing')}   # Slot 17, 4 Nov: no Keep editing.


def discard_target(text, dialog):
    """Centre of the one 'Discard' line when the dialog's labels each appear once, in reading order
    (each next label below the last, or on its row to the right)."""
    rows = {}
    for line in text.get('lines', []):
        words = line.get('words') or []
        if not words: continue
        box = (min(w['x'] for w in words), min(w['y'] for w in words), max(w['x']+w['width'] for w in words), max(w['y']+w['height'] for w in words))
        rows.setdefault(line['text'].strip().casefold(), []).append(box)
    labels = DIALOGS[dialog]
    if dialog in SHORT and not rows.get(SHORT[dialog][1]): labels = SHORT[dialog][0]
    if any(len(rows.get(label, [])) != 1 for label in labels):
        raise InspectionStopped(f'The {dialog} discard dialog is not shown exactly; nothing was tapped.')
    boxes = [rows[label][0] for label in labels]
    if not all(a[1] < b[1]-5 or (abs(a[1]-b[1]) <= 5 and a[2] < b[0]) for a, b in zip(boxes, boxes[1:])):
        raise InspectionStopped(f'The {dialog} dialog rows are out of order; nothing was tapped.')
    left, top, right, bottom = rows['discard'][0]
    return (round((left+right)/2), round((top+bottom)/2)), (left-10, top-10, right+10, bottom+10)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', required=True); p.add_argument('--folder', required=True)
    p.add_argument('--dialog', required=True, choices=sorted(DIALOGS)); p.add_argument('--approval', required=True)
    a = p.parse_args()
    config = json.loads(Path(a.config).read_text(encoding='utf-8'))
    s = StartScreen(a.folder, phone=phone_of(config))
    s.record.update(purpose='discard-unsaved-leftover', dialog=a.dialog, approval=a.approval)
    s.tokens = s.kernel.acquire([s.phone.board], 30000)
    try:
        s.command('/mouse/reset', 'initial_pointer_reset')
        raw, text, _, _ = s.fresh('before')
        point, region = discard_target(text, a.dialog)
        taken, age = s.confirm_unchanged(raw, 'discard_dialog', (region,))
        if (s.clock() - taken) * 1000 + age > MAX_AGE_MS:
            raise InspectionStopped('The discard decision aged past the limit; nothing was tapped.')
        s.command('/mouse/click', 'discard-unsaved-leftover', x=point[0], y=point[1], button=1)
        s.command('/mouse/move', 'park_after_answered_action', x=480, y=300)
        s.pause(1.5)
        raw, text, _, _ = s.fresh('after')
        s.record['state'] = 'tapped'
        print(json.dumps(dict(state='tapped', point=point, after=[l['text'] for l in text.get('lines', [])][:30])))
    except InspectionStopped as stop:
        s.record['state'] = 'stopped'; print(json.dumps(dict(state='stopped', error=str(stop))))
    finally:
        s.kernel.release(s.tokens); s.save()


if __name__ == '__main__':
    main()
