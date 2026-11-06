"""Safari's Start Page (no tab open) and its focused, empty address field. OCR rows from C24C, 21 Oct."""
import unittest

from farm_carousel_inspection import InspectionStopped
from farm_creation_layout import safari_address_empty, safari_blank, safari_start_page


def text(*rows):
    return dict(width=500, height=1080, lines=[dict(text=t, words=[dict(text=t, x=x0, y=y0, width=x1-x0, height=y1-y0)])
                                               for t, x0, y0, x1, y1 in rows])


PAGE = [('Favorites', 60, 121, 172, 142), ('Privacy Report', 27, 315, 205, 340), ('Recently Closed Tabs', 27, 509, 289, 534),
        ('Reel draft transfer', 41, 564, 189, 578), ('Edit', 233, 663, 268, 679)]
ENTRY = text(*PAGE, ('Q', 53, 945, 72, 965), ('Search or enter website name', 115, 947, 385, 963))
FOCUSED = text(*PAGE, ('x', 450, 77, 465, 92), ('Search or enter webse name', 38, 939, 309, 963))


class SafariStartPageTests(unittest.TestCase):
    def test_start_page_is_recognized_before_focus_only(self):
        self.assertTrue(safari_start_page(ENTRY)['startPage'])
        with self.assertRaises(InspectionStopped): safari_start_page(FOCUSED)
        with self.assertRaises(InspectionStopped): safari_start_page(text(*PAGE))

    def test_focused_field_must_be_empty_with_its_close_button(self):
        self.assertTrue(safari_address_empty(FOCUSED)['addressEmpty'])
        with self.assertRaises(InspectionStopped): safari_address_empty(ENTRY)   # Not focused yet.
        typed = text(*PAGE, ('x', 450, 77, 465, 92), ('example.com', 38, 939, 140, 963))
        with self.assertRaises(InspectionStopped): safari_address_empty(typed)   # Existing text is never overwritten.
        no_close = text(*PAGE, ('Search or enter website name', 38, 947, 309, 963))   # 21 Oct frame: OCR missed the close button.
        self.assertTrue(safari_blank(ENTRY)['startPage'] and safari_blank(FOCUSED)['addressEmpty'])
        with self.assertRaises(InspectionStopped): safari_blank(typed)
        self.assertTrue(safari_address_empty(no_close)['addressEmpty'] and safari_blank(no_close)['startPage'])


class DownloadsListTests(unittest.TestCase):
    def test_a_split_file_name_is_matched_by_its_unique_code(self):
        import farm_reel_layout as reel
        header = [('Done', 27, 523, 75, 538), ('Downloads', 199, 522, 303, 538), ('Clear', 428, 522, 475, 538)]
        split = text(*header, ('mouse', 94, 590, 158, 601), ('-cpfypm', 202, 586, 279, 605), ('31 KB', 94, 615, 133, 625),
                     ('mouse-', 94, 682, 167, 694), ('cvrfec', 211, 678, 268, 694), ('31 KB', 94, 707, 133, 718))
        self.assertEqual((186, 596), reel.downloads_list(split, 'imouse-reel-cpfypm', 31166)['target'])   # 21 Oct, slot 18.
        for name, size in (('imouse-reel-aaaaaa', 31166), ('imouse-reel-cpfypm', 64000)):
            with self.subTest(name=name, size=size), self.assertRaises(InspectionStopped): reel.downloads_list(split, name, size)
        no_dash = text(*header, ('mouse', 94, 590, 158, 601), ('htxkyd', 212, 586, 271, 605), ('31 KB', 94, 615, 133, 625),
                       ('mouse-', 94, 682, 167, 694), ('pfauct', 212, 678, 269, 697), ('31 KB', 94, 707, 133, 718))   # 22 Oct.
        self.assertEqual((182, 596), reel.downloads_list(no_dash, 'imouse-reel-htxkyd', 31166)['target'])
        with self.assertRaises(InspectionStopped): reel.downloads_list(no_dash, 'imouse-reel-xtkyde', 31166)
        twice = text(*header, ('imouse-reel-cpfypm', 94, 586, 279, 605), ('31 KB', 94, 615, 133, 625),
                     ('imouse-reel-cpfypm', 94, 678, 279, 694), ('31 KB', 94, 707, 133, 718))
        with self.assertRaises(InspectionStopped): reel.downloads_list(twice, 'imouse-reel-cpfypm', 31166)   # Ambiguous.


class LeftoverShareSheetTests(unittest.TestCase):
    ROWS = [('imouse-reel-featmr', 142, 76, 353, 92), ('Done', 426, 77, 474, 92), ('Video .31 KB', 69, 545, 164, 557),
            ('Copy', 50, 765, 96, 784), ('Save Video', 50, 837, 151, 854), ('Add Tags', 50, 899, 134, 918),
            ('Save to Files', 50, 959, 163, 975), ('Add to Shared Album', 50, 1020, 243, 1036)]   # 22 Oct, slot 18.

    def test_an_earlier_downloads_sheet_is_closed_by_its_close_button(self):
        import farm_reel_layout as reel
        found = reel.leftover_share_sheet(text(('imouse-reel-featmr', 69, 521, 237, 536), *self.ROWS))
        self.assertEqual(('imouse-reel-featmr', (460, 531)), (found['name'], found['closeTarget']))
        for header in (('Photo', 69, 521, 237, 536), ('imouse-reel-featmr', 142, 300, 353, 316)):
            with self.subTest(header=header), self.assertRaises(InspectionStopped): reel.leftover_share_sheet(text(header, *self.ROWS))
        x_rows = [('imouse-x-hctunh', 85, 519, 232, 534)] + [r for r in self.ROWS if r[1] < 100]   # 22 Oct, slot 17 (X route).
        self.assertEqual('imouse-x-hctunh', reel.leftover_share_sheet(text(*x_rows))['name'])
        with self.assertRaises(InspectionStopped): reel.leftover_share_sheet(text(('imouse-zz-hctunh', 85, 519, 232, 534), *x_rows[1:]))
        with self.assertRaises(InspectionStopped):   # Not the share sheet's actions.
            reel.leftover_share_sheet(text(('imouse-reel-featmr', 69, 521, 237, 536), *self.ROWS[:4]))


class TransferPageWaitTests(unittest.TestCase):
    def workflow(self, pages):
        from types import SimpleNamespace
        from farm_reel_creation import ReelCreationWorkflow
        import farm_reel_layout as reel
        flow = ReelCreationWorkflow.__new__(ReelCreationWorkflow)
        frames = iter(pages); shots = []
        def shot(board): shots.append(board); return next(frames), {'X-iMouse-Frame-Sequence': str(len(shots))}
        flow.kernel = SimpleNamespace(shot=shot); flow.phone = SimpleNamespace(board='C24C')
        flow.store = SimpleNamespace(ocr=SimpleNamespace(read=lambda raw: raw)); flow.record = {}; flow.pause = lambda s: None
        flow.transfer_page = lambda t: reel.reel_transfer_page(t, 'imouse-reel-ktreed')
        return flow, shots

    def page(self, name):
        return text(('Reel draft', 25, 112, 177, 140), ('File ' + name, 25, 175, 271, 196), ('Download video', 173, 248, 327, 268),
                    ('Copy caption', 186, 438, 314, 458))

    def test_input_waits_until_this_transfers_page_shows(self):
        flow, shots = self.workflow([self.page('imouse-reel-featmr'), self.page('imouse-reel-featmr'), self.page('imouse-reel-ktreed')])
        flow.await_transfer_page()   # 22 Oct, slot 18: the earlier page stayed while the new one loaded.
        self.assertEqual(3, len(shots)); self.assertTrue(flow.record['transferPageWait'][-1]['shown'])

    def test_a_page_that_never_shows_is_left_to_the_page_check(self):
        flow, shots = self.workflow([self.page('imouse-reel-featmr')] * 10)
        flow.await_transfer_page()
        self.assertEqual(10, len(shots)); self.assertNotIn('shown', flow.record['transferPageWait'][-1])


class NextPillTests(unittest.TestCase):
    def test_the_pill_matches_over_any_backdrop_but_not_when_it_changes(self):
        import base64, io, json
        from pathlib import Path
        import numpy as np
        from PIL import Image
        import farm_reel_layout as reel
        row = json.loads(Path(reel.__file__).with_name('farm_reel_controls.json').read_text(encoding='utf-8'))['next_pill']
        with Image.open(io.BytesIO(base64.b64decode(row['png']))) as image: pill = image.convert('RGB')
        inside = np.asarray(pill)[..., 2] > 180

        def frame(backdrop, colour=None):
            image = Image.new('RGB', (500, 1080), backdrop); left, top, _, _ = row['box']
            patch = np.asarray(pill).copy(); patch[~inside] = backdrop
            if colour: patch[inside & (np.asarray(pill)[..., 0] < 200)] = colour
            image.paste(Image.fromarray(patch), (left, top)); out = io.BytesIO(); image.save(out, 'BMP'); return out.getvalue()
        for backdrop in ((9, 58, 44), (230, 230, 230), (120, 20, 90)):   # Blurred photos behind the corners (22 Oct, slot 18).
            with self.subTest(backdrop=backdrop): self.assertTrue(reel.present(frame(backdrop), 'next_pill'))
        self.assertFalse(reel.present(frame((9, 58, 44), colour=(120, 120, 120)), 'next_pill'))   # A grey (disabled) pill.


class FirstDraftLabelTests(unittest.TestCase):
    def test_the_label_is_read_by_its_words_even_joined_to_its_icon(self):
        from unittest import mock
        import farm_reel_layout as reel
        stubs = dict(_picker_frame=lambda f, t: (None, None, None), numbered_one=lambda i, c: True, selected_disk=lambda i, c: False,
                     reel_control=lambda f, n: None, video_match=lambda *a, **k: dict(matched=True), band_words=lambda f, b: [])
        with mock.patch.multiple(reel, **stubs):
            joined = text(('t-g First draft', 285, 985, 379, 1003))
            joined['lines'][0]['words'] = [dict(text=t, x=x0, y=y0, width=x1-x0, height=y1-y0) for t, x0, y0, x1, y1 in
                                           (('t-g', 285, 985, 303, 1003), ('First', 309, 988, 340, 1000), ('draft', 345, 988, 379, 1000))]
            self.assertEqual((444, 993), reel.reel_selected(None, joined, None, (0, 1))['target'])   # 22 Oct, slot 18.
            with self.assertRaises(InspectionStopped): reel.reel_selected(None, text(('First', 309, 988, 340, 1000)), None, (0, 1))


class PreviewReconfirmTests(unittest.TestCase):
    def test_a_newer_frame_without_ocr_is_compared_by_its_video_pixels(self):
        from unittest import mock
        from farm_reel_creation import ReelCreationWorkflow
        import farm_reel_layout as reel
        flow = ReelCreationWorkflow.__new__(ReelCreationWorkflow); flow.download, flow.video = 'imouse-reel-ktreed', object()
        compare = flow.confirmation_compare('quicklook')
        # 22 Oct, slot 18: the reconfirmation passes no text; the toolbar showed, so the header check crashed.
        with mock.patch.object(reel, 'preview_media', return_value=dict(matched=True)) as media,                 mock.patch.object(reel, 'quicklook', side_effect=AssertionError('needs OCR text')):
            self.assertEqual('ready', compare(b'first', {}, b'second', None)['state'])
        media.assert_called_once_with(b'second', flow.video)
        with mock.patch.object(reel, 'preview_media', side_effect=InspectionStopped('not the package video')):
            self.assertEqual('wait', compare(b'first', {}, b'second', None)['state'])


