"""Run only recorded offline tests; no rack endpoints, windows or phone input."""
import json
import os
from pathlib import Path
import subprocess
import sys

record = Path(__file__).resolve().parent
repo = record.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(repo / 'tools'))
import build_manifest as bm

protected = json.loads((repo / 'analysis/candidate-retry-20261013/restoration-files.json').read_text(encoding='utf-8-sig'))
protected = [r for r in protected if Path(r['path']).name not in ('receiver-C24C.log', 'receiver-C241.log')]
assert all(bm.sha256(Path(r['path'])) == r['sha256'] for r in protected)
temporary = record / 'test-temp'
temporary.mkdir(exist_ok=True)
environment = dict(os.environ, TEMP=str(temporary), TMP=str(temporary))
commands = [
    ('preview-tests', ['dotnet', str(record / 'verified-preview/PreviewTests.dll')], 45),
    ('loopback-tests', ['dotnet', str(record / 'verified-preview/PreviewTests.dll'), '--loopback'], 30),
    ('self-tests', [str(record / 'final-console/iMouse2.exe'), '--self-test'], 120),
]
results = {}
for name, command, timeout in commands:
    run = subprocess.run(command, capture_output=True, timeout=timeout, env=environment,
                         creationflags=subprocess.CREATE_NO_WINDOW)
    (record / (name + '.txt')).write_bytes(run.stdout + run.stderr)
    results[name] = {'exit_code': run.returncode}
    print(name, run.returncode, flush=True)
assert all(bm.sha256(Path(r['path'])) == r['sha256'] for r in protected)
results['installed_static_files_unchanged'] = True
(record / 'verification.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
raise SystemExit(0 if all(row['exit_code'] == 0 for name, row in results.items() if isinstance(row, dict)) else 1)
