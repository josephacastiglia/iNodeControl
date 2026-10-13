"""Run offline launcher checks, including a real no-hardware validation child."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

record = Path(__file__).resolve().parent
repo = record.parents[1]
source = repo / 'Open iMouse 2.0.ps1'
negative = record / 'negative-launcher.ps1'
text = source.read_text(encoding='utf-8-sig')
needle = '$reason = Read-ReleaseStartupError $Start.ErrorLog'
assert text.count(needle) == 1
negative.write_text(text.replace(needle, "$reason = '' # negative control: discard the actual refusal"), encoding='utf-8')
shells = {'pwsh': shutil.which('pwsh'), 'windows-powershell': shutil.which('powershell')}
results = []
environment = os.environ.copy()
# A pwsh parent passes its own module directory through Python; let each child
# construct its native module path rather than loading PowerShell 7 modules in 5.1.
for key in list(environment):
    if key.casefold() == 'psmodulepath':
        del environment[key]
run_id = uuid.uuid4().hex[:8]
for name, shell in shells.items():
    assert shell
    for case in ('offline', 'actual', 'negative'):
        args = [shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File']
        if case == 'actual':
            args += [str(record / 'Check-ActualRefusal.ps1'), '-RecordName', f'actual-{name}-{run_id}']
        else:
            args += [str(repo / 'tools/test_launcher.ps1'), '-Offline', '-ReportPath', str(record / f'{case}-{name}.json')]
            if case == 'negative':
                args += ['-LauncherPath', str(negative)]
        run = subprocess.run(args, capture_output=True, timeout=45,
                             creationflags=subprocess.CREATE_NO_WINDOW, cwd=repo, env=environment)
        (record / f'{case}-{name}.stdout.txt').write_bytes(run.stdout)
        (record / f'{case}-{name}.stderr.txt').write_bytes(run.stderr)
        assert (run.returncode != 0) if case == 'negative' else (run.returncode == 0), (case, name, run.stderr)
        if case == 'negative':
            result = json.loads((record / f'{case}-{name}.json').read_text(encoding='utf-8'))
            assert any('kernel refusal' in failure for failure in result['failures'])
        results.append({'runtime': name, 'case': case, 'exit': run.returncode, 'expected_outcome_observed': True,
                        'record': f'actual-{name}-{run_id}/result.json' if case == 'actual' else f'{case}-{name}.json'})
summary = {'launcher_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'checks': results,
           'all_passed': True, 'no_phone_or_receiver_or_service_started': True,
           'negative_control': 'Removing error-log detail is detected in both PowerShell runtimes.',
           'limit': 'Launcher adapters, real validation-only kernel child and bounded error display; no live launch or dialog interaction.'}
(record / 'results.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary, indent=2))