class SelectionTrayTests(unittest.TestCase):
    def test_a_narrowly_missed_tray_thumbnail_needs_this_packages_tile_colours(self):
        from unittest import mock
        import farm_reel_layout as reel
        label = text(('First draft', 309, 988, 379, 1000))
        label['lines'][0]['words'] = [dict(text='First', x=309, y=988, width=31, height=12), dict(text='draft', x=345, y=988, width=34, height=12)]
        stubs = dict(_picker_frame=lambda f, t: (None, None, None), numbered_one=lambda i, c: True, selected_disk=lambda i, c: False,
                     reel_control=lambda f, n: None)
        for mean, colours, expected in ((.067, True, True), (.067, False, False), (.17, True, False)):   # 22 Oct, slot 18.
            near = dict(matched=False, mean=mean, worstBlock=.1)
            with self.subTest(mean=mean, colours=colours), mock.patch.multiple(reel, **stubs),                     mock.patch.object(reel, 'video_match', return_value=near),                     mock.patch.object(reel, 'tile_colours_match', return_value=dict(matched=colours)):
                if expected: self.assertTrue(reel.reel_selected(None, label, None, (0, 1))['tray']['matched'])
                else:
                    with self.assertRaises(InspectionStopped): reel.reel_selected(None, label, None, (0, 1))


class EditorToolbarTests(unittest.TestCase):
    def test_missed_toolbar_labels_are_read_again_from_the_enlarged_row(self):
        from unittest import mock
        import farm_reel_layout as reel
        screen = text(('Edit video', 36, 986, 104, 998), ('Next', 414, 986, 445, 997))   # 22 Oct, slot 18: no toolbar words.
        read = [('audio', 58, 86), ('text', 150, 168), ('voice', 234, 266), ('captions', 312, 362), ('overlay', 403, 448)]
        with mock.patch.multiple(reel, no_overlay=lambda t: None, video_match=lambda *a, **k: dict(matched=True)):
            with mock.patch.object(reel, 'toolbar_words', return_value=read):
                self.assertEqual((444, 993), reel.reel_editor(None, screen, None)['target'])
            moved = [(w, x0 + 120, x1 + 120) for w, x0, x1 in read]   # Same words elsewhere are not the toolbar.
            with mock.patch.object(reel, 'toolbar_words', return_value=moved), self.assertRaises(InspectionStopped):
                reel.reel_editor(None, screen, None)


class StartScreenReelEditorTests(unittest.TestCase):
    EDITOR = [('x', 29, 87, 53, 111), ('REEL DRAFT TEST', 45, 148, 395, 177), ('Edit video', 36, 986, 104, 998), ('Next', 414, 986, 445, 997)]
    PICKER = [('New reel', 210, 88, 290, 106), ('Recents', 22, 218, 96, 238), ('Next', 414, 986, 445, 997)]

    DIALOG = [('Start over?', 199, 408, 301, 423), ('If you go back now, you will lose this', 111, 447, 390, 464),
              ('Start over', 205, 548, 296, 563), ('Save draft', 206, 610, 294, 626), ('Keep editing', 197, 673, 303, 692)]

    def screen(self, *after):
        from farm_start_screen import StartScreen
        start = StartScreen.__new__(StartScreen); taps = []; frames = iter(after)
        start.tap = lambda raw, text, point, role, purpose, only=None: taps.append((purpose, point))
        start.pause = lambda s: None
        start.fresh = lambda label: (b'after', next(frames), 0, 0)
        return start, taps

    def test_the_start_over_dialog_drops_the_unsaved_session_never_saving_it(self):
        start, taps = self.screen(text(*self.DIALOG), text(*self.PICKER))   # 22 Oct, slot 18.
        start.close_reel_editor(b'before', text(*self.EDITOR))
        self.assertEqual([('close-reel-editor', (41, 98)), ('start-over-1', (250, 556))], taps)
        start, taps = self.screen(text(*self.PICKER))
        start.close_reel_editor(b'before', text(*self.EDITOR, *self.DIALOG))   # Left open by an earlier stop.
        self.assertEqual([('start-over-1', (250, 556))], taps)
        start, taps = self.screen(text(*self.EDITOR, *self.DIALOG), text(*self.PICKER))   # First tap not taken (22 Oct).
        start.close_reel_editor(b'before', text(*self.EDITOR, *self.DIALOG))
        self.assertEqual(['start-over-1', 'start-over-2'], [p for p, _ in taps])
        start, taps = self.screen(text(*self.EDITOR, *self.DIALOG), text(*self.EDITOR, *self.DIALOG))
        with self.assertRaises(InspectionStopped): start.close_reel_editor(b'before', text(*self.EDITOR, *self.DIALOG))
        self.assertEqual(2, len(taps))
        reordered = [row if row[0] != 'Save draft' else ('Save draft', 206, 540, 294, 556) for row in self.DIALOG]
        self.assertIsNone(start.start_over_dialog(text(*reordered)))

    def test_a_leftover_editor_closes_back_to_the_picker_then_the_picker_closes(self):
        start, taps = self.screen(text(*self.PICKER))   # 22 Oct, slot 18: Instagram reopened in the editor.
        self.assertTrue(start.reel_editor(text(*self.EDITOR)) and not start.reel_editor(text(*self.PICKER)))
        start.close_reel_editor(b'before', text(*self.EDITOR))
        self.assertEqual([('close-reel-editor', (41, 98))], taps)

    def test_leftover_details_go_back_to_the_editor_first(self):
        details = text(('New reel', 210, 77, 289, 92), ('Add a caption...', 22, 495, 142, 511), ('Save draft', 90, 991, 171, 1004),
                       ('Share', 347, 991, 392, 1004))   # 22 Oct, slot 18.
        # The editor is read twice after the back tap: it must have settled (A18, 4 Nov).
        start, taps = self.screen(text(*self.EDITOR), text(*self.EDITOR), text(*self.DIALOG), text(*self.PICKER), text(('xs.halle.xo', 150, 90, 260, 110)))
        self.assertTrue(start.reel_details(details) and not start.reel_details(text(*self.EDITOR)))
        start.close_new_reel(b'before', details)
        self.assertEqual(['details-back', 'close-reel-editor', 'start-over-1', 'close-new-reel'], [p for p, _ in taps])
        self.assertEqual((30, 84), taps[0][1])
        start, taps = self.screen(text(*self.PICKER), text(*self.PICKER))
        with self.assertRaises(InspectionStopped): start.close_reel_details(b'before', details)   # Back must reach the editor.

    def test_anything_but_the_picker_after_the_close_stops(self):
        start, taps = self.screen(text(('Discard edits?', 150, 450, 350, 470), ('Discard', 200, 520, 300, 540)))

        with self.assertRaises(InspectionStopped): start.close_reel_editor(b'before', text(*self.EDITOR))
        self.assertEqual(1, len(taps))


    def test_the_screen_after_the_back_tap_is_decided_only_once_settled(self):
        import io
        from PIL import Image, ImageDraw
        from farm_start_screen import StartScreen, SETTLE_TRIES
        def frame(bar_x, video=0):
            image = Image.new('RGB', (500, 1080), (20, 20, 20)); draw = ImageDraw.Draw(image)
            draw.rectangle((bar_x, 80, bar_x + 60, 120), fill='white')            # Top bar sliding in.
            draw.rectangle((0, 300 + video, 500, 400 + video), fill=(200, 50, 50))   # The playing video.
            out = io.BytesIO(); image.save(out, 'PNG'); return out.getvalue()
        def start_with(raws):
            start = StartScreen.__new__(StartScreen); frames = iter(raws); start.pause = lambda s: None
            start.fresh = lambda role: (next(frames), role, 0, 0)
            return start
        start = start_with([frame(200), frame(100), frame(20, 0), frame(20, 40)])   # The video moves; the bar has stopped.
        self.assertEqual('after-settle-3', start.fresh_settled('after', only=((0, 65, 500, 130),))[1])
        start = start_with([frame(20 + 30 * n) for n in range(SETTLE_TRIES)])
        with self.assertRaises(InspectionStopped): start.fresh_settled('after', only=((0, 65, 500, 130),))

class ShiftedShareSheetTests(unittest.TestCase):
    def test_a_sheet_settled_lower_is_read_at_its_own_position(self):
        import farm_reel_layout as reel
        rows = [('imouse-reel-nthhym', 69, 556, 244, 574), ('Video .31 KB', 69, 580, 164, 592), ('Copy', 50, 799, 96, 819),
                ('Save Video', 50, 872, 151, 888), ('Add Tags', 50, 933, 134, 952), ('Save to Files', 50, 994, 163, 1010)]   # 22 Oct, slot 18.
        found = reel.share_sheet(text(*rows), 'imouse-reel-nthhym')
        self.assertEqual(((100, 880), 35), (found['target'], found['shift']))
        self.assertEqual((460, 566), reel.leftover_share_sheet(text(*rows))['closeTarget'])
        with self.assertRaises(InspectionStopped): reel.share_sheet(text(*rows), 'imouse-reel-featmr')
        unshifted_rows = [rows[0]] + [(t, x0, y0 - 35 - 70, x1, y1 - 35 - 70) for t, x0, y0, x1, y1 in rows[1:]]
        with self.assertRaises(InspectionStopped): reel.share_sheet(text(*unshifted_rows), 'imouse-reel-nthhym')   # Rows must move with it.
        too_low = [(t, x0, y0 + 80, x1, y1 + 80) for t, x0, y0, x1, y1 in rows]
        with self.assertRaises(InspectionStopped): reel.share_sheet(text(*too_low), 'imouse-reel-nthhym')


