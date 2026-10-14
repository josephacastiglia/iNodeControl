"""Assemble recorded repairs in a fresh review bundle; no builds or service starts."""
import json
from pathlib import Path
import subprocess
import sys

record = Path(__file__).resolve().parent
repo = record.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(repo / 'tools'))
import stage_release as stage

previous = repo / 'output/staging/combined-shutdown-20261013'
output = repo / 'output/staging/combined-timing-20261013'
kernel_record = repo / 'analysis/fleet-shutdown-20261013/resumed'
console_record = repo / 'analysis/gate6-preflight-20261013'
assert stage.verify(previous) == []
old_manifest_hash = stage.row(previous / 'package.json')
package = stage.stage(repo, output, {
    'kernel': (kernel_record / 'final-kernel', kernel_record / 'kernel-manifest.json'),
    'console': (console_record / 'console-artifacts', console_record / 'console-manifest.json')},
    previous / 'payload/receiver/uxplay.exe', previous / 'provenance/receiver.json',
    previous / 'source/receiver', record / 'BUNDLE-GUIDE.md',
    repo / 'output/staging/native-runtime-startup-preserved-final-20261013',
    repo / 'docs/OPERATOR-GUIDE.md', include_launcher_source=True)
assert stage.verify(output) == []
old = stage.load(previous / 'package.json')
unchanged = [name for name in old['files'] if name.startswith(
    ('payload/receiver/', 'dependencies/receiver-runtime/', 'source/receiver/'))]
assert all(package['files'][name] == old['files'][name] for name in unchanged)
assert stage.row(previous / 'package.json') == old_manifest_hash
assert stage.verify(previous) == []
for tool, bundle, log in (
    (output / 'verify_package.py', output, 'package-verify.txt'),
    (output / 'dependencies/receiver-runtime/verify_runtime.py', output / 'dependencies/receiver-runtime', 'runtime-verify.txt'),
):
    checked = subprocess.run([sys.executable, '-B', str(tool), 'verify', '--bundle', str(bundle)],
                             capture_output=True, timeout=60)
    (record / log).write_bytes(checked.stdout + checked.stderr)
    assert checked.returncode == 0, log
result = {'package': str(output), 'files': len(package['files']),
          'bytes': sum(row['bytes'] for row in package['files'].values()),
          'manifest': stage.row(output / 'package.json'),
          'kernel_dll': stage.row(output / 'payload/kernel/iMouse2.Kernel.dll'),
          'console_dll': stage.row(output / 'payload/console/iMouse2.dll'),
          'launcher_source': package['launcher_source'],
          'unchanged_receiver_runtime_files': len(unchanged),
          'previous_package_manifest': old_manifest_hash,
          'previous_package_unchanged': True, 'integrity_and_sources_verified': True,
          'review_only': True, 'launched': False, 'services_started': False,
          'physical_acceptance': False}
(record / 'package-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
