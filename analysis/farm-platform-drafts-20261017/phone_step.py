"""Operator-observed C24C steps, not an unattended Instagram workflow.

Every invocation requires a live frame and a free C24C lease, saves before/after
frames, then releases in finally. No PC control or other targets. Home is only
used after observing that no editable field has focus (vendor Home sends Tab).
"""
import argparse
import io
import json
from pathlib import Path
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from imouse_social_automation import IMouseKernel
from PIL import Image

p = argparse.ArgumentParser()
p.add_argument('label')
p.add_argument('action', choices=['frame', 'tap', 'settledtap', 'text', 'enter', 'escape', 'home', 'swipe', 'hold'])
p.add_argument('values', nargs='*')
a = p.parse_args()
if not a.label.replace('-', '').replace('_', '').isalnum():
    p.error('Use a simple unique label')
folder = Path(__file__).resolve().parent / a.label
folder.mkdir(exist_ok=False)
k = IMouseKernel()
record = {'started': datetime.now(timezone.utc).isoformat(), 'action': a.action, 'values': a.values}
tokens = {}

def frame(name):
    raw, headers = k.shot('C24C')
    Image.open(io.BytesIO(raw)).save(folder / (name + '.png'))
    return headers

try:
    record['preflight'] = k.preflight_phone('C24C')
    record['beforeHeaders'] = frame('before')
    if a.action != 'frame':
        tokens = k.acquire(['C24C'])
        def send(fun, **data):
            k.renew_if_needed(tokens)
            result = k.send('C24C', tokens['C24C'], fun, **data)
            record.setdefault('commands', []).append({'fun': fun, 'data': data, 'result': result})
        if a.action in ('tap', 'settledtap', 'hold'):
            x, y = map(int, a.values)
            if not (0 <= x < 500 and 0 <= y < 1080):
                raise ValueError('Outside C24C frame')
            send('/mouse/reset')
            if a.action == 'settledtap':
                send('/mouse/move', x=x, y=y)
                time.sleep(0.6)
                record['pointerHeaders'] = frame('pointer')
                send('/mouse/click', x=x, y=y, button=1)
            elif a.action == 'tap':
                send('/mouse/click', x=x, y=y, button=1)
            else:
                send('/mouse/move', x=x, y=y)
                time.sleep(0.6)
                send('/mouse/down', button=1)
                time.sleep(1.1)
                send('/mouse/up', button=1)
        elif a.action == 'text':
            text = a.values[0]
            if len(text) > 200 or any(not 32 <= ord(c) <= 126 for c in text):
                raise ValueError('This observed test only supports 200 printable ASCII characters')
            for start in range(0, len(text), 12):
                send('/key/sendkey', key=text[start:start+12])
        elif a.action == 'enter':
            send('/key/sendkey', fn_key='Enter')
        elif a.action == 'escape':
            send('/key/sendkey', fn_key='Escape')
        elif a.action == 'home':
            send('/key/sendkey', fn_key='Home')
        elif a.action == 'swipe':
            x1,y1,x2,y2 = map(int,a.values)
            if not all(0 <= x < 500 for x in (x1,x2)) or not all(0 <= y < 1080 for y in (y1,y2)):
                raise ValueError('Outside C24C frame')
            send('/mouse/reset')
            send('/mouse/swipe', x1=x1,y1=y1,x2=x2,y2=y2,duration=450)
        record['immediateHeaders'] = frame('immediate')
        time.sleep(1.5)
    record['afterHeaders'] = frame('after')
except Exception as exc:
    record['error'] = str(exc)
    raise
finally:
    try:
        if tokens:
            k.release(tokens)
        record['finalInput'] = k.input_status().get(k.resolve_device_id('C24C'))
    finally:
        (folder / 'record.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps({'folder': str(folder), 'released': record['finalInput']['owned'] is False}))