class ReelDetailsRowsTests(unittest.TestCase):
    def test_location_and_audio_rows_are_found_in_either_list_layout(self):
        from unittest import mock
        import farm_reel_layout as reel
        top = [('New reel', 210, 77, 289, 92), ('Preview', 193, 164, 256, 177), ('Edit cover', 193, 420, 273, 434),
               ('Add a caption...', 22, 495, 142, 511), ('Poll', 194, 622, 219, 633), ('Prompt', 280, 619, 337, 636),
               ('Save draft', 90, 991, 171, 1004), ('Share', 347, 991, 392, 1004)]
        def screen(location_y, audio_y):
            rows = [('Add location', 65, location_y, 173, location_y + 15), ('Original audio', 344, audio_y, 475, audio_y + 17)]
            built = text(*top)
            for label, x, y in (('Add location', 65, location_y), ('Original audio', 344, audio_y)):   # One OCR word per word.
                built['lines'].append(dict(text=label, words=[dict(text=w, x=x + 60*i, y=y, width=55, height=15)
                                                              for i, w in enumerate(label.split())]))
            return built
        stubs = dict(no_overlay=lambda *a: None, reel_control=lambda f, n: None, video_match=lambda *a, **k: dict(matched=True))
        with mock.patch.multiple(reel, **stubs):
            for location_y, audio_y in ((749, 808), (807, 865)):   # 17 Oct and 22 Oct (slot 18).
                with self.subTest(location_y=location_y):
                    self.assertEqual((130, 996), reel.reel_details(None, screen(location_y, audio_y), None)['saveTarget'])
            with self.assertRaises(InspectionStopped): reel.reel_details(None, screen(807, 808), None)   # Not a settings list.
        stubs['pixels'] = lambda frame, exact=False: None
        for mean, colours, expected in ((.134, True, True), (.134, False, False), (.21, True, False)):   # Darkened cover (22 Oct).
            with self.subTest(mean=mean, colours=colours), mock.patch.multiple(reel, **dict(stubs, video_match=lambda *a, **k: dict(matched=False, mean=mean))),                     mock.patch.object(reel, 'tile_colours_match', return_value=dict(matched=colours)):
                if expected: self.assertTrue(reel.reel_details(None, screen(807, 865), None)['cover']['matched'])
                else:
                    with self.assertRaises(InspectionStopped): reel.reel_details(None, screen(807, 865), None)


class FeedReloadTests(unittest.TestCase):
    def flow(self, outcomes):
        from farm_draft_creation import CreationWorkflow
        flow = CreationWorkflow.__new__(CreationWorkflow); outcomes = iter(outcomes); steps = []
        def observe(role, *a, **k):
            role_, result = next(outcomes); self.assertEqual(role_, role)
            if isinstance(result, Exception): raise result
            return dict(result=dict(screen=result)), None
        flow.observe = observe; flow.step = lambda label, role, point=None, **k: steps.append((label, role, point))
        return flow, steps

    def test_a_feed_reload_after_the_profile_gets_one_profile_tab(self):
        flow, steps = self.flow([('account_entry', 'profile'), ('profile', InspectionStopped('not visible')),   # 22 Oct, slot 18.
                                 ('account_entry', 'instagram_feed'), ('profile', 'profile')])
        flow.account_profile('verify-returned-account')
        self.assertEqual([('verify-returned-account-after-reload', 'instagram_navigation', (447, 1008))], steps)

    def test_no_second_recovery_and_prompts_keep_their_own_handling(self):
        flow, steps = self.flow([('account_entry', 'profile'), ('profile', InspectionStopped('not visible')),
                                 ('account_entry', 'instagram_feed'), ('profile', InspectionStopped('still not visible'))])
        with self.assertRaises(InspectionStopped): flow.account_profile('verify-returned-account')
        prompt = InspectionStopped('prompt'); prompt.decision = dict(action='answer')
        flow, steps = self.flow([('account_entry', 'profile'), ('profile', prompt)])
        with self.assertRaises(InspectionStopped) as raised: flow.account_profile('verify-returned-account')
        self.assertIs(prompt, raised.exception); self.assertEqual([], steps)
        flow, steps = self.flow([('account_entry', 'profile'), ('profile', InspectionStopped('different account')), ('account_entry', 'profile')])
        with self.assertRaises(InspectionStopped): flow.account_profile('verify-returned-account')   # Profile again: no tap.
        self.assertEqual([], steps)


class PreviewReconfirmRuleTests(unittest.TestCase):
    def test_a_playing_preview_is_reconfirmed_by_its_button_bar_and_media(self):
        from unittest import mock
        import numpy as np
        import farm_reel_layout as reel
        from farm_reel_creation import ReelCreationWorkflow
        bar = np.zeros((1080, 500, 3), dtype=np.uint8); bar[960:1030] = 200
        moved = bar.copy(); moved[960:1030] = 20
        frames = {b'first': bar, b'same': bar.copy(), b'moved': moved}
        flow = ReelCreationWorkflow.__new__(ReelCreationWorkflow); flow.video = object()
        compare = flow.confirmation_compare('reel_preview')   # 22 Oct: the keep decision aged to 1539 ms.
        with mock.patch.object(reel, 'pixels', lambda frame, exact=False: frames[frame]):
            for second, matched, state in ((b'same', True, 'ready'), (b'same', False, 'wait'), (b'moved', True, 'wait')):
                with self.subTest(second=second, matched=matched),                         mock.patch.object(reel, 'preview_playback', return_value=dict(matched=matched)):
                    self.assertEqual(state, compare(b'first', {}, second, None)['state'])


class PreviewAccountTests(unittest.TestCase):
    def test_only_a_garbled_or_unread_account_is_read_again_enlarged(self):
        from unittest import mock
        import numpy as np
        import farm_reel_layout as reel
        def screen(audio):
            built = text(('Save draft', 90, 991, 172, 1004), ('Share', 347, 991, 392, 1004), ('Fresh reel acceptance', 21, 918, 191, 934))
            words = audio.split()
            built['lines'].append(dict(text=audio, words=[dict(text=w, x=64 + 60*i, y=903, width=55, height=14) for i, w in enumerate(words)]))
            return built
        bright = np.full((1080, 500, 3), 230, dtype=np.uint8)
        stubs = dict(no_overlay=lambda *a: None, pixels=lambda frame, exact=False: bright,
                     preview_playback=lambda f, r: dict(matched=True), band_words=lambda f, b: [('xs.halle.xo', 74, 872, 160, 888)])
        with mock.patch.multiple(reel, **stubs):
            # 22 Oct, slot 18: the audio line read '. alle.xu', the name row not at all.
            self.assertEqual((130, 996), reel.reel_preview(b'f', screen('. alle.xu • Original audit'), None, 'xs.halle.xo', 'Fresh reel acceptance')['saveTarget'])
            with self.assertRaises(InspectionStopped):   # A clean read of another handle is never overruled.
                reel.reel_preview(b'f', screen('wrong.account • Original audio'), None, 'xs.halle.xo', 'Fresh reel acceptance')
        with mock.patch.multiple(reel, **dict(stubs, band_words=lambda f, b: [('xs.hallexx', 74, 872, 160, 888)])),                 self.assertRaises(InspectionStopped):   # A similar account still needs an exact enlarged read.
            reel.reel_preview(b'f', screen('. hallexx • Original audio'), None, 'xs.halle.xo', 'Fresh reel acceptance')


class SuggestionLabelTests(unittest.TestCase):
    def test_a_missed_suggestion_label_is_read_again_from_its_row(self):
        from unittest import mock
        import farm_creation_layout as layout
        import farm_reel_layout as reel
        screen = text(('Siri Suggestions', 26, 76, 164, 94), ('YouTube', 166, 212, 225, 223), ('Instagram', 269, 212, 338, 226))
        row = [('TikTok', 65, 211, 111, 224), ('YouTube', 166, 212, 225, 223)]   # 22 Oct, slot 20: OCR missed 'TikTok'.
        with mock.patch.object(layout, 'home', side_effect=InspectionStopped('not home')), mock.patch.object(reel, 'band_words', return_value=row):
            self.assertEqual((88, 169), layout.app_target(screen, 'TikTok', b'frame'))
            with self.assertRaises(InspectionStopped): layout.app_target(screen, 'Snapchat', b'frame')
        with mock.patch.object(layout, 'home', side_effect=InspectionStopped('not home')),                 mock.patch.object(reel, 'band_words', return_value=row + [('TikTok', 380, 211, 420, 224)]), self.assertRaises(InspectionStopped):
            layout.app_target(screen, 'TikTok', b'frame')   # Read twice: ambiguous.

    def test_a_missed_top_hit_label_is_read_again_leftmost_in_its_row(self):
        from unittest import mock
        import farm_creation_layout as layout
        import farm_reel_layout as reel
        screen = text(('Top Hit', 26, 76, 100, 94), ('Search', 160, 212, 214, 224))   # Full-frame OCR missed 'TikTok' and 'Inbox'.
        row = [('Search', 160, 212, 214, 224), ('TikTok', 62, 212, 112, 225), ('Inbox', 250, 212, 290, 224)]   # A20, 4 Nov.
        with mock.patch.object(layout, 'home', side_effect=InspectionStopped('not home')), \
                mock.patch.object(reel, 'band_words', return_value=row) as band:
            self.assertEqual((87, 218), layout.app_target(screen, 'TikTok', b'frame'))
            band.assert_called_with(b'frame', layout.TOP_HIT_LABELS, 3)
            with self.assertRaises(InspectionStopped): layout.app_target(screen, 'Inbox', b'frame')    # A shortcut, not leftmost.
            with self.assertRaises(InspectionStopped): layout.app_target(screen, 'Snapchat', b'frame')
            with self.assertRaises(InspectionStopped): layout.app_target(screen, 'TikTok')             # No frame: no reread.
        for rows in (row + [('TikTok', 380, 212, 430, 225)], []):
            with self.subTest(rows=rows), mock.patch.object(layout, 'home', side_effect=InspectionStopped('not home')), \
                    mock.patch.object(reel, 'band_words', return_value=rows), self.assertRaises(InspectionStopped):
                layout.app_target(screen, 'TikTok', b'frame')


class TikTokFeedHeaderTests(unittest.TestCase):
    def test_a_covered_feed_header_is_read_again_in_place(self):
        from unittest import mock
        import farm_tiktok_layout as tt
        import farm_reel_layout as reel
        nav = [(name, box[0] + 2, box[1] + 2, box[0] + 30, box[1] + 14) for name, box in tt.NAV]
        screen = text(*[(name.capitalize(), x0, y0, x1, y1) for name, x0, y0, x1, y1 in nav])
        for row in screen['lines']: row['words'][0]['text'] = row['text'] = row['text'].casefold()
        with mock.patch.object(tt, 'band_words', return_value=[('Community', 99, 76, 190, 92), ('Following', 213, 76, 290, 92)]):
            self.assertEqual((450, 1005), tt.tiktok_feed(b'frame', screen)['profileTarget'])   # 22 Oct, slot 20.
        with mock.patch.object(tt, 'band_words', return_value=[("Fb!19wiK9'", 150, 76, 290, 92), ("'Shop'.", 300, 76, 340, 92)]):
            self.assertEqual((450, 1005), tt.tiktok_feed(b'frame', screen)['profileTarget'])   # 25 Oct: only 'Shop' read.
        with mock.patch.object(tt, 'band_words', return_value=[('Sponsored', 150, 76, 260, 92)]), self.assertRaises(InspectionStopped):
            tt.tiktok_feed(b'frame', screen)


