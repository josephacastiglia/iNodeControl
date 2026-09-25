"""One observed action at a time on the two authorized phones; never fan out."""
import argparse, io, json, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis' / 'two-phone-live-test-20260914'
IDS = {'C24C': '86:1D:4A:04:2F:F6', 'C241': 'FE:A9:BC:D7:A0:44'}
BASE = 'http://127.0.0.1:9913/api'
OUT.mkdir(parents=True, exist_ok=True)

def get(path, body=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())

def verify():
    devices = get('/device/get')['data']['list']
    states = get('/kernel/status')['data']
    assert set(states['allowed']) == set(IDS), 'Unexpected input allowlist'
    for board, identity in IDS.items():
        d = next(d for d in devices if d['deviceid'] == identity)
        assert d['pid'] == board and d['uid'] == board + 'BFBD', 'Binding changed'
        r = next(r for r in states['receivers'] if r['deviceid'] == identity)
        assert r['live'] and r['name'] == 'iMouse2-' + board, 'Expected receiver not live'
    return states

def shot(board, label):
    with urllib.request.urlopen(BASE + '/pic/screenshot?id=' + IDS[board] + '&binary=true', timeout=8) as resp:
        raw = resp.read()
    assert raw[:2] == b'BM', 'No live BMP'
    im = Image.open(io.BytesIO(raw)).convert('RGB')
    assert im.size == (500,1080)
    im.save(OUT / (label + '-' + board + '.png'))
    return im

def pair(label):
    with ThreadPoolExecutor(max_workers=2) as pool:
        ims = dict(zip(IDS, pool.map(lambda b: shot(b,label), IDS)))
    return ims

def main():
    p=argparse.ArgumentParser()
    p.add_argument('label'); p.add_argument('--board',choices=IDS)
    p.add_argument('--action',choices=['home','search','left','right','reset','move'])
    p.add_argument('--x',type=int,default=250);p.add_argument('--y',type=int,default=900)
    p.add_argument('--watch',action='store_true',help='Sample returned frames for three seconds after the API response')
    args=p.parse_args()
    before_status=verify();before=pair(args.label+'-before')
    row={'at':datetime.now(timezone.utc).isoformat(),'label':args.label,'board':args.board,'action':args.action,'before_status':before_status}
    if args.action:
        assert args.board
        data={'id':IDS[args.board]}
        if args.action=='home': fun='/key/sendkey';data['fn_key']='Home'
        elif args.action=='search':fun='/mouse/click';data.update(x=args.x,y=args.y,button=1)
        elif args.action in ['left','right']:fun='/mouse/swipe';data.update(direction=args.action,len=0.75,duration=400)
        elif args.action=='reset':fun='/mouse/reset'
        else:fun='/mouse/move';data.update(x=args.x,y=args.y)
        t=time.perf_counter();response=get('/',{'fun':fun,'data':data});row['api_ms']=round((time.perf_counter()-t)*1000,1)
        row['response']=response
        assert response['status']==200 and response['data']['code']==0, response
        assert [r['id'] for r in response['data']['results']]==[IDS[args.board]], 'Response target mismatch'
        if args.watch:
            row['visual_samples']=[]
            while time.perf_counter()-t < 3.5:
                observed=shot(args.board,args.label+'-watched-last')
                difference=sum(ImageStat.Stat(ImageChops.difference(before[args.board].crop((0,70,500,1080)),observed.crop((0,70,500,1080)))).mean)/3
                row['visual_samples'].append({'since_send_ms':round((time.perf_counter()-t)*1000,1),'difference':round(difference,4)})
                if difference>8 and 'first_large_change_ms' not in row:
                    row['first_large_change_ms']=row['visual_samples'][-1]['since_send_ms']
                    observed.save(OUT/(args.label+'-first-change-'+args.board+'.png'))
                time.sleep(.1)
        else:time.sleep(1.2)
    after=pair(args.label+'-after');row['after_status']=verify()
    row['screen_difference']={b:round(sum(ImageStat.Stat(ImageChops.difference(before[b].crop((0,70,500,1080)),after[b].crop((0,70,500,1080)))).mean)/3,4) for b in IDS}
    with (OUT/'actions.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
    print(json.dumps({k:v for k,v in row.items() if k not in ['before_status','after_status']}))

if __name__=='__main__':main()
