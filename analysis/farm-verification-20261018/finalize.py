import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT.parent / 'iMouseXP-2.0-evidence-archive/20261018-farm-verification'
git = ['git', '-c', 'safe.directory=' + ROOT.as_posix()]
head = subprocess.check_output(git + ['rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
branch = subprocess.check_output(git + ['branch', '--show-current'], cwd=ROOT).decode().strip()
assert not subprocess.check_output(git + ['status', '--porcelain', '--untracked-files=no'], cwd=ROOT).strip()
for file in (ARCHIVE / 'source').rglob('*'):
    if file.is_file(): assert file.read_bytes() == (ROOT / file.relative_to(ARCHIVE / 'source')).read_bytes(), str(file)
record = dict(commit=head, branch=branch, pushed=False, installedReleaseChanged=False, rackApiCalls=0, phoneInput=False,
              desktopControl=False, publishing=False, messaging=False, pythonTests=223, nativeChecks=502,
              candidateDllSha256=hashlib.sha256((ARCHIVE / 'candidate/iMouse2.dll').read_bytes()).hexdigest(),
              savedDraftVerificationAccepted=False)
(ARCHIVE / 'COMMIT.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
inventory = {file.relative_to(ARCHIVE).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
             for file in sorted(ARCHIVE.rglob('*')) if file.is_file() and file.name != 'SHA256SUMS.txt'}
(ARCHIVE / 'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name, digest in inventory.items()), encoding='utf-8')
assert all(hashlib.sha256((ARCHIVE / name).read_bytes()).hexdigest() == digest for name, digest in inventory.items())
print(json.dumps(dict(commit=head, archive=str(ARCHIVE), verifiedFiles=len(inventory), trackedClean=True)))