class SafariChromeTests(unittest.TestCase):
    def frame(self, recolour):
        import base64, io, json
        from pathlib import Path
        import numpy as np
        from PIL import Image
        import farm_draft_creation
        image = Image.new('RGB', (500, 1080), (248, 248, 248))
        for row in json.loads(Path(farm_draft_creation.__file__).with_name('farm_creation_browser.json').read_text(encoding='utf-8')):
            with Image.open(io.BytesIO(base64.b64decode(row['png']))) as icon: rgb = np.asarray(icon.convert('RGB')).copy()
            rgb = recolour(rgb); image.paste(Image.fromarray(rgb), tuple(row['box'][:2]))
        out = io.BytesIO(); image.save(out, 'BMP'); return out.getvalue()

    def test_black_toolbar_icons_match_by_shape_but_other_shapes_do_not(self):
        import numpy as np
        from farm_draft_creation import CreationWorkflow
        flow = CreationWorkflow.__new__(CreationWorkflow)
        def black(rgb):   # 22 Oct, slot 20: the same icons drawn black.
            ink = rgb.min(axis=2) < 150; rgb[ink] = (20, 20, 20); return rgb
        self.assertEqual('safari', flow.verify_screen('safari', dict(text=text()), self.frame(black))['browser'])
        def shifted(rgb): return np.roll(black(rgb), 12, axis=1)
        with self.assertRaises(InspectionStopped): flow.verify_screen('safari', dict(text=text()), self.frame(shifted))


class XHeaderTests(unittest.TestCase):
    def test_the_newer_header_with_more_tabs_is_the_timeline(self):
        from unittest import mock
        import numpy as np
        import farm_x_layout as xl
        image = np.full((1080, 500, 3), 255, dtype=np.uint8); image[909:961, 428:480] = (29, 155, 240)
        screen = text(('For you', 31, 130, 96, 148), ('Crypto', 376, 130, 430, 148))
        screen['lines'].append(dict(text='Following • Add +', words=[dict(text='Following', x=154, y=130, width=80, height=18),
                                                                    dict(text='•', x=262, y=136, width=4, height=4)]))
        with mock.patch.object(xl, 'pixels', lambda frame, exact=False: image):
            self.assertEqual((454, 935), xl.x_feed(b'f', screen)['composeTarget'])   # 22 Oct, slot 17's new account.
            screen['lines'][-1]['words'][0]['x'] = 100
            with self.assertRaises(InspectionStopped): xl.x_feed(b'f', screen)


class PrivateBrowsingAddressTests(unittest.TestCase):
    def frame(self, highlight):
        import io
        from PIL import Image, ImageDraw
        image = Image.new('RGB', (500, 1080), (242, 242, 247)); draw = ImageDraw.Draw(image)
        draw.rectangle((20, 930, 480, 982), fill=(80, 77, 80)); draw.rectangle((0, 1066, 499, 1069), fill=(10, 10, 10))
        if highlight: draw.rectangle((34, 943, 374, 968), fill=(150, 147, 152))
        draw.text((40, 948), 'https://www.example.com/', fill=(235, 234, 237))
        out = io.BytesIO(); image.save(out, 'BMP'); return out.getvalue()

    def test_a_grey_highlight_on_the_dark_private_field_counts_as_selected(self):
        from farm_draft_creation import CreationWorkflow
        flow = CreationWorkflow.__new__(CreationWorkflow)
        self.assertTrue(flow.verify_screen('address_selected', dict(text=text()), self.frame(True))['privateBrowsing'])   # 22 Oct, slot 20.
        with self.assertRaises(InspectionStopped): flow.verify_screen('address_selected', dict(text=text()), self.frame(False))


class XMenuTests(unittest.TestCase):
    def test_either_grok_row_is_the_account_menu(self):
        import farm_x_layout as xl
        rows = [('Profile', 99, 271, 175, 291), ('Communities', 98, 465, 256, 485), ('Settings and privacy', 93, 844, 272, 863),
                ('@example_handle', 40, 167, 190, 186)]
        for grok in (('Download Grok', 93, 780, 230, 800), ('Try Grok Bot', 93, 788, 202, 807)):   # Older; 22 Oct slot 17.
            with self.subTest(grok=grok[0]): self.assertEqual((447, 83), xl.x_menu(None, text(*rows, grok))['closeTarget'])
        with self.assertRaises(InspectionStopped): xl.x_menu(None, text(*rows))


class EmptyAppSearchTests(unittest.TestCase):
    def test_the_placeholder_shows_an_empty_field_when_the_template_follows_the_wallpaper(self):
        from unittest import mock
        import farm_creation_layout as layout
        base = [('Siri Suggestions', 26, 76, 164, 94)]
        with mock.patch.object(layout, 'control', side_effect=InspectionStopped('wallpaper')):
            for placeholder in ('Q Search', 'Q bearch'):   # 22 Oct, slots 17 and 20.
                with self.subTest(placeholder=placeholder):
                    self.assertTrue(layout.empty_search(text(*base, (placeholder, 43, 990, 148, 1023)), b'frame'))
            for typed in (('Q Safari', 43, 990, 148, 1023), ('Q Search', 43, 600, 148, 630)):
                with self.subTest(typed=typed), self.assertRaises(InspectionStopped):
                    layout.empty_search(text(*base, typed), b'frame')


class SelectedAddressEntryTests(unittest.TestCase):
    def test_safari_reopened_with_its_address_selected_is_an_entry_that_needs_no_focus_tap(self):
        from unittest import mock
        import farm_reel_creation as rc
        flow = rc.ReelCreationWorkflow.__new__(rc.ReelCreationWorkflow)
        flow.check_prompt = lambda role, value: None
        real = rc.ReelCreationWorkflow.verify_screen
        def verify(self, role, value, frame, index=None, require_next=False):
            if role == 'safari': raise InspectionStopped('toolbar hidden while editing')
            if role == 'address_selected': return dict(addressSelected=True, privateBrowsing=True)
            return real(self, role, value, frame, index, require_next)
        with mock.patch.object(rc.ReelCreationWorkflow, 'verify_screen', verify), mock.patch.object(rc, 'safari_blank', side_effect=InspectionStopped('no')):
            entry = real(flow, 'reel_safari_entry', dict(text=text()), b'f')
        self.assertTrue(entry['addressSelected'])   # 22 Oct, slot 20.


class AppResultReconfirmTests(unittest.TestCase):
    def test_sections_below_the_top_hit_may_rearrange_but_the_top_hit_may_not(self):
        import io
        from PIL import Image, ImageDraw
        from farm_draft_creation import still_compare
        def frame(box=None):
            image = Image.new('RGB', (500, 1080), (40, 50, 90))
            if box: ImageDraw.Draw(image).rectangle(box, fill=(250, 200, 20))
            out = io.BytesIO(); image.save(out, 'BMP'); return out.getvalue()
        compare = still_compare('app_result')
        self.assertEqual('ready', compare(frame(), {}, frame((0, 400, 499, 1040)), None)['state'])   # 22 Oct, slot 17.
        self.assertEqual('wait', compare(frame(), {}, frame((20, 90, 200, 240)), None)['state'])
        self.assertEqual('wait', still_compare('home')(frame(), {}, frame((0, 400, 499, 1040)), None)['state'])


class AgedDecisionRecheckTests(unittest.TestCase):
    """safari_or_blank and instagram_navigation decisions may be carried by a newer matching frame (A18, 4 Nov)."""
    @staticmethod
    def frame(box=None):
        import io
        from PIL import Image, ImageDraw
        image = Image.new('RGB', (500, 1080), (240, 240, 245))
        if box: ImageDraw.Draw(image).rectangle(box, fill=(30, 120, 220))
        out = io.BytesIO(); image.save(out, 'BMP'); return out.getvalue()

    def test_both_roles_get_a_still_compare_in_creation_and_reel_runs(self):
        from farm_draft_creation import CreationWorkflow
        from farm_reel_creation import ReelCreationWorkflow
        for role in ('safari_or_blank', 'instagram_navigation'):
            for flow in (CreationWorkflow, ReelCreationWorkflow):
                with self.subTest(role=role, flow=flow.__name__):
                    self.assertIsNotNone(flow.confirmation_compare(flow.__new__(flow), role))

    def test_instagram_feed_may_play_but_its_bars_may_not_change(self):
        from farm_draft_creation import still_compare
        compare = still_compare('instagram_navigation')
        self.assertEqual('ready', compare(self.frame(), {}, self.frame((0, 130, 499, 970)), None)['state'])   # Feed video.
        self.assertEqual('wait', compare(self.frame(), {}, self.frame((20, 990, 200, 1040)), None)['state'])    # Tab bar.
        self.assertEqual('wait', compare(self.frame(), {}, self.frame((20, 70, 200, 115)), None)['state'])      # Header.

    def test_safari_compares_the_whole_page(self):
        from farm_draft_creation import still_compare
        compare = still_compare('safari_or_blank')
        self.assertEqual('ready', compare(self.frame(), {}, self.frame(), None)['state'])
        self.assertEqual('wait', compare(self.frame(), {}, self.frame((20, 400, 300, 600)), None)['state'])


class SearchClearGlyphTests(unittest.TestCase):
    def test_the_white_clear_glyph_is_found_in_place_when_the_template_follows_the_wallpaper(self):
        import io
        from unittest import mock
        from PIL import Image, ImageDraw
        import farm_creation_layout as layout
        def frame(glyph):
            image = Image.new('RGB', (500, 1080), (60, 50, 110)); draw = ImageDraw.Draw(image)
            if glyph: draw.ellipse((434, 992, 458, 1018), fill='white'); draw.line((440, 998, 452, 1012), fill=(60, 50, 110), width=3)
            out = io.BytesIO(); image.save(out, 'BMP'); return out.getvalue()
        with mock.patch.object(layout, 'control', side_effect=InspectionStopped('wallpaper')):
            self.assertEqual([430, 988, 462, 1022], layout.search_clear(frame(True)))   # 22 Oct, slot 17.
            with self.assertRaises(InspectionStopped): layout.search_clear(frame(False))


class SendCopyShareSheetTests(unittest.TestCase):
    def test_rows_below_a_send_copy_row_are_read_at_their_own_height(self):
        import farm_reel_layout as reel
        rows = [('imouse-x-hctunh', 85, 519, 232, 534), ('Send Copy', 120, 566, 209, 583), ('Copy', 50, 795, 96, 814),
                ('Save Video', 50, 868, 151, 884), ('Add Tags', 50, 929, 134, 948), ('Save to Files', 50, 989, 163, 1005)]   # 22 Oct, slot 17.
        self.assertEqual((100, 876), reel.share_sheet(text(*rows), 'imouse-x-hctunh')['target'])
        wrong = [r if r[0] != 'Save Video' else ('Save Video', 50, 920, 151, 936) for r in rows]
        with self.assertRaises(InspectionStopped): reel.share_sheet(text(*wrong), 'imouse-x-hctunh')


class LinkMenuTests(unittest.TestCase):
    ROWS = [('Hide preview', 372, 100, 457, 114), ('Open', 120, 773, 168, 792), ('Open in New Tab', 120, 826, 274, 845),
            ('Download Linked File', 120, 879, 312, 895), ('Add to Reading List', 120, 932, 297, 952)]   # 22 Oct, slot 20 (private).

    def test_either_menu_height_and_a_leftover_menu_closes_beside_it(self):
        import farm_reel_layout as reel
        self.assertEqual((216, 887), reel.link_menu(text(*self.ROWS))['target'])
        normal = self.ROWS[:3] + [('Download Linked File', 120, 932, 312, 948), ('Add to Reading List', 120, 985, 297, 1005)]
        self.assertEqual((216, 940), reel.link_menu(text(*normal))['target'])
        self.assertEqual((50, 760), reel.leftover_link_menu(text(*self.ROWS))['closeTarget'])
        swapped = self.ROWS[:3] + [('Download Linked File', 120, 932, 312, 948), ('Add to Reading List', 120, 879, 297, 895)]
        with self.assertRaises(InspectionStopped): reel.link_menu(text(*swapped))


