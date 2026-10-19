"""Test-only local delay before the first prepared Save; no phone command added."""
import hashlib
import json
from pathlib import Path
import runpy
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from farm_draft_runs import ACCOUNT, CONTENT_SHA256
from farm_draft_workflow import Workflow, atomic_json

DELAY_SECONDS = 1.65


def install_delay(marker, *, pause=time.sleep):
    """Patch only this process. One fresh, unsent test Save gets a real delay."""
    marker = Path(marker)
    if marker.exists(): raise ValueError('This delay record already exists; do not reuse a test window.')
    original = Workflow.save
    lock = threading.Lock()
    used = False

    def save(workflow):
        nonlocal used
        original(workflow)
        commands = workflow.record['commands']
        if not commands: return
        command = commands[-1]
        checks = command.get('decisionChecks', [])
        if (command.get('purpose') != 'prepared-save-once' or command.get('state') != 'outcome_unknown'
                or len(checks) != 1 or checks[0].get('stage') != 'before_dispatch_journal'
                or checks[0].get('freshness') != 'recent'):
            return
        # This exact save() boundary precedes before_transport and kernel.send.
        # Do not inject on an uncertain reply, another endpoint/account/content,
        # a second action, or a different source revision.
        identity = dict(caption=workflow.caption,
                        slides=[hashlib.sha256(raw).hexdigest() for raw in workflow.assets])
        content = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if (workflow.account != ACCOUNT or content != CONTENT_SHA256
                or workflow.kernel.url.rstrip('/') != 'http://127.0.0.1:9916/api'):
            raise ValueError('Local delay is restricted to the isolated C24C test draft.')
        with lock:
            if used: return
            used = True
        record = dict(kind='local_pre_dispatch_age_delay', source='test_only_backend_wrapper',
            state='waiting', delaySeconds=DELAY_SECONDS, runId=workflow.owned.run_id,
            packageSha256=workflow.package_hash, account=workflow.account, device='C24C',
            commandIndex=len(commands)-1, purpose=command['purpose'],
            evidenceRecordSha256=checks[0]['evidenceRecordSha256'], observationId=checks[0]['observationId'],
            startedUtcEpoch=time.time(), transportCalledByWrapper=False,
            publishing=False, messaging=False, desktopControl=False)
        atomic_json(marker, record)
        started = time.monotonic()
        pause(DELAY_SECONDS)
        record.update(state='delay_completed', elapsedSeconds=time.monotonic()-started,
                      completedUtcEpoch=time.time())
        atomic_json(marker, record)

    Workflow.save = save
    return lambda: setattr(Workflow, 'save', original)


def main():
    if len(sys.argv) < 5 or sys.argv[1] != '--fault-record' or sys.argv[3] != '--':
        raise SystemExit('Use --fault-record PATH -- followed by the prepared server arguments.')
    marker = Path(sys.argv[2]).resolve()
    if marker.parent != HERE or marker.name != 'local-delay.json':
        raise SystemExit('Delay evidence must stay in this dedicated test window.')
    install_delay(marker)
    sys.argv = [str(ROOT/'tools/imouse_farm_server.py'), *sys.argv[4:]]
    runpy.run_path(sys.argv[0], run_name='__main__')


if __name__ == '__main__': main()
