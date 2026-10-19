"""Preserve this offline candidate and its evidence without touching the rack."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ARCHIVE = ROOT.parent / 'iMouseXP-2.0-evidence-archive' / '20261018-farm-interface-integration'


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if ARCHIVE.exists(): raise RuntimeError('Preserve the existing archive; choose a new destination for another run.')
    source_commit = subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),'rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    changed = subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),'diff-tree','--no-commit-id','--name-only','-r',source_commit],cwd=ROOT,text=True).splitlines()
    # All console sources plus the exact Python backend fingerprint dependencies.
    tracked = subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),'ls-files','src/iMouse.Console'],cwd=ROOT,text=True).splitlines()
    dependencies = ('imouse_farm_server.py','imouse_social_automation.py','farm_jobs.py','farm_drafts.py',
        'farm_media_transfer.py','farm_transfers.py','farm_capabilities.py','farm_video.py','farm_observations.py',
        'Read-FarmImageText.ps1','farm_preparation_schedule.py','farm_frame_evidence.py','farm_draft_verification.py',
        'farm_draft_media.py','farm_carousel_inspection.py','farm_draft_rehearsal.py','farm_screen_layout.py',
        'farm_transitions.py','farm_live_verification.py','farm_draft_transport.py','farm_draft_workflow.py',
        'farm_draft_runs.py','farm_draft_anchors.json')
    sources = sorted(set(changed + tracked + ['tools/'+name for name in dependencies]))
    previous=json.loads((ROOT/'analysis/farm-live-final-20261018/protected-files.json').read_text(encoding='utf-8-sig'))
    protected=[dict(path=p,sha256=digest(Path(p)),unchanged=digest(Path(p))==v['sha256']) for p,v in previous.items()]
    if not all(v['unchanged'] for v in protected): raise RuntimeError('A protected file changed; record and investigate before finalizing.')
    tests=json.loads((HERE/'python-tests.json').read_text())
    focused=json.loads((HERE/'focused-tests.json').read_text())
    native=json.loads((HERE/'native-self-tests.json').read_text(encoding='utf-8-sig'))
    assert tests['success'] and focused['success'] and native['passed']==546
    assert 'Ran 12 tests' in (HERE/'extraction-tests.txt').read_text(encoding='utf-8-sig')
    assert (HERE/'extraction-tests.txt').read_text(encoding='utf-8-sig').rstrip().endswith('OK')
    candidate=ROOT/'output/codex-farm-interface-20261018'
    validation=dict(sourceCommit=source_commit,candidate=str(candidate),nativeDllSha256=digest(candidate/'iMouse2.dll'),
        backendSourceHash=json.loads((HERE/'launcher-draft-candidate.json').read_text(encoding='utf-8-sig'))['SourceHash'],
        broadPython=tests,focusedPython=focused,distinctPythonProductChecks=394,retainedSequenceChecks=12,
        nativeChecks=native['passed'],sources={p:digest(ROOT/p) for p in sources},
        protectedFiles=protected,noPhoneOrDesktopInput=True,liveInterfaceAccepted=False,installedReleaseChanged=False)
    (HERE/'validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
    copies={}
    for path in HERE.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.name!='archive-summary.json':
            copies['record/'+path.relative_to(HERE).as_posix()]=path
    for p in sources: copies['source/'+p]=ROOT/p
    for path in candidate.rglob('*'):
        if path.is_file(): copies['candidate/'+path.relative_to(candidate).as_posix()]=path
    ARCHIVE.mkdir(parents=True)
    rows=[]
    for relative,path in sorted(copies.items()):
        target=ARCHIVE/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,target)
        actual=digest(target)
        if actual!=digest(path): raise RuntimeError('Archive mismatch: '+relative)
        rows.append((relative,actual,target.stat().st_size))
    manifest=ARCHIVE/'SHA256SUMS.txt'
    manifest.write_text(''.join(checksum+'  '+name+'\n' for name,checksum,_ in rows),encoding='utf-8',newline='\n')
    for name,checksum,_ in rows:
        if digest(ARCHIVE/name)!=checksum: raise RuntimeError('Final archive verification failed: '+name)
    summary=dict(path=str(ARCHIVE),files=len(rows),bytes=sum(size for _,_,size in rows),verified=True,
        manifestSha256=digest(manifest),sourceCommit=source_commit,previousArchivesRequiredForRetainedPhoneFixtures=True)
    (HERE/'archive-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))


if __name__=='__main__': main()
