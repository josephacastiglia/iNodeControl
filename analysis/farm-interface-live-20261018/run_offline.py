"""Preparation checks with socket access limited to owned fake HTTP servers."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

RECORD = Path(__file__).resolve().parent
ROOT = RECORD.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import farm_test_network
import test_farm_draft_journal as journal


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, file)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def old_atomic(path, value):
    import os
    temporary = path.with_suffix('.writing')
    with temporary.open('w', encoding='utf-8') as output:
        json.dump(value, output); output.flush(); os.fsync(output.fileno())
    temporary.replace(path)


stream = io.StringIO()
with patch.object(journal, 'atomic_json', old_atomic):
    control = unittest.TextTestRunner(stream=stream).run(unittest.TestSuite([
        journal.DraftJournalTests('test_reader_holding_old_record_does_not_fail_writer_or_expose_partial_json')]))
assert len(control.failures) == 1 and not control.errors, stream.getvalue()
(RECORD/'journal-control.txt').write_text(stream.getvalue(), encoding='utf-8')

suite = unittest.TestSuite()
for name in ('test_farm_draft_journal', 'test_farm_draft_runs', 'test_farm_draft_runs_http', 'test_farm_draft_transport'):
    suite.addTests(unittest.defaultTestLoader.loadTestsFromName(name))
extraction = module('extracted_acceptance', ROOT/'analysis/farm-interface-integration-20261018/test_extracted_workflow.py')
suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(extraction))
native = module('native_acceptance', RECORD/'test_native_probe.py')
suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(native))
log = io.StringIO()
with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
(RECORD/'offline-tests.txt').write_text(log.getvalue(), encoding='utf-8')
summary = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
    skipped=len(result.skipped), passed=result.wasSuccessful(), journalControlFailedAsExpected=True,
    network='owned ephemeral loopback fixtures only', phoneInput=False, desktopControl=False)
(RECORD/'offline-tests.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary))
raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
