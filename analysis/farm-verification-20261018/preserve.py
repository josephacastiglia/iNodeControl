"""Keep exact binaries, source and private C24C regression evidence outside Git."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(__file__).resolve().parent
ARCHIVE = ROOT.parent / 'iMouseXP-2.0-evidence-archive/20261018-farm-verification'
ARCHIVE.mkdir(parents=True, exist_ok=False)


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if source.read_bytes() != target.read_bytes(): raise RuntimeError('Archive copy mismatch: ' + str(source))


for file in RUN.rglob('*'):
    if file.is_file() and '__pycache__' not in file.parts: copy(file, ARCHIVE / 'run' / file.relative_to(RUN))
native = ROOT / 'output/codex-farm-verification-20261018'
for file in native.rglob('*'):
    if file.is_file(): copy(file, ARCHIVE / 'candidate' / file.relative_to(native))
prior = ROOT / 'analysis/farm-phone-transfer-20261017'
for name in ('test-carousel.zip', 'test-draft.json', 'README.md'):
    copy(prior / name, ARCHIVE / 'regression-inputs' / name)
for step in ('05-instagram-profile', '43-caption-ok', '47-open-drafts-library', '50-reopened-caption'):
    copy(prior / step / 'after.png', ARCHIVE / 'regression-inputs' / step / 'after.png')
sources = [ROOT / name for name in ('MARKETING-FARM-STATUS.md', 'MARKETING-FARM-ACCEPTANCE.md',
                                   'Open Marketing Farm Candidate.ps1', 'tools/requirements-farm.txt',
                                   'tools/imouse_farm_server.py', 'tools/imouse_social_automation.py', 'tools/Read-FarmImageText.ps1')]
sources += list((ROOT / 'tools').glob('farm_*.py')) + list((ROOT / 'tools').glob('test_farm*.py'))
for pattern in ('*.cs', '*.xaml', '*.csproj'): sources += list((ROOT / 'src/iMouse.Console').glob(pattern))
for file in sorted(set(sources)): copy(file, ARCHIVE / 'source' / file.relative_to(ROOT))
inventory = {file.relative_to(ARCHIVE).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
             for file in sorted(ARCHIVE.rglob('*')) if file.is_file()}
(ARCHIVE / 'SHA256SUMS.txt').write_text(''.join(f'{digest}  {name}\n' for name, digest in inventory.items()), encoding='utf-8')
assert all(hashlib.sha256((ARCHIVE / name).read_bytes()).hexdigest() == digest for name, digest in inventory.items())
print(json.dumps(dict(archive=str(ARCHIVE), verifiedFiles=len(inventory), bytes=sum((ARCHIVE / name).stat().st_size for name in inventory))))
