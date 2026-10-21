"""Candidate guard regression tests; synthetic frames and an in-memory transport."""
from farm_phone_identity import LEGACY_C24C
import copy
import unittest
import farm_draft_transport as step
from test_farm_screen_layout import screen,changed,crop_proof

class DraftTransportTests(unittest.TestCase):
    def test_details_requires_exact_next_on_the_same_frame_at_the_target(self):
        raw,text=screen('editor')
        with self.assertRaises(step.InspectionStopped): step.allowed_tap(text,438,1006,'details',raw)
        crop_proof(raw,text)
        step.allowed_tap(text,438,1006,'details',raw)
        with self.assertRaises(step.InspectionStopped): step.allowed_tap(text,250,1006,'details',raw)
        with self.assertRaises(step.InspectionStopped):
            step.allowed_tap(text,438,1006,'details',changed(raw,(100,200,200,300),'red'))

    def test_drafts_requires_actual_picker_not_words_on_an_unrelated_page(self):
        raw,text=screen(); step.allowed_tap(text,164,644,'open_drafts',raw)
        with self.assertRaises(step.InspectionStopped):
            step.allowed_tap(text,164,644,'open_drafts',changed(raw,(70,65,180,108),'gray'))

    def test_share_label_blocks_click_even_under_a_different_intent(self):
        raw,text=screen('editor'); crop_proof(raw,text)
        text['lines'].append(dict(text='Share',words=[dict(text='Share',x=410,y=995,width=60,height=20)]))
        with self.assertRaises(step.InspectionStopped): step.allowed_tap(text,438,1006,'details',raw)

    def test_create_sheet_with_edits_row_needs_all_exact_positioned_anchors(self):
        labels=[('Create',219,516,62),('Edits',70,621,41),('post',70,675,37),
                ('Story',69,728,46),('Instants',70,781,67)]
        text=dict(width=500,height=1080,lines=[dict(text=label,words=[
            dict(text=label,x=x,y=y,width=w,height=15)]) for label,x,y,w in labels])
        step.allowed_tap(text,88,681,'choose_post_format')
        for index in (0,1,3,4):
            bad=copy.deepcopy(text); bad['lines'].pop(index)
            with self.subTest(missing=index),self.assertRaises(step.InspectionStopped):
                step.allowed_tap(bad,88,681,'choose_post_format')
        bad=copy.deepcopy(text); bad['lines'][0]['words'][0]['y']=80
        with self.assertRaises(step.InspectionStopped): step.allowed_tap(bad,88,681,'choose_post_format')
        with self.assertRaises(step.InspectionStopped): step.allowed_tap(text,88,681,'details')

    def test_transport_allows_only_candidate_and_c24c_input(self):
        calls=[]
        def transport(*args): calls.append(args); return b'{}',{}
        client=step.StepKernel('http://127.0.0.1:9916/api',transport=transport,phone=LEGACY_C24C)
        address=client.url+'/'
        for fun,pid in (('/mouse/click',LEGACY_C24C.device_id),('/input/release',LEGACY_C24C.device_id)):
            client._transport('POST',address,dict(fun=fun,data=dict(id=pid)),1)
        self.assertEqual(2,len(calls))
        forbidden=[dict(fun='/mouse/click',data=dict(id='C241')),
                   dict(fun='/key/send',data=dict(id=LEGACY_C24C.device_id)),
                   dict(fun='/publish',data=dict(id=LEGACY_C24C.device_id)),
                   dict(fun='/message',data=dict(id=LEGACY_C24C.device_id)),
                   dict(fun='/input/stop',data=dict(id=LEGACY_C24C.device_id))]
        for body in forbidden:
            with self.subTest(body=body),self.assertRaises(step.KernelSafetyError):
                client._transport('POST',address,body,1)
        self.assertEqual(2,len(calls))
        with self.assertRaises(step.KernelSafetyError):
            client._transport('POST','http://127.0.0.1:9913/api/',forbidden[0],1)
        for url in ('http://127.0.0.1:9913/api','http://example.com:9916/api'):
            with self.assertRaises(step.KernelSafetyError): step.StepKernel(url,transport=transport,phone=LEGACY_C24C)
