import unittest
from farm_observations import classify
from test_farm_observations import ocr_lines


class ScreenRecognitionTests(unittest.TestCase):
    def setUp(self):
        self.expected = {'platform': 'instagram', 'account': 'test.account', 'caption': 'DRAFT ONLY'}
        self.caption = [('Caption', 76), ('# Hashtags', 255), ('Poll', 258), ('Prompt', 259),
                        ('Original audio', 808), ('Save draft', 991), ('Share', 991), ('DRAFT ONLY', 496)]
        self.photo = [('Preview', 77), ('Location', 615), ('Add link', 728), ('Everyone can view this post', 790),
                      ('O More options', 849), ('Share to', 915), ('Drafts', 997), ('O Post', 994), ('DRAFT ONLY', 324)]

    def test_caption_sheet_is_an_editing_interruption_not_background_details(self):
        screen = ocr_lines(*self.caption, ('New reel', 85))
        result = classify(screen, self.expected)
        self.assertEqual('caption_editor', result['screen'])
        self.assertEqual('needs_review', result['captionStatus']); self.assertEqual('not_visible', result['accountStatus'])
        self.assertFalse(result['automaticInputAllowed'])

    def test_photo_draft_details_without_video_edit_cover(self):
        result = classify(ocr_lines(*self.photo), {**self.expected, 'platform': 'tiktok'})
        self.assertEqual('draft_details', result['screen']); self.assertEqual('tiktok', result['appPattern'])
        self.assertEqual('exact_line_match', result['captionStatus']); self.assertEqual('not_visible', result['accountStatus'])

    def test_isolated_caption_words_do_not_fake_a_photo_details_screen(self):
        displaced = [(word, 400 + i * 20) for i, (word, _) in enumerate(self.photo)]
        self.assertEqual('unknown', classify(ocr_lines(*displaced), self.expected)['screen'])
        for missing in ('Preview', 'Share to', 'Drafts', 'O Post', 'O More options'):
            with self.subTest(missing=missing):
                screen = ocr_lines(*[(word, y) for word, y in self.photo if word != missing])
                self.assertEqual('unknown', classify(screen, self.expected)['screen'])

    def test_video_details_use_independent_anchors_without_repairing_ocr(self):
        screen = ocr_lines(('Cancel', 77), ('Preview', 134), ('Edit cover', 289), ('Everyone can view this post', 605),
                           ('Share to', 730), ('Drafts', 997), ('ost', 998), ('DRAFT', 132), ('ONLY', 154))
        result = classify(screen, {**self.expected, 'platform': 'tiktok'})
        self.assertEqual('draft_details', result['screen'])
        self.assertEqual('needs_review', result['captionStatus'])
        self.assertFalse(result['automaticInputAllowed'])

    def test_system_permission_overrides_caption_sheet(self):
        result = classify(ocr_lines(*self.caption, ("Don't Allow", 640), ('Allow', 690)), self.expected)
        self.assertEqual('permission_prompt', result['screen']); self.assertIsNone(result['appPattern'])

    def test_carousel_details_excludes_slide_text_from_caption(self):
        screen = ocr_lines(('New post', 77), ('Add audio', 640), ('Tag people', 754), ('Add location', 814),
                           ('Add AI Label', 867), ('Share', 990), ('DRAFT ONLY', 370), ('Caption test', 461))
        result = classify(screen, self.expected)
        self.assertEqual(('draft_details', 'instagram', 'carousel_details'),
                         (result['screen'], result['appPattern'], result['layout']))
        self.assertEqual('needs_review', result['captionStatus'])
        self.assertEqual('exact_line_match', classify(screen, {**self.expected, 'caption': 'Caption test'})['captionStatus'])
        self.assertEqual('not_visible', result['accountStatus']); self.assertFalse(result['automaticInputAllowed'])
        for missing in ('New post', 'Add audio', 'Tag people', 'Add location', 'Add AI Label', 'Share'):
            without = {**screen, 'lines': [line for line in screen['lines'] if line['text'] != missing]}
            with self.subTest(missing=missing): self.assertEqual('unknown', classify(without, self.expected)['screen'])

    def test_sparse_drafts_title_does_not_identify_instagram(self):
        result = classify(ocr_lines(('Drafts', 77), ('Select', 78), ('DRAFT ONLY', 212)), self.expected)
        self.assertEqual('unknown', result['screen']); self.assertIsNone(result['appPattern'])

    def test_truncated_suggested_audio_requires_the_complete_carousel_toolbar(self):
        toolbar=[(word,921) for word in ('Audio','Overlay','Filter','Edit','Ratio')]
        for label in ('Suggested a...','Suggested...','Suggested a…','Suggested…'):
            screen=ocr_lines(*toolbar,(label,102),('ext',1001))
            result=classify(screen,self.expected)
            self.assertEqual('carousel_editor',result['layout'])
            self.assertEqual('not_visible',result['accountStatus'])
            self.assertFalse(result['automaticInputAllowed'])
            self.assertFalse(result['savedDraftVerified'])
        for missing in ('Audio','Overlay','Filter','Edit','Ratio'):
            without={**screen,'lines':[row for row in screen['lines'] if row['text']!=missing]}
            with self.subTest(missing=missing): self.assertEqual('unknown',classify(without,self.expected)['screen'])

    def test_truncated_label_outside_audio_region_or_partial_next_stays_unknown(self):
        toolbar=[(word,921) for word in ('Audio','Overlay','Filter','Edit','Ratio')]
        for labels in ([('Suggested a...',500),('ext',1001)], [('ext',1001)], [('Suggested',102)]):
            self.assertEqual('unknown',classify(ocr_lines(*toolbar,*labels),self.expected)['screen'])

    def test_known_ui_label_variant_never_changes_caption_or_account_text(self):
        screen = ocr_lines(('New post', 77), ('Add audio', 640), ('Tag people', 754), ('Add location', 814),
                           ('Add Al Label', 867), ('Share', 990), ('Al test', 461), ('@test.account', 483))
        result = classify(screen, {**self.expected, 'caption': 'AI test'})
        self.assertEqual('draft_details', result['screen']); self.assertEqual('needs_review', result['captionStatus'])
        self.assertEqual('not_visible', result['accountStatus'])

    def test_caption_comparison_does_not_use_navigation_or_footer_text(self):
        screen = ocr_lines(('New reel', 75), ('Save draft', 991), ('Share', 991))
        for caption in ('New reel', 'Save draft', 'Share'):
            self.assertEqual('needs_review', classify(screen, {**self.expected, 'caption': caption})['captionStatus'])

    def test_geometry_scales_but_invalid_geometry_is_refused(self):
        screen = ocr_lines(*self.photo)
        for line in screen['lines']:
            for word in line['words']:
                for key in ('x', 'y', 'width', 'height'): word[key] *= 2
        screen.update(width=1000, height=2160)
        self.assertEqual('draft_details', classify(screen, self.expected)['screen'])
        for value in (float('nan'), -1, 99999):
            screen['lines'][0]['words'][0]['y'] = value
            with self.assertRaises(ValueError): classify(screen, self.expected)


if __name__ == '__main__': unittest.main()
