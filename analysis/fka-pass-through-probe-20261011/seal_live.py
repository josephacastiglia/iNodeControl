"""Copy and verify the completed live window without replacing any previous evidence."""
import hashlib
import shutil
from pathlib import Path

record = Path(__file__).resolve().parent
repo = record.parents[1]
live = record / 'live-20261011'
archive = repo.parent / 'iMouseXP-2.0-evidence-archive/20261011-fka-pass-through-live'
if archive.exists():
    raise SystemExit('Refusing to replace an existing live archive')
if not (live / 'restoration-verified.json').exists():
    raise SystemExit('Restoration record is required before sealing')
files = [(p, Path('live') / p.relative_to(live)) for p in live.rglob('*') if p.is_file()]
files += [(p, Path('tools') / p.name) for p in record.iterdir() if p.is_file() and p.suffix in ('.py', '.md')]
files += [(p, Path('build') / p.name) for p in (record / 'build').iterdir() if p.is_file()]
for name in ('provenance.json', 'candidate.patch', 'invalid-startup-results.json', 'self-tests.txt', 'self-tests-full.txt'):
    source = record / name
    if source.is_file():
        files.append((source, Path('offline-record') / name))
for source in (repo / 'src/iMouse.Kernel').glob('*.cs'):
    files.append((source, Path('source/iMouse.Kernel') / source.name))
files.append((repo / 'src/iMouse.Kernel/iMouse.Kernel.csproj', Path('source/iMouse.Kernel/iMouse.Kernel.csproj')))
main = repo.parent / 'iMouseXP-2.0'
for relative in ('PROGRESS.md', 'analysis/fka-typing-mode-20261011/OFFLINE-INVESTIGATION.md'):
    files.append((main / relative, Path('main-record') / relative))
lines = []
for original, relative in sorted(files, key=lambda x: x[1].as_posix()):
    target = archive / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(original, target)
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest, relative
    lines.append(f'{digest}  {relative.as_posix()}')
(archive / 'SHA256SUMS.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print(f'Archived {len(files)} files; every copy hash-verified')
print(archive)
