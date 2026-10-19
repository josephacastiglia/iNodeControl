"""Preserve this session's evidence, exact source and binaries without uploading."""
import hashlib
import json
from pathlib import Path
import shutil

record=Path(__file__).resolve().parent;root=record.parents[1]
archive=root.parent/'iMouseXP-2.0-evidence-archive/20261019-farm-new-draft'
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
validation=read(record/'validation.json');prep=read(record/'attempt-15-preparation.json')
assert validation['priority1ScopedAccepted'] and validation['inputImplementationUnchangedAfterLive']
assert read(record/'after-tests-state.json')['clear'] and read(record/'restoration.json')['restored']
assert all(sha(root/name)==digest for name,digest in validation['sourceHashes'].items())
assert all(sha(root/name)==digest for name,digest in validation['nativeSourceHashes'].items())
assert sha(prep['nativeAssembly'])==prep['nativeSha256']
assert all(sha(path)==value['sha256'] for path,value in read(record/'protected-files.json').items())
assert read(record/'launcher-final-live-validation.json')['SourceHash']==validation['finalBackendSourceHash']
assert read(record/'launcher-final-sim-validation.json')['StartsProcesses'] is False
copies={}
for file in record.rglob('*'):
    if file.is_file() and not {'__pycache__','obj','bin'}.intersection(file.relative_to(record).parts) and file.name!='archive-summary.json':
        copies['record/'+file.relative_to(record).as_posix()]=file
for name in validation['sourceHashes']|validation['nativeSourceHashes']:
    copies['source/'+name]=root/name
for name in ('MARKETING-FARM-STATUS.md','MARKETING-FARM-ACCEPTANCE.md','Open Marketing Farm Candidate.ps1'):
    copies['source/'+name]=root/name
backend=root/'output/candidate-runs/farm-new-draft-20261019/backend'
for file in backend.rglob('*'):
    if file.is_file():copies['backend/'+file.relative_to(backend).as_posix()]=file
for tag,path in [('native',Path(prep['nativeAssembly']).parent),('native-driver',Path(prep['nativeProbe']).parent),('kernel',Path(prep['kernel']).parent)]:
    for file in path.iterdir():
        if file.is_file() and file.suffix in ('.exe','.dll','.pdb','.json'):copies[tag+'/'+file.name]=file
qa=Path(prep['nativeAssembly']).parent/'qa'
for file in qa.rglob('*'):
    if file.is_file():copies['native-qa/'+file.relative_to(qa).as_posix()]=file
archive.mkdir(exist_ok=False)
rows=[]
for name,source in sorted(copies.items()):
    target=archive/name
    assert target.resolve().is_relative_to(archive.resolve())
    target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    digest=sha(source);assert sha(target)==digest
    rows.append((name,digest,target.stat().st_size))
manifest=archive/'SHA256SUMS.txt'
manifest.write_text(''.join(digest+'  '+name+'\n' for name,digest,_ in rows),encoding='utf-8',newline='\n')
assert all(sha(archive/name)==digest for name,digest,_ in rows)
summary=dict(path=str(archive),files=len(rows),bytes=sum(size for _,_,size in rows),verified=True,
    manifestSha256=sha(manifest),sourceCommit=validation['finalSourceCommit'],freshRunId=validation['freshRunId'],
    uploadPerformed=False,includesHeldAttempts=True,includesExactNativeAndKernel=True)
(record/'archive-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary))
