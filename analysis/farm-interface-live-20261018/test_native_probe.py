"""Preserved WPF assembly -> real HTTP -> fake worker. No rack or desktop UI."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
import uuid
from unittest.mock import patch

RECORD = Path(__file__).resolve().parent
ROOT = RECORD.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import farm_draft_runs as runs
from test_farm_draft_runs import Drafts, FixtureRuns, CONFIG
from test_farm_http_jobs import FarmHttpJobsTests
from farm_draft_workflow import atomic_json


class NativeProbeTests(FarmHttpJobsTests):
    # Inherit only fixture utilities, not the unrelated HTTP tests.
    def run_probe(self, scenario):
        drafts = Drafts()
        content = runs.source_content(drafts.export('fixture', 3))[2]
        with patch.object(runs, 'CONTENT_SHA256', content):
            service = FixtureRuns(self.root / 'runs', drafts, self.runtime.jobs, CONFIG)
            self.runtime.draft_runs = service
            self.runtime.execution_mode = 'live'
            service.source = 'candidate_phone_workflow'  # synthetic acceptance fixture ONLY
            service.wait = True
            output = RECORD / 'offline' / (scenario + '-' + uuid.uuid4().hex[:8])
            options = dict(phase='offline', scenario=scenario, output=str(output),
                backend=self.base, backendSourceHash=self.runtime.source_hash,
                assembly=str(ROOT/'output/codex-farm-interface-20261018/iMouse2.dll'),
                draftId=str(uuid.uuid4()), revision=3, storeId=service.store_id,
                exerciseOwnedReset=scenario == 'cancel-on-admission')
            self.root.joinpath('options.json').write_text(json.dumps(options), encoding='utf-8')
            # Keep the fake operation active until its admission response has
            # been processed. No real Workflow/transport can be constructed.
            def release():
                if service.entered.wait(15):
                    threading.Event().wait(.8)
                    if scenario == 'response-loss': service.proceed.set()
            helper = threading.Thread(target=release, daemon=True); helper.start()
            def record_fixture(path, value):
                if scenario == 'cancel-on-admission':
                    value['commands'] = [dict(purpose='initial_pointer_reset', state='answered')]
                    value['actions'] = []
                atomic_json(path, value)
            with patch.object(self.runtime, 'get_kernel', side_effect=AssertionError('No rack')), \
                    patch('test_farm_draft_runs.atomic_json', side_effect=record_fixture):
                result = subprocess.run([str(ROOT/'output/farm-interface-live-native-probe-20261018/NativeProbe.exe'), str(self.root/'options.json')],
                    capture_output=True, timeout=35, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            helper.join(1)
            failure = (output/'failure.json').read_text() if (output/'failure.json').exists() else result.stderr.decode(errors='replace')
            self.assertEqual(0, result.returncode, failure)
            record = json.loads((output/'result.json').read_text())
            self.assertTrue(record['passed'])
            self.assertEqual(1, service.executions)
            self.assertEqual(1, record['startRequests'])
            self.assertEqual(0, record['windowHandles'])
            self.assertFalse(record['desktopControl'])
            self.assertEqual('offline', record['phase'])

    def test_native_response_loss_recovers_original_http_request(self):
        self.run_probe('response-loss')

    def test_native_stop_and_reopen_never_resume_cancelled_worker(self):
        self.run_probe('cancel-on-admission')


# Keep only the two explicit tests while sharing the existing HTTP fixture.
for name in list(vars(FarmHttpJobsTests)):
    if name.startswith('test_'):
        setattr(NativeProbeTests, name, None)
del FarmHttpJobsTests
if __name__ == '__main__': unittest.main(verbosity=2)
