import copy
import io
import json
import unittest
import uuid
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw
from farm_draft_media import media_comparison, carousel_position
from farm_observations import classify
from test_farm_observations import ocr_lines


class CarouselContinuityTests(unittest.TestCase):
    def setUp(self):
        from test_farm_draft_verification import VerificationTests
        self.f=VerificationTests(); self.f.setUp(); self.addCleanup(self.f.doCleanups)

    @staticmethod
    def png(image):
        data=io.BytesIO(); image.save(data,'PNG'); return data.getvalue()

    def library(self, index=0, shaded=True):
        with Image.open(io.BytesIO(self.f.assets[index])) as source:
            source=source.convert('RGB').crop((0,135,1080,1215)).resize((124,124),Image.Resampling.LANCZOS)
        pixels=np.asarray(source,dtype=float)
        if shaded:
            alpha=1-.70*(np.maximum(0,np.linspace(0,1,124)-.30)/.70)**2
            pixels*=alpha[:,None,None]
        image=Image.new('RGB',(500,1080),'black')
        image.paste(Image.fromarray(pixels.astype('uint8')),(0,111))
        ImageDraw.Draw(image).rounded_rectangle((10,205,25,220),radius=3,fill='white')
        return image

    def test_library_overlay_and_plain_thumbnail_match_without_relaxed_thresholds(self):
        for shade in (False,True):
            result=media_comparison(self.png(self.library(shaded=shade)),self.f.assets,'draft_library_candidate')
            self.assertEqual(1,result['matchedIndex'],result)
            self.assertLessEqual(result['scores'][0]['meanError'],.045)
            self.assertLessEqual(result['scores'][0]['worstBlock'],.12)
            self.assertFalse(result['fullImageVisible'])
        self.assertIsNone(media_comparison(self.png(self.library(1)),self.f.assets,'draft_library_candidate')['matchedIndex'])

    def test_library_cover_can_move_but_duplicate_matching_covers_are_ambiguous(self):
        image=self.library(); tile=image.crop((0,111,124,235))
        image.paste('black',(0,111,124,235)); image.paste(tile,(250,361))
        result=media_comparison(self.png(image),self.f.assets,'draft_library_candidate')
        self.assertEqual(1,result['matchedIndex'])
        self.assertEqual(dict(row=3,column=3),result['libraryCell'])
        image.paste(tile,(125,111))
        result=media_comparison(self.png(image),self.f.assets,'draft_library_candidate')
        self.assertEqual('ambiguous_library',result['status']); self.assertIsNone(result['matchedIndex'])

    def test_library_scan_decodes_each_source_once_and_keeps_no_cross_frame_cache(self):
        image=self.library(); tile=image.crop((0,111,124,235)); image.paste(tile,(250,361))
        raw=self.png(image)
        with patch('farm_draft_media.Image.open',wraps=Image.open) as opened:
            result=media_comparison(raw,self.f.assets,'draft_library_candidate')
        self.assertEqual('ambiguous_library',result['status'])
        self.assertLessEqual(opened.call_count,2+len(self.f.assets))
        image.paste('black',(0,111,124,235))
        changed=media_comparison(self.png(image),self.f.assets,'draft_library_candidate')
        self.assertEqual(1,changed['matchingCovers']); self.assertEqual(dict(row=3,column=3),changed['libraryCell'])
        wrong=media_comparison(self.png(image),[self.f.assets[1],self.f.assets[1]],'draft_library_candidate')
        self.assertIsNone(wrong['matchedIndex'])

    def test_library_occlusion_wrong_content_and_lookalikes_do_not_pass(self):
        image=self.library(); ImageDraw.Draw(image).rectangle((35,135,100,193),fill='red')
        self.assertIsNone(media_comparison(self.png(image),self.f.assets,'draft_library_candidate')['matchedIndex'])
        self.assertIsNone(media_comparison(self.png(self.library()),[self.f.assets[0]]*2,'draft_library_candidate')['matchedIndex'])
        image=self.library(); image.paste(image.crop((0,111,124,235)).rotate(90),(0,111))
        self.assertIsNone(media_comparison(self.png(image),self.f.assets,'draft_library_candidate')['matchedIndex'])

    def test_page_position_requires_one_active_dot_and_expected_count(self):
        key=self.f.spec['observations']['reopened'][0]; value,frame=self.f.captures[key]
        self.assertEqual(dict(status='visible_position',index=1,count=2),carousel_position(frame))
        image=Image.open(io.BytesIO(frame)).convert('RGB'); draw=ImageDraw.Draw(image)
        draw.ellipse((253,836,259,842),fill='white')
        self.assertEqual('ambiguous',carousel_position(self.png(image))['status'])
        draw.rectangle((180,830,320,849),fill='black')
        for i,x in enumerate((238,250,262)): draw.ellipse((x-3,836,x+3,842),fill='white' if i==0 else '#555555')
        self.f.captures[key]=(value,self.png(image))
        self.assertFalse(self.f.evaluate()['slideCoverage']['reopened']['fullSizeAndPositionMatch'])

    def test_repeated_image_under_another_dot_is_not_a_second_slide(self):
        first,second=self.f.spec['observations']['reopened'][:2]
        value,frame=self.f.captures[first]; image=Image.open(io.BytesIO(frame)).convert('RGB'); draw=ImageDraw.Draw(image)
        draw.ellipse((241,836,247,842),fill='#555555'); draw.ellipse((253,836,259,842),fill='white')
        self.f.captures[second]=(self.f.captures[second][0],self.png(image))
        self.assertFalse(self.f.evaluate()['slideCoverage']['reopened']['fullSizeAndPositionMatch'])

    def test_editor_recognition_requires_toolbar_and_next_outside_media(self):
        text=self.f.row('reopened')['text']; expected={**self.f.spec,'caption':self.f.draft['caption']}
        self.assertEqual('carousel_editor',classify(text,expected)['layout'])
        missing=copy.deepcopy(text); missing['lines']=missing['lines'][:-1]
        self.assertNotEqual('carousel_editor',classify(missing,expected)['layout'])
        overlay=copy.deepcopy(text); overlay['lines']+=ocr_lines(("Don't Allow",640),('Allow',690))['lines']
        self.assertEqual('permission_prompt',classify(overlay,expected)['screen'])

    def insert_history(self, text=None, failed=False, pruned=False):
        f=self.f
        records=list(f.captures.values()); before=records[1][0]; after=records[2][0]
        value=copy.deepcopy(records[0][0]); frame=records[0][1]; value['id']=str(uuid.uuid4())
        value.update(requestedAt=before['completedAt']+.1, completedAt=after['requestedAt']-.1)
        value['frameEvidence']['sequence']=before['frameEvidence']['sequence']+1
        if text: value['text']=text
        if failed: value['state']='failed'
        records.insert(2,(value,None if pruned else frame))
        with f.observations.connect() as db:
            db.execute('DELETE FROM observations')
            for v,b in records: db.execute('INSERT INTO observations VALUES (?,?,?,?)',(v['id'],'',json.dumps(v),b))
        return value['id']

    def test_unselected_account_switch_cannot_be_hidden_by_matching_boundaries(self):
        text=copy.deepcopy(self.f.row('account_before')['text']); text['lines'][0]['text']='another.account'
        hidden=self.insert_history(text)
        review=self.f.reviews.create(self.f.spec)
        history=review['assessment']['accountHistory']
        self.assertEqual('incomplete',history['status'])
        self.assertTrue(any('different or unreadable account' in b for b in history['blockers']))
        self.assertIn(hidden,review['intervalObservationIds'])
        with self.f.observations.connect() as db: db.execute('DELETE FROM observations')
        self.assertTrue(self.f.reviews.frame(review['id'],hidden))

    def test_unselected_permission_and_unknown_screen_break_sampled_history(self):
        for text in (ocr_lines(("Don't Allow",640),('Allow',690)),ocr_lines(('Unknown',80))):
            with self.subTest(text=text):
                self.insert_history(text)
                review=self.f.reviews.create({**self.f.spec,'id':str(uuid.uuid4())})
                self.assertTrue(any('unrecognized' in b for b in review['assessment']['accountHistory']['blockers']))

    def test_unselected_failed_or_pruned_observation_breaks_history(self):
        for options in ({'failed':True},{'pruned':True}):
            self.insert_history(**options)
            review=self.f.reviews.create({**self.f.spec,'id':str(uuid.uuid4())})
            self.assertTrue(any('failed, pruned' in b for b in review['assessment']['accountHistory']['blockers']))

    def test_long_gap_and_unwitnessed_ownership_change_do_not_prove_continuity(self):
        records=list(self.f.captures.values())
        for value,_ in records[2:]: value['requestedAt']+=30; value['completedAt']+=30
        result=self.f.evaluate()
        self.assertTrue(any('15 seconds' in b for b in result['accountHistory']['blockers']))
        self.assertFalse(result['accountContinuityProven'])
        self.f.row('reopened')['inputGeneration']+=1
        self.assertTrue(any('ownership generation' in b for b in self.f.evaluate()['accountHistory']['blockers']))

    def test_consistent_samples_are_explicitly_not_continuous_recording_or_save_proof(self):
        review=self.f.reviews.create(self.f.spec); assessment=review['assessment']
        self.assertEqual('consistent_sampled_history',assessment['accountHistory']['status'])
        self.assertFalse(assessment['accountHistory']['continuousRecording'])
        self.assertTrue(assessment['slideCoverage']['prepared']['fullSizeAndPositionMatch'])
        for key in ('accountContinuityProven','savedDraftVerified','automaticInputAllowed'): self.assertFalse(assessment[key])

    def test_owned_samples_need_authenticated_matching_run_and_generation(self):
        for value,_ in self.f.captures.values():
            value.update(inputIdle=False,inputSettled=True,ownershipEvidence=dict(source='owned_capture_guard',
                authenticatedBeforeAndAfter=True,runId='one-run',generation=value['inputGeneration']))
        result=self.f.evaluate()
        self.assertEqual('consistent_sampled_history',result['accountHistory']['status'])
        self.assertFalse(result['accountContinuityProven'])
        self.f.row('reopened')['ownershipEvidence']['runId']='other-run'
        self.assertEqual('incomplete',self.f.evaluate()['accountHistory']['status'])
        self.f.row('reopened')['ownershipEvidence'].update(runId='one-run',authenticatedBeforeAndAfter=False)
        self.assertEqual('incomplete',self.f.evaluate()['accountHistory']['status'])


if __name__=='__main__': unittest.main()
