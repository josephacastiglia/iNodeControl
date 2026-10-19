"""Final offline farm regressions. Uses fixture kernels and disposable HTTP services."""
import contextlib
import json
from pathlib import Path
import sys
import time
import unittest

record=Path(__file__).resolve().parent;root=record.parents[1]
sys.path.insert(0,str(root/'tools'))
started=time.monotonic()
with (record/'python-tests-final.txt').open('w',encoding='utf-8',newline='\n') as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
    suite=unittest.defaultTestLoader.discover(str(root/'tools'),pattern='test_farm*.py')
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
summary=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
    passed=result.wasSuccessful() and not result.skipped,seconds=round(time.monotonic()-started,3),phoneInput=False,
    failuresAndErrors=[dict(test=str(test),trace=trace) for test,trace in result.failures+result.errors])
(record/'python-tests-final.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k!='failuresAndErrors'}))
sys.exit(0 if summary['passed'] else 1)
