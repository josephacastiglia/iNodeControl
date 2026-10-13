"""Build deliberately broken copies. Execute only their fake-transport self-tests separately."""
import json
import shutil
import subprocess
from pathlib import Path

record = Path(__file__).resolve().parent
repo = record.parents[1]
mutations = {
    'operator-wait': ('InputLeaseClient.cs', 'await Task.WhenAll(operators).ConfigureAwait(false);', '// Negative control: ignore in-flight operators.'),
    'reconnect-wait': ('MainWindow.xaml.cs', 'await FinishConnectionCleanupAsync();\n        if (_closing || session != _session || _pendingConnection != next)', '_ = FinishConnectionCleanupAsync(); // Negative control: connect too early.\n        if (_closing || session != _session || _pendingConnection != next)'),
}
rows = []
for name, (file, old, new) in mutations.items():
    source = record / ('negative-' + name)
    if not source.exists():
        shutil.copytree(repo / 'src/iMouse.Console', source, ignore=shutil.ignore_patterns('obj', 'bin'))
    path = source / file
    text = path.read_text(encoding='utf-8')
    expected = (repo / 'src/iMouse.Console' / file).read_text(encoding='utf-8')
    assert expected.count(old) == 1
    assert text in (expected, expected.replace(old, new)), 'Scratch source changed unexpectedly'
    path.write_text(expected.replace(old, new), encoding='utf-8', newline='')
    output = record / ('negative-' + name + '-build')
    commands = [
        ['dotnet', 'restore', str(source / 'iMouse.Console.csproj'), '--configfile', str(repo / 'tools/performance-audit/NuGet.Config')],
        ['dotnet', 'build', str(source / 'iMouse.Console.csproj'), '-c', 'Release', '--no-restore', '-m:1', '-nodeReuse:false', '-o', str(output)],
    ]
    for index, command in enumerate(commands):
        run = subprocess.run(command, cwd=repo, capture_output=True, timeout=120)
        (record / f'negative-{name}-{index}.txt').write_bytes(run.stdout + run.stderr)
        assert run.returncode == 0, (name, index, run.returncode)
    rows.append({'name': name, 'file': file, 'removed': old, 'replacement': new, 'built': True})
(record / 'negative-mutations.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
print('Both negative copies built; no tests or live actions executed by this script.')
