"""YouTube recognizers: synthetic boundary cases always run; retained C24C frames when present.

No phone, socket or desktop access. Retained frames/OCR are private local
artifacts (17 Oct supervised YouTube routes: photo Short 46-66, MP4 Short
131-151). The channel handle is read at run time and never written into this file.
"""
import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw

import farm_permission_prompts as prompts
import farm_reel_test_media as media
import farm_tiktok_layout as tt
import farm_youtube_layout as yl
from farm_owned_capture import InspectionStopped

ROOT = Path(__file__).resolve().parents[1]
R17 = ROOT/'analysis/farm-platform-drafts-20261017'
import farm_paths  # noqa: E402  (the archive beside the main folder, also from a lane worktree)
OCR = farm_paths.ARCHIVE/'20261020-farm-youtube-offline/ocr-20261017'
PRIVATE = (R17/'normalized-test.mp4').exists() and OCR.exists() and (R17/'140-youtube-mp4-trim-review/pointer.png').exists()
TITLE = 'IMOUSE-VIDEO-DRAFT-TEST-20261017'   # The retained MP4 draft's title, 32 characters: longer than the candidate allows.
FIRST = [0, 298, 164, 589]                  # The package video's tile in the retained picker.
BADGE = (118, 296, 166, 348)


def load(step, which='after'):
    text = json.loads((OCR/f'{step}__{which}.json').read_text(encoding='utf-8')); text.pop('source', None)
    return (R17/step/(which+'.png')).read_bytes(), text


def png(image):
    out = io.BytesIO(); image.save(out, 'PNG'); return out.getvalue()


def selected_picker():
    """The selected picker without the supervised pointer: 139/after, whose pointer covers the badge, with the
    badge area of 140/pointer, a frame of the same screen captured after the pointer had moved to Next."""
    frame, text = load('139-youtube-select-mp4')
    with Image.open(io.BytesIO(frame)) as base, Image.open(R17/'140-youtube-mp4-trim-review/pointer.png') as clean:
        image = base.convert('RGB'); image.paste(clean.convert('RGB').crop(BADGE), BADGE[:2])
        return png(image), text


