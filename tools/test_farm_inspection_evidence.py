"""Action decisions must use the current, retained frame; no rack access."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
import uuid
from unittest.mock import patch

from farm_observations import WindowsOcr

class InspectionEvidenceTests(unittest.TestCase):
    def setUp(self):
        from test_farm_carousel_inspection import InspectionTests
        self.fixture = InspectionTests(); self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_new_permission_before_swipe_is_seen_before_any_input(self):
        f = self.fixture; original = f.ocr.read; calls = []
        def change_screen(raw):
            calls.append(1)
            # First: unowned preflight; second: first owned slide.
            # The next screenshot now shows a newly arrived permission dialog.
            if len(calls) >= 3: f.ocr.interrupted = True
            return original(raw)
        with patch.object(f.ocr, 'read', side_effect=change_screen): result = f.run_inspection()
        self.assertEqual('review_required', result['state'])
        self.assertNotIn('swipe', f.kernel.calls)
        self.assertEqual('confirmed', result['cleanup'])

    def test_saved_result_rejects_damaged_evidence_without_waiting_for_image_request(self):
        f = self.fixture; result = f.run_inspection()
        with f.store.connect() as db:
            db.execute('UPDATE frames SET frame=? WHERE observation_id=?',
                       (b'damaged', result['slides'][0]['observationId']))
        with self.assertRaisesRegex(ValueError, 'damaged'): f.store.get(result['id'])

    def test_action_names_the_fresh_guard_frame_and_its_matching_slide(self):
        f=self.fixture; result=f.run_inspection(); action=result['actions'][0]
        self.assertEqual('visual_match',result['state']); self.assertEqual('answered',action['state'])
        observation_id=action['basis']['observationId']
        self.assertNotIn(observation_id,[slide['observationId'] for slide in result['slides']])
        self.assertEqual('before_swipe',result['captureRoles'][observation_id])
        self.assertEqual(1,result['captureChecks'][observation_id]['comparison']['matchedIndex'])
        current,frame=f.observations.current_evidence(observation_id)
        self.assertEqual(current['evidenceRecordSha256'],action['basis']['recordSha256'])
        self.assertEqual(hashlib.sha256(frame).hexdigest(),action['basis']['frameSha256'])
        self.assertEqual(result['id'],action['basis']['runId'])
        self.assertGreater(action['basis']['frameSequence'],result['slides'][0]['sequence'])

    def test_wrong_media_appearing_before_movement_stops_without_sending(self):
        f=self.fixture; original=f.kernel.shot; calls=[]
        def changed(phone):
            calls.append(1)
            if len(calls)==3: f.kernel.index=1
            return original(phone)
        with patch.object(f.kernel,'shot',side_effect=changed): result=f.run_inspection()
        self.assertEqual('review_required',result['state']); self.assertNotIn('swipe',f.kernel.calls)
        self.assertEqual('confirmed',result['cleanup'])

    def test_frame_expiring_while_intent_is_journalled_is_not_sent(self):
        f=self.fixture; original=f.store.save; changed=[]
        def delayed(record):
            original(record)
            if record['actions'] and record['actions'][-1]['state']=='outcome_unknown' and not changed:
                changed.append(True); f.now[0]+=2
        with patch.object(f.store,'save',side_effect=delayed): result=f.run_inspection()
        self.assertEqual('not_sent',result['actions'][0]['state'])
        self.assertEqual('review_required',result['state']); self.assertNotIn('swipe',f.kernel.calls)
        self.assertEqual('confirmed',result['cleanup'])

    def test_cancel_after_journalling_but_before_transport_is_not_sent(self):
        f=self.fixture; original=f.store.save
        def cancel(record):
            original(record)
            if record['actions'] and record['actions'][-1]['state']=='outcome_unknown': f.store.cancel(record['id'])
        with patch.object(f.store,'save',side_effect=cancel): result=f.run_inspection()
        self.assertEqual('not_sent',result['actions'][0]['state']); self.assertNotIn('swipe',f.kernel.calls)
        self.assertEqual('confirmed',result['cleanup'])

    def test_observation_text_changed_after_decision_cannot_authorize_movement(self):
        f=self.fixture; original=f.store.save; changed=[]
        def mutate(record):
            original(record)
            if record['actions'] and not changed:
                changed.append(True); observation=record['actions'][-1]['basis']['observationId']
                with f.observations.connect() as db:
                    value=json.loads(db.execute('SELECT document FROM observations WHERE id=?',(observation,)).fetchone()[0])
                    value['text']['lines'][0]['text']='A different frame description'
                    db.execute('UPDATE observations SET document=? WHERE id=?',(json.dumps(value),observation))
        with patch.object(f.store,'save',side_effect=mutate): result=f.run_inspection()
        self.assertEqual('not_sent',result['actions'][0]['state']); self.assertNotIn('swipe',f.kernel.calls)
        self.assertEqual('confirmed',result['cleanup'])

    def test_saved_observation_record_tampering_is_rejected_even_with_intact_image(self):
        f=self.fixture; result=f.run_inspection()
        with f.store.connect() as db:
            row=db.execute('SELECT observation_id,document FROM frames LIMIT 1').fetchone()
            value=json.loads(row[1]); value['ownershipEvidence']={'generation':999}
            db.execute('UPDATE frames SET document=? WHERE observation_id=?',(json.dumps(value),row[0]))
        with self.assertRaisesRegex(ValueError,'damaged'): f.store.get(result['id'])

    def test_missing_retained_frame_is_not_a_successful_result(self):
        f=self.fixture; result=f.run_inspection()
        with f.store.connect() as db: db.execute('DELETE FROM frames WHERE observation_id=?',(result['slides'][0]['observationId'],))
        with self.assertRaisesRegex(ValueError,'missing or damaged'): f.store.get(result['id'])

    def test_legacy_result_is_kept_but_cannot_claim_current_acceptance(self):
        f=self.fixture; result=f.run_inspection(); result.pop('inspectionVersion')
        f.store.save(result); legacy=f.store.get(result['id'])
        self.assertEqual('review_required',legacy['state']); self.assertIn('Historical',legacy['reason'])
        self.assertTrue(f.store.frame(result['id'],result['slides'][0]['observationId']))

    def test_capture_rejects_missing_or_wrong_ocr_frame_digest(self):
        f=self.fixture; raw,_=f.kernel.shot('C24C'); text=f.ocr.read(raw)
        for digest in (None,'f'*64):
            candidate=copy.deepcopy(text); candidate['frameSha256']=digest
            f.spec['id']=uuid.uuid4().hex
            with patch.object(f.ocr,'read',return_value=candidate): result=f.run_inspection()
            self.assertEqual('review_required',result['state']); self.assertEqual([],f.kernel.calls)

    def test_real_ocr_bridge_checks_the_image_digest_returned_by_its_process(self):
        f=self.fixture; raw,_=f.kernel.shot('C24C')
        def reply(arguments,**kwargs):
            image_path=Path(arguments[arguments.index('-ImagePath')+1])
            digest=hashlib.sha256(image_path.read_bytes()).hexdigest()
            control_path=Path(arguments[arguments.index('-ControlImagePath')+1])
            value=dict(width=500,height=1080,lines=[],imageSha256=digest,
                control=dict(width=129,height=117,lines=[],imageSha256=hashlib.sha256(control_path.read_bytes()).hexdigest()))
            return subprocess.CompletedProcess(arguments,0,json.dumps(value).encode(),b'')
        with patch('farm_observations.subprocess.run',side_effect=reply) as process: value=WindowsOcr().read(raw)
        self.assertEqual(1,process.call_count)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),value['frameSha256'])
        wrong=dict(width=500,height=1080,lines=[],imageSha256='f'*64)
        with patch('farm_observations.subprocess.run',return_value=subprocess.CompletedProcess([],0,json.dumps(wrong).encode(),b'')):
            with self.assertRaisesRegex(ValueError,'exact submitted image'): WindowsOcr().read(raw)

    def test_ocr_batch_rejects_missing_swapped_or_mis_sized_control(self):
        raw,_=self.fixture.kernel.shot('C24C')
        def reply(arguments,**kwargs):
            image=Path(arguments[arguments.index('-ImagePath')+1]).read_bytes()
            control=Path(arguments[arguments.index('-ControlImagePath')+1]).read_bytes()
            detail=dict(width=129,height=117,lines=[],imageSha256=hashlib.sha256(control).hexdigest())
            if problem=='swapped': detail['imageSha256']=hashlib.sha256(image).hexdigest()
            elif problem=='dimensions': detail['width']=128
            elif problem=='missing': detail=None
            value=dict(width=500,height=1080,lines=[],imageSha256=hashlib.sha256(image).hexdigest(),control=detail)
            return subprocess.CompletedProcess(arguments,0,json.dumps(value).encode(),b'')
        for problem in ('missing','swapped','dimensions'):
            with self.subTest(problem=problem), patch('farm_observations.subprocess.run',side_effect=reply):
                with self.assertRaises(ValueError): WindowsOcr().read(raw)
