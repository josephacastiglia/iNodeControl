"""Copy this run's private evidence outside the worktree; never overwrite evidence."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(__file__).resolve().parent
ARCHIVE = ROOT.parent / 'iMouseXP-2.0-evidence-archive/20261017-farm-phone-transfer'
if ARCHIVE.exists():
    raise SystemExit('Archive already exists. Verify it; do not overwrite it.')
ARCHIVE.mkdir(parents=True)

def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(target.read_bytes()).digest():
        raise RuntimeError('Evidence copy checksum differs: ' + str(source))

for source in RUN.rglob('*'):
    if source.is_file() and '__pycache__' not in source.parts:
        copy(source, ARCHIVE / 'run' / source.relative_to(RUN))
for relative in ('tools/farm_media_transfer.py', 'tools/farm_drafts.py', 'tools/farm_test_network.py',
                 'tools/test_farm_media_transfer.py', 'tools/test_farm_http_jobs.py',
                 'tools/imouse_social_automation.py', 'MARKETING-FARM-STATUS.md'):
    copy(ROOT / relative, ARCHIVE / 'source' / relative)

database = ROOT / 'output/farm-data/v2/simulate/carousel-drafts.db'
with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as source:
    with sqlite3.connect(ARCHIVE / 'carousel-drafts.db') as destination:
        source.backup(destination)

inventory = {str(file.relative_to(ARCHIVE)).replace('\\', '/'): hashlib.sha256(file.read_bytes()).hexdigest()
             for file in sorted(ARCHIVE.rglob('*')) if file.is_file()}
(ARCHIVE / 'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name, digest in inventory.items()), encoding='utf-8')
for name, digest in inventory.items():
    if hashlib.sha256((ARCHIVE / name).read_bytes()).hexdigest() != digest:
        raise RuntimeError('Archive verification failed: ' + name)
print(json.dumps({'archive': str(ARCHIVE), 'filesVerified': len(inventory), 'bytes': sum((ARCHIVE / name).stat().st_size for name in inventory)}))
