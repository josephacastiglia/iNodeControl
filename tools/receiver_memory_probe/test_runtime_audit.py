import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import runtime_audit as r


class RuntimeAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "runtime"
        self.system = self.root / "system"
        self.system.mkdir()
        (self.runtime / "bin").mkdir(parents=True)
        self.receiver = self.root / "receiver.exe"
        for path in [self.receiver, self.runtime / "libexec/gstreamer-1.0/gst-plugin-scanner.exe",
                     *[self.runtime / "lib/gstreamer-1.0" / name for name in r.PLUGIN_FILES]]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
        self.graph = {}
        self.seen = []

    def inspect(self, path):
        self.seen.append(path.name)
        return self.graph.get(path.name, [])

    def audit(self):
        with patch("subprocess.Popen", side_effect=AssertionError("No binary should be executed by graph traversal")):
            return r.audit(self.receiver, self.runtime, self.system, self.inspect)

    def test_consistency_never_claims_launch_readiness(self):
        result = self.audit()
        self.assertTrue(result["files_consistent"])
        self.assertEqual(len(result["files"]), 2 + len(r.PLUGIN_FILES))
        self.assertFalse(result["launch_ready"])
        self.assertFalse(result["receiver_started"])
        self.assertFalse(result["dlls_loaded"])

    def test_missing_plugin_fails(self):
        (self.runtime / "lib/gstreamer-1.0" / r.PLUGIN_FILES[0]).unlink()
        self.assertFalse(self.audit()["files_consistent"])

    def test_receiver_startup_requirements_are_not_just_video_decoding(self):
        # UxPlay checks playback/autodetect even with appsink/fakesink, then
        # initializes its audio pipelines. These are not ordinary PE imports.
        required = ("libgstplayback.dll", "libgstautodetect.dll",
                    "libgstaudioconvert.dll", "libgstaudioresample.dll",
                    "libgstvolume.dll", "libgstlevel.dll")
        for name in required:
            with self.subTest(plugin=name):
                path = self.runtime / "lib/gstreamer-1.0" / name
                path.unlink(missing_ok=True)
                result = self.audit()
                self.assertFalse(result["files_consistent"])
                self.assertIn(f"Missing file: {path}", result["errors"])
                path.write_bytes(b"fixture")

    def test_transitive_missing_import_fails(self):
        (self.runtime / "bin/a.dll").write_bytes(b"fixture")
        self.graph = {"receiver.exe": ["a.dll"], "a.dll": ["missing.dll"]}
        self.assertIn("Unresolved import: a.dll -> missing.dll", self.audit()["errors"])

    def test_cycles_are_inspected_once(self):
        for name in ("a.dll", "b.dll"):
            (self.runtime / "bin" / name).write_bytes(b"fixture")
        self.graph = {"receiver.exe": ["a.dll"], "a.dll": ["b.dll"], "b.dll": ["a.dll"]}
        self.assertTrue(self.audit()["files_consistent"])
        self.assertEqual(self.seen.count("a.dll"), 1)

    def test_system_presence_and_contracts_are_explicit(self):
        (self.system / "KERNEL32.dll").write_bytes(b"fixture")
        self.graph = {"receiver.exe": ["kernel32.dll", "api-ms-win-crt-runtime-l1-1-0.dll"]}
        result = self.audit()
        self.assertTrue(result["files_consistent"])
        self.assertEqual(result["dependencies"][0]["kind"], "system_file_present")
        self.assertEqual(len(result["windows_api_contracts"]), 1)
        self.assertNotIn("KERNEL32.dll", self.seen)

    def test_bad_import_name_cannot_escape_search_roots(self):
        self.graph = {"receiver.exe": ["../../outside.dll"]}
        self.assertFalse(self.audit()["files_consistent"])

    def test_inspector_failure_is_not_a_pass(self):
        def broken(path):
            raise ValueError("unreadable PE")
        result = r.audit(self.receiver, self.runtime, self.system, broken)
        self.assertFalse(result["files_consistent"])
        self.assertEqual(len(result["errors"]), 2 + len(r.PLUGIN_FILES))

    def test_wrong_architecture_is_refused(self):
        class Result:
            returncode = 0
            stdout = "file format pei-i386\nDLL Name: KERNEL32.dll"
        with patch("subprocess.run", return_value=Result()):
            with self.assertRaisesRegex(ValueError, "x64 PE"):
                r.imports(Path("objdump"), self.receiver)

    def test_cpp_runtime_name_is_valid(self):
        class Result:
            returncode = 0
            stdout = "file format pei-x86-64\n\tDLL Name: libstdc++-6.dll\n\tDLL Name: KERNEL32.dll\n"
        with patch("subprocess.run", return_value=Result()):
            self.assertEqual(r.imports(Path("objdump"), self.receiver), ["libstdc++-6.dll", "KERNEL32.dll"])
        (self.runtime / "bin/libstdc++-6.dll").write_bytes(b"fixture")
        self.graph = {"receiver.exe": ["libstdc++-6.dll"]}
        self.assertTrue(self.audit()["files_consistent"])


if __name__ == "__main__":
    unittest.main()
