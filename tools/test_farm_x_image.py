"""X image route: recognizers, workflow guards and runs admission against fakes. No phone or real socket.

Synthetic frames are labelled as such: a package image pasted where the A17 transfer page, Safari's image
menu and the X composer show it (positions read from 4 Nov slot 17 frames, which stay in the private run
folders), with OCR rows written by hand. Retained 17 Oct C24C frames from the main folder are used where
present (the X image route, steps 36-42) and skipped otherwise. This tests the protocol and recognizers on
known layouts. It is not fresh-phone acceptance.
"""
import io
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid
import zipfile
from unittest.mock import MagicMock, patch

from PIL import Image, ImageDraw, ImageFilter

import farm_test_network  # noqa: F401  Refuse every real socket in this process.
import farm_paths
import farm_reel_runs
from farm_owned_capture import InspectionStopped
from farm_jobs import FarmJobs
import farm_x_image_creation as xic
import farm_x_image_layout as xil
import farm_x_layout as xl
from farm_x_runs import XImageCreationRuns
from test_farm_image import BOARD, CONFIG, PHONE, FakeImageVerification, FakeImageWorkflow, source_image, stage

R17 = farm_paths.MAIN/'analysis/farm-platform-drafts-20261017'
CAROUSEL = farm_paths.MAIN/'analysis/farm-phone-transfer-20261017/test-carousel.zip'
RETAINED = R17.exists() and CAROUSEL.exists()
PACKAGE = 'imouse-xi-duwmtk'
PAGE_BG = (244, 247, 252)


def png(image):
    out = io.BytesIO(); image.save(out, 'PNG'); return out.getvalue()


def line(text, x, y, width=None, height=18):
    words, cursor = [], x
    for part in text.split(' '):
        w = max(8, round((width or len(text)*9) * len(part)/max(1, len(text))))
        words.append(dict(text=part, x=cursor, y=y, width=w, height=height)); cursor += w + 6
    return dict(text=text, words=words)


def centre_of(text, label):
    words = next(r['words'] for r in text['lines'] if r['text'] == label)
    return (round((min(w['x'] for w in words)+max(w['x']+w['width'] for w in words))/2),
            round((min(w['y'] for w in words)+max(w['y']+w['height'] for w in words))/2))


def ocr(*rows):
    return dict(width=500, height=1080, lines=[line(*row) for row in rows])


def package_image(index):
    """A normalized x_image slide (1080x1350 JPEG) made from the shared test source pattern."""
    from farm_image import normalize_image
    return normalize_image(source_image(index), 'x_image')[0]


def pasted(base, raw, box):
    with Image.open(io.BytesIO(raw)) as image:
        base.paste(image.convert('RGB').resize((box[2]-box[0], box[3]-box[1]), Image.Resampling.LANCZOS), box[:2])
    return base


class Images:
    one, two = package_image(1), package_image(2)
    ref, other = xil.XImageReference([one]), xil.XImageReference([two])


def slide_frame(raw, top=230):
    page = pasted(Image.new('RGB', (500, 1080), PAGE_BG), raw, (23, top, 477, top+xil.SLIDE_HEIGHT))
    return png(page), ocr(('Slide 1 of 1', 23, 88, 140, 26), ('Touch and hold the image, then choose Save to', 23, 145, 430),
                         ('Photos. Verify it in Photos before selecting it in X.', 23, 175, 445), ('Back to caption', 180, 834, 140))


def menu_frame(raw, rows=None):
    page = Image.new('RGB', (500, 1080), (150, 150, 155)).filter(ImageFilter.BLUR)
    page = pasted(page, raw, (25, 110, 475, 110+xil.PREVIEW_HEIGHT))
    ImageDraw.Draw(page).rounded_rectangle((100, 697, 400, 1015), 12, fill=(235, 235, 240))
    rows = rows or [('Share...', 119, 716, 70), ('Save to Photos', 119, 769, 137), ('Copy', 119, 822, 45),
                    ('Copy Subject', 119, 875, 115), ('Look Up', 119, 928, 75), ('Show Text', 119, 981, 93)]
    return png(page), ocr(*rows)


