import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(__file__).resolve().parent
ARCHIVE = ROOT.parent / 'iMouseXP-2.0-evidence-archive/20261017-farm-recognition'
git = ['git', '-c', 'safe.directory=' + ROOT.as_posix()]
head = subprocess.check_output(git + ['rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
branch = subprocess.check_output(git + ['branch', '--show-current'], cwd=ROOT).decode().strip()
tracked = subprocess.check_output(git + ['status', '--porcelain', '--untracked-files=no'], cwd=ROOT).decode().strip()
if tracked: raise SystemExit('Tracked changes remain; do not finalize this checkpoint.')
for file in (ARCHIVE / 'source').rglob('*'):
    if file.is_file():
        original = ROOT / file.relative_to(ARCHIVE / 'source')
        if file.read_bytes() != original.read_bytes(): raise SystemExit('Archived source differs: ' + str(original))
for file in RUN.glob('*.py'): shutil.copy2(file, ARCHIVE / 'run' / file.name)
record = dict(commit=head, branch=branch, pushed=False, installedReleaseChanged=False, inputSent=False,
              candidateDllSha256=hashlib.sha256((ARCHIVE / 'candidate/iMouse2.dll').read_bytes()).hexdigest(),
              pythonTests=208, nativeChecks=494, frameTests=34, productionMetadataCases=4,
              savedFrameRegressionCases=39, savedFramesAreIndependentAccuracySet=False)
(ARCHIVE / 'COMMIT.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
files = [p for p in sorted(ARCHIVE.rglob('*')) if p.is_file() and p != ARCHIVE / 'SHA256SUMS.txt']
inventory = {p.relative_to(ARCHIVE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(ARCHIVE / 'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name, digest in inventory.items()), encoding='utf-8')
assert all(hashlib.sha256((ARCHIVE / name).read_bytes()).hexdigest() == digest for name, digest in inventory.items())
print(json.dumps(dict(commit=head, archive=str(ARCHIVE), filesVerified=len(inventory), trackedClean=True)))