class SyntheticYouTubeLayoutTests(unittest.TestCase):
    def test_unrotate_turns_word_centres_back_about_the_image_centre(self):
        from farm_observations import unrotate
        level = dict(width=500, height=1080, textAngle=0.2, lines=[dict(text='a', words=[dict(text='a', x=10, y=20, width=30, height=10)])])
        unrotate(level); self.assertEqual((10, 20), (level['lines'][0]['words'][0]['x'], level['lines'][0]['words'][0]['y']))
        tilted = dict(width=500, height=1080, textAngle=90, lines=[dict(text='a', words=[dict(text='a', x=345, y=535, width=10, height=10)])])
        unrotate(tilted)   # Centre (350, 540) turned 90 degrees about (250, 540) lands on (250, 640).
        word = tilted['lines'][0]['words'][0]
        self.assertEqual((245, 635), (word['x'], word['y'])); self.assertEqual(90, tilted['unrotated'])

    def test_the_draft_prompt_targets_start_over_centre(self):
        # The OCR of slot 16's prompt (26 Oct): Start over's two words, the second lower and shorter.
        def row(text, *words): return dict(text=text, words=[dict(text=t, x=x, y=y, width=w, height=h) for t, x, y, w, h in words])
        lines = [row('Continue your draft video?', ('Continue', 107, 482, 96, 19), ('your', 210, 487, 47, 18), ('draft', 264, 482, 51, 19),
                     ('video?', 321, 482, 70, 19)),
                 row('Start over', ('Start', 215, 610, 38, 13), ('over', 259, 613, 34, 10)), row('Continue', ('Continue', 323, 610, 71, 13))]
        text = dict(width=500, height=1080, lines=lines)
        self.assertEqual((254, 616), yl.yt_draft_prompt(text)['target'])
        for missing in range(3):   # Title, Start over and Continue are each required.
            with self.subTest(missing=missing), self.assertRaises(InspectionStopped):
                yl.yt_draft_prompt(dict(text, lines=lines[:missing] + lines[missing+1:]))

    def test_title_rules_never_truncate_wrap_or_repair(self):
        self.assertTrue(yl.caption_supported('Fresh yt acceptance'))
        self.assertTrue(yl.caption_supported('y'*24))
        for caption in ('', 'y'*25, TITLE, 'two\nlines', ' lead', 'trail ', 'two  spaces', 'café'):
            self.assertFalse(yl.caption_supported(caption), repr(caption))

    def test_a_wrapped_drafts_title_must_rejoin_to_the_exact_caption(self):
        self.assertTrue(yl.title_lines(['Fresh yt acceptance'], 'Fresh yt acceptance'))
        self.assertTrue(yl.title_lines(['IMOUSE-VIDEO-DRAFT-', 'TEST-20261017'], TITLE))
        self.assertTrue(yl.title_lines(['Fresh yt', 'acceptance'], 'Fresh yt acceptance'))
        for lines, caption in ((['Fresh yt'], 'Fresh yt acceptance'), (['Fresh yt', 'acceptance', 'x'], 'Fresh yt acceptance'),
                               (['Fresh yt-', 'acceptance'], 'Fresh yt acceptance'), (['Fresh', 'yt acceptanc'], 'Fresh yt acceptance'),
                               (['IMOUSE-VIDEO-DRAFT', 'TEST-20261017'], TITLE), ([], 'Fresh yt acceptance')):
            self.assertFalse(yl.title_lines(lines, caption), lines)

    def test_the_caret_is_taller_than_any_title_glyph(self):
        image = np.full((1080, 500, 3), 255, dtype=np.uint8)
        image[160:177, 140:300:9] = 30                      # 17-px glyph stems
        self.assertFalse(yl.caret_visible(image))
        image[157:181, 320:322] = 30                        # the 24-px caret
        self.assertTrue(yl.caret_visible(image))

    def test_paste_callout_needs_paste_and_autofill_side_by_side(self):
        def word(t, x, y, w): return dict(text=t, words=[dict(text=t, x=x, y=y, width=w, height=16)])
        frame = png(Image.new('RGB', (500, 1080), 'white'))
        text = dict(width=500, height=1080, lines=[word('Paste', 75, 94, 45), word('AutoFill', 140, 94, 70)])
        self.assertEqual((98, 102), yl.yt_paste_menu(frame, text)['target'])
        with self.assertRaises(InspectionStopped): yl.yt_paste_menu(frame, dict(text, lines=text['lines'][:1]))


LIVE26 = farm_paths.ARCHIVE/'20261026-youtube-gallery-drafts'


def live26(name):
    text = json.loads((LIVE26/f'{name}.json').read_text(encoding='utf-8'))
    image = LIVE26/f'{name}.bmp'
    return (image if image.exists() else LIVE26/f'{name}.png').read_bytes(), text


