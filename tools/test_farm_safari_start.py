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
                     reel_control=lambda f, n: None, video_match=lambda *a, **k: dict(matched=True))
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
        start, taps = self.screen(text(*self.EDITOR), text(*self.DIALOG), text(*self.PICKER), text(('xs.halle.xo', 150, 90, 260, 110)))
        self.assertTrue(start.reel_details(details) and not start.reel_details(text(*self.EDITOR)))
        start.close_new_reel(b'before', details)
        self.assertEqual(['details-back', 'close-reel-editor', 'start-over-1', 'close-new-reel'], [p for p, _ in taps])
        self.assertEqual((30, 84), taps[0][1])
        start, taps = self.screen(text(*self.PICKER))
        with self.assertRaises(InspectionStopped): start.close_reel_details(b'before', details)   # Back must reach the editor.

    def test_anything_but_the_picker_after_the_close_stops(self):
        start, taps = self.screen(text(('Discard edits?', 150, 450, 350, 470), ('Discard', 200, 520, 300, 540)))

        with self.assertRaises(InspectionStopped): start.close_reel_editor(b'before', text(*self.EDITOR))
        self.assertEqual(1, len(taps))


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


if __name__ == '__main__':
    unittest.main()
