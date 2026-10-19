"""Preserve this completed run outside the checkout; no network or processes."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[1]
ARCHIVE = ROOT.parent / 'iMouseXP-2.0-evidence-archive/20261018-farm-live-verification'
git = ['git', '-c', 'safe.directory=' + ROOT.as_posix()]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    head = subprocess.check_output(git + ['rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    if subprocess.check_output(git + ['status', '--porcelain', '--untracked-files=no'], cwd=ROOT).strip():
        raise SystemExit('Commit tracked work before taking the final archive.')
    ARCHIVE.mkdir(exist_ok=False)
    copied = {}
    def copy_file(original, relative):
        target = ARCHIVE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        before = digest(original)
        shutil.copy2(original, target)
        if digest(target) != before or digest(original) != before:
            raise RuntimeError('Source changed or copy verification failed: ' + str(original))
        copied[relative.as_posix()] = before
    def copy_tree(original, name):
        for file in sorted(original.rglob('*')):
            if file.is_file() and '__pycache__' not in file.parts:
                copy_file(file, Path(name) / file.relative_to(original))
    copy_tree(RUN, 'run')
    copy_tree(ROOT / 'output/codex-farm-live-kernel-20261018', 'test-kernel')
    copy_tree(ROOT / 'output/candidate-runs/farm-live-20261018', 'test-runtime')
    # Keep the native binary separate: it did not run in this API-only test.
    native = ROOT / 'output/codex-farm-preparation-20261018'
    for file in native.iterdir():
        if file.is_file(): copy_file(file, Path('native-candidate-not-run') / file.name)
    copy_file(ROOT / 'analysis/farm-phone-transfer-20261017/test-carousel.zip', Path('source-media/test-carousel.zip'))
    tracked = subprocess.check_output(git + ['ls-files', '-z'], cwd=ROOT).decode().split('\0')
    for name in tracked:
        if not name: continue
        file = Path(name)
        include = (name.startswith('src/iMouse.Kernel/') or name.startswith('src/iMouse.Console/')
            or name.startswith('tools/farm_') or name.startswith('tools/test_farm')
            or name in ('tools/imouse_farm_server.py', 'tools/imouse_social_automation.py',
                        'tools/Read-FarmImageText.ps1', 'Open Marketing Farm Candidate.ps1',
                        'MARKETING-FARM-STATUS.md', 'MARKETING-FARM-ACCEPTANCE.md',
                        'Directory.Build.props', 'Directory.Build.targets', 'global.json'))
        if include and (ROOT / file).is_file(): copy_file(ROOT / file, Path('source') / file)
    record = dict(commit=head, pushed=False, installedReleaseChanged=False, pcControl=False,
        phoneInputScope='C24C only, supervised existing-draft inspection/save/reopen; no publishing or messaging',
        pythonTests=330, kernelTests=290, savedRecognitionRegressionCases=36,
        sourceCopies=copied, automaticInputAllowed=False,
        restoration='Initial rack stopped; isolated test kernel/receiver stopped; 25 protected file hashes unchanged.')
    (ARCHIVE / 'COMMIT.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    files = [p for p in sorted(ARCHIVE.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS.txt']
    inventory = {p.relative_to(ARCHIVE).as_posix(): digest(p) for p in files}
    (ARCHIVE / 'SHA256SUMS.txt').write_text(''.join(f'{value}  {name}\n' for name, value in inventory.items()), encoding='utf-8')
    assert all(digest(ARCHIVE / name) == value for name, value in inventory.items())
    print(json.dumps(dict(commit=head, archive=str(ARCHIVE), copiedFilesVerified=len(copied),
                          filesVerified=len(inventory), bytes=sum(p.stat().st_size for p in files))))


if __name__ == '__main__':
    main()
