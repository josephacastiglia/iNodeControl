"""Run three new acceptance cases against the preserved pre-change engine in memory."""
from pathlib import Path
import subprocess
import sys
import types
import unittest

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'tools'))
source = subprocess.check_output(['git', '-c', f'safe.directory={root.as_posix()}', 'show',
                                  'f770b34:tools/imouse_social_automation.py'], cwd=root)
old = types.ModuleType('imouse_social_automation')
old.__file__ = str(root / 'tools/imouse_social_automation.py')
sys.modules[old.__name__] = old
exec(compile(source.decode('utf-8-sig'), old.__file__, 'exec'), old.__dict__)
import farm_test_network  # Blocks live sockets; fixtures use temporary data only.
from test_farm_readiness import FarmReadinessTests
names = ['test_counts_alone_cannot_pause_or_invent_24_hour_views',
         'test_scheduler_uses_requested_utc_day_for_upload_budget',
         'test_phase_one_plans_warmup_instead_of_holding_forever']
result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(FarmReadinessTests(name) for name in names))
print(f'Negative control: {len(result.failures)} assertion failures, {len(result.errors)} errors, {result.testsRun} tests against f770b34; working files were not changed.')
raise SystemExit(0 if len(result.failures) == 3 and not result.errors else 1)
