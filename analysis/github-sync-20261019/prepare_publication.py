"""Choose project work explicitly; do not stage or alter the original checkouts."""
import collections
import hashlib
import json
from pathlib import Path
import re
import shutil

HERE=Path(__file__).resolve().parent
WORKSPACE=HERE.parent
inventory=json.loads((HERE/'local-inventory.json').read_bytes())
repo=inventory['repositories'][0]
text_extensions={'.cs','.csproj','.py','.ps1','.md','.json','.txt','.xaml','.manifest','.patch','.diff','.c','.cpp','.h','.hpp','.html','.css','.js','.ts','.yaml','.yml','.config','.sln','.toml','.sha256'}
config_names={'.gitignore','.gitattributes','CMakeLists.txt','Makefile','LICENSE','COPYING'}
def sha(raw):return hashlib.sha256(raw).hexdigest()
def reason(name,path):
    parts=Path(name).parts
    if path.is_dir():return 'separate nested repository or directory'
    if not path.is_file():return 'not a regular file'
    if parts[0] in ('output','tmp','sites'):return 'generated output, scratch or unrelated nested site'
    if any(p in ('bin','obj','__pycache__','build') for p in parts):return 'compiler/generated build tree'
    if path.suffix.lower() not in text_extensions and path.name not in config_names:return 'private capture, runtime data or compiled artifact'
    if path.stat().st_size>8*1024*1024:return 'large artifact requires separate review'
    if b'\x00' in path.read_bytes():return 'binary/runtime artifact'
    return None

plans=[]
branches={
    'iMouseXP-2.0':'handoff/orca-working-tree-20261019',
    'iMouseXP-2.0-combined-candidate':'handoff/gemini-and-local-records-20261019',
    'iMouseXP-2.0-fka-passthrough-probe':'handoff/fka-probe-working-tree-20261019',
}
for tree in repo['worktrees']:
    root=Path(tree['worktree'])
    if root.name not in branches:continue
    selected=[];excluded=[]
    for item in tree['changes']:
        name=item['path'];path=root/name
        skip=reason(name,path) if item['state']=='??' else None
        if skip:
            excluded.append(dict(path=name,reason=skip,bytes=item.get('bytes')));continue
        if not path.is_file():raise RuntimeError('A tracked deletion needs explicit preservation: '+name)
        raw=path.read_bytes()
        selected.append(dict(path=name,source=str(path),bytes=len(raw),sha256=sha(raw),tracked=item['state']!='??'))
    plans.append(dict(worktree=str(root),base=tree['HEAD'],originalBranch=tree.get('branch'),branch=branches[root.name],files=selected,excluded=excluded))

# This separate Orca project contains the original Gemini export/handoff, not a
# different implementation. Preserve its account identifier only in the LOCAL copy.
other=Path.home()/'orca/projects/iMouse2Automations'
private=WORKSPACE/'iMouseXP-2.0-evidence-archive/20261019-cross-agent-preservation'
if not private.exists():private.mkdir(parents=True)
external=[]
for name in ('ANTIGRAVITY_CHAT_EXPORT.md','HANDOFF.md'):
    source=other/name
    raw=source.read_bytes()
    target=private/'orca-originals'/name
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and target.read_bytes()!=raw:raise RuntimeError('Never overwrite an original export.')
    if not target.exists():shutil.copy2(source,target)
    assert target.read_bytes()==raw
    text=raw.decode('utf-8-sig')
    cleaned,count=re.subn(r'(?im)^(\*\*Account:\*\*\s*)[^\r\n]*@[^\r\n]*',r'\1(withheld: account identifier)',text)
    dest=HERE/'sanitized-orca-export'/name
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(cleaned,encoding='utf-8',newline='')
    entry=dict(path='analysis/cross-agent-preservation-20261019/orca-imouse2-automations/'+name,
        source=str(dest),bytes=dest.stat().st_size,sha256=sha(dest.read_bytes()),tracked=False,
        originalPath=str(source),originalSha256=sha(raw),accountHeaderRedactions=count)
    external.append(entry)
next(p for p in plans if 'combined-candidate' in p['worktree'])['files'].extend(external)

notes=dict(expectedRepository='josephacastiglia/iNodeControl',since=inventory['since'],plans=plans,
    externalOrcaProject=dict(path=str(other),head='e34251c21d7091c92cb354353b29188cdc06a31a',initialCommitHasNoImplementation=True,uncommittedFiles=2),
    privateOriginalArchive=str(private),excludedUnredactedBranch='backup/input-timeout-integration-pre-redaction',
    unrelatedRepositories=['installed-marketing','sites/keystone-cards'],
    limitations=['Orca runtime unavailable; saved worktrees, handoffs and session project locations were inspected.',
        'Conversation/account memory is not source control; only the dedicated project handoff export is included.',
        'Phone captures, live SQLite/session stores, compiled binaries and toolchain/download caches stay local.'])
(HERE/'publication-plan.json').write_text(json.dumps(notes,indent=2),encoding='utf-8')
for p in plans:print(json.dumps(dict(branch=p['branch'],base=p['base'],selectedFiles=len(p['files']),selectedBytes=sum(f['bytes'] for f in p['files']),trackedChanges=sum(f['tracked'] for f in p['files']),excluded=collections.Counter(f['reason'] for f in p['excluded']))))
print(json.dumps(dict(externalOrcaFiles=len(external),accountHeaderRedactions=sum(f['accountHeaderRedactions'] for f in external),originalsKeptLocal=True)))
