"""Read-only identity, source, free-input and receiver readiness verification."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request

RECORD = Path(__file__).resolve().parent
ROOT = RECORD.parents[1]
sys.path.insert(0, str(ROOT/'tools'))
from farm_live_verification import ReadOnlyKernel, validate_runtime, idle, NoRedirect
from imouse_social_automation import LIVE_TEST_DEVICE_ID

prep = json.loads((RECORD/'preparation.json').read_text(encoding='utf-8'))
processes = json.loads((RECORD/'processes.json').read_text(encoding='utf-8-sig'))
kernel = ReadOnlyKernel(prep['arguments'][0])
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
tree = ast.parse((ROOT/'tools/imouse_farm_server.py').read_text(encoding='utf-8'))
source_names = None
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and any(isinstance(target, ast.Attribute) and target.attr == 'source_hash' for target in node.targets):
        names = [item for item in ast.walk(node.value) if isinstance(item, ast.Tuple)]
        source_names = ast.literal_eval(names[0]); break
assert source_names and 'farm_draft_workflow.py' in source_names
source_hash = hashlib.sha256(b''.join((ROOT/'tools'/name).read_bytes() for name in source_names)).hexdigest()
deadline = time.monotonic()+25
while True:
    try:
        with opener.open('http://127.0.0.1:9915/health', timeout=3) as response: health = json.load(response)
        status, devices = kernel.kernel_status(), kernel.devices()
        identity = validate_runtime(status, devices, prep['validation']['build']['sha256'], prep['expectedUid'])
        assert identity[0] == processes['kernel']['pid']
        receiver = status['receivers'][0]
        assert receiver['receiver_pid'] > 0 and receiver['receiver_restarts'] == 0
        assert health['protocolVersion'] == 2 and health['executionMode'] == 'live'
        assert health['sourceHash'] == source_hash == prep['backendSourceHash']
        capability = health['draftWorkflow']
        assert capability['enabled'] and capability['device'] == 'C24C' and capability['account'] == 'xs.halle.xo'
        assert not capability['publishing'] and not capability['messaging']
        input_state = kernel.input_status().get(LIVE_TEST_DEVICE_ID)
        assert idle(input_state)
        break
    except Exception:
        if time.monotonic() >= deadline: raise
        time.sleep(.5)
record = dict(ready=True, capturedUtc=time.time(), kernelPid=identity[0], receiverPid=receiver['receiver_pid'],
    receiverName=receiver['name'], receiverRestarts=receiver['receiver_restarts'],
    live=receiver.get('live'), backendPid=processes['backend']['pid'], storeId=capability['storeId'],
    backendSourceHash=source_hash, input=input_state, phoneInput=False, desktopControl=False)
(RECORD/'ready.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps(record))

options = dict(phase='live', scenario='response-loss',
    output=str(RECORD/'live-save-reopen-with-refresh'), backend='http://127.0.0.1:9915',
    backendSourceHash=source_hash, assembly=prep['nativeAssembly'],
    draftId=prep['draftId'], revision=prep['revision'], storeId=capability['storeId'])
assert not Path(options['output']).exists(), 'A live attempt already exists; never replay it.'
(RECORD/'live.options.json').write_text(json.dumps(options,indent=2),encoding='utf-8')
