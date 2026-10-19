"""Offline checks for the local fault injector; no socket or desktop access."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tools'))

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec); spec.loader.exec_module(result); return result

backend=module('local_delay_backend',HERE/'test_backend.py')
fixtures=module('prompt_fixture_library',ROOT/'analysis/farm-prompt-recovery-20261018/test_prompt_recovery.py')
import farm_test_network


class PreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.PromptRecoveryTests.setUpClass()
        cls.fixtures=fixtures.PromptRecoveryTests.fixtures

    fixture=fixtures.extracted.ExtractionTests.fixture

    def candidate(self):
        workflow,kernel=self.fixture(); kernel.url='http://127.0.0.1:9916/api'
        marker=workflow.folder/'fault.json'
        return workflow,kernel,marker

    @staticmethod
    def pending(workflow):
        workflow.record['commands']=[dict(purpose='prepared-save-once',state='outcome_unknown',
            decisionChecks=[dict(stage='before_dispatch_journal',freshness='recent',
                evidenceRecordSha256='a'*64,observationId='fixture')])]

    def test_controlled_delay_exercises_real_recovery_and_complete_sequence_once(self):
        workflow,kernel,marker=self.candidate(); pauses=[]
        def pause(seconds): pauses.append(seconds); kernel.pause(seconds)
        restore=backend.install_delay(marker,pause=pause)
        try: result=workflow.run()
        finally: restore()
        self.assertEqual('validation_passed',result['state'],result.get('error'))
        self.assertEqual([1.65],pauses); self.assertEqual(19,len(result['actions'])); self.assertEqual(2,kernel.saves)
        self.assertEqual(1,len(result['promptRecoveries'])); self.assertEqual('profile',kernel.screen)
        self.assertEqual('confirmed',result['cleanup'])
        proof=json.loads(marker.read_text(encoding='utf-8'))
        self.assertEqual('delay_completed',proof['state']); self.assertFalse(proof['transportCalledByWrapper'])
        saves=[c for c in result['commands'] if c['purpose']=='prepared-save-once']
        self.assertEqual(['not_sent','answered'],[c['state'] for c in saves])
        self.assertEqual(proof['commandIndex'],result['commands'].index(saves[0]))
        self.assertEqual(proof['observationId'],saves[0]['decisionChecks'][0]['observationId'])

    def test_stop_during_local_delay_never_sends_the_pending_save(self):
        workflow,kernel,marker=self.candidate()
        def pause(seconds): kernel.pause(seconds); workflow.cancelled.set()
        restore=backend.install_delay(marker,pause=pause)
        try: result=workflow.run()
        finally: restore()
        self.assertEqual('review_required',result['state']); self.assertEqual(0,kernel.saves)
        self.assertEqual('not_sent',result['actions'][-1]['state']); self.assertEqual('confirmed',result['cleanup'])
        self.assertEqual('release',kernel.calls[-1]); self.assertFalse(kernel.owned)

    def test_delay_refuses_other_account_endpoint_or_content(self):
        for change in ('account','endpoint','content'):
            with self.subTest(change=change):
                workflow,kernel,marker=self.candidate(); self.pending(workflow)
                if change=='account': workflow.account='other.account'
                elif change=='endpoint': kernel.url='http://127.0.0.1:9913/api'
                else: workflow.assets=[b'not the test image']
                restore=backend.install_delay(marker,pause=lambda _:self.fail('Delay must not run'))
                try:
                    with self.assertRaisesRegex(ValueError,'isolated C24C test draft'): workflow.save()
                finally: restore()
                self.assertFalse(marker.exists()); self.assertEqual([],kernel.calls)

    def test_already_used_fault_record_cannot_be_reinstalled(self):
        workflow,kernel,marker=self.candidate(); marker.write_text('{}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'already exists'): backend.install_delay(marker)
        self.assertEqual([],kernel.calls)

    def test_nonfresh_or_uncertain_post_dispatch_record_is_never_delayed(self):
        changes=({'state':'answered'}, {'purpose':'reopened-save-once'},
            {'decisionChecks':[dict(stage='before_dispatch_journal',freshness='stale')]},
            {'decisionChecks':[dict(stage='before_dispatch_journal',freshness='recent'),dict(stage='before_transport',freshness='recent')]})
        for change in changes:
            with self.subTest(change=change):
                workflow,kernel,marker=self.candidate(); self.pending(workflow)
                workflow.record['commands'][-1].update(copy.deepcopy(change))
                restore=backend.install_delay(marker,pause=lambda _:self.fail('No eligible pre-dispatch decision'))
                try: workflow.save()
                finally: restore()
                self.assertFalse(marker.exists()); self.assertEqual([],kernel.calls)

    def test_server_bootstrap_rejects_malformed_or_outside_record_path(self):
        for args in (['bootstrap'],['bootstrap','--fault-record',str(ROOT/'wrong.json'),'--','--mode','live']):
            with self.subTest(args=args),patch.object(sys,'argv',args),patch.object(backend.runpy,'run_path',side_effect=AssertionError('No server')):
                with self.assertRaises(SystemExit): backend.main()

    def test_server_bootstrap_forwards_only_explicit_arguments(self):
        arguments=['bootstrap','--fault-record',str(HERE/'local-delay.json'),'--','--host','127.0.0.1','--port','9915','--mode','live','--no-browser']
        with patch.object(sys,'argv',arguments),patch.object(backend,'install_delay') as install,patch.object(backend.runpy,'run_path') as run:
            backend.main()
            install.assert_called_once_with((HERE/'local-delay.json').resolve())
            run.assert_called_once_with(str(ROOT/'tools/imouse_farm_server.py'),run_name='__main__')
            self.assertEqual(arguments[4:],sys.argv[1:])


if __name__=='__main__': unittest.main(verbosity=2)
