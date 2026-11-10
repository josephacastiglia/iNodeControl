"""Offline tests for rack_recovery.py: the stop ledger, the bring-up order and retries, the watchdog's
decision. Fake kernel and phone actions; no kernel, phone, socket or subprocess.

  python -m unittest test_rack_recovery    (from this folder)
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        # B20 alone: small card row 1 at cy 483; the PC's browse (with this kernel's withdrawn names) is 'advertised'.
        survey, why = rr.crafted_survey('iMouse2-B20', 'small', set(), {'iMouse2-B20', 'iMouse2-old'}, {'iMouse2-B20', 'iMouse2-old'})
        self.assertEqual((survey['row'], survey['lines'][0]['cy'], survey['advertised']), (1, 483, ['iMouse2-B20', 'iMouse2-old']))
        self.assertTrue(survey['small'] and survey['lines'][1]['text'] == 'Stop Mirroring')
        # A20 after 2, 5, 6 and rack B: natural order puts it 4th: cy 226 + 3 * 63 = 415 (413 worked live).
        live = {'iMouse2-2', 'iMouse2-5', 'iMouse2-6'} | {f'iMouse2-B{n}' for n in range(1, 21)}
        survey, _ = rr.crafted_survey('iMouse2-20', 'xr', live, live, live | {'iMouse2-20'})
        self.assertEqual((survey['row'], survey['lines'][0]['cy']), (4, 415))
        # A small phone below the three visible rows is refused, not guessed.
        survey, why = rr.crafted_survey('iMouse2-B9', 'small', {'iMouse2-17', 'iMouse2-18', 'iMouse2-20'}, set(), set())
        self.assertIsNone(survey); self.assertIn('row 4', why)

    def test_a_computed_row_is_refused_when_the_network_lists_a_receiver_that_is_not_ours(self):
        # The phone's card lists every AirPlay receiver on the network. One that is not this kernel's (a TV,
        # another PC's receiver) shifts the rows, and a tap on its row would mirror the phone to it.
        ours = set(BOARDS.values())
        survey, why = rr.crafted_survey('iMouse2-B20', 'small', set(), ours | {'Bedroom TV'}, ours)
        self.assertIsNone(survey); self.assertIn('Bedroom TV', why); self.assertTrue(why.startswith('refused'))
        survey, why = rr.crafted_survey('iMouse2-20', 'xr', {'iMouse2-2'}, {'iMouse2-2', 'iMouse2-20', 'imouse2-b20 '}, ours)
        self.assertIsNone(survey, 'a name that only resembles ours is still not ours')
        survey, why = rr.crafted_survey('iMouse2-B20', 'small', set(), ours, ours)   # our own names, advertised or not, are fine
        self.assertEqual((survey['row'], why), (1, None))


class FakeActions:
    """The rack as the bring-up sees it: who is live, input state, what each connect returns."""

    def __init__(self, results=None, stopped=None, live=()):
        self.live = set(live)
        self.inputs = {b: state() for b in BOARDS}
        self.inputs.update(stopped or {})
        self.results = {b: list(r) for b, r in (results or {}).items()}
        self.calls = []
        self.foreign = set()   # AirPlay names on the network that are not this kernel's.

    def receivers(self): return {n: dict(live=n in self.live) for n in BOARDS.values()}
    def advertised(self): return set(self.live)
    def browse(self): return set(BOARDS.values()) | self.foreign   # The PC's cache keeps this kernel's withdrawn names.
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

    def test_no_anchor_is_tapped_at_a_computed_row_while_a_foreign_receiver_is_listed(self):
        fake = FakeActions(); fake.foreign = {'Living Room TV'}
        report = {r['board']: r for r in rr.bring_up(self.phones, fake, self.ledger)}
        self.assertFalse([c for c in fake.calls if c[0] in ('connect', 'crafted') and c[1] in ('636D', 'C214')])   # both anchors
        for anchor in ('636D', 'C214'):
            self.assertIn('Living Room TV', report[anchor]['result'])
            self.assertEqual(len(report[anchor]['attempts']), 1, 'nothing to retry: the network has to change first')
        self.assertFalse(rr.summary(list(report.values()))['ok'])

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
        self.assertEqual([e['by'] for e in rr.read_ledger(self.ledger)], ['bringup'])
        self.assertIn(('resume', '24B7', 1), fake.calls)


class FakeKernel:
    """Answers the kernel calls Actions makes; `codes` maps a function to the codes it returns in turn."""
    api = 'http://127.0.0.1:1/api'

    def __init__(self, codes=None):
        self.codes = {k: list(v) for k, v in (codes or {}).items()}
        self.posts = []

    def devices(self): return {'dev-0F01': '0F01'}

    def post(self, fun, data, timeout=30):
        self.posts.append((fun, {k: v for k, v in data.items() if k not in ('id', 'token')}))
        if fun == '/input/acquire': return dict(code=0, leases=[dict(token='t')])
        code = self.codes[fun].pop(0) if self.codes.get(fun) else 0
        return dict(code=code, message='' if code == 0 else 'refused by the fake')


class ActionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name); self.run = self.state / 'bringup-x'; self.run.mkdir()

    def test_release_runs_the_one_script_and_reads_its_record(self):
        calls, outcome = [], {}

        def script(name, *args, log=None):
            calls.append((name, args, Path(log).name))
            if outcome:
                with open(self.state / 'releases.jsonl', 'a', encoding='utf-8') as f: f.write(json.dumps(outcome) + '\n')
            return 1 if outcome.get('problem', 'no record') else 0

        actions = rr.Actions(FakeKernel(), self.run)
        with mock.patch.object(rr, 'powershell', script):
            outcome.update(board='0F01', code=0, problem='')
            self.assertEqual(actions.release('0F01'), dict(code=0))
            outcome.update(code=409, problem='Kernel refused: iMouse2-Z1 is restarting; wait for it to finish.')
            self.assertEqual(actions.release('0F01'), dict(code=1, message=outcome['problem']))
            outcome.clear()   # The script stopped before it asked the kernel: no record to read.
            got = actions.release('0F01')
            self.assertEqual(got['code'], 1); self.assertIn('release-output.txt', got['message'])
        self.assertEqual(calls[0], ('Release-Receiver.ps1', ('-Board', '0F01'), 'release-output.txt'))
        self.assertFalse(actions.kernel.posts, 'the bring-up itself never posts /device/airplay/connect')

    def test_wake_is_home_twice_under_one_renewed_lease(self):
        kernel = FakeKernel()
        with mock.patch('time.sleep') as sleep:
            rr.Actions(kernel, self.run).wake('0F01')
        self.assertEqual([p[0] for p in kernel.posts], ['/input/acquire', '/input/renew', '/key/sendkey', '/input/renew', '/key/sendkey', '/input/release'])
        self.assertEqual([p[1] for p in kernel.posts if p[0] == '/key/sendkey'], [dict(fn_key='Home')] * 2)
        self.assertEqual([c.args for c in sleep.call_args_list], [(1.8,), (1.8,)])

    def test_a_wake_whose_key_was_refused_is_reported_as_failed(self):
        with mock.patch('time.sleep'):
            self.assertEqual(rr.Actions(FakeKernel(), self.run).wake('0F01'), 'woken')
            for codes in ([41, 0], [0, 41]):   # either Home refused: the phone may still be dark
                got = rr.Actions(FakeKernel({'/key/sendkey': codes}), self.run).wake('0F01')
                self.assertTrue(got.startswith('wake failed'), got)
                self.assertIn('41', got)


class ReportPrivacyTests(unittest.TestCase):
    """The bring-up report is read and passed around; a phone's device ID must never be in it."""
    MAC, UDID, OLD_UDID = '02:00:5A:00:0F:01', '0000A1B2-' + '0011223344556677', 'a1' * 20   # shaped like the real things

    def test_device_ids_are_replaced_wherever_they_sit(self):
        ids = {'dev-0C6D-private': '0C6D', self.MAC: '24B7'}
        dirty = dict(n=3, ok=False, rows=[dict(result=f"Screen Mirroring tile: {{'code': 41, 'id': '{self.MAC}'}}", board='24B7'),
                                         dict(result='wake refused: dev-0C6D-private is leased'),
                                         dict(result=f'other phone {self.MAC.lower()} and {self.UDID} and {self.OLD_UDID}')])
        clean = rr.without_device_ids(dirty, ids)
        text = json.dumps(clean).casefold()
        for secret in (self.MAC, 'dev-0C6D-private', self.UDID, self.OLD_UDID):
            self.assertNotIn(secret.casefold(), text)
        self.assertEqual((clean['n'], clean['ok'], clean['rows'][0]['board']), (3, False, '24B7'))
        self.assertIn('<phone on board 0C6D>', clean['rows'][1]['result'])
        self.assertEqual(rr.without_device_ids('iMouse2-B19 row 2, board 24B7, api http://127.0.0.1:9916/api', ids),
                         'iMouse2-B19 row 2, board 24B7, api http://127.0.0.1:9916/api')   # names, boards and addresses stay

    def test_the_written_report_and_the_printed_summary_hold_no_device_id(self):
        leak = f"stopped: lease renewal: {{'code': 41, 'message': 'phone {self.MAC} is not leased'}}"

        class Kernel(FakeKernel):
            def __init__(self, api): super().__init__(); self.api = api
            def alive(self): return True
            def devices(self): return {ReportPrivacyTests.MAC: '636D', 'dev-24B7-private': '24B7'}

        class Leaky(FakeActions):
            def __init__(self, kernel, folder): super().__init__(results={'636D': [leak], '24B7': ['stopped: dev-24B7-private refused']})
            def wake(self, board): return 'wake refused: dev-24B7-private is leased'

        with tempfile.TemporaryDirectory() as d, mock.patch.object(rr, 'Kernel', Kernel), mock.patch.object(rr, 'Actions', Leaky), \
                mock.patch.object(rr, 'planned_phones', lambda folder, plan: (dict(arguments=['http://127.0.0.1:1/api/']),
                                                                             rr.build_plan(PLAN, rr.slot_boards(A_SLOTS, B_SLOTS), PREP))):
            result = rr.run_bringup(d, 'plan.json')
            written = Path(result['report']).read_text(encoding='utf-8')
        for text in (written, json.dumps(result)):
            self.assertNotIn(self.MAC, text); self.assertNotIn('dev-24B7-private', text)
        self.assertIn('<phone on board 636D>', written)
        self.assertFalse(result['ok'])


