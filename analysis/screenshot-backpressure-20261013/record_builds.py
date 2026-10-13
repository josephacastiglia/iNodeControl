"""Record exact sources/binaries; no launch, packaging or deployment."""
import hashlib
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
test_sources = bm.source_snapshot(repo, 'tools/frame_tests/FrameTests.csproj')
for name in ('src/iMouse.Kernel/FrameStore.cs', 'src/iMouse.Kernel/AirplaySupervisor.cs', 'src/iMouse.Console/FrameMetrics.cs'):
    test_sources[name] = {'sha256': bm.sha256(repo / name), 'bytes': (repo / name).stat().st_size}
test_manifest = {'project': 'tools/frame_tests/FrameTests.csproj', 'linked_sources_included': True,
                 'sources': test_sources, 'artifacts': bm.snapshot(record / 'final-frame-tests')}
(record / 'frame-tests-manifest.json').write_text(json.dumps(test_manifest, indent=2), encoding='utf-8')
(record / 'harness-artifacts.json').write_text(json.dumps(bm.snapshot(record / 'harness'), indent=2), encoding='utf-8')
# Reconstruct the first minimal regression source from the base plus its recorded
# addition. The separate PDB check must match before this is called exact evidence.
baseline = subprocess.check_output(git + ['show', '7aff93e:tools/frame_tests/Program.cs']).decode('utf-8')
addition = '''    ("a stalled screenshot client does not block frame delivery or status", async () => {
        await using var r = new Rig(); await r.Send(Bmp());
        using var entered = new ManualResetEventSlim(); using var release = new ManualResetEventSlim();
        var transfer = Task.Run(() => r.Store.WriteFrame("fake", (_, _) => { entered.Set(); release.Wait(); }));
        Task? progress = null;
        try {
            Check(entered.Wait(TimeSpan.FromSeconds(1)));
            progress = Task.Run(async () => { await r.Send(Bmp()); Check(r.Store.Delivery.Sequence == 2); });
            await progress.WaitAsync(TimeSpan.FromMilliseconds(500));
        } finally {
            release.Set(); await transfer.WaitAsync(TimeSpan.FromSeconds(2));
            if (progress is not null) await progress.WaitAsync(TimeSpan.FromSeconds(2));
        }
    }),
'''
anchor = '    ("independent stores have distinct identities and failure isolation", async () => {'
assert baseline.count(anchor) == 1
baseline = baseline.replace(anchor, addition + anchor).replace('\r\n', '\n').replace('\n', '\r\n')
(record / 'Program-before.cs.txt').write_bytes(baseline.encode('utf-8'))
print(json.dumps({'kernel_sha256': manifest['artifacts']['iMouse2.Kernel.dll']['sha256'],
                  'kernel_source_and_output_verified': True, 'frame_sources': len(test_sources),
                  'baseline_program_reconstruction_sha256': hashlib.sha256(baseline.encode()).hexdigest()}, indent=2))
