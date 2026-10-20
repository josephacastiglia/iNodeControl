"""Prompt-validation window steps against a synthetic C24C stand-in. No socket, phone or service.

The fixture draws iOS-style alerts, a pointer and a Full Keyboard Access highlight. It tests
the protocol and the guards (declining button only, one method once, no replay, lease cleanup,
evidence wiring), not how iOS treats any input.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import farm_test_network  # noqa: F401  Refuse every real socket in this process.
import farm_permission_prompts as prompts
import farm_prompt_validation as pv
from farm_carousel_inspection import InspectionStopped
from farm_observations import ObservationStore
from farm_prompt_fixture import FixtureOcr, PromptPhone
from imouse_social_automation import KernelSafetyError, LIVE_TEST_DEVICE_ID

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT/'analysis/farm-prompt-validation-20261020'


def semantic(phone):
    """Every phone input except the runs' fresh-frame and parking moves."""
    return [c for c in phone.calls if isinstance(c, tuple) and not (c[0] == '/mouse/move' and (c[1]['x'], c[1]['y']) in pv.CHALLENGES)]


class Steps(unittest.TestCase):
    def step(self, phone, probe=False, expected='a'*64):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        folder = Path(temporary.name)
        store = ObservationStore(folder/'observations.sqlite3', ocr=FixtureOcr(phone), clock=phone.clock, monotonic=phone.clock)
        return pv.ValidationStep(folder/'step', phone, store, expected, 'fixture-uid', probe=probe,
                                 monotonic=phone.clock, pause=phone.pause, clock=phone.clock)

    def trial(self, method, activate=True, **options):
        phone = PromptPhone(**options)
        step = self.step(phone)
        return step.trial(method, activate=activate), phone, step


class TransportTests(unittest.TestCase):
    def kernels(self):
        sent = []
        def transport(method, target, body, timeout):
            sent.append(body)
            return json.dumps({'status': 200, 'data': {'code': 0, 'results': [{'id': LIVE_TEST_DEVICE_ID, 'code': 0}]}}).encode(), {}
        return pv.TrialKernel(transport=transport), pv.ProbeKernel(transport=transport), sent

    def test_trial_transport_sends_only_the_reviewed_inputs(self):
        trial, probe, sent = self.kernels()
        for fun, data in (('/mouse/move', dict(x=168, y=808)), ('/mouse/click', dict(x=168, y=808, button=1)),
                          ('/mouse/down', dict(button=1)), ('/mouse/up', dict(button=1)), ('/mouse/reset', {}),
                          ('/key/sendkey', dict(fn_key='Tab')), ('/key/sendkey', dict(fn_key='Escape')), ('/key/sendkey', dict(key=' '))):
            trial.send(LIVE_TEST_DEVICE_ID, 'token', fun, **data)
        self.assertEqual(8, len(sent))
        for fun, data in (('/key/sendkey', dict(fn_key='Enter')), ('/key/sendkey', dict(fn_key='ENTER')), ('/key/sendkey', dict(fn_key='Home')),
                          ('/key/sendkey', dict(key='\r')), ('/key/sendkey', dict(key='  ')), ('/key/sendkey', dict(key='a')),
                          ('/key/sendkey', dict(key=' ', fn_key='Tab')), ('/mouse/swipe', dict(direction='up')),
                          ('/mouse/click', dict(x=10, y=10, button=2)), ('/device/usb/restart', {}), ('/input/stop', {})):
            with self.subTest(fun=fun, data=data), self.assertRaises(KernelSafetyError):
                trial.send(LIVE_TEST_DEVICE_ID, 'token', fun, **data)
        with self.assertRaises(KernelSafetyError): trial.send('C241', 'token', '/mouse/move', x=1, y=1)
        self.assertEqual(8, len(sent))

    def test_probe_transport_sends_moves_only(self):
        _, probe, sent = self.kernels()
        probe.send(LIVE_TEST_DEVICE_ID, 'token', '/mouse/move', x=250, y=540)
        for fun, data in (('/mouse/click', dict(x=1, y=1, button=1)), ('/mouse/down', dict(button=1)), ('/mouse/reset', {}),
                          ('/key/sendkey', dict(fn_key='Tab')), ('/key/sendkey', dict(key=' '))):
            with self.subTest(fun=fun), self.assertRaises(KernelSafetyError): probe.send(LIVE_TEST_DEVICE_ID, 'token', fun, **data)
        self.assertEqual(1, len(sent))

    def test_only_the_isolated_kernel_port(self):
        for url in ('http://127.0.0.1:9913/api', 'http://127.0.0.1:9911/api', 'http://192.168.1.2:9916/api'):
            with self.subTest(url=url), self.assertRaises(KernelSafetyError): pv.TrialKernel(url)


