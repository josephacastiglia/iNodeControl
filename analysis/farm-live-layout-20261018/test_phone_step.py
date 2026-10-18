"""Offline checks for this supervised run; no listener, device or desktop access."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'tools'))
spec=importlib.util.spec_from_file_location('layout_phone_step',HERE/'phone_step.py')
step=importlib.util.module_from_spec(spec); spec.loader.exec_module(step)
from test_farm_screen_layout import screen,changed,crop_proof
from farm_observations import classify


def observation(text,sequence=1):
    return dict(id=f'frame-{sequence}',freshness='recent',stable=True,inputSettled=True,
        receiverPid=123,inputGeneration=7,
        ownershipEvidence=dict(source='owned_capture_guard',runId='this-run',generation=7,
                               authenticatedBeforeAndAfter=True),
        frameEvidence=dict(session='a'*32,sequence=sequence,pairedMetadata=True),text=text)


class RunGuardTests(unittest.TestCase):
    def test_autoplay_pair_uses_production_stability_and_keeps_freshness_separate(self):
        first,text1=screen(preview=(20,40,60)); second,text2=screen(preview=(110,40,60))
        result=step.fresh_pair(observation(text1),first,observation(text2,2),second)
        self.assertTrue(result['controlsStable']); self.assertTrue(result['previewChanged'])
        self.assertTrue(result['freshAtEachCapture']); self.assertFalse(result['automaticInputAllowed'])
        self.assertEqual([[0,0,500,65],[0,112,500,612]],result['ignoredRegions'])

    def test_unknown_picker_never_receives_a_preview_mask(self):
        first,text1=screen(); second,text2=screen(preview=(200,60,90)); text2['lines'].pop()
        with self.assertRaises(step.InspectionStopped):
            step.same_reviewed_page(first,second,before_text=text1,after_text=text2)

    def test_autoplay_cannot_hide_changed_controls_or_library(self):
        raw,text=screen()
        for box in ((160,638,165,644),(135,689,143,697),(100,1050,105,1055)):
            with self.subTest(box=box),self.assertRaises(step.InspectionStopped):
                step.fresh_pair(observation(text),raw,observation(text,2),changed(raw,box,'white'))

    def test_stale_or_unsettled_comparison_does_not_grant_input(self):
        raw,text=screen()
        for key,value in (('freshness','stale'),('stable',False),('inputSettled',False)):
            for index in (0,1):
                pair=[observation(text),observation(text,2)]; pair[index][key]=value
                with self.subTest(key=key,index=index),self.assertRaises(step.InspectionStopped):
                    step.fresh_pair(pair[0],raw,pair[1],raw)

    def test_changed_receiver_lease_stream_or_repeated_frame_holds(self):
        raw,text=screen()
        mutations=[('receiverPid',124),('inputGeneration',8),('frameEvidence.session','b'*32),
                   ('frameEvidence.sequence',1),('frameEvidence.pairedMetadata',False),
                   ('ownershipEvidence.runId','another'),('ownershipEvidence.generation',8),
                   ('ownershipEvidence.authenticatedBeforeAndAfter',False),
                   ('ownershipEvidence.source','untrusted')]
        for path,value in mutations:
            newer=observation(text,2); parts=path.split('.'); container=newer
            for part in parts[:-1]: container=container[part]
            container[parts[-1]]=value
            with self.subTest(path=path),self.assertRaises(step.InspectionStopped):
                step.fresh_pair(observation(text),raw,newer,raw)

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

    def test_manual_editor_override_is_removed(self):
        raw,text=screen('editor')
        with self.assertRaises(step.InspectionStopped):
            step.verified_slide(raw,dict(result=dict(screen='unknown'),text=text))

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
        client=step.StepKernel('http://127.0.0.1:9916/api',transport=transport)
        address=client.url+'/'
        for fun,pid in (('/mouse/click',step.LIVE_TEST_DEVICE_ID),('/input/release',step.LIVE_TEST_DEVICE_ID)):
            client._transport('POST',address,dict(fun=fun,data=dict(id=pid)),1)
        self.assertEqual(2,len(calls))
        forbidden=[dict(fun='/mouse/click',data=dict(id='C241')),
                   dict(fun='/key/send',data=dict(id=step.LIVE_TEST_DEVICE_ID)),
                   dict(fun='/publish',data=dict(id=step.LIVE_TEST_DEVICE_ID)),
                   dict(fun='/message',data=dict(id=step.LIVE_TEST_DEVICE_ID)),
                   dict(fun='/input/stop',data=dict(id=step.LIVE_TEST_DEVICE_ID))]
        for body in forbidden:
            with self.subTest(body=body),self.assertRaises(step.KernelSafetyError):
                client._transport('POST',address,body,1)
        self.assertEqual(2,len(calls))
        with self.assertRaises(step.KernelSafetyError):
            client._transport('POST','http://127.0.0.1:9913/api/',forbidden[0],1)
        for url in ('http://127.0.0.1:9913/api','http://example.com:9916/api'):
            with self.assertRaises(step.KernelSafetyError): step.StepKernel(url,transport=transport)


if __name__=='__main__': unittest.main(verbosity=2)
