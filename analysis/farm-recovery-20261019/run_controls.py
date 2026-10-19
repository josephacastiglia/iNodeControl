"""Negative controls: old behavior must fail the new offline regressions."""
import ast
import contextlib
import json
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import farm_jobs
from farm_draft_creation import CreationWorkflow
from farm_draft_workflow import Workflow
import test_farm_recovery
import test_retained_recovery

old = subprocess.run(['git', '-c', 'safe.directory='+str(ROOT), 'show', '61356f7:tools/farm_jobs.py'],
    cwd=ROOT, capture_output=True, text=True, check=True).stdout
tree = ast.parse(old)
class_node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'FarmJobs')
method = next(n for n in class_node.body if isinstance(n, ast.FunctionDef) and n.name == '_stored')
namespace = dict(vars(farm_jobs))
exec(compile(textwrap.dedent(ast.get_source_segment(old, method)), '<preserved _stored>', 'exec'), namespace)
controls = []
with (HERE/'negative-controls.txt').open('w', encoding='utf-8', newline='\n') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
    cases = [
        (patch.object(farm_jobs.FarmJobs, '_stored', namespace['_stored']),
         test_farm_recovery.RecoveryTests('test_hard_process_exit_is_latched_even_while_a_different_job_runs'), 'old_interruption_status'),
        (patch.object(CreationWorkflow, 'save_history_ready', Workflow.save_history_ready),
         test_retained_recovery.RetainedRecoveryTests('test_creation_save_local_expiry_uses_new_exact_prompt_and_sends_save_only_once'), 'old_creation_prompt_history'),
    ]
    for changed, test, label in cases:
        with changed:
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.TestSuite([test]))
        controls.append(dict(name=label, regressionDetected=not result.wasSuccessful(),
            tests=result.testsRun, failures=len(result.failures), errors=len(result.errors)))
summary = dict(controls=controls, passed=all(c['regressionDetected'] for c in controls),
    phoneInput=False, desktopControl=False, sourceFilesModified=False)
(HERE/'negative-controls.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary))
raise SystemExit(0 if summary['passed'] else 1)
