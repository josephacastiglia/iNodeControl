"""Permission prompt recognition and policy. Synthetic cases always run; retained frames when present."""
import json
from pathlib import Path
import unittest

import farm_permission_prompts as pp

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT.parent/'iMouseXP-2.0-evidence-archive'
RETAINED = ('20261019-farm-reel-offline', '20261019-farm-tiktok-offline', '20261019-farm-x-offline', '20261020-farm-youtube-offline')
PRIVATE = all((ARCHIVE/name/'ocr-20261017').is_dir() for name in RETAINED)


def ocr(*rows):
    lines = []
    for text, x, y in rows:
        lines.append(dict(text=text, words=[dict(text=text, x=x, y=y, width=max(8, len(text)*9), height=16)]))
    return dict(width=500, height=1080, lines=lines)


def alert(*body, buttons=(("Don't Allow", 118, 800), ('Allow', 307, 800))):
    rows = [(line, 110, 290 + 22*i) for i, line in enumerate(body)]
    return ocr(*rows, *buttons)


class PromptTests(unittest.TestCase):
    def test_families_apps_and_buttons(self):
        cases = [
            (alert('Allow "YouTube" to find', 'devices on local networks?'), 'local_network', 'YouTube'),
            (alert('“TikTok” Would Like to', 'Send You Notifications'), 'notifications', 'TikTok'),
            (alert('Allow "X" to track your activity across', "other companies' apps and websites?",
                   buttons=(('Ask App Not to Track', 120, 760), ('Allow', 230, 820))), 'tracking', 'X'),
            (alert('Allow "Instagram" to access', 'your photos?', buttons=(('Limit Access...', 120, 700), ('Allow Full Access', 120, 760),
                                                                       ("Don't Allow", 120, 820))), 'photos', 'Instagram'),
            (alert('"TikTok" would like to paste from', '"Safari"', buttons=(("Don't Allow Paste", 120, 800), ('Allow Paste', 300, 800))),
             'paste', 'TikTok'),
            (alert('Allow "YouTube" to use your location?'), 'location', 'YouTube'),
            (alert('"App" Needs Something New'), 'unknown_permission', None),
        ]
        for text, kind, app in cases:
            with self.subTest(kind=kind):
                found = pp.detect(text)
                self.assertEqual((kind, app), (found['kind'], found['app']))
        self.assertEqual((168, 808), pp.detect(cases[0][0])['buttons']["Don't Allow"])
        self.assertIsNone(pp.detect(ocr(('Allow notifications from friends', 40, 300), ('Next', 400, 1000))))
        self.assertIsNone(pp.detect(ocr(('Drafts', 118, 997), ('Post', 360, 997))))

    def test_policy_never_answers_without_a_validated_method(self):
        prompt = pp.detect(alert('Allow "YouTube" to find', 'devices on local networks?'))
        result = pp.plan(prompt)
        self.assertEqual(('stop', "Don't Allow", None), (result['action'], result['answer'], result['method']))
        self.assertIn('one-time step per phone and app', result['request'])
        self.assertEqual(['keyboard_escape', 'pointer_tap'], result['ignoredMethods'])
        proven = {('local_network', 'absolute_tap'): ('validated', 'fixture')}
        answered = pp.plan(prompt, validated=proven)
        self.assertEqual(('answer', 'absolute_tap', (168, 808)), (answered['action'], answered['method'], answered['target']))
        # An ignored method never counts as proven.
        self.assertEqual('stop', pp.plan(prompt, validated={('local_network', 'pointer_tap'): ('ignored', 'x')})['action'])

    def test_context_limits_privileged_answers(self):
        photos = pp.detect(alert('Allow "TikTok" to access', 'your photos?', buttons=(('Limit Access...', 120, 700),
                           ('Allow Full Access', 120, 760), ("Don't Allow", 120, 820))))
        proven = {('photos', 'pointer_tap'): ('validated', 'fixture'), ('paste', 'pointer_tap'): ('validated', 'fixture')}
        self.assertEqual('stop', pp.plan(photos, validated=proven)['action'])
        self.assertEqual('Allow Full Access', pp.plan(photos, needs_media_picker=True, app_expected='TikTok', validated=proven)['answer'])
        self.assertEqual('stop', pp.plan(photos, needs_media_picker=True, app_expected='Instagram', validated=proven)['action'])
        paste = pp.detect(alert('"TikTok" would like to paste from', '"Safari"',
                                buttons=(("Don't Allow Paste", 120, 800), ('Allow Paste', 300, 800))))
        self.assertEqual('stop', pp.plan(paste, validated=proven)['action'])
        self.assertEqual('answer', pp.plan(paste, after_own_paste=True, validated=proven)['action'])

    def test_unreadable_or_ambiguous_buttons_stop(self):
        proven = {('local_network', 'pointer_tap'): ('validated', 'fixture')}
        hidden = pp.detect(alert('Allow "YouTube" to find', 'devices on local networks?', buttons=(('Allow', 307, 800),)))
        self.assertEqual(('stop', 'The policy answer is not visible on this prompt.'), (pp.plan(hidden, validated=proven)['action'],
                                                                                     pp.plan(hidden, validated=proven)['reason']))
        twice = pp.detect(alert('Allow "YouTube" to find', 'devices on local networks?',
                                buttons=(("Don't Allow", 118, 800), ("Don't Allow", 118, 860), ('Allow', 307, 800))))
        self.assertTrue(twice['ambiguous']); self.assertEqual('stop', pp.plan(twice, validated=proven)['action'])


@unittest.skipUnless(PRIVATE, 'Retained private C24C OCR is not available in this checkout.')
class RetainedPromptTests(unittest.TestCase):
    def test_only_the_retained_prompt_frames_are_detected(self):
        found, total = {}, 0
        for name in RETAINED:
            for path in sorted((ARCHIVE/name/'ocr-20261017').glob('*.json')):
                total += 1
                prompt = pp.detect(json.loads(path.read_text(encoding='utf-8')))
                if prompt: found[path.name] = prompt
        self.assertGreater(total, 400)
        self.assertEqual({'132', '133', '134', '135'}, {name.split('-')[0] for name in found})
        self.assertTrue(all(p['kind'] == 'local_network' and p['app'] == 'YouTube' for p in found.values()))
        result = pp.plan(found['132-youtube-loaded__after.json'], app_expected='YouTube')
        self.assertEqual(('stop', "Don't Allow"), (result['action'], result['answer']))
        # With the pointer over the button OCR loses its label: the run still stops, never guesses.
        self.assertNotIn("Don't Allow", found['133-youtube-decline-network__pointer.json']['buttons'])


if __name__ == '__main__':
    unittest.main()
