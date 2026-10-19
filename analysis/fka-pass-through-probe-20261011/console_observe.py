"""Read-only C24C phone/state capture around the actual Windows console button."""
import argparse
import io
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image

parser=argparse.ArgumentParser()
parser.add_argument('action', choices=('frame','watch'))
parser.add_argument('label')
args=parser.parse_args()
assert args.label.replace('-','').replace('_','').isalnum()
live=Path(__file__).resolve().parent/'live-repeat-20261011'
out=live/args.label
out.mkdir(exist_ok=False)
base='http://127.0.0.1:9913/api/'
phone='86:1D:4A:04:2F:F6'
expected=json.loads((live/'test-start.json').read_text(encoding='utf-8-sig'))

def get(path): return json.loads(urllib.request.urlopen(base+path,timeout=5).read())['data']
kernel=get('kernel/status')
assert kernel['allowed']==['C24C'] and len(kernel['receivers'])==1
assert kernel['receivers'][0]['deviceid']==phone and kernel['receiver_pid']==expected['receiver_pid'] and kernel['live']
devices=get('device/get')['list']
assert len(devices)==1 and devices[0]['deviceid']==phone and devices[0]['pid']=='C24C' and devices[0]['uid']=='C24CBFBD'

def capture(name):
    raw=urllib.request.urlopen(base+'pic/screenshot?id='+phone+'&binary=true',timeout=5).read()
    assert raw[:2]==b'BM'
    Image.open(io.BytesIO(raw)).save(out/(name+'.png'))
    state=get('input/status')
    assert len(state['phones'])==1 and state['phones'][0]['id']==phone
    with (out/'states.jsonl').open('a',encoding='utf-8') as f:
        f.write(json.dumps({'utc':datetime.now(timezone.utc).isoformat(),'frame':name+'.png','input':state})+'\n')

capture('before')
if args.action=='frame':
    print(out/'before.png')
else:
    (out/'capture-start.json').write_text(json.dumps({'utc':datetime.now(timezone.utc).isoformat(),'read_only':True,'limit_seconds':45}),encoding='utf-8')
    print('CAPTURE STARTED '+str(out),flush=True)
    start=time.monotonic()
    index=0
    while time.monotonic()-start<45 and not (out/'capture-stop').exists():
        capture(f'frame-{index:03d}')
        index+=1
        time.sleep(0.5)
    capture('after')
    (out/'capture-end.json').write_text(json.dumps({'utc':datetime.now(timezone.utc).isoformat(),'frames':index,'elapsed_seconds':time.monotonic()-start}),encoding='utf-8')
    print('CAPTURE FINISHED '+str(out/'after.png'),flush=True)