def composer_frame(raw, *, callout=True, alt=False):
    image = Image.new('RGB', (500, 1080), 'white')
    image = pasted(image, raw, (xil.CARD_LEFT, xil.CARD_TOP, xil.CARD_LEFT+xil.CARD_WIDTH, xil.CARD_TOP+xil.CARD_HEIGHT))
    draw = ImageDraw.Draw(image)
    draw.ellipse((445, 182, 473, 210), fill='black')                       # remove x
    for left, right in ((208, 303), (314, 421), (432, 477)): draw.rounded_rectangle((left, 648, right, 688), 18, fill=(30, 30, 30))
    if callout: draw.rounded_rectangle((262, 596, 472, 640), 6, fill=(29, 155, 240))   # 'Make Video with Grok'
    if alt: draw.rounded_rectangle((40, 573, 492, 640), 6, fill=(29, 155, 240))        # 'Describe this image ...'
    draw.rounded_rectangle((402, 64, 474, 104), 20, fill=(29, 155, 240))   # Post
    rows = [('Cancel', 13, 76, 63), ('O Fresh x image acceptance', 25, 125, 304), ('Post', 422, 78, 33), ('Tag people', 104, 710, 77),
            ('Everyone can reply', 50, 941, 144)]
    if callout: rows.append(('Make Video with Grok', 275, 609, 185))
    return png(image), ocr(*rows)


class TransferPageTests(unittest.TestCase):
    def index(self, *extra, order=None):
        rows = [('X image draft', 23, 88, 180, 26), ('Draft only · nothing published', 23, 145, 270), ('Package ' + PACKAGE, 23, 195, 255),
                ('1. Save the image', 23, 258, 195), ('Open slide 1 of 1', 175, 325, 150), ('2. Copy the caption', 23, 405, 218),
                ('Fresh x image acceptance', 39, 470, 227), ('Copy caption', 43, 676, 120), ('3. Save in X', 23, 757, 128)]
        if order: rows = [rows[i] for i in order]
        return ocr(*rows, *extra)

    def test_index_targets_open_and_copy_in_page_order(self):
        text = self.index(); found = xil.transfer_index(text, PACKAGE)
        self.assertEqual(centre_of(text, 'Open slide 1 of 1'), found['openTarget'])
        self.assertEqual(centre_of(text, 'Copy caption'), found['copyTarget'])

    def test_index_refuses_other_packages_more_slides_or_a_changed_order(self):
        with self.assertRaises(InspectionStopped): xil.transfer_index(self.index(), 'imouse-xi-aaaaaa')
        with self.assertRaises(InspectionStopped): xil.transfer_index(self.index(('Open slide 2 of 2', 175, 400, 150)), PACKAGE)
        moved = self.index(); moved['lines'][7] = line('Copy caption', 43, 150, 120)
        with self.assertRaises(InspectionStopped): xil.transfer_index(moved, PACKAGE)

    def test_a_copy_click_taken_as_a_hold_shows_the_selection_menu_and_is_dismissed_beside_the_button(self):
        # A17, 4 Nov prep 13: the click selected 'caption' and Safari showed Copy / Find Selection / Look Up.
        menu = (('Copy', 55, 624, 40), ('Find Selection', 137, 623, 120), ('Look Up', 292, 623, 70))
        found = xil.copy_selection(self.index(*menu), PACKAGE)
        copy = centre_of(self.index(), 'Copy caption')
        self.assertEqual(copy, found['copyTarget']); self.assertEqual((430, copy[1]), found['dismissTarget'])
        with self.assertRaises(InspectionStopped): xil.copy_selection(self.index(), PACKAGE)              # No menu.
        with self.assertRaises(InspectionStopped):                                                           # Already copied.
            xil.copy_selection(self.index(*menu, ('Caption copied. Verify the pasted text in X.', 23, 740, 390)), PACKAGE)
        with self.assertRaises(InspectionStopped): xil.copy_selection(self.index(('Copy', 55, 300, 40), ('Look Up', 292, 300, 70)), PACKAGE)
        source = Path(xic.__file__).read_text(encoding='utf-8')
        self.assertEqual(1, source.count("self.tap('copy-caption-again'")); self.assertEqual(1, source.count("self.tap('dismiss-text-selection'"))

    def test_copied_page_may_have_scrolled_past_the_title(self):
        # Focusing the caption box scrolls the page by about 54 px (slot 17, 4 Nov): the title is gone.
        text = ocr(('Draft only · nothing published', 23, 90, 270), ('Package ' + PACKAGE, 23, 141, 255), ('Open slide 1 of 1', 175, 273, 150),
                   ('Copy caption', 43, 623, 120), ('Caption copied. Verify the pasted text in X.', 23, 690, 390))
        self.assertTrue(xil.caption_copied(text, PACKAGE)['copied'])
        unconfirmed = ocr(('Package ' + PACKAGE, 23, 141, 255), ('Copy caption', 43, 623, 120))
        with self.assertRaises(InspectionStopped): xil.caption_copied(unconfirmed, PACKAGE)

    def test_slide_is_found_wherever_the_paragraph_leaves_it(self):
        for top in (214, 230, 262):
            frame, text = slide_frame(Images.one, top)
            found = xil.transfer_slide(frame, text, Images.ref)
            self.assertTrue(found['image']['matched']); self.assertLessEqual(abs(found['image']['box'][1]-top), 2)
            self.assertEqual(centre_of(text, 'Back to caption'), found['backTarget'])
            x, y = found['holdTarget']; self.assertTrue(23 < x < 477 and top < y < top+xil.SLIDE_HEIGHT)

    def test_slide_with_another_image_stops(self):
        frame, text = slide_frame(Images.two)
        with self.assertRaises(InspectionStopped): xil.transfer_slide(frame, text, Images.ref)

    def test_save_menu_targets_save_to_photos_only(self):
        frame, text = menu_frame(Images.one)
        found = xil.save_menu(frame, text, Images.ref)
        self.assertEqual(centre_of(text, 'Save to Photos'), found['target']); self.assertTrue(found['preview']['matched'])

    def test_save_menu_refuses_other_images_close_share_and_another_order(self):
        frame, text = menu_frame(Images.two)
        with self.assertRaises(InspectionStopped): xil.save_menu(frame, text, Images.ref)
        close = [('Share...', 119, 750, 70), ('Save to Photos', 119, 769, 137), ('Copy', 119, 822, 45)]
        frame, text = menu_frame(Images.one, close)
        with self.assertRaises(InspectionStopped): xil.save_menu(frame, text, Images.ref)
        swapped = [('Copy', 119, 716, 45), ('Save to Photos', 119, 769, 137), ('Share...', 119, 822, 70)]
        frame, text = menu_frame(Images.one, swapped)
        with self.assertRaises(InspectionStopped): xil.save_menu(frame, text, Images.ref)