@unittest.skipUnless((LIVE26/'gallery.bmp').exists(), 'Slot 16 frames of 26 Oct are not available in this checkout.')
class Slot16CameraGalleryTests(unittest.TestCase):
    def test_the_draft_prompt_is_answered_at_start_over_and_is_not_the_camera(self):
        frame, text = live26('prompt')
        self.assertEqual((254, 616), yl.yt_draft_prompt(text)['target'])
        with self.assertRaises(InspectionStopped): yl.yt_camera(frame, text)
        _, small = live26('prompt-small')   # Run 73: drawn smaller over a black camera; 'Contirwe'.
        self.assertEqual((252, 583), yl.yt_draft_prompt(small)['target'])

    def test_the_white_record_button_camera_has_no_drafts_button(self):
        frame, text = live26('camera-white')
        self.assertEqual(((46, 847), None), tuple(yl.yt_camera(frame, text)[k] for k in ('addTarget', 'draftsTarget')))
        with self.assertRaises(InspectionStopped): yl.yt_draft_prompt(text)

    def test_a_label_lost_over_a_bright_preview_is_read_enlarged(self):
        # Run 66: full-frame OCR missed 'Add' over a lamp; the enlarged band reads it inside its box.
        frame, text = live26('camera-lamp')
        self.assertFalse(any(l['text'] == 'Add' for l in text['lines']))
        self.assertEqual((46, 847), yl.yt_camera(frame, text)['addTarget'])
        self.assertFalse(yl.enlarged_label(frame, 'live', (25, 878, 65, 900)))

    def test_the_title_label_lost_beside_the_caret_is_read_enlarged(self):
        # Run 67: full-frame OCR dropped 'Title' and 'test' while the caret blinked after the pasted title.
        frame, text = live26('details-caret')
        self.assertFalse(any(l['text'] == 'Title' for l in text['lines']))
        self.assertTrue(yl.enlarged_label(frame, 'title', (125, 130, 175, 155)))

    def test_a_tilted_ocr_read_of_the_drafts_list_is_rotated_back(self):
        # Run 70: Windows OCR reported TextAngle 5.1 and every word up to 40 px off; unrotated, the
        # notice is found where it is drawn and the title column holds the title alone.
        from farm_observations import WindowsOcr
        image = (LIVE26/'drafts-tilted.png').read_bytes()
        with Image.open(io.BytesIO(image)) as frame:
            out = io.BytesIO(); frame.convert('RGB').save(out, 'BMP')
        text = WindowsOcr().read(out.getvalue())
        self.assertGreater(abs(text['textAngle']), 4)
        self.assertTrue(yl.drafts_notice(text))
        header = next(l for l in text['lines'] if l['text'] == 'Drafts')['words'][0]
        self.assertLess(abs(header['x'] - 70) + abs(header['y'] - 66), 8)

    def test_the_create_disk_tinted_by_the_feed_is_still_found(self):
        frame, text = live26('home-tinted')   # Run 73: the bar tinted the + disk teal.
        self.assertEqual((250, 1011), yl.yt_home(frame, text)['createTarget'])
        frame, text = live26('home-pink')     # Prep 75 relaunch: pink, its red channel near white.
        self.assertEqual((250, 1011), yl.yt_home(frame, text)['createTarget'])

    def test_the_title_is_read_with_only_the_caret_blanked(self):
        # Run 74: the caret was drawn in 18 of 20 frames; blanking its columns reads the exact title.
        from farm_screen_layout import pixels
        raw = (LIVE26/'details-caret-solid.png').read_bytes(); image = pixels(raw, exact=True)
        self.assertEqual([269, 270, 271], yl.caret_columns(image))
        self.assertEqual(['Fresh', 'short', 'test'], [w[0] for w in yl.caret_masked_title(raw, image)])
        clean = (LIVE26/'details-no-caret.png').read_bytes()
        self.assertEqual([], yl.caret_masked_title(clean, pixels(clean, exact=True)))

    def test_the_gallery_offers_drafts_beside_create_video(self):
        for name in ('gallery', 'gallery-back'):
            frame, text = live26(name)
            self.assertEqual(dict(draftsTarget=(128, 177), closeTarget=(465, 87)), yl.yt_gallery(frame, text))
        frame, text = live26('camera-white')
        with self.assertRaises(InspectionStopped): yl.yt_gallery(frame, text)


A14 = farm_paths.ARCHIVE/'20261105-fleet-a14'


def a14(name):
    return (A14/f'{name}.png').read_bytes(), json.loads((A14/f'{name}.json').read_text(encoding='utf-8'))


