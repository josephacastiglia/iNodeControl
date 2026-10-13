"""Reproduce a missing active-profile export in a separate source copy."""
import hashlib
import json
from pathlib import Path
import shutil

record = Path(__file__).resolve().parent
repo = record.parents[1]
source = repo / 'src/iMouse.Console'
target = record / 'negative-profile'
assert not target.exists(), 'Never replace a prior negative control'
shutil.copytree(source, target, ignore=shutil.ignore_patterns('bin', 'obj'))
file = target / 'MainWindowDiagnostics.cs'
before = file.read_bytes()
assert before.count(b'dataPath: _dataPath') == 1
file.write_bytes(before.replace(b'dataPath: _dataPath', b'dataPath: null'))
changed = []
for path in target.rglob('*'):
    if path.is_file() and path.read_bytes() != (source / path.relative_to(target)).read_bytes():
        changed.append(path.relative_to(target).as_posix())
assert changed == ['MainWindowDiagnostics.cs']
(record / 'negative-change.json').write_text(json.dumps({
    'change': 'Withhold the active profile from the real window diagnostic collector.',
    'changed_files': changed,
    'before_sha256': hashlib.sha256(before).hexdigest(),
    'after_sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
    'expected_failure': 'The actual window export reads its isolated receipt after disconnect'
}, indent=2), encoding='utf-8')
print('Prepared one deliberately regressed copy; working product source unchanged.')
