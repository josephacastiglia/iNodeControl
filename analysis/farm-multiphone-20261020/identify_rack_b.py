"""rb.py [board slot] [next_board] [--home board]: record a rack B slot, then flash the next board's
App Switcher (Home, App Switcher for 3 s, Home). The page swipe was slow enough on rack B's
6s/7/8 phones to count as a long press (icons wiggled, 30 Oct), so keys only."""
import json, sys, time, pathlib
D = pathlib.Path(r'C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-combined-candidate\analysis\farm-multiphone-20261020')
sys.path.insert(0, str(D.parents[1] / 'tools'))
from identify_phone import acquire, post, request  # noqa: E402
B = 'http://127.0.0.1:9916/api'


def keys(board, seq):
    d = f'pending-{board}'
    row = next(p for p in request(B, 'GET', '/input/status', timeout=5)['phones'] if p['id'] == d)
    if row['stopped']: post(B, '/input/resume', dict(id=d, expected_generations={d: row['generation']}))
    t = acquire(B, d); codes = []
    try:
        for key, wait in seq:
            post(B, '/input/renew', dict(id=d, token=t))
            codes.append(post(B, '/key/sendkey', dict(id=d, token=t, fn_key=key)).get('code')); time.sleep(wait)
    finally:
        post(B, '/input/release', dict(id=d, token=t))
    print(json.dumps(dict(board=board, keys=[k for k, _ in seq], codes=codes)))


p = D / 'rack-b-slots.json'
s = json.loads(p.read_text(encoding='utf-8'))
args = sys.argv[1:]
if args[:1] == ['--home']:
    keys(args[1].upper(), [('Home', 1.5)]); args = args[2:]
if len(args) >= 2:
    board, slot = args[0].upper(), args[1]
    if slot in s['slots']: sys.exit(f'slot {slot} already recorded ({s["slots"][slot]["board"]})')
    if any(v['board'] == board for v in s['slots'].values()): sys.exit(f'{board} already recorded')
    s['slots'][slot] = dict(board=board, receiver=f'iMouse2-B{slot}')
    s['slots'] = dict(sorted(s['slots'].items(), key=lambda kv: int(kv[0])))
    p.write_text(json.dumps(s, indent=2), encoding='utf-8')
    args = args[2:]
boards = [b['board'] for b in json.loads((D / 'rack-b-boards.json').read_text(encoding='utf-8-sig'))['boards']]
done = {v['board'] for v in s['slots'].values()}
print('recorded slots:', ' '.join(s['slots']), '| boards left:', ' '.join(b for b in boards if b not in done))
def flip(board, n=10):
    """Quick 100 ms swipes, alternating, every 2 s (no wiggle on 0C6D, 30 Oct)."""
    sys.path.insert(0, str(D))
    from card_survey import to_send, SMALL
    d = f'pending-{board}'
    row = next(p for p in request(B, 'GET', '/input/status', timeout=5)['phones'] if p['id'] == d)
    if row['stopped']: post(B, '/input/resume', dict(id=d, expected_generations={d: row['generation']}))
    a, b = to_send((440, 560), SMALL), to_send((90, 560), SMALL)
    t = acquire(B, d); codes = []
    try:
        for i in range(n):
            post(B, '/input/renew', dict(id=d, token=t))
            s_, e = (a, b) if i % 2 == 0 else (b, a)
            post(B, '/mouse/reset', dict(id=d, token=t))
            codes.append(post(B, '/mouse/swipe', dict(id=d, token=t, x1=s_[0], y1=s_[1], x2=e[0], y2=e[1], duration=100)).get('code'))
            time.sleep(2.0)
    finally:
        post(B, '/input/release', dict(id=d, token=t))
    print(json.dumps(dict(board=board, swipes=codes)))


if args:
    flip(args[0].upper())