class ComposerTests(unittest.TestCase):
    def test_composer_card_matches_under_the_grok_callout(self):
        frame, text = composer_frame(Images.one)
        found = xil.composer_image(frame, text, Images.ref)
        self.assertTrue(found['media']['matched']); self.assertEqual((57, 85), found['cancelTarget'])
        for kwargs in (dict(callout=False), dict(callout=False, alt=True)):
            frame, text = composer_frame(Images.one, **kwargs)
            self.assertTrue(xil.composer_image(frame, text, Images.ref)['media']['matched'])
        frame, text = composer_frame(Images.two, callout=False, alt=True)
        with self.assertRaises(InspectionStopped): xil.composer_image(frame, text, Images.ref)

    def test_composer_card_with_another_image_or_no_text_stops(self):
        frame, text = composer_frame(Images.two)
        with self.assertRaises(InspectionStopped): xil.composer_image(frame, text, Images.ref)
        frame, text = composer_frame(Images.one)
        text['lines'][1] = line("O What's happening?", 25, 125, 210)
        with self.assertRaises(InspectionStopped): xil.composer_image(frame, text, Images.ref)

    def test_save_sheet_both_layouts_and_discard_never_near(self):
        three = ocr(('Save to drafts', 181, 464, 137), ('Discard', 213, 531, 74), ('Keep editing', 189, 599, 127))
        two = ocr(('Save to drafts', 181, 498, 137), ('Discard', 213, 565, 74))   # Slot 17 since 4 Nov.
        self.assertEqual((centre_of(three, 'Save to drafts'), 'three_rows'), (xl.x_save_sheet(three)['target'], xl.x_save_sheet(three)['layout']))
        self.assertEqual((centre_of(two, 'Save to drafts'), 'two_rows'), (xl.x_save_sheet(two)['target'], xl.x_save_sheet(two)['layout']))
        with self.assertRaises(InspectionStopped): xl.x_save_sheet(ocr(('Save to drafts', 181, 498, 137), ('Discard', 213, 520, 74)))
        with self.assertRaises(InspectionStopped): xl.x_save_sheet(ocr(('Save to drafts', 181, 498, 137)))

    def test_cancel_from_x_13_is_the_composer_not_a_dialog(self):
        frame = png(Image.new('RGB', (500, 1080), 'white'))
        text = ocr(('Cancel', 13, 76, 63), ("O What's happening?", 25, 125, 210), ('Everyone can reply', 50, 941, 144), ('Drafts', 326, 78, 46))
        self.assertEqual((344, 85), xl.x_composer_empty(frame, text)['draftsTarget'])
        text['lines'].append(line('Discard', 213, 565, 74))
        with self.assertRaises(InspectionStopped): xl.x_composer_empty(frame, text)

    def test_drafts_sheet_drawn_lower_on_slot_17(self):
        # 4 Nov: the sheet's tabs sit 14 px lower ('Scheduled' to y 172); the exact-text row with the image decides.
        image = Image.new('RGB', (500, 1080), 'white')
        image = pasted(image, Images.one, (406, 210, 476, 298))
        text = ocr(('Cancel', 26, 96, 61), ('Drafts', 222, 95, 57), ('Drafts', 113, 160, 45), ('Scheduled', 327, 160, 76),
                   ('Fresh x image acceptance', 22, 226, 220))
        with patch.object(xl, 'media_match', lambda *a, **k: dict(matched=True, mean=.01)):
            self.assertEqual(226, xl.x_drafts(png(image), text, Images.ref, 'Fresh x image acceptance')['row']['y'])

    def test_x_top_hit_is_read_from_its_icon(self):
        image = Image.new('RGB', (500, 1080), (40, 60, 110)); draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((47, 125, 127, 203), 16, fill='black')
        draw.line((66, 144, 108, 184), fill='white', width=7); draw.line((108, 144, 66, 184), fill='white', width=4)
        text = ocr(('Top Hit', 25, 76, 61), ('Suggestions', 25, 275, 107))
        self.assertEqual((87, 163), xic.x_top_hit(png(image), text))
        safari = Image.new('RGB', (500, 1080), (40, 60, 110)); ImageDraw.Draw(safari).rounded_rectangle((47, 125, 127, 203), 16, fill=(30, 140, 250))
        with self.assertRaises(InspectionStopped): xic.x_top_hit(png(safari), text)
        with self.assertRaises(InspectionStopped): xic.x_top_hit(png(image), ocr(('Siri Suggestions', 25, 76, 140)))