class TrialTests(Steps):
    def test_class_check_tap_is_the_runs_settled_tap_on_the_declining_button(self):
        record, phone, step = self.trial('pointer_tap')
        self.assertEqual(('completed', 'ignored', 'confirmed'), (record['state'], record['result'], record['cleanup']))
        self.assertEqual([('/mouse/reset', {}), ('/mouse/move', dict(x=168, y=809)), ('/mouse/click', dict(x=168, y=809, button=1))],
                         semantic(phone))
        self.assertEqual("Don't Allow", record['prompt']['declining']); self.assertIsNone(phone.answered)
        self.assertEqual('release', phone.calls[-1]); self.assertFalse(phone.owned)
        self.assertTrue((step.folder/'record.json').is_file())
        self.assertTrue(all((step.folder/o['frame']).is_file() for o in record['observations'] if o.get('frame')))

    def test_long_press_and_escape_send_what_the_run_sends(self):
        record, phone, _ = self.trial('long_press', answers={'long_press'})
        self.assertEqual(('dismissed', "Don't Allow"), (record['result'], phone.answered))
        self.assertEqual([('/mouse/reset', {}), ('/mouse/move', dict(x=168, y=809)), ('/mouse/down', dict(button=1)),
                          ('/mouse/up', dict(button=1))], semantic(phone))
        record, phone, _ = self.trial('keyboard_escape')
        self.assertEqual('ignored', record['result'])
        self.assertEqual([('/mouse/reset', {}), ('/key/sendkey', dict(fn_key='Escape'))], semantic(phone))

    def test_long_press_holds_like_the_run(self):
        pauses = []
        phone = PromptPhone(answers={'long_press'})
        original = phone.pause
        def pause(seconds): pauses.append((len(phone.calls), seconds)); original(seconds)
        phone.pause = pause
        step = self.step(phone); step.pause = pause
        step.trial('long_press')
        down = next(i for i, c in enumerate(phone.calls) if c[0] == '/mouse/down')
        self.assertIn((down, .6), pauses); self.assertIn((down + 1, 1.1), pauses)

    def test_keyboard_focus_presses_space_only_on_the_verified_declining_focus(self):
        for style in ('fill', 'ring'):
            with self.subTest(style=style):
                record, phone, _ = self.trial('keyboard_focus', answers={'keyboard_focus'}, focus_style=style)
                self.assertEqual(('dismissed', "Don't Allow", 'space_sent_on_declining_focus'),
                                 (record['result'], phone.answered, record['focusResult']))
                keys = [c[1] for c in phone.calls if isinstance(c, tuple) and c[0] == '/key/sendkey']
                self.assertEqual([dict(fn_key='Tab'), dict(fn_key='Tab'), dict(key=' ')], keys)
                self.assertEqual([('focused', 'Allow'), ('focused', "Don't Allow")], [(s['state'], s['button']) for s in record['focusPath']])
                space = next(c for c in record['commands'] if c['purpose'] == 'activate-declining-focus')
                self.assertLessEqual(space['decisionChecks'][-1]['ageMs'], pv.FOCUS_MAX_AGE_MS)

    def test_keyboard_focus_on_a_stacked_location_prompt(self):
        # iOS 18's location alert also has a Precise: On control; focus there is not an answer.
        record, phone, _ = self.trial('keyboard_focus', prompt='location', answers={'keyboard_focus'},
                                      focus_order=('Precise: On', 'Allow Once', 'Allow While Using App', "Don't Allow"))
        self.assertEqual(('dismissed', "Don't Allow"), (record['result'], phone.answered))
        self.assertEqual('stacked', record['prompt']['layout'])
        self.assertEqual([('focus_elsewhere', None), ('focused', 'Allow Once'), ('focused', 'Allow While Using App'),
                          ('focused', "Don't Allow")], [(s['state'], s['button']) for s in record['focusPath']])

    def test_keyboard_focus_never_sends_space_without_a_verified_declining_focus(self):
        cases = [
            (dict(fka=False), 'no_visible_focus', 'ignored'),
            (dict(focus_order=('Allow',)), 'declining_never_focused', 'declining_never_focused'),
            (dict(focus_order=('body', 'Allow')), 'declining_never_focused', 'declining_never_focused'),
        ]
        for options, focus, result in cases:
            with self.subTest(options=options):
                record, phone, _ = self.trial('keyboard_focus', answers={'keyboard_focus'}, **options)
                keys = [c[1] for c in phone.calls if isinstance(c, tuple) and c[0] == '/key/sendkey']
                self.assertNotIn(dict(key=' '), keys); self.assertEqual(pv.MAX_TABS, len(keys))
                self.assertEqual((focus, result, None), (record['focusResult'], record['result'], phone.answered))

    def test_a_highlight_left_from_an_earlier_trial_stops_as_ambiguous(self):
        phone = PromptPhone(answers={'keyboard_focus'}, focus_auto_hide=None)
        self.assertEqual('declining_focused_not_activated', self.step(phone).trial('keyboard_focus', activate=False)['result'])
        second = self.step(phone).trial('keyboard_focus')
        self.assertEqual('stopped', second['result']); self.assertIn('ambiguous', second['error']); self.assertIsNone(phone.answered)
        # With C24C's 1 s Auto-Hide the highlight is gone before the next trial's unfocused frame.
        phone = PromptPhone(answers={'keyboard_focus'})
        self.step(phone).trial('keyboard_focus', activate=False)
        self.assertEqual('dismissed', self.step(phone).trial('keyboard_focus')['result'])
        self.assertEqual("Don't Allow", phone.answered)

    def test_focus_only_run_finds_the_focus_and_stops(self):
        record, phone, _ = self.trial('keyboard_focus', activate=False, answers={'keyboard_focus'})
        self.assertEqual('declining_focused_not_activated', record['result'])
        self.assertNotIn(dict(key=' '), [c[1] for c in phone.calls if isinstance(c, tuple)]); self.assertIsNone(phone.answered)

    def test_stale_focus_frame_sends_no_space(self):
        record, phone, _ = self.trial('keyboard_focus', answers={'keyboard_focus'}, focus_order=("Don't Allow",), stale_after_tab=True)
        self.assertEqual(('review_required', 'stopped'), (record['state'], record['result']))
        self.assertIn('DecisionExpired', record['error'])
        self.assertNotIn(dict(key=' '), [c[1] for c in phone.calls if isinstance(c, tuple)])
        self.assertEqual('not_sent', record['commands'][-1]['state']); self.assertEqual('confirmed', record['cleanup'])

    def test_ambiguous_focus_stops_before_space(self):
        record, phone, step = self.trial('keyboard_focus', answers={'keyboard_focus'}, focus_order=("Don't Allow",))
        self.assertEqual('dismissed', record['result'])   # Control: the clean case answers.
        with patch.object(pv, 'focused_button', lambda *a: dict(state='ambiguous', button=None, scores={}, textChange=0)):
            record, phone, _ = self.trial('keyboard_focus', answers={'keyboard_focus'}, focus_order=("Don't Allow",))
        self.assertEqual('stopped', record['result']); self.assertIn('no Space was sent', record['error'])
        self.assertNotIn(dict(key=' '), [c[1] for c in phone.calls if isinstance(c, tuple)])

    def test_nothing_is_sent_without_a_recognized_prompt_and_its_declining_button(self):
        for options in (dict(prompt=None), dict(busy=True), dict(kernel_hash='b'*64), dict(probe=True)):
            with self.subTest(options=options):
                record, phone, _ = self.trial('long_press', answers={'long_press'}, **options)
                self.assertEqual(('review_required', 'stopped'), (record['state'], record['result']))
                self.assertEqual([], [c for c in phone.calls if isinstance(c, tuple)]); self.assertIsNone(phone.answered)

    def test_a_pointer_resting_on_the_answer_is_parked_before_the_target_is_read(self):
        # The resting pointer hides "Don't Allow" from OCR (17 Oct); the family is still recognized.
        record, phone, _ = self.trial('long_press', answers={'long_press'}, pointer=(168, 809))
        self.assertEqual(('local_network', 'YouTube', "Don't Allow"), tuple(record['precheck'][k] for k in ('kind', 'app', 'declining')))
        self.assertEqual(('/mouse/reset', {}), semantic(phone)[0])
        self.assertEqual(('dismissed', "Don't Allow", [168, 809]), (record['result'], phone.answered, list(record['prompt']['target'])))
        observed = PromptPhone(pointer=(168, 809)); summary = self.step(observed).observe()
        self.assertEqual(('local_network', None), (summary['detected']['kind'], summary['prompt']))
        self.assertIn('not read', summary['promptReason']); self.assertEqual([], observed.calls)

    def test_lost_reply_stays_uncertain_and_nothing_follows(self):
        record, phone, _ = self.trial('long_press', answers={'long_press'}, lose_reply=lambda fun, data: fun == '/mouse/up')
        self.assertEqual(('review_required', 'uncertain'), (record['state'], record['result']))
        self.assertEqual('outcome_unknown', record['commands'][-1]['state'])
        self.assertEqual(['/mouse/up', 'release'], [c if isinstance(c, str) else c[0] for c in phone.calls[-2:]])
        self.assertEqual('confirmed', record['cleanup'])

    def test_receiver_change_stops_before_more_input(self):
        record, phone, _ = self.trial('long_press', answers={'long_press'}, receiver_change_after=3)
        self.assertEqual('review_required', record['state'])
        self.assertLessEqual(len([c for c in phone.calls if isinstance(c, tuple)]), 3); self.assertEqual('release', phone.calls[-1])

    def test_cancel_at_the_dispatch_journal_sends_nothing_for_that_action(self):
        for purpose in ('long-press-position', 'long-press-press', 'long-press-release'):
            with self.subTest(purpose=purpose):
                phone = PromptPhone(answers={'long_press'}); step = self.step(phone)
                original = step.save
                def save():
                    original()
                    commands = step.record['commands']
                    if commands and commands[-1]['purpose'] == purpose and commands[-1]['state'] == 'outcome_unknown':
                        step.cancelled.set()
                step.save = save
                record = step.trial('long_press')
                self.assertEqual(('stopped', 'not_sent', None), (record['result'], record['commands'][-1]['state'], phone.answered))
                self.assertEqual(purpose, record['commands'][-1]['purpose']); self.assertEqual('confirmed', record['cleanup'])
        phone = PromptPhone(answers={'long_press'}); step = self.step(phone)
        (step.folder/'STOP').write_text('stop')
        self.assertEqual('stopped', step.trial('long_press')['result'])
        self.assertEqual([], [c for c in phone.calls if isinstance(c, tuple)])

    def test_a_step_is_never_replayed(self):
        phone = PromptPhone(); step = self.step(phone); step.observe()
        store = ObservationStore(step.folder/'again.sqlite3', ocr=FixtureOcr(phone))
        with self.assertRaises(InspectionStopped): pv.ValidationStep(step.folder, phone, store, 'a'*64, 'fixture-uid')

    def test_observe_is_read_only(self):
        for name in ('local_network', 'paste', 'location'):
            with self.subTest(prompt=name):
                phone = PromptPhone(name); record = self.step(phone).observe()
                self.assertEqual(prompts.DECLINING[name], record['prompt']['declining'])
                self.assertEqual([], phone.calls)


