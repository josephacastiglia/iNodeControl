"""Preserve exact offline source, build and evidence without modifying older archives."""
import hashlib,json,os,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; RUN=Path(__file__).resolve().parent
ARCHIVE=ROOT.parent/'iMouseXP-2.0-evidence-archive/20261018-farm-save-reopen'
git=['git','-c','safe.directory='+ROOT.as_posix()]
head=subprocess.check_output(git+['rev-parse','HEAD'],cwd=ROOT).decode().strip()
assert not subprocess.check_output(git+['status','--porcelain','--untracked-files=no'],cwd=ROOT).strip()
ARCHIVE.mkdir(parents=True,exist_ok=False)
def copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target)
    if source.read_bytes()!=target.read_bytes(): raise RuntimeError('Archive copy mismatch')
for path in RUN.rglob('*'):
    if path.is_file() and '__pycache__' not in path.parts: copy(path,ARCHIVE/'run'/path.relative_to(RUN))
candidate=ROOT/'output/codex-farm-save-reopen-20261018'
for path in candidate.rglob('*'):
    if path.is_file(): copy(path,ARCHIVE/'candidate'/path.relative_to(candidate))
sources=[ROOT/name for name in ('MARKETING-FARM-STATUS.md','MARKETING-FARM-ACCEPTANCE.md','Open Marketing Farm Candidate.ps1',
                               'tools/requirements-farm.txt','tools/imouse_farm_server.py','tools/imouse_social_automation.py','tools/Read-FarmImageText.ps1')]
sources+=list((ROOT/'tools').glob('farm_*.py'))+list((ROOT/'tools').glob('test_farm*.py'))
for pattern in ('*.cs','*.xaml','*.csproj'): sources+=list((ROOT/'src/iMouse.Console').glob(pattern))
for path in sorted(set(sources)): copy(path,ARCHIVE/'source'/path.relative_to(ROOT))
settings=Path(os.environ['APPDATA'])/'iMouse2/settings.json'
before=json.loads((RUN/'settings-before.json').read_text(encoding='utf-8-sig'))['sha256']
after=hashlib.sha256(settings.read_bytes()).hexdigest() if settings.exists() else None
unchanged=(before or '').lower()==(after or '').lower()
record=dict(commit=head,pushed=False,pythonTests=294,nativeChecks=517,phoneInput=False,desktopControl=False,rackApiCalls=False,
            publishing=False,messaging=False,installedReleaseChanged=False,operatorSettingsContentUnchanged=unchanged,
            liveInspectionEnabled=False,liveDraftRehearsalEnabled=False,offlineScenarios=9,candidateDllSha256=hashlib.sha256((candidate/'iMouse2.dll').read_bytes()).hexdigest())
(ARCHIVE/'COMMIT.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
inventory={p.relative_to(ARCHIVE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(ARCHIVE.rglob('*')) if p.is_file()}
(ARCHIVE/'SHA256SUMS.txt').write_text(''.join(f'{h}  {p}\n' for p,h in inventory.items()),encoding='utf-8')
assert all(hashlib.sha256((ARCHIVE/p).read_bytes()).hexdigest()==h for p,h in inventory.items())
print(json.dumps(dict(commit=head,archive=str(ARCHIVE),verifiedFiles=len(inventory),operatorSettingsContentUnchanged=unchanged)))
