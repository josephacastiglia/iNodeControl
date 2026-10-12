"""Local synthetic build fixtures only; no compiler, application or hardware."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("manifest", Path(__file__).with_name("build_manifest.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo, self.build = self.root / "repo", self.root / "build"
        self.project = "src/Console/Console.csproj"
        (self.repo / "src/Console").mkdir(parents=True)
        self.build.mkdir()
        (self.repo / self.project).write_text("<Project/>", encoding="utf-8")
        (self.repo / "src/Console/Main.cs").write_text("class Main {}", encoding="utf-8")
        (self.build / "iMouse2.dll").write_bytes(b"fixture assembly")
        (self.build / "iMouse2.exe").write_bytes(b"same apphost")
        self.record = m.record(self.repo, self.build, self.project)

    def test_unchanged_fixture_verifies(self):
        self.assertEqual(m.verify(self.record, self.repo, self.build), [])

    def test_changed_dll_is_detected_even_when_launcher_is_unchanged(self):
        (self.build / "iMouse2.dll").write_bytes(b"different assembly")
        self.assertIn("artifact changed: iMouse2.dll", m.verify(self.record, self.repo, self.build))

    def test_uncommitted_source_change_is_detected(self):
        (self.repo / "src/Console/Main.cs").write_text("class Changed {}", encoding="utf-8")
        self.assertIn("source changed: src/Console/Main.cs", m.verify(self.record, self.repo, self.build))

    def test_new_source_cannot_be_omitted_silently(self):
        (self.repo / "src/Console/Extra.cs").write_text("class Extra {}", encoding="utf-8")
        self.assertIn("source unrecorded: src/Console/Extra.cs", m.verify(self.record, self.repo, self.build))

    def test_new_dll_or_missing_artifact_invalidates_snapshot(self):
        (self.build / "Extra.dll").write_bytes(b"extra")
        (self.build / "iMouse2.exe").unlink()
        issues = m.verify(self.record, self.repo, self.build)
        self.assertIn("artifact unrecorded: Extra.dll", issues)
        self.assertIn("artifact missing: iMouse2.exe", issues)

    def test_generated_obj_files_do_not_change_source_identity(self):
        folder = self.repo / "src/Console/obj"
        folder.mkdir()
        (folder / "generated.cs").write_text("generated", encoding="utf-8")
        self.assertEqual(m.verify(self.record, self.repo, self.build), [])

    def test_root_build_properties_are_included(self):
        (self.repo / "Directory.Build.props").write_text("<Project/>", encoding="utf-8")
        self.assertIn("source unrecorded: Directory.Build.props", m.verify(self.record, self.repo, self.build))

    def test_manifest_paths_cannot_escape_roots(self):
        for name in ("../private", "C:/private", "/private", "dir\\private"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                m.verify(dict(self.record, artifacts={name: {"sha256": "0"*64}}), self.repo, self.build)

    def test_empty_manifest_cannot_pass(self):
        with self.assertRaises(ValueError):
            m.verify(dict(self.record, artifacts={}), self.repo, self.build)


if __name__ == "__main__":
    unittest.main()
