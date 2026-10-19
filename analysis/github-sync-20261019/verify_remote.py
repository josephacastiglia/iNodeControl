"""Verify live GitHub refs and selected stored file bytes after the scoped push."""
import base64
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import quote

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent/'iMouseXP-2.0'
GIT=['git','-C',str(ROOT),'-c','safe.directory='+ROOT.as_posix()]
def git(*args):return subprocess.check_output(GIT+list(args))
def api(path,*args):return json.loads(subprocess.check_output(['gh','api',path,*args]))
metadata=json.loads(subprocess.check_output(['gh','repo','view','josephacastiglia/iNodeControl','--json','nameWithOwner,isPrivate,url,defaultBranchRef']))
assert metadata['isPrivate'] and metadata['nameWithOwner']=='josephacastiglia/iNodeControl' and metadata['defaultBranchRef']['name']=='main'
remote={row['name']:row['commit']['sha'] for row in api('repos/josephacastiglia/iNodeControl/branches?per_page=100')}
local={}
for row in git('for-each-ref','--format=%(refname) %(objectname)','refs/heads').decode().splitlines():
    name,oid=row.split();name=name.removeprefix('refs/heads/')
    if name.startswith('backup/'):continue
    local[name]=oid
assert all(remote.get(name)==oid for name,oid in local.items())
assert not any(name.startswith('backup/') for name in remote)
before=json.loads((HERE/'push-intent.json').read_bytes())['before']
assert remote['main']==before['refs/heads/main']=='ee445d70e5f7e3cd9497a9162fc89ba9f6061e4a'
assert all(name.removeprefix('refs/heads/') in remote for name in before)
files=[
    ('local/combined-candidate-20261012','GITHUB-SYNC-20261019.md'),
    ('local/combined-candidate-20261012','tools/farm_draft_recovery.py'),
    ('handoff/gemini-and-local-records-20261019','analysis/cross-agent-preservation-20261019/orca-imouse2-automations/ANTIGRAVITY_CHAT_EXPORT.md'),
    ('handoff/orca-working-tree-20261019','src/iMouse.Console/LiveFrame.cs'),
    ('handoff/fka-probe-working-tree-20261019','src/iMouse.Kernel/InputRouter.cs'),
]
checks=[]
for branch,name in files:
    value=api('repos/josephacastiglia/iNodeControl/contents/'+quote(name,safe='/'),'--method','GET','-f','ref='+branch)
    remote_bytes=base64.b64decode(value['content'])
    local_bytes=git('show',local[branch]+':'+name)
    assert remote_bytes==local_bytes
    if name.endswith('ANTIGRAVITY_CHAT_EXPORT.md'):
        assert b'**Account:** (withheld: account identifier)' in remote_bytes
    checks.append(dict(branch=branch,path=name,gitBlob=value['sha'],sha256=hashlib.sha256(remote_bytes).hexdigest(),byteExact=True))
report=dict(verified=True,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),repository=metadata,
    githubBranches=remote,localBranchesMatched=len(local),remoteBranchCount=len(remote),criticalFileChecks=checks,
    mainUnchanged=True,allOriginalRemoteBranchesRemain=True,backupBranchAbsent=True,
    publicationRound='initial cross-agent push; later documentation-only verification commit is checked separately')
(HERE/'remote-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(dict(verified=True,localBranchTipsMatched=len(local),githubBranches=len(remote),fileBytesVerified=len(checks),mainUnchanged=True,backupBranchAbsent=True)))
