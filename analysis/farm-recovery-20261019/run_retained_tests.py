"""Run retained-layout fault scenarios with every network socket refused."""
import contextlib
import json
from pathlib import Path
import time
import unittest
import test_retained_recovery

HERE = Path(__file__).resolve().parent
start = time.monotonic()
with (HERE/'retained-tests.txt').open('w', encoding='utf-8', newline='\n') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_retained_recovery)
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
summary = dict(tests=result.testsRun, passed=result.wasSuccessful(), failures=len(result.failures), errors=len(result.errors),
    seconds=round(time.monotonic()-start, 3), phoneInput=False, networkAccess=False,
    basis='Retained C24C frames/OCR plus a simulated HID kernel; not a fresh-phone or restart pass.',
    problems=[dict(test=str(t), trace=trace) for t, trace in result.failures+result.errors])
(HERE/'retained-tests.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in summary.items() if k != 'problems'}))
raise SystemExit(0 if result.wasSuccessful() else 1)
