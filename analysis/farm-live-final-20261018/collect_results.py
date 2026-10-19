"""Summarize retained diagnostic evidence without any network or phone access."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def summarize(folder):
    record = json.loads((folder/'record.json').read_text(encoding='utf-8'))
    observations = record['observations']
    complete = [entry for entry in observations if entry.get('state') == 'observed']
    for entry in complete:
        raw = (folder/entry['frame']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry['observation']['reviewFrameSha256']:
            raise ValueError('Exported image differs from the observation: '+str(folder/entry['frame']))
    actions = record['actions']
    return dict(
        state=record['state'], error=record.get('error'), cleanup=record['cleanup'],
        mode=record.get('mode'), savedDraftVerified=record['savedDraftVerified'],
        productionAdapterAccepted=record['productionAdapterAccepted'],
        actionCount=len(actions), answeredActions=sum(a['state']=='answered' for a in actions),
        saves=[a for a in actions if a['kind']=='save_draft'],
        observations=len(observations), exportedImagesVerified=len(complete),
        maxCaptureAgeMs=max((o['observation']['frameEvidence']['ageUpperBoundMs'] for o in complete),default=None),
        sampledIntervalSeconds=(complete[-1]['observation']['completedAt']-complete[0]['observation']['requestedAt']) if complete else None,
        inputGenerations=sorted({o['observation']['inputGeneration'] for o in complete}),
        streamSessions=sorted({o['observation']['frameEvidence']['session'] for o in complete}),
        ownershipRuns=sorted({o['observation']['ownershipEvidence']['runId'] for o in complete}),
        accountHistory=record.get('accountHistory'),
        transitionWaitReasons=[e['reason'] for e in record['transitionChecks'] if e.get('state')=='wait' and 'reason' in e],
        readyTransitions=[dict(stage=e['stage'],capture=e['attempt']) for e in record['transitionChecks'] if e.get('state')=='ready'],
        finalInput=record.get('finalInput'),
        publishing=record['publishing'], messaging=record['messaging'], desktopControl=record['desktopControl'])


if __name__ == '__main__':
    result = {p.parent.name:summarize(p.parent) for p in sorted(HERE.glob('*/record.json'))
              if p.parent.name.startswith(('attempt-','recovery-'))}
    (HERE/'live-results.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({name:dict(state=value['state'],captures=value['observations'],saves=len(value['saves']),
                                cleanup=value['cleanup']) for name,value in result.items()},indent=2))
