"""Offline regression/control run. Only owned fixture HTTP ports are allowed."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tools'))
sys.path.insert(0,str(HERE))
import farm_test_network
import test_prompt_recovery as regression

baseline='759474b'
raw=subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),'show',baseline+':tools/farm_draft_workflow.py'],cwd=ROOT)
before=types.ModuleType('workflow_before'); before.__file__=str(ROOT/'tools/farm_draft_workflow.py')
exec(compile(raw,before.__file__,'exec'),before.__dict__)
log=io.StringIO()
with patch.object(regression.extracted.product,'Workflow',before.Workflow):
    control=unittest.TextTestRunner(stream=log).run(unittest.TestSuite([
        regression.PromptRecoveryTests('test_expired_at_last_commit_recaptures_same_prompt_and_sends_save_once'),
        regression.PromptRecoveryTests('test_unexpected_permission_dialog_is_blocked_even_without_age_failure')]))
(HERE/'regression-control.txt').write_text(log.getvalue(),encoding='utf-8')
assert len(control.failures)==2 and not control.errors, log.getvalue()

suite=unittest.TestSuite()
suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(regression))
suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(regression.extracted.ExtractionTests))
for name in ('test_farm_draft_journal','test_farm_draft_runs','test_farm_draft_runs_http','test_farm_draft_transport',
             'test_farm_transitions','test_farm_frame_evidence','test_farm_observations','test_farm_draft_verification'):
    suite.addTests(unittest.defaultTestLoader.loadTestsFromName(name))

spec=importlib.util.spec_from_file_location('native_probe_regression', ROOT/'analysis/farm-interface-live-20261018/test_native_probe.py')
native=importlib.util.module_from_spec(spec); spec.loader.exec_module(native)
native.RECORD=HERE
suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(native))
log=io.StringIO()
with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
(HERE/'tests.txt').write_text(log.getvalue(),encoding='utf-8')
summary=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
    passed=result.wasSuccessful(),baselineCommit=baseline,expectedControlFailures=2,
    network='owned ephemeral loopback fixtures only; all other sockets denied',
    phoneInput=False,desktopControl=False,liveRecoveryValidated=False)
(HERE/'tests.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary))
if not result.wasSuccessful(): print(log.getvalue()[-18000:])
raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
