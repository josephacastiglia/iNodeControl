"""Summarize saved reply captures; temporal windows are not command acknowledgements."""
import argparse
from collections import Counter
import json
from pathlib import Path
from vendor_hid_decode import decode_report


def analyze(path):
    rows = [json.loads(line) for line in Path(path).read_text(encoding='utf-8-sig').splitlines()]
    phase = 'before-first-command'
    phases = {}
    families = Counter()
    patterns = Counter()
    formula_matches = 0
    movement = 0
    for row in rows:
        if row['kind'] == 'command-start':
            phase = row['detail']['label']
        elif row['kind'] == 'release-start':
            phase = 'release-and-drain'
        elif row['kind'] == 'reader' and row['detail']['kind'] == 'input':
            raw = bytes.fromhex(row['detail']['detail']['report_hex'])
            parsed = decode_report(raw, direction='in', framing='windows')
            families[parsed['family']] += 1
            patterns[parsed['payload_hex']] += 1
            window = phases.setdefault(phase, {'families':Counter(), 'movement_fields':[]})
            window['families'][parsed['family']] += 1
            if raw[1] == 0xA1:
                payload = raw[1:]
                movement += 1
                matches = payload[4] == (0x80 + sum(payload[1:4])) & 0xff
                formula_matches += matches
                window['movement_fields'].append({'buttons':payload[1],
                    'dx':int.from_bytes(payload[2:3],'little',signed=True),
                    'dy':int.from_bytes(payload[3:4],'little',signed=True),
                    'check_byte':payload[4]})
    return {'source':str(path),'families':dict(families),'reports':sum(families.values()),
        'temporal_windows':phases,'payload_patterns':dict(patterns),
        'a1_observed_formula':{'expression':'byte4 == (0x80 + byte1 + byte2 + byte3) modulo 256',
            'matched':formula_matches,'observed':movement,'status':'candidate interpretation, not a verified integrity check'},
        'limits':['Windows/IPC receipt timing, not USB write-to-reply latency',
            'Echo-like fields do not establish a unique sequence or iOS completion',
            'No report was captured from C241']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('captures',nargs='+')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    result=[analyze(path) for path in args.captures]
    with Path(args.output).open('x',encoding='utf-8') as out:
        json.dump(result,out,indent=2)
    print(json.dumps([{'source':r['source'],'reports':r['reports'],'families':r['families']} for r in result],indent=2))
