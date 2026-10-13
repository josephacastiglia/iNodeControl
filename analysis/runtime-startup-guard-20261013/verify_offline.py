"""Exercise real startup validation only; never start a receiver, listener or HID."""
import hashlib
import json
from pathlib import Path
import subprocess

record = Path(__file__).resolve().parent
repo = record.parents[1]
data = repo / 'output/candidate-runs/runtime-startup-20261013/kernel/data'
old = repo / 'output/staging/combined-scope-release-20261012'
fixed = repo / 'output/staging/combined-runtime-startup-final-20261013'
new_dll = record / 'final-kernel/iMouse2.Kernel.dll'
sha = lambda file: hashlib.sha256(file.read_bytes()).hexdigest()
inventory = lambda folder: {file.relative_to(folder).as_posix(): sha(file) for file in folder.rglob('*') if file.is_file()}
before = {str(folder): inventory(folder) for folder in (data, old, fixed)}
protected = json.loads((repo / 'analysis/runtime-provenance-20261012/protected-files.json').read_text(encoding='utf-8'))
assert all(sha(Path(item['path'])) == item['sha256'] for item in protected)
cases = [
    ('previous-kernel-broken-runtime', old / 'payload/kernel/iMouse2.Kernel.dll', old, 0),
    ('guarded-kernel-broken-runtime', new_dll, old, 2),
    ('guarded-kernel-repaired-runtime', new_dll, fixed, 0),
]
results = []
missing = ('libgstplayback.dll', 'libgstautodetect.dll', 'libgstaudioconvert.dll',
           'libgstaudioresample.dll', 'libgstvolume.dll', 'libgstlevel.dll')
for name, dll, package, expected in cases:
    command = ['dotnet', str(dll), '--validate-startup', 'http://127.0.0.1:9913/api/',
        '--data-dir', str(data), '--input-pid', 'C24C', '--receivers', str(data / 'receivers.json'),
        '--receiver', str(package / 'payload/receiver/uxplay.exe'),
        '--receiver-runtime', str(package / 'dependencies/receiver-runtime/runtime')]
    run = subprocess.run(command, capture_output=True, timeout=30,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    (record / (name + '.stdout.txt')).write_bytes(run.stdout)
    (record / (name + '.stderr.txt')).write_bytes(run.stderr)
    assert run.returncode == expected, (name, run.returncode, run.stderr.decode(errors='replace'))
    if expected == 2:
        message = run.stderr.decode('utf-8')
        assert all(plugin in message for plugin in missing)
        assert message.startswith('Startup refused: Receiver runtime has missing or empty required files:')
        assert 'Verify the dependency package' in message
        assert not run.stdout
    else:
        report = json.loads(run.stdout)
        assert report['valid'] is True
        assert all(report[field] is False for field in ('hardware_accessed', 'listener_started', 'receivers_started', 'settings_written'))
    results.append({'case': name, 'assembly_sha256': sha(dll), 'package_manifest_sha256': sha(package / 'package.json'),
                    'exit': run.returncode, 'passed': True, 'validation_only': True})
assert all(inventory(Path(folder)) == files for folder, files in before.items())
assert all(sha(Path(item['path'])) == item['sha256'] for item in protected)
result = {'cases': results, 'all_passed': True, 'old_and_repaired_packages_unchanged': True,
    'saved_configuration_unchanged': True, 'installed_protected_hashes_unchanged': True,
    'hardware_accessed': False, 'receiver_started': False, 'listener_started': False,
    'limit': 'File-presence validation; native imports/loading, discovery and physical acceptance remain separate.'}
(record / 'cli-results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print('Three real CLI checks passed: old kernel accepted the broken runtime; repaired kernel refuses it and accepts the complete file set. No components started.')
