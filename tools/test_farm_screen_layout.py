import copy
import hashlib
import io
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw
from farm_observations import WindowsOcr, classify
from farm_screen_layout import NEXT_BOX, NEXT_LABEL_BOX, NEXT_LABEL_SCALE, NEXT_CROP_SIZE, editor_controls, next_crop, next_label, picker_controls, picker_stability


def encoded(image):
    stream=io.BytesIO(); image.save(stream,'PNG'); return stream.getvalue()


def screen(kind='picker', preview=(30,40,90)):
    image=Image.new('RGB',(500,1080),'black'); draw=ImageDraw.Draw(image)
    if kind=='picker':
        draw.rectangle((0,112,499,611),fill=preview)
        draw.rectangle((125,679,248,802),fill='green')
        entries=[('New post',208,78,88),('Next',435,78,44),('Recents',20,637,78),
                 ('Drafts',135,637,58),('Select',417,637,49)]
    else:
        draw.rectangle((0,164,499,788),fill=preview)
        for index,x in enumerate((238,250,262)):
            draw.ellipse((x-3,836,x+3,842),fill='white' if index==0 else '#555555')
        draw.rounded_rectangle((396,980,477,1031),radius=26,fill=(70,83,255))
        entries=[('Audio',42,921,33),('Overlay',190,921,44),('Filter',273,921,30),
                 ('Edit',353,921,23),('Ratio',427,921,29),('ext',422,1001,21),('Suggested',210,102,71)]
    rows=[]
    for label,x,y,width in entries:
        draw.text((x,y),label,fill='white')
        rows.append(dict(text=label,words=[dict(text=label,x=x,y=y,width=width,height=14)]))
    raw=encoded(image)
    return raw,dict(width=500,height=1080,lines=rows,frameSha256=hashlib.sha256(raw).hexdigest())


def changed(raw, box, fill):
    with Image.open(io.BytesIO(raw)) as image:
        draw=ImageDraw.Draw(image); draw.rectangle(box,fill=fill); return encoded(image)


def crop_proof(frame, text, label='Next'):
    crop, source_pixels=next_crop(frame)
    text['controlOcr']={'next': dict(width=NEXT_CROP_SIZE[0],height=NEXT_CROP_SIZE[1],scale=NEXT_LABEL_SCALE,bounds=list(NEXT_LABEL_BOX),
        sourcePixelsSha256=source_pixels,sourceFrameSha256=text['frameSha256'],
        imageSha256=hashlib.sha256(crop).hexdigest(),
        lines=[dict(text=label,words=[dict(text=label,x=40,y=50,width=80,height=30)])])}
    return text


