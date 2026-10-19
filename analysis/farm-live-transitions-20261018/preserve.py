"""Archive this completed local validation window without uploading or deleting."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARCHIVE = ROOT.parent/'iMouseXP-2.0-evidence-archive'/'20261018-farm-live-transitions'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == '__main__':
    final = json.loads((HERE/'final-rack.json').read_text(encoding='utf-8-sig'))
    if not final['allProtectedFilesUnchanged'] or not final['initialStoppedStateRestored']:
        raise ValueError('Complete restoration auditing before the final archive.')
    if ARCHIVE.exists():
        raise FileExistsError('Never overwrite an earlier evidence archive.')
    ARCHIVE.mkdir(parents=True)
    pairs = []
    for source in sorted(HERE.rglob('*')):
        if not source.is_file() or '__pycache__' in source.parts or source.name=='archive-summary.json': continue
        target = ARCHIVE/'records'/source.relative_to(HERE)
        target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target); pairs.append((source,target))
    extras = [ROOT/'.gitattributes', ROOT/'MARKETING-FARM-STATUS.md', ROOT/'Open Marketing Farm Candidate.ps1',
              ROOT/'analysis/farm-phone-transfer-20261017/test-carousel.zip']
    extras += [ROOT/'tools'/name for name in ('test_farm_inspection_evidence.py','test_farm_screen_layout.py',
                                            'test_farm_transitions.py','test_farm_carousel_continuity.py')]
    for source in extras:
        target = ARCHIVE/'final-source'/source.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source,target); pairs.append((source,target))
    for source,target in pairs:
        if digest(source)!=digest(target): raise ValueError('Copy mismatch: '+str(source))
    commit = subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),'-C',str(ROOT),'rev-parse','HEAD'],text=True).strip()
    metadata = dict(sourceCommit=commit,createdUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    earlierPreparationArchive=str(ARCHIVE.with_name(ARCHIVE.name+'-preparation')),
                    copiedFiles=len(pairs),allCopiesVerified=True,uploaded=False)
    (ARCHIVE/'ARCHIVE.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    inventory = {f.relative_to(ARCHIVE).as_posix():dict(bytes=f.stat().st_size,sha256=digest(f))
                 for f in sorted(ARCHIVE.rglob('*')) if f.is_file()}
    (ARCHIVE/'SHA256SUMS.json').write_text(json.dumps(inventory,indent=2)+'\n',encoding='utf-8')
    for name,row in inventory.items():
        if digest(ARCHIVE/name)!=row['sha256']: raise ValueError('Archive verification failed: '+name)
    summary = dict(path=str(ARCHIVE),files=len(inventory),bytes=sum(r['bytes'] for r in inventory.values()),
                   manifestSha256=digest(ARCHIVE/'SHA256SUMS.json'),**metadata)
    (HERE/'archive-summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))
