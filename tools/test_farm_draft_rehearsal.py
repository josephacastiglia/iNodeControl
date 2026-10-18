import copy
import io
import json
import sqlite3
import subprocess
import sys
import threading
import unittest
import uuid
from unittest.mock import patch
from PIL import Image, ImageDraw, PngImagePlugin

from farm_draft_rehearsal import DraftRehearsals, DraftAppModel, SCENARIOS, save_prompt
from farm_drafts import DraftConflict


class RehearsalTests(unittest.TestCase):
    def setUp(self):
        from test_farm_carousel_inspection import InspectionTests
        self.fixture=InspectionTests(); self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        f=self.fixture
        # Deterministic fault tests; real-clock aging is covered separately below.
        self.store=DraftRehearsals(f.root/'rehearsal.db',f.drafts,clock=lambda:f.now[0],monotonic=lambda:f.now[0])
        self.spec=dict(id=str(uuid.uuid4()),draft_id=f.draft['id'],revision=f.draft['revision'],scenario='normal')
        self.models=[]

    def factory(self,*args):
        model=DraftAppModel(*args); self.models.append(model); return model

    def run_case(self,scenario='normal',**kwargs):
        self.spec.update(id=str(uuid.uuid4()),scenario=scenario)
        return self.store.run(self.spec,model_factory=kwargs.pop('model_factory',self.factory),**kwargs)

    def test_full_sequence_saves_once_checks_every_slide_and_reopens_persisted_model(self):
        result=self.run_case()
        self.assertEqual('simulation_passed',result['state'],result)
        self.assertEqual('confirmed',result['cleanup']); self.assertFalse(self.models[0].owned)
        self.assertEqual(1,self.models[0].saves)
        picker=next(a for a in result['actions'] if a['kind']=='open_drafts')['pickerStability']
        self.assertTrue(picker['previewChanged']); self.assertTrue(picker['controlsStable'])
        self.assertEqual(2,self.models[0].calls.count('open_drafts'))
        self.assertEqual(['open_create','choose_post_format','open_drafts','open_prepared'],
                         [a['kind'] for a in result['actions'][:4]])
        self.assertEqual(['save_draft','reopen'],[a['kind'] for a in result['actions'] if a['kind'] in ('save_draft','reopen')])
        for phase in ('prepared','reopened'):
            self.assertEqual({1,2},{c['index'] for c in result['checks'] if c['role']==phase+'_slide'})
            self.assertTrue(any(c['role']==phase+'_caption' for c in result['checks']))
        for flag in ('savedDraftVerified','accountContinuityProven','automaticInputAllowed'): self.assertFalse(result[flag])
        self.assertEqual('simulation',result['source'])

    def test_every_advertised_fault_holds_and_never_claims_live_acceptance(self):
        reasons={'save_reply_lost':'TimeoutError','reopen_reply_lost':'TimeoutError',
                 'permission_prompt':'dialog','account_changed':'Account boundary','stale_frame':'fresh',
                 'wrong_slide':'Full-size slide','wrong_caption':'caption','duplicate_cover':'ambiguous'}
        for scenario in SCENARIOS[1:]:
            with self.subTest(scenario=scenario):
                result=self.run_case(scenario)
                self.assertEqual('review_required',result['state'],result)
                self.assertIn(reasons[scenario],result['reason'])
                self.assertEqual('confirmed',result['cleanup'])
                self.assertFalse(result['savedDraftVerified']); self.assertFalse(self.models[-1].owned)

    def test_lost_save_answer_observes_picker_without_navigation_or_resave(self):
        result=self.run_case('save_reply_lost'); model=self.models[-1]
        self.assertEqual(1,model.saves); self.assertNotIn('reopen',model.calls)
        self.assertEqual('outcome_unknown',result['actions'][-1]['state'])
        self.assertEqual('picker_after_unknown_reply',result['reconciliation']['status'])
        self.assertEqual(1,model.calls.count('open_drafts'))  # Initial prepared draft only.
        calls=list(model.calls)
        restarted=DraftRehearsals(self.store.path,self.fixture.drafts)
        self.assertEqual(result,restarted.run(self.spec,model_factory=lambda *a: self.fail('No replay after restart')))
        self.assertEqual(calls,model.calls)

    def test_lost_reopen_reply_is_reviewed_read_only_not_reopened_twice(self):
        result=self.run_case('reopen_reply_lost')
        self.assertEqual(1,self.models[-1].calls.count('reopen'))
        self.assertEqual('reopen',result['reconciliation']['action'])
        self.assertEqual('matching_screen_after_unknown_reply',result['reconciliation']['status'])

    def test_picker_changes_expiry_stream_change_and_cancellation_stop_before_navigation(self):
        for fault in ('control','stale','stream','cancel','overlay'):
            event=threading.Event()
            def factory(*args):
                model=self.factory(*args); shot=model.shot; count=[0]
                def capture(phone):
                    raw,headers=shot(phone)
                    if model.screen=='picker' and model.saved is not None:
                        count[0]+=1
                        if count[0]==3:
                            if fault=='stale': headers['X-iMouse-Frame-Age-Ms']='2000'
                            elif fault=='stream': model.session=uuid.uuid4().hex
                            elif fault=='cancel': event.set()
                            else:
                                with Image.open(io.BytesIO(raw)) as image:
                                    text=json.loads(image.info['imouseSyntheticText']); image=image.convert('RGB')
                                if fault=='control': ImageDraw.Draw(image).rectangle((435,80,440,85),fill='white')
                                else:
                                    for label,y in (("Don't Allow",600),('Allow',650)):
                                        text['lines'].append(dict(text=label,words=[dict(text=label,x=100,y=y,width=90,height=16)]))
                                info=PngImagePlugin.PngInfo(); info.add_text('imouseSyntheticText',json.dumps(text))
                                stream=io.BytesIO(); image.save(stream,'PNG',pnginfo=info); raw=stream.getvalue()
                    return raw,headers
                model.shot=capture; return model
            with self.subTest(fault=fault):
                result=self.run_case(model_factory=factory,cancelled=event); model=self.models[-1]
                self.assertEqual('review_required',result['state'],result)
                self.assertEqual(1,model.saves); self.assertEqual(1,model.calls.count('open_drafts'))
                self.assertNotIn('reopen',model.calls); self.assertFalse(model.owned)

    def test_lost_drafts_navigation_reply_never_repeats_save_or_navigation(self):
        def factory(*args):
            model=self.factory(*args); perform=model.perform
            def action(value,token):
                response=perform(value,token)
                if value['kind']=='open_drafts' and model.saved is not None: raise TimeoutError('Lost navigation reply')
                return response
            model.perform=action; return model
        result=self.run_case(model_factory=factory); model=self.models[-1]
        self.assertEqual('review_required',result['state']); self.assertEqual(1,model.saves)
        self.assertEqual(2,model.calls.count('open_drafts')); self.assertNotIn('reopen',model.calls)
        self.assertEqual('outcome_unknown',result['actions'][-1]['state'])

    def test_known_loading_changes_settle_without_manual_review_or_repeating_actions(self):
        def factory(*args):
            model=self.factory(*args); shot=model.shot; counts={}
            def capture(phone):
                raw,headers=shot(phone)
                key=(model.screen,model.saved is not None,model.reopened)
                counts[key]=counts.get(key,0)+1
                with Image.open(io.BytesIO(raw)) as source:
                    annotations=source.info['imouseSyntheticText']; image=source.convert('RGB')
                draw=ImageDraw.Draw(image)
                if model.screen=='picker':
                    draw.rectangle((161,1064,338,1070),fill='white' if counts[key]<=2 else '#555555')
                elif model.screen=='editor' and counts[key]>=3:
                    draw.rounded_rectangle((123,65,376,132),radius=30,fill='#888888')
                info=PngImagePlugin.PngInfo(); info.add_text('imouseSyntheticText',annotations)
                stream=io.BytesIO(); image.save(stream,'PNG',pnginfo=info)
                return stream.getvalue(),headers
            model.shot=capture; return model
        result=self.run_case(model_factory=factory); model=self.models[-1]
        self.assertEqual('simulation_passed',result['state'],result['reason'])
        self.assertEqual(1,model.saves); self.assertEqual(1,model.calls.count('reopen'))
        self.assertEqual(1,model.calls.count('choose_post_format'))
        self.assertTrue(any('fading' in e.get('reason','') for e in result['transitionChecks']))
        self.assertTrue(any('header' in e.get('reason','') for e in result['transitionChecks']))
        self.assertFalse(any(e['state']=='held' for e in result['transitionChecks']))
        self.assertEqual('confirmed',result['cleanup']); self.assertFalse(model.owned)

    def test_cancel_while_waiting_for_indicator_does_not_repeat_save_or_navigate(self):
        event=threading.Event()
        def factory(*args):
            model=self.factory(*args); shot=model.shot; count=[0]
            def capture(phone):
                raw,headers=shot(phone)
                if model.screen=='picker' and model.saved is not None:
                    count[0]+=1
                    if count[0]==3: event.set()
                return raw,headers
            model.shot=capture; return model
        result=self.run_case(model_factory=factory,cancelled=event); model=self.models[-1]
        self.assertEqual('review_required',result['state'])
        self.assertEqual(1,model.saves); self.assertEqual(1,model.calls.count('open_drafts'))
        self.assertNotIn('reopen',model.calls); self.assertFalse(model.owned)

    def test_editor_layout_is_not_permission_to_press_an_ambiguous_next_button(self):
        original=self.store.observations.ocr.read
        def ambiguous(raw):
            text=original(raw)
            for row in text['lines']:
                if row['text']=='Next' and row['words'][0]['y']>980:
                    row['text']=row['words'][0]['text']='ext'
            return text
        with patch.object(self.store.observations.ocr,'read',side_effect=ambiguous): result=self.run_case()
        self.assertEqual('review_required',result['state']); self.assertIn('Next label',result['reason'])
        self.assertNotIn('details',self.models[-1].calls); self.assertEqual(0,self.models[-1].saves)

    def test_exact_cropped_next_label_works_but_recognition_delay_can_expire_it(self):
        from test_farm_screen_layout import crop_proof
        original=self.store.observations.ocr.read
        for slow in (False,True):
            def cropped(raw):
                text=original(raw)
                for row in text['lines']:
                    if row['text']=='Next' and row['words'][0]['y']>980:
                        row['text']=row['words'][0]['text']='ext'; crop_proof(raw,text)
                        if slow: self.fixture.now[0]+=2
                return text
            with self.subTest(slow=slow),patch.object(self.store.observations.ocr,'read',side_effect=cropped):
                result=self.run_case()
            self.assertEqual('review_required' if slow else 'simulation_passed',result['state'],result)
            if slow: self.assertEqual(0,self.models[-1].saves); self.assertNotIn('details',self.models[-1].calls)

    def test_dialog_or_stale_save_frame_prevents_save(self):
        for scenario in ('permission_prompt','stale_frame'):
            self.run_case(scenario)
            self.assertEqual(0,self.models[-1].saves)

    def test_malformed_requests_or_live_adapter_never_start(self):
        for change in ({'device_id':'C241'},{'publish':True},{'scenario':'real_phone'},{'revision':True}):
            with self.assertRaises(ValueError): self.store.run({**self.spec,**change},model_factory=self.factory)
        self.assertEqual([],self.models)
        def live(*args):
            model=self.factory(*args); model._is_live_http=True; return model
        result=self.run_case(model_factory=live)
        self.assertIn('offline',result['reason']); self.assertEqual([],self.models[-1].calls)

    def test_cancel_at_every_action_boundary_stops_and_releases_without_replay(self):
        success=self.run_case()
        self.assertEqual('simulation_passed',success['state'])
        for position in range(len(success['actions'])):
            event=threading.Event()
            def make(*args):
                model=self.factory(*args); original=model.perform; count=[0]
                def perform(action,token):
                    result=original(action,token)
                    if count[0]==position: event.set()
                    count[0]+=1; return result
                model.perform=perform; return model
            with self.subTest(position=position):
                result=self.run_case(cancelled=event,model_factory=make)
                self.assertEqual('review_required',result['state']); self.assertEqual('confirmed',result['cleanup'])
                self.assertEqual(position+1,len(result['actions']))
                self.assertLessEqual(self.models[-1].saves,1)

    def test_cancel_before_any_work_does_not_acquire(self):
        event=threading.Event(); event.set(); result=self.run_case(cancelled=event)
        self.assertEqual('review_required',result['state']); self.assertEqual([],self.models[-1].calls)

    def test_early_cancel_survives_delayed_start_and_backend_restart(self):
        self.assertTrue(self.store.cancel(self.spec['id'])['cancellationRequested'])
        restarted=DraftRehearsals(self.store.path,self.fixture.drafts)
        result=restarted.run(self.spec,model_factory=self.factory)
        self.assertEqual('review_required',result['state']); self.assertEqual([],self.models[-1].calls)

    def test_real_process_exit_after_save_recovers_unknown_without_repeating_action(self):
        from pathlib import Path
        root=self.fixture.root
        (root/'request.json').write_text(json.dumps(self.spec),encoding='utf-8')
        script='''import json,os,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from farm_drafts import CarouselDrafts
from farm_draft_rehearsal import DraftAppModel,DraftRehearsals
root=Path(sys.argv[2])
class CrashAfterSave(DraftAppModel):
    def perform(self,action,token):
        result=super().perform(action,token)
        if action['kind']=='save_draft':
            (root/'saved-once.txt').write_text(str(self.saves))
            os._exit(73)
        return result
drafts=CarouselDrafts(root/'drafts.db',root/'stage')
DraftRehearsals(root/'rehearsal.db',drafts).run(json.loads((root/'request.json').read_text()),model_factory=CrashAfterSave)
'''
        child=subprocess.run([sys.executable,'-c',script,str(Path(__file__).resolve().parent),str(root)],
                             timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),capture_output=True)
        self.assertEqual(73,child.returncode,child.stderr.decode(errors='replace'))
        restarted=DraftRehearsals(self.store.path,self.fixture.drafts)
        result=restarted.run(self.spec,model_factory=lambda *a:self.fail('No replay after process crash'))
        self.assertEqual('review_required',result['state']); self.assertEqual('unconfirmed',result['cleanup'])
        self.assertEqual('outcome_unknown',result['actions'][-1]['state'])
        self.assertEqual('save_draft',result['actions'][-1]['kind']); self.assertEqual('1',(root/'saved-once.txt').read_text())

    def test_replaced_lease_does_not_release_new_owner_or_send_more_actions(self):
        def factory(*args):
            model=self.factory(*args); original=model.perform
            def perform(action,token):
                response=original(action,token)
                if action['kind']=='save_draft': model.generation+=1; model.token='other-owner'
                return response
            model.perform=perform; return model
        result=self.run_case(model_factory=factory)
        self.assertEqual('review_required',result['state']); self.assertEqual('unconfirmed',result['cleanup'])
        self.assertNotIn('reopen',self.models[-1].calls); self.assertTrue(self.models[-1].owned)
        self.assertEqual('other-owner',self.models[-1].token)

    def test_cleanup_failure_never_reports_success(self):
        def factory(*args):
            model=self.factory(*args)
            def release(tokens): raise TimeoutError('private token must not leak')
            model.release=release; return model
        result=self.run_case(model_factory=factory)
        self.assertEqual('review_required',result['state']); self.assertEqual('unconfirmed',result['cleanup'])
        self.assertNotIn('private token',json.dumps(result))

    def test_caption_that_cannot_fit_on_the_supported_screen_requires_review(self):
        f=self.fixture
        for caption in ('Hidden text '*100, '\n'.join('Line '+str(n) for n in range(10))):
            f.draft=f.drafts.save(f.draft['id'],f.draft['revision'],'Caption limits',caption,f.draft['slideIds'])
            self.spec['revision']=f.draft['revision']
            result=self.run_case()
            self.assertEqual('review_required',result['state']); self.assertIn('caption',result['reason'])
            self.assertEqual(0,self.models[-1].saves)

    def test_multiline_caption_survives_model_save_and_reopen_exactly(self):
        f=self.fixture; caption='Draft only.\nSecond line: 1, 2, 3.\nNever publish.'
        f.draft=f.drafts.save(f.draft['id'],f.draft['revision'],'Caption test',caption,f.draft['slideIds'])
        self.spec['revision']=f.draft['revision']
        self.assertEqual('simulation_passed',self.run_case()['state'])
        self.assertEqual(caption,self.models[-1].saved[1])

    def test_action_journal_precedes_model_save(self):
        def factory(*args):
            model=self.factory(*args); original=model.perform
            def perform(action,token):
                if action['kind']=='save_draft':
                    with self.store.connect() as db:
                        doc=json.loads(db.execute('SELECT document FROM inspections WHERE id=?',(self.spec['id'],)).fetchone()[0])
                    self.assertEqual('outcome_unknown',doc['actions'][-1]['state'])
                return original(action,token)
            model.perform=perform; return model
        self.assertEqual('simulation_passed',self.run_case(model_factory=factory)['state'])

    def test_expiry_while_committing_action_is_not_sent(self):
        original=self.store.save
        def save(record):
            original(record)
            if record['actions'] and record['actions'][-1]['kind']=='save_draft':
                observation=record['actions'][-1]['basis']['observationId']
                started,finished=self.store.observations.timings[observation]
                self.store.observations.timings[observation]=(started-10,finished-10)
        with patch.object(self.store,'save',side_effect=save): result=self.run_case()
        self.assertEqual('not_sent',result['actions'][-1]['state']); self.assertEqual(0,self.models[-1].saves)

    def test_restart_partial_journal_does_not_resume_and_frames_survive_pruning(self):
        result=self.run_case(); first=result['observationIds'][0]
        frame=self.store.frame(result['id'],first)
        with self.store.observations.connect() as db: db.execute('DELETE FROM observations')
        result['state']='running'; self.store.save(result)
        restart=DraftRehearsals(self.store.path,self.fixture.drafts)
        recovered=restart.run(self.spec,model_factory=lambda *a:self.fail('No restart replay'))
        self.assertEqual('review_required',recovered['state']); self.assertEqual(frame,restart.frame(result['id'],first))

    def test_conflicting_id_and_changed_source_revision_do_not_replay(self):
        self.run_case()
        with self.assertRaises(DraftConflict): self.store.run({**self.spec,'scenario':'save_reply_lost'})
        f=self.fixture
        f.drafts.save(f.draft['id'],f.draft['revision'],'Edited','changed',f.draft['slideIds'])
        self.assertTrue(self.store.get(self.spec['id'])['draftChangedSinceRun'])
        with self.assertRaises(DraftConflict): self.run_case()

    def test_frame_and_record_corruption_prevent_successful_retrieval(self):
        for column,value in [('frame',b'broken'),('document','{}')]:
            result=self.run_case()
            with self.store.connect() as db:
                db.execute('UPDATE frames SET '+column+'=? WHERE run_id=? AND observation_id=?',(value,result['id'],result['observationIds'][0]))
            with self.assertRaises(ValueError): self.store.get(result['id'])

    def test_save_prompt_needs_complete_geometry_and_no_duplicate_buttons(self):
        from test_farm_observations import ocr_lines
        text=ocr_lines(('If you go back now, your edits will be discarded.',793),('Discard',858),('Save draft',925),('Cancel',1002))
        self.assertTrue(save_prompt(text))
        missing=copy.deepcopy(text); missing['lines'].pop(0); self.assertFalse(save_prompt(missing))
        text['lines'].append(copy.deepcopy(text['lines'][2])); self.assertFalse(save_prompt(text))


if __name__=='__main__': unittest.main()
