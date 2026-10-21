"""No hardware/network: exercise the real capture, media checks, journal and lease guard."""
from farm_phone_identity import LEGACY_C24C
import base64
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import uuid
import zipfile
from unittest.mock import patch

from PIL import Image, ImageDraw
from farm_carousel_inspection import CarouselInspections
from farm_drafts import CarouselDrafts, DraftConflict
from farm_frame_evidence import capture_settled
from farm_observations import ObservationStore
from test_farm_draft_verification import patterned
from test_farm_observations import ocr_lines


class EditorKernel:
    _is_live_http = False
    phone = LEGACY_C24C   # Fixtures model the single-phone C24C window.
    def __init__(self, assets):
        self.assets, self.index, self.sequence, self.generation = assets, 0, 1, 4
        self.owned = False; self.active = False; self.paused = False; self.calls = []
        self.session = 'a' * 32; self.headers = True; self.failure = None
        self.release_failure = False; self.bad_media = False; self.repeat = False
        self.cancelled = None; self.token = None
    def resolve_device_id(self, phone):
        if phone != 'C24C': raise AssertionError('Other phone addressed')
        return 'C24C'
    def kernel_status(self):
        return dict(input_leases_required=True, receivers=[dict(deviceid='C24C', live=True, receiver_pid=10,
                    receiver_restarts=0, frames=self.sequence, frame_session=self.session)])
    def input_status(self):
        return {'C24C': dict(generation=self.generation, owned=self.owned, active=self.active, stopped=self.paused,
                            releasing=False, release_failed=False, lease_remaining_ms=28000)}
    def preflight_phone(self, phone):
        self.resolve_device_id(phone)
        if self.owned: raise RuntimeError('Another controller owns C24C')
        return dict(resolved_id='C24C', receiver=self.kernel_status()['receivers'][0])
    def acquire(self, ids, lease_ms):
        assert ids == ['C24C'] and lease_ms == 30000
        self.calls.append('acquire'); self.owned = True; self.token = 'private-test-token'
        if self.failure == 'acquire_lost': raise TimeoutError(self.token)
        return {'C24C': self.token}
    def renew_if_needed(self, tokens, min_remaining_ms):
        self.calls.append('renew')
        assert min_remaining_ms > 120000
        if not self.owned or tokens != {'C24C': self.token}: raise RuntimeError('Refused token')
        return True
    def release(self, tokens):
        self.calls.append('release')
        if self.release_failure: raise TimeoutError('private-test-token')
        if tokens != {'C24C': self.token}: raise RuntimeError('New owner cannot be released')
        self.owned = False; self.token = None
    def send(self, phone, token, fun, **data):
        self.resolve_device_id(phone)
        assert self.owned and token == self.token and fun == '/mouse/swipe'
        assert data == dict(x1=400, y1=480, x2=100, y2=480, duration=350)
        self.calls.append('swipe'); self.index += 1
        if self.cancelled is not None: self.cancelled.set()
        if self.failure == 'lost_answer': raise TimeoutError('private-test-token')
        if self.failure == 'lease_replaced': self.generation += 1; self.token = 'other-controller'
        if self.failure == 'stream_changed': self.session = 'b' * 32
        if self.failure == 'paused': self.paused = True
        return dict(code=0)
    def shot(self, phone):
        self.resolve_device_id(phone)
        if not self.repeat: self.sequence += 1
        image = Image.new('RGB', (500,1080), 'black')
        source = self.assets[0 if self.bad_media else self.index]
        with Image.open(io.BytesIO(source)) as asset: image.paste(asset.resize((500,625)), (0,164))
        draw = ImageDraw.Draw(image)
        for n, x in enumerate((244,256)): draw.ellipse((x-3,836,x+3,842), fill='white' if n == self.index else '#555555')
        data = io.BytesIO(); image.save(data, 'BMP')
        headers = {'X-iMouse-Frame-Session': self.session, 'X-iMouse-Frame-Sequence': str(self.sequence),
                   'X-iMouse-Frame-Age-Ms': '10', 'X-iMouse-Frame-Delivery': 'flowing'} if self.headers else {}
        return data.getvalue(), headers