class SplitHeaderNameTests(unittest.TestCase):
    def test_a_name_split_into_two_words_is_joined_within_its_line(self):
        import farm_reel_layout as reel
        split = text(('Done', 426, 77, 474, 92))
        split['lines'].append(dict(text='imouse-x- hctunh', words=[dict(text='imouse-x-', x=152, y=76, width=90, height=16),
                                                                  dict(text='hctunh', x=248, y=76, width=68, height=16)]))   # 22 Oct, slot 17.
        self.assertEqual(['imouse-x-hctunh'], reel.header_names(split, reel.LEFTOVER_NAME))
        split['lines'][-1]['words'][1]['text'] = 'hctunz'
        self.assertEqual([], reel.header_names(split, reel.LEFTOVER_NAME))


class PrivateDownloadBadgeTests(unittest.TestCase):
    def test_the_white_download_glyph_in_the_dark_private_bar(self):
        import io
        from unittest import mock
        from PIL import Image, ImageDraw
        import farm_reel_layout as reel
        def frame(glyph):
            image = Image.new('RGB', (500, 1080), (245, 245, 247)); draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((35, 930, 465, 980), 20, fill=(70, 68, 72))
            if glyph: draw.ellipse((82, 946, 101, 965), fill='white')
            out = io.BytesIO(); image.save(out, 'BMP'); return out.getvalue()
        with mock.patch.object(reel, 'reel_control', side_effect=InspectionStopped('light-mode template')):
            self.assertEqual((91, 955), reel.download_badge(frame(True))['target'])   # 22 Oct, slot 20.
            with self.assertRaises(InspectionStopped): reel.download_badge(frame(False))
            import io as _io
            from PIL import Image as _Image, ImageDraw as _Draw
            with _Image.open(_io.BytesIO(frame(False))) as base: ringed = base.convert('RGB')
            _Draw.Draw(ringed).ellipse((80, 944, 103, 967), outline=(20, 120, 250), width=3)   # Still downloading (22 Oct).
            out = _io.BytesIO(); ringed.save(out, 'BMP')
            self.assertEqual((91, 955), reel.download_badge(out.getvalue())['target'])


class TikTokLaunchTests(unittest.TestCase):
    def test_the_launch_splash_is_waited_out_without_input(self):
        from types import SimpleNamespace
        from farm_tiktok_creation import TikTokCreationWorkflow
        flow = TikTokCreationWorkflow.__new__(TikTokCreationWorkflow); flow.record = {}; flow.pause = lambda s: None
        frames = iter([['TikTok'], ['TikTok'], ['Home', 'Friends', 'Inbox', 'Profile']])   # 22 Oct, slot 20.
        flow.kernel = SimpleNamespace(shot=lambda board: (b'f', {})); flow.phone = SimpleNamespace(board='C214')
        flow.store = SimpleNamespace(ocr=SimpleNamespace(read=lambda raw: text(*[(t, 40, 500, 200, 520) for t in next(frames)])))
        flow.await_launch()
        self.assertEqual([True, True, False], [w['splash'] for w in flow.record['launchWaits']])


class XComposerRowTests(unittest.TestCase):
    def test_an_avatar_joined_to_the_first_row_is_dropped_only_there(self):
        import farm_x_layout as xl
        self.assertEqual(["What's happening?"], xl.composer_rows(text(("O What's happening?", 25, 123, 260, 153))))   # 22 Oct, slot 17.
        self.assertEqual(['Fresh x acceptance'], xl.composer_rows(text(('O Fresh x acceptance', 25, 123, 260, 153))))
        self.assertEqual(['O Fresh x acceptance'], xl.composer_rows(text(('O Fresh x acceptance', 66, 123, 260, 153))))   # Typed, not joined.
        self.assertEqual([], xl.composer_rows(text(('Q Fresh', 25, 123, 260, 153))))


class TikTokGridTests(unittest.TestCase):
    def test_bright_rows_inside_a_short_last_row_are_not_gutters(self):
        import numpy as np
        import farm_tiktok_layout as tt
        image = np.full((1080, 500, 3), 60, dtype=np.uint8)
        for y in (301, 467, 635): image[y:y+2] = 255
        image[802:807] = 255                      # Gutter merged with white-topped thumbnails below.
        image[807:967, 333:] = 255                # The empty third cell.
        for y in (858, 911): image[y:y+2, :333] = 255   # White spacing inside the two test videos.
        image[967:] = 255
        image[:, 166:168] = 255; image[:, 332:334] = 255
        rows, bottom = tt.grid(image)   # 22 Oct, slot 20.
        self.assertEqual((967, [303, 469, 637, 807]), (bottom, [r['top'] for r in rows if r['complete']]))


class XComposerTipTests(unittest.TestCase):
    def test_a_tip_may_cover_the_reply_row_but_only_a_known_tip(self):
        from unittest import mock
        import farm_x_layout as xl
        base = [('Cancel', 26, 76, 87, 92), ("O What's happening?", 25, 123, 260, 153), ('O Everyone can', 22, 939, 151, 957)]
        with mock.patch.object(xl, 'pixels', lambda frame, exact=False: None):
            self.assertEqual((160, 140), xl.x_composer_empty(b'f', text(*base, ('Find awesome GIFs', 167, 953, 332, 968)))['textTarget'])   # 22 Oct.
            with self.assertRaises(InspectionStopped): xl.x_composer_empty(b'f', text(*base))
            full = [base[0], base[1], ('O Everyone can reply', 22, 939, 194, 957)]
            self.assertEqual((160, 140), xl.x_composer_empty(b'f', text(*full))['textTarget'])


class TikTokSelectionTests(unittest.TestCase):
    def test_the_badge_is_compared_without_the_tile_around_it(self):
        import base64, io, json
        from pathlib import Path
        import numpy as np
        from PIL import Image
        import farm_tiktok_layout as tt
        row = json.loads(Path(tt.__file__).with_name('farm_tiktok_controls.json').read_text(encoding='utf-8'))['tt_badge_one']
        with Image.open(io.BytesIO(base64.b64decode(row['png']))) as icon: badge = np.asarray(icon.convert('RGB')).copy()
        keep = ((badge[..., 0] > 180) & (badge[..., 1] < 90)) | (badge.min(axis=2) > 230)
        def frame(around, numeral=None):
            image = np.full((1080, 500, 3), around, dtype=np.uint8); patch = badge.copy(); patch[~keep] = around
            if numeral: patch[badge.min(axis=2) > 230] = numeral
            left, top = row['box'][:2]; image[top:top+patch.shape[0], left:left+patch.shape[1]] = patch
            out = io.BytesIO(); Image.fromarray(image).save(out, 'BMP'); return out.getvalue()
        for around in ((30, 120, 60), (200, 40, 40), (240, 240, 240)):   # 22 Oct, slot 20: another video's picture.
            with self.subTest(around=around): tt.control(frame(around), 'tt_badge_one')
        with self.assertRaises(InspectionStopped): tt.control(frame((30, 120, 60), numeral=(200, 30, 50)), 'tt_badge_one')
        drawn = frame((30, 120, 60))   # Drawn at the template's own circle (478, 678).
        for shift, expected in ((0, True), (1, True), (-1, True), (2, False), (-3, False)):   # 23 Oct: one pixel right.
            with self.subTest(shift=shift):
                self.assertEqual(expected, tt.badge_one(drawn, 478+shift, 678))

    def test_the_tray_colours_decide_only_a_narrow_miss(self):
        from unittest import mock
        import farm_tiktok_layout as tt
        stubs = dict(_picker_header=lambda f, t: None, line_at=lambda *a: True, words_at=lambda *a: True, control=lambda *a, **k: None,
                     pixels=lambda f, exact=False: __import__('numpy').full((1080, 500, 3), 255, dtype='uint8'), grid=lambda image: ([], 980),
                     _tiles=lambda image, rows: [((334, 657, 500, 820), True)], badge=lambda image, tile: True,
                     _tile_match=lambda *a: dict(matched=False))
        for mean, colours, expected in ((.091, True, True), (.091, False, False), (.2, True, False)):
            with self.subTest(mean=mean, colours=colours), mock.patch.multiple(tt, **stubs),                     mock.patch.object(tt, 'media_match', return_value=dict(matched=False, mean=mean)),                     mock.patch.object(tt, 'tray_colours', return_value=dict(matched=colours)):
                if expected: self.assertEqual((367, 1006), tt.tiktok_selected(b'f', text(), None)['target'])
                else:
                    with self.assertRaises(InspectionStopped): tt.tiktok_selected(b'f', text(), None)


class StartScreenSpotlightTests(unittest.TestCase):
    def test_a_restored_query_is_cleared_by_the_glyph_fallback(self):
        # A17, 4 Nov: Spotlight restored 'Safari'; the clear button's template missed, its glyph did not.
        from unittest import mock
        from types import SimpleNamespace
        import farm_creation_layout as layout
        from farm_start_screen import StartScreen
        start = StartScreen.__new__(StartScreen); taps = []; keys = []
        start.record = dict(commands=[], observations=[]); start.save = lambda: None; start.pause = lambda s: None
        start.command = lambda fun, purpose, **data: keys.append(purpose)
        start.tap = lambda raw, text, point, role, purpose, only=None: taps.append((purpose, point))
        start.control_center = lambda text: False
        frames = iter([(b'app', 'app'), (b'home', 'home'), (b'restored', 'restored'), (b'cleared', 'cleared'), (b'result', 'result'),
                       (b'after', 'after')])
        start.fresh = lambda role: (*next(frames), 0, 0)
        def app_target(text, name, frame=None):
            if text != 'result': raise InspectionStopped('no label')
            return (87, 163)
        def empty_search(text, frame=None):
            if text != 'cleared': raise InspectionStopped('restored query')
            return True
        def home(text, frame=None):
            if text != 'home': raise InspectionStopped('not home')
            return True
        with mock.patch.multiple(layout, app_target=app_target, empty_search=empty_search, home=home,
                                 home_search=lambda raw, text: [205, 879, 296, 920],
                                 search_clear=lambda raw: [430, 988, 462, 1022]),                 mock.patch.object(layout, 'control', side_effect=AssertionError('template only')):
            start.open_from_home('X')
        self.assertEqual(['open-app-search', 'clear-restored-search', 'open-x'], [p for p, _ in taps])
        self.assertEqual((446, 1005), taps[1][1])
        self.assertEqual(['home-before-start-screen', 'query-x'], keys)

    def test_home_is_never_sent_over_control_center_or_on_the_home_screen(self):
        # B5, 4 Nov: a Home over Control Center opened Settings; a Home on the Home screen opened Control Center.
        from unittest import mock
        import farm_creation_layout as layout
        from farm_start_screen import StartScreen
        def run(screens):
            start = StartScreen.__new__(StartScreen); keys = []; frames = iter(screens)
            start.record = dict(commands=[], observations=[]); start.save = lambda: None; start.pause = lambda s: None
            start.command = lambda fun, purpose, **data: keys.append(purpose)
            start.tap = lambda raw, text, point, role, purpose, only=None: keys.append(purpose)
            start.control_center = lambda text: text == 'cc'
            start.fresh = lambda role: (next(frames), next(frames), 0, 0)
            def home(text, frame=None):
                if text != 'home': raise InspectionStopped('not home')
                return True
            with mock.patch.multiple(layout, home=home, app_target=lambda text, name, frame=None: (87, 163)):
                try: start.open_from_home('X'); return 'opened', keys
                except InspectionStopped: return 'stopped', keys
        self.assertEqual(('stopped', []), run([b'cc', 'cc']))
        self.assertEqual(('opened', ['open-x']), run([b'h', 'home', b'a', 'after']))
        self.assertEqual(('opened', ['home-before-start-screen', 'open-x']), run([b'a', 'app', b'h', 'home', b'x', 'after']))
        self.assertEqual(('stopped', ['home-before-start-screen']), run([b'a', 'app', b'cc', 'cc']))


