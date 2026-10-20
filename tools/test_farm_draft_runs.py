"""Offline admission/restart tests. No real transport or phone is constructed."""
import errno
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
import zipfile
from unittest.mock import patch

import farm_draft_runs as runs
from farm_draft_workflow import atomic_json
from farm_jobs import FarmJobs
from farm_drafts import DraftConflict


class Drafts:
    def __init__(self): self.revision = 3
    def export(self, draft_id, revision):
        if revision != self.revision: raise DraftConflict('Saved revision changed.')
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            archive.writestr('manifest.json', json.dumps(dict(caption='Fixture caption', assets=[dict(file=str(i)) for i in range(3)])))
            for i in range(3): archive.writestr(str(i), b'fixture-image-' + str(i).encode())
        return output.getvalue()
    def get(self, draft_id): return dict(revision=self.revision)


CONFIG = dict(version=1, api=runs.API, kernelSha256='a'*64, expectedUid='fixture-only')


class FixtureRuns(runs.DraftRuns):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.entered = threading.Event(); self.proceed = threading.Event(); self.wait = False
        self.executions = 0; self.unknown = False; self.source = 'offline_protocol_fixture'
    def execute(self, folder, assets, caption, package_hash, cancelled):
        self.executions += 1; self.entered.set()
        record = dict(packageSha256=package_hash, state='running', source=self.source,
            cleanup='unconfirmed', savedDraftVerified=False, observations=[], actions=[dict(label='prepared-save-once',state='outcome_unknown')])
        atomic_json(folder/'record.json', record)
        if self.wait:
            deadline = time.monotonic()+3
            while not self.proceed.wait(.01) and not cancelled.is_set():
                if time.monotonic() > deadline: raise TimeoutError('Fixture was not released')
        if self.unknown or cancelled.is_set():
            record.update(state='review_required', error='Save reply was lost; no replay.', cleanup='confirmed', evidenceExport='confirmed')
        else:
            record['actions'][0]['state'] = 'answered'
            record.update(state='validation_passed',savedDraftVerified=True,cleanup='confirmed',evidenceExport='confirmed')
        atomic_json(folder/'record.json',record)
        return record


class DraftRunTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(prefix='farm-draft-run-'); self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name); self.drafts=Drafts()
        self.content=runs.source_content(self.drafts.export('fixture',3))[2]
        self.patch=patch.object(runs,'CONTENT_SHA256',self.content); self.patch.start(); self.addCleanup(self.patch.stop)
        self.jobs=FarmJobs(journal_path=self.root/'jobs.db')
        self.service=FixtureRuns(self.root/'runs',self.drafts,self.jobs,CONFIG)
        self.spec=dict(id=str(uuid.uuid4()),draft_id=str(uuid.uuid4()),revision=3,store_id=self.service.store_id)
        self.addCleanup(self.finish_workers)

    def finish_workers(self):
        self.jobs.cancel_active(); self.service.proceed.set()
        for job in list(self.jobs._jobs.values()): self.assertTrue(job.done.wait(4))
        with self.jobs._lock: pass

    def finish(self):
        self.assertTrue(self.jobs._jobs[self.spec['id']].done.wait(4))
        return self.service.get(self.spec['id'])

    def test_default_disabled_and_config_cannot_target_release_other_host_or_simulation(self):
        service=runs.DraftRuns(self.root/'disabled',self.drafts,self.jobs)
        self.assertFalse(service.capability()['enabled'])
        with self.assertRaises(runs.KernelSafetyError): service.start({**self.spec,'store_id':service.store_id})
        path=self.root/'config.json'
        for change in ({'api':'http://127.0.0.1:9913/api'}, {'api':'http://remote:9916/api'}, {'version':True}, {'device':'C241'}, {'kernelSha256':'bad'}):
            path.write_text(json.dumps({**CONFIG,**change}))
            with self.assertRaises(ValueError): runs.load_config(path,'live')
        path.write_text(json.dumps(CONFIG)); self.assertEqual(CONFIG,runs.load_config(path,'live'))
        with self.assertRaises(ValueError): runs.load_config(path,'simulate')

    def test_start_returns_while_worker_runs_and_stop_remains_available(self):
        self.service.wait=True
        first=self.service.start(self.spec); self.assertFalse(first['terminal'])
        self.assertTrue(self.service.entered.wait(1))
        self.assertEqual('running',self.service.get(self.spec['id'])['state'])
        self.service.cancel(self.spec['id']); result=self.finish()
        self.assertEqual('cancelled',result['jobStatus']); self.assertEqual('confirmed',result['cleanup'])
        self.assertFalse(result['savedDraftVerified']); self.assertEqual(1,self.service.executions)

    def test_lost_submit_reply_duplicate_and_restart_only_retrieve_original(self):
        self.service.unknown=True; self.service.start(self.spec); original=self.finish()
        self.assertEqual('review_required',original['state'])
        self.assertEqual(original,self.service.start(self.spec)); self.assertEqual(1,self.service.executions)
        other=FixtureRuns(self.root/'runs',self.drafts,FarmJobs(journal_path=self.root/'jobs.db'))
        self.assertEqual(original,other.start(self.spec)); self.assertEqual(0,other.executions)
        with self.assertRaises(DraftConflict): other.start({**self.spec,'revision':4})

    def test_simulated_success_does_not_claim_a_phone_draft(self):
        self.service.start(self.spec); result=self.finish()
        self.assertEqual('succeeded',result['jobStatus']); self.assertFalse(result['savedDraftVerified'])
        self.assertFalse(result['automaticResume']); self.assertFalse(result['integratedLiveValidated'])
        self.assertFalse(result['publishing']); self.assertFalse(result['messaging'])

    def test_confirmed_phone_result_is_bound_to_original_revision_and_content(self):
        self.service.source='candidate_phone_workflow'; self.service.start(self.spec); result=self.finish()
        self.assertTrue(result['savedDraftVerified']); self.assertEqual('verified',result['state'])
        self.drafts.revision=4
        result=self.service.get(self.spec['id']); self.assertTrue(result['draftChangedSinceRun'])
        self.assertEqual(3,result['request']['revision']); self.assertEqual(1,self.service.executions)

    def test_changed_content_store_or_request_fields_never_reach_worker(self):
        with patch.object(runs,'CONTENT_SHA256','f'*64):
            self.assertFalse(self.service.eligibility(self.spec['draft_id'],3)['eligible'])
            with self.assertRaises(ValueError): self.service.start(self.spec)
        for fields in ({'device':'C241'},{'account':'another'},{'api':runs.API},{'actions':[]},{'revision':True}):
            with self.assertRaises(ValueError): self.service.start({**self.spec,**fields})
        with self.assertRaises(DraftConflict): self.service.start({**self.spec,'store_id':str(uuid.uuid4())})
        self.assertEqual(0,self.service.executions)

    def test_stop_before_admission_is_durable_and_never_starts_later(self):
        self.service.cancel(self.spec['id']); result=self.service.start(self.spec)
        self.assertTrue(result['terminal']); self.assertEqual('cancelled',result['jobStatus'])
        self.assertEqual(0,self.service.executions)
        self.assertEqual(result,self.service.start(self.spec))

    def test_orphaned_admission_has_no_automatic_resume(self):
        with patch.object(self.jobs,'submit',side_effect=RuntimeError('Interrupted after admission')):
            with self.assertRaises(RuntimeError): self.service.start(self.spec)
        result=self.service.start(self.spec)
        self.assertEqual('interrupted',result['jobStatus']); self.assertTrue(result['terminal'])
        self.assertEqual(0,self.service.executions)

    def test_completed_record_and_retained_package_corruption_fail_closed(self):
        self.service.start(self.spec); self.finish()
        path=self.root/'runs'/self.spec['id']/'record.json'
        original=path.read_bytes(); record=json.loads(original); record['state']='made_up'; atomic_json(path,record)
        with self.assertRaisesRegex(ValueError,'journal'): self.service.get(self.spec['id'])
        path.write_bytes(original)
        with self.service.connect() as db: db.execute('UPDATE runs SET package=?',(b'corrupt',))
        with self.assertRaisesRegex(ValueError,'package'): self.service.get(self.spec['id'])

    def refuse_journal_reads(self, error, failures):
        """Patch Path.read_bytes so this run's journal read raises `error` `failures` times first."""
        path=self.root/'runs'/self.spec['id']/'record.json'; read=Path.read_bytes; attempts=[]
        def refused(target):
            if target==path:
                attempts.append(target)
                if len(attempts)<=failures: raise error
            return read(target)
        return patch.object(Path,'read_bytes',refused), attempts

    def test_transient_windows_read_refusal_still_returns_the_complete_record(self):
        # 19 Oct suite failure: opening the journal during its atomic replacement
        # raised errno 13 with no winerror. The writer-side shape is retried too.
        self.service.source='candidate_phone_workflow'; self.service.start(self.spec); expected=self.finish()
        record=json.loads((self.root/'runs'/self.spec['id']/'record.json').read_bytes())
        sharing=PermissionError('sharing denied'); sharing.winerror=32
        for error in (PermissionError(errno.EACCES,'Permission denied'), sharing):
            refused,attempts=self.refuse_journal_reads(error,3)
            with self.subTest(error=error):
                with refused: result=self.service.get(self.spec['id'])
                self.assertEqual(4,len(attempts)); self.assertEqual(expected,result)
                self.assertEqual(record,result['workflow']); self.assertEqual('verified',result['state'])

    def test_lasting_or_unrelated_read_errors_still_raise(self):
        self.service.start(self.spec); self.finish()
        refused,attempts=self.refuse_journal_reads(PermissionError(errno.EACCES,'Permission denied'),10**6)
        started=time.monotonic()
        with refused, self.assertRaises(PermissionError): self.service.get(self.spec['id'])
        self.assertLess(time.monotonic()-started,2); self.assertGreater(len(attempts),1); self.assertLess(len(attempts),80)
        failed,attempts=self.refuse_journal_reads(OSError(errno.EIO,'disk failure'),10**6)
        with failed, self.assertRaises(OSError): self.service.get(self.spec['id'])
        self.assertEqual(1,len(attempts))

    @unittest.skipUnless(os.name=='nt','Actual Windows sharing semantics')
    def test_status_polls_during_real_journal_replacement_never_fail(self):
        # The same race without mocks: keep replacing a running journal while polling it.
        self.service.wait=True; self.service.start(self.spec); self.assertTrue(self.service.entered.wait(1))
        path=self.root/'runs'/self.spec['id']/'record.json'; deadline=time.monotonic()+2
        while not path.exists() and time.monotonic()<deadline: time.sleep(.005)  # Fixture's first write.
        record=json.loads(path.read_bytes()); stop=time.monotonic()+.5; errors=[]; states=[]
        def rewrite():
            try:
                while time.monotonic()<stop: atomic_json(path,record)
            except BaseException as error: errors.append(error)
        writer=threading.Thread(target=rewrite); writer.start()
        try:
            while time.monotonic()<stop: states.append(self.service.get(self.spec['id'])['state'])
        finally: writer.join(5)
        self.assertEqual([],errors); self.assertGreater(len(states),20); self.assertEqual({'running'},set(states))

    def test_heartbeat_loss_stops_worker_without_an_extra_save(self):
        self.jobs.heartbeat_seconds=.05; self.service.wait=True
        self.service.start(self.spec); result=self.finish()
        self.assertEqual('cancelled',result['jobStatus']); self.assertEqual(1,self.service.executions)
        self.assertEqual(1,len(result['workflow']['actions'])); self.assertFalse(result['savedDraftVerified'])

    def test_graceful_shutdown_waits_for_scoped_cleanup_and_keeps_unknown_save(self):
        self.service.wait=True; self.service.start(self.spec)
        self.assertTrue(self.service.entered.wait(1)); self.assertTrue(self.jobs.close(timeout=3))
        result=self.service.get(self.spec['id'])
        self.assertEqual('cancelled',result['jobStatus']); self.assertEqual('confirmed',result['cleanup'])
        self.assertEqual('outcome_unknown',result['workflow']['actions'][0]['state'])
        self.assertFalse(result['savedDraftVerified'])

    def test_real_child_process_death_after_unknown_save_never_replays(self):
        code = '''
import json,os,sys,threading
from pathlib import Path
import farm_draft_runs as runs
from farm_jobs import FarmJobs
from farm_draft_workflow import atomic_json
from test_farm_draft_runs import Drafts,CONFIG
root=Path(sys.argv[1]); drafts=Drafts()
runs.CONTENT_SHA256=runs.source_content(drafts.export('fixture',3))[2]
class Crashing(runs.DraftRuns):
    def execute(self,folder,assets,caption,package_hash,cancelled):
        atomic_json(folder/'record.json',dict(packageSha256=package_hash,state='running',source='offline_protocol_fixture',cleanup='unconfirmed',savedDraftVerified=False,observations=[],actions=[dict(label='prepared-save-once',state='outcome_unknown')]))
        with (root/'sends.txt').open('a') as f: f.write('Save\\n'); f.flush(); os.fsync(f.fileno())
        os._exit(71)
service=Crashing(root/'runs',drafts,FarmJobs(journal_path=root/'jobs.db'),CONFIG)
spec=json.loads((root/'spec.json').read_text()); spec['store_id']=service.store_id
service.start(spec); threading.Event().wait(5)
'''
        child=self.root/'child'; child.mkdir(); (child/'spec.json').write_text(json.dumps(self.spec))
        env={**os.environ,'PYTHONPATH':str(Path(__file__).parent)}
        proc=subprocess.run([sys.executable,'-c',code,str(child)],env=env,capture_output=True,timeout=10)
        self.assertEqual(71,proc.returncode,proc.stderr.decode())
        recovered=FixtureRuns(child/'runs',Drafts(),FarmJobs(journal_path=child/'jobs.db'),CONFIG)
        spec={**self.spec,'store_id':recovered.store_id}; result=recovered.start(spec)
        self.assertEqual('interrupted',result['jobStatus']); self.assertFalse(result['savedDraftVerified'])
        self.assertEqual('unconfirmed',result['cleanup']); self.assertEqual(0,recovered.executions)
        self.assertEqual('Save\n',(child/'sends.txt').read_text())
        self.assertEqual(result,recovered.get(spec['id']))


if __name__ == '__main__': unittest.main()
