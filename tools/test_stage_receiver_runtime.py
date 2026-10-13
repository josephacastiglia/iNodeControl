"""Synthetic package files only; never launch or inspect a native binary."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import stage_receiver_runtime as r


class RuntimeStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.msys = self.repo / "msys"
        self.library = self.msys / "ucrt64/bin/fixture.dll"
        self.library.parent.mkdir(parents=True)
        self.library.write_bytes(b"library")
        self.receiver = self.repo / "uxplay.exe"
        self.receiver.write_bytes(b"receiver")
        self.db = self.msys / "var/lib/pacman/local/fixture-1.2-1"
        self.db.mkdir(parents=True)
        (self.db / "desc").write_text("%NAME%\nfixture\n\n%VERSION%\n1.2-1\n\n%LICENSE%\nMIT\n")
        self.notice = self.msys / "ucrt64/share/licenses/fixture/LICENSE"
        self.notice.parent.mkdir(parents=True)
        self.notice.write_text("fixture notice")
        (self.db / "files").write_text("%FILES%\nucrt64/bin/fixture.dll\nucrt64/share/licenses/fixture/LICENSE\n")
        self.audit = self.repo / "audit.json"
        self.record = {"schema_version": 1, "files_consistent": True, "errors": [], "files": {
            str(self.library): r.package.row(self.library), str(self.receiver): r.package.row(self.receiver)}}
        self.save_audit()
        self.out = self.repo / "output/staging/runtime"

    def save_audit(self):
        self.audit.write_text(json.dumps(self.record))

    def stage(self):
        with patch("subprocess.Popen", side_effect=AssertionError("must not launch processes")):
            return r.stage(self.repo, self.out, self.msys, self.audit, self.receiver)

    def test_copy_notice_receipt_and_verify(self):
        manifest = self.stage()
        self.assertEqual(r.verify(self.out), [])
        self.assertEqual(manifest["runtime_file_count"], 1)
        self.assertEqual(manifest["notice_gaps"], [])
        self.assertFalse(manifest["installation_allowed"])
        self.assertFalse(manifest["redistribution_cleared"])
        self.assertEqual((self.out / "runtime/bin/fixture.dll").read_bytes(), b"library")

    def test_missing_notices_are_reported_not_invented(self):
        self.notice.unlink()
        result = self.stage()
        self.assertEqual(result["notice_gaps"], ["fixture"])

    def test_package_listed_doc_notice_is_preserved(self):
        notice = self.msys / "ucrt64/share/doc/fixture/COPYING"
        notice.parent.mkdir(parents=True)
        notice.write_text("the package's actual notice")
        (self.db / "files").write_text("%FILES%\nucrt64/bin/fixture.dll\nucrt64/share/doc/fixture/COPYING\n")
        result = self.stage()
        self.assertEqual(result["notice_gaps"], [])
        self.assertEqual(r.verify(self.out), [])
        saved = next((self.out / "metadata/packages").rglob("COPYING"))
        self.assertEqual(saved.read_bytes(), notice.read_bytes())

    def test_missing_doc_notice_remains_a_gap(self):
        (self.db / "files").write_text("%FILES%\nucrt64/bin/fixture.dll\nucrt64/share/doc/fixture/COPYING\n")
        result = self.stage()
        self.assertEqual(result["notice_gaps"], ["fixture"])
        receipt = r.package.load(self.out / "metadata/receipts.json")["packages"][0]
        self.assertEqual(receipt["missing_listed_notices"], ["ucrt64/share/doc/fixture/COPYING"])

    def test_translations_and_unlisted_documents_do_not_fill_notice_gap(self):
        self.notice.write_text("unlisted notice")
        translation = self.msys / "ucrt64/share/doc/fixture/license-translations.dict"
        translation.parent.mkdir(parents=True)
        translation.write_text("not a license text")
        (self.db / "files").write_text("%FILES%\nucrt64/bin/fixture.dll\nucrt64/share/doc/fixture/license-translations.dict\n")
        self.assertEqual(self.stage()["notice_gaps"], ["fixture"])

    def test_notice_summary_cannot_hide_a_gap(self):
        self.notice.unlink()
        manifest = self.stage()
        manifest["notice_gaps"] = []
        (self.out / "runtime.json").write_text(json.dumps(manifest))
        self.assertIn("Notice-gap summary disagrees with package receipts", r.verify(self.out))

    def test_runtime_summary_counts_are_checked(self):
        manifest = self.stage()
        manifest["package_count"] = 0
        (self.out / "runtime.json").write_text(json.dumps(manifest))
        self.assertIn("Runtime summary counts disagree with package receipts", r.verify(self.out))

    def test_changed_runtime_refused_before_output_creation(self):
        self.library.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Recorded bytes changed"):
            self.stage()
        self.assertFalse(self.out.exists())

    def test_changed_receiver_refused(self):
        self.receiver.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "receiver has changed"):
            self.stage()

    def test_failed_audit_refused(self):
        self.record["files_consistent"] = False
        self.save_audit()
        with self.assertRaisesRegex(ValueError, "successful"):
            self.stage()

    def test_unowned_file_refused(self):
        (self.db / "files").write_text("%FILES%\n")
        with self.assertRaisesRegex(ValueError, "ownership"):
            self.stage()

    def test_duplicate_ownership_refused(self):
        shutil.copytree(self.db, self.db.with_name("fixture-2.0-1"))
        with self.assertRaisesRegex(ValueError, "Multiple packages"):
            self.stage()

    def test_external_file_refused(self):
        extra = self.repo / "private.txt"
        extra.write_bytes(b"not part of runtime")
        self.record["files"][str(extra)] = r.package.row(extra)
        self.save_audit()
        with self.assertRaisesRegex(ValueError, "outside"):
            self.stage()

    def test_unexpected_runtime_payload_refused(self):
        extra = self.msys / "ucrt64/bin/settings.json"
        extra.write_text("{}")
        self.record["files"][str(extra)] = r.package.row(extra)
        self.save_audit()
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            self.stage()

    def test_existing_output_never_overwritten(self):
        self.stage()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.stage()
        self.assertEqual(r.verify(self.out), [])

    def test_output_must_be_in_staging(self):
        self.out = self.repo / "release"
        with self.assertRaisesRegex(ValueError, "staging"):
            self.stage()
        self.assertFalse(self.out.exists())

    def test_tampering_extra_files_and_missing_notices_detected(self):
        self.stage()
        (self.out / "runtime/bin/fixture.dll").write_bytes(b"corrupt")
        (self.out / "package.json").write_text("{}")
        next((self.out / "metadata/packages").rglob("LICENSE")).unlink()
        issues = r.verify(self.out)
        self.assertTrue(any("changed" in s for s in issues))
        self.assertTrue(any("unrecorded: package.json" in s for s in issues))
        self.assertTrue(any("missing" in s for s in issues))

    def test_relocated_verification_needs_no_installed_runtime(self):
        self.stage()
        relocated = Path(self.tmp.name) / "relocated"
        shutil.copytree(self.out, relocated)
        self.library.unlink()
        self.assertEqual(r.verify(relocated), [])

    def test_standalone_verifier_never_changes_the_package_it_verifies(self):
        self.stage()
        relocated = Path(self.tmp.name) / "standalone"
        shutil.copytree(self.out, relocated)
        before = r.package.inventory(relocated, "not-an-existing-manifest")
        for _ in range(2):
            # Ignore inherited Python environment, particularly bytecode settings.
            result = subprocess.run([sys.executable, "-E", "-s", str(relocated / "verify_runtime.py"),
                                     "verify", "--bundle", str(relocated)], cwd=self.tmp.name,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(r.package.inventory(relocated, "not-an-existing-manifest"), before)

    def test_malicious_notice_path_refused(self):
        (self.db / "files").write_text("%FILES%\nucrt64/bin/fixture.dll\nucrt64/share/licenses/../../../../outside\n")
        with self.assertRaisesRegex(ValueError, "unsafe"):
            self.stage()
        self.assertFalse(self.out.exists())

    def test_combined_package_embeds_runtime_without_operator_configuration(self):
        # Reuse the existing package fixtures so this exercises both real stagers.
        from test_stage_release import StageTests
        other = StageTests()
        other.setUp()
        try:
            self.record["files"].pop(str(self.receiver))
            self.receiver = other.exe
            self.record["files"][str(self.receiver)] = r.package.row(self.receiver)
            self.save_audit()
            self.stage()
            combined = r.package.stage(other.repo, other.output, other.managed, other.exe,
                other.native_record, other.native, other.guide, self.out)
            self.assertEqual(combined["native_runtime"], "dependencies/receiver-runtime")
            self.assertEqual(r.package.verify(other.output), [])
            self.assertFalse(combined["launch_allowed"])
            capsule = other.output / combined["native_runtime"]
            self.assertEqual(r.verify(capsule), [])
            self.assertFalse((other.output / "payload/console/data").exists())
            manifest = other.output / "package.json"
            combined.pop("native_runtime")
            manifest.write_text(json.dumps(combined))
            self.assertIn("Undeclared dependency payload", r.package.verify(other.output))
        finally:
            other.doCleanups()

    def test_combined_package_rejects_unrelated_runtime_audit(self):
        from test_stage_release import StageTests
        other = StageTests()
        other.setUp()
        try:
            self.stage()
            with self.assertRaisesRegex(ValueError, "different receiver"):
                r.package.stage(other.repo, other.output, other.managed, other.exe,
                    other.native_record, other.native, other.guide, self.out)
            self.assertFalse(other.output.exists())
        finally:
            other.doCleanups()


if __name__ == "__main__":
    unittest.main()
