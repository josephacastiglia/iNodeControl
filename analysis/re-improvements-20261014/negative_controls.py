"""Run focused mock tests against isolated source copies with two guards removed."""
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
source = REPO / 'src/iMouse.Kernel'
cases = {
    'baseline': None,
    'tab-reintroduced': ('if (Navigation == NavigationSequence.Vendor) await Stroke(state,0,43);',
                         'await Stroke(state,0,43);'),
    'probe-activation-guard-removed': ('&& fun is not ("/mouse/reset" or "/mouse/move"))', '&& false)'),
}
results = []
for name, mutation in cases.items():
    folder = HERE / ('negative-' + name)
    folder.mkdir(exist_ok=False)
    for file in source.iterdir():
        if file.suffix in ('.cs', '.csproj') and file.name != 'Program.cs':
            shutil.copy2(file, folder / file.name)
    (folder / 'Program.cs').write_text('using IMouse2.Kernel;\nint passed=0;\n'
        'await InputSessionTests.NavigationAndProbeAsync((ok, label) => { if (!ok) throw new Exception(label); passed++; });\n'
        'Console.WriteLine($"{passed} focused checks passed; fake transport only.");\n', encoding='utf-8')
    if mutation:
        file = folder / 'InputRouter.cs'
        content = file.read_text(encoding='utf-8')
        assert content.count(mutation[0]) == 1, name
        file.write_text(content.replace(*mutation), encoding='utf-8')
    built = subprocess.run(['dotnet', 'build', str(folder / 'iMouse.Kernel.csproj'), '-c', 'Release', '-o', str(folder / 'out')],
                           capture_output=True, timeout=120)
    (folder / 'build.txt').write_bytes(built.stdout + built.stderr)
    assert built.returncode == 0, name
    tested = subprocess.run(['dotnet', str(folder / 'out/iMouse2.Kernel.dll')], capture_output=True, timeout=30)
    (folder / 'test.txt').write_bytes(tested.stdout + tested.stderr)
    text = (tested.stdout + tested.stderr).decode(errors='replace')
    expected = (tested.returncode == 0 if mutation is None else tested.returncode != 0 and
                ('DirectFn AppSwitch exact reports' if name == 'tab-reintroduced' else 'Absolute probe refuses activation before transport') in text)
    results.append(dict(case=name, exit=tested.returncode, expected_result=expected, output=text[-1200:]))
    assert expected, name
(HERE / 'negative-controls.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print('Baseline passes; both guard-removal controls fail on the intended assertion.')
