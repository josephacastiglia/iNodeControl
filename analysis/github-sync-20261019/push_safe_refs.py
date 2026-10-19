"""Push only exact reviewed refs; never --all, --mirror, force or backup/* refs."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent/'iMouseXP-2.0'
GIT=['git','-C',str(ROOT),'-c','safe.directory='+ROOT.as_posix()]
def git(*args):return subprocess.check_output(GIT+list(args)).decode().strip()
scan=json.loads((HERE/'security-scan.json').read_bytes())
if not scan['passed'] or scan['blockedFindings']:raise RuntimeError('Unreviewed content cannot be pushed.')
known={'effb526f457597fe3b9e1dfa4a6e0b1635bf19e444ba6fd65eba449048ee4cca','b3c53c08828847f11b3083a5b1fa83ddf6751112653f0fd9d563754092ec65f7'}
if any(v['valueSha256'] not in known for v in scan['genericReview']):raise RuntimeError('A new literal needs review.')
if git('remote','get-url','origin')!='https://github.com/josephacastiglia/iNodeControl.git':raise RuntimeError('Unexpected destination repository.')
refs={}
for line in git('for-each-ref','--format=%(refname) %(objectname)','refs/heads').splitlines():
    name,oid=line.split()
    if name.startswith('refs/heads/backup/'):continue
    refs[name]=oid
remote={line.split('\t')[1]:line.split('\t')[0] for line in git('ls-remote','--heads','origin').splitlines()}
if any(name.startswith('refs/heads/backup/') for name in remote):raise RuntimeError('A backup branch is already remote; report it, do not delete or overwrite.')
updates={name:oid for name,oid in refs.items() if remote.get(name)!=oid}
for name,oid in updates.items():
    if name in remote:
        if subprocess.run(GIT+['merge-base','--is-ancestor',remote[name],oid],capture_output=True).returncode:
            raise RuntimeError('Remote branch diverged; never force it: '+name)
intent=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),repository='josephacastiglia/iNodeControl',
    updates=updates,before=remote,excludedBackup=True,atomic=True,force=False)
(HERE/'push-intent.json').write_text(json.dumps(intent,indent=2),encoding='utf-8')
if not updates:
    print(json.dumps(dict(upToDate=True)));raise SystemExit(0)
if sys.argv[1:] not in (['--dry-run'],['--push']):raise RuntimeError('Choose --dry-run or --push explicitly.')
args=['push','--atomic','--porcelain']
if sys.argv[1]=='--dry-run':args.append('--dry-run')
args+=['origin']+[name+':'+name for name in updates]
result=subprocess.run(GIT+args,capture_output=True,text=True)
kind='dry-run' if sys.argv[1]=='--dry-run' else 'push'
(HERE/(kind+'.stdout.txt')).write_text(result.stdout,encoding='utf-8')
(HERE/(kind+'.stderr.txt')).write_text(result.stderr,encoding='utf-8')
print(result.stdout)
if result.stderr:print(result.stderr,file=sys.stderr)
if result.returncode:raise SystemExit(result.returncode)
print(json.dumps(dict(stage=kind,refs=len(updates),backupPushed=False,force=False)))
