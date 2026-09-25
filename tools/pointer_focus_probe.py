"""One focus-mode trial, with live identity guards and no fan-out."""
import argparse, json, subprocess, time
from pathlib import Path
import two_phone_check as check

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis' / 'pointer-reliability-20260915'
check.OUT = OUT
p = argparse.ArgumentParser()
p.add_argument('board', choices=check.IDS)
p.add_argument('mode', choices=['zero', 'wake'])
p.add_argument('label')
a = p.parse_args()
check.verify()
identity = check.IDS[a.board]
def send(fun, **kw):
    r = check.get('/', {'fun': fun, 'data': {'id': identity, **kw}})
    assert r['data']['code'] == 0, r
    return r

send('/key/sendkey', fn_key='Home')
time.sleep(.6)
send('/mouse/move', x=250,y=900)
time.sleep(.2)
check.pair(a.label+'-at-search')
send('/key/sendkey', fn_key='Home')
time.sleep(.6)
check.pair(a.label+'-after-home')
reports = []
if a.mode == 'wake':
    reports += [{'Hex':'A100010000000000','DelayMs':20}, {'Hex':'A100FF0000000000','DelayMs':20}]
reports += [{'Hex':'A100000000000000','DelayMs':120}, {'Hex':'A101000000000000','DelayMs':80}, {'Hex':'A100000000000000','DelayMs':0}]
file = OUT/(a.label+'-replay.json')
file.write_text(json.dumps(reports))
check.verify()
try:
    subprocess.run([str(ROOT/'release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe'),'--hid-replay',a.board,str(file)], check=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    time.sleep(.5)
    check.pair(a.label+'-result')
finally:
    send('/mouse/reset')
    send('/key/sendkey', fn_key='Home')
    time.sleep(.5)
check.verify()
print(json.dumps({'label':a.label,'board':a.board,'mode':a.mode,'visual_result':'requires inspection'}))
