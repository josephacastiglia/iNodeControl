"""Scan STAGED blobs for private values before a commit. Prints file names and counts only, never values.

The private values live outside Git, in the evidence archive beside this repository:
  iMouseXP-2.0-evidence-archive/privacy/withheld-candidates.txt   serial-shaped personal-iPhone tokens
  iMouseXP-2.0-evidence-archive/privacy/extra-handles.txt         X handles to keep out of Git (one per line)
plus the X handle read at run time from the retained 17 Oct side-menu OCR. Also refuses staged files
over 50 MB and paths under output/, and flags vendor credential markers for review.

  python tools/privacy_scan_staged.py        # exit 0 clean, 1 problems, 2 private lists missing
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
from farm_paths import ARCHIVE  # noqa: E402  (beside the main folder, also from a lane worktree)
PRIVATE = ARCHIVE / 'privacy'
OCR = ARCHIVE / '20261019-farm-x-offline/ocr-20261017/31-x-account__after.json'


def git(*args):
    return subprocess.run(['git', '-C', str(REPO), *args], capture_output=True, check=True).stdout


def lines(path):
    return [t.strip() for t in path.read_text(encoding='utf-8').splitlines() if t.strip() and not t.strip().startswith('#')]


def main():
    missing = [p for p in (PRIVATE / 'withheld-candidates.txt', PRIVATE / 'extra-handles.txt', OCR) if not p.exists()]
    if missing:
        print('Private scan lists are missing; nothing was scanned:', *[str(p) for p in missing], sep='\n  ')
        return 2
    # Only serial-shaped candidates are private; the file also lists ordinary words checked earlier.
    tokens = [t for t in lines(PRIVATE / 'withheld-candidates.txt') if len(t) >= 12 and not t.isalpha()]
    text = json.loads(OCR.read_text(encoding='utf-8'))
    handles = {m.group(1) for line in text['lines'] for m in re.finditer(r'@([A-Za-z0-9_]{1,15})', line['text'])}
    handles |= {h.lstrip('@') for h in lines(PRIVATE / 'extra-handles.txt')}
    needles = [('withheld token', t) for t in tokens] + [('x handle', h) for h in sorted(handles) if h.casefold() != 'xs.halle.xo']
    markers = [('vendor credential file', 'IMService.json'), ('password field', '"password"'), ('api key field', 'apikey')]
    print(f'{len(tokens)} withheld token(s), {len(handles)} X handle(s) loaded.')

    staged = [p for p in git('diff', '--cached', '--name-only', '-z').decode('utf-8').split('\0') if p]
    problems = 0
    for path in staged:
        if path.startswith('output/') or '/output/' in path:
            print('OUTPUT PATH STAGED:', path); problems += 1
        try: blob = git('show', ':' + path)
        except subprocess.CalledProcessError:
            continue   # Deleted in the index.
        if len(blob) > 50 * 1024 * 1024:
            print('OVER 50 MB:', path); problems += 1
        low = blob.decode('utf-8', errors='replace').casefold()
        for kind, value in needles:
            if value.casefold() in low:
                print(f'PRIVATE VALUE ({kind}) in {path}'); problems += 1
        for kind, value in markers:
            if value.casefold() in low and not path.endswith('.md') and path != 'tools/privacy_scan_staged.py':
                print(f'review marker ({kind}) in {path}')
    print(f'{len(staged)} staged file(s) scanned; {problems} problem(s).')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
