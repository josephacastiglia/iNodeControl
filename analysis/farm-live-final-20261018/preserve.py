"""Preserve the completed validation locally; no network or phone access."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARCHIVE = ROOT.parent / 'iMouseXP-2.0-evidence-archive/20261018-farm-live-final'
REFERENCES = ROOT.parent / 'iMouseXP-2.0-evidence-archive/20261018-farm-live-layout'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_verified(source, destination, *, source_root=ROOT):
    source = source.resolve()
    if not source.is_relative_to(source_root.resolve()):
        raise ValueError('Source escapes its verified root: ' + str(source))
    raw = source.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    if destination.read_bytes() != raw:
        raise ValueError('Archive copy differs: ' + str(destination))


def main():
    final = read(HERE / 'final-validation.json')
    restored = read(HERE / 'final-rack.json')
    assert final['status'] == 'bounded_live_validation_passed'
    assert final['fullLivePasses'] == 2 and final['allOwnLeasesReleased']
    assert restored['initialStoppedStateRestored'] and restored['allProtectedFilesUnchanged']
    sources = read(HERE / 'validation-sources.json')['files']
    for path, expected in sources.items():
        assert digest(Path(path)) == expected, path
    references = read(HERE / 'reference-frames.json')
    for row in references.values():
        reference = Path(row['path']).resolve()
        assert reference.is_relative_to(REFERENCES.resolve())
        assert digest(reference) == row['sha256']
        assert (reference.parent / 'record.json').is_file()
    commit = subprocess.check_output(
        ['git', '-c', 'safe.directory=' + ROOT.as_posix(), 'rev-parse', 'HEAD'],
        cwd=ROOT, text=True).strip()
    ARCHIVE.mkdir(parents=True, exist_ok=False)
    for source in sorted(HERE.rglob('*')):
        if not source.is_file() or '__pycache__' in source.parts or source.name == 'archive-summary.json':
            continue
        copy_verified(source, ARCHIVE / 'records' / source.relative_to(HERE))
    for path in sources:
        source = Path(path)
        copy_verified(source, ARCHIVE / 'source' / source.relative_to(ROOT))
    for source in (
        ROOT / '.gitattributes', ROOT / 'MARKETING-FARM-STATUS.md',
        ROOT / 'analysis/farm-phone-transfer-20261017/test-carousel.zip',
        ROOT / 'tools/stage_release.py', ROOT / 'tools/validate_rack_config.py',
    ):
        copy_verified(source, ARCHIVE / 'source' / source.relative_to(ROOT))
    # Retain the original control images and OCR records used by the offline suite.
    for row in references.values():
        source = Path(row['path'])
        assert digest(source) == row['sha256']
        for item in (source, source.parent / 'record.json'):
            copy_verified(item, ARCHIVE / 'references' / item.relative_to(REFERENCES),
                          source_root=REFERENCES)
    preparation = read(HERE / 'preparation.json')
    native = Path(preparation['kernel'])
    assert digest(native.with_suffix('.dll')) == preparation['validation']['build']['sha256']
    for item in native.parent.glob('iMouse2.Kernel.*'):
        if item.is_file():
            copy_verified(item, ARCHIVE / 'native-kernel' / item.name)
    for name in ('devices.json', 'receivers.json', 'pointer-calibration.json'):
        copy_verified(Path(preparation['runDirectory']) / 'data' / name,
                      ARCHIVE / 'private-config' / name)
    metadata = dict(
        createdUtc=datetime.now(timezone.utc).isoformat(), sourceCommit=commit,
        productSourceCommit=final['productSourceCommit'], fullLivePasses=2,
        restored=True, uploaded=False,
        receiverRuntime='Preserved validated runtime identified by preparation.json; not duplicated here.',
        earlierPreparationArchive=str(ARCHIVE.with_name('20261018-farm-live-final-preparation')),
    )
    (ARCHIVE / 'ARCHIVE.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    inventory = {p.relative_to(ARCHIVE).as_posix(): digest(p)
                 for p in sorted(ARCHIVE.rglob('*')) if p.is_file()}
    (ARCHIVE / 'SHA256SUMS.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
    assert all(digest(ARCHIVE / name) == value for name, value in inventory.items())
    summary = dict(path=str(ARCHIVE), files=len(inventory),
                   bytes=sum((ARCHIVE / name).stat().st_size for name in inventory),
                   allCopiesVerified=True, manifestSha256=digest(ARCHIVE / 'SHA256SUMS.json'),
                   sourceCommit=commit, uploaded=False)
    (HERE / 'archive-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
