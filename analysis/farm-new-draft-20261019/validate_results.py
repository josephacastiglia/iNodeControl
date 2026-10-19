"""Validate retained real evidence and final source provenance without sockets."""
import ast
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

record=Path(__file__).resolve().parent;root=record.parents[1]
sys.path.insert(0,str(root/'tools'))
from farm_creation_runs import CreationRuns

def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
prep=read(record/'attempt-15-preparation.json')
acceptance=read(record/'acceptance-attempt-15.json')
assert acceptance['accepted'] and acceptance['history'] and len(acceptance['history'])==1
assert read(record/'python-tests-final.json')['passed'] and read(record/'metadata-tests.json')['passed']
assert sha(prep['nativeAssembly'])==prep['nativeSha256']
names=sorted(p.name for p in (record/'attempt-15-source').iterdir() if p.is_file())
changed=[n for n in names if sha(record/'attempt-15-source'/n)!=sha(root/'tools'/n)]
assert changed==['farm_creation_runs.py']
def without_get(path):
    tree=ast.parse(path.read_text(encoding='utf-8'))
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='CreationRuns')
    cls.body=[n for n in cls.body if not (isinstance(n,ast.FunctionDef) and n.name=='get')]
    return ast.dump(tree,include_attributes=False)
assert without_get(record/'attempt-15-source/farm_creation_runs.py')==without_get(root/'tools/farm_creation_runs.py')
tree=ast.parse((root/'tools/imouse_farm_server.py').read_text(encoding='utf-8'))
assignment=next(n for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Attribute) and t.attr=='source_hash' for t in n.targets))
ordered=ast.literal_eval(next(n for n in ast.walk(assignment.value) if isinstance(n,ast.Tuple)))
final_hash=hashlib.sha256(b''.join((root/'tools'/name).read_bytes() for name in ordered)).hexdigest()
backend=root/'output/candidate-runs/farm-new-draft-20261019/backend'

class ReadOnlyJobs:
    def get(self,key):
        with sqlite3.connect('file:'+str(backend/'jobs.db').replace('\\','/')+'?mode=ro',uri=True) as db:
            return json.loads(db.execute('SELECT record FROM farm_jobs WHERE id=?',(key,)).fetchone()[0])
class ReadOnlyDrafts:
    def get(self,key):
        with sqlite3.connect('file:'+str(backend/'carousel-drafts.db').replace('\\','/')+'?mode=ro',uri=True) as db:
            return json.loads(db.execute('SELECT document FROM carousel_drafts WHERE id=?',(key,)).fetchone()[0])
service=object.__new__(CreationRuns);service.folder=backend/'draft-creations';service.jobs=ReadOnlyJobs();service.drafts=ReadOnlyDrafts();service.config=None
with sqlite3.connect(service.folder/'runs.db') as db:service.store_id=db.execute('SELECT id FROM identity').fetchone()[0]
path=service.folder/acceptance['runId']/'record.json';original=sha(path)
value=service.get(acceptance['runId'])
assert value['savedDraftVerified'] and value['state']=='verified' and value['workflow']['createdDraftVerified']
assert value['workflow']['finalInput']['generation']==18 and value['workflow']['creationFinalInput']['generation']==17
assert sha(path)==original
(record/'final-result-readonly.json').write_text(json.dumps(dict(id=value['id'],state=value['state'],
    cleanup=value['cleanup'],savedDraftVerified=value['savedDraftVerified'],finalInput=value['workflow']['finalInput'],
    creationFinalInput=value['workflow']['creationFinalInput'],recordUnchanged=True),indent=2),encoding='utf-8')
protected=read(record/'protected-files.json');assert all(sha(path)==value['sha256'] for path,value in protected.items())
assert read(record/'restoration.json')['restored']
native=read(record/'native-checks-attempt-10.json')
git=['git','-c','safe.directory='+root.as_posix()]
commit=subprocess.check_output(git+['rev-parse','HEAD'],cwd=root,text=True).strip()
source_hashes={'tools/'+name:sha(root/'tools'/name) for name in ordered}
native_hashes={p.relative_to(root).as_posix():sha(p) for p in (root/'src/iMouse.Console').rglob('*')
    if p.is_file() and p.suffix in ('.cs','.xaml','.csproj') and not {'bin','obj'}.intersection(p.parts)}
result=dict(priority1ScopedAccepted=True,productSourceCommit='0ada6fd',finalSourceCommit=commit,
    liveBackendSourceHash=prep['backendSourceHash'],finalBackendSourceHash=final_hash,
    onlyPostLiveProductChange='Read-only get() presents the later verifier release state and retains creationFinalInput; original journals are unchanged.',
    inputImplementationUnchangedAfterLive=True,sourceHashes=source_hashes,nativeSourceHashes=native_hashes,
    nativeSha256=prep['nativeSha256'],nativeTests=len(native['tests']),fullRegression=read(record/'python-tests-final.json'),
    metadataRegression=read(record/'metadata-tests.json'),nativeDriverAssertions=acceptance['nativeAssertions'],
    freshRunId=acceptance['runId'],freshRunActions=acceptance['semanticActions'],freshRunFrames=len(acceptance['images']),
    protectedFilesUnchanged=len(protected),restoredStoppedState=True,publishing=False,messaging=False,desktopControl=False,
    inputDevices=['C24C'],generalUnattendedProductAccepted=False)
(record/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(dict(validated=True,finalSourceCommit=commit,finalBackendSourceHash=final_hash,readOnlyResultCorrect=True)))
