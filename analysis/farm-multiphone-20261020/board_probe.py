"""Which boards' phones take input right now: twelve small pointer moves each, under one lease.

A board buffers a few reports, so one move can pass with no phone behind it; when the phone does
not take them (off or flat), the board stops taking reports and the kernel's 2 s HID write times
out ('Input cancelled', 28 Oct, rack A's added boards). The kernel then stops that phone's input;
this probe resumes it (generation-checked) so the board is ready again. Pointer moves only.

  python board_probe.py E414 3523 ...
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'tools'))
from identify_phone import acquire, post, request  # noqa: E402

BASE = 'http://127.0.0.1:9916/api'
MOVES = [(240, 530), (260, 550)] * 6


def resume(device):
    row = next(p for p in request(BASE, 'GET', '/input/status', timeout=5)['phones'] if p['id'] == device)
    if row['stopped']:
        post(BASE, '/input/resume', dict(id=device, expected_generations={device: row['generation']}))


def main():
    devices = {d.get('pid', '').upper(): d['deviceid'] for d in request(BASE, 'GET', '/device/get', timeout=8)['list']}
    out = {}
    for board in (b.upper() for b in sys.argv[1:]):
        device = devices.get(board)
        if not device: out[board] = 'not in the kernel'; continue
        resume(device)
        token = acquire(BASE, device)
        done = 0
        try:
            for x, y in MOVES:
                if post(BASE, '/mouse/move', dict(id=device, token=token, x=x, y=y)).get('code') != 0: break
                done += 1
        finally:
            post(BASE, '/input/release', dict(id=device, token=token))
            resume(device)
        out[board] = 'takes input' if done == len(MOVES) else f'stalled after {done} of {len(MOVES)} moves'
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
