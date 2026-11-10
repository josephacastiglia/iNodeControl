"""Permission prompt recognition and policy. Synthetic cases always run; retained frames when present."""
import inspect
import json
import unittest

import farm_permission_prompts as pp

import farm_paths  # noqa: E402  (the archive beside the main folder, also from a lane worktree)
ARCHIVE = farm_paths.ARCHIVE
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
        proven = {('local_network', 'long_press'): ('validated', 'fixture')}
        answered = pp.plan(prompt, validated=proven)
        self.assertEqual(('answer', 'long_press', (168, 808)), (answered['action'], answered['method'], answered['target']))
        # A method validated in a window but not yet sendable by runs stops with the one-time request.
        waiting = pp.plan(prompt, validated={('local_network', 'absolute_tap'): ('validated', 'fixture'),
                                             ('local_network', 'keyboard_focus'): ('validated', 'fixture')})
        self.assertEqual(('stop', None), (waiting['action'], waiting['method']))
        self.assertEqual('Validated but not usable for this answer in a run: absolute_tap, keyboard_focus.', waiting['reason'])
        self.assertIn('one-time step per phone and app', waiting['request'])
        # An ignored method never counts as proven.
        self.assertEqual('stop', pp.plan(prompt, validated={('local_network', 'pointer_tap'): ('ignored', 'x')})['action'])
        # Escape only ever reaches an alert's cancel action, so it never gives an allowing answer.
        photos = pp.detect(alert('Allow "TikTok" to access', 'your photos?', buttons=(('Limit Access...', 120, 700),
                           ('Allow Full Access', 120, 760), ("Don't Allow", 120, 820))))
        escape = {('photos', 'keyboard_escape'): ('validated', 'fixture'), ('local_network', 'keyboard_escape'): ('validated', 'fixture')}
        self.assertEqual('stop', pp.plan(photos, needs_media_picker=True, app_expected='TikTok', validated=escape)['action'])
        self.assertEqual('keyboard_escape', pp.plan(prompt, validated=escape)['method'])

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


class ReminderTests(unittest.TestCase):
    """20 Oct (coordinator, rack phones): "<App> has been able to access your entire photo library ...
    continue to allow full access?" with Limit Access / Allow Full Access."""
    def reminder(self, *extra):
        return pp.detect(alert('"Instagram" has been able to access', 'your entire photo library.', 'Do you want to continue to',
                               'allow full access?', buttons=(('Limit Access', 120, 760), ('Allow Full Access', 120, 820), *extra)))

    def test_the_reminder_keeps_the_current_setting(self):
        found = self.reminder()
        self.assertEqual(('photos_reminder', 'Instagram'), (found['kind'], found['app']))
        stop = pp.plan(found, app_expected='Instagram')
        self.assertEqual(('stop', 'Allow Full Access'), (stop['action'], stop['answer']))
        self.assertIn('keeps the current setting', stop['request'])
        proven = {('photos_reminder', 'pointer_tap'): ('validated', 'fixture')}
        # No media picker is needed, and keeping the setting is safe even for another app.
        for context in (dict(), dict(app_expected='Instagram'), dict(app_expected='TikTok')):
            with self.subTest(**context):
                self.assertEqual(('answer', 'Allow Full Access'), (pp.plan(found, validated=proven, **context)['action'],
                                                                   pp.plan(found, validated=proven, **context)['answer']))
        # Escape could reach Limit Access, which changes the setting: never used here.
        self.assertEqual('stop', pp.plan(found, validated={('photos_reminder', 'keyboard_escape'): ('validated', 'fixture')})['action'])
        # A Don't Allow means this is not the reminder; it is not answered.
        odd = self.reminder(("Don't Allow", 120, 880))
        self.assertEqual(('photos_reminder', 'stop'), (odd['kind'], pp.plan(odd, validated=proven)['action']))

    def test_ellipsis_variants_read_as_the_same_button(self):
        first = pp.detect(alert('Allow "TikTok" to access', 'your photos?', buttons=(('Limit Access…', 120, 700),
                                ('Allow Full Access', 120, 760), ("Don't Allow", 120, 820))))
        self.assertEqual('photos', first['kind']); self.assertIn('Limit Access...', first['buttons'])
        self.assertIn('Limit Access', self.reminder()['buttons'])


class EvidenceTests(unittest.TestCase):
    prompt = staticmethod(lambda: pp.detect(alert('Allow "YouTube" to find', 'devices on local networks?')))

    def test_nothing_is_validated_by_default(self):
        self.assertFalse([key for key, (state, _) in pp.EVIDENCE.items() if state == 'validated'])
        self.assertEqual('stop', pp.plan(self.prompt())['action'])
        self.assertEqual(['keyboard_escape', 'pointer_tap'], pp.plan(self.prompt())['ignoredMethods'])

    def test_safe_answers_and_run_methods(self):
        self.assertEqual(set(pp.POLICY) - {'unknown_permission'}, set(pp.SAFE_ANSWER))
        self.assertTrue(set(pp.SAFE_ANSWER.values()) <= set(pp.BUTTONS) and set(pp.CANCEL_ANSWERS) <= set(pp.SAFE_ANSWER.values()))
        # Every safe answer grants nothing new: a declining button, or keeping existing full access.
        self.assertEqual({'photos_reminder'}, {f for f, a in pp.SAFE_ANSWER.items() if a not in pp.CANCEL_ANSWERS})
        self.assertTrue(set(pp.RUN_METHODS) <= set(pp.METHODS))
        # RUN_METHODS is exactly what the shared run answer path implements.
        from farm_reel_creation import ReelCreationWorkflow
        source = inspect.getsource(ReelCreationWorkflow.answer_prompt)
        self.assertEqual(set(pp.RUN_METHODS), {m for m in pp.METHODS if f"'{m}'" in source})

    def test_button_boxes(self):
        text = alert('Allow "YouTube" to find', 'devices on local networks?')
        self.assertEqual({"Don't Allow": (118, 800, 217, 816), 'Allow': (307, 800, 352, 816)}, pp.button_boxes(text))
        twice = alert('x', buttons=(("Don't Allow", 118, 800), ("Don't Allow", 118, 860)))
        self.assertIsNone(pp.button_boxes(twice))


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