class StartScreenExitTests(unittest.TestCase):
    def test_a_stop_prints_its_summary_and_exits_non_zero(self):
        import io, json, sys, tempfile
        from contextlib import nullcontext, redirect_stdout
        from pathlib import Path
        from unittest import mock
        import farm_start_screen as fs
        class Tool:
            outcome = None
            def __init__(self, folder, phone=None): self.record = dict(state='started', commands=[])
            def to_x_timeline(self):
                if Tool.outcome == 'at_start': self.record['state'] = 'at_start'; return self.record
                if Tool.outcome == 'stopped': self.record.update(state='stopped', error='InspectionStopped: x'); raise InspectionStopped('x')
                raise ConnectionError('kernel gone')
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / 'c.json'; config.write_text('{}', encoding='utf-8')
            for outcome, code, state in (('at_start', None, 'at_start'), ('stopped', 1, 'stopped'), ('error', 1, 'stopped')):
                Tool.outcome = outcome; out = io.StringIO()
                with self.subTest(outcome=outcome), mock.patch.object(fs, 'StartScreen', Tool), mock.patch.object(fs, 'phone_of', lambda c: None), mock.patch('farm_rack_lock.hold_rack', lambda holder: nullcontext()),                         mock.patch.object(sys, 'argv', ['x', 'x-timeline', folder, str(config)]), redirect_stdout(out):
                    try: fs.main(); got = None
                    except SystemExit as exit: got = exit.code
                    self.assertEqual(code, got)
                    self.assertEqual(state, json.loads(out.getvalue().strip().splitlines()[-1])['state'])


class AppHomeStartScreenTests(unittest.TestCase):
    def start(self, screens):
        from types import SimpleNamespace
        from farm_start_screen import StartScreen
        start = StartScreen.__new__(StartScreen); frames = iter(screens); opened = []
        start.record = dict(commands=[], observations=[]); start.save = lambda: None; start.pause = lambda s: None
        start.kernel = SimpleNamespace(acquire=lambda boards, ms: {'B': 't'}, release=lambda tokens: None,
                                       renew_if_needed=lambda tokens, ms: None)
        start.phone = SimpleNamespace(board='B'); start.command = lambda *a, **k: None
        start.fresh = lambda role: (next(frames), None, 0, 0)
        start.open_from_home = lambda name: (opened.append(name), (next(frames), None, 0, 0))[1]
        return start, opened

    def test_the_app_is_opened_once_and_its_start_screen_waited_for(self):
        def check(raw, text):
            if raw != 'home': raise InspectionStopped('not yet')
        start, opened = self.start(['other', 'splash', 'home'])   # 22 Oct: YouTube and X start screens.
        self.assertEqual('at_start', start.to_app_home('YouTube', 'youtube_home', check)['state'])
        self.assertEqual(['YouTube'], opened)
        start, opened = self.start(['other', 'splash', 'splash', 'splash', 'splash'])
        with self.assertRaises(InspectionStopped): start.to_app_home('YouTube', 'youtube_home', check)
        self.assertEqual(['YouTube'], opened)

    def test_youtube_backs_out_of_its_draft_prompt_and_camera_once_each(self):
        # 26 Oct, slot 16: YouTube reopened on the Short camera, after a cold start with 'Continue your draft video?'.
        def check(raw, text):
            if raw != 'home': raise InspectionStopped('not yet')
        moves = {'prompt': ((254, 616), 'youtube_draft_prompt', 'start-over-saves-draft', ()),
                 'camera': ((44, 125), 'youtube_camera', 'close-short-camera', ())}
        def run(screens):
            start, _ = self.start(screens); taps = []
            start.tap = lambda raw, text, point, role, purpose, only=None: taps.append(purpose)
            try: return start.to_app_home('YouTube', 'youtube_home', check, back_out=lambda raw, text: moves.get(raw))['state'], taps
            except InspectionStopped: return 'stopped', taps
        self.assertEqual(('at_start', ['start-over-saves-draft', 'close-short-camera']),
                         run(['other', 'prompt', 'prompt', 'prompt', 'prompt', 'camera', 'home']))
        self.assertEqual(('at_start', ['close-short-camera']), run(['other', 'camera', 'camera', 'camera', 'camera', 'home']))
        # A tap that changes nothing is never repeated.
        self.assertEqual(('stopped', ['close-short-camera']), run(['other'] + ['camera'] * 8))
        self.assertEqual(('stopped', []), run(['other', 'feed', 'feed', 'feed', 'feed']))


class YouTubeLabelledBarTests(unittest.TestCase):
    def frame(self, plus=True):
        import io
        from PIL import Image, ImageDraw
        image = Image.new('RGB', (500, 1080), 'white'); draw = ImageDraw.Draw(image)
        draw.ellipse((229, 990, 271, 1032), fill=(236, 236, 236))
        if plus: draw.rectangle((249, 1001, 250, 1021), fill=(12, 12, 12)); draw.rectangle((239, 1011, 261, 1011), fill=(12, 12, 12))
        out = io.BytesIO(); image.save(out, 'BMP'); return out.getvalue()

    def test_the_labelled_five_item_bar_is_a_home_feed_with_its_own_plus(self):
        from unittest import mock
        import farm_youtube_layout as yl
        screen = text(('YouTube', 58, 74, 132, 96), ('Home', 38, 1022, 67, 1030), ('Shorts', 134, 1022, 168, 1031),
                      ('Subscriptions', 312, 1022, 384, 1032))   # 22 Oct, slot 16.
        with mock.patch.object(yl, 'control', lambda frame, name: None), mock.patch.object(yl, 'no_overlay', lambda text: None):
            found = yl.yt_home(self.frame(), screen)
            self.assertEqual(((250, 1011), 'labelled'), (found['createTarget'], found['navLayout']))
            with self.assertRaises(InspectionStopped): yl.yt_home(self.frame(plus=False), screen)
            partial = text(('YouTube', 58, 74, 132, 96), ('Home', 38, 1022, 67, 1030))   # Labels, but not this bar.
            with mock.patch.object(yl, 'control', side_effect=InspectionStopped('unlabelled templates')), self.assertRaises(InspectionStopped):
                yl.yt_home(self.frame(), partial)


class PointerBlobTests(unittest.TestCase):
    def test_only_a_lone_grey_pointer_sized_change_is_ignored(self):
        import numpy as np
        from farm_start_screen import pointer_blob
        a = np.ones((1080, 500, 3)); mask = np.ones((1080, 500), dtype=bool)
        b = a.copy(); b[100:122, 162:184] = 160 / 255   # 724E's pointer settling from its reset spot (22 Oct).
        self.assertTrue(pointer_blob(a, b, mask)[110, 170])
        c = a.copy(); c[100:122, 162:184] = (1.0, .1, .1)   # A red badge of the same size is a real change.
        self.assertFalse(pointer_blob(a, c, mask).any())
        d = b.copy(); d[500:560, 100:300] = 0                # Anything larger than the dot is never ignored.
        self.assertFalse(pointer_blob(a, d, mask).any())


class CaretAndClippedRowTests(unittest.TestCase):
    def test_a_caret_read_before_the_placeholder_still_means_empty(self):
        from farm_creation_layout import safari_address_empty
        self.assertTrue(safari_address_empty(text(('(Search or enter website name', 35, 943, 310, 963)))['addressEmpty'])   # 22 Oct.
        with self.assertRaises(InspectionStopped): safari_address_empty(text(('example.com', 35, 943, 140, 963)))

    def test_one_clipped_side_row_is_tolerated_but_never_the_target(self):
        import farm_reel_layout as reel
        rows = [('imouse-x-fxpxuu', 85, 521, 230, 539), ('Copy', 50, 797, 96, 816), ('Save Video', 50, 870, 151, 886),
                ('Add Tags', 50, 931, 134, 950), ('ave to Files', 62, 991, 163, 1007)]   # 22 Oct, slot 17.
        self.assertEqual((100, 878), reel.share_sheet(text(*rows), 'imouse-x-fxpxuu')['target'])
        clipped_target = [r if r[0] != 'Save Video' else ('ave Video', 62, 870, 151, 886) for r in rows]
        with self.assertRaises(InspectionStopped): reel.share_sheet(text(*clipped_target), 'imouse-x-fxpxuu')
        two_missing = [r for r in rows if r[0] != 'Add Tags']
        with self.assertRaises(InspectionStopped): reel.share_sheet(text(*two_missing), 'imouse-x-fxpxuu')


class TikTokPickerNearMissTests(unittest.TestCase):
    def test_a_narrow_miss_is_selected_only_by_its_tile_colours(self):
        from unittest import mock
        import numpy as np
        import farm_tiktok_layout as tt
        tiles = [((167, 807, 332, 967), True), ((0, 807, 166, 967), True)]
        means = {167: .060, 0: .292}   # 22 Oct, slot 20: the newest test video and an older one.
        stubs = dict(_picker_header=lambda f, t: None, line_at=lambda *a: True, control=lambda *a, **k: None,
                     red_fraction=lambda image, box: 1.0, pixels=lambda f, exact=False: np.full((1080, 500, 3), 255, dtype='uint8'),
                     grid=lambda image: ([], 967), _tiles=lambda image, rows: tiles, badge=lambda image, tile: False,
                     _tile_match=lambda frame, tile, ref, image: dict(matched=False, mean=means[tile[0]]))
        for colours, expected in ((True, (310, 828)), (False, None)):
            with self.subTest(colours=colours), mock.patch.multiple(tt, **stubs),                     mock.patch.object(tt, 'tile_colours', lambda image, box, ref: dict(matched=colours and box[0] == 169)):
                if expected: self.assertEqual(expected, tt.tiktok_picker(b'f', text(), None)['target'])
                else:
                    with self.assertRaises(InspectionStopped): tt.tiktok_picker(b'f', text(), None)


