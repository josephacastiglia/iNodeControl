"""Preserve completed backend evidence and summarize only recorded live results."""
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

HERE = Path(__file__).resolve().parent
PREP = json.loads((HERE/'preparation.json').read_text(encoding='utf-8'))


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def summarize(attempt):
    terminal = read(attempt/'terminal.json')['run']
    source = Path(PREP['backendData'])/'draft-runs'/terminal['id']
    evidence = attempt/'backend-evidence'
    if not evidence.exists():
        evidence.mkdir()
        for path in source.iterdir():
            if not path.is_file() or path.name.endswith(('-journal','-wal','-shm')): continue
            if path.suffix == '.sqlite3':
                with sqlite3.connect(path.as_uri()+'?mode=ro', uri=True) as original:
                    with sqlite3.connect(evidence/path.name) as copy: original.backup(copy)
            else: shutil.copyfile(path, evidence/path.name)
    workflow = read(evidence/'record.json')
    if workflow != terminal['workflow']: raise ValueError('Terminal response differs from the saved workflow.')
    observations = [o for o in workflow['observations'] if o.get('state') == 'observed']
    for observation in observations:
        frame = (evidence/observation['frame']).read_bytes()
        if hashlib.sha256(frame).hexdigest() != observation['observation']['reviewFrameSha256']:
            raise ValueError('Retained frame checksum changed.')
    http = [json.loads(line) for line in (attempt/'http.jsonl').read_text(encoding='utf-8').splitlines()]
    checks = read(attempt/'checks.json')
    native = read(attempt/'result.json') if (attempt/'result.json').exists() else None
    return dict(requestId=terminal['id'], storeId=terminal['storeId'], state=terminal['state'],
        reason=terminal['reason'], savedDraftVerified=terminal['savedDraftVerified'],
        jobStatus=terminal['jobStatus'], cleanup=terminal['cleanup'],
        nativeDriverPassed=native is not None and native['passed'],
        nativeChecksPassed=sum(c['pass'] for c in checks), nativeChecksFailed=[c['name'] for c in checks if not c['pass']],
        submissionCount=sum(h['method']=='POST' and h['route']=='/api/farm/draft-runs' for h in http),
        cancellationCount=sum(h['method']=='POST' and h['route'].endswith('/cancel') for h in http),
        actionCount=len(workflow['actions']), actionStates=[dict(label=a['label'],state=a['state']) for a in workflow['actions']],
        saveCommands=[c for c in workflow['commands'] if 'save-once' in c['purpose']],
        observedFrames=len(observations), exportedImagesVerified=len(observations),
        maxAgeAtCaptureMs=max((o['observation']['frameEvidence']['ageUpperBoundMs'] for o in observations), default=None),
        accountHistory=workflow.get('accountHistory'), finalInput=workflow.get('finalInput'),
        publishing=False, messaging=False, desktopControl=False,
        source=workflow['source'], nativeWindowHandles=native['windowHandles'] if native else None)


results = {attempt.name:summarize(attempt) for attempt in sorted(HERE.glob('live-*'))
           if (attempt/'terminal.json').exists()}
(HERE/'live-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps({name:{key:value[key] for key in ('state','reason','savedDraftVerified','cleanup','submissionCount','actionCount','observedFrames')}
                  for name,value in results.items()}))
