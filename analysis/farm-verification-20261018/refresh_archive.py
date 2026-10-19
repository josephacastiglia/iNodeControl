"""Refresh this run's existing archive after final tests; do not alter older archives."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(__file__).resolve().parent
ARCHIVE = ROOT.parent / 'iMouseXP-2.0-evidence-archive/20261018-farm-verification'
assert ARCHIVE.is_dir()
copied = 0
for file in RUN.rglob('*'):
    if file.is_file() and '__pycache__' not in file.parts:
        target = ARCHIVE / 'run' / file.relative_to(RUN)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
        assert file.read_bytes() == target.read_bytes()
        copied += 1
for file in (ARCHIVE / 'source').rglob('*'):
    if file.is_file():
        source = ROOT / file.relative_to(ARCHIVE / 'source')
        shutil.copy2(source, file)
        assert file.read_bytes() == source.read_bytes()
        copied += 1
for file in (ARCHIVE / 'candidate').rglob('*'):
    if file.is_file():
        source = ROOT / 'output/codex-farm-verification-20261018' / file.relative_to(ARCHIVE / 'candidate')
        assert file.read_bytes() == source.read_bytes(), str(file)
print(f'Refreshed {copied} source/evidence files; candidate bytes unchanged.')
