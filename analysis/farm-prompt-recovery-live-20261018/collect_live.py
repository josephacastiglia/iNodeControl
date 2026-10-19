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

attempt=HERE/'live-save-reopen-with-refresh'
if (attempt/'terminal.json').exists():
    run=read(attempt/'terminal.json')['run']; record=run['workflow']
    marker=read(HERE/'local-delay.json') if (HERE/'local-delay.json').exists() else {}
    prepared=[c for c in record['commands'] if c['purpose']=='prepared-save-once']
    reopened=[c for c in record['commands'] if c['purpose']=='reopened-save-once']
    recovery=[r for r in record.get('promptRecoveries',[]) if r['label']=='prepared-save-once']
    observations={entry['observationId']:entry['observation'] for entry in record['observations'] if entry.get('state')=='observed'}
    before=observations.get(marker.get('observationId'),{})
    after=observations.get(recovery[0].get('observationId'),{}) if recovery else {}
    native=read(attempt/'result.json') if (attempt/'result.json').exists() else {}
    summary=results[attempt.name]
    checks=dict(
        verifiedSaveReopen=run['savedDraftVerified'] is True and run['state']=='verified',
        nativePassed=native.get('passed') is True and native.get('windowHandles')==0,
        exactlyOneSubmission=summary['submissionCount']==1,
        noCancellationOrAutomaticResume=summary['cancellationCount']==0 and run['automaticResume'] is False,
        completeSemanticSequence=len(record['actions'])==19 and all(a['state']=='answered' for a in record['actions']),
        delayRanOnce=marker.get('state')=='delay_completed' and marker.get('runId')==record['id'] and marker.get('delaySeconds')==1.65,
        originalSaveDefinitelyUnsent=len(prepared)==2 and prepared[0]['state']=='not_sent' and prepared[0].get('refusal','').startswith('DecisionExpired:'),
        refreshedSaveAnswered=len(prepared)==2 and prepared[1]['state']=='answered',
        twoTransportSavesOnly=len([c for c in prepared+reopened if c['state']=='answered'])==2,
        onePreparedPromptRefresh=len(recovery)==1 and recovery[0].get('state')=='fresh_decision' and recovery[0].get('phoneActionRetried') is False,
        independentFreshObservation=bool(before and after and before['id']!=after['id'] and after['frameEvidence']['sequence']>before['frameEvidence']['sequence']),
        captionAndAccountHistory=record.get('accountHistory',{}).get('status')=='consistent_sampled_history',
        cleanupConfirmed=run['cleanup']=='confirmed' and record.get('finalInput',{}).get('owned') is False,
        evidenceExportVerified=summary['observedFrames']==summary['exportedImagesVerified'] and record.get('evidenceExport')=='confirmed')
    output=dict(passed=all(checks.values()),checks=checks,requestId=run['id'],runId=record['id'],
        preparedSaveStates=[c['state'] for c in prepared],reopenedSaveStates=[c['state'] for c in reopened],
        rejectedDecisionChecks=prepared[0].get('decisionChecks') if prepared else None,
        refreshedDecisionChecks=prepared[1].get('decisionChecks') if len(prepared)>1 else None,
        promptRecoveries=record.get('promptRecoveries',[]),fault=marker,
        phoneInputDevice='C24C',desktopControl=False,publishing=False,messaging=False,
        appRestartPersistenceTested=False)
    (HERE/'prompt-recovery-acceptance.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps(dict(promptRecoveryPassed=output['passed'],checks=checks)))
