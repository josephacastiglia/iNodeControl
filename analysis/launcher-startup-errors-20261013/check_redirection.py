import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid

record = Path(__file__).resolve().parent
env = {key: value for key, value in os.environ.items() if key.casefold() != 'psmodulepath'}
results = []
for shell in ('pwsh', 'powershell'):
    folder = record / f'redirection-{shell}-{uuid.uuid4().hex[:8]}'
    run = subprocess.run([shutil.which(shell), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                          str(record / 'Check-RedirectionParent.ps1'), '-RunDir', str(folder)],
                         capture_output=True, timeout=15, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    deadline = time.monotonic() + 10
    while not (folder / 'done.txt').exists() and time.monotonic() < deadline:
        time.sleep(.1)
    assert (folder / 'done.txt').read_text() == 'finished'
    content = Path(result['log']).read_text(encoding='utf-8-sig')
    assert 'first' in content.splitlines() and 'last' in content.splitlines(), content
    result.update(runtime=shell, passed=True, both_error_lines_saved=True, synthetic_child_only=True,
                  extra_shell_progress_output=content.splitlines() != ['first', 'last'])
    results.append(result)
(record / 'redirection-results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print('Both synthetic children finished and preserved stderr across parent launcher exit.')