class LayoutTests(unittest.TestCase):
    expected=dict(platform='instagram',account='test.account',caption='Exact caption')

    def test_partial_next_needs_frame_geometry_without_repairing_text(self):
        frame,text=screen('editor'); original=copy.deepcopy(text)
        self.assertEqual('unknown',classify(text,self.expected)['screen'])
        result=classify(text,self.expected,frame)
        self.assertEqual('carousel_editor',result['layout'])
        self.assertEqual('toolbar_button_and_page_dots',result['layoutEvidence']['method'])
        self.assertFalse(result['layoutEvidence']['actionTargetVerified'])
        self.assertEqual('not_visible',result['accountStatus'])
        self.assertEqual('needs_review',result['captionStatus'])
        self.assertFalse(result['automaticInputAllowed']); self.assertFalse(result['savedDraftVerified'])
        self.assertEqual(original,text)

    def test_editor_requires_every_toolbar_word_at_its_own_location(self):
        frame,text=screen('editor')
        for label in ('Audio','Overlay','Filter','Edit','Ratio'):
            with self.subTest(label=label):
                missing=copy.deepcopy(text); missing['lines']=[r for r in missing['lines'] if r['text']!=label]
                self.assertIsNone(editor_controls(frame,missing))
                shifted=copy.deepcopy(text)
                next(r for r in shifted['lines'] if r['text']==label)['words'][0]['x']=20
                self.assertIsNone(editor_controls(frame,shifted))
        duplicate=copy.deepcopy(text); duplicate['lines'].append(copy.deepcopy(text['lines'][0]))
        self.assertIsNone(editor_controls(frame,duplicate))

    def test_editor_blue_rectangle_alone_or_bad_dots_is_insufficient(self):
        frame,text=screen('editor')
        for box,fill in (((396,980,477,1031),(70,83,255)),((396,980,477,1031),'gray'),
                         ((185,835,315,844),'black'),((396,970,477,979),'white')):
            with self.subTest(box=box,fill=fill): self.assertIsNone(editor_controls(changed(frame,box,fill),text))

    def test_overlay_takes_precedence_over_editor_or_picker(self):
        for kind in ('picker','editor'):
            frame,text=screen(kind)
            for label,y in (("Don't Allow",600),('Allow',650)):
                text['lines'].append(dict(text=label,words=[dict(text=label,x=100,y=y,width=90,height=16)]))
            self.assertEqual('permission_prompt',classify(text,self.expected,frame)['screen'])
            self.assertIsNone(picker_controls(frame,text)); self.assertIsNone(editor_controls(frame,text))

    def test_picker_navigation_handles_a_combined_recents_drafts_ocr_line(self):
        frame,text=screen()
        one,two=text['lines'][2:4]
        text['lines'][2:4]=[dict(text='Recents > Drafts',words=one['words']+two['words'])]
        result=classify(text,self.expected,frame)
        self.assertEqual('post_media_picker',result['layout'])
        self.assertFalse(result['automaticInputAllowed'])

    def test_autoplay_motion_does_not_require_static_preview_content(self):
        first,text1=screen(preview=(20,40,60)); second,text2=screen(preview=(110,40,60))
        result=picker_stability(first,text1,second,text2)
        self.assertTrue(result['previewChanged']); self.assertTrue(result['controlsStable'],result)
        self.assertFalse(result['automaticInputAllowed'])
        self.assertEqual([[0,0,500,65],[0,112,500,612]],result['ignoredRegions'])

    def test_control_and_library_changes_are_never_masked_as_preview_motion(self):
        frame,text=screen()
        for box in ((435,80,439,84),(160,638,165,644),(135,689,143,697),(100,1050,105,1055)):
            with self.subTest(box=box):
                result=picker_stability(frame,text,changed(frame,box,'white'),text)
                self.assertFalse(result['controlsStable'],result)

    def test_overlay_dim_and_partly_open_drawer_are_rejected_even_with_old_ocr(self):
        frame,text=screen()
        for box in ((70,65,180,108),(0,612,499,619),(0,666,499,676)):
            self.assertIsNone(picker_controls(changed(frame,box,'gray'),text))
        altered=copy.deepcopy(text); altered['lines'].pop()
        self.assertFalse(picker_stability(frame,text,frame,altered)['controlsStable'])

    def test_duplicate_or_displaced_picker_controls_are_unknown(self):
        frame,text=screen()
        for index in range(len(text['lines'])):
            missing=copy.deepcopy(text); missing['lines'].pop(index)
            self.assertIsNone(picker_controls(frame,missing))
        duplicate=copy.deepcopy(text); duplicate['lines'].append(copy.deepcopy(text['lines'][3]))
        self.assertIsNone(picker_controls(frame,duplicate))
        shifted=copy.deepcopy(text); shifted['lines'][3]['words'][0]['y']=500
        self.assertIsNone(picker_controls(frame,shifted))

    def test_wrong_size_or_blank_frame_cannot_support_ambiguous_ocr(self):
        frame,text=screen('editor')
        self.assertIsNone(editor_controls(encoded(Image.new('RGB',(500,1080))),text))
        with Image.open(io.BytesIO(frame)) as image:
            self.assertIsNone(editor_controls(encoded(image.resize((1000,2160))),text))

    def test_identical_images_do_not_claim_liveness(self):
        frame,text=screen(); result=picker_stability(frame,text,frame,text)
        self.assertTrue(result['controlsStable']); self.assertFalse(result['previewChanged'])
        self.assertFalse(result['automaticInputAllowed'])
        self.assertNotIn('freshness',result)

    def test_cropped_label_is_exact_and_bound_to_the_entire_source_frame(self):
        frame,text=screen('editor'); original=copy.deepcopy(text['lines'])
        crop_proof(frame,text)
        self.assertEqual('same_frame_crop_exact_word',next_label(frame,text)['method'])
        self.assertTrue(editor_controls(frame,text)['actionTargetVerified'])
        self.assertEqual(original,text['lines'])
        # Reusing the same button pixels on another slide is not the same frame.
        self.assertIsNone(next_label(changed(frame,(100,200,200,300),'red'),text))
        for label in ('ext','N ext','Next?','Share',''):
            with self.subTest(label=label):
                self.assertIsNone(next_label(frame,crop_proof(frame,copy.deepcopy(text),label)))

    def test_crop_metadata_mismatch_or_ambiguous_words_cannot_authorize_next(self):
        frame,text=screen('editor'); crop_proof(frame,text)
        for key,value in (('sourceFrameSha256','wrong'),('sourcePixelsSha256','wrong'),
                          ('imageSha256','wrong'),('bounds',[0,0,500,1080]),('scale',2),
                          ('width',247),('height',155)):
            with self.subTest(key=key):
                bad=copy.deepcopy(text); bad['controlOcr']['next'][key]=value
                self.assertIsNone(next_label(frame,bad))
        duplicate=copy.deepcopy(text); detail=duplicate['controlOcr']['next']
        detail['lines'].append(copy.deepcopy(detail['lines'][0]))
        self.assertIsNone(next_label(frame,duplicate))
        outside=copy.deepcopy(text); outside['controlOcr']['next']['lines'][0]['words'][0]['x']=250
        self.assertIsNone(next_label(frame,outside))

    def test_crop_evidence_survives_lossless_bmp_to_png_retention(self):
        frame,text=screen('editor')
        with Image.open(io.BytesIO(frame)) as image:
            stream=io.BytesIO(); image.save(stream,'BMP'); bmp=stream.getvalue()
        text['frameSha256']=hashlib.sha256(bmp).hexdigest(); crop_proof(bmp,text)
        self.assertIsNotNone(next_label(frame,text))

    def test_windows_ocr_uses_one_optional_fixed_crop_without_rewriting_full_text(self):
        frame,text=screen('editor'); calls=[]
        def read(path,size):
            raw=Path(path).read_bytes(); calls.append((raw,size))
            if len(calls)==1: return copy.deepcopy(text)
            detail=crop_proof(frame,copy.deepcopy(text))['controlOcr']['next']
            return {k:v for k,v in detail.items() if k in ('width','height','imageSha256','lines')}
        with patch.object(WindowsOcr,'_read_file',side_effect=read): result=WindowsOcr().read(frame)
        self.assertEqual([(500,1080),NEXT_CROP_SIZE],[size for _,size in calls])
        self.assertEqual(next_crop(frame)[0],calls[1][0])
        self.assertEqual(text['lines'],result['lines'])
        self.assertIsNotNone(next_label(frame,result))

    def test_exact_whole_frame_label_and_unrelated_screens_do_not_start_crop_ocr(self):
        for kind in ('editor','picker'):
            frame,text=screen(kind)
            if kind=='editor':
                row=next(r for r in text['lines'] if r['text']=='ext')
                row['text']=row['words'][0]['text']='Next'
            with patch.object(WindowsOcr,'_read_file',return_value=text) as read:
                result=WindowsOcr().read(frame)
            self.assertEqual(1,read.call_count); self.assertNotIn('controlOcr',result)

    def test_ambiguous_crop_does_not_retry_or_invent_a_label(self):
        frame,text=screen('editor'); bad=crop_proof(frame,copy.deepcopy(text),'ext')['controlOcr']['next']
        with patch.object(WindowsOcr,'_read_file',side_effect=[copy.deepcopy(text),bad]) as read:
            result=WindowsOcr().read(frame)
        self.assertEqual(2,read.call_count); self.assertIsNone(next_label(frame,result))
        self.assertEqual('draft_editor',classify(result,self.expected,frame)['screen'])

    def test_label_crop_excludes_arrow_but_is_bound_to_the_whole_source(self):
        frame,text=screen('editor'); original_crop,_=next_crop(frame)
        arrow_changed=changed(frame,(451,1000,462,1012),'white')
        crop,pixels_hash=next_crop(arrow_changed)
        self.assertEqual(original_crop,crop)
        self.assertEqual((129,117),Image.open(io.BytesIO(crop)).size)
        crop_proof(frame,text)
        self.assertIsNone(next_label(arrow_changed,text))
        self.assertNotEqual(text['controlOcr']['next']['sourcePixelsSha256'],pixels_hash)

    def test_old_full_button_ocr_proof_cannot_authorize_the_new_label_crop(self):
        frame,text=screen('editor'); crop_proof(frame,text)
        text['controlOcr']['next'].update(bounds=list(NEXT_BOX),width=246,height=156)
        self.assertIsNone(next_label(frame,text))


if __name__=='__main__': unittest.main()