class EditorOcr:
    interrupted = False
    def read(self, raw):
        text = ocr_lines(*[(label,899) for label in ('Audio','Text','Overlay','Filter','Edit','Ratio')], ('Next',995))
        if self.interrupted: text['lines'] += ocr_lines(("Don't Allow",600),('Allow',650))['lines']
        text['frameSha256'] = hashlib.sha256(raw).hexdigest()
        return text


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.now = [1000.0]
        self.drafts = CarouselDrafts(self.root / 'drafts.db', self.root / 'stage')
        self.draft = self.drafts.create(str(uuid.uuid4()))
        for n, color in enumerate(('navy','green'),1):
            self.draft = self.drafts.import_image(self.draft['id'], self.draft['revision'], str(n), base64.b64encode(patterned(color,n)).decode())
        with zipfile.ZipFile(io.BytesIO(self.drafts.export(self.draft['id'], self.draft['revision']))) as files:
            self.assets = [files.read('01.jpg'),files.read('02.jpg')]
        self.ocr = EditorOcr()
        self.observations = ObservationStore(self.root / 'observations.db', self.ocr, clock=lambda:self.now[0], monotonic=lambda:self.now[0])
        self.store = CarouselInspections(self.root / 'inspections.db', self.observations, self.drafts, clock=lambda:self.now[0], monotonic=lambda:self.now[0])
        self.kernel = EditorKernel(self.assets)
        self.spec = dict(id=str(uuid.uuid4()),draft_id=self.draft['id'],revision=self.draft['revision'],
                         device_id='C24C',platform='instagram',account='test.account')

    def run_inspection(self, **kwargs): return self.store.run(self.spec, self.kernel, **kwargs)

    def test_matching_slides_are_captured_under_one_private_lease_and_retained(self):
        result = self.run_inspection()
        self.assertEqual('visual_match', result['state'], result)
        self.assertEqual('confirmed', result['cleanup']); self.assertFalse(self.kernel.owned)
        self.assertEqual([1,2], [s['index'] for s in result['slides']])
        self.assertEqual(1, self.kernel.calls.count('acquire')); self.assertEqual(1,self.kernel.calls.count('swipe'))
        self.assertEqual(1, self.kernel.calls.count('release'))
        for key in ('accountContinuityProven','savedDraftVerified','automaticInputAllowed'): self.assertFalse(result[key])
        for slide in result['slides']:
            capture, frame = self.observations.evidence(slide['observationId'])
            self.assertFalse(capture['inputIdle']); self.assertTrue(capture_settled(capture))
            self.assertEqual(result['id'],capture['ownershipEvidence']['runId'])
            with self.observations.connect() as db: db.execute('DELETE FROM observations WHERE id=?',(slide['observationId'],))
            self.assertEqual(frame, self.store.frame(result['id'],slide['observationId']))
        self.assertNotIn('private-test-token', self.store.path.read_bytes().decode('latin1'))

    def test_lost_command_answer_never_retries_even_after_restart(self):
        self.kernel.failure = 'lost_answer'
        result = self.run_inspection(); self.assertEqual('review_required',result['state'])
        self.assertEqual('outcome_unknown',result['actions'][0]['state']); self.assertEqual('confirmed',result['cleanup'])
        calls = list(self.kernel.calls)
        restart = CarouselInspections(self.store.path,self.observations,self.drafts)
        self.assertEqual(result,restart.run(self.spec,self.kernel)); self.assertEqual(calls,self.kernel.calls)
        self.assertNotIn('private-test-token',json.dumps(result))

    def test_missing_paired_metadata_prevents_acquire_or_movement(self):
        self.kernel.headers = False
        result = self.run_inspection()
        self.assertEqual('review_required', result['state']); self.assertIn('paired',result['reason'])
        self.assertEqual([],self.kernel.calls); self.assertEqual('not_needed',result['cleanup'])

    def test_live_movement_is_disabled_even_with_good_frame_metadata(self):
        self.kernel._is_live_http = True
        result = self.run_inspection()
        self.assertIn('disabled',result['reason']); self.assertEqual([],self.kernel.calls)

    def test_foreign_owner_is_not_acquired_or_released(self):
        self.kernel.owned = True; self.kernel.token = 'other-controller'
        result = self.run_inspection()
        self.assertEqual('review_required', result['state']); self.assertEqual([],self.kernel.calls)
        self.assertTrue(self.kernel.owned)

    def test_cancel_after_send_releases_own_lease_without_replay(self):
        event = threading.Event(); self.kernel.cancelled = event
        result = self.run_inspection(cancelled=event)
        self.assertEqual('review_required',result['state']); self.assertEqual('confirmed',result['cleanup'])
        self.assertIn('cancelled',result['reason']); self.assertEqual(1,self.kernel.calls.count('swipe'))

    def test_cancel_before_start_does_not_touch_kernel(self):
        event = threading.Event(); event.set()
        result = self.run_inspection(cancelled=event)
        self.assertIn('cancelled',result['reason']); self.assertEqual([],self.kernel.calls)

    def test_release_failure_is_not_success_and_cannot_be_replayed(self):
        self.kernel.release_failure = True
        result = self.run_inspection()
        self.assertEqual('review_required',result['state']); self.assertEqual('unconfirmed',result['cleanup'])
        calls = list(self.kernel.calls); self.assertEqual(result,self.run_inspection()); self.assertEqual(calls,self.kernel.calls)

    def test_lost_acquire_response_reports_unknown_lease_and_sends_nothing(self):
        self.kernel.failure = 'acquire_lost'
        result = self.run_inspection()
        self.assertEqual('unconfirmed',result['cleanup']); self.assertEqual(['acquire'],self.kernel.calls)
        self.assertNotIn('private-test-token',json.dumps(result))

    def test_replaced_lease_is_not_released_by_old_token(self):
        self.kernel.failure = 'lease_replaced'
        result = self.run_inspection()
        self.assertEqual('review_required',result['state']); self.assertEqual('unconfirmed',result['cleanup'])
        self.assertTrue(self.kernel.owned); self.assertEqual('other-controller',self.kernel.token)
        self.assertEqual(1,self.kernel.calls.count('swipe'))

    def test_stream_change_or_pause_stops_without_extra_movement(self):
        for failure in ('stream_changed','paused'):
            with self.subTest(failure=failure):
                self.kernel = EditorKernel(self.assets); self.kernel.failure = failure
                self.spec['id'] = str(uuid.uuid4()); result = self.run_inspection()
                self.assertEqual('review_required',result['state']); self.assertEqual(1,self.kernel.calls.count('swipe'))
                self.assertEqual('confirmed',result['cleanup'])

    def test_wrong_slide_and_repeated_frame_are_not_accepted(self):
        for flag in ('bad_media','repeat'):
            with self.subTest(flag=flag):
                self.kernel = EditorKernel(self.assets); setattr(self.kernel,flag,True)
                self.spec['id'] = str(uuid.uuid4()); result = self.run_inspection()
                self.assertEqual('review_required',result['state']); self.assertEqual(1,len(result['slides']))
                self.assertEqual('confirmed',result['cleanup'])

    def test_permission_prompt_prevents_input(self):
        self.ocr.interrupted = True
        result = self.run_inspection(); self.assertEqual('review_required',result['state']); self.assertEqual([],self.kernel.calls)

    def test_slow_recognition_refuses_stale_evidence(self):
        original = self.ocr.read
        def slow(raw): self.now[0] += 2; return original(raw)
        with patch.object(self.ocr,'read',side_effect=slow): result = self.run_inspection()
        self.assertIn('paired',result['reason']); self.assertEqual([],self.kernel.calls)

    def test_request_cannot_inject_targets_commands_or_owned_proof(self):
        for change in ({'device_id':'C241'},{'platform':'x'},{'fun':'/mouse/click'},
                       {'ownershipEvidence':{'authenticatedBeforeAndAfter':True}}, {'revision':True}):
            with self.subTest(change=change), self.assertRaises(ValueError): self.store.run({**self.spec,**change},self.kernel)
        self.assertEqual([],self.kernel.calls)

    def test_duplicate_request_with_different_account_is_refused(self):
        self.run_inspection()
        with self.assertRaises(DraftConflict): self.store.run({**self.spec,'account':'other.account'},self.kernel)

    def test_uncertain_durable_record_is_never_resumed(self):
        result = self.run_inspection()
        result.update(state='running',cleanup='unconfirmed')
        self.store.save(result); calls = list(self.kernel.calls)
        restart = CarouselInspections(self.store.path,self.observations,self.drafts)
        reread = restart.run(self.spec,self.kernel)
        self.assertEqual('review_required',reread['state']); self.assertEqual(calls,self.kernel.calls)

    def test_tampered_retained_frame_is_rejected(self):
        result = self.run_inspection(); observation = result['slides'][0]['observationId']
        with self.store.connect() as db: db.execute('UPDATE frames SET frame=? WHERE observation_id=?',(b'changed',observation))
        with self.assertRaisesRegex(ValueError,'damaged'): self.store.frame(result['id'],observation)

    def test_budget_expires_during_owned_capture_and_still_releases(self):
        original = self.ocr.read
        def slow(raw):
            if self.kernel.owned: self.now[0] += 91
            return original(raw)
        with patch.object(self.ocr,'read',side_effect=slow): result = self.run_inspection()
        self.assertEqual('review_required',result['state']); self.assertEqual('confirmed',result['cleanup'])
        self.assertNotIn('swipe',self.kernel.calls)

    def test_lease_replacement_during_capture_cannot_be_mislabeled_idle(self):
        original = self.ocr.read
        def replace(raw):
            if self.kernel.owned: self.kernel.token = 'other-controller'; self.kernel.generation += 1
            return original(raw)
        with patch.object(self.ocr,'read',side_effect=replace): result = self.run_inspection()
        self.assertEqual('review_required',result['state']); self.assertEqual('unconfirmed',result['cleanup'])
        self.assertNotIn('swipe',self.kernel.calls); self.assertEqual([],result['slides'])

    def test_action_is_journalled_before_transport_and_route_cancel_remains_available(self):
        original = self.kernel.send
        def inspect_then_cancel(*args,**kwargs):
            with self.store.connect() as db: record=json.loads(db.execute('SELECT document FROM inspections').fetchone()[0])
            self.assertEqual('outcome_unknown',record['actions'][0]['state'])
            self.assertTrue(self.store.cancel(self.spec['id'])['cancellationRequested'])
            return original(*args,**kwargs)
        with patch.object(self.kernel,'send',side_effect=inspect_then_cancel): result=self.run_inspection()
        self.assertEqual('review_required',result['state']); self.assertEqual('confirmed',result['cleanup'])
        self.assertFalse(self.store.cancel(self.spec['id'])['cancellationRequested'])

    def test_real_adapter_serializes_single_phone_token_for_renew_send_and_release(self):
        from imouse_social_automation import IMouseKernel
        peer=self.kernel; requests=[]
        def transport(method,url,body,timeout):
            if method=='GET':
                if url.endswith('/kernel/status'): response=peer.kernel_status()
                else: return peer.shot('C24C')
            else:
                fun,data=body['fun'],body['data']; requests.append((fun,data))
                if fun=='/input/status': response=dict(code=0,phones=[dict(id=k,**v) for k,v in peer.input_status().items()])
                elif fun=='/input/acquire':
                    tokens=peer.acquire([data['id']],data['lease_ms'])
                    response=dict(code=0,leases=[dict(id=k,token=v) for k,v in tokens.items()])
                elif fun=='/input/renew':
                    peer.renew_if_needed(data['tokens'],1_000_000); response=dict(code=0)
                elif fun=='/input/release': peer.release(data['tokens']); response=dict(code=0)
                else: response=peer.send(data['id'],data['token'],fun,**{k:v for k,v in data.items() if k not in ('id','token')})
            return json.dumps(dict(data=response)).encode(),{}
        self.kernel=IMouseKernel(transport=transport)
        result=self.run_inspection(); self.assertEqual('visual_match',result['state'],result)
        self.assertEqual({'/input/status','/input/acquire','/input/renew','/input/release','/mouse/swipe'},{fun for fun,_ in requests})
        for fun,data in requests:
            if fun!='/input/status': self.assertEqual('C24C',data['id'])


if __name__ == '__main__': unittest.main()
