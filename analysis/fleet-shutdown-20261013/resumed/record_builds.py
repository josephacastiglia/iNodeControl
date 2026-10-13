"""Record the verified offline builds and linked source; do not launch anything."""
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

record = Path(__file__).resolve().parent
repo = record.parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(repo / 'tools'))
import build_manifest as bm

base = subprocess.check_output(['git', '-c', 'safe.directory=' + repo.as_posix(), '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
for name, project, output in (
    ('kernel', 'src/iMouse.Kernel/iMouse.Kernel.csproj', 'final-kernel'),
    ('recovery', 'tools/recovery_tests/RecoveryTests.csproj', 'expanded-recovery'),
    ('frame', 'tools/frame_tests/FrameTests.csproj', 'frame-tests'),
    ('process', 'tools/receiver_process_tests/ReceiverProcessTests.csproj', 'process-tests'),
):
    result = bm.record(repo, record / output, project, {'base_commit': base, 'includes_working_changes': True})
    for item in ET.parse(repo / project).iter('Compile'):
        included = item.attrib.get('Include')
        if included:
            source = (repo / project).parent / included
            key = source.resolve().relative_to(repo).as_posix()
            result['sources'][key] = {'sha256': bm.sha256(source), 'bytes': source.stat().st_size}
    (record / (name + '-manifest.json')).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(name, len(result['sources']), 'source files;', len(result['artifacts']), 'artifacts')

protected = json.loads((repo / 'analysis/candidate-retry-20261013/restoration-files.json').read_text(encoding='utf-8-sig'))
checked = []
for row in protected:
    if Path(row['path']).name in ('receiver-C24C.log', 'receiver-C241.log'):
        continue
    current = bm.sha256(Path(row['path']))
    checked.append({'path': row['path'], 'sha256': current, 'expected': row['sha256'], 'matches': current == row['sha256']})
(record / 'protected-files-verified.json').write_text(json.dumps(checked, indent=2) + '\n', encoding='utf-8')
assert all(row['matches'] for row in checked), 'Protected installed files changed; inspect record'
print('Installed static files/settings verified unchanged; no live status request.')