class LeftoverPlayerTests(unittest.TestCase):
    def frame(self, top, middle, bottom, overlay=False):
        import io
        from PIL import Image, ImageDraw
        image = Image.new('RGB', (500, 1080), middle); draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 499, 95), fill=top); draw.rectangle((0, 986, 499, 1079), fill=bottom)
        if overlay:   # 22 Oct, slot 18: play glyph, grey scrubber and home indicator; OCR read no '10'.
            draw.polygon(((233, 530), (233, 575), (273, 552)), fill='white')
            draw.rectangle((42, 986, 458, 996), fill=(90, 90, 90)); draw.rectangle((160, 1063, 340, 1068), fill='white')
        out = io.BytesIO(); image.save(out, 'BMP'); return out.getvalue()

    def test_the_overlay_is_known_by_its_play_glyph_when_ocr_misses_it(self):
        from farm_creation_layout import leftover_player
        self.assertTrue(leftover_player(self.frame('black', (200, 200, 200), 'black', overlay=True), {'lines': []})['leftoverPlayer'])
        bare = self.frame('black', (200, 200, 200), 'black', overlay=True)
        from PIL import Image; import io
        with Image.open(io.BytesIO(bare)) as image:
            image = image.copy(); image.paste((200, 200, 200), (225, 520, 285, 585)); out = io.BytesIO(); image.save(out, 'BMP')
        with self.assertRaises(InspectionStopped): leftover_player(out.getvalue(), {'lines': []})   # Scrubber alone is not enough.

    def test_only_black_bars_around_a_bright_picture_count(self):
        from farm_creation_layout import leftover_player
        self.assertTrue(leftover_player(self.frame('black', (240, 240, 235), 'black'))['leftoverPlayer'])
        for top, middle, bottom in (('white', (240, 240, 235), 'black'), ('black', 'black', 'black'), ('black', (240, 240, 235), 'white')):
            with self.subTest(top=top, middle=middle, bottom=bottom), self.assertRaises(InspectionStopped):
                leftover_player(self.frame(top, middle, bottom))


class XVideoEditorTests(unittest.TestCase):
    ROWS = [('x', 39, 81, 55, 97), ('Edit Video', 203, 80, 297, 97), ('Next', 422, 83, 460, 96), ('Trim', 58, 1023, 89, 1035),
            ('Text', 147, 1023, 177, 1035), ('Cover', 230, 1023, 271, 1036), ('Settings', 309, 1023, 367, 1038),
            ('Save', 409, 1023, 444, 1036)]   # 23 Oct, slot 17's new account, after Add.

    def test_next_is_the_target_and_save_is_fenced_off(self):
        import farm_x_layout as xl
        from farm_x_creation import FORBIDDEN
        tip = [('Text gives your video context', 31, 890, 286, 909), ("Sa what it's about in a few words", 31, 916, 292, 929)]
        self.assertEqual((441, 90), xl.x_video_editor(b'f', text(*self.ROWS, *tip))['nextTarget'])
        self.assertIn(xl.EDITOR_SAVE, FORBIDDEN['x_video_editor'])
        left, top, right, bottom = xl.EDITOR_SAVE
        self.assertTrue(left <= 426 <= right and top <= 1030 <= bottom)   # The Save label's centre.
        for missing in ('Next', 'Save', 'Edit Video'):
            with self.subTest(missing=missing), self.assertRaises(InspectionStopped):
                xl.x_video_editor(b'f', text(*[r for r in self.ROWS if r[0] != missing]))


class DownloadSizeBandTests(unittest.TestCase):
    def test_a_missed_size_line_is_read_from_the_row_enlarged(self):
        from unittest import mock
        import farm_reel_layout as reel
        rows = text(('Done', 27, 523, 75, 538), ('Downloads', 199, 522, 303, 538), ('Clear', 428, 522, 475, 538),
                    ('moUse-X-vtrmva', 94, 587, 248, 601), ('mouse', 94, 682, 150, 697))   # 23 Oct: no '31 KB' line.
        band = [('imouse-x-vtrmva', 94, 586, 248, 600), ('31', 94, 614, 110, 624), ('KB', 113, 615, 133, 624)]
        with self.assertRaises(InspectionStopped): reel.downloads_list(rows, 'imouse-x-vtrmva', 31166)   # No frame: refused.
        with mock.patch.object(reel, 'band_words', return_value=band):
            self.assertEqual('31 KB', reel.downloads_list(rows, 'imouse-x-vtrmva', 31166, b'f')['size'])
            with self.assertRaises(InspectionStopped): reel.downloads_list(rows, 'imouse-x-vtrmva', 34242, b'f')
        with mock.patch.object(reel, 'band_words', return_value=band[:1]), self.assertRaises(InspectionStopped):
            reel.downloads_list(rows, 'imouse-x-vtrmva', 31166, b'f')   # Still nothing below the name.


class YouTubeSelectedTileTests(unittest.TestCase):
    def test_the_top_border_may_sit_one_pixel_lower(self):
        import numpy as np
        import farm_youtube_layout as yl
        tile = (0, 212, 164, 503)
        def image(top_rows):
            a = np.full((1080, 500, 3), 170, dtype=np.uint8); a[212:503, 1:3] = 255; a[212:503, 161:163] = 255
            for y in top_rows: a[y, 5:159] = 255
            return a
        self.assertTrue(yl.border(image((213, 214)), tile))
        self.assertTrue(yl.border(image((214, 215)), tile))   # 23 Oct, slot 16's shifted gallery.
        self.assertFalse(yl.border(image((216, 217)), tile))
        self.assertFalse(yl.border(image(()), tile))

    def test_only_a_plausible_dark_veil_is_lifted_inside_the_tile(self):
        from unittest import mock
        import numpy as np
        import farm_youtube_layout as yl
        tile = (0, 212, 164, 503); seen = []
        def match(frame, box, ref, image):
            seen.append(image); return dict(matched=bool(image[300, 80, 0] > 240), mean=0.0)
        veiled = np.full((1080, 500, 3), 40, dtype=np.uint8); veiled[212:503, 0:164] = 178   # White under the veil.
        with mock.patch.object(yl, '_tile_match', match):
            found = yl._veiled_match(b'f', tile, None, veiled)
            self.assertTrue(found['matched']); self.assertAlmostEqual(1.43, found['veilGain'], places=2)
            self.assertEqual(40, seen[-1][100, 300, 0])   # Outside the tile nothing changes.
            plain = veiled.copy(); plain[212:503, 0:164] = 255
            self.assertEqual('no_veil', yl._veiled_match(b'f', tile, None, plain)['status'])
            dark = veiled.copy(); dark[212:503, 0:164] = 90
            self.assertEqual('no_veil', yl._veiled_match(b'f', tile, None, dark)['status'])


class YouTubeBlankTitleTests(unittest.TestCase):
    def test_a_clipped_placeholder_is_read_again_enlarged(self):
        from unittest import mock
        import numpy as np
        import farm_youtube_layout as yl
        stubs = dict(no_overlay=lambda *a: None, words_at=lambda text, word, box: word != 'title', exact=lambda *a: None,
                     control=lambda *a, **k: None, line_at=lambda text, label, box: label != 'processing', handle=lambda text: 'channel',
                     pixels=lambda f, exact=False: np.full((1080, 500, 3), 255, dtype=np.uint8),
                     media_match=lambda *a, **k: dict(matched=True))
        clipped = text(('Caption y', 134, 151, 210, 170))   # 23 Oct, slot 16.
        placeholder = [('Caption', 134, 151, 200, 170), ('your', 205, 151, 240, 170), ('Short', 245, 151, 297, 170)]
        with mock.patch.multiple(yl, **stubs):
            with mock.patch.object(yl, 'band_words', return_value=placeholder):
                self.assertEqual('blank', yl.yt_details(b'f', clipped, None, state='blank')['state'])
            with mock.patch.object(yl, 'band_words', return_value=[('Fresh', 134, 151, 180, 170)]), self.assertRaises(InspectionStopped):
                yl.yt_details(b'f', clipped, None, state='blank')


class TikTokSoundPillTests(unittest.TestCase):
    def test_the_x_is_found_along_a_shorter_pill(self):
        from unittest import mock
        import farm_tiktok_layout as tt
        for hits, expected in (({-31}, -31), ({0}, 0), ({-32, -31, -30}, -31), (set(), None), ({-31, 20}, None)):
            with self.subTest(hits=hits), mock.patch.object(tt, 'present', lambda frame, name, offset=(0, 0): offset[0] in hits):
                self.assertEqual(expected, tt.sound_remove(b'f'))


class DiscardLeftoverTests(unittest.TestCase):
    def test_only_the_exact_dialogs_give_a_discard_target(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'analysis' / 'farm-multiphone-20261020'))
        from discard_leftover import discard_target
        tiktok = [('Discard', 66, 166, 134, 186), ('Save draft', 66, 224, 159, 243)]   # 23 Oct, slot 20.
        self.assertEqual((100, 176), discard_target(text(*tiktok), 'tiktok')[0])
        x = [('Save to drafts', 180, 455, 320, 480), ('Discard', 210, 528, 290, 552), ('Keep editing', 190, 595, 315, 620)]
        self.assertEqual((250, 540), discard_target(text(*x), 'x')[0])
        two = [('Save to drafts', 181, 498, 318, 515), ('Discard', 213, 565, 287, 582)]   # 4 Nov, slot 17: no Keep editing.
        self.assertEqual((250, 574), discard_target(text(*two), 'x')[0])
        for rows in ([('Discard', 213, 498, 287, 515), ('Save to drafts', 181, 565, 318, 582)], two[1:], [x[0], x[1], ('Keep editing', 190, 500, 315, 520)], two + [('Discard', 213, 640, 287, 657)]):
            with self.subTest(rows=rows), self.assertRaises(InspectionStopped): discard_target(text(*rows), 'x')
        youtube = [('Discard changes?', 107, 482, 298, 505), ('Cancel', 249, 610, 302, 623), ('Discard', 334, 610, 393, 623)]
        self.assertEqual((364, 616), discard_target(text(*youtube), 'youtube')[0])   # 23 Oct, slot 16.
        swapped = [youtube[0], ('Discard', 249, 610, 312, 623), ('Cancel', 334, 610, 393, 623)]
        with self.assertRaises(InspectionStopped): discard_target(text(*swapped), 'youtube')
        reordered = [('Discard', 66, 224, 134, 243), ('Save draft', 66, 166, 159, 186)]
        for rows, dialog in ((reordered, 'tiktok'), (tiktok[:1], 'tiktok'), (tiktok + tiktok[:1], 'tiktok'), (tiktok, 'x')):
            with self.subTest(rows=rows, dialog=dialog), self.assertRaises(InspectionStopped):
                discard_target(text(*rows), dialog)


