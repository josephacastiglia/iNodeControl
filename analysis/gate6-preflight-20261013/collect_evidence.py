"""Preserve this offline check's source/build evidence; never start UIA or the rack."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

record = Path(__file__).resolve().parent
repo = record.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(repo / 'tools'))
import build_manifest as bm

spec = importlib.util.spec_from_file_location('gate6', repo / 'analysis/gate6-release-validation-20260916/run_gate6.py')
gate6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate6)
gate6.CONSOLE.update(pid=999999, exe=r"C:\candidate's folder\iMouse2.exe", started=123456789, phone='C24C')
with patch.object(gate6, 'run_uia_helper') as helper, patch.object(gate6, 'verify_bound_profile'):
    gate6.uia_invoke('HomeButton')
(record / 'action-helper.ps1').write_text(helper.call_args.args[0][-1], encoding='utf-8')
(record / 'disconnect-helper.ps1').write_text(gate6.disconnect_script(), encoding='utf-8')

build = record / 'console'
artifacts = record / 'console-artifacts'
artifacts.mkdir(exist_ok=False)
for source in build.iterdir():
    if source.is_file():
        shutil.copy2(source, artifacts / source.name)
        assert bm.sha256(source) == bm.sha256(artifacts / source.name)
shutil.copy2(build / 'qa/self-tests.json', record / 'console-self-tests.json')
assert json.loads((record / 'console-self-tests.json').read_text(encoding='utf-8'))['passed'] == 409
git = ['git', '-c', 'safe.directory=' + repo.as_posix(), '-C', str(repo)]
metadata = {'git_head': subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip(),
            'source_snapshot_includes_uncommitted_files': True,
            'validation': '409 headless self-tests, fake HTTP, no window or rack',
            'sdk_version': subprocess.check_output(['dotnet', '--version'], text=True).strip()}
manifest = bm.record(repo, artifacts, 'src/iMouse.Console/iMouse.Console.csproj', metadata)
assert bm.verify(manifest, repo, artifacts) == []
(record / 'console-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')

sources = list(manifest['sources']) + ['analysis/gate6-release-validation-20260916/run_gate6.py',
    'analysis/gate6-release-validation-20260916/test_run_gate6.py', 'tools/export_diagnostics.py',
    'tools/windows_command_line.py', 'tools/test_export_diagnostics.py']
rows = {}
for name in sources:
    target = record / 'final-source' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(repo / name, target)
    assert bm.sha256(target) == bm.sha256(repo / name)
    rows[name] = {'sha256': bm.sha256(target), 'bytes': target.stat().st_size}
(record / 'source-manifest.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')

protected = json.loads((repo / 'analysis/candidate-retry-20261013/restoration-files.json').read_text(encoding='utf-8'))
checked = []
for item in protected:
    if Path(item['path']).name in ('receiver-C24C.log', 'receiver-C241.log'):
        continue
    assert bm.sha256(item['path']) == item['sha256'], item['path']
    checked.append({'path': item['path'], 'sha256': item['sha256'], 'unchanged': True})
(record / 'protected-files.json').write_text(json.dumps(checked, indent=2), encoding='utf-8')
print(f'Preserved {len(sources)} source files, {len(manifest["artifacts"])} build files; {len(checked)} protected files unchanged. No input or service request.')
