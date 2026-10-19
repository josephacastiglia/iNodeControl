"""Offline protocol/retained-screen tests. No listener, desktop or phone access."""
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import uuid
import zipfile

from PIL import Image, ImageDraw

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import validate_workflow as live
from farm_observations import ObservationStore
from farm_screen_layout import next_crop


class FixtureOcr:
    """Retained OCR metadata, not a new OCR accuracy test."""
    def __init__(self, kernel): self.kernel=kernel
    def read(self, raw):
        if self.kernel.scenario=='failed_ocr' and self.kernel.owned: raise RuntimeError('Fixture OCR failure')
        text=copy.deepcopy(self.kernel.texts[self.kernel.frame_key()])
        digest=hashlib.sha256(raw).hexdigest(); text['frameSha256']=digest
        detail=text.get('controlOcr',{}).get('next')
        if detail:
            crop,pixel_hash=next_crop(raw)
            detail.update(sourceFrameSha256=digest,sourcePixelsSha256=pixel_hash,imageSha256=hashlib.sha256(crop).hexdigest())
        if self.kernel.scenario=='wrong_account' and self.kernel.screen=='profile':
            for row in text['lines']:
                row['text']=row['text'].replace(live.ACCOUNT,'wrong.account')
                for word in row['words']: word['text']=word['text'].replace(live.ACCOUNT,'wrong.account')
        if self.kernel.scenario=='wrong_caption' and self.kernel.screen=='details':
            for row in text['lines']:
                if row['text']=='iMouse carousel draft test.': row['text']='Different caption.'
        return text


class FixtureKernel:
    _is_live_http=False
    def __init__(self, templates, texts, scenario='normal'):
        self.templates,self.texts,self.scenario=templates,texts,scenario
        self.screen,self.index,self.saves,self.owned='profile',1,0,False
        self.generation,self.sequence,self.now=4,100,1000.
        self.session=uuid.uuid4().hex; self.calls=[]; self.page_captures=0
        self.cancelled=None

    def clock(self): self.now+=.001; return self.now
    def pause(self, seconds): self.now+=seconds
    def resolve_device_id(self, phone):
        if phone!='C24C': raise AssertionError('Other phone addressed')
        return live.LIVE_TEST_DEVICE_ID
    def receiver(self):
        return dict(deviceid=live.LIVE_TEST_DEVICE_ID,name='iMouse2-C24C',receiver_pid=321,receiver_restarts=0,
            live=True,frames=self.sequence,frame_session=self.session)
    def kernel_status(self):
        return dict(code=0,build_identity=dict(sha256='a'*64),input_leases_required=True,allowed=['C24C'],
            process=dict(pid=123,started_utc='fixture'),receivers=[self.receiver()])
    def devices(self): return [dict(deviceid=live.LIVE_TEST_DEVICE_ID,pid='C24C',uid='fixture-uid')]
    def input_status(self):
        return {live.LIVE_TEST_DEVICE_ID:dict(id=live.LIVE_TEST_DEVICE_ID,generation=self.generation,owned=self.owned,
            active=False,stopped=False,releasing=False,release_failed=False,lease_remaining_ms=30000)}
    def preflight_phone(self, phone):
        if self.owned: raise AssertionError('Takeover')
        return dict(resolved_id=self.resolve_device_id(phone),receiver=self.receiver())
    def acquire(self, phones, lease_ms):
        assert phones==['C24C'] and not self.owned
        self.owned=True; return {'C24C':'fixture-token'}
    def renew_if_needed(self, tokens, min_remaining_ms):
        assert tokens=={'C24C':'fixture-token'} and self.owned
    def release(self, tokens):
        assert tokens=={'C24C':'fixture-token'}; self.owned=False; self.calls.append('release')
    def frame_key(self):
        if self.screen=='editor': return 'editor'+str(self.index)
        if self.screen in ('picker','library') and self.saves: return self.screen+'_saved'
        return self.screen
    def shot(self, phone):
        self.resolve_device_id(phone); self.sequence+=1; self.page_captures+=1
        raw=self.templates[self.frame_key()]
        if self.scenario=='known_transients':
            with Image.open(io.BytesIO(raw)) as image:
                draw=ImageDraw.Draw(image)
                if self.screen=='picker':
                    draw.rectangle((161,1064,337,1069),fill='#555555' if self.page_captures==2 else 'white')
                if self.screen=='editor' and self.page_captures==1:
                    draw.rectangle((140,76,360,120),fill='#555555')
                buffer=io.BytesIO(); image.save(buffer,'PNG'); raw=buffer.getvalue()
        age='2000' if self.scenario=='stale_frame' and self.owned else '0'
        return raw,{'X-iMouse-Frame-Session':self.session,'X-iMouse-Frame-Sequence':str(self.sequence),
            'X-iMouse-Frame-Age-Ms':age,'X-iMouse-Frame-Delivery':'flowing'}
    def send(self, phone, token, fun, **data):
        assert phone=='C24C' and token=='fixture-token' and self.owned
        self.calls.append((fun,dict(data)))
        if fun in ('/mouse/reset','/mouse/move'):
            self.sequence+=1; return dict(code=0)
        if fun=='/mouse/swipe':
            assert self.screen=='editor' and self.index<3
            self.index+=1
        elif fun=='/mouse/click':
            if self.screen=='profile': self.screen='create'
            elif self.screen=='create': self.screen='picker'
            elif self.screen=='picker': self.screen='profile' if data['x']==39 else 'library'
            elif self.screen=='library': self.screen='editor'; self.index=1
            elif self.screen=='editor': self.screen='details' if data['x']==438 else 'save_prompt'
            elif self.screen=='details': self.screen='editor'  # Retain index 3, as observed live.
            elif self.screen=='save_prompt':
                self.screen='picker'; self.saves+=1
                if self.scenario=='lost_save': raise TimeoutError('Fixture lost Save response')
                if self.scenario=='cancel_after_save': self.cancelled.set()
            else: raise AssertionError('Unexpected action')
        else: raise AssertionError('Unapproved function')
        self.page_captures=0
        return dict(code=0)


