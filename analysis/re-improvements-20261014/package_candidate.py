"""Assemble a new immutable offline candidate from the tested final builds."""
import json
from pathlib import Path
import subprocess
import sys

record = Path(__file__).resolve().parent
repo = record.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(repo / 'tools'))
import build_manifest as bm
import stage_release as stage
import managed_symbols

previous = repo / 'output/staging/combined-timing-20261013'
output = repo / 'output/staging/combined-re-improvements-20261014'
old_hash = stage.row(previous / 'package.json')
# Old immutable packages retain their own recorded verifier; never retrofit it.
verified = subprocess.run([sys.executable, '-B', str(previous / 'verify_package.py'), 'verify', '--bundle', str(previous)],
                          capture_output=True, timeout=60)
(record / 'previous-package-verify.txt').write_bytes(verified.stdout + verified.stderr)
assert verified.returncode == 0
assert '290 tests passed' in (record / 'kernel-final-tests.txt').read_text(encoding='utf-8-sig')
assert stage.load(record / 'console-final/qa/self-tests.json')['passed'] == 411
commit = subprocess.check_output(['git', '-c', 'safe.directory=' + repo.as_posix(), '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
managed, pairs = {}, {}
for component, assembly in stage.MANAGED.items():
    folder = record / (component + '-final')
    project = 'src/iMouse.' + ('Console' if component == 'console' else 'Kernel')
    manifest = bm.record(repo, folder, project + '/' + project.split('/')[-1] + '.csproj',
                         {'source_commit': commit, 'validation': 'headless mock tests; no physical acceptance'})
    path = record / (component + '-manifest.json')
    path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    assert bm.verify(manifest, repo, folder) == []
    pairs[component] = managed_symbols.verify_pair(folder / (assembly + '.dll'), folder / (assembly + '.pdb'))
    managed[component] = folder, path
package = stage.stage(repo, output, managed,
    previous / 'payload/receiver/uxplay.exe', previous / 'provenance/receiver.json', previous / 'source/receiver',
    record / 'BUNDLE-GUIDE.md', repo / 'output/staging/native-runtime-startup-preserved-final-20261013',
    repo / 'docs/OPERATOR-GUIDE.md', include_launcher_source=True)
assert stage.verify(output) == []
old = stage.load(previous / 'package.json')
unchanged = [name for name in old['files'] if name.startswith(('payload/receiver/', 'dependencies/receiver-runtime/', 'source/receiver/'))]
assert all(package['files'][name] == old['files'][name] for name in unchanged)
assert stage.row(previous / 'package.json') == old_hash
for tool, bundle, log in (
    (output / 'verify_package.py', output, 'package-verify.txt'),
    (output / 'dependencies/receiver-runtime/verify_runtime.py', output / 'dependencies/receiver-runtime', 'runtime-verify.txt')):
    checked = subprocess.run([sys.executable, '-B', str(tool), 'verify', '--bundle', str(bundle)], capture_output=True, timeout=60)
    (record / log).write_bytes(checked.stdout + checked.stderr)
    assert checked.returncode == 0, log
result = {'package': str(output), 'source_commit': commit, 'files': len(package['files']),
    'bytes': sum(row['bytes'] for row in package['files'].values()), 'manifest': stage.row(output / 'package.json'),
    'kernel_dll': stage.row(output / 'payload/kernel/iMouse2.Kernel.dll'),
    'console_dll': stage.row(output / 'payload/console/iMouse2.dll'), 'managed_symbol_pairs': pairs,
    'native_entries_preserved': len(unchanged), 'previous_package_unchanged': True,
    'headless_kernel_checks': 290, 'headless_console_checks': 411,
    'physical_acceptance': False, 'launched': False, 'promoted': False}
(record / 'package-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