class ProbeTests(Steps):
    def probe(self, **options):
        phone = PromptPhone(None, probe=True, **options)
        return self.step(phone, probe=True).probe_moves(), phone

    def test_positioned_pointer_at_every_blank_point(self):
        record, phone = self.probe()
        self.assertEqual(('completed', 'positioned'), (record['state'], record['result']))
        self.assertEqual([('/mouse/move', dict(x=x, y=y)) for x, y in pv.PROBE_POINTS], [c for c in phone.calls if isinstance(c, tuple)])
        self.assertEqual(len(pv.PROBE_POINTS), phone.replies); self.assertEqual('release', phone.calls[-1])
        self.assertTrue(all(row['pointer']['distance'] <= 12 for row in record['probe']))

    def test_first_unexpected_probe_result_stops(self):
        for mode, result in (('ignored', 'no_visible_change'), ('offset', 'mispositioned'), ('tap', 'unexpected_change')):
            with self.subTest(mode=mode):
                record, phone = self.probe(probe_mode=mode)
                self.assertEqual(result, record['result'])
                self.assertEqual(1, len([c for c in phone.calls if isinstance(c, tuple)])); self.assertFalse(phone.owned)

    def test_probe_needs_a_blank_screen_and_the_probe_kernel(self):
        record, phone = self.probe(screen='app')
        self.assertIn('not on a blank screen', record['error']); self.assertEqual([], phone.calls)
        phone = PromptPhone(None, screen='blank')
        record = self.step(phone, probe=True).probe_moves()
        self.assertIn('probe kernel', record['error']); self.assertEqual([], phone.calls)


