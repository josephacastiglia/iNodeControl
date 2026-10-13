"""Prepare a C24C candidate profile and validate it offline. Never start a service."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

record = Path(__file__).resolve().parent
repo = record.parents[1]
sys.path.insert(0, str(repo / 'tools'))
import stage_release as p
import validate_rack_config as rack

release = repo.parent / 'iMouseXP-2.0'
source_config = release / 'analysis/two-phone-config'
package = repo / 'output/staging/combined-cleanup-diagnostics-20261012'
run_dir = repo / 'output/candidate-runs/cleanup-diagnostics-20261012'
assert not run_dir.exists(), 'Never reuse or overwrite a candidate run'
assert p.verify(package) == []
before = {name: p.row(source_config / name) for name in ('receivers.json', 'devices.json', 'pointer-calibration.json')}
records = [rack.read_records(source_config / name) for name in before]
assert rack.validate(*records)['configuration_valid']
selected = [[row for row in rows if row[key] == 'C24C'] for rows, key in zip(records, ('BoardPid', 'pid', 'Pid'))]
assert all(len(rows) == 1 for rows in selected), 'C24C selection is ambiguous'
selected_check = rack.validate(*selected)
assert selected_check['configuration_valid'] and selected_check['bindings_complete']
assert selected[0][0]['DeviceId'] == selected[1][0]['deviceid'] == rack.KNOWN['C24C']
run_dir.mkdir(parents=True, exist_ok=False)
data = run_dir / 'kernel/data'
data.mkdir(parents=True)
for name, rows in zip(before, selected):
    (data / name).write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')
kernel_bin = run_dir / 'kernel/bin'
kernel_bin.mkdir()
manifest = p.load(package / 'package.json')
for file in (package / 'payload/kernel').iterdir():
    expected = manifest['files'][file.relative_to(package).as_posix()]
    assert p.row(file) == expected
    shutil.copy2(file, kernel_bin / file.name)
    assert p.row(kernel_bin / file.name) == expected
console_run = run_dir / 'console'
hidden = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
command = [r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
    '-File', str(repo / 'tools/candidate-launcher/Start-iMouse2Candidate.ps1'),
    '-ConsoleExe', str(package / 'payload/console/iMouse2.exe'),
    '-BuildManifest', str(repo / 'analysis/cleanup-diagnostics-20261012/console-manifest.json'),
    '-SourceRoot', str(repo), '-RunDir', str(console_run), '-Address', 'http://127.0.0.1:9913', '-PrepareOnly']
launcher_environment = {key: value for key, value in os.environ.items() if key.casefold() != 'psmodulepath'}
# Python bypasses pwsh's native-child module-path adjustment. Let Windows
# PowerShell initialize its own defaults, without changing the host environment.
preparation = subprocess.run(command, capture_output=True, timeout=60, creationflags=hidden, env=launcher_environment)
(record / 'console-preparation.txt').write_bytes(preparation.stdout + preparation.stderr)
assert preparation.returncode == 0, 'Candidate preparation failed; partial run retained'
profile = console_run / 'data/settings.json'
settings = p.load(profile)
assert settings['address'].rstrip('/') == 'http://127.0.0.1:9913' and settings['trackPointer'] is False
profile_before = p.row(profile)
receiver = package / 'payload/receiver/uxplay.exe'
runtime = package / 'dependencies/receiver-runtime/runtime'
arguments = ['http://127.0.0.1:9913/api/', '--data-dir', str(data), '--input-pid', 'C24C',
    '--receivers', str(data / 'receivers.json'), '--receiver', str(receiver), '--receiver-runtime', str(runtime)]
kernel_files = p.inventory(run_dir / 'kernel', 'no-manifest')
checked = subprocess.run(['dotnet', str(kernel_bin / 'iMouse2.Kernel.dll'), '--validate-startup', *arguments],
    capture_output=True, timeout=30, creationflags=hidden)
(record / 'kernel-validation.stdout.json').write_bytes(checked.stdout)
(record / 'kernel-validation.stderr.txt').write_bytes(checked.stderr)
assert checked.returncode == 0, 'Kernel configuration was refused'
kernel = json.loads(checked.stdout)
assert kernel['valid'] and kernel['allowed'] == ['C24C'] and kernel['receiver_count'] == 1
assert kernel['bindings_complete'] and kernel['home_sequence'] == 'vendor'
assert all(kernel[key] is False for key in ('hardware_accessed', 'listener_started', 'receivers_started', 'settings_written'))
assert kernel['build']['sha256'] == manifest['files']['payload/kernel/iMouse2.Kernel.dll']['sha256']
assert kernel_files == p.inventory(run_dir / 'kernel', 'no-manifest')
checked_console = subprocess.run([str(console_run / 'bin/iMouse2.exe'), '--validate-startup',
    '--data-dir=' + str(console_run / 'data'), '--address=http://127.0.0.1:9913'], capture_output=True, timeout=30, creationflags=hidden)
validation = console_run / 'bin/startup-validation.json'
assert checked_console.returncode == 0 and validation.is_file()
console = p.load(validation)
assert console['valid'] and console['connected'] is False and console['settingsWritten'] is False
assert Path(console['dataDirectory']).resolve() == (console_run / 'data').resolve()
assert console['address'].rstrip('/') == 'http://127.0.0.1:9913'
assert console['build']['Sha256'] == manifest['files']['payload/console/iMouse2.dll']['sha256']
assert p.row(profile) == profile_before
shutil.copy2(validation, record / 'console-validation.json')
assert before == {name: p.row(source_config / name) for name in before}
for item in p.load(repo / 'analysis/runtime-provenance-20261012/protected-files.json'):
    assert p.bm.sha256(Path(item['path'])) == item['sha256']
result = {'prepared': True, 'service_started': False, 'window_shown': False, 'rack_contacted': False,
    'run_directory': str(run_dir), 'package_manifest': p.row(package / 'package.json'),
    'source_configuration': str(source_config), 'source_configuration_hashes': before,
    'source_configuration_unchanged': True, 'installed_hashes_unchanged': True,
    'input_allowed': ['C24C'], 'receiver_boards': ['C24C'], 'C241_in_candidate': False,
    'candidate_settings_unchanged_by_validation': True,
    'kernel_validation': kernel, 'console_validation': console,
    'kernel_arguments_for_later_review_only': arguments,
    'remaining': ['No process/port/ownership preflight for a live window.',
        'No dependency loading, physical identity, video or input test.',
        'A kernel/receiver swap still requires an approved interruption and restoration window.',
        'Home still uses the vendor sequence (Tab side effect); typing investigation remains deferred.']}
(record / 'preparation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
(run_dir / 'PREPARED-NOT-LAUNCHED.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
(record / 'run-inventory.json').write_text(json.dumps(p.inventory(run_dir, 'no-manifest'), indent=2), encoding='utf-8')
print('Prepared C24C-only configuration and isolated hover-off console; both exact binaries validated offline. No window, listener, receiver or hardware input.')
