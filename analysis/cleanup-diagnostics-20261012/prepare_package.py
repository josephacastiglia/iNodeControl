"""Record the tested console and create an immutable review package; no launch."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

record = Path(__file__).resolve().parent
repo = record.parents[1]
sys.path.insert(0, str(repo / 'tools'))
import build_manifest as bm
import stage_release as p

tests = json.loads((record / 'final-build/qa/self-tests.json').read_text(encoding='utf-8'))
assert tests['passed'] == 372
shutil.copy2(record / 'final-build/qa/self-tests.json', record / 'self-tests.json')
negative = (record / 'negative-build/self-test-failure.txt').read_text(encoding='utf-8')
assert 'The actual window export reads its isolated receipt after disconnect' in negative
shutil.copy2(record / 'negative-build/self-test-failure.txt', record / 'negative-failure.txt')
component = record / 'candidate-console'
component.mkdir(exist_ok=False)
names = ['iMouse2.exe', 'iMouse2.dll', 'iMouse2.pdb', 'iMouse2.deps.json', 'iMouse2.runtimeconfig.json']
for name in names:
    shutil.copy2(record / 'final-build' / name, component / name)
env = dict(os.environ, GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='safe.directory', GIT_CONFIG_VALUE_0=repo.as_posix())
subprocess.run([sys.executable, str(repo / 'tools/build_manifest.py'), 'record', '--repo', str(repo),
    '--build', str(component), '--project', 'src/iMouse.Console/iMouse.Console.csproj',
    '--manifest', str(record / 'console-manifest.json')], env=env, check=True)
manifest = p.load(record / 'console-manifest.json')
assert bm.verify(manifest, repo, component) == []
prior = repo / 'output/staging/combined-runtime-provenance-final-20261012'
assert p.verify(prior) == []
out = repo / 'output/staging/combined-cleanup-diagnostics-20261012'
package = p.stage(repo, out, {
    'console': (component, record / 'console-manifest.json'),
    'kernel': (repo / 'analysis/persistence-20261012/final-kernel', repo / 'analysis/persistence-20261012/kernel-manifest.json')},
    prior / 'payload/receiver/uxplay.exe', prior / 'provenance/receiver.json', prior / 'source/receiver',
    repo / 'docs/RELEASE-STAGING.md', repo / 'output/staging/native-runtime-provenance-final-20261012', repo / 'docs/OPERATOR-GUIDE.md')
before = p.load(prior / 'package.json')
unchanged = ('payload/kernel/', 'payload/receiver/', 'source/kernel/', 'source/receiver/', 'dependencies/receiver-runtime/')
select = lambda files: {name: row for name, row in files.items() if name.startswith(unchanged)}
assert select(before['files']) == select(package['files'])
for tool, root in ((out / 'verify_package.py', out), (out / 'dependencies/receiver-runtime/verify_runtime.py', out / 'dependencies/receiver-runtime')):
    checked = subprocess.run([sys.executable, '-E', '-s', str(tool), 'verify', '--bundle', str(root)], capture_output=True, check=True)
    (record / (tool.stem + '-result.txt')).write_bytes(checked.stdout + checked.stderr)
protected = []
for row in p.load(repo / 'analysis/runtime-provenance-20261012/protected-files.json'):
    assert bm.sha256(Path(row['path'])) == row['sha256']
    protected.append(dict(row, matches_previous_record=True))
(record / 'protected-files.json').write_text(json.dumps(protected, indent=2), encoding='utf-8')
result = {'package': str(out), 'files': len(package['files']), 'console_sha256': bm.sha256(component / 'iMouse2.dll'),
    'console_tests_passed': tests['passed'], 'source_inputs': len(manifest['sources']),
    'negative_control_detected': True, 'unchanged_kernel_receiver_runtime': True,
    'prior_package_unchanged': p.verify(prior) == [], 'all_hashes_verified': p.verify(out) == [],
    'installed_hashes_unchanged': True, 'status': package['status'], 'launched': False}
(record / 'package-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
