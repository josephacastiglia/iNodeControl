"""Permission prompt recognition and policy. Synthetic cases always run; retained frames when present."""
import hashlib
import inspect
import json
from pathlib import Path
import unittest
from unittest.mock import patch

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


def window_entry(**changes):
    """A complete validation-window record for a declined local-network prompt."""
    entry = dict(family='local_network', method='long_press', state='validated', answer="Don't Allow", app='YouTube', phone='C24C',
                 source=pp.WINDOW_SOURCE, date='2026-10-21', trial='6f1c1d52-6a0e-4f4c-8a39-2f2a8f3e9b10',
                 summary=pp.WINDOW_RECORD + 'a3-long-press.json', summarySha256='1'*64, beforeFrameSha256='2'*64,
                 afterFrameSha256='3'*64, outcome='dismissed', commandsAnswered=True, declinedConfirmed=True,
                 confirmation='Settings > Privacy > Local Network shows YouTube off', note='fixture')
    entry.update(changes)
    return entry


class WindowEvidenceTests(unittest.TestCase):
    prompt = staticmethod(lambda: pp.detect(alert('Allow "YouTube" to find', 'devices on local networks?')))

    def test_nothing_is_validated_by_default(self):
        self.assertEqual((), pp.WINDOW_EVIDENCE)
        self.assertFalse([key for key, (state, _) in pp.evidence().items() if state == 'validated'])
        self.assertEqual('stop', pp.plan(self.prompt())['action'])

    def test_complete_window_evidence_validates_its_family_and_method_only(self):
        self.assertEqual([], pp.window_problems(window_entry()))
        with patch.object(pp, 'WINDOW_EVIDENCE', (window_entry(),)):
            decision = pp.plan(self.prompt())
            self.assertEqual(('answer', 'long_press', "Don't Allow"), (decision['action'], decision['method'], decision['answer']))
            self.assertIn('C24C window trial', decision['evidence'])
            other = pp.detect(alert('Allow "YouTube" to use your location?'))
            self.assertEqual('stop', pp.plan(other)['action'])

    def test_incomplete_or_contradicted_evidence_never_validates(self):
        broken = {
            'allow button': dict(answer='Allow'), 'not confirmed': dict(declinedConfirmed=False), 'no confirmation text': dict(confirmation=' '),
            'ignored outcome': dict(outcome='ignored'), 'uncertain command': dict(commandsAnswered=False),
            'outside the record': dict(summary='analysis/other/a3.json'), 'path escape': dict(summary=pp.WINDOW_RECORD + '../x.json'),
            'no summary hash': dict(summarySha256='abc'), 'no frame hash': dict(afterFrameSha256=None), 'other phone': dict(phone='C241'),
            'other source': dict(source='simulation'), 'unknown family': dict(family='unknown_permission'),
            'unknown method': dict(method='voice'), 'no date': dict(date='today'), 'no trial': dict(trial='a3'), 'other state': dict(state='likely'),
        }
        for name, change in broken.items():
            with self.subTest(name):
                self.assertTrue(pp.window_problems(window_entry(**change)))
                with patch.object(pp, 'WINDOW_EVIDENCE', (window_entry(**change),)):
                    self.assertEqual('stop', pp.plan(self.prompt())['action'])
        self.assertTrue(pp.window_problems('validated'))
        ignored = window_entry(state='ignored', outcome='ignored', declinedConfirmed=False, confirmation='')
        self.assertEqual([], pp.window_problems(ignored))
        for entries in ((ignored,), (window_entry(), ignored), (window_entry(method='pointer_tap'),)):
            with self.subTest(entries=len(entries)), patch.object(pp, 'WINDOW_EVIDENCE', entries):
                self.assertEqual('stop', pp.plan(self.prompt())['action'])
        with patch.object(pp, 'WINDOW_EVIDENCE', (ignored,)):
            self.assertEqual(['keyboard_escape', 'long_press', 'pointer_tap'], pp.plan(self.prompt())['ignoredMethods'])
        with patch.object(pp, 'WINDOW_EVIDENCE', (window_entry(), ignored)):
            self.assertEqual('conflicting', pp.evidence()[('local_network', 'long_press')][0])

    def test_committed_window_evidence_matches_its_recorded_summaries(self):
        for entry in pp.WINDOW_EVIDENCE:
            with self.subTest(trial=entry.get('trial')):
                self.assertEqual([], pp.window_problems(entry))
                summary = ROOT/entry['summary']
                self.assertEqual(entry['summarySha256'], hashlib.sha256(summary.read_bytes()).hexdigest())
                recorded = json.loads(summary.read_text(encoding='utf-8'))
                self.assertEqual((entry['trial'], entry['family'], entry['method'], 'phone'),
                                 (recorded['trial'], recorded['family'], recorded['method'], recorded['recordSource']))

    def test_declining_buttons_and_run_methods(self):
        self.assertEqual(set(pp.POLICY) - {'unknown_permission'}, set(pp.DECLINING))
        self.assertTrue(set(pp.DECLINING.values()) <= set(pp.BUTTONS))
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
