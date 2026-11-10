"""verify_window.py's gates: which stopped attempts may be re-checked, once, and under the rack lock. Offline."""
from contextlib import contextmanager
import importlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

WINDOWS = Path(__file__).resolve().parents[1] / 'rack'
sys.path.insert(0, str(WINDOWS))
verify_window = importlib.import_module('verify_window')


def reel_run(**changes):
    action = dict(label='save-reel-draft-once', state='answered', observationId='o1')
    toast = dict(observationId='o2', observation=dict(text=dict(lines=[dict(text='Draft saved')])))
    workflow = dict(cleanup='confirmed', packageSha256='p' * 64, actions=[action], observations=[dict(observationId='o1'), toast])
    workflow.update(changes.pop('workflow', {}))
    return dict(dict(id='run-1', terminal=True, state='review_required', savedDraftVerified=False, workflow=workflow), **changes)


def youtube_run(**changes):
    action = dict(label='save-youtube-draft-once', state='answered', observationId='o1')
    toast = dict(observationId='o2', role='yt_home_saved', observation=dict(text=dict(lines=[dict(text='Draft saved')])))
    workflow = dict(cleanup='confirmed', account='channel', packageSha256='p' * 64, actions=[action],
                    observations=[dict(observationId='o1', role='yt_details'), toast])
    workflow.update(changes.pop('workflow', {}))
    return dict(dict(id='run-1', terminal=True, state='review_required', savedDraftVerified=False, workflow=workflow), **changes)


class SavedThenStoppedGate(unittest.TestCase):
    def test_saved_and_stopped_reel_passes(self):
        self.assertTrue(verify_window.saved_then_stopped(reel_run(), 'reel'))

    def test_everything_else_is_refused_for_a_reel(self):
        for bad in (reel_run(terminal=False), reel_run(savedDraftVerified=True), reel_run(workflow=dict(cleanup='unconfirmed')),
                    reel_run(workflow=dict(verification={})), reel_run(workflow=dict(actions=[])),
                    reel_run(workflow=dict(actions=[dict(label='open-reel-editor', state='answered', observationId='o1')])),
                    reel_run(workflow=dict(actions=[dict(label='save-reel-draft-once', state='outcome_unknown', observationId='o1')])),
                    reel_run(workflow=dict(observations=[dict(observationId='o1')]))):
            self.assertFalse(verify_window.saved_then_stopped(bad, 'reel'))

    def test_each_platform_answers_only_to_its_own_save(self):
        self.assertTrue(verify_window.saved_then_stopped(youtube_run())); self.assertTrue(verify_window.saved_then_stopped(youtube_run(), 'youtube'))
        self.assertFalse(verify_window.saved_then_stopped(reel_run(workflow=dict(account='a')), 'youtube'))
        self.assertFalse(verify_window.saved_then_stopped(youtube_run(), 'reel'))
        self.assertFalse(verify_window.saved_then_stopped(youtube_run(workflow=dict(account=None))))   # The channel creation bound.
        elsewhere = youtube_run(); elsewhere['workflow']['observations'][1]['role'] = 'yt_details'
        self.assertFalse(verify_window.saved_then_stopped(elsewhere))   # YouTube's toast counts on its home only.
        self.assertEqual({'youtube', 'reel'}, set(verify_window.SAVED_THEN_STOPPED))


class ReCheckCommand(unittest.TestCase):
    """main() on a temporary window folder; verify() itself (the phone work) is replaced."""
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='farm-verify-window-'); self.addCleanup(temp.cleanup)
        self.state = Path(temp.name); self.events = []
        self.result = dict(state='validation_passed', savedDraftVerified=True, cleanup='confirmed', commands=[1, 2])

    def window(self, platform, run):
        folder = self.state / 'windows' / f'{platform}-slot19'; (folder / 'attempt-3').mkdir(parents=True)
        backend = self.state / 'backend'
        (folder / 'preparation.json').write_text(json.dumps(dict(platform=platform, backendData=str(backend), route=platform + '-creations')), encoding='utf-8')
        (folder / 'attempt-3' / 'result.json').write_text(json.dumps(dict(run=run)), encoding='utf-8')
        return folder, backend / (platform + '-creations') / run['id']

    def run_main(self, *arguments):
        @contextmanager
        def hold(holder):
            self.events.append(('lock', holder))
            try: yield
            finally: self.events.append(('unlock', holder))
        def verify(prep, run, child):
            self.events.append(('verify', prep['platform'], child.name)); child.mkdir(parents=True)
            return self.result
        out = io.StringIO()
        with patch.object(verify_window, 'STATE', self.state), patch.object(verify_window, 'hold_rack', hold), \
                patch.object(verify_window, 'verify', verify), patch.object(sys, 'argv', ['verify_window.py', *arguments]), redirect_stdout(out):
            verify_window.main()
        return json.loads(out.getvalue())

    def test_a_saved_and_stopped_reel_is_verified_once_under_the_rack_lock(self):
        folder, _ = self.window('reel', reel_run())
        summary = self.run_main('--window', 'reel-slot19', '--attempt', '3', '--check', '2')
        holder = 'verify_window reel-slot19 attempt 3 check 2'
        self.assertEqual([('lock', holder), ('verify', 'reel', 'verification-2'), ('unlock', holder)], self.events)
        self.assertEqual(('reel-slot19', 3, 2, True, 2), (summary['window'], summary['attempt'], summary['check'],
                                                          summary['savedDraftVerified'], summary['commands']))
        self.assertEqual(self.result, json.loads((folder / 'attempt-3' / 'verification-2.json').read_text(encoding='utf-8')))
        with self.assertRaisesRegex(SystemExit, 'Never replay a check'):   # The same check number is never used twice.
            self.run_main('--window', 'reel-slot19', '--attempt', '3', '--check', '2')
        self.assertEqual(3, len(self.events))

    def test_refusals_send_nothing_and_never_take_the_lock(self):
        self.window('reel', reel_run(workflow=dict(cleanup='unconfirmed')))
        with self.assertRaisesRegex(SystemExit, 'not a saved Reel draft whose creation stopped after Draft saved'):
            self.run_main('--window', 'reel-slot19', '--attempt', '3', '--check', '2')
        self.assertEqual([], self.events)

    def test_the_first_check_number_is_reserved_for_a_reel(self):
        self.window('reel', reel_run())
        with self.assertRaisesRegex(SystemExit, 'reserved'): self.run_main('--window', 'reel-slot19', '--attempt', '3', '--check', '1')
        self.assertEqual([], self.events)

    def test_a_stopped_verifier_is_still_rechecked_as_before(self):
        stopped = reel_run(workflow=dict(creationState='created_unverified', verification=dict(state='review_required')))
        self.window('reel', stopped)
        self.run_main('--window', 'reel-slot19', '--attempt', '3', '--check', '2')
        self.assertEqual(['lock', 'verify', 'unlock'], [e[0] for e in self.events])

    def test_youtube_keeps_its_own_rule(self):
        folder, run_folder = self.window('youtube', youtube_run())
        self.run_main('--window', 'youtube-slot19', '--attempt', '3', '--check', '1')   # Its verifier never ran: check 1 is free.
        self.assertEqual([('verify', 'youtube', 'verification-1')], [e for e in self.events if e[0] == 'verify'])
        (run_folder / 'verification').mkdir()
        with self.assertRaisesRegex(SystemExit, 'Never replay a check'):
            self.run_main('--window', 'youtube-slot19', '--attempt', '3', '--check', '2')


if __name__ == '__main__':
    unittest.main()
