"""Preserve completed offline work outside the checkout; never contacts a phone."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

RUN=Path(__file__).resolve().parent
ROOT=RUN.parents[1]
ARCHIVE=ROOT.parent/'iMouseXP-2.0-evidence-archive/20261018-farm-layout-stability'
GIT=['git','-c','safe.directory='+ROOT.as_posix()]


def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    head=subprocess.check_output(GIT+['rev-parse','HEAD'],cwd=ROOT).decode().strip()
    if subprocess.check_output(GIT+['status','--porcelain','--untracked-files=no'],cwd=ROOT).strip():
        raise SystemExit('Commit tracked work before archiving final evidence.')
    ARCHIVE.mkdir(exist_ok=False)
    copied={}
    def copy(original,relative):
        target=ARCHIVE/relative; target.parent.mkdir(parents=True,exist_ok=True)
        before=digest(original); shutil.copy2(original,target)
        assert digest(original)==digest(target)==before, str(original)
        copied[relative.as_posix()]=before
    for original in sorted(RUN.rglob('*')):
        if original.is_file() and '__pycache__' not in original.parts:
            copy(original,Path('run')/original.relative_to(RUN))
    prior=ROOT/'analysis/farm-live-verification-20261018'
    for record in sorted(prior.glob('*/record.json')):
        copy(record,Path('inputs/live')/record.relative_to(prior))
        value=json.loads(record.read_text(encoding='utf-8'))
        for item in value['captures']:
            image=record.parent/(item['name']+'.png')
            assert digest(image)==item['observation']['reviewFrameSha256']
            copy(image,Path('inputs/live')/image.relative_to(prior))
    recognition=ROOT/'analysis/farm-recognition-20261017/recognition-replay.json'
    copy(recognition,Path('inputs/recognition-replay.json'))
    for item in json.loads(recognition.read_text(encoding='utf-8')):
        copy(ROOT/'analysis/farm-observations-20261017'/item['file'],Path('inputs/ocr')/item['file'])
    tracked=subprocess.check_output(GIT+['ls-files','-z'],cwd=ROOT).decode().split('\0')
    for name in tracked:
        if (name.startswith(('tools/farm_','tools/test_farm')) or name in (
                'tools/imouse_farm_server.py','tools/imouse_social_automation.py','tools/Read-FarmImageText.ps1',
                'Open Marketing Farm Candidate.ps1','MARKETING-FARM-STATUS.md','MARKETING-FARM-ACCEPTANCE.md')):
            copy(ROOT/name,Path('source')/name)
    record=dict(commit=head,pushed=False,scope='offline only',phoneCalls=0,pcControl=False,
        installedReleaseChanged=False,publishing=False,messaging=False,automaticInputAllowed=False,
        earlierLiveArchive='20261018-farm-live-verification',sourceCopies=copied)
    (ARCHIVE/'COMMIT.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    files=[p for p in sorted(ARCHIVE.rglob('*')) if p.is_file()]
    inventory={p.relative_to(ARCHIVE).as_posix():digest(p) for p in files}
    (ARCHIVE/'SHA256SUMS.txt').write_text(''.join(f'{sha}  {name}\n' for name,sha in inventory.items()),encoding='utf-8')
    assert all(digest(ARCHIVE/name)==sha for name,sha in inventory.items())
    print(json.dumps(dict(commit=head,archive=str(ARCHIVE),filesVerified=len(inventory),
                          sourceCopiesVerified=len(copied),bytes=sum(p.stat().st_size for p in files))))


if __name__=='__main__': main()
