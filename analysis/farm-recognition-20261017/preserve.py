"""Preserve this increment and its private regression inputs without overwriting archives."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(__file__).resolve().parent
ARCHIVE = ROOT.parent / 'iMouseXP-2.0-evidence-archive/20261017-farm-recognition'
ARCHIVE.mkdir(parents=True, exist_ok=False)


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(target.read_bytes()).digest():
        raise RuntimeError('Copy mismatch: ' + str(source))


for file in RUN.rglob('*'):
    if file.is_file() and '__pycache__' not in file.parts:
        copy(file, ARCHIVE / 'run' / file.relative_to(RUN))
native = ROOT / 'output/codex-farm-recognition-20261017'
for file in native.rglob('*'):
    if file.is_file(): copy(file, ARCHIVE / 'candidate' / file.relative_to(native))
prior = ROOT / 'analysis/farm-observations-20261017'
for file in prior.glob('*.json'):
    copy(file, ARCHIVE / 'regression-inputs' / file.relative_to(ROOT))
for step in ('39-caption-review', '47-open-drafts-library', '50-reopened-caption'):
    file = ROOT / 'analysis/farm-phone-transfer-20261017' / step / 'after.png'
    copy(file, ARCHIVE / 'regression-inputs' / file.relative_to(ROOT))
sources = [ROOT / name for name in ('MARKETING-FARM-STATUS.md', 'MARKETING-FARM-ACCEPTANCE.md',
                                   'Open Marketing Farm Candidate.ps1', 'tools/requirements-farm.txt',
                                   'tools/imouse_farm_server.py', 'tools/imouse_social_automation.py',
                                   'tools/Read-FarmImageText.ps1')]
sources += list((ROOT / 'tools').glob('farm_*.py')) + list((ROOT / 'tools').glob('test_farm*.py'))
for directory in ('src/iMouse.Console', 'src/iMouse.Kernel', 'tools/frame_tests'):
    for pattern in ('*.cs', '*.xaml', '*.csproj'):
        sources += list((ROOT / directory).glob(pattern))
for file in sorted(set(sources)): copy(file, ARCHIVE / 'source' / file.relative_to(ROOT))
inventory = {str(file.relative_to(ARCHIVE)).replace('\\', '/'): hashlib.sha256(file.read_bytes()).hexdigest()
             for file in sorted(ARCHIVE.rglob('*')) if file.is_file()}
(ARCHIVE / 'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name, digest in inventory.items()), encoding='utf-8')
for name, digest in inventory.items():
    if hashlib.sha256((ARCHIVE / name).read_bytes()).hexdigest() != digest: raise RuntimeError('Archive mismatch: ' + name)
print(json.dumps({'archive': str(ARCHIVE), 'filesVerified': len(inventory),
                  'bytes': sum((ARCHIVE / name).stat().st_size for name in inventory)}))