def row(result, slot='B1'): return dict(slot=slot, board='0F01', result=result)


class ExitCodeTests(unittest.TestCase):
    """A caller that only looks at the exit code must learn that a phone is not connected."""

    def main(self, *argv, **patched):
        with tempfile.TemporaryDirectory() as d, contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(sys, 'argv', ['rack_recovery.py', *argv]))
            stack.enter_context(mock.patch.object(rr, 'kernel_folder', return_value=Path(d)))
            for name, value in patched.items(): stack.enter_context(mock.patch.object(rr, name, value))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            try: rr.main()
            except SystemExit as stop: return stop.code
            return 0

    def test_the_summary_says_whether_every_phone_in_the_plan_mirrors(self):
        self.assertTrue(rr.summary([row('mirroring'), row('already mirroring'), row('mirroring; Control Center did not close')])['ok'])
        self.assertFalse(rr.summary([row('mirroring'), row('stopped: receiver did not go live within 10 s')])['ok'])
        self.assertFalse(rr.summary([row('mirroring'), row('skipped: input stopped by someone else (Stopped by operator.)')])['ok'])
        self.assertFalse(rr.summary([row('mirroring'), dict(slot='B2', board='0F02')])['ok'])   # never got a result

    def test_bringup_exits_non_zero_unless_every_phone_mirrors(self):
        for report, code in (([row('mirroring'), row('already mirroring')], 0),
                             ([row('mirroring'), row('stopped: no AirPlay query from the phone after the tile tap')], 3),
                             ([row('skipped: release refused (x)')], 3)):
            result = dict(report='report.json', **rr.summary(report))
            self.assertEqual(self.main('bringup', run_bringup=lambda *a, **k: result), code, report)

    def test_one_watchdog_check_exits_non_zero_when_it_ended_badly(self):
        good = dict(report='r', **rr.summary([row('mirroring')]))
        bad = dict(report='r', **rr.summary([row('mirroring'), row('stopped: receiver did not go live within 10 s')]))
        for entry, code in ((dict(action='healthy'), 0), (dict(action='idle'), 0), (dict(action='paused'), 0), (dict(action='unresponsive'), 0),
                            (dict(action='restart', start=0), 0),                    # --no-bringup
                            (dict(action='restart', start=0, bringup=good), 0),
                            (dict(action='restart', start=0, bringup=bad), 3),       # a phone did not come back
                            (dict(action='restart', start=0, bringup=dict(error='No kernel answers')), 3),
                            (dict(action='restart', start=1), 3),                    # the kernel did not start again
                            (dict(action='give-up'), 3)):
            self.assertEqual(self.main('watch', '--once', watch=lambda *a, **k: entry), code, entry)

    def test_the_watchdog_records_a_bring_up_that_fell_short(self):
        bad = dict(report='r', **rr.summary([row('mirroring'), row('stopped: receiver did not go live within 10 s')]))
        with tempfile.TemporaryDirectory() as d, contextlib.ExitStack() as stack:
            folder = Path(d)
            (folder / 'preparation.json').write_text(json.dumps(dict(arguments=['http://127.0.0.1:1/api/'], runDirectory=d,
                                                                      receivers=[dict(board='0F01', name='iMouse2-Z1', port=7900)])), encoding='utf-8')
            (folder / 'processes.json').write_text(json.dumps(dict(kernel=dict(pid=4000000, path='k.exe'), api='http://127.0.0.1:1/api')), encoding='utf-8')
            for name, value in (('processes', lambda exe: []), ('powershell', lambda *a, **k: 0), ('run_bringup', lambda *a, **k: bad)):
                stack.enter_context(mock.patch.object(rr, name, value))
            stack.enter_context(mock.patch.object(rr.subprocess, 'run', return_value=mock.Mock(returncode=0)))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            entry = rr.watch(folder, 0, True, True)
            logged = json.loads((folder / 'watchdog.jsonl').read_text(encoding='utf-8').splitlines()[-1])
        self.assertEqual((entry['action'], entry['start'], entry['ok']), ('restart', 0, False))
        self.assertEqual(logged['bringup']['failed'], [dict(slot='B1', result='stopped: receiver did not go live within 10 s')])
        self.assertFalse(logged['ok'])


