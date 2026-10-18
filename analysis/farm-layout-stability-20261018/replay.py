"""Replay retained phone frames offline. No capture, network or input."""
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import types

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(__file__).resolve().parent
PRIOR = ROOT / 'analysis/farm-live-verification-20261018'
sys.path.insert(0, str(ROOT / 'tools'))
from farm_observations import classify
from farm_screen_layout import picker_stability


def capture(folder, phase):
    record = json.loads((PRIOR / folder / 'record.json').read_text(encoding='utf-8'))
    value = next(c['observation'] for c in record['captures'] if c['name'] == phase)
    frame = (PRIOR / folder / (phase+'.png')).read_bytes()
    assert hashlib.sha256(frame).hexdigest() == value['reviewFrameSha256']
    return value, frame


def main():
    baseline_commit='cb6178395053e5dc1322cc5d23abf95431635de8'
    source=subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),
        'show',baseline_commit+':tools/farm_observations.py'],cwd=ROOT)
    baseline=types.ModuleType('prior_observations')
    exec(compile(source,'prior_observations.py','exec'),baseline.__dict__)
    rows = []
    for path in sorted(PRIOR.glob('*/record.json')):
        record = json.loads(path.read_text(encoding='utf-8'))
        for item in record['captures']:
            value, frame = capture(path.parent.name, item['name'])
            prior=baseline.classify(value['text'],value['expected'])
            current = classify(value['text'], value['expected'], frame)
            rows.append(dict(folder=path.parent.name, phase=item['name'],
                before=prior['screen'], beforeLayout=prior['layout'],
                after=current['screen'], afterLayout=current['layout'],
                layoutEvidence=current['layoutEvidence'],
                automaticInputAllowed=current['automaticInputAllowed']))
    pairs = []
    for first, second in (('18-library-after-save', '19-confirm-saved-library'),
                          ('29-final-library', '31-exit-picker')):
        a, raw_a = capture(first, 'fresh'); b, raw_b = capture(second, 'fresh')
        pairs.append(dict(first=first, second=second, result=picker_stability(raw_a,a['text'],raw_b,b['text'])))
    regression=[]
    records=json.loads((ROOT/'analysis/farm-recognition-20261017/recognition-replay.json').read_text(encoding='utf-8'))
    for item in records:
        text=json.loads((ROOT/'analysis/farm-observations-20261017'/item['file']).read_text(encoding='utf-8-sig'))
        expect=dict(device_id='C24C',platform='instagram',account='not.this.account',caption='')
        before=baseline.classify(text,expect); after=classify(text,expect)
        regression.append(dict(file=item['file'],expected=item['expected'],before=before['screen'],after=after['screen']))
    assert all(row['before']==row['after']==row['expected'] for row in regression)
    assert all(not row['automaticInputAllowed'] for row in rows)
    changes=[r for r in rows if r['before']!=r['after']]
    result = dict(source='retained_phone_evidence', baselineCommit=baseline_commit,
                  phoneCalls=0, captures=rows, pickerPairs=pairs, historicalOcrRegressions=regression,
                  independentAccuracySet=False)
    (RUN/'replay.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(captures=len(rows),changed=len(changes),
        changesByState={state:sum(r['after']==state for r in changes) for state in sorted({r['after'] for r in changes})},
        historicalOcrRegressions=len(regression),pickerPairs=pairs)))


if __name__ == '__main__': main()
