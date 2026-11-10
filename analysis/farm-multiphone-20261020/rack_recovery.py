"""Unattended rack recovery: who stopped which board's input, the ordered bring-up, and the watchdog.

The bring-up report and summary never hold a phone's device ID (without_device_ids); the phone
addresses of the plan are left out of both.

  python rack_recovery.py snapshot --api URL --out FILE
      Input state per board (stopped, generation, message; boards only, never device IDs).
  python rack_recovery.py ledger --api URL --before FILE --by NAME --ledger FILE
      Appends a ledger entry for every board whose input became stopped since FILE: what we stopped,
      with the generation it left, so a later bring-up resumes exactly those and nothing else.
  python rack_recovery.py bringup [--plan bringup-plan.json] [--plan-only] [--attempts 2]
      The ordered reconnect of the rack's phones. Wakes Home-button phones, retries once, and writes
      bringup-<time>/report.json beside the preparation. Drives phones (taps, Home): run it only when
      no lane is on a phone. Exit 0 only when every phone in the plan mirrors; 3 when one was
      skipped or failed (the printed summary and the report say which).
  python rack_recovery.py watch [--interval 30] [--no-bringup] [--once] [--max-restarts 3]
      The watchdog, for the operator to leave running. Every interval it checks the kernel in
      processes.json. When that kernel has died it stops the receivers it left (useless without it and
      holding its ports), withdraws their names, starts the kernel again (Start-Multiphone.ps1) and
      runs the bring-up. It never touches a kernel that is running, even one whose API is silent (it
      reports that), and never restarts a kernel stopped on purpose (Stop-Multiphone.ps1 marks the stop
      in stopping.json before it begins and renames the record when it is done) or one that is still
      starting (processes-starting.json). At most --max-restarts an hour, then it stops and says so. Pause it without stopping
      it: create watchdog-pause beside the preparation. Log: watchdog.jsonl beside the preparation.
      Exit 3 when it gives up, or when a --once check restarted the kernel and the start or the
      bring-up fell short ('ok': false in the log line).

Bring-up order (5 Nov, the orchestrator's live findings; bringup-plan.json): the 4.7-inch card shows
three rows and numeric names sort ahead of 'iMouse2-B..', so rack B goes first, from B20 alone
(crafted one-row survey) then B19 down surveyed on B20, then rack A's small phones, then A20
(crafted XR survey, row n at cy 226 + 63(n-1)), then the XRs from 19 down surveyed on A20. A crafted
survey's 'advertised' is the PC's Bonjour browse (its cache keeps withdrawn names), its row the
receiver's natural-order rank among the receivers the kernel actually advertises. A crafted row is
refused while the PC's browse lists an AirPlay receiver that is not this kernel's (a TV, another PC).

Input resumes only boards the ledger says we stopped and that nothing has touched since (same
generation). 'Stopped by operator.' is never resumed. Every phone action takes its own lease.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from rack_kernels import STATE, kernel_folder  # noqa: E402  (beside this script)
OPERATOR_STOP = 'Stopped by operator.'
SMALL_ROW1, SMALL_PITCH, SMALL_ROWS = 483, 69, 3      # The 4.7-inch card: three visible rows (card_survey.py).
XR_ROW1, XR_PITCH, XR_ROWS = 226, 63, 9               # The XR card, unscrolled.


def utc(): return datetime.now(timezone.utc).isoformat()
def stamp(): return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))


# ---------------------------------------------------------------- kernel access

class Kernel:
    def __init__(self, api): self.api = api.rstrip('/')

    def _call(self, path, body=None, timeout=10):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.api + path, data=data, method='GET' if body is None else 'POST',
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=timeout) as r: return json.load(r)['data']

    def post(self, fun, data, timeout=30): return self._call('/', dict(fun=fun, data=data), timeout)
    def status(self): return self._call('/kernel/status')
    def devices(self): return {d['deviceid']: d.get('pid', '').upper() for d in self._call('/device/get')['list']}
    def input_status(self): return self._call('/input/status')['phones']

    def alive(self):
        try: self.status(); return True
        except (OSError, ValueError, KeyError): return False


# What a phone's device ID looks like when the kernel does not list it: the MAC-style AirPlay ID, a UDID.
DEVICE_ID_SHAPES = re.compile(r'(?i)(?<![0-9a-f:])(?:[0-9a-f]{2}:){5}[0-9a-f]{2}(?![0-9a-f:])'
                              r'|\b[0-9a-f]{8}-[0-9a-f]{16}\b|(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])')


def without_device_ids(value, ids):
    """`value` (text, list or dict) with no phone device ID left in any string. An ID the kernel knows
    ({device ID: board}) becomes '<phone on board XXXX>'; anything else shaped like one becomes
    '<device id>'. Kernel replies and tool output are quoted into results, and they can name the phone.
    Receiver names, board IDs, placeholder IDs ('pending-<board>') and loopback addresses stay."""
    if isinstance(value, dict): return {k: without_device_ids(v, ids) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [without_device_ids(v, ids) for v in value]
    if not isinstance(value, str): return value
    for device, board in sorted(ids.items(), key=lambda item: -len(item[0])):
        if len(device) >= 6 and not device.startswith('pending-'):
            value = re.sub(re.escape(device), f'<phone on board {board}>', value, flags=re.I)
    return DEVICE_ID_SHAPES.sub('<device id>', value)


def snapshot(kernel):
    """{board: {stopped, generation, message, owned, release_failed}}; device IDs stay out."""
    ids = kernel.devices()
    return {ids[p['id']]: dict(stopped=bool(p.get('stopped')), generation=int(p.get('generation', 0)), message=p.get('message', ''),
                               owned=bool(p.get('owned')), release_failed=bool(p.get('release_failed')))
            for p in kernel.input_status() if p.get('id') in ids}


def ledger_entries(before, after, by, when=None):
    """Boards whose input became stopped between two snapshots, attributed to `by`."""
    when = when or utc()
    out = []
    for board, now in sorted(after.items()):
        was = before.get(board)
        if not now['stopped'] or now['message'] == OPERATOR_STOP: continue
        if was and was['stopped'] and was['generation'] == now['generation']: continue   # already stopped, untouched
        out.append(dict(utc=when, board=board, by=by, generation=now['generation'], message=now['message']))
    return out


def read_ledger(path):
    path = Path(path)
    if not path.exists(): return []
    return [json.loads(l) for l in path.read_text(encoding='utf-8-sig').splitlines() if l.strip()]


def append_ledger(path, entries):
    if not entries: return
    with open(path, 'a', encoding='utf-8') as f:
        for e in entries: f.write(json.dumps(e) + '\n')


def resumable(board, now, ledger):
    """Resume only what we stopped, unchanged since (same generation), never an operator stop."""
    if not now or not now['stopped'] or now['owned'] or now['release_failed'] or now['message'] == OPERATOR_STOP: return False
    ours = [e for e in ledger if e['board'] == board]
    return bool(ours) and ours[-1]['generation'] == now['generation']


# ---------------------------------------------------------------- bring-up plan

def expand(spec):
    """'B19..B1' -> ['B19', ..., 'B1']; '19..10' -> ['19', ..., '10']; a list passes through."""
    if isinstance(spec, list): return [str(s) for s in spec]
    m = re.fullmatch(r'(B?)(\d+)\.\.(B?)(\d+)', spec)
    if not m or m.group(1) != m.group(3): raise SystemExit(f'Bad slot range {spec!r}.')
    a, b = int(m.group(2)), int(m.group(4))
    step = -1 if a > b else 1
    return [f'{m.group(1)}{n}' for n in range(a, b + step, step)]


def slot_boards(rack_a_slots, rack_b_slots):
    """'20' -> rack A board, 'B20' -> rack B board."""
    out = {str(k): v['board'].upper() for k, v in rack_a_slots['slots'].items()}
    out.update({f'B{k}': v['board'].upper() for k, v in rack_b_slots['slots'].items()})
    return out


def build_plan(plan, slots, prep, addresses=None):
    """Ordered phones: dict(group, slot, board, receiver, card, survey_board | None, phone_ip)."""
    names = {r['board'].upper(): r['name'] for r in prep['receivers']}
    addresses = {k.upper(): v for k, v in (addresses or {}).items()}
    out, seen = [], set()
    for step in plan['steps']:
        card = step['card']
        if card not in ('small', 'xr'): raise SystemExit(f"Card must be small or xr: {step}")
        survey = None
        if 'survey' in step:
            survey = slots.get(step['survey'])
            if survey not in names: raise SystemExit(f"Survey phone {step['survey']} has no receiver on this kernel.")
        labels = [step['anchor']] if 'anchor' in step else expand(step['receivers'])
        for label in labels:
            board = slots.get(label)
            if board not in names: continue    # Not on this kernel (the other rack, or an empty slot).
            if board in seen: raise SystemExit(f'{label} appears twice in the plan.')
            seen.add(board)
            out.append(dict(group=step['group'], slot=label, board=board, receiver=names[board], card=card,
                            survey_board=None if 'anchor' in step else survey, phone_ip=addresses.get(board)))
    return out


def crafted_survey(receiver, card, advertised_by_kernel, pc_browse, kernel_names):
    """The anchor phone's survey with no mirroring phone to read the card on: its row is its
    natural-order rank among what the kernel advertises; 'advertised' is the PC's browse (its
    Bonjour cache keeps withdrawn names, and auto_connect compares against that).

    The row is computed, not seen, so it is refused when the PC's browse lists any AirPlay receiver
    that is not one of this kernel's (`kernel_names`: all of them, advertised or not). The phone's card
    lists that receiver too: every row below it shifts, and a tap on its row would mirror the phone
    to it. The PC cannot see what only the phone sees, so a clean browse is necessary, not proof."""
    from farm_mirroring import natural   # The order iOS lists receivers in, as auto_connect.py reads a surveyed card.
    foreign = sorted(set(pc_browse) - set(kernel_names))
    if foreign:
        return None, ('refused: the network lists %d AirPlay receiver(s) that are not this kernel\'s (%s); a computed row cannot be trusted'
                      % (len(foreign), ', '.join(foreign[:3]) + (', ...' if len(foreign) > 3 else '')))
    listed = sorted(set(advertised_by_kernel) | {receiver}, key=natural)
    n = listed.index(receiver) + 1
    row1, pitch, rows = (SMALL_ROW1, SMALL_PITCH, SMALL_ROWS) if card == 'small' else (XR_ROW1, XR_PITCH, XR_ROWS)
    if n > rows: return None, f'{receiver} would be row {n}; the unscrolled card shows {rows}.'
    lines = [dict(text=receiver, cy=row1 + pitch * (n - 1))]
    lines.append(dict(text='Stop Mirroring', cy=729) if card == 'small' else dict(text='Screen Mirroring', cy=162))
    return dict(advertised=sorted(set(pc_browse)), small=card == 'small', lines=lines, crafted=True, row=n), None


# ---------------------------------------------------------------- bring-up run

def last_json(text):
    for line in reversed((text or '').strip().splitlines()):
        try: return json.loads(line)
        except ValueError: continue
    return None


class Actions:
    """Real phone actions, each through the one tool that does it: Release-Receiver.ps1, card_survey.py,
    auto_connect.py. `folder` is this bring-up's own folder inside the kernel's."""

    def __init__(self, kernel, folder):
        self.kernel, self.folder = kernel, Path(folder)
        self.env = dict(os.environ, IMOUSE_RACK_API=kernel.api)

    def advertised(self):
        return {r['name'] for r in self.kernel.status()['receivers'] if r['receiver_pid'] > 0}

    def receivers(self): return {r['name']: r for r in self.kernel.status()['receivers']}
    def release(self, board):
        """Advertises the board's receiver through Release-Receiver.ps1: it checks that the prepared kernel is
        the one running, waits for the receiver process and records the outcome in releases.jsonl, which is
        read back here (no parsing of what the script printed)."""
        releases = self.folder.parent / 'releases.jsonl'
        before = len(read_ledger(releases))
        code = powershell('Release-Receiver.ps1', '-Board', board, log=self.folder / 'release-output.txt')
        if code == 0: return dict(code=0)
        mine = [r for r in read_ledger(releases)[before:] if r.get('board') == board]
        return dict(code=code, message=(mine[-1].get('problem') if mine else '') or 'Release-Receiver.ps1 failed; see release-output.txt')

    def resume(self, board, generation, device_id):
        return self.kernel.post('/input/resume', dict(id=device_id, expected_generations={device_id: generation}))
    def device_id(self, board): return next(d for d, b in self.kernel.devices().items() if b == board)
    def snapshot(self): return snapshot(self.kernel)

    def browse(self):
        from farm_mirroring import browse
        return set(browse(4)[0])

    def _run(self, *args, timeout=240):
        run = subprocess.run([sys.executable, *args], cwd=HERE, env=self.env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, errors='replace', timeout=timeout)
        return run.stdout

    def wake(self, board):
        """Home, pause, Home (card_survey.home_twice): wakes a passcode-less Home-button phone and opens
        it. One lease, renewed before each key and released at the end."""
        from card_survey import home_twice
        device = self.device_id(board)
        lease = self.kernel.post('/input/acquire', dict(id=device, lease_ms=15000))
        if lease.get('code') != 0: return f"wake refused: {lease.get('message')}"
        token = lease['leases'][0]['token']
        answers = []

        def send(fun, purpose, **data):
            self.kernel.post('/input/renew', dict(id=device, token=token))
            answers.append(self.kernel.post(fun, dict(id=device, token=token, **data)))

        try:
            home_twice(send, 'wake', 'open the home screen', pause=1.8)
            refused = [f"code {a.get('code')}: {a.get('message') or 'no message'}" for a in answers if a.get('code') != 0]
            return 'woken' if not refused else 'wake failed (' + '; '.join(refused) + ')'
        finally:
            self.kernel.post('/input/release', dict(id=device, token=token))

    def survey(self, board, small):
        out = self._run('card_survey.py', '--board', board, *(['--small'] if small else []))
        got = last_json(out)
        if not got or not got.get('folder'): return None, 'survey failed: ' + (out.strip().splitlines() or [''])[-1][-200:]
        return STATE / got['folder'] / 'record.json', 'surveyed'

    def write_survey(self, board, survey):
        path = self.folder / f'crafted-{board}-{stamp()}.json'
        path.write_text(json.dumps(dict(survey, board=board), indent=2), encoding='utf-8')
        return path

    def connect(self, board, survey_path, small, phone_ip):
        args = ['auto_connect.py', '--board', board, '--survey', str(survey_path)]
        if small: args.append('--small')
        if phone_ip: args += ['--phone-ip', phone_ip]
        out = self._run(*args)
        got = last_json(out)
        if got and 'result' in got: return got['result'] or ''
        return (out.strip().splitlines() or ['no output'])[-1][-200:]

    def sleep(self, seconds): time.sleep(seconds)


def bring_up(phones, actions, ledger_path, attempts=2):
    """Runs the ordered plan; returns the report rows. Never resumes what someone else stopped."""
    ledger = read_ledger(ledger_path)
    report = []
    for phone in phones:
        row = dict(phone, attempts=[])
        report.append(row)
        receivers = actions.receivers()
        if receivers.get(phone['receiver'], {}).get('live'):
            row['result'] = 'already mirroring'; continue
        for attempt in range(1, attempts + 1):
            tried = dict(attempt=attempt)
            row['attempts'].append(tried)
            state = actions.snapshot().get(phone['board'])
            if state and state['stopped']:
                if not resumable(phone['board'], state, ledger):
                    row['result'] = f"skipped: input stopped by someone else ({state['message'] or 'no message'})"; break
                tried['resume'] = actions.resume(phone['board'], state['generation'], actions.device_id(phone['board'])).get('code')
                if tried['resume'] != 0: row['result'] = 'skipped: resume refused'; break
            released = actions.release(phone['board'])
            tried['release'] = released.get('code')
            if released.get('code') != 0: row['result'] = f"skipped: release refused ({released.get('message')})"; break
            actions.sleep(3)
            if phone['card'] == 'small': tried['wake'] = actions.wake(phone['board'])
            if phone['survey_board'] is None:
                survey, why = crafted_survey(phone['receiver'], phone['card'], actions.advertised(), actions.browse(), set(receivers))
                path = actions.write_survey(phone['board'], survey) if survey else None
                tried['survey'] = 'crafted row %s' % survey['row'] if survey else why
            else:
                path, tried['survey'] = actions.survey(phone['survey_board'], phone['card'] == 'small')
            if path is None:
                row['result'] = tried['survey']
                if survey_retry(tried['survey']): continue
                break
            before = actions.snapshot()
            tried['result'] = actions.connect(phone['board'], path, phone['card'] == 'small', phone.get('phone_ip'))
            mine = ledger_entries(before, actions.snapshot(), 'bringup')   # our own lease expiring, if any
            append_ledger(ledger_path, mine); ledger += mine
            row['result'] = tried['result']
            if tried['result'].startswith('mirroring') or 'already mirroring' in tried['result']: break
            if not retryable(tried['result']): break
            actions.sleep(3)
    return report


def planned_phones(folder, plan_path):
    """(preparation, ordered phones) for the kernel this folder prepares."""
    prep = load(Path(folder) / 'preparation.json')
    learned = Path(prep['runDirectory']) / 'learned-addresses.json'
    # The slot maps are this PC's private state: beside this script in a checkout, in the data folder when installed.
    return prep, build_plan(load(plan_path), slot_boards(load(STATE / 'phone-slots.json'), load(STATE / 'rack-b-slots.json')), prep,
                            load(learned) if learned.exists() else None)


def run_bringup(folder, plan_path, attempts=2):
    """The ordered reconnect against the kernel this folder records. Writes bringup-<time>/report.json and
    returns its path with the summary."""
    folder = Path(folder)
    prep, phones = planned_phones(folder, plan_path)
    record = load(folder / 'processes.json') if (folder / 'processes.json').exists() else {}
    api = record.get('api') or prep['arguments'][0].rstrip('/')
    kernel = Kernel(api)
    if not kernel.alive(): raise SystemExit(f'No kernel answers on {api}.')
    run = folder / f'bringup-{stamp()}'; run.mkdir()
    report = bring_up(phones, Actions(kernel, run), folder / 'input-stops.jsonl', attempts)
    try: ids = kernel.devices()
    except (OSError, ValueError, KeyError): ids = {}   # The kernel went away: the shapes are still removed.
    result = without_device_ids(dict(utc=utc(), api=api, summary=summary(report),
                                     phones=[{k: v for k, v in r.items() if k != 'phone_ip'} for r in report]), ids)
    (run / 'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return dict(report=str(run / 'report.json'), **result['summary'])


def survey_retry(message): return message.startswith('survey failed')


def retryable(result):
    # A phone just woken often misses the first tile tap; a stale survey is read again.
    return any(s in result for s in ('no AirPlay query', 'did not go live', 'differ from the surveyed card', 'lease renewal', 'survey failed'))


def summary(report):
    """Counts for a caller; 'ok' only when every phone in the plan mirrors (a skipped phone is not connected either)."""
    done = [r for r in report if r.get('result', '').startswith('mirroring') or r.get('result') == 'already mirroring']
    return dict(ok=len(done) == len(report), phones=len(report), mirroring=len(done),
                skipped=sum(1 for r in report if r.get('result', '').startswith('skipped')),
                failed=[dict(slot=r['slot'], result=r.get('result', '')) for r in report if r not in done and not r.get('result', '').startswith('skipped')])


# ---------------------------------------------------------------- watchdog

def decide(record, kernel_alive, api_alive, paused, recent_restarts, max_restarts=3, stopping=False):
    """What the watchdog does now. Restarting is only for a kernel that is recorded as running
    and is gone; a stopped kernel (no record), one being stopped on purpose (`stopping`) and a hung
    one (alive, API silent) are left alone."""
    if paused: return 'paused'
    if record is None: return 'idle'                   # Stopped on purpose, or never started.
    if kernel_alive: return 'healthy' if api_alive else 'unresponsive'
    if stopping: return 'stopping'                     # Gone because Stop-Multiphone.ps1 asked; its record is renamed last.
    if recent_restarts >= max_restarts: return 'give-up'
    return 'restart'


def stop_requested(folder, record):
    """True when Stop-Multiphone.ps1 has marked this record's kernel as being stopped on purpose
    (stopping.json names its PID; the script writes it before the kernel is asked to exit)."""
    try: return bool(record) and int(load(Path(folder) / 'stopping.json')['pid']) == int(record['kernel']['pid'])
    except (OSError, ValueError, KeyError, TypeError): return False


def tick_ok(entry):
    """False when a watchdog check ended badly: it gave up, the kernel did not start again, or the bring-up
    after the restart left a phone unconnected (or could not run)."""
    if entry['action'] == 'give-up': return False
    if entry['action'] != 'restart': return True
    return entry.get('start') == 0 and ('bringup' not in entry or bool(entry['bringup'].get('ok')))


def receiver_exe(prep):
    args = prep['arguments']
    return Path(args[args.index('--receiver') + 1]).name.lower() if '--receiver' in args else 'uxplay.exe'


def orphans(processes, kernel_pid, names, exe='uxplay.exe'):
    """Receivers the dead kernel left: receiver children of that PID, or a receiver with one of our names."""
    out = []
    for p in processes:
        if (p.get('Name') or '').lower() != exe: continue
        m = re.search(r'(?:^|\s)-n\s+"?([^\s"]+)', p.get('CommandLine') or '')
        if p.get('ParentProcessId') == kernel_pid or (m and m.group(1) in names): out.append(p['ProcessId'])
    return out


def powershell(script, *args, log=None):
    cmd = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(HERE / script), *args]
    with open(log or os.devnull, 'a', encoding='utf-8') as out:
        return subprocess.run(cmd, cwd=HERE, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, timeout=600).returncode


def processes(receiver='uxplay.exe'):
    out = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                          f"@(Get-CimInstance Win32_Process | Where-Object {{ $_.Name -in 'uxplay.exe','iMouse2.Kernel.exe','{receiver}' }} | "
                          "Select-Object Name,ProcessId,ParentProcessId,CommandLine,ExecutablePath) | ConvertTo-Json -Compress"],
                         stdin=subprocess.DEVNULL, capture_output=True, text=True, errors='replace', timeout=60).stdout.strip()
    got = json.loads(out) if out else []
    return got if isinstance(got, list) else [got]


def kernel_running(record, procs):
    pid, path = record['kernel']['pid'], record['kernel']['path']
    return any(p['ProcessId'] == pid and (p.get('ExecutablePath') or '').lower() == path.lower() for p in procs)


def watch(folder, interval, bringup, once, max_restarts=3, window=3600):
    folder = Path(folder)
    log = folder / 'watchdog.jsonl'
    restarts = []
    misses = 0
    while True:
        record_file = folder / 'processes.json'
        pending = folder / 'watchdog-pending.json'   # A died kernel whose restart has not succeeded yet.
        record = load(record_file) if record_file.exists() else (load(pending) if pending.exists() else None)
        prep = load(folder / 'preparation.json')
        procs = processes(receiver_exe(prep))
        alive = bool(record) and kernel_running(record, procs)
        api = Kernel(record.get('api') or prep['arguments'][0]).alive() if alive else False
        misses = misses + 1 if alive and not api else 0
        restarts = [t for t in restarts if time.time() - t < window]
        # Read after the process snapshot above: a stop writes its marker before the kernel exits, so a kernel
        # seen gone on purpose always has its marker by now.
        stopping = stop_requested(folder, record)
        action = decide(record, alive, api or misses < 3, (folder / 'watchdog-pause').exists(), len(restarts), max_restarts, stopping)
        entry = dict(utc=utc(), action=action)
        if action == 'restart':
            restarts.append(time.time())
            if record_file.exists():
                died = record_file.with_name(f'processes-died-{stamp()}.json'); record_file.rename(died)
                pending.write_text(json.dumps(record), encoding='utf-8')
                entry['record'] = died.name
            names = {r['name'] for r in prep['receivers']}
            left = orphans(procs, record['kernel']['pid'], names, receiver_exe(prep))
            for pid in left:   # Our own receivers, useless without their kernel and holding its ports.
                subprocess.run(['powershell.exe', '-NoProfile', '-Command', f'Stop-Process -Id {pid} -Force'], stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
            entry['orphans_stopped'] = len(left)
            boards = [a for r in prep['receivers'] for a in ('--board', r['board'])]
            goodbye = subprocess.run([sys.executable, str(ROOT / 'tools/mdns_goodbye.py'), '--receivers', str(Path(prep['runDirectory']) / 'data/receivers.json'),
                                      '--status-url', (record.get('api') or prep['arguments'][0].rstrip('/')) + '/kernel/status', *boards],
                                     stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
            entry['goodbye'] = goodbye.returncode
            entry['start'] = powershell('Start-Multiphone.ps1', log=folder / 'watchdog-start.txt')
            if entry['start'] == 0: pending.unlink(missing_ok=True)
            if entry['start'] == 0 and bringup:
                try: entry['bringup'] = run_bringup(folder, HERE / 'bringup-plan.json')
                except (Exception, SystemExit) as error: entry['bringup'] = dict(error=str(error)[-300:])   # noqa: BLE001 - the watchdog keeps watching
        entry['ok'] = tick_ok(entry)
        if action != 'healthy' or once:
            with open(log, 'a', encoding='utf-8') as f: f.write(json.dumps(entry) + '\n')
            print(json.dumps(entry), flush=True)
        if once or action == 'give-up': return entry
        time.sleep(interval)


# ---------------------------------------------------------------- command line

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    s = sub.add_parser('snapshot'); s.add_argument('--api', required=True); s.add_argument('--out', required=True)
    l = sub.add_parser('ledger'); l.add_argument('--api', required=True); l.add_argument('--before', required=True)
    l.add_argument('--by', required=True); l.add_argument('--ledger', required=True)
    b = sub.add_parser('bringup'); b.add_argument('--plan', default=str(HERE / 'bringup-plan.json')); b.add_argument('--plan-only', action='store_true')
    b.add_argument('--attempts', type=int, default=2)
    w = sub.add_parser('watch'); w.add_argument('--interval', type=int, default=30); w.add_argument('--no-bringup', action='store_true')
    w.add_argument('--once', action='store_true'); w.add_argument('--max-restarts', type=int, default=3)
    args = parser.parse_args()
    if args.command == 'snapshot':
        Path(args.out).write_text(json.dumps(snapshot(Kernel(args.api)), indent=2), encoding='utf-8'); return
    if args.command == 'ledger':
        entries = ledger_entries(load(args.before), snapshot(Kernel(args.api)), args.by)
        append_ledger(args.ledger, entries); print(json.dumps(dict(recorded=[e['board'] for e in entries]))); return
    folder = kernel_folder()
    if args.command == 'watch':
        if not tick_ok(watch(folder, args.interval, not args.no_bringup, args.once, args.max_restarts)): raise SystemExit(3)
        return
    if args.plan_only:
        print(json.dumps([{k: v for k, v in p.items() if k != 'phone_ip'} for p in planned_phones(folder, args.plan)[1]], indent=2)); return
    result = run_bringup(folder, args.plan, args.attempts)
    print(json.dumps(result))
    if not result['ok']: raise SystemExit(3)   # A phone in the plan is not mirroring: say so to whoever only reads the exit code.


if __name__ == '__main__':
    main()