@unittest.skipUnless((A14/'yt-gallery.png').exists(), 'A14 frames of 5 Nov are not available in this checkout.')
class A14GalleryTests(unittest.TestCase):
    """A14's gallery before its first draft: Recents, no Create video row, Select multiple over the third row."""
    def test_the_bare_gallery_finds_the_package_tile(self):
        frame, text = a14('yt-gallery')
        image, dy = yl._picker_header(frame, text, 'yt_picker')
        self.assertEqual(yl.BARE_DY, dy)
        found = yl.yt_picker(frame, text, tt.TikTokReference((A14/'yt-package.mp4').read_bytes()))
        self.assertEqual(([0, 112, 164, 403], (141, 134)), (found['tile'], found['target']))
        self.assertGreater(found['nearestOther'] - found['match']['mean'], yl.UNIQUE_MARGIN)

    def test_without_select_multiple_it_is_not_the_bare_gallery(self):
        frame, text = a14('yt-gallery')
        text = dict(text, lines=[l for l in text['lines'] if 'select multiple' not in l['text'].casefold()])
        with self.assertRaises(InspectionStopped): yl._picker_header(frame, text, 'yt_picker')

    def test_the_bare_gallery_offers_no_drafts_button(self):
        frame, text = a14('yt-gallery')
        with self.assertRaises(InspectionStopped): yl.yt_gallery(frame, text)

    def test_the_selected_bare_gallery(self):
        frame, text = a14('yt-selected')
        reference = tt.TikTokReference((A14/'yt-selected-package.mp4').read_bytes())
        found = yl.yt_picker_selected(frame, text, reference, [0, 112, 164, 403])
        self.assertEqual((441, 1000), found['target'])
        # Another tile, nothing shown as selected there.
        with self.assertRaises(InspectionStopped): yl.yt_picker_selected(frame, text, reference, [168, 112, 332, 403])

    def test_the_selected_bare_gallery_needs_its_tray_and_active_next(self):
        from PIL import Image
        frame, text = a14('yt-selected')
        reference = tt.TikTokReference((A14/'yt-selected-package.mp4').read_bytes())
        def painted(box, fill):
            image = Image.open(io.BytesIO(frame)).convert('RGB'); image.paste(fill, box)
            out = io.BytesIO(); image.save(out, 'PNG'); return out.getvalue()
        for reason, box, fill in (('tray is empty', (10, 895, 80, 965), (0, 0, 0)), ('more than one', (100, 901, 158, 955), (90, 90, 90)),
                                  ('Next button', (403, 979, 480, 1022), (60, 60, 60))):
            with self.subTest(reason), self.assertRaisesRegex(InspectionStopped, reason):
                yl.yt_picker_selected(painted(box, fill), text, reference, [0, 112, 164, 403])
        no_next = dict(text, lines=[l for l in text['lines'] if l['text'] != 'Next'])
        with self.assertRaises(InspectionStopped): yl.yt_picker_selected(frame, no_next, reference, [0, 112, 164, 403])

    def test_an_offline_home_stops_the_run(self):
        frame, text = a14('yt-home-offline')
        with self.assertRaisesRegex(InspectionStopped, 'offline'): yl.yt_home(frame, text)

    def test_the_slot16_offset_does_not_fit_this_grid(self):
        frame, text = a14('yt-gallery')
        image = yl.pixels(frame, exact=True)
        self.assertLess((image[503:507, 5:495].max(axis=2) < 40).mean(), .95)   # Slot 16's row gap: tiles here.


