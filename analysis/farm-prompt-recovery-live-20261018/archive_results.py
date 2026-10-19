"""Archive the completed live run and exact test-wrapper/source provenance."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
ARCHIVE=ROOT.parent/'iMouseXP-2.0-evidence-archive/20261018-farm-prompt-recovery-live'

def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    prep=read(HERE/'preparation.json'); acceptance=read(HERE/'prompt-recovery-acceptance.json')
    assert acceptance['passed'] and all(acceptance['checks'].values())
    native=read(HERE/'live-save-reopen-with-refresh/result.json')
    assert native['passed'] and native['checks']==18 and native['windowHandles']==0
    restored=read(HERE/'restoration.json')
    assert restored['finalState']=='stopped' and not any(restored[key] for key in ('processes','tcpListeners','udpEndpoints'))
    protected=read(HERE/'protected-files.json')
    assert all(sha(Path(name))==row['sha256'] for name,row in protected.items())
    pinned=read(HERE/'validation-sources.json')
    assert all(sha(ROOT/name)==digest for name,digest in pinned.items())
    assert sha(Path(prep['nativeAssembly']))==prep['nativeSha256']
    assert sha(Path(prep['nativeProbe']).with_suffix('.dll'))==prep['nativeProbeSha256']
    product=read(ROOT/'analysis/farm-prompt-recovery-20261018/validation.json')
    assert product['backendSourceHash']==prep['backendSourceHash']
    assert all(sha(ROOT/name)==digest for name,digest in product['sources'].items())
    record_commit=subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),'rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    validation=dict(recordCommit=record_commit,productSourceCommit=product['sourceCommit'],
        backendSourceHash=prep['backendSourceHash'],nativeSha256=prep['nativeSha256'],nativeProbeSha256=prep['nativeProbeSha256'],
        requestId=native['requestId'],acceptance=acceptance,preparationChecks=prep['offlineTests'],
        protectedFilesUnchanged=len(protected),promptRecoveryLiveValidated=True,
        existingTestDraftSaveReopenValidated=True,generalUnattendedProductAccepted=False,
        publishing=False,messaging=False,desktopControl=False,inputDevices=['C24C'],
        installedReleaseChanged=False,restoration=restored,
        wrapperSha256=sha(HERE/'test_backend.py'),sourceHashes=product['sources'])
    (HERE/'validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
    copies={'source/'+name:ROOT/name for name in product['sources']}
    for file in HERE.rglob('*'):
        if file.is_file() and '__pycache__' not in file.parts and file.name!='archive-summary.json':
            copies['record/'+file.relative_to(HERE).as_posix()]=file
    probe=Path(prep['nativeProbe'])
    for path in probe.parent.glob('NativeProbe.*'):
        if path.is_file(): copies['native-driver/'+path.name]=path
    ARCHIVE.mkdir(exist_ok=False)
    rows=[]
    for name,source in sorted(copies.items()):
        target=ARCHIVE/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,target)
        assert sha(source)==sha(target)
        rows.append((name,sha(target),target.stat().st_size))
    manifest=ARCHIVE/'SHA256SUMS.txt'
    manifest.write_text(''.join(digest+'  '+name+'\n' for name,digest,_ in rows),encoding='utf-8',newline='\n')
    assert all(sha(ARCHIVE/name)==digest for name,digest,_ in rows)
    summary=dict(path=str(ARCHIVE),files=len(rows),bytes=sum(size for _,_,size in rows),verified=True,
        manifestSha256=sha(manifest),recordCommit=record_commit,requestId=native['requestId'],
        nativeCandidatePreservedInPriorIntegrationArchive=True)
    (HERE/'archive-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary))

if __name__=='__main__': main()
