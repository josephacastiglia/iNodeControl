"""Verify cached MSYS2 packages against a staged runtime, without installing or running them."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from datetime import datetime, timezone

import stage_receiver_runtime as runtime

MAX_MEMBER = 256 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def metadata(raw):
    result = {}
    for line in raw.decode('utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        key, separator, value = line.partition(' = ')
        if not separator:
            raise ValueError('Invalid package metadata line')
        result.setdefault(key, []).append(value)
    return result


def single(values, key):
    result = values.get(key)
    if not isinstance(result, list) or len(result) != 1 or not isinstance(result[0], str):
        raise ValueError(f'Expected one {key}')
    return result[0]


def msys_path(path):
    path = str(Path(path).resolve()).replace('\\', '/')
    if re.match(r'^[A-Za-z]:/', path):
        return '/' + path[0].lower() + path[2:]
    return path


def run(command):
    return subprocess.run(command, capture_output=True, timeout=90)


def signature(status, code):
    lines = status.decode('utf-8', errors='replace').splitlines()
    errors = ('BADSIG', 'ERRSIG', 'NO_PUBKEY', 'EXPSIG', 'EXPKEYSIG', 'REVKEYSIG', 'KEYEXPIRED', 'SIGEXPIRED')
    if code != 0 or any(any(line.startswith('[GNUPG:] ' + error) for error in errors) for line in lines):
        raise ValueError('Package signature was not verified with the selected local keyring')
    valid = [line.split() for line in lines if line.startswith('[GNUPG:] VALIDSIG ')]
    if len(valid) != 1 or len(valid[0]) < 4 or not re.fullmatch(r'[0-9A-Fa-f]{40,64}', valid[0][2]):
        raise ValueError('No single valid signing fingerprint in gpgv result')
    return valid[0][2].upper()


def read_member(archive, member, tar, runner, limit=MAX_MEMBER):
    if member not in ('.PKGINFO', '.BUILDINFO'):
        runtime.package.safe(archive.parent, member)
    # -O returns one explicit member to memory; nothing is extracted to the filesystem.
    found = runner([str(tar), '-xOf', str(archive), member])
    if found.returncode != 0:
        raise ValueError(f'Cannot read archive member: {member}')
    if len(found.stdout) > limit:
        raise ValueError(f'Archive member exceeds the permitted size: {member}')
    return found.stdout


def audit_package(item, capsule, cache, out, tar, gpgv, keyring, runner=run):
    name, version = single(item, 'name'), single(item, 'version')
    if not all(re.fullmatch(r'[A-Za-z0-9_.+~-]+', text) for text in (name, version)):
        raise ValueError('Unsafe package name or version')
    desc = runtime.fields(runtime.package.safe(capsule, item['metadata_files'][0]))
    architecture = single(desc, 'ARCH')
    if not re.fullmatch(r'[A-Za-z0-9_]+', architecture):
        raise ValueError('Unsafe package architecture')
    archive = runtime.package.safe(cache, f'{name}-{version}-{architecture}.pkg.tar.zst')
    sig = archive.with_name(archive.name + '.sig')
    if not archive.is_file() or not sig.is_file():
        raise ValueError('Exact cached package or its detached signature is missing')
    if archive.stat().st_size > 512 * 1024 * 1024 or sig.stat().st_size > 64 * 1024:
        raise ValueError('Cached package or signature exceeds the permitted size')
    before = runtime.package.row(archive)
    before_sig = runtime.package.row(sig)
    verified = runner([str(gpgv), '--status-fd', '1', '--keyring', msys_path(keyring), msys_path(sig), msys_path(archive)])
    fingerprint = signature(verified.stdout, verified.returncode)
    pkginfo = read_member(archive, '.PKGINFO', tar, runner, 1024 * 1024)
    buildinfo = read_member(archive, '.BUILDINFO', tar, runner, 2 * 1024 * 1024)
    pkg, build = metadata(pkginfo), metadata(buildinfo)
    if single(pkg, 'pkgname') != name or single(pkg, 'pkgver') != version or single(pkg, 'arch') != architecture:
        raise ValueError('Archive identity disagrees with the installed receipt')
    if name not in build.get('pkgname', []) or single(build, 'pkgver') != version:
        raise ValueError('Build metadata disagrees with the selected package')
    recipe_hash = single(build, 'pkgbuild_sha256sum')
    if not re.fullmatch(r'[0-9a-f]{64}', recipe_hash):
        raise ValueError('Invalid recorded build-recipe checksum')
    if set(pkg.get('license', [])) != set(item['declared_licenses']):
        raise ValueError('Archive license declarations disagree with the installed receipt')
    # Check actual member bytes, rather than assuming a signed archive's .MTREE is accurate.
    matches = []
    for relative in item['runtime_files'] + item['notices']:
        target = runtime.package.safe(capsule, relative)
        if relative.startswith('runtime/'):
            member = 'ucrt64/' + relative[len('runtime/'):]
        elif '/notices/' in relative:
            member = relative.split('/notices/', 1)[1]
        else:
            raise ValueError('Unexpected notice record path')
        payload = read_member(archive, member, tar, runner)
        actual = {'bytes': len(payload), 'sha256': sha(payload)}
        if actual != runtime.package.row(target):
            raise ValueError(f'Staged bytes differ from the signed package: {relative}')
        matches.append({'file': relative, 'archive_member': member, **actual})
    if before != runtime.package.row(archive) or before_sig != runtime.package.row(sig):
        raise ValueError('Cached evidence changed during verification')
    destination = runtime.package.safe(out, name + '-' + version)
    destination.mkdir(parents=True, exist_ok=False)
    for file, data in (('PKGINFO', pkginfo), ('BUILDINFO', buildinfo), ('signature-status.txt', verified.stdout), ('signature-log.txt', verified.stderr)):
        (destination / file).write_bytes(data)
    shutil.copy2(archive, destination / archive.name)
    shutil.copy2(sig, destination / sig.name)
    if runtime.package.row(destination / archive.name) != before or runtime.package.row(destination / sig.name) != before_sig:
        raise ValueError('Copied package evidence changed')
    return {'name': name, 'version': version, 'architecture': architecture, 'state': 'verified',
            'archive': archive.name, 'archive_sha256': before['sha256'], 'signature_sha256': before_sig['sha256'],
            'signing_fingerprint': fingerprint, 'pkgbuild_sha256': recipe_hash,
            'pkgbase': pkg.get('pkgbase', []), 'upstream_urls': pkg.get('url', []),
            'declared_licenses': pkg.get('license', []), 'files': matches}


def audit(capsule, cache, out, tar, gpgv, keyring, runner=run):
    capsule, cache, out, tar, gpgv, keyring = [Path(p).resolve() for p in (capsule, cache, out, tar, gpgv, keyring)]
    if out.exists():
        raise ValueError('Output exists; previous evidence must not be overwritten')
    issues = runtime.verify(capsule)
    if issues:
        raise ValueError('Runtime inventory failed: ' + '; '.join(issues))
    key_hash = runtime.package.row(keyring)
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(keyring, out / 'selected-public-keyring.gpg')
    items = runtime.package.load(capsule / 'metadata/receipts.json')['packages']
    rows = []
    for item in items:
        try:
            rows.append(audit_package(item, capsule, cache, out, tar, gpgv, keyring, runner))
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            rows.append({'name': item.get('name'), 'version': item.get('version'), 'state': 'unverified', 'error': str(error)})
        print(f'{len(rows)}/{len(items)}: {item["name"][0]}: {rows[-1]["state"]}', flush=True)
    if runtime.package.row(keyring) != key_hash or runtime.package.row(out / 'selected-public-keyring.gpg') != key_hash:
        raise ValueError('Selected keyring changed during verification')
    result = {'schema_version': 1, 'recorded_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'Signatures against the selected local public keyring and exact archived members. No online revocation or trust-chain refresh. Not a license clearance or corresponding-source archive.',
              'keyring': key_hash, 'tools': {str(p): runtime.package.row(p) for p in (tar, gpgv)},
              'package_count': len(rows), 'verified_count': sum(r['state'] == 'verified' for r in rows), 'packages': rows}
    (out / 'package-provenance.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    inventory = runtime.package.inventory(out, 'SHA256SUMS.json')
    (out / 'SHA256SUMS.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ('capsule', 'cache', 'out', 'tar', 'gpgv', 'keyring'):
        parser.add_argument('--' + field, type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit(args.capsule, args.cache, args.out, args.tar, args.gpgv, args.keyring)
        return 0 if report['verified_count'] == report['package_count'] else 1
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print('Refused: ' + str(error))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