class WatchdogTests(unittest.TestCase):
    def test_decide(self):
        rec = dict(kernel=dict(pid=1, path='k.exe'))
        self.assertEqual(rr.decide(None, False, False, False, 0), 'idle')         # stopped on purpose
        self.assertEqual(rr.decide(rec, True, True, False, 0), 'healthy')
        self.assertEqual(rr.decide(rec, True, False, False, 0), 'unresponsive')   # never killed
        self.assertEqual(rr.decide(rec, False, False, False, 0), 'restart')
        self.assertEqual(rr.decide(rec, False, False, False, 3), 'give-up')
        self.assertEqual(rr.decide(rec, False, False, True, 0), 'paused')

    def test_a_kernel_being_stopped_on_purpose_is_never_restarted(self):
        # Stop-Multiphone.ps1 renames the record last, after the kernel has gone; in between the record
        # names a dead kernel. stopping.json, written before the stop begins, says that is on purpose.
        rec = dict(kernel=dict(pid=4000000, path='k.exe'))
        self.assertEqual(rr.decide(rec, False, False, False, 0, stopping=True), 'stopping')
        self.assertEqual(rr.decide(rec, True, True, False, 0, stopping=True), 'healthy')        # still shutting down
        self.assertEqual(rr.decide(rec, False, False, False, 0), 'restart')                    # no marker: it died
        self.assertTrue(rr.tick_ok(dict(action='stopping')))

        def boom(*a, **k): raise AssertionError('a kernel being stopped on purpose must not be touched')

        with tempfile.TemporaryDirectory() as d, contextlib.ExitStack() as stack:
            folder = Path(d)
            (folder / 'preparation.json').write_text(json.dumps(dict(arguments=['http://127.0.0.1:1/api/'], runDirectory=d, receivers=[])), encoding='utf-8')
            (folder / 'processes.json').write_text(json.dumps(rec), encoding='utf-8')
            self.assertFalse(rr.stop_requested(folder, rec))
            (folder / 'stopping.json').write_text(json.dumps(dict(pid=4000001)), encoding='utf-8')   # an earlier kernel's stop
            self.assertFalse(rr.stop_requested(folder, rec))
            (folder / 'stopping.json').write_text('\ufeff' + json.dumps(dict(utc='t', pid=4000000)), encoding='utf-8')   # as PowerShell writes it
            self.assertTrue(rr.stop_requested(folder, rec))
            stack.enter_context(mock.patch.object(rr, 'processes', lambda exe: []))
            stack.enter_context(mock.patch.object(rr, 'powershell', boom))
            stack.enter_context(mock.patch.object(rr.subprocess, 'run', boom))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            entry = rr.watch(folder, 0, True, True)
            self.assertEqual((entry['action'], entry['ok']), ('stopping', True))
            self.assertTrue((folder / 'processes.json').exists())
            self.assertFalse(list(folder.glob('processes-died-*')) + list(folder.glob('watchdog-pending.json')))

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

    def test_last_json(self):
        self.assertEqual(rr.last_json('noise\n{"a": 1}\ntrailing'), {'a': 1})
        self.assertIsNone(rr.last_json('Traceback\nError'))


if __name__ == '__main__':
    unittest.main()
