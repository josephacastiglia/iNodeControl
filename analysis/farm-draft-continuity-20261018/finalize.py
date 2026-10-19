import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];RUN=Path(__file__).resolve().parent
ARCHIVE=ROOT.parent/'iMouseXP-2.0-evidence-archive/20261018-farm-continuity'
git=['git','-c','safe.directory='+ROOT.as_posix()]
head=subprocess.check_output(git+['rev-parse','HEAD'],cwd=ROOT).decode().strip()
assert not subprocess.check_output(git+['status','--porcelain','--untracked-files=no'],cwd=ROOT).strip()
for file in (ARCHIVE/'source').rglob('*'):
    if file.is_file(): assert file.read_bytes()==(ROOT/file.relative_to(ARCHIVE/'source')).read_bytes(),str(file)
actions=[json.loads(p.read_text(encoding='utf-8')) for p in RUN.glob('*/record.json')]
record=dict(commit=head,pushed=False,installedReleaseChanged=False,desktopControl=False,publishing=False,messaging=False,
            liveInputTarget='C24C',inputCommands=sum(len(a.get('commands',[])) for a in actions),
            stoppedBeforeStep12=True,accountAfterCaptured=False,savedDraftAccepted=False,
            pythonTests=234,nativeChecks=505,
            candidateDllSha256=hashlib.sha256((ARCHIVE/'candidate/iMouse2.dll').read_bytes()).hexdigest())
assert not next(a for a in actions if 'error' in a).get('commands')
(ARCHIVE/'COMMIT.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
inventory={p.relative_to(ARCHIVE).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(ARCHIVE.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.txt'}
(ARCHIVE/'SHA256SUMS.txt').write_text(''.join(f'{h}  {p}\n' for p,h in inventory.items()),encoding='utf-8')
assert all(hashlib.sha256((ARCHIVE/p).read_bytes()).hexdigest()==h for p,h in inventory.items())
print(json.dumps(dict(commit=head,archive=str(ARCHIVE),verifiedFiles=len(inventory),trackedClean=True)))
