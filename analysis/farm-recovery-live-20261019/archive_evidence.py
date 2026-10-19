"""Preserve stopped live evidence and exact binaries outside Git, without deletion."""
import hashlib
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
prep=load(HERE/'preparation.json')
validation=load(HERE/'validation.json')
assert validation['passed'] and load(HERE/'restoration.json')['restored']
archive=(ROOT.parent/'iMouseXP-2.0-evidence-archive/20261019-farm-recovery-live').resolve()
archive.relative_to(ROOT.parent.resolve())
if archive.exists():raise RuntimeError('Archive already exists; never overwrite evidence.')
archive.mkdir(parents=True)
copied={}
def copy(source,relative):
    source=source.resolve();source.relative_to(ROOT.resolve())
    target=(archive/relative).resolve();target.relative_to(archive)
    if target.exists():raise RuntimeError('Duplicate archive destination: '+relative)
    target.parent.mkdir(parents=True,exist_ok=True)
    digest=sha(source)
    shutil.copy2(source,target)
    if sha(target)!=digest or sha(source)!=digest:raise RuntimeError('Source changed while copying: '+str(source))
    copied[relative]=digest
def tree(source,prefix):
    for path in sorted(source.rglob('*')):
        if path.is_file() and not {'obj','bin','__pycache__'}.intersection(path.relative_to(source).parts):
            copy(path,prefix+'/'+path.relative_to(source).as_posix())
tree(HERE,'live-record')
tree(Path(prep['backendData']),'backend')
run=Path(prep['runDirectory'])
tree(run/'data','kernel-data')
for path in sorted(run.glob('native*-data')):
    if path.is_dir():tree(path,'native-data/'+path.name)
for name in ('MARKETING-FARM-STATUS.md','MARKETING-FARM-ACCEPTANCE.md','.gitattributes'):
    copy(ROOT/name,'reports/'+name)
offline=load(ROOT/'analysis/farm-recovery-20261019/validation.json')
for name,digest in offline['productSourceFiles'].items():
    assert sha(ROOT/name)==digest
    copy(ROOT/name,'source/'+name)
for folder,prefix in (
    (Path(prep['assembly']).parent,'native-candidate'),
    (Path(prep['nativeProbe']).parent,'native-driver'),
    (ROOT/'output/farm-recovery-fault-probe-20261019','reply-loss-driver'),
    (ROOT/'output/farm-recovery-fault-stop-probe-20261019','stop-and-recovery-driver')):
    for path in sorted(folder.iterdir()):
        if path.is_file():copy(path,prefix+'/'+path.name)
kernel=Path(prep['kernel'])
for path in sorted(kernel.parent.glob('iMouse2.Kernel.*')):
    if path.is_file():copy(path,'private-kernel/'+path.name)
metadata=dict(productSourceCommit=validation['productSourceCommit'],nativeSha256=prep['nativeSha256'],kernelSha256=prep['kernelSha256'],
    backendSourceHash=prep['backendSourceHash'],sourceCreationId=prep['creationId'],restored=True,uploaded=False,
    priorOfflineArchive=offline['archive'],meaning='Live records include private screenshots and journals. No installed release or operator settings are copied.')
meta=archive/'ARCHIVE.json'
meta.write_text(json.dumps(metadata,indent=2),encoding='utf-8')
copied['ARCHIVE.json']=sha(meta)
manifest=archive/'SHA256SUMS.txt'
manifest.write_text(''.join(copied[name]+'  '+name+'\n' for name in sorted(copied)),encoding='utf-8')
assert all(sha(archive/name)==digest for name,digest in copied.items())
report=dict(archive=str(archive),files=len(copied),bytes=sum((archive/name).stat().st_size for name in copied),
    manifestSha256=sha(manifest),allCopiesVerified=True,productSourceCommit=validation['productSourceCommit'],
    uploaded=False,initialStoppedStateRestored=True,priorOfflineArchive=offline['archive'])
(HERE/'archive-summary.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
