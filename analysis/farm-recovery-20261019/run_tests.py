"""Offline product regressions; fixture kernels and disposable loopback servers."""
import contextlib
import json
from pathlib import Path
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'tools'))
full = '--full' in sys.argv
label = 'full-tests' if full else 'focused-tests'
started = time.monotonic()
with (HERE/(label+'.txt')).open('w', encoding='utf-8', newline='\n') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
    suite = (unittest.defaultTestLoader.discover(str(ROOT/'tools'), pattern='test_farm*.py') if full else
             unittest.defaultTestLoader.loadTestsFromNames(['test_farm_recovery', 'test_farm_recovery_http', 'test_farm_creation',
                 'test_farm_draft_runs', 'test_farm_draft_runs_http', 'test_farm_jobs']))
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
summary = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
    passed=result.wasSuccessful() and not result.skipped, seconds=round(time.monotonic()-started, 3),
    phoneInput=False, desktopControl=False,
    problems=[dict(test=str(t), trace=trace) for t, trace in result.failures+result.errors])
(HERE/(label+'.json')).write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in summary.items() if k != 'problems'}))
sys.exit(0 if summary['passed'] else 1)
