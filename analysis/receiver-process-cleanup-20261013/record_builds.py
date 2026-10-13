"""Record exact offline receiver-lifetime builds and linked production sources."""
import json
from pathlib import Path
import subprocess
import sys

record = Path(__file__).resolve().parent
repo = record.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(repo / 'tools'))
import build_manifest as bm

git = ['git', '-c', 'safe.directory=' + repo.as_posix(), '-C', str(repo)]
head = subprocess.check_output(git + ['rev-parse', 'HEAD'], text=True).strip()
manifest = bm.record(repo, record / 'final-kernel', 'src/iMouse.Kernel/iMouse.Kernel.csproj',
                     {'git_head': head, 'source_snapshot_includes_uncommitted_files': True,
                      'sdk_version': subprocess.check_output(['dotnet', '--version'], text=True).strip()})
assert not bm.verify(manifest, repo, record / 'final-kernel')
(record / 'kernel-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
for label, project, folder, linked in (
    ('process-tests', 'tools/receiver_process_tests/ReceiverProcessTests.csproj', 'final-process-tests',
     ('ReceiverProcessLifetime.cs', 'AirplaySupervisor.cs', 'AirplayProcess.cs', 'ReceiverLog.cs')),
    ('recovery-tests', 'tools/recovery_tests/RecoveryTests.csproj', 'final-recovery',
     ('AirplaySupervisor.cs', 'ReceiverLog.cs')),
):
    sources = bm.source_snapshot(repo, project)
    for filename in linked:
        name = 'src/iMouse.Kernel/' + filename
        sources[name] = {'sha256': bm.sha256(repo / name), 'bytes': (repo / name).stat().st_size}
    test_manifest = {'project': project, 'linked_sources_included': True,
                     'sources': sources, 'artifacts': bm.snapshot(record / folder)}
    (record / (label + '-manifest.json')).write_text(json.dumps(test_manifest, indent=2), encoding='utf-8')

before = {'scope': 'initial extraction preserves original startup/dispose order; nine fake cases',
          'sources': {p.name: {'sha256': bm.sha256(p), 'bytes': p.stat().st_size}
                      for p in record.glob('*-before.cs.txt')},
          'artifacts': bm.snapshot(record / 'before')}
(record / 'before-manifest.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
print(json.dumps({'kernel_sha256': manifest['artifacts']['iMouse2.Kernel.dll']['sha256'],
                  'kernel_source_and_output_verified': True}, indent=2))