class PromotionTests(Steps):
    def summary(self, method='long_press', **options):
        record, phone, _ = self.trial(method, **options)
        summary = pv.summarize(record, 'a3-' + method.replace('_', '-'), 'a'*64)
        summary['recordSource'] = 'phone'           # Stand in for a phone trial.
        return summary

    def promote(self, summary, confirmation=None):
        if confirmation is not None: summary = dict(summary, confirmation=confirmation)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root/prompts.WINDOW_RECORD/'trial.json'
            path.parent.mkdir(parents=True); path.write_text(json.dumps(summary), encoding='utf-8')
            return pv.promotion(path, root)

    def test_only_a_confirmed_declined_dismissal_validates(self):
        summary = self.summary(answers={'long_press'})
        self.assertNotIn('OCR', json.dumps(summary)); self.assertNotIn('Phone app', json.dumps(summary))
        entry, problems = self.promote(summary)
        self.assertIn("The operator's confirmation of the declined answer is missing.", problems)
        for confirmation in (dict(declined=False, observed='Allow was chosen'), dict(declined=None, observed='not sure')):
            self.assertTrue(self.promote(summary, confirmation)[1])
        entry, problems = self.promote(summary, dict(declined=True, observed='Settings shows Local Network off for YouTube'))
        self.assertEqual([], problems)
        self.assertEqual(('validated', 'local_network', 'long_press', "Don't Allow"), (entry['state'], entry['family'], entry['method'], entry['answer']))
        with patch.object(prompts, 'WINDOW_EVIDENCE', (entry,)):
            decision = prompts.plan(prompts.detect(dict(lines=[dict(text=t['text'], words=t['words']) for t in PromptPhone().render()[1]['lines']])))
        self.assertEqual(('answer', 'long_press'), (decision['action'], decision['method']))

    def test_ignored_results_are_evidence_too_but_never_answers(self):
        entry, problems = self.promote(self.summary('pointer_tap'))
        self.assertEqual(([], 'ignored'), (problems, entry['state']))
        with patch.object(prompts, 'WINDOW_EVIDENCE', (entry,)):
            text = dict(lines=PromptPhone().render()[1]['lines'])
            decision = prompts.plan(prompts.detect(text))
        self.assertEqual('stop', decision['action']); self.assertIn('pointer_tap', decision['ignoredMethods'])

    def test_focus_only_uncertain_and_fixture_results_never_promote(self):
        self.assertTrue(self.promote(self.summary('keyboard_focus', activate=False, answers={'keyboard_focus'}),
                                     dict(declined=True, observed='x'))[1])
        lost = self.summary(answers={'long_press'}, lose_reply=lambda fun, data: fun == '/mouse/up')
        self.assertTrue(self.promote(lost, dict(declined=True, observed='x'))[1])
        fixture = dict(self.summary(answers={'long_press'}), recordSource='offline_fixture')
        self.assertIn('Only a phone trial can become evidence.', self.promote(fixture, dict(declined=True, observed='x'))[1])

    def test_command_line_confirm_and_promote(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preparation = root/'live/preparation.json'; preparation.parent.mkdir()
            preparation.write_text(json.dumps(dict(root=str(root), windowRecord=str(root/prompts.WINDOW_RECORD), runDirectory=str(root/'run'),
                                                   kernelSha256='a'*64, expectedUid='fixture-uid')), encoding='utf-8')
            phone = PromptPhone(answers={'long_press'})
            argv = ['--preparation', str(preparation), '--label', 'a3-long-press']
            with patch('sys.stdout'):
                code = pv.main(['trial', *argv, '--part', 'A', '--method', 'long_press'], kernel_factory=lambda probe: phone,
                               ocr=FixtureOcr(phone), clock=phone.clock, monotonic=phone.clock, pause=phone.pause)
                self.assertEqual(0, code)
                with self.assertRaises(SystemExit):   # Never replayed.
                    pv.main(['trial', *argv, '--part', 'A', '--method', 'long_press'], kernel_factory=lambda probe: phone,
                            ocr=FixtureOcr(phone), clock=phone.clock, monotonic=phone.clock, pause=phone.pause)
                self.assertEqual(0, pv.main(['confirm', *argv, '--declined', '--observed', 'Local Network: YouTube off'], clock=phone.clock))
                with self.assertRaises(SystemExit): pv.main(['confirm', *argv, '--declined', '--observed', 'again'])
                self.assertEqual(2, pv.main(['promote', *argv]))      # A fixture is never phone evidence.
                with self.assertRaises(SystemExit):
                    pv.main(['probe', *argv[:2], '--label', 'b1-probe', '--part', 'A'], kernel_factory=lambda probe: phone)
            summary = json.loads((root/prompts.WINDOW_RECORD/'a3-long-press.json').read_text(encoding='utf-8'))
            self.assertEqual(('dismissed', True), (summary['result'], summary['confirmation']['declined']))
            self.assertTrue((root/'run/trials/a3-long-press/record.json').is_file())


class EquivalenceTests(unittest.TestCase):
    def test_trial_methods_match_the_run_answer_path(self):
        import inspect
        from farm_draft_creation import CreationWorkflow
        from farm_reel_creation import ReelCreationWorkflow
        answer = inspect.getsource(ReelCreationWorkflow.answer_prompt)
        step = inspect.getsource(CreationWorkflow.step)
        self.assertIn("self.step(label, 'permission_prompt', point=target, settle=True)", answer)
        self.assertIn("self.step(label, 'permission_prompt', point=target, hold=True)", answer)
        self.assertIn("self.step(label, 'permission_prompt', key='Escape')", answer)
        for sequence in ("self.command('/mouse/move',basis=value,purpose=label+'-position',x=x,y=y)",
                         'self.pause(.6)', "self.command('/mouse/down',purpose=label+'-press',button=1)", 'self.pause(1.1)',
                         "self.command('/mouse/up',purpose=label+'-release',button=1)",
                         "self.command('/mouse/click',purpose=label,x=x,y=y,button=1)",
                         "self.command('/mouse/move',purpose='park_after_answered_action',x=480,y=300)", 'self.pause(.7)',
                         "self.command('/key/sendkey',basis=value,purpose=label,fn_key=key)"):
            self.assertIn(sequence, step)
        self.assertEqual((.6, 1.1, .6, .7, (480, 300)), (*pv.HOLD, pv.SETTLED_TAP, pv.AFTER_ANSWER, pv.PARK))


R17 = ROOT/'analysis/farm-platform-drafts-20261017'
OCR17 = ROOT.parent/'iMouseXP-2.0-evidence-archive/20261020-farm-youtube-offline/ocr-20261017'
PRIVATE = (R17/'135-youtube-cancel-optional-prompt/before.png').exists() and OCR17.is_dir()


@unittest.skipUnless(PRIVATE, 'Retained private 17 Oct YouTube prompt frames/OCR are not available in this checkout.')
class RetainedPromptTests(unittest.TestCase):
    """The real 17 Oct local-network alert: planning and the focus check on actual mirrored frames."""
    def text(self, name): return json.loads((OCR17/f'{name}.json').read_text(encoding='utf-8'))
    def image(self, step, which): return pv.rgb((R17/step/f'{which}.png').read_bytes())

    def test_target_is_inside_the_real_dont_allow_button_and_a_hovered_label_refuses(self):
        for name in ('132-youtube-loaded__after', '133-youtube-decline-network__before', '135-youtube-cancel-optional-prompt__after'):
            with self.subTest(name):
                plan = pv.target_plan(self.text(name))
                self.assertEqual(('local_network', 'YouTube', "Don't Allow", 'row'), (plan['kind'], plan['app'], plan['declining'], plan['layout']))
                x, y = plan['target']
                self.assertTrue(88 < x < 250 and 782 < y < 835, plan['target'])   # The drawn button, not Allow.
        for name in ('133-youtube-decline-network__pointer', '134-youtube-permission-settled__after', '136-youtube-after-operator__after'):
            with self.subTest(name), self.assertRaises(InspectionStopped): pv.target_plan(self.text(name))

    def test_focus_check_on_real_frames(self):
        plan = pv.target_plan(self.text('135-youtube-cancel-optional-prompt__before'))
        before = self.image('135-youtube-cancel-optional-prompt', 'before')
        # Unchanged alert across real deliveries: no focus, no change.
        for step, which in (('135-youtube-cancel-optional-prompt', 'immediate'), ('135-youtube-cancel-optional-prompt', 'after'),
                            ('132-youtube-loaded', 'after')):
            self.assertEqual('no_focus', pv.focused_button(before, self.image(step, which), plan)['state'])
        # The dismissed alert is a changed alert, never a focus.
        self.assertEqual('alert_changed', pv.focused_button(before, self.image('136-youtube-after-operator', 'after'), plan)['state'])
        # A pointer hovering an answer highlights it exactly like a focus would. This is why a keyboard
        # trial parks the pointer off the alert and sends nothing between its two frames.
        hover = pv.focused_button(self.image('133-youtube-decline-network', 'before'), self.image('133-youtube-decline-network', 'pointer'), plan)
        self.assertEqual(('focused', "Don't Allow"), (hover['state'], hover['button']))


class WindowScriptTests(unittest.TestCase):
    """The window scripts parse and keep their guards. Nothing is executed."""
    def test_scripts_parse_and_never_force_stop(self):
        live = RECORD/'live'
        scripts = sorted(live.glob('*.ps1'))
        self.assertEqual(['Run-PromptStep.ps1', 'Start-PromptWindow.ps1', 'Stop-PromptWindow.ps1'], [s.name for s in scripts])
        paths = ','.join("'" + str(script).replace("'", "''") + "'" for script in scripts)
        command = ('$errors=$null; foreach($p in @(' + paths + ')){[void][System.Management.Automation.Language.Parser]::ParseFile($p,[ref]$null,[ref]$errors);'
                   ' if($errors.Count){Write-Output ($p+": "+$errors[0].Message); exit 1}}')
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        for script in scripts:
            body = script.read_text(encoding='utf-8-sig')
            for forbidden in ('Stop-Process', 'taskkill', 'Remove-Item', 'setup_imouse_farm', 'Open Marketing Farm.ps1', '--ui-test'):
                self.assertNotIn(forbidden, body, script.name)
        start = (live/'Start-PromptWindow.ps1').read_text(encoding='utf-8-sig')
        for guard in ('9913', '9916', 'uxplay.exe', 'verify_preparation.py', '--validate-startup', 'absolute_probe_board', 'Rack/test services are active'):
            self.assertIn(guard, start)
        stop = (live/'Stop-PromptWindow.ps1').read_text(encoding='utf-8-sig')
        for guard in ('Stop-ConsoleProcessGracefully.ps1', 'protected-before.json', 'release_failed', 'Nothing is force-killed'):
            self.assertIn(guard, stop)


if __name__ == '__main__':
    unittest.main()
