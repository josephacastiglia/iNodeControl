"""Preserve this pass without changing old evidence or the installed release."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]; RUN = Path(__file__).resolve().parent
ARCHIVE = ROOT.parent / 'iMouseXP-2.0-evidence-archive/20261018-farm-preparation-continuity'
git = ['git', '-c', 'safe.directory=' + ROOT.as_posix()]
head = subprocess.check_output(git + ['rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
assert not subprocess.check_output(git + ['status', '--porcelain', '--untracked-files=no'], cwd=ROOT).strip()
ARCHIVE.mkdir(parents=True, exist_ok=False)

def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
    assert source.read_bytes() == target.read_bytes(), 'Archive copy differs from source'

for path in RUN.rglob('*'):
    if path.is_file() and '__pycache__' not in path.parts: copy(path, ARCHIVE / 'run' / path.relative_to(RUN))
candidate = ROOT / 'output/codex-farm-preparation-20261018'
for path in candidate.rglob('*'):
    if path.is_file(): copy(path, ARCHIVE / 'candidate' / path.relative_to(candidate))
sources = [ROOT / name for name in ('MARKETING-FARM-STATUS.md', 'MARKETING-FARM-ACCEPTANCE.md', 'Open Marketing Farm Candidate.ps1',
    'tools/requirements-farm.txt', 'tools/imouse_farm_server.py', 'tools/imouse_social_automation.py', 'tools/Read-FarmImageText.ps1')]
sources += list((ROOT / 'tools').glob('farm_*.py')) + list((ROOT / 'tools').glob('test_farm*.py'))
for pattern in ('*.cs', '*.xaml', '*.csproj'): sources += list((ROOT / 'src/iMouse.Console').glob(pattern))
for path in sorted(set(sources)): copy(path, ARCHIVE / 'source' / path.relative_to(ROOT))
settings = Path(os.environ['APPDATA']) / 'iMouse2/settings.json'
before = json.loads((RUN / 'settings-before.json').read_text(encoding='utf-8-sig'))['sha256']
after = hashlib.sha256(settings.read_bytes()).hexdigest() if settings.exists() else None
assert (before or '').lower() == (after or '').lower(), 'Operator settings changed; inspect before claiming restoration'
build = json.loads((RUN / 'build-source.json').read_text(encoding='utf-8-sig'))
native = json.loads((RUN / 'native-self-tests.json').read_text(encoding='utf-8-sig'))
log = (RUN / 'python-verified.txt').read_text(encoding='utf-8-sig')
tests = int(re.search(r'^Ran (\d+) tests', log, re.M)[1])
record = dict(codeCommit=build['commit'], reportCommit=head, pushed=False, pythonTests=tests, nativeChecks=native['passed'],
              phoneInput=False, desktopControl=False, rackApiCalls=False, publishing=False, messaging=False,
              installedReleaseChanged=False, operatorSettingsContentUnchanged=True, liveAutomationEnabled=False,
              candidateDllSha256=hashlib.sha256((candidate / 'iMouse2.dll').read_bytes()).hexdigest())
(ARCHIVE / 'COMMIT.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
inventory = {path.relative_to(ARCHIVE).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(ARCHIVE.rglob('*')) if path.is_file()}
(ARCHIVE / 'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name, digest in inventory.items()), encoding='utf-8')
assert all(hashlib.sha256((ARCHIVE / name).read_bytes()).hexdigest() == digest for name, digest in inventory.items())
print(json.dumps(dict(archive=str(ARCHIVE), verifiedFiles=len(inventory), **record)))
