"""Offline guard/analysis tests; no native processes, sockets or UI."""
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from run import environment, summarize
from provenance import normalized_pe


class AnalysisTests(unittest.TestCase):
    def rows(self):
        return [{"seconds": i, "private_bytes": 1048576 + i*1024,
                 "frames": i*30, "received": i*30} for i in range(61)]

    def test_known_growth(self):
        result = summarize(self.rows(), 30)
        self.assertAlmostEqual(result["private_mib_per_hour"], 3600/1024)
        self.assertFalse(result["acceptance"])

    def test_warmup_and_teardown_excluded(self):
        rows = self.rows()
        for row in rows[:30] + rows[-1:]: row["private_bytes"] = 10**12
        self.assertAlmostEqual(summarize(rows, 30)["private_mib_per_hour"], 3600/1024)

    def test_short_run_is_inconclusive(self):
        self.assertEqual(summarize(self.rows()[:4], 0)["status"], "insufficient_samples")

    def test_flat_is_not_acceptance(self):
        rows = self.rows()
        for row in rows: row["private_bytes"] = 1000
        result = summarize(rows, 30)
        self.assertEqual(result["private_mib_per_hour"], 0)
        self.assertFalse(result["acceptance"])

    def test_child_environment_overrides_receiver_state(self):
        with patch.dict(os.environ, {"IMOUSE2_FRAME_PIPE": "real-pipe", "GST_TRACERS": "leaks",
                                     "GST_PLUGIN_PATH": "wrong", "GST_REGISTRY_1_0": "shared"}):
            env = environment(Path("scratch"))
            self.assertNotIn("IMOUSE2_FRAME_PIPE", env)
            self.assertNotIn("GST_TRACERS", env)
            self.assertNotIn("GST_PLUGIN_PATH", env)
            self.assertEqual(env["GST_REGISTRY_1_0"], str(Path("scratch/registry.bin")))
            self.assertEqual(os.environ["IMOUSE2_FRAME_PIPE"], "real-pipe")


class NormalizationTests(unittest.TestCase):
    def image(self):
        b = bytearray(1024)
        struct.pack_into("<I", b, 60, 128)
        b[128:132] = b"PE\0\0"
        struct.pack_into("<H", b, 134, 1)
        struct.pack_into("<H", b, 148, 240)
        struct.pack_into("<H", b, 152, 0x20b)
        struct.pack_into("<I", b, 264, 4096)
        b[392:400] = b".edata\0\0"
        struct.pack_into("<IIII", b, 400, 128, 4096, 128, 512)
        return b

    def compare(self, a, b):
        with tempfile.TemporaryDirectory() as directory:
            x, y = Path(directory)/"a.exe", Path(directory)/"b.exe"
            x.write_bytes(a); y.write_bytes(b)
            return normalized_pe(x)["sha256"] == normalized_pe(y)["sha256"]

    def test_only_metadata_ignored(self):
        a = self.image(); b = a.copy()
        for offset in (136, 216, 516): struct.pack_into("<I", b, offset, 123456)
        self.assertTrue(self.compare(a, b))

    def test_code_changes_remain_visible(self):
        a = self.image(); b = a.copy(); b[800] = 1
        self.assertFalse(self.compare(a, b))

    def test_export_content_changes_remain_visible(self):
        a = self.image(); b = a.copy(); b[530] = 1
        self.assertFalse(self.compare(a, b))


if __name__ == "__main__":
    unittest.main()