@unittest.skipUnless(RETAINED, 'Retained 17 Oct C24C frames are in the main folder only.')
class RetainedC24CTests(unittest.TestCase):
    """The 17 Oct X image route (carousel slide 1 as the one image), OCR read at test time."""
    @classmethod
    def setUpClass(cls):
        from farm_observations import WindowsOcr
        with zipfile.ZipFile(CAROUSEL) as archive: cls.slides = [archive.read(n) for n in ('01.jpg', '02.jpg')]
        cls.ref, cls.other = xil.XImageReference(cls.slides[:1]), xil.XImageReference(cls.slides[1:])
        cls.ocr = WindowsOcr()

    def frame(self, step):
        with Image.open(R17/step/'after.png') as image:
            rgb = image.convert('RGB'); raw = png(rgb); bmp = io.BytesIO(); rgb.save(bmp, 'BMP')
        return raw, self.ocr.read(bmp.getvalue())

    def test_composer_picker_and_drafts_tell_the_image_apart(self):
        frame, text = self.frame('38-x-add-image')
        self.assertTrue(xil.composer_image(frame, text, self.ref)['media']['matched'])
        with self.assertRaises(InspectionStopped): xil.composer_image(frame, text, self.other)
        frame, text = self.frame('36-x-picker-loaded')
        self.assertEqual([334, 201, 500, 367], xl.x_picker(frame, text, self.ref)['tile'])
        frame, text = self.frame('42-x-drafts-library')
        self.assertTrue(xl.x_drafts(frame, text, self.ref, 'IMOUSE-DRAFT-TEST-20261017')['row']['match']['matched'])
        with self.assertRaises(InspectionStopped): xl.x_drafts(frame, text, self.other, 'IMOUSE-DRAFT-TEST-20261017')
        frame, text = self.frame('39-x-cancel-to-save')
        self.assertEqual('three_rows', xl.x_save_sheet(text)['layout'])