@unittest.skipUnless(PRIVATE, 'Retained private C24C YouTube frames/OCR are not available in this checkout.')
class RetainedYouTubeLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ref = tt.TikTokReference((R17/'normalized-test.mp4').read_bytes())
        with tempfile.TemporaryDirectory() as directory:
            cls.alpha = tt.TikTokReference(media.render('alpha', Path(directory)/'a.mp4').read_bytes())

    def test_every_route_screen_is_recognized_with_its_target(self):
        for step in ('136-youtube-after-operator', '145-youtube-save-video-draft', '150-youtube-resave-verified-video'):
            f, t = load(step); home = yl.yt_home(f, t)
            self.assertEqual((311, 1020), home['createTarget']); self.assertEqual(step != '136-youtube-after-operator', home['toastSeen'])
        # The labelled five-item tab bar (17 Oct here; slot 16 since 22 Oct) is accepted with its centre +.
        home = yl.yt_home(*load('50-youtube-loaded'))
        self.assertEqual(((250, 1011), 'labelled'), (home['createTarget'], home['navLayout']))
        for step, which in (('137-youtube-create-video', 'after'), ('146-youtube-draft-route', 'after'), ('147-youtube-video-draft-library', 'before')):
            f, t = load(step, which); self.assertEqual(((46, 847), (455, 846)), tuple(yl.yt_camera(f, t)[k] for k in ('addTarget', 'draftsTarget')))
        f, t = load('52-youtube-create'); self.assertIsNone(yl.yt_camera(f, t)['draftsTarget'])     # no drafts yet
        f, t = load('138-youtube-mp4-picker'); picker = yl.yt_picker(f, t, self.ref)
        self.assertEqual((FIRST, (141, 320), '0:03'), (picker['tile'], picker['target'], picker['durationRead']))
        self.assertGreaterEqual(picker['nearestOther'] - picker['match']['mean'], yl.UNIQUE_MARGIN)
        f, t = selected_picker(); self.assertEqual((367, 997), yl.yt_picker_selected(f, t, self.ref, FIRST)['target'])
        for step, which, read in (('140-youtube-mp4-trim-review', 'after', None), ('141-youtube-mp4-editor', 'before', '3.0s')):
            f, t = load(step, which); trim = yl.yt_trim(f, t, self.ref)
            self.assertEqual(((449, 1005), True, read), (trim['target'], trim['wholeVideo'], trim['lengthRead']))
        indices = []
        for step, which in (('141-youtube-mp4-editor', 'after'), ('142-youtube-video-details', 'before'),
                            ('148-youtube-video-draft-reopen', 'after'), ('149-youtube-reopened-caption', 'before')):
            f, t = load(step, which); editor = yl.yt_editor(f, t, self.ref)
            self.assertEqual((368, 1006), editor['target']); indices.append(editor['media']['index'])
        self.assertNotEqual(indices[2], indices[3])     # the reopened draft visibly played between two frames
        f, t = load('142-youtube-video-details'); blank = yl.yt_details(f, t, self.ref, state='blank')
        self.assertRegex(blank['channel'], r'^[A-Za-z0-9_.-]{1,50}$')
        self.assertEqual(((256, 161), (130, 996)), (blank['titleTarget'], blank['saveTarget']))
        for step, which in (('143-youtube-video-caption-focus', 'after'), ('144-youtube-video-caption', 'before')):
            f, t = load(step, which); self.assertEqual(blank['channel'], yl.yt_details(f, t, self.ref, state='focused')['channel'])
        for step, which in (('147-youtube-video-draft-library', 'after'), ('148-youtube-video-draft-reopen', 'before')):
            f, t = load(step, which); drafts = yl.yt_drafts(f, t, self.ref, TITLE)
            self.assertEqual(((228, 264), 2, ['IMOUSE-VIDEO-DRAFT-', 'TEST-20261017'], '31 seconds ago'),
                             (drafts['target'], drafts['rows'], drafts['row']['title'], drafts['row']['when']))

    def test_negative_controls_on_real_renderings(self):
        cases = [
            ('132-youtube-loaded', 'after', lambda f, t: yl.yt_home(f, t)),                      # local-network prompt over home
            ('137-youtube-create-video', 'after', lambda f, t: yl.yt_home(f, t)),
            ('136-youtube-after-operator', 'after', lambda f, t: yl.yt_camera(f, t)),
            ('53-youtube-add-media', 'after', lambda f, t: yl.yt_picker(f, t, self.ref)),        # earlier picker layout
            ('139-youtube-select-mp4', 'after', lambda f, t: yl.yt_picker(f, t, self.ref)),      # already selected
            ('138-youtube-mp4-picker', 'after', lambda f, t: yl.yt_picker_selected(f, t, self.ref, FIRST)),   # nothing selected
            ('139-youtube-select-mp4', 'after', lambda f, t: yl.yt_picker_selected(f, t, self.ref, FIRST)),   # badge hidden by the pointer
            ('55-youtube-editor', 'after', lambda f, t: yl.yt_trim(f, t, self.ref)),             # 2 s selected of a longer strip
            ('142-youtube-video-details', 'after', lambda f, t: yl.yt_editor(f, t, self.ref)),
            ('141-youtube-mp4-editor', 'after', lambda f, t: yl.yt_details(f, t, self.ref, state='blank')),
            ('58-youtube-details-loaded', 'after', lambda f, t: yl.yt_details(f, t, self.ref, state='blank')),   # earlier layout, photo
            ('142-youtube-video-details', 'after', lambda f, t: yl.yt_details(f, t, self.ref, state='focused')),
            ('143-youtube-video-caption-focus', 'after', lambda f, t: yl.yt_details(f, t, self.ref, TITLE, state='titled')),
            # The 32-character title ran into the field's edge and OCR lost its first letter: never accepted.
            ('145-youtube-save-video-draft', 'before', lambda f, t: yl.yt_details(f, t, self.ref, TITLE, state='titled')),
            ('149-youtube-reopened-caption', 'after', lambda f, t: yl.yt_details(f, t, self.ref, TITLE, state='titled')),
            ('147-youtube-video-draft-library', 'after', lambda f, t: yl.yt_drafts(f, t, self.ref, 'IMOUSE-DRAFT-TEST-20261017')),   # photo
            ('147-youtube-video-draft-library', 'after', lambda f, t: yl.yt_drafts(f, t, self.ref, 'Another title')),
            ('142-youtube-video-details', 'after', lambda f, t: yl.yt_drafts(f, t, self.ref, TITLE)),
        ]
        for step, which, check in cases:
            with self.subTest(step=step, which=which):
                frame, text = load(step, which)
                with self.assertRaises(InspectionStopped): check(frame, text)

    def test_the_camera_must_be_in_short_mode(self):
        frame, text = load('137-youtube-create-video')
        self.assertEqual((46, 847), yl.yt_camera(frame, text)['addTarget'])
        with Image.open(io.BytesIO(frame)) as base: image = np.asarray(base.convert('RGB')).copy()
        band = image[970:1012, 214:286]
        band[band.max(axis=2) < 120] = (7, 6, 7)        # the Short pill gone, its letters kept
        with self.assertRaises(InspectionStopped): yl.yt_camera(png(Image.fromarray(image)), text)

    def test_the_retained_prompt_is_the_shared_local_network_family(self):
        found = prompts.detect(load('132-youtube-loaded')[1])
        self.assertEqual(('local_network', 'YouTube'), (found['kind'], found['app']))
        decision = prompts.plan(found, app_expected='YouTube')
        self.assertEqual(('stop', "Don't Allow"), (decision['action'], decision['answer']))
        self.assertEqual(['keyboard_escape', 'pointer_tap'], decision['ignoredMethods'])

    def test_caret_and_whole_video_on_real_frames(self):
        image = lambda step, which='after': np.asarray(Image.open(R17/step/(which+'.png')).convert('RGB'))
        self.assertTrue(yl.caret_visible(image('143-youtube-video-caption-focus')))
        self.assertTrue(yl.caret_visible(image('60-youtube-test-label')))
        for step, which in (('142-youtube-video-details', 'after'), ('145-youtube-save-video-draft', 'before'), ('65-youtube-reopened-details', 'after')):
            self.assertFalse(yl.caret_visible(image(step, which)), step)
        self.assertTrue(yl.whole_video(image('140-youtube-mp4-trim-review')))
        self.assertFalse(yl.whole_video(image('55-youtube-editor')))

    def test_light_test_media_drawn_into_the_retained_screens_is_accepted(self):
        """Synthetic composite: the labelled, light acceptance media in each retained media box (fixed crops, as the app draws them)."""
        source = media.frame('alpha', 0, 60)
        def draw(frame, box, rows):
            left, top, right, bottom = box
            crop = source.crop((0, (1280-rows)//2, 720, (1280-rows)//2+rows)).resize((right-left, bottom-top), Image.Resampling.LANCZOS)
            with Image.open(io.BytesIO(frame)) as base:
                image = base.convert('RGB'); image.paste(crop, (left, top)); return png(image)
        frame, text = load('138-youtube-mp4-picker')
        for line in text['lines']:     # The tile's duration label belongs to the drawn media.
            for word in line['words']: word['text'] = word['text'].replace('0:03', self.alpha.duration)
        self.assertEqual(FIRST, yl.yt_picker(draw(frame, (2, 300, 162, 587), 1280), text, self.alpha)['tile'])
        frame, text = selected_picker(); frame = draw(frame, (4, 302, 160, 585), 1280)
        disk = Image.new('L', (BADGE[2]-BADGE[0], BADGE[3]-BADGE[1]), 0)
        ImageDraw.Draw(disk).ellipse((141-15-BADGE[0], 320-15-BADGE[1], 141+15-BADGE[0], 320+15-BADGE[1]), fill=255)
        with Image.open(io.BytesIO(frame)) as base, Image.open(R17/'140-youtube-mp4-trim-review/pointer.png') as clean:
            image = base.convert('RGB'); image.paste(clean.convert('RGB').crop(BADGE), BADGE[:2], disk); frame = png(image)
        self.assertEqual((367, 997), yl.yt_picker_selected(frame, text, self.alpha, FIRST)['target'])
        frame, text = load('140-youtube-mp4-trim-review'); self.assertTrue(yl.yt_trim(draw(frame, (50, 154, 450, 868), 1280), text, self.alpha)['wholeVideo'])
        frame, text = load('148-youtube-video-draft-reopen'); yl.yt_editor(draw(frame, (0, 71, 500, 958), 1280), text, self.alpha)
        frame, text = load('142-youtube-video-details'); yl.yt_details(draw(frame, (15, 125, 119, 282), 1056), text, self.alpha, state='blank')
        frame, text = load('147-youtube-video-draft-library')
        drafts = yl.yt_drafts(draw(frame, (15, 190, 153, 396), 1056), text, self.alpha, TITLE)
        self.assertEqual((190, 2), (drafts['row']['top'], drafts['rows']))

    def test_new_test_media_never_matches_the_old_renderings(self):
        selected = selected_picker()
        for name, frame, call in [
                ('picker', load('138-youtube-mp4-picker'), lambda f, t, r: yl.yt_picker(f, t, r)),
                ('selected', selected, lambda f, t, r: yl.yt_picker_selected(f, t, r, FIRST)),
                ('trim', load('140-youtube-mp4-trim-review'), lambda f, t, r: yl.yt_trim(f, t, r)),
                ('editor', load('148-youtube-video-draft-reopen'), lambda f, t, r: yl.yt_editor(f, t, r)),
                ('details', load('142-youtube-video-details'), lambda f, t, r: yl.yt_details(f, t, r, state='blank')),
                ('drafts', load('147-youtube-video-draft-library'), lambda f, t, r: yl.yt_drafts(f, t, r, TITLE))]:
            with self.subTest(screen=name):
                call(*frame, self.ref)
                with self.assertRaises(InspectionStopped): call(*frame, self.alpha)


if __name__ == '__main__':
    unittest.main()
