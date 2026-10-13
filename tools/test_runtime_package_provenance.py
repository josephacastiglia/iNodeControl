"""Synthetic archives and verifier results; no package, tool or service is executed."""
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

import runtime_package_provenance as p


class PackageProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.capsule, self.cache, self.out = (self.root / name for name in ('capsule', 'cache', 'out'))
        for folder in (self.capsule, self.cache, self.out): folder.mkdir()
        self.name, self.version = 'mingw-w64-ucrt-x86_64-fixture', '1.2-3'
        self.archive = self.cache / (self.name + '-' + self.version + '-any.pkg.tar.zst')
        self.archive.write_bytes(b'archived bytes')
        self.archive.with_name(self.archive.name + '.sig').write_bytes(b'signature')
        self.item = {'name': [self.name], 'version': [self.version], 'metadata_files': ['desc'],
                     'runtime_files': ['runtime/bin/fixture.dll'], 'notices': ['metadata/fixture/notices/ucrt64/share/doc/fixture/COPYING'],
                     'declared_licenses': ['spdx:MIT']}
        (self.capsule / 'desc').write_text('%ARCH%\nany\n')
        self.members = {
            '.PKGINFO': f'pkgname = {self.name}\npkgver = {self.version}\narch = any\nlicense = spdx:MIT\n'.encode(),
            '.BUILDINFO': f'pkgname = {self.name}\npkgver = {self.version}\npkgbuild_sha256sum = {"a" * 64}\n'.encode(),
            'ucrt64/bin/fixture.dll': b'payload', 'ucrt64/share/doc/fixture/COPYING': b'notice'}
        for name, data in ((self.item['runtime_files'][0], b'payload'), (self.item['notices'][0], b'notice')):
            path = self.capsule / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        self.status = ('[GNUPG:] VALIDSIG ' + 'A' * 40 + ' 2026-10-12\n').encode()
        self.code = 0
        self.calls = []

    def runner(self, args):
        self.calls.append(args)
        if args[0] == 'gpgv':
            return SimpleNamespace(returncode=self.code, stdout=self.status, stderr=b'public signing identity')
        self.assertEqual(args[0], 'tar')
        self.assertEqual(args[1], '-xOf')
        return SimpleNamespace(returncode=0, stdout=self.members[args[-1]], stderr=b'')

    def audit(self):
        return p.audit_package(self.item, self.capsule, self.cache, self.out, 'tar', 'gpgv', self.root / 'keyring', self.runner)

    def test_records_identity_recipe_exact_payload_and_notice(self):
        result = self.audit()
        self.assertEqual(result['state'], 'verified')
        self.assertEqual(len(result['files']), 2)
        self.assertEqual(result['pkgbuild_sha256'], 'a' * 64)
        self.assertEqual(result['signing_fingerprint'], 'A' * 40)
        saved = self.out / (self.name + '-' + self.version)
        self.assertEqual((saved / self.archive.name).read_bytes(), self.archive.read_bytes())
        self.assertEqual((saved / 'BUILDINFO').read_bytes(), self.members['.BUILDINFO'])

    def test_unsigned_or_bad_signature_stops_before_reading_payload(self):
        self.code = 1
        with self.assertRaisesRegex(ValueError, 'signature was not verified'): self.audit()
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(any(self.out.iterdir()))

    def test_validsig_alone_cannot_override_expired_or_revoked_status(self):
        for flag in ('EXPKEYSIG', 'REVKEYSIG', 'BADSIG', 'ERRSIG', 'NO_PUBKEY', 'KEYEXPIRED'):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                p.signature(self.status + ('[GNUPG:] ' + flag + ' detail\n').encode(), 0)

    def test_no_or_multiple_signing_identities_refused(self):
        for text in (b'[GNUPG:] GOODSIG name\n', self.status * 2):
            with self.assertRaisesRegex(ValueError, 'single valid'): p.signature(text, 0)

    def test_archive_version_must_match_receipt(self):
        self.members['.PKGINFO'] = self.members['.PKGINFO'].replace(b'1.2-3', b'1.3-1')
        with self.assertRaisesRegex(ValueError, 'identity disagrees'): self.audit()

    def test_signed_payload_must_match_staged_bytes(self):
        self.members['ucrt64/bin/fixture.dll'] = b'another build'
        with self.assertRaisesRegex(ValueError, 'Staged bytes differ'): self.audit()

    def test_notice_bytes_are_verified_too(self):
        self.members['ucrt64/share/doc/fixture/COPYING'] = b'different notice'
        with self.assertRaisesRegex(ValueError, 'Staged bytes differ'): self.audit()

    def test_license_declaration_mismatch_is_not_hidden(self):
        self.item['declared_licenses'] = ['spdx:BSD-3-Clause']
        with self.assertRaisesRegex(ValueError, 'license declarations disagree'): self.audit()

    def test_missing_exact_archive_or_signature_never_substitutes_latest(self):
        self.archive.with_name(self.archive.name + '.sig').unlink()
        with self.assertRaisesRegex(ValueError, 'missing'): self.audit()
        self.assertEqual(self.calls, [])

    def test_unsafe_package_and_archive_member_paths_refused(self):
        self.item['name'] = ['../../elsewhere']
        with self.assertRaisesRegex(ValueError, 'Unsafe package'): self.audit()
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            p.read_member(self.archive, '../private', 'tar', self.runner)
        self.assertEqual(self.calls, [])

    def test_duplicate_identity_metadata_refused(self):
        self.members['.PKGINFO'] += b'pkgname = another\n'
        with self.assertRaisesRegex(ValueError, 'Expected one pkgname'): self.audit()

    def test_copy_never_overwrites_prior_evidence(self):
        self.audit()
        with self.assertRaises(FileExistsError): self.audit()

    def test_changed_archive_during_check_is_refused(self):
        def changing(args):
            result = self.runner(args)
            if args[-1] == 'ucrt64/share/doc/fixture/COPYING': self.archive.write_bytes(b'changed')
            return result
        with self.assertRaisesRegex(ValueError, 'changed during'):
            p.audit_package(self.item, self.capsule, self.cache, self.out, 'tar', 'gpgv', self.root / 'keyring', changing)

    def test_member_size_limit(self):
        with self.assertRaisesRegex(ValueError, 'exceeds'):
            p.read_member(self.archive, 'ucrt64/bin/fixture.dll', 'tar', self.runner, limit=2)


if __name__ == '__main__':
    unittest.main()