class PhotosReminderTests(unittest.TestCase):
    """A17's prep 5 (4 Nov) stopped on iOS's full-access reminder; the run now answers it once by one tap."""
    def reminder(self, app='X'):
        import farm_permission_prompts as pp
        rows = [(f'"{app}" has been able to access', 110, 290), ('your entire photo library.', 110, 312),
                ('Do you want to continue to', 110, 334), ('allow full access?', 110, 356),
                ('Limit Access', 120, 760), ('Allow Full Access', 120, 820)]
        return pp.detect(dict(width=500, height=1080, lines=[dict(text=t, words=[dict(text=t, x=x, y=y, width=len(t)*9, height=16)])
                                                              for t, x, y in rows]))

    def test_the_reminder_is_answered_by_one_tap_keeping_the_setting(self):
        import farm_permission_prompts as pp
        found = self.reminder()
        decision = pp.plan(found, app_expected='X', validated=xic.XImageCreationWorkflow.validated_prompt_methods)
        self.assertEqual(('answer', 'Allow Full Access', 'pointer_tap'), (decision['action'], decision['answer'], decision['method']))
        self.assertEqual(found['buttons']['Allow Full Access'], decision['target'])
        self.assertEqual(1, xic.XImageCreationWorkflow.PROMPT_LIMIT)
        self.assertIs(xic.XImageCreationWorkflow.validated_prompt_methods, xic.XImageVerification.validated_prompt_methods)

    def test_only_one_reminder_per_run_and_no_other_prompt(self):
        flow = xic.XImageCreationWorkflow.__new__(xic.XImageCreationWorkflow)
        reminder = dict(kind='photos_reminder', answer='Allow Full Access')
        for actions, decision in (([dict(label='answer-photos-reminder-prompt-1')], reminder),
                                  ([], dict(kind='photos', answer='Allow Full Access')),
                                  ([], dict(kind='photos_reminder', answer='Limit Access'))):
            with self.subTest(decision=decision, actions=actions),                     patch('farm_reel_creation.ReelCreationWorkflow.answer_prompt') as answered, self.assertRaises(InspectionStopped):
                flow.record = dict(actions=actions); flow.answer_prompt(decision, 'xi_page')
            answered.assert_not_called()
        with patch('farm_reel_creation.ReelCreationWorkflow.answer_prompt') as answered:
            flow.record = dict(actions=[]); flow.answer_prompt(reminder, 'xi_page')
            answered.assert_called_once_with(reminder, 'xi_page')


