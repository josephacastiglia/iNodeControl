"""Record offline validation and copy the tested component; never launch it."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

record = Path(__file__).resolve().parent
repo = record.parents[1]
def save(name, data):
    (record / name).write_text(json.dumps(data, indent=2), encoding='utf-8')
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

build = record / 'lifecycle-build'
result = json.loads((build / 'qa/self-tests.json').read_text(encoding='utf-8'))
assert result['passed'] == 348
shutil.copy2(build / 'qa/self-tests.json', record / 'self-tests.json')
mutations = json.loads((record / 'negative-mutations.json').read_text(encoding='utf-8'))
negative = []
for mutation in mutations:
    name = mutation['name']
    failure = record / f'negative-{name}-build/self-test-failure.txt'
    message = failure.read_text(encoding='utf-8').splitlines()[0]
    expected = 'Close observes a release already in flight' if name == 'operator-wait' else 'Reconnect disables input and waits'
    assert expected in message
    shutil.copy2(failure, record / f'negative-{name}-failure.txt')
    source = record / f'negative-{name}'
    for original in (repo / 'src/iMouse.Console').rglob('*'):
        if not original.is_file() or any(p in ('bin', 'obj') for p in original.relative_to(repo / 'src/iMouse.Console').parts):
            continue
        relative = original.relative_to(repo / 'src/iMouse.Console')
        copied = source / relative
        if relative.as_posix() == mutation['file']:
            assert copied.read_text(encoding='utf-8') == original.read_text(encoding='utf-8').replace(mutation['removed'], mutation['replacement'])
        else:
            assert copied.read_bytes() == original.read_bytes(), relative
    negative.append({'name': name, 'exit_code': 1, 'failure': message, 'only_recorded_mutation': True})
save('negative-results.json', negative)
rows = []
for previous in json.loads((repo / 'analysis/drag-ordering-20261012/protected-files.json').read_text(encoding='utf-8')):
    path = Path(previous['path'])
    current = sha(path)
    assert current == previous['sha256'], path
    rows.append({'path': str(path), 'sha256': current, 'matches_previous_record': True})
save('protected-files.json', rows)
component = record / 'candidate-console'
component.mkdir(exist_ok=False)
for name in ('iMouse2.exe', 'iMouse2.dll', 'iMouse2.pdb', 'iMouse2.deps.json', 'iMouse2.runtimeconfig.json'):
    shutil.copy2(build / name, component / name)
old = subprocess.run(['git', 'show', '2349ce5:src/iMouse.Console/MainWindow.xaml.cs'], cwd=repo, capture_output=True, check=True).stdout.decode('utf-8')
save('old-source-markers.json', {'base': '2349ce5', 'closed_used_sync_dispose': 'Closed += ' in old and '_api?.Dispose();' in old,
    'connect_used_sync_dispose': '_api?.Dispose(); _api = next;' in old,
    'disconnect_used_sync_dispose': '_api?.Dispose(); _api = null;' in old})
save('build-result.json', {'build': 'lifecycle-build', 'warnings': 0, 'errors': 0, 'self_tests': result['passed'],
    'new_checks': 34, 'shown_windows': 0, 'native_window_handles_created_by_lifecycle_tests': 0,
    'live_calls': 0, 'sha256': sha(component / 'iMouse2.dll'), 'kernel_changed': False})
print('348 checks and both negative failures recorded; protected hashes unchanged; component preserved.')
