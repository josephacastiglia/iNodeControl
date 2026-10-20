"""Local Windows OCR of the retained 17 Oct C24C YouTube steps (Short 46-66, video 131-151).

Writes private JSON beside the other offline archives, outside Git: the frames
show personal account content. No socket, phone or service is involved.
"""
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from farm_observations import WindowsOcr  # noqa: E402

FRAMES = ROOT / 'analysis/farm-platform-drafts-20261017'
ARCHIVE = ROOT.parent / 'iMouseXP-2.0-evidence-archive/20261020-farm-youtube-offline'
OUT = ARCHIVE / 'ocr-20261017'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ocr, written = WindowsOcr(), []
    steps = sorted((p for p in FRAMES.iterdir() if p.is_dir() and re.match(r'(4[6-9]|5\d|6[0-6]|13[1-9]|14\d|15[01])-', p.name)),
                   key=lambda p: int(p.name.split('-')[0]))
    for step in steps:
        for name in ('before', 'immediate', 'pointer', 'after'):
            frame = step / (name + '.png')
            if not frame.is_file(): continue
            raw = frame.read_bytes()
            value = ocr.read(raw)
            value['source'] = dict(step=step.name, frame=frame.name, sha256=hashlib.sha256(raw).hexdigest())
            path = OUT / f'{step.name}__{name}.json'
            path.write_text(json.dumps(value, indent=1) + '\n', encoding='utf-8')
            written.append(path)
    sums = ''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest().upper()}  ocr-20261017/{p.name}\n' for p in sorted(written))
    (ARCHIVE / 'SHA256SUMS.txt').write_text(sums, encoding='utf-8')
    summary = dict(created='2026-10-20', files=len(written),
                   contents='Local Windows OCR of retained 17 Oct C24C YouTube frames (Short steps 46-66, video steps 131-151); private, '
                            'contains personal content; never upload.',
                   manifestSha256=hashlib.sha256(sums.encode('utf-8')).hexdigest(),
                   sourceFrames='iMouseXP-2.0-combined-candidate/analysis/farm-platform-drafts-20261017 (ignored *.png)',
                   usedBy=['tools/test_farm_permission_prompts.py'])
    (ARCHIVE / 'archive-summary.json').write_text(json.dumps(summary, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(dict(files=len(written), manifestSha256=summary['manifestSha256'])))


if __name__ == '__main__':
    main()
