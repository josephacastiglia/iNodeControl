"""One-time shutdown checkpoint. Preserves draft bytes; does not run tests."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

record = Path(__file__).resolve().parent
repo = record.parents[1]
git = ['git', '-c', 'safe.directory=' + repo.as_posix(), '-C', str(repo)]
draft = record / 'draft'
assert not draft.exists(), 'Do not overwrite a prior checkpoint'
tracked = ['tools/recovery_tests/Program.cs', 'tools/recovery_tests/RecoveryTests.csproj']
new = repo / 'tools/recovery_tests/FleetShutdownTests.cs'
assert new.is_file()
sources = set(tracked + ['tools/recovery_tests/FleetShutdownTests.cs'])
for item in ET.parse(repo / tracked[1]).iter('Compile'):
    sources.add((repo / 'tools/recovery_tests' / item.attrib['Include']).resolve().relative_to(repo).as_posix())
# Preserve the complete local test source too, including any existing helper.
sources.update(p.relative_to(repo).as_posix() for p in (repo / 'tools/recovery_tests').glob('*.cs'))
sources.add('src/iMouse.Kernel/Program.cs')
for name in sorted(sources):
    source, target = repo / name, draft / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    assert source.read_bytes() == target.read_bytes(), name
(draft / 'tracked-working.patch').write_bytes(subprocess.check_output(git + ['diff', '--binary', '--', *tracked]))
manifest = {'base_commit': subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip(),
            'draft_tests_run': False, 'fixture_bug_known': True, 'files': {}}
for base in (draft, record / 'before-recovery'):
    for p in sorted(base.rglob('*')):
        if p.is_file():
            manifest['files'][p.relative_to(record).as_posix()] = {
                'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
(record / 'draft-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
# Restore only the two known draft edits after byte-verified preservation.
for name in tracked:
    (repo / name).write_bytes(subprocess.check_output(git + ['show', 'HEAD:' + name]))
# This exact untracked file is now preserved and verified in draft/.
assert new.read_bytes() == (draft / new.relative_to(repo)).read_bytes()
new.unlink()
print(json.dumps({'draft_files_preserved': len(sources), 'tracked_test_files_restored': tracked,
                  'product_changes': False, 'tests_run': False}, indent=2))
