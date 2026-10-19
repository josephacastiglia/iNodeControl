"""Scan unpublished history and selected files without printing matched values."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zlib

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent/'iMouseXP-2.0'
GIT=['git','-C',str(ROOT),'-c','safe.directory='+ROOT.as_posix()]
def git(*args):return subprocess.check_output(GIT+list(args))
plan=json.loads((HERE/'publication-plan.json').read_bytes())
refs=[r.decode() for r in git('for-each-ref','--format=%(refname)','refs/heads').splitlines() if not r.startswith(b'refs/heads/backup/')]
refs.append('b946b942c82d909d0594ebdd22bb012d9b211753')
private=set(git('rev-list','backup/input-timeout-integration-pre-redaction','--not','8731eb7').splitlines())
unsafe=[]
for ref in refs:
    if private.intersection(git('rev-list',ref).splitlines()):unsafe.append(ref)
diff=git('diff','--no-ext-diff','--unified=0','backup/input-timeout-integration-pre-redaction','8731eb7','--','analysis/accessory-connection-20260927/README.md').decode('utf-8','replace')
removed='\n'.join(s[1:] for s in diff.splitlines() if s.startswith('-') and not s.startswith('---'))
added='\n'.join(s[1:] for s in diff.splitlines() if s.startswith('+') and not s.startswith('+++'))
personal=set(re.findall(r'(?<![A-Za-z0-9])(?:[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16}|[A-Za-z0-9]{12,64})(?![A-Za-z0-9])',removed))-set(re.findall(r'[A-Za-z0-9-]{12,64}',added))
personal={s for s in personal if any(c.isdigit() for c in s)}
if not personal:raise RuntimeError('Known withheld identifier could not be derived; do not push unreviewed history.')
patterns={
    'github_token':rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})',
    'openai_key':rb'sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{30,}',
    'aws_access_key':rb'(?:AKIA|ASIA)[A-Z0-9]{16}',
    'slack_token':rb'xox[baprs]-[A-Za-z0-9-]{20,}',
    'private_key':rb'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----',
}
findings=[];generic=[];scanned=0;total=0;payloads=0
def scan(raw,name):
    global scanned,total
    scanned+=1;total+=len(raw)
    for secret in personal:
        if any(encoded.lower() in raw.lower() for encoded in (secret.encode(),secret.encode('utf-16-le'),secret.encode('utf-16-be'))):
            findings.append(dict(path=name,kind='withheld_personal_identifier'))
    for kind,pattern in patterns.items():
        for match in re.finditer(pattern,raw):findings.append(dict(path=name,kind=kind,line=raw[:match.start()].count(b'\n')+1))
    # Human-review candidates only: fixture placeholders are not proof of a key.
    pattern=rb'''(?i)["']?(?:password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret)["']?\s*[:=]\s*["']([^"'\r\n]{8,})["']'''
    for match in re.finditer(pattern,raw):
        literal=match.group(1)
        if literal.startswith((b'os.',b'http',b'$',b'<')) or literal in (b'api_key',b'password',b'test-secret',b'not-configured'):continue
        generic.append(dict(path=name,line=raw[:match.start()].count(b'\n')+1,characters=len(literal),valueSha256=hashlib.sha256(literal).hexdigest()))

objects={}
for line in git('rev-list','--objects',*refs,'--not','--remotes=origin').splitlines():
    oid,_,name=line.partition(b' ');objects[oid.decode()]=name.decode('utf-8','replace')
info=subprocess.check_output(GIT+['cat-file','--batch-check'],input=''.join(key+'\n' for key in objects).encode())
blobs=[];large=[]
for line in info.splitlines():
    oid,kind,size=line.split();oid=oid.decode()
    if kind==b'blob':
        if int(size)>90*1024*1024:large.append(dict(oid=oid,path=objects[oid],bytes=int(size)))
        blobs.append(oid)
batch=subprocess.check_output(GIT+['cat-file','--batch'],input=''.join(key+'\n' for key in blobs).encode())
offset=0
for oid in blobs:
    end=batch.index(b'\n',offset);header=batch[offset:end].split();size=int(header[2]);start=end+1
    raw=batch[start:start+size];offset=start+size+1
    scan(raw,'git:'+oid+':'+objects[oid])
for item in [f for p in plan['plans'] for f in p['files']]:
    raw=Path(item['source']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise RuntimeError('A selected file changed: '+item['source'])
    scan(raw,item['source'])

# The original Gemini installer embeds compressed code. Treat it as data;
# never import/run the installer just to inspect those source bytes.
installer=HERE.parent/'iMouseXP-2.0-combined-candidate/tools/setup_imouse_farm.py'
def walk(value):
    global payloads
    if isinstance(value,dict):
        if 'zlib_b64' in value:
            raw=zlib.decompress(base64.b64decode(value['zlib_b64']))
            if len(raw)>8*1024*1024:raise RuntimeError('Unexpectedly large embedded installer payload.')
            payloads+=1;scan(raw,'embedded-gemini-installer:'+str(payloads))
        for item in value.values():walk(item)
    elif isinstance(value,list):
        for item in value:walk(item)
tree=ast.parse(installer.read_text(encoding='utf-8-sig'))
for node in ast.walk(tree):
    if isinstance(node,ast.Constant) and isinstance(node.value,str) and len(node.value)>1000:
        try:value=json.loads(node.value)
        except (ValueError,TypeError):continue
        walk(value)
if not payloads:
    for node in tree.body:
        if isinstance(node,(ast.Assign,ast.AnnAssign)):
            try:value=ast.literal_eval(node.value)
            except (ValueError,TypeError):continue
            walk(value)
report=dict(passed=not findings and not unsafe and not large,objects=len(objects),blobs=len(blobs),scanned=scanned,bytes=total,
    knownWithheldIdentifiersChecked=len(personal),unredactedAncestorRefs=unsafe,blockedFindings=findings,genericReview=generic,
    oversizedBlobs=large,embeddedInstallerPayloads=payloads,backupBranchExcluded=True,matchedValuesPrinted=False)
(HERE/'security-scan.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:report[k] for k in ('passed','objects','blobs','scanned','bytes','knownWithheldIdentifiersChecked','unredactedAncestorRefs','blockedFindings','genericReview','oversizedBlobs','embeddedInstallerPayloads')}))
if not report['passed']:raise SystemExit(1)
