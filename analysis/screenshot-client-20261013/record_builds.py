"""Record existing offline build bytes; never build, start or promote a component."""
import json
from pathlib import Path
import shutil
import sys

record = Path(__file__).resolve().parent
repo = record.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(repo / 'tools'))
import build_manifest as bm

artifacts = record / 'console-artifacts'
artifacts.mkdir(exist_ok=False)
for suffix in ('.exe', '.dll', '.deps.json', '.runtimeconfig.json', '.pdb'):
    source = record / 'final-console' / ('iMouse2' + suffix)
    shutil.copy2(source, artifacts / source.name)
    assert bm.sha256(source) == bm.sha256(artifacts / source.name)
shutil.copy2(record / 'final-console/qa/self-tests.json', record / 'self-tests.json')
console = bm.record(repo, artifacts, 'src/iMouse.Console/iMouse.Console.csproj',
                    {'base_commit': 'a170ff1', 'scope': 'working source; mock self-tests only, no UI/phone acceptance'})
assert not bm.verify(console, repo, artifacts)
(record / 'console-manifest.json').write_text(json.dumps(console, indent=2), encoding='utf-8')
for name, project, output, linked in (
    ('preview', 'tools/preview_tests/PreviewTests.csproj', 'verified-preview',
     ['ApiClient.cs', 'InputLeaseClient.cs', 'PreviewFreshness.cs']),
    ('wall', 'tools/wall_tests/WallTests.csproj', 'final-wall',
     ['ApiClient.cs', 'InputLeaseClient.cs', 'PreviewFreshness.cs', 'TileStreams.cs', 'FrameMetrics.cs']),
):
    manifest = bm.record(repo, record / output, project, {'scope': 'headless test tool with explicit linked source inventory'})
    for filename in linked:
        path = 'src/iMouse.Console/' + filename
        manifest['sources'][path] = {'sha256': bm.sha256(repo / path), 'bytes': (repo / path).stat().st_size}
    (record / (name + '-manifest.json')).write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(json.dumps({'console_dll': console['artifacts']['iMouse2.dll'],
                  'source_files': len(console['sources']), 'artifacts': len(console['artifacts'])}, indent=2))
