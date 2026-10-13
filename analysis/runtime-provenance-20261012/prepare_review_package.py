"""Copy current reviewed binaries with the enriched runtime; never launch anything."""
import json
from pathlib import Path
import subprocess
import sys

record = Path(__file__).resolve().parent
repo = record.parents[1]
sys.path.insert(0, str(repo / 'tools'))
import stage_release as p
import stage_receiver_runtime as runtime

prior = repo / 'output/staging/combined-input-cleanup-20261012'
assert p.verify(prior) == []
out = repo / 'output/staging/combined-runtime-provenance-final-20261012'
manifest = p.stage(repo, out, {
    'console': (repo / 'analysis/input-cleanup-20261012/candidate-console', repo / 'analysis/input-cleanup-20261012/console-manifest.json'),
    'kernel': (repo / 'analysis/persistence-20261012/final-kernel', repo / 'analysis/persistence-20261012/kernel-manifest.json')},
    prior / 'payload/receiver/uxplay.exe', prior / 'provenance/receiver.json', prior / 'source/receiver',
    repo / 'docs/RELEASE-STAGING.md', repo / 'output/staging/native-runtime-provenance-final-20261012', repo / 'docs/OPERATOR-GUIDE.md')
before = p.load(prior / 'package.json')
payload = lambda files: {k: v for k, v in files.items() if k.startswith(('payload/', 'source/')) or '/runtime/' in k}
assert payload(before['files']) == payload(manifest['files']), 'Product or runtime bytes changed'
for tool, root in ((out / 'verify_package.py', out), (out / 'dependencies/receiver-runtime/verify_runtime.py', out / 'dependencies/receiver-runtime')):
    run = subprocess.run([sys.executable, '-E', '-s', str(tool), 'verify', '--bundle', str(root)], capture_output=True, check=True)
    (record / (tool.stem + '-result.txt')).write_bytes(run.stdout + run.stderr)
protected = []
for row in p.load(repo / 'analysis/input-cleanup-20261012/protected-files.json'):
    path = Path(row['path'])
    assert p.bm.sha256(path) == row['sha256'], str(path)
    protected.append({'path': str(path), 'sha256': row['sha256'], 'matches_previous_record': True})
(record / 'protected-files.json').write_text(json.dumps(protected, indent=2), encoding='utf-8')
armored = repo.parent / 'iMouseXP-2.0/tools/airplay/msys64/usr/share/pacman/keyrings/msys2.gpg'
converted = record / 'msys2-public-keyring.gpg'
(record / 'keyring-record.json').write_text(json.dumps({'installed_public_armored': p.row(armored),
    'converted_binary_public': p.row(converted),
    'conversion': 'gpg --no-options --batch --no-tty --homedir <isolated-empty-home> --output <scratch-public-keyring> --dearmor <installed-public-keyring>',
    'scope': 'Public key material only; no imported private keys, signing, network or trust database refresh.'}, indent=2), encoding='utf-8')
result = {'package': str(out), 'files': len(manifest['files']), 'all_package_hashes_verified': True,
    'standalone_parent_and_runtime_verifiers_pass': True, 'product_source_and_payload_unchanged': True,
    'prior_package_unchanged': p.verify(prior) == [], 'installed_hashes_unchanged': True,
    'launched': False, 'status': manifest['status']}
(record / 'package-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
