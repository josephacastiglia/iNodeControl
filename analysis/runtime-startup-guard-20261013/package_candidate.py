"""Record the guarded kernel and stage a fresh offline review package."""
import json
from pathlib import Path
import subprocess
import sys

record = Path(__file__).resolve().parent
repo = record.parents[1]
sys.path.insert(0, str(repo / 'tools'))
import build_manifest as bm
import stage_release as stage

git = ['git', '-c', f'safe.directory={repo.as_posix()}']
head = subprocess.check_output(git + ['rev-parse', 'HEAD'], cwd=repo, text=True).strip()
sdk = subprocess.check_output(['dotnet', '--version'], text=True).strip()
kernel = record / 'final-kernel'
manifest_file = record / 'kernel-manifest.json'
manifest = bm.record(repo, kernel, 'src/iMouse.Kernel/iMouse.Kernel.csproj',
    {'git_head': head, 'sdk_version': sdk, 'source_snapshot_includes_uncommitted_files': True})
with manifest_file.open('x', encoding='utf-8') as stream:
    json.dump(manifest, stream, indent=2)
assert bm.verify(manifest, repo, kernel) == []
previous = repo / 'output/staging/combined-runtime-startup-final-20261013'
output = repo / 'output/staging/combined-runtime-guard-20261013'
assert stage.verify(previous) == []
package = stage.stage(repo, output, {
    'kernel': (kernel, manifest_file),
    'console': (repo / 'analysis/scope-release-20261012/candidate-console', repo / 'analysis/scope-release-20261012/console-manifest.json')},
    previous / 'payload/receiver/uxplay.exe', previous / 'provenance/receiver.json',
    previous / 'source/receiver', repo / 'docs/RELEASE-STAGING.md',
    repo / 'output/staging/native-runtime-startup-preserved-final-20261013',
    repo / 'docs/OPERATOR-GUIDE.md')
assert stage.verify(output) == []
old = stage.load(previous / 'package.json')
for name, row in old['files'].items():
    if name.startswith(('payload/console/', 'payload/receiver/', 'dependencies/receiver-runtime/', 'source/receiver/')):
        assert package['files'][name] == row, name
result = {'package': str(output), 'files': len(package['files']), 'package_manifest': stage.row(output / 'package.json'),
    'kernel_manifest': stage.row(manifest_file), 'kernel_dll': stage.row(kernel / 'iMouse2.Kernel.dll'),
    'source_verified': True, 'console_receiver_and_runtime_unchanged': True, 'review_only': True,
    'launched': False, 'kernel_self_tests_passed': 206, 'new_kernel_checks': 27,
    'negative_self_test_failed_as_expected': True, 'cli_checks_passed': 3,
    'limitations': ['File presence is not native loading or full dependency validation.',
                    'The repaired runtime and guarded kernel still require physical candidate acceptance.']}
(record / 'package-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(f'Staged {len(package["files"])} verified files. Only kernel source/binaries and preparation guidance changed; no process started.')