class FakeKernel:
    _is_live_http = False
    phone = MagicMock(board=BOARD, device_id=PHONE['deviceId'])


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='farm-x-image-workflow-'); self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)

    def workflow(self, cls=xic.XImageCreationWorkflow, **kwargs):
        args = dict(transfer_url='http://192.0.2.1:9937/t/x/', package_name=PACKAGE, slides=['01.jpg'], account=None,
                    package_hash='b'*64, allowed=[BOARD]) if cls is xic.XImageCreationWorkflow else dict(account='bound', package_hash='b'*64)
        args.update(kwargs)
        return cls(self.folder, FakeKernel(), MagicMock(), Images.ref, 'Fresh x image acceptance', {}, 'a'*64, 'uid', **args)

    def test_record_names_the_image_route_and_no_video(self):
        record = self.workflow().record
        self.assertEqual(('create_x_image_draft', 'x_image', 'safari_touch_hold_save_to_photos'), (record['mode'], record['format'], record['mediaMethod']))
        self.assertEqual(Images.ref.hashes, record['imageSha256']); self.assertEqual(PACKAGE, record['packageName'])
        self.assertFalse({'videoSha256', 'videoSeconds', 'downloadName'} & set(record))
        self.assertIsNone(record['account'])   # Bound from the side menu at run time.

    def test_one_image_and_a_supported_caption_only(self):
        with self.assertRaises(InspectionStopped): self.workflow(slides=['01.jpg', '02.jpg'])
        with self.assertRaises(InspectionStopped):
            xic.XImageCreationWorkflow(self.folder, FakeKernel(), MagicMock(), xil.XImageReference([Images.one, Images.two]),
                                       'Fresh x image acceptance', {}, 'a'*64, 'uid', transfer_url='u', package_name=PACKAGE,
                                       slides=['01.jpg'], package_hash='b'*64)
        with self.assertRaises(InspectionStopped):
            xic.XImageCreationWorkflow(self.folder, FakeKernel(), MagicMock(), Images.ref, 'x'*33, {}, 'a'*64, 'uid',
                                       transfer_url='u', package_name=PACKAGE, slides=['01.jpg'], package_hash='b'*64)

    def test_verifier_needs_the_bound_account_and_is_read_only(self):
        with self.assertRaises(InspectionStopped): self.workflow(xic.XImageVerification, account=None)
        record = self.workflow(xic.XImageVerification).record
        self.assertEqual(('verify_x_image_draft', True, False), (record['mode'], record['inspectionOnly'], record['reopened']))
        self.assertNotIn('verify-open-saved-draft', Path(xic.__file__).read_text(encoding='utf-8'))

    def test_targets_never_touch_post_remove_card_buttons_or_discard(self):
        flow = self.workflow()
        frame, text = composer_frame(Images.one)
        value = dict(text=text)
        for point in ((438, 84), (459, 196), (360, 668), (300, 615)):
            with self.assertRaises(InspectionStopped): flow.check_target('x_composer_image', point)(value, frame)
        self.assertEqual((57, 85), flow.check_target('x_composer_image', (57, 85))(value, frame))
        sheet = dict(text=ocr(('Save to drafts', 181, 498, 137), ('Discard', 213, 565, 74)))
        save = centre_of(sheet['text'], 'Save to drafts')
        self.assertEqual(save, flow.check_target('x_save_sheet', save)(sheet, frame))
        with self.assertRaises(InspectionStopped): flow.check_target('x_save_sheet', (250, 560))(sheet, frame)
        menu, menu_text = menu_frame(Images.one)
        with self.assertRaises(InspectionStopped): flow.check_target('xi_save_menu', (188, 725))(dict(text=menu_text), menu)

    def test_video_screens_are_not_part_of_this_route(self):
        flow = self.workflow(); flow.check_prompt = lambda role, value: None
        for role in ('x_composer_media', 'x_after_add', 'x_video_editor', 'x_reopened', 'x_playing', 'reel_page'):
            with self.assertRaises(InspectionStopped): flow.verify_screen(role, dict(text=ocr()), b'')

    def test_settling_masks_the_caret_and_the_pointer_only(self):
        frame, text = composer_frame(Images.one)
        with Image.open(io.BytesIO(frame)) as image:
            caret = image.copy(); ImageDraw.Draw(caret).rectangle((330, 128, 333, 152), fill=(29, 155, 240))
            moved = image.copy(); ImageDraw.Draw(moved).rectangle((100, 300, 300, 400), fill='black')
        check = xic.compare('x_composer_image')
        self.assertEqual('ready', check(frame, text, png(caret), None)['state'])
        self.assertEqual('wait', check(frame, text, png(moved), None)['state'])

    def test_an_ignored_open_slide_click_reads_the_unchanged_page_and_is_sent_once_more(self):
        # A17, 4 Nov prep 7: Safari ignored even the settled click; the transfer page stayed.
        flow = self.workflow(); flow.check_prompt = lambda role, value: None
        index = TransferPageTests().index()
        self.assertFalse(flow.verify_screen('xi_after_open', dict(text=index), b'')['opened'])
        frame, text = slide_frame(Images.one)
        self.assertTrue(flow.verify_screen('xi_after_open', dict(text=text), frame)['opened'])
        with self.assertRaises(InspectionStopped): flow.verify_screen('xi_after_open', dict(text=ocr(('Loading', 23, 88, 100))), b'')
        source = Path(xic.__file__).read_text(encoding='utf-8')
        self.assertEqual(1, source.count("self.tap('open-slide-1-again'"))   # One more click, never a loop.
        # Prep 8: 'Back to caption' was ignored the same way; the unchanged slide page gets one more click.
        self.assertFalse(flow.verify_screen('xi_after_back', dict(text=text), frame)['back'])
        self.assertTrue(flow.verify_screen('xi_after_back', dict(text=index), b'')['back'])
        self.assertEqual(1, source.count("self.tap('back-to-caption-again'"))

    def test_committing_prefixes_cover_every_save_and_media_step(self):
        self.assertEqual(('save-photo-', 'select-package-image', 'add-package-image', 'paste-exact-caption', 'save-x-draft-once'), xic.COMMITTING)
        source = Path(xic.__file__).read_text(encoding='utf-8')
        for label in ("'save-photo-1'", "'select-package-image'", "'add-package-image'", "'paste-exact-caption'", "'save-x-draft-once'"):
            self.assertIn(label, source)


