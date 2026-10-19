"""Create preservation commits using alternate indexes; never modify a checkout."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
plan=json.loads((HERE/'publication-plan.json').read_bytes())
scan=json.loads((HERE/'security-scan.json').read_bytes())
if not scan['passed'] or not scan.get('genericReviewResolved'):raise RuntimeError('Security review is incomplete.')
report=[]
def sha(raw):return hashlib.sha256(raw).hexdigest()
def git(root,*args,data=None,env=None,check=True):
    r=subprocess.run(['git','-C',str(root),'-c','safe.directory='+Path(root).as_posix(),*args],input=data,capture_output=True,env=env)
    if check and r.returncode:raise RuntimeError(f'Git {args[0]} failed: '+r.stderr.decode('utf-8','replace')[:400])
    return r.stdout
for entry in plan['plans']:
    root=Path(entry['worktree'])
    if git(root,'rev-parse','HEAD').decode().strip()!=entry['base']:raise RuntimeError('A worktree advanced during audit.')
    branch='refs/heads/'+entry['branch']
    if git(root,'rev-parse','--verify',branch,check=False):raise RuntimeError('Preservation branch already exists; do not overwrite.')
    index=Path(git(root,'rev-parse','--path-format=absolute','--git-path','index').decode().strip())
    index_before=sha(index.read_bytes())
    staged_before=git(root,'diff','--cached','--binary')
    for item in entry['files']:
        if sha(Path(item['source']).read_bytes())!=item['sha256']:raise RuntimeError('A selected source changed during review.')
    task_env=os.environ.copy()
    task_index=HERE/('index-'+root.name)
    if task_index.exists():raise RuntimeError('Alternate index already exists; preserve it for review.')
    task_env['GIT_INDEX_FILE']=str(task_index)
    git(root,'read-tree',entry['base'],env=task_env)
    sources=[Path(item['source']).as_posix() for item in entry['files']]
    if any('\n' in value or '\r' in value for value in sources):raise RuntimeError('Unexpected source filename.')
    oids=git(root,'hash-object','-w','--no-filters','--stdin-paths',data=('\n'.join(sources)+'\n').encode(),env=task_env).decode().splitlines()
    if len(oids)!=len(sources):raise RuntimeError('Not every selected source was written.')
    entries=[]
    manifest=[]
    for item,oid in zip(entry['files'],oids):
        raw=Path(item['source']).read_bytes()
        if sha(raw)!=item['sha256'] or hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=oid:
            raise RuntimeError('A source changed while its blob was written.')
        manifest.append({key:item[key] for key in ('path','bytes','sha256','tracked')})
        entries.append(('100644 '+oid+'\t'+item['path']).encode()+b'\0')
    note=f'''# Preserved project work — 19 October 2026

This is a preservation branch, **not a tested release or an integration merge**.
It records {len(entry['files'])} selected files from `{root.name}` at base
`{entry['base']}`. The original checkout, index and branch remain unchanged.

The current integrated source is on `local/combined-candidate-20261012`.
Read its `MARKETING-FARM-STATUS.md` and `RESUME-NEXT.md` before development.
Do not reapply this entire snapshot over that candidate: it includes historical,
experimental and negative-control source versions.

Source, scripts, handoffs and safe text evidence are retained byte-for-byte.
The file manifest is `analysis/cross-agent-preservation-20261019/{root.name}-files.json`.
Phone captures, SQLite/session stores, binaries, build trees, toolchain caches
and unrelated nested websites remain local. Their omission is deliberate.
The unredacted `backup/*` branch must never be pushed.

The original Gemini installer `tools/setup_imouse_farm.py`, if present here, is
an obsolete preservation artifact: running it can overwrite the hardened source.
Its claims and historical handoff claims are not current acceptance results.
The dedicated Orca/Gemini export has its account header redacted; the exact
original stays in the private local evidence archive.

No deployment, promotion, phone input, release edit or main-branch merge is made
by preserving this work. Use Git with `core.autocrlf=false` when verifying the
manifest against a new checkout, or hash the stored blobs directly.
'''
    extra={
        'PRESERVATION-NOTES-20261019.md':note.encode(),
        'analysis/cross-agent-preservation-20261019/'+root.name+'-files.json':json.dumps(manifest,indent=2).encode(),
    }
    for name,raw in extra.items():
        oid=git(root,'hash-object','-w','--stdin',data=raw,env=task_env).decode().strip()
        entries.append(('100644 '+oid+'\t'+name).encode()+b'\0')
    git(root,'update-index','-z','--index-info',data=b''.join(entries),env=task_env)
    tree=git(root,'write-tree',env=task_env).decode().strip()
    message=('Preserve cross-agent '+root.name+' work without altering its checkout\n\nSnapshot for the iNodeControl cross-agent backup audit. Unreviewed historical work stays separate from the integrated candidate.\n').encode()
    commit=git(root,'commit-tree',tree,'-p',entry['base'],data=message,env=task_env).decode().strip()
    git(root,'update-ref',branch,commit,'0'*40)
    if index_before!=sha(index.read_bytes()) or staged_before!=git(root,'diff','--cached','--binary'):
        raise RuntimeError('Original index changed; preserve all records for review.')
    if git(root,'rev-parse','HEAD').decode().strip()!=entry['base']:raise RuntimeError('Original HEAD changed.')
    for item in entry['files']:
        if sha(Path(item['source']).read_bytes())!=item['sha256']:raise RuntimeError('Original file changed during snapshot.')
    value=dict(branch=entry['branch'],commit=commit,base=entry['base'],tree=tree,selectedFiles=len(entry['files']),bytes=sum(f['bytes'] for f in entry['files']),originalIndexUnchanged=True,originalHeadUnchanged=True,originalFilesUnchanged=True)
    report.append(value)
    (HERE/'snapshot-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(value),flush=True)
root=HERE.parent/'iMouseXP-2.0'
orphan='b946b942c82d909d0594ebdd22bb012d9b211753'
branch='refs/heads/handoff/orca-coordinator-reflog-20261002'
if git(root,'rev-parse','--verify',branch,check=False):raise RuntimeError('Reflog preservation ref already exists.')
git(root,'update-ref',branch,orphan,'0'*40)
print(json.dumps(dict(branch=branch,commit=orphan,reflogCommitPreserved=True)),flush=True)
