"""Download pinned analysis tools only. Never launches the vendor application."""
from pathlib import Path
import concurrent.futures
import hashlib
import json
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[3] / '.tooling' / 'imouse-rea-20261014'
PACKAGES = [
    ('ghidra', 'https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.4_build/ghidra_12.1.4_PUBLIC_20260921.zip', 'ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db'),
    ('jdk', 'https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk_x64_windows_hotspot_21.0.12.1_1.zip', 'f9d6e191ab098c0d416e7d588a24420a8621cd2f4720dab2459b8b7b2d2d8b4e'),
]

def prepare(item):
    name, url, digest = item
    archive = ROOT / (name + '.zip')
    if not archive.exists():
        req = urllib.request.Request(url, headers={'User-Agent': 'iMouse-offline-analysis'})
        with urllib.request.urlopen(req, timeout=45) as response, archive.open('wb') as out:
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
    actual = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
    if actual != digest:
        raise ValueError(f'{name} SHA256 mismatch: {actual}')
    dest = ROOT / name
    if not dest.exists():
        with zipfile.ZipFile(archive) as z:
            for entry in z.infolist():
                if not (dest / entry.filename).resolve().is_relative_to(dest.resolve()):
                    raise ValueError('Archive path leaves destination')
            z.extractall(dest)
    return {'name': name, 'url': url, 'sha256': actual, 'bytes': archive.stat().st_size, 'directory': str(dest)}

if __name__ == '__main__':
    ROOT.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(prepare, PACKAGES))
    (ROOT / 'tool-downloads.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results, indent=2))
