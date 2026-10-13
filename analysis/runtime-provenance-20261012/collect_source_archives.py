"""Fetch exact public source packages for notice gaps; never run package build scripts."""
import json
from pathlib import Path
import re
import subprocess
import sys

record = Path(__file__).resolve().parent
repo = record.parents[1]
sys.path.insert(0, str(repo / 'tools'))
import runtime_package_provenance as provenance

capsule = repo / 'output/staging/native-runtime-notices-20261012'
binary = json.loads((repo / 'output/provenance/native-packages-20261012/package-provenance.json').read_text(encoding='utf-8'))
gaps = json.loads((capsule / 'runtime.json').read_text(encoding='utf-8'))['notice_gaps']
out = repo / 'output/provenance/native-sources-20261012'
out.mkdir(exist_ok=False)
tar = Path('C:/Windows/System32/tar.exe')
curl = Path('C:/Windows/System32/curl.exe')
gpgv = repo.parent / 'iMouseXP-2.0/tools/airplay/msys64/usr/bin/gpgv.exe'
keyring = record / 'msys2-public-keyring.gpg'
groups = {}
for item in binary['packages']:
    if item['name'] in gaps:
        assert item['state'] == 'verified' and len(item['pkgbase']) == 1
        groups.setdefault((item['pkgbase'][0], item['version'], item['pkgbuild_sha256']), []).append(item['name'])
results = []
for (base, version, expected_recipe), packages in groups.items():
    assert re.fullmatch(r'[A-Za-z0-9_.+~-]+', base) and re.fullmatch(r'[A-Za-z0-9_.+~-]+', version)
    filename = f'{base}-{version}.src.tar.zst'
    destination = out / (base + '-' + version)
    destination.mkdir()
    result = {'base': base, 'version': version, 'packages': packages, 'expected_recipe_sha256': expected_recipe, 'state': 'unverified'}
    try:
        transfers = []
        for suffix, maximum in (('', 256 * 1024 * 1024), ('.sig', 65536)):
            url = 'https://mirror.msys2.org/mingw/sources/' + filename + suffix
            path = destination / (filename + suffix)
            run = subprocess.run([str(curl), '--silent', '--show-error', '--fail', '--location', '--max-time', '120',
                '--proto', '=https', '--proto-redir', '=https', '--max-filesize', str(maximum),
                '--output', str(path), '--write-out', '%{url_effective}', url], capture_output=True, timeout=130)
            transfers.append({'requested': url, 'final': run.stdout.decode('utf-8', errors='replace'), 'exit_code': run.returncode})
            if run.returncode != 0: raise ValueError('Download failed: ' + run.stderr.decode('utf-8', errors='replace'))
            if path.stat().st_size > maximum: raise ValueError('Downloaded file exceeded the limit')
        result['transfers'] = transfers
        archive = destination / filename
        sig = destination / (filename + '.sig')
        verified = provenance.run([str(gpgv), '--status-fd', '1', '--keyring', provenance.msys_path(keyring), provenance.msys_path(sig), provenance.msys_path(archive)])
        (destination / 'signature-status.txt').write_bytes(verified.stdout)
        (destination / 'signature-log.txt').write_bytes(verified.stderr)
        result['signing_fingerprint'] = provenance.signature(verified.stdout, verified.returncode)
        listing = subprocess.run([str(tar), '-tf', str(archive)], capture_output=True, check=True, timeout=90).stdout
        (destination / 'archive-members.txt').write_bytes(listing)
        members = listing.decode('utf-8').splitlines()
        recipes = [m for m in members if m.endswith('/PKGBUILD') or m == 'PKGBUILD']
        if len(recipes) != 1: raise ValueError('No unique build recipe')
        recipe = provenance.read_member(archive, recipes[0], tar, provenance.run, 1024 * 1024)
        (destination / 'PKGBUILD').write_bytes(recipe)
        actual = provenance.sha(recipe)
        result['recipe_sha256'] = actual
        if actual != expected_recipe: raise ValueError('Source recipe does not match signed binary BUILDINFO')
        result.update(state='signature_and_recipe_verified', archive_sha256=provenance.sha(archive.read_bytes()), archive_bytes=archive.stat().st_size)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        result['error'] = str(error)
    results.append(result)
    (out / 'source-provenance.json').write_text(json.dumps({'sources': results,
        'scope': 'Exact public source packages, signature and recipe links only. Nested source hashes, extracted notices and complete corresponding source not yet verified.'}, indent=2), encoding='utf-8')
    print(f'{len(results)}/{len(groups)}: {base}: {result["state"]}', flush=True)
