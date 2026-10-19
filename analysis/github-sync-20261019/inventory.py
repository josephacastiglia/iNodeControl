"""Read-only Git inventory for the explicitly requested cross-agent push audit."""
import collections
import datetime
import json
from pathlib import Path
import subprocess
from urllib.parse import urlsplit,urlunsplit

HERE=Path(__file__).resolve().parent
WORKSPACE=HERE.parent
EXPECTED='josephacastiglia/iNodeControl'
SINCE='2026-09-28T00:00:00-04:00'

def git(path,*args,check=True,raw=False):
    result=subprocess.run(['git','-C',str(path),'-c','safe.directory='+str(path).replace('\\','/'),*args],capture_output=True)
    if check and result.returncode:raise RuntimeError(f'Git {args[0]} failed in {path}: '+result.stderr.decode('utf-8','replace')[:400])
    return result.stdout if raw else result.stdout.decode('utf-8','replace').strip()

def safe_url(value):
    if value.startswith('git@'):return value
    parsed=urlsplit(value)
    return urlunsplit((parsed.scheme,parsed.netloc.split('@')[-1],parsed.path,'',''))

def worktrees(path):
    values=[];value={}
    for line in (git(path,'worktree','list','--porcelain')+'\n\n').splitlines():
        if not line:
            if value:values.append(value);value={}
            continue
        key,_,text=line.partition(' ');value[key]=text or True
    return values

paths=[WORKSPACE/name for name in ('iMouseXP-2.0','iMouseXP-2.0-combined-candidate','iMouseXP-2.0-fka-passthrough-probe','installed-marketing')]
repos=[];seen=set();extra=[]
for path in paths:
    if not (path/'.git').exists():
        if path.exists():extra.append(dict(path=str(path),topLevel=[p.name for p in path.iterdir()]))
        continue
    common=git(path,'rev-parse','--path-format=absolute','--git-common-dir')
    if common in seen:continue
    seen.add(common)
    refs=[]
    for line in git(path,'for-each-ref','--format=%(refname)%00%(objectname)%00%(upstream)%00%(committerdate:iso-strict)%00%(subject)','refs/heads','refs/remotes','refs/tags').splitlines():
        name,oid,upstream,date,subject=line.split('\0',4)
        refs.append(dict(name=name,oid=oid,upstream=upstream,date=date,subject=subject,withheld=name.startswith('refs/heads/backup/')))
    remote_names=git(path,'remote').splitlines()
    remotes={name:safe_url(git(path,'remote','get-url',name)) for name in remote_names}
    checked=[]
    for tree in worktrees(path):
        target=Path(tree['worktree'])
        if not target.exists():tree['missing']=True;checked.append(tree);continue
        status=git(target,'status','--porcelain=v1','-z','--untracked-files=all',raw=True)
        # NUL-delimited parsing preserves spaces and quoted filenames.
        pieces=status.split(b'\0');items=[];index=0
        while index<len(pieces):
            piece=pieces[index];index+=1
            if not piece:continue
            state=piece[:2].decode();name=piece[3:].decode('utf-8','replace')
            row=dict(state=state,path=name)
            if 'R' in state or 'C' in state:
                row['from']=pieces[index].decode('utf-8','replace');index+=1
            file=target/name
            if file.is_file():row['bytes']=file.stat().st_size
            items.append(row)
        tree.update(changes=items,trackedChanges=sum(v['state']!='??' for v in items),untrackedFiles=sum(v['state']=='??' for v in items))
        checked.append(tree)
    stashes=[]
    for line in git(path,'stash','list','--format=%H%x00%gd%x00%gs').splitlines():
        oid,name,subject=line.split('\0',2);stashes.append(dict(oid=oid,name=name,subject=subject))
    recent=list(dict.fromkeys(git(path,'log','--all','--since='+SINCE,'--format=%H').splitlines()))
    reflog=list(dict.fromkeys(git(path,'reflog','--all','--since='+SINCE,'--format=%H').splitlines()))
    repos.append(dict(path=str(path),common=common,remotes=remotes,refs=refs,worktrees=checked,stashes=stashes,recentCommits=recent,recentReflogCommits=reflog))
value=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),since=SINCE,expectedRepository=EXPECTED,repositories=repos,nonGitCandidates=extra)
(HERE/'local-inventory.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
for repo in repos:
    print(json.dumps(dict(path=repo['path'],remotes=repo['remotes'],localBranches=[{k:v[k] for k in ('name','oid','date','withheld')} for v in repo['refs'] if v['name'].startswith('refs/heads/')],
        worktrees=[dict(path=t['worktree'],branch=t.get('branch'),head=t.get('HEAD'),tracked=t.get('trackedChanges'),untracked=t.get('untrackedFiles'),missing=t.get('missing',False)) for t in repo['worktrees']],stashes=repo['stashes'],recentCommits=len(repo['recentCommits']),recentReflogCommits=len(repo['recentReflogCommits']))))
print(json.dumps(dict(nonGitCandidates=extra)))
