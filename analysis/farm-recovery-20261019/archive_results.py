"""Preserve this offline candidate, cloned data and reports; never delete sources."""
import hashlib
import json
from pathlib import Path
import re
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
validation = json.loads((HERE/'validation.json').read_bytes())
target = Path(validation['archive'])
if target.exists(): raise SystemExit('Archive exists. Preserve it; do not overwrite a prior snapshot.')
target.mkdir(parents=True)
def copy(source, relative):
    output = target/relative
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(output.read_bytes()).digest():
        raise RuntimeError('Archive copy differs: '+str(relative))
for path in HERE.rglob('*'):
    if path.is_file() and not {'obj','bin','__pycache__'}.intersection(path.relative_to(HERE).parts):
        copy(path, Path('record')/path.relative_to(HERE))
launcher = (ROOT/'Open Marketing Farm Candidate.ps1').read_text(encoding='utf-8-sig')
section = launcher.split('foreach ($name in @(', 1)[1].split(')) {', 1)[0]
for name in re.findall("'([^']+)'", section): copy(ROOT/'tools'/name, Path('runtime-source/tools')/name)
for name in validation['productSourceFiles']: copy(ROOT/name, Path('changed-source')/name)
for folder, label in [('output/codex-farm-recovery-20261019','native'),
                      ('output/farm-recovery-native-probe-20261019','headless-driver'),
                      ('output/candidate-runs/farm-recovery-20261019/backend','backend-copy')]:
    base = ROOT/folder
    for path in base.rglob('*'):
        if path.is_file(): copy(path, Path(label)/path.relative_to(base))
files = sorted(p for p in target.rglob('*') if p.is_file())
manifest = '\n'.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(target).as_posix() for p in files)+'\n'
(target/'SHA256SUMS.txt').write_text(manifest, encoding='utf-8', newline='\n')
summary = dict(archive=str(target), files=len(files), bytes=sum(p.stat().st_size for p in files),
    manifestSha256=hashlib.sha256((target/'SHA256SUMS.txt').read_bytes()).hexdigest(),
    allCopiesVerified=True, sourceCommit=validation['sourceCommit'], uploaded=False)
(HERE/'archive-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary))
