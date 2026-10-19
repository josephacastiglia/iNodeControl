"""Preserve the tested Python candidate and its dependencies; no runtime startup."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
ARCHIVE=ROOT.parent/'iMouseXP-2.0-evidence-archive/20261018-farm-prompt-recovery'

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    tests=json.loads((HERE/'tests.json').read_text(encoding='utf-8'))
    assert tests['passed'] and tests['tests']==106 and not tests['skipped']
    assert tests['expectedControlFailures']==2
    commit=subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),'rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    tree=ast.parse((ROOT/'tools/imouse_farm_server.py').read_text(encoding='utf-8'))
    names=None
    for node in ast.walk(tree):
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Attribute) and t.attr=='source_hash' for t in node.targets):
            names=ast.literal_eval(next(n for n in ast.walk(node.value) if isinstance(n,ast.Tuple))); break
    assert names and 'farm_draft_workflow.py' in names
    sources={'tools/'+name:sha(ROOT/'tools'/name) for name in names}
    protected=json.loads((ROOT/'analysis/farm-interface-live-20261018/protected-files.json').read_text(encoding='utf-8'))
    assert all(sha(Path(path))==value['sha256'] for path,value in protected.items())
    native=ROOT/'output/codex-farm-interface-20261018/iMouse2.dll'
    assert sha(native)=='effa8083c8c71a7f1522cfaf9765de315e6bca9c18891c2a1bd42822bf49570a'
    backend_hash=hashlib.sha256(b''.join((ROOT/'tools'/name).read_bytes() for name in names)).hexdigest()
    validation=dict(sourceCommit=commit,backendSourceHash=backend_hash,sources=sources,
        nativeSourceCommit='6dae91a05f63a05d86ea06360db8835c676cd85e',nativeDllSha256=sha(native),
        nativeUnchanged=True,pythonTests=tests,protectedFilesUnchanged=len(protected),
        promptRecoveryLiveValidated=False,liveSaveReopenAccepted=False,
        installedReleaseChanged=False,publishing=False,messaging=False,desktopControl=False,
        priorLiveArchive=json.loads((ROOT/'analysis/farm-interface-live-20261018/final-archive-summary.json').read_text(encoding='utf-8')))
    (HERE/'validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
    copies={'source/'+name:ROOT/name for name in sources}
    for path in HERE.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.name!='archive-summary.json':
            copies['record/'+path.relative_to(HERE).as_posix()]=path
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
        manifestSha256=sha(manifest),sourceCommit=commit,backendSourceHash=backend_hash,
        retainedPhoneFramesRemainInPriorArchives=True)
    (HERE/'archive-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary))

if __name__=='__main__': main()
