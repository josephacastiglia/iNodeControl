"""Local journal replacement under concurrent Windows status reads; no network."""
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from farm_draft_workflow import atomic_json


class DraftJournalTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / 'record.json'
        atomic_json(self.path, {'state': 'before'})

    @unittest.skipUnless(os.name == 'nt', 'Actual Windows sharing semantics')
    def test_reader_holding_old_record_does_not_fail_writer_or_expose_partial_json(self):
        errors = []; done = threading.Event()
        def write():
            try: atomic_json(self.path, {'state': 'after', 'actions': ['answered']})
            except BaseException as error: errors.append(error)
            finally: done.set()
        reader = self.path.open('rb')
        worker = threading.Thread(target=write)
        try:
            worker.start()
            self.assertFalse(done.wait(.08), 'Replacement must wait for the existing reader')
            self.assertEqual({'state': 'before'}, json.load(reader))
        finally:
            reader.close(); worker.join(2)
        self.assertFalse(worker.is_alive()); self.assertEqual([], errors)
        self.assertEqual({'state': 'after', 'actions': ['answered']}, json.loads(self.path.read_bytes()))

    def test_permanent_sharing_denial_is_bounded_and_preserves_previous_record(self):
        error = PermissionError('sharing denied'); error.winerror = 32
        before = self.path.read_bytes(); started = time.monotonic()
        with patch.object(Path, 'replace', side_effect=error) as replace:
            with self.assertRaises(PermissionError): atomic_json(self.path, {'state': 'after'})
        self.assertLess(time.monotonic() - started, 2)
        self.assertLess(replace.call_count, 80); self.assertGreater(replace.call_count, 1)
        self.assertEqual(before, self.path.read_bytes())

    def test_unrelated_file_errors_fail_without_retry(self):
        with patch.object(Path, 'replace', side_effect=OSError('disk failure')) as replace:
            with self.assertRaises(OSError): atomic_json(self.path, {'state': 'after'})
        self.assertEqual(1, replace.call_count)
        self.assertEqual({'state': 'before'}, json.loads(self.path.read_bytes()))

    def test_invalid_value_never_replaces_previous_record(self):
        before = self.path.read_bytes()
        with self.assertRaises(ValueError): atomic_json(self.path, {'invalid': float('nan')})
        self.assertEqual(before, self.path.read_bytes())


if __name__ == '__main__': unittest.main()