class WorkflowTests(unittest.TestCase):
    def test_owned_budget_remains_bounded_and_original_inspection_keeps_90_seconds(self):
        now=[1000.]
        original=live.OwnedCaptureRun(None,'test',threading.Event(),lambda:now[0])
        self.assertEqual(1090.,original.deadline)
        full=live.OwnedCaptureRun(None,'test',threading.Event(),lambda:now[0],budget_seconds=120)
        now[0]=1090.
        with self.assertRaises(live.InspectionStopped): original.check_budget()
        full.check_budget()
        now[0]=1120.
        with self.assertRaises(live.InspectionStopped): full.check_budget()
        for invalid in (0,121,True,float('inf')):
            with self.assertRaises(ValueError):
                live.OwnedCaptureRun(None,'test',threading.Event(),lambda:now[0],budget_seconds=invalid)

    @classmethod
    def setUpClass(cls):
        cls.templates=live.references(); cls.texts={}
        refs=json.loads((HERE/'reference-frames.json').read_text(encoding='utf-8'))
        for label,row in refs.items():
            path=Path(row['path']); record=json.loads((path.parent/'record.json').read_text(encoding='utf-8-sig'))
            cls.texts[label]=next(c['observation']['text'] for c in record['captures'] if c['name']==path.stem)
        with zipfile.ZipFile(live.ROOT/'analysis/farm-phone-transfer-20261017/test-carousel.zip') as package:
            manifest=json.loads(package.read('manifest.json'))
            cls.caption=manifest['caption']; cls.assets=[package.read(a['file']) for a in manifest['assets']]

    def run_fixture(self, scenario='normal', restore=False, preserve=False):
        temporary=tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        folder=Path(temporary.name); kernel=FixtureKernel(self.templates,self.texts,scenario)
        if restore: kernel.screen='picker'
        if preserve: kernel.screen='editor'; kernel.index=3
        store=ObservationStore(folder/'observations.sqlite3',ocr=FixtureOcr(kernel),clock=kernel.clock,monotonic=kernel.clock)
        workflow=live.Workflow(folder,kernel,store,self.assets,self.caption,self.templates,'a'*64,'fixture-uid',
            monotonic=kernel.clock,pause=kernel.pause)
        kernel.cancelled=workflow.cancelled
        return workflow.run(restore_profile_only=restore,preserve_open_draft=preserve),kernel,workflow

    def test_open_draft_preservation_checks_caption_saves_once_and_returns_profile(self):
        result,kernel,_=self.run_fixture(preserve=True)
        self.assertEqual('draft_preserved_profile_restored',result['state'],result.get('error'))
        self.assertEqual(1,kernel.saves); self.assertEqual('profile',kernel.screen)
        self.assertEqual('confirmed',result['cleanup']); self.assertFalse(result['savedDraftVerified'])
        self.assertFalse(any(a['kind']=='open_test_draft' for a in result['actions']))

    def test_open_draft_preservation_refuses_wrong_caption(self):
        result,kernel,_=self.run_fixture('wrong_caption',preserve=True)
        self.assertEqual('review_required',result['state']); self.assertEqual(0,kernel.saves)
        self.assertEqual('confirmed',result['cleanup'])

    def test_open_draft_preservation_stops_after_uncertain_save(self):
        result,kernel,_=self.run_fixture('lost_save',preserve=True)
        self.assertEqual('review_required',result['state']); self.assertEqual(1,kernel.saves)
        self.assertEqual('release',kernel.calls[-1]); self.assertEqual('/mouse/click',kernel.calls[-2][0])

    def test_whole_flow_uses_one_lease_all_slides_caption_and_returns_profile(self):
        result,kernel,_=self.run_fixture()
        self.assertEqual('validation_passed',result['state'],result.get('error'))
        self.assertEqual('confirmed',result['cleanup']); self.assertFalse(kernel.owned)
        self.assertEqual('profile',kernel.screen); self.assertEqual(2,kernel.saves)
        self.assertEqual('consistent_sampled_history',result['accountHistory']['status'])
        self.assertEqual([1,2,3,3,1,2,3,3], [o['index'] for i,o in enumerate(result['observations'])
            if o['role']=='editor' and (i==0 or result['observations'][i-1]['role']!='editor' or o['index']!=result['observations'][i-1]['index'])])
        self.assertEqual('offline_protocol_fixture',result['source'])
        self.assertFalse(result['productionAdapterAccepted'])
        self.assertEqual('confirmed',result['evidenceExport'])
        for index, command in enumerate(result['commands']):
            if command['fun'] in ('/mouse/click','/mouse/swipe'):
                self.assertEqual('park_after_answered_action',result['commands'][index+1]['purpose'])

    def test_duplicate_image_export_happens_after_release_and_matches_retained_bytes(self):
        from unittest.mock import patch
        written=[]; released=[]; write=Path.write_bytes; release=FixtureKernel.release
        def record_release(kernel, tokens):
            release(kernel,tokens); released.append(True)
        def record_write(path, raw):
            if path.suffix=='.png':
                self.assertTrue(released,'Duplicate image export must follow confirmed lease release.')
                written.append((path.name,bytes(raw)))
            return write(path,raw)
        with patch.object(Path,'write_bytes',record_write), patch.object(FixtureKernel,'release',record_release):
            result,kernel,workflow=self.run_fixture()
        self.assertEqual('validation_passed',result['state'],result.get('error'))
        self.assertEqual(len(result['observations']),len(written))
        self.assertEqual('release',kernel.calls[-1])
        for entry,(name,raw) in zip(result['observations'],written):
            self.assertEqual(entry['frame'],name)
            self.assertEqual(entry['observation']['reviewFrameSha256'],hashlib.sha256(raw).hexdigest())

    def test_known_transients_collect_new_pairs_without_semantic_retries(self):
        result,kernel,_=self.run_fixture('known_transients')
        self.assertEqual('validation_passed',result['state'],result.get('error'))
        reasons=' '.join(event.get('reason','') for event in result['transitionChecks'])
        self.assertIn('indicator',reasons); self.assertIn('suggestion',reasons)
        self.assertEqual(2,kernel.saves)
        self.assertEqual(len(result['actions']),len({a['label'] for a in result['actions']}))

    def test_unknown_save_response_stops_without_another_input(self):
        result,kernel,_=self.run_fixture('lost_save')
        self.assertEqual('review_required',result['state']); self.assertEqual(1,kernel.saves)
        self.assertEqual('release',kernel.calls[-1]); self.assertEqual('/mouse/click',kernel.calls[-2][0])
        self.assertEqual('outcome_unknown',result['commands'][-1]['state'])
        self.assertFalse(result['savedDraftVerified'])

    def test_cancel_after_save_releases_without_navigation(self):
        result,kernel,_=self.run_fixture('cancel_after_save')
        self.assertEqual('review_required',result['state']); self.assertEqual(1,kernel.saves)
        self.assertEqual('release',kernel.calls[-1]); self.assertEqual('/mouse/click',kernel.calls[-2][0])
        self.assertEqual('confirmed',result['cleanup'])

    def test_wrong_account_refuses_even_pointer_input(self):
        result,kernel,_=self.run_fixture('wrong_account')
        self.assertEqual('review_required',result['state']); self.assertEqual([],kernel.calls)

    def test_wrong_caption_stops_before_save(self):
        result,kernel,_=self.run_fixture('wrong_caption')
        self.assertEqual('review_required',result['state']); self.assertEqual(0,kernel.saves)
        self.assertEqual('details',kernel.screen); self.assertEqual('confirmed',result['cleanup'])

    def test_stale_capture_never_reaches_click_or_swipe(self):
        result,kernel,_=self.run_fixture('stale_frame')
        self.assertEqual('review_required',result['state'])
        self.assertFalse(any(isinstance(call,tuple) and call[0] in ('/mouse/click','/mouse/swipe') for call in kernel.calls))

    def test_failed_capture_retains_its_id_and_reason_without_a_click(self):
        result,kernel,_=self.run_fixture('failed_ocr')
        self.assertEqual('review_required',result['state']); self.assertIn('Fixture OCR failure',result['error'])
        self.assertEqual('failed',result['observations'][0]['state'])
        self.assertEqual(result['observations'][0]['observationId'],result['observations'][0]['observation']['id'])
        self.assertFalse(any(isinstance(call,tuple) and call[0] in ('/mouse/click','/mouse/swipe') for call in kernel.calls))
        self.assertEqual('confirmed',result['cleanup'])

    def test_changed_navigation_icon_is_not_guessed(self):
        image=Image.open(io.BytesIO(self.templates['profile'])).convert('RGB')
        ImageDraw.Draw(image).rectangle((15,69,56,107),fill='red')
        output=io.BytesIO(); image.save(output,'PNG')
        with self.assertRaises(live.InspectionStopped):
            live.icon_matches(output.getvalue(),self.templates['profile'],(15,69,57,108))

    def test_duplicate_action_label_cannot_be_replayed(self):
        result,kernel,workflow=self.run_fixture()
        before=list(kernel.calls)
        with self.assertRaises(live.InspectionStopped): workflow.action('prepared-save-once','save_draft','save_prompt')
        self.assertEqual(before,kernel.calls)

    def test_picker_recovery_returns_to_profile_without_opening_or_saving(self):
        result,kernel,_=self.run_fixture(restore=True)
        self.assertEqual('profile_restored',result['state'],result.get('error'))
        self.assertEqual('confirmed',result['cleanup']); self.assertEqual('profile',kernel.screen)
        self.assertEqual(0,kernel.saves); self.assertFalse(result['savedDraftVerified'])
        self.assertEqual(['leave_picker'],[a['kind'] for a in result['actions']])

    def test_picker_recovery_still_obeys_cancellation_before_actions(self):
        temporary=tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        folder=Path(temporary.name); (folder/'STOP').write_text('',encoding='utf-8')
        kernel=FixtureKernel(self.templates,self.texts); kernel.screen='picker'
        store=ObservationStore(folder/'observations.sqlite3',ocr=FixtureOcr(kernel),clock=kernel.clock,monotonic=kernel.clock)
        workflow=live.Workflow(folder,kernel,store,self.assets,self.caption,self.templates,'a'*64,'fixture-uid',
            monotonic=kernel.clock,pause=kernel.pause)
        result=workflow.run(restore_profile_only=True)
        self.assertEqual('review_required',result['state']); self.assertFalse(result['actions'])
        self.assertEqual(['release'],kernel.calls)


if __name__=='__main__': unittest.main()