class FakeXImageRuns(XImageCreationRuns):
    workflow, verifier = FakeImageWorkflow, FakeImageVerification


class RunsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='farm-x-image-runs-'); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.drafts, self.draft, _ = stage(self.root, 'x_image', 1, caption='Fresh x image acceptance')
        self.jobs = FarmJobs(journal_path=self.root/'jobs.db'); self.addCleanup(self.jobs.close)
        FakeImageWorkflow.calls, FakeImageVerification.calls, FakeImageWorkflow.fetch = [], [], ('01.jpg',)

    def spec(self, service):
        return dict(id=str(uuid.uuid4()), draft_id=self.draft['id'], revision=1, store_id=service.store_id)

    def test_lane_class_capability_and_account_policy(self):
        capability = XImageCreationRuns(self.root/'runs', self.drafts, self.jobs, CONFIG).capability()
        self.assertEqual((True, 'x_image', BOARD, None, 'first_signed_in', False, False),
                         (capability['enabled'], capability['format'], capability['device'], capability['account'],
                          capability['accountPolicy'], capability['publishing'], capability['messaging']))
        self.assertIn('signed in first', capability['reason'])
        self.assertFalse(XImageCreationRuns(self.root/'off', self.drafts, self.jobs).capability()['enabled'])

    def test_supports_one_image_and_one_short_ascii_line(self):
        service = XImageCreationRuns(self.root/'runs', self.drafts, self.jobs, CONFIG)
        self.assertTrue(service.eligibility(self.draft['id'], 1)['eligible'])
        for caption in ('x'*33, 'two  spaces', ' leading'):
            other = self.root/str(uuid.uuid4()); other.mkdir()
            drafts, draft, _ = stage(other, 'x_image', 1, caption=caption)
            self.assertFalse(XImageCreationRuns(other/'runs', drafts, self.jobs, CONFIG).eligibility(draft['id'], 1)['supportedContent'])
        photo = self.root/'photo'; photo.mkdir()
        drafts, draft, _ = stage(photo, 'tt_photo', 2, caption='Fresh x image acceptance')
        self.assertFalse(XImageCreationRuns(photo/'runs', drafts, self.jobs, CONFIG).supports(drafts.export(draft['id'], 1)))

    def test_execute_serves_the_image_then_verifies_on_the_bound_account(self):
        service = FakeXImageRuns(self.root/'runs', self.drafts, self.jobs, CONFIG)
        spec = self.spec(service)
        with patch.object(farm_reel_runs, 'CreationKernel', MagicMock()), patch.object(farm_reel_runs, 'ObservationStore', MagicMock()), \
                patch.object(farm_reel_runs, 'references', lambda: {}):
            service.start(spec)
            end = time.monotonic() + 10
            while not (result := service.get(spec['id']))['terminal'] and time.monotonic() < end: time.sleep(.02)
        self.assertEqual('verified', result['state']); self.assertTrue(result['savedDraftVerified'])
        call = FakeImageWorkflow.calls[0]
        self.assertEqual((['01.jpg'], 'X image draft'), (call['slides'], call['transfer_title']))
        self.assertRegex(call['package_name'], '^imouse-xi-[a-z]{6}$'); self.assertIsNone(call['account'])
        self.assertIsInstance(call['images'], xil.XImageReference); self.assertIn('whole', call['images'].models)
        self.assertEqual('bound-account', FakeImageVerification.calls[0]['account'])
        self.assertEqual({'01.jpg': 1}, result['workflow']['mediaDelivery']['imageRequests'])
        with self.assertRaises(Exception): service.start(dict(spec, id=str(uuid.uuid4())))   # Held: never a second draft.

    def test_retry_only_before_a_photos_save_or_draft_input(self):
        def stopped(*purposes):
            return dict(terminal=True, state='review_required', workflow=dict(source='candidate_phone_workflow', cleanup='confirmed',
                        evidenceExport='confirmed', commands=[dict(purpose=p, state='answered') for p in purposes]))
        self.assertTrue(XImageCreationRuns.retry_allowed(stopped('home-from-x-feed', 'open-slide-1', 'image-menu-1-press')))
        for committed in ('save-photo-1', 'save-photo-1-position', 'select-package-image', 'paste-exact-caption', 'save-x-draft-once'):
            self.assertFalse(XImageCreationRuns.retry_allowed(stopped('home-from-x-feed', committed)))


if __name__ == '__main__':
    unittest.main()
