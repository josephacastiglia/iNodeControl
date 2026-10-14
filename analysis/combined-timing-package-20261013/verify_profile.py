"""Check the prepared candidate's saved files only; no process, UI or HTTP calls."""
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
record = Path(__file__).resolve().parent
repo = record.parents[1]
spec = importlib.util.spec_from_file_location('gate6', repo / 'analysis/gate6-release-validation-20260916/run_gate6.py')
gate6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate6)
prepared = json.loads((record / 'preparation.json').read_text(encoding='utf-8'))
assert prepared['prepared'] and prepared['service_started'] is False
run = Path(prepared['run_directory']) / 'console'
exe = run / 'bin/iMouse2.exe'
data = run / 'data'
digest = prepared['console_validation']['build']['Sha256']
result = gate6.validate_candidate_profile(str(exe),
    [str(exe), '--data-dir=' + str(data), '--address=http://127.0.0.1:9913'], str(data), digest)
assert result['active_connection_verified'] is False
result.update(process_inspected=False, ui_control=False, rack_contacted=False,
              two_stream_preflight_performed=False, gate6_acceptance=False)
(record / 'saved-profile-check.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print('Prepared files match the Gate 6 saved-profile checks. No process, UI, network or two-stream preflight ran.')