class XEditedCardTests(unittest.TestCase):
    def test_the_larger_card_after_edit_video_is_matched_in_its_own_box(self):
        from unittest import mock
        import farm_x_layout as xl
        rows = text(('Cancel', 26, 76, 87, 92), ('Fresh x acceptance', 66, 127, 262, 150), ('Post', 420, 76, 456, 92),
                    ('Tag people', 104, 708, 182, 724), ('Everyone can reply', 49, 939, 194, 957))   # 23 Oct, slot 17.
        def media(boxes):
            return lambda frame, box, ref, model, image=None, ignore=(): dict(matched=box in boxes, mean=.03)
        stubs = dict(_composer=lambda frame, text: __import__('numpy').zeros((1080, 500, 3)), words_at=lambda *a: True)
        with mock.patch.multiple(xl, **stubs):
            with mock.patch.object(xl, 'media_match', media({xl.EDITED_CARD})):
                self.assertEqual('edited', xl.x_composer_media(b'f', rows, None)['media']['card'])
            with mock.patch.object(xl, 'media_match', media({xl.CARD})):
                self.assertNotIn('card', xl.x_composer_media(b'f', rows, None)['media'])
            with mock.patch.object(xl, 'media_match', media(set())), self.assertRaises(InspectionStopped):
                xl.x_composer_media(b'f', rows, None)


class SaveVideoRowTests(unittest.TestCase):
    def test_a_garbled_target_row_is_read_again_enlarged_and_must_be_exact(self):
        from unittest import mock
        import farm_reel_layout as reel
        rows = [('imouse-x-dyayke', 85, 519, 233, 537), ('Send Copy', 120, 566, 209, 583), ('Copy', 50, 795, 96, 814),
                ('Save V o', 50, 868, 151, 884), ('Add Tags', 50, 929, 134, 948), ('Save to Files', 50, 989, 163, 1005)]   # 23 Oct, slot 17.
        with self.assertRaises(InspectionStopped): reel.share_sheet(text(*rows), 'imouse-x-dyayke')   # No frame: refused.
        read = lambda *words: mock.patch.object(reel, 'band_words', return_value=list(words))
        with read(('Save', 50, 868, 93, 884), ('Video', 99, 868, 151, 884)):
            self.assertEqual((100, 876), reel.share_sheet(text(*rows), 'imouse-x-dyayke', b'f')['target'])
        for words in ((('Save', 50, 868, 93, 884),), (('ave', 62, 868, 93, 884), ('Video', 99, 868, 151, 884)),
                      (('Save', 50, 868, 93, 884), ('Video', 99, 868, 190, 884))):   # Short, clipped, or past the row.
            with self.subTest(words=words), read(*words), self.assertRaises(InspectionStopped):
                reel.share_sheet(text(*rows), 'imouse-x-dyayke', b'f')


class SheetPendingTests(unittest.TestCase):
    def test_the_preview_header_after_share_means_wait_not_stop(self):
        import farm_reel_layout as reel
        preview = text(('imouse-x-xpftup', 155, 76, 314, 95), ('Done', 426, 77, 474, 92), ('Open in VLC', 131, 1004, 243, 1024))   # 23 Oct, slot 17.
        with self.assertRaises(reel.SheetPending): reel.share_sheet(preview, 'imouse-x-xpftup')
        other = text(('imouse-x-aaaaaa', 155, 76, 314, 95), ('Done', 426, 77, 474, 92))
        with self.assertRaises(InspectionStopped) as stop: reel.share_sheet(other, 'imouse-x-xpftup')
        self.assertNotIsInstance(stop.exception, reel.SheetPending)   # Another file's preview is a real stop.


class XDraftsLoadingTests(unittest.TestCase):
    def test_a_spinner_alone_means_loading(self):
        import numpy as np
        import farm_x_layout as xl
        image = np.full((1080, 500, 3), 255, dtype=np.uint8)
        image[600:620, 240:260] = 150                       # Spinner.
        image[290:310, 437:457] = 150                       # Parked pointer, left out.
        self.assertTrue(xl.drafts_loading(image))
        image[214:290, 405:475] = 60                        # A row's thumbnail: not loading.
        self.assertFalse(xl.drafts_loading(image))

    def test_a_row_without_its_thumbnail_waits(self):
        from unittest import mock
        import numpy as np
        import farm_x_layout as xl
        rows = text(('Cancel', 26, 91, 87, 107), ('Drafts', 222, 91, 279, 107), ('Scheduled', 327, 148, 403, 161),
                    ('Fresh x acceptance', 21, 214, 186, 232))
        with mock.patch.object(xl, 'pixels', lambda f, exact=False: np.full((1080, 500, 3), 255, dtype=np.uint8)):
            with self.assertRaises(xl.Loading): xl.x_drafts(b'f', rows, None, 'Fresh x acceptance')


class XPlayButtonTests(unittest.TestCase):
    def test_the_triangle_on_its_disc_is_the_paused_card(self):
        import numpy as np
        import farm_x_layout as xl
        image = np.full((1080, 500, 3), 200, dtype=np.uint8)
        image[396:468, 178:250] = 100                       # Dark disc.
        image[420:446, 206:230] = 255                       # Triangle.
        self.assertTrue(xl.play_button(image))
        gutter = np.full((1080, 500, 3), 200, dtype=np.uint8); gutter[:, 212:216] = 255   # The video's white gutter only.
        self.assertFalse(xl.play_button(gutter))


class YouTubeProcessingTests(unittest.TestCase):
    def test_processing_is_awaited_like_the_caret(self):
        import farm_youtube_layout as yl
        with self.assertRaises(yl.Processing): yl.yt_details(b'f', text(('Processing', 206, 556, 295, 572)), None, 'x', state='titled')
        self.assertTrue(issubclass(yl.Processing, yl.CaretVisible))


class TikTokLargeCoverTests(unittest.TestCase):
    def test_the_larger_card_is_tried_only_after_the_usual_one(self):
        from unittest import mock
        import numpy as np
        import farm_tiktok_layout as tt
        seen = []
        def media(frame, box, ref, model, image=None, ignore=()):
            seen.append(box); return dict(matched=box == (345, 120, 480, 318), mean=.04)
        stubs = dict(no_overlay=lambda *a: None, words_at=lambda text, word, box: word not in ('back', 'cancel'),
                     line_at=lambda *a: True, exact=lambda *a: None, control=lambda *a, **k: None, detail_rows=lambda text: 0,
                     red_fraction=lambda *a: 1.0, caret_visible=lambda image: False,
                     rows_between=lambda *a: ['Add description...'],
                     pixels=lambda f, exact=False: np.full((1080, 500, 3), 255, dtype=np.uint8), media_match=media)
        with mock.patch.multiple(tt, **stubs):
            self.assertEqual('large', tt.tiktok_details(b'f', text(), None)['cover']['card'])
        self.assertEqual([(345, 122, 475, 313), (345, 120, 480, 318)], seen)


class TikTokGutterChainTests(unittest.TestCase):
    def test_thin_white_rows_inside_test_videos_lose_to_real_gutters(self):
        import numpy as np
        import farm_tiktok_layout as tt
        image = np.full((1080, 500, 3), 60, dtype=np.uint8)
        for y in (210, 378, 545): image[y:y+1] = 255             # 1 px rows inside white thumbnails (24 Oct).
        for y, h in ((321, 5), (489, 4), (655, 2)): image[y:y+h] = 255   # Real gutters.
        image[820:845] = 255                                      # Selection tray.
        image[:, 164:168] = 255; image[:, 331:335] = 255
        rows, bottom = tt.grid(image)
        self.assertEqual((820, [326, 493, 657]), (bottom, [r['top'] for r in rows if r['complete']]))


class CloseAppEvidenceTests(unittest.TestCase):
    """close_app reports 'closed' only when the swiped card's pixels are gone (A20, 4 Nov check 4: three swipes
    changed nothing, 'Following' was simply not read again, and it reported closed)."""
    @staticmethod
    def frames():
        import io
        import numpy as np
        from PIL import Image
        rng = np.random.default_rng(5)
        base = np.full((1080, 500), 120, np.uint8)
        card = rng.integers(0, 255, (560, 160), dtype=np.uint8)
        def png(array):
            out = io.BytesIO(); Image.fromarray(array).save(out, 'PNG'); return out.getvalue()
        def at(x, alpha=1.0):
            image = base.copy(); part = image[180:740, x:x+160].astype(float)
            image[180:740, x:x+160] = (alpha*card[:, :500-x] + (1-alpha)*part).astype(np.uint8) if x+160 > 500 else (alpha*card + (1-alpha)*part).astype(np.uint8)
            return png(image)
        other = rng.integers(0, 255, (1080, 500), dtype=np.uint8)   # What the switcher shows once the card is gone.
        return at, png(other)

    def module(self):
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'analysis' / 'farm-multiphone-20261020'))
        import close_app
        return close_app

    def test_card_pixels_decide_gone_present_or_unclear(self):
        close_app = self.module(); at, empty = self.frames()
        before = at(320)
        self.assertEqual('present', close_app.card_gone(before, before, 320)['verdict'])
        slid = close_app.card_gone(before, at(200), 320)
        self.assertEqual(('present', -120), (slid['verdict'], slid['offset']))
        self.assertEqual('gone', close_app.card_gone(before, empty, 320)['verdict'])
        self.assertEqual('unclear', close_app.card_gone(before, at(320, .5), 320)['verdict'])

    def run_close(self, after_frames, after_texts):
        from unittest import mock
        close_app = self.module(); at, _ = self.frames()
        following = dict(text='Following', words=[dict(text='Following', x=453, y=300, width=40, height=12)])
        texts = iter([dict(width=500, height=1080, lines=[following])] + after_texts)
        frames = iter([at(320)] + after_frames)
        sent = []
        class Screen:
            def __init__(self, folder, phone=None):
                self.phone = mock.MagicMock(board='C214', device_id='d'); self.record = dict(commands=[])
                self.kernel = mock.MagicMock(); self.kernel.acquire.return_value = {'C214': 't'}
            def fresh(self, role): return next(frames), next(texts), 0, 0
            def command(self, fun, purpose, **data): sent.append(purpose)
            def pause(self, seconds): pass
            def save(self): pass
        def post(base, fun, data): sent.append(fun); return dict(code=0)
        with mock.patch.object(close_app, 'StartScreen', Screen), mock.patch.object(close_app, 'post', post), \
                mock.patch.object(close_app, 'phone_of', lambda config: None):
            result = close_app.close(dict(), 'folder', 'TikTok')
        return result, sent

    def test_a_card_not_read_again_but_still_there_is_never_closed(self):
        at, _ = self.frames(); blank = dict(width=500, height=1080, lines=[])
        result, sent = self.run_close([at(320)] * 3, [blank] * 3)
        self.assertEqual('stopped', result['state']); self.assertEqual(3, sent.count('/mouse/swipe'))
        self.assertNotIn('home-after-close', sent)

    def test_a_card_gone_from_the_switcher_is_closed(self):
        _, empty = self.frames(); blank = dict(width=500, height=1080, lines=[])
        result, sent = self.run_close([empty], [blank])
        self.assertEqual('closed', result['state']); self.assertEqual(1, sent.count('/mouse/swipe')); self.assertIn('home-after-close', sent)

    def test_a_partial_match_stops_as_not_proven(self):
        at, _ = self.frames(); blank = dict(width=500, height=1080, lines=[])
        result, sent = self.run_close([at(320, .5)], [blank])
        self.assertEqual('stopped', result['state']); self.assertIn('not proven', result['error'])


if __name__ == '__main__':
    unittest.main()
