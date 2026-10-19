"""Verify each selected source byte against the preservation commit's Git blobs."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent/'iMouseXP-2.0'
GIT=['git','-C',str(ROOT),'-c','safe.directory='+ROOT.as_posix()]
def git(*args,data=None):return subprocess.check_output(GIT+list(args),input=data)
plan=json.loads((HERE/'publication-plan.json').read_bytes())
snaps=json.loads((HERE/'snapshot-results.json').read_bytes())
verify=[]
for entry,snapshot in zip(plan['plans'],snaps):
    assert entry['branch']==snapshot['branch']
    tree={}
    for line in git('ls-tree','-r','-z',snapshot['commit']).split(b'\0'):
        if not line:continue
        info,name=line.split(b'\t',1);mode,kind,oid=info.split()
        if kind==b'blob':tree[name.decode()]=oid.decode()
    oids=list(dict.fromkeys(tree[item['path']] for item in entry['files']))
    raw=git('cat-file','--batch',data=''.join(oid+'\n' for oid in oids).encode())
    offset=0;hashes={}
    for oid in oids:
        end=raw.index(b'\n',offset);header=raw[offset:end].split();size=int(header[2]);start=end+1
        hashes[oid]=hashlib.sha256(raw[start:start+size]).hexdigest();offset=start+size+1
    for item in entry['files']:
        assert hashes[tree[item['path']]]==item['sha256'], item['path']
        assert hashlib.sha256(Path(item['source']).read_bytes()).hexdigest()==item['sha256'], item['source']
    verify.append(dict(branch=entry['branch'],commit=snapshot['commit'],files=len(entry['files']),allGitBlobsByteExact=True,originalFilesUnchanged=True))
value=dict(passed=True,files=sum(v['files'] for v in verify),snapshots=verify)
(HERE/'snapshot-verification.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
print(json.dumps(dict(passed=True,files=value['files'],snapshots=len(verify))))
