"""Offline tests for rack_recovery.py: the stop ledger, the bring-up order and retries, the watchdog's
decision. Fake kernel and phone actions; no kernel, phone, socket or subprocess.

  python -m unittest test_rack_recovery    (from this folder)
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rack_recovery as rr  # noqa: E402

A_SLOTS = {'slots': {'20': {'board': 'C214'}, '19': {'board': 'C241'}, '18': {'board': 'C24C'}, '2': {'board': '1814'}}}
B_SLOTS = {'slots': {'20': {'board': '636D'}, '19': {'board': '24B7'}, '18': {'board': '0C6D'}}}
BOARDS = {'C214': 'iMouse2-20', 'C241': 'iMouse2-19', 'C24C': 'iMouse2-18', '1814': 'iMouse2-2',
          '636D': 'iMouse2-B20', '24B7': 'iMouse2-B19', '0C6D': 'iMouse2-B18'}
PREP = {'receivers': [dict(board=b, name=n, port=7000 + 10 * i) for i, (b, n) in enumerate(BOARDS.items())]}
PLAN = {'steps': [
    {'group': 'rack B anchor', 'anchor': 'B20', 'card': 'small'},
    {'group': 'rack B', 'receivers': 'B19..B1', 'survey': 'B20', 'card': 'small'},
    {'group': 'rack A small', 'receivers': ['2', '5'], 'survey': 'B20', 'card': 'small'},
    {'group': 'rack A anchor', 'anchor': '20', 'card': 'xr'},
    {'group': 'rack A XRs', 'receivers': '19..10', 'survey': '20', 'card': 'xr'}]}


def state(stopped=False, generation=0, message='', owned=False):
    return dict(stopped=stopped, generation=generation, message=message, owned=owned, release_failed=False)


class LedgerTests(unittest.TestCase):
    def test_records_only_new_stops_and_never_an_operator_stop(self):
        before = {'A': state(), 'B': state(True, 4, 'Stopped by operator.'), 'C': state(True, 2, 'Controller lease expired.'), 'D': state()}
        after = {'A': state(True, 1, 'Kernel shutting down.'), 'B': state(True, 4, 'Stopped by operator.'),
                 'C': state(True, 2, 'Controller lease expired.'), 'D': state(True, 3, 'Stopped by operator.')}
        got = rr.ledger_entries(before, after, 'Stop-Multiphone', 'T')
        self.assertEqual(got, [dict(utc='T', board='A', by='Stop-Multiphone', generation=1, message='Kernel shutting down.')])

    def test_resumes_only_what_we_stopped_and_nothing_touched_since(self):
        ledger = [dict(board='A', generation=1, by='Stop-Multiphone')]
        self.assertTrue(rr.resumable('A', state(True, 1, 'Kernel shutting down.'), ledger))
        self.assertFalse(rr.resumable('A', state(True, 2, 'Kernel shutting down.'), ledger))      # touched since
        self.assertFalse(rr.resumable('B', state(True, 1, 'x'), ledger))                          # not ours
        self.assertFalse(rr.resumable('A', state(True, 1, 'Stopped by operator.'), ledger))
        self.assertFalse(rr.resumable('A', state(True, 1, 'x', owned=True), ledger))
        self.assertFalse(rr.resumable('A', state(False, 1), ledger))

    def test_ledger_file_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'input-stops.jsonl'
            self.assertEqual(rr.read_ledger(path), [])
            rr.append_ledger(path, [dict(board='A', generation=1)]); rr.append_ledger(path, [dict(board='B', generation=2)])
            self.assertEqual([e['board'] for e in rr.read_ledger(path)], ['A', 'B'])


class PlanTests(unittest.TestCase):
    def test_expand(self):
        self.assertEqual(rr.expand('B3..B1'), ['B3', 'B2', 'B1'])
        self.assertEqual(rr.expand('10..12'), ['10', '11', '12'])
        self.assertEqual(rr.expand(['2', 5]), ['2', '5'])
        with self.assertRaises(SystemExit): rr.expand('B3..1')

    def test_plan_order_and_surveys(self):
        phones = rr.build_plan(PLAN, rr.slot_boards(A_SLOTS, B_SLOTS), PREP, {'c241': '192.0.2.9'})
        self.assertEqual([p['slot'] for p in phones], ['B20', 'B19', 'B18', '2', '20', '19', '18'])
        self.assertEqual([p['survey_board'] for p in phones], [None, '636D', '636D', '636D', None, 'C214', 'C214'])
        self.assertEqual([p['card'] for p in phones], ['small'] * 4 + ['xr'] * 3)
        self.assertEqual(phones[5]['phone_ip'], '192.0.2.9')

    def test_plan_skips_boards_not_on_this_kernel_and_refuses_repeats(self):
        prep = {'receivers': [r for r in PREP['receivers'] if r['board'] in ('C214', 'C241')]}
        phones = rr.build_plan({'steps': PLAN['steps'][3:]}, rr.slot_boards(A_SLOTS, B_SLOTS), prep)
        self.assertEqual([p['slot'] for p in phones], ['20', '19'])
        with self.assertRaises(SystemExit): rr.build_plan({'steps': PLAN['steps'][3:4] * 2}, rr.slot_boards(A_SLOTS, B_SLOTS), PREP)
        with self.assertRaises(SystemExit): rr.build_plan({'steps': PLAN['steps'][1:2]}, rr.slot_boards(A_SLOTS, B_SLOTS), prep)  # survey phone absent

    def test_crafted_surveys_follow_the_live_rows(self):
        # B20 alone: small card row 1 at cy 483; the PC's browse (with stale names) is 'advertised'.
        survey, why = rr.crafted_survey('iMouse2-B20', 'small', set(), {'iMouse2-B20', 'iMouse2-old'})
        self.assertEqual((survey['row'], survey['lines'][0]['cy'], survey['advertised']), (1, 483, ['iMouse2-B20', 'iMouse2-old']))
        self.assertTrue(survey['small'] and survey['lines'][1]['text'] == 'Stop Mirroring')
        # A20 after 2, 5, 6 and rack B: natural order puts it 4th: cy 226 + 3 * 63 = 415 (413 worked live).
        live = {'iMouse2-2', 'iMouse2-5', 'iMouse2-6'} | {f'iMouse2-B{n}' for n in range(1, 21)}
        survey, _ = rr.crafted_survey('iMouse2-20', 'xr', live, live)
        self.assertEqual((survey['row'], survey['lines'][0]['cy']), (4, 415))
        # A small phone below the three visible rows is refused, not guessed.
        survey, why = rr.crafted_survey('iMouse2-B9', 'small', {'iMouse2-17', 'iMouse2-18', 'iMouse2-20'}, set())
        self.assertIsNone(survey); self.assertIn('row 4', why)


class FakeActions:
    """The rack as the bring-up sees it: who is live, input state, what each connect returns."""

    def __init__(self, results=None, stopped=None, live=()):
        self.live = set(live)
        self.inputs = {b: state() for b in BOARDS}
        self.inputs.update(stopped or {})
        self.results = {b: list(r) for b, r in (results or {}).items()}
        self.calls = []

    def receivers(self): return {n: dict(live=n in self.live) for n in BOARDS.values()}
    def advertised(self): return set(self.live)
    def browse(self): return set(self.live) | {'iMouse2-stale'}
    def snapshot(self): return {b: dict(s) for b, s in self.inputs.items()}
    def device_id(self, board): return 'dev-' + board
    def sleep(self, s): pass

    def resume(self, board, generation, device):
        self.calls.append(('resume', board, generation)); self.inputs[board] = state(False, generation); return dict(code=0)

    def release(self, board): self.calls.append(('release', board)); return dict(code=0)
    def wake(self, board): self.calls.append(('wake', board)); return 'woken'

    def survey(self, board, small):
        self.calls.append(('survey', board)); return Path(f'survey-{board}.json'), 'surveyed'

    def write_survey(self, board, survey):
        self.calls.append(('crafted', board, survey['row'])); return Path(f'crafted-{board}.json')

    def connect(self, board, path, small, ip):
        self.calls.append(('connect', board, str(path)))
        queue = self.results.get(board) or ['mirroring']
        result = queue.pop(0) if len(queue) > 1 else queue[0]
        if result == 'mirroring': self.live.add(BOARDS[board])
        if result == 'lease expired':
            self.inputs[board] = state(True, self.inputs[board]['generation'] + 1, 'Controller lease expired.')
            result = 'stopped: lease renewal: refused'
        return result


class BringUpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.ledger = Path(self.tmp.name) / 'input-stops.jsonl'
        self.phones = rr.build_plan(PLAN, rr.slot_boards(A_SLOTS, B_SLOTS), PREP)

    def tearDown(self): self.tmp.cleanup()

    def test_connects_in_order_from_crafted_anchors(self):
        fake = FakeActions()
        report = rr.bring_up(self.phones, fake, self.ledger)
        connects = [c[1] for c in fake.calls if c[0] == 'connect']
        self.assertEqual(connects, ['636D', '24B7', '0C6D', '1814', 'C214', 'C241', 'C24C'])
        self.assertIn(('crafted', '636D', 1), fake.calls)
        self.assertIn(('crafted', 'C214', 2), fake.calls)    # after 2: 'iMouse2-2' < 'iMouse2-20'
        self.assertEqual([c[1] for c in fake.calls if c[0] == 'survey'], ['636D', '636D', '636D', 'C214', 'C214'])
        self.assertEqual({c[1] for c in fake.calls if c[0] == 'wake'}, {'636D', '24B7', '0C6D', '1814'})   # small phones only
        self.assertEqual(rr.summary(report)['mirroring'], 7)

    def test_skips_live_phones_and_retries_once(self):
        fake = FakeActions(results={'24B7': ['stopped: no AirPlay query from the phone after the tile tap', 'mirroring'],
                                    '0C6D': ['stopped: no AirPlay query from the phone after the tile tap']},
                           live={'iMouse2-19'})
        report = {r['board']: r for r in rr.bring_up(self.phones, fake, self.ledger)}
        self.assertEqual(report['C241']['result'], 'already mirroring')
        self.assertEqual(len(report['24B7']['attempts']), 2); self.assertEqual(report['24B7']['result'], 'mirroring')
        self.assertEqual(len(report['0C6D']['attempts']), 2); self.assertTrue(report['0C6D']['result'].startswith('stopped'))
        self.assertNotIn(('connect', 'C241', 'survey-C214.json'), fake.calls)

    def test_never_resumes_an_operator_or_unknown_stop(self):
        fake = FakeActions(stopped={'24B7': state(True, 5, 'Stopped by operator.'), '0C6D': state(True, 2, 'Controller lease expired.')})
        report = {r['board']: r for r in rr.bring_up(self.phones, fake, self.ledger)}
        self.assertTrue(report['24B7']['result'].startswith('skipped'))
        self.assertTrue(report['0C6D']['result'].startswith('skipped'))   # not in our ledger
        self.assertFalse([c for c in fake.calls if c[0] == 'resume'])
        self.assertFalse([c for c in fake.calls if c[0] == 'release' and c[1] in ('24B7', '0C6D')])

    def test_resumes_exactly_the_boards_our_stop_left(self):
        rr.append_ledger(self.ledger, [dict(board='0C6D', generation=2, by='Stop-Multiphone')])
        fake = FakeActions(stopped={'0C6D': state(True, 2, 'Kernel shutting down.')})
        report = {r['board']: r for r in rr.bring_up(self.phones, fake, self.ledger)}
        self.assertIn(('resume', '0C6D', 2), fake.calls)
        self.assertEqual(report['0C6D']['result'], 'mirroring')

    def test_own_lease_expiry_is_ledgered_and_resumed_on_retry(self):
        fake = FakeActions(results={'24B7': ['lease expired', 'mirroring']})
        report = {r['board']: r for r in rr.bring_up(self.phones, fake, self.ledger)}
        self.assertEqual(report['24B7']['result'], 'mirroring')
        self.assertEqual([e['by'] for e in rr.read_ledger(self.ledger)], ['Bringup-Rack'])
        self.assertIn(('resume', '24B7', 1), fake.calls)


class WatchdogTests(unittest.TestCase):
    def test_decide(self):
        rec = dict(kernel=dict(pid=1, path='k.exe'))
        self.assertEqual(rr.decide(None, False, False, False, 0), 'idle')         # stopped on purpose
        self.assertEqual(rr.decide(rec, True, True, False, 0), 'healthy')
        self.assertEqual(rr.decide(rec, True, False, False, 0), 'unresponsive')   # never killed
        self.assertEqual(rr.decide(rec, False, False, False, 0), 'restart')
        self.assertEqual(rr.decide(rec, False, False, False, 3), 'give-up')
        self.assertEqual(rr.decide(rec, False, False, True, 0), 'paused')

    def test_orphans_are_only_our_receivers(self):
        procs = [dict(Name='uxplay.exe', ProcessId=10, ParentProcessId=1, CommandLine='uxplay -n iMouse2-other -p 1'),
                 dict(Name='uxplay.exe', ProcessId=11, ParentProcessId=99, CommandLine='uxplay -n iMouse2-B5 -nh -p 7300'),
                 dict(Name='uxplay.exe', ProcessId=12, ParentProcessId=99, CommandLine='uxplay -n iMouse2-x -p 7400'),
                 dict(Name='iMouse2.Kernel.exe', ProcessId=13, ParentProcessId=1, CommandLine='-n iMouse2-B5')]
        self.assertEqual(rr.orphans(procs, 1, {'iMouse2-B5'}), [10, 11])
        self.assertEqual(rr.orphans([dict(procs[0], Name='stand-in.exe')], 1, set(), 'stand-in.exe'), [10])
        self.assertEqual(rr.receiver_exe({'arguments': ['x', '--receiver', 'C:/r/UxPlay.exe']}), 'uxplay.exe')

    def test_kernel_running_checks_pid_and_path(self):
        rec = dict(kernel=dict(pid=5, path='C:\\K\\iMouse2.Kernel.exe'))
        self.assertTrue(rr.kernel_running(rec, [dict(ProcessId=5, ExecutablePath='c:\\k\\imouse2.kernel.exe')]))
        self.assertFalse(rr.kernel_running(rec, [dict(ProcessId=5, ExecutablePath='C:\\other.exe')]))   # PID reused

    def test_python_scope(self):
        self.assertEqual(rr.python_scope(['-Stage', 'slots']), ['--stage', 'slots'])
        self.assertEqual(rr.python_scope(['-Rack', 'B']), ['--rack', 'B'])

    def test_last_json(self):
        self.assertEqual(rr.last_json('noise\n{"a": 1}\ntrailing'), {'a': 1})
        self.assertIsNone(rr.last_json('Traceback\nError'))


if __name__ == '__main__':
    unittest.main()
