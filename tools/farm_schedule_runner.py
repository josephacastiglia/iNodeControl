"""Runs due approved slots on a phone: one at a time, never late, never retried by itself.

A scheduled package here is a prepared farm window (prepare_window.py): its exact test package,
backend data and creation config, staged out of the way under the queue's state folder so several
can wait for their slots. For each due slot on its phone the runner:

  1. claims it in the queue (planned -> running; a passed slot lapses there, never runs late);
  2. checks the staged window still holds the approved package and the phone is mirroring
     (receiver live, frames flowing and fresh) and idle (no lease, no stop, no release pending);
  3. puts the window back in place and starts its backend (Start-Window.ps1);
  4. brings the phone to the platform's start screen (farm_start_screen.py) - the first phone input;
  5. runs the window's creation once (run_window.py --attempt 1: the backend's own runs class,
     e.g. farm_reel_runs.ReelCreationRuns on slot 18, which ends with its read-only verifier);
  6. optionally (--recheck, off by default) reruns only the read-only verifier once
     (verify_window.py --check 2) when creation saved a draft but its verifier stopped;
  7. stops the backend (Stop-Window.ps1) and archives the window (windows-archive/);
  8. records the one outcome on the slot: verified, stopped (with the reason) or not_ready.

Anything that fails before the first phone input is 'not_ready': the window goes back to staging
and the package to approved, with no slot (a new slot needs `plan --commit`). After the first input
a failure is 'stopped': the package stays stopped for the operator. The runner never repeats a
creation, never sends input itself, and never touches the kernel, a receiver or another phone.
Draft only: the creation runs have no publish path; nothing here posts or messages.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from farm_schedule_queue import NOT_READY, STOPPED_SAFELY, VERIFIED, check_label  # noqa: E402
import farm_paths  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'analysis/farm-multiphone-20261020'  # release-lint: code (the rack scripts; their state: farm_paths.rack_state)
KERNEL = 'http://127.0.0.1:9916/api'
MAX_FRAME_AGE_MS = 1500
# window platform -> (queue platform label, start screen)
PLATFORMS = {'reel': ('instagram', 'instagram-profile'), 'tiktok': ('tiktok', 'tiktok-profile'),
             'tiktok-photo': ('tiktok', 'tiktok-profile'), 'x': ('x', 'x-timeline'),
             'x-image': ('x', 'x-timeline'), 'youtube': ('youtube', 'youtube-home')}
FORMATS = {'reel': 'ig_reel', 'tiktok': 'tt_video', 'tiktok-photo': 'tt_photo', 'x': 'x_video',
           'x-image': 'x_image', 'youtube': 'yt_short'}
SAFETY = {'phoneInput': 'through the window backend only', 'publishing': False, 'messaging': False}


class PhoneNotReady(Exception):
    """Refused before any phone input; the package goes back to approved."""


def phone_ready(kernel_status, input_status, prep):
    """The reason this window's phone can't take a run now, or None. Pure, for fakes and the live kernel alike."""
    phone = prep['phone']
    if kernel_status.get('build_identity', {}).get('sha256') != prep['kernelSha256']:
        return 'the kernel is not the one this window was prepared on'
    own = [r for r in kernel_status.get('receivers', []) if r.get('deviceid') == phone['deviceId']]
    if len(own) != 1 or own[0].get('name') != phone['receiver']: return 'the kernel does not map this phone to its receiver'
    r = own[0]
    if not r.get('live') or r.get('receiver_state') != 'mirroring': return f'not mirroring (receiver {r.get("receiver_state")})'
    # AirPlay sends no frames while the screen is still: the kernel calls an idle phone 'quiet' (4 Nov, A18 on
    # Home: 55 s without a frame, flowing again at the next change). Quiet is ready; the start screen and the
    # workflow refuse stale frames themselves. Anything else, or a broken frame pipe, is not.
    delivery = r.get('frame_delivery')
    if delivery not in ('flowing', 'quiet') or not r.get('frame_pipe_connected'): return f'mirror frames are not arriving ({delivery})'
    age = r.get('frame_age_ms')
    if delivery == 'flowing' and (not isinstance(age, (int, float)) or age > MAX_FRAME_AGE_MS):
        return f'mirror stalled (newest frame {age} ms old)'
    mine = [p for p in input_status.get('phones', []) if p.get('id') == phone['deviceId']]
    if len(mine) != 1: return 'the phone has no input board on the kernel'
    held = [k for k in ('owned', 'active', 'stopped', 'releasing', 'release_failed') if mine[0].get(k)]
    if held: return 'the phone is not idle (' + ', '.join(held) + ')'
    return None


def start_screen_problem(code, last_line):
    """The start screen's summary state decides; since 5d35b76 it also exits 1 on any stop (4 Nov it exited 0)."""
    if code != 0: return f'start screen: {last_line}'[:300]
    try: summary = json.loads(last_line)
    except ValueError: return f'start screen gave no summary: {last_line}'[:300]
    if summary.get('state') in ('at_start', 'already_at_start'): return None
    return f'start screen {summary.get("state")}: {summary.get("error")}'[:300]


def outcome_of(run):
    """(outcome, reason) for run_window's retained run."""
    if run.get('terminal') and run.get('savedDraftVerified') is True: return VERIFIED, run.get('reason') or 'verified'
    why = run.get('error') or run.get('reason') or f'run ended {run.get("state")}'
    return STOPPED_SAFELY, f'{run.get("state")}: {why}'[:500]


def saved_unverified(run):
    """Creation saved one draft and only its verifier stopped: the case verify_window.py reruns."""
    workflow = run.get('workflow') or {}
    return bool(run.get('terminal') and workflow.get('creationState') == 'created_unverified' and not run.get('savedDraftVerified')
                and workflow.get('cleanup') == 'confirmed' and isinstance(workflow.get('verification'), dict))


class WindowSteps:
    """The live steps, each the existing window tool run as its own process (the same path as by hand)."""

    def __init__(self, staging, folder=FOLDER, kernel=KERNEL, python=sys.executable, log_dir=None):
        self.staging, self.folder, self.kernel, self.python = Path(staging), Path(folder), kernel, python
        # Code runs from self.folder; window state lives there too in a checkout, in the data folder when installed.
        self.state = farm_paths.rack_state(self.folder)
        self.log_dir = Path(log_dir) if log_dir else self.staging.parent / 'runs'

    # --- staging ---
    def window_path(self, name): return self.state / 'windows' / name
    def staged(self, package_id): return self.staging / str(package_id)

    def read_staged(self, package_id):
        path = self.staged(package_id) / 'preparation.json'
        if not path.exists(): raise PhoneNotReady('the staged window is missing')
        return json.loads(path.read_text(encoding='utf-8'))

    def window_in_place(self, name): return self.window_path(name).exists()

    def restore(self, package_id, name):
        if self.window_in_place(name): raise PhoneNotReady(f'another window {name} is in place')
        shutil.move(str(self.staged(package_id)), str(self.window_path(name)))

    def unstage_back(self, package_id, name):
        shutil.move(str(self.window_path(name)), str(self.staged(package_id)))

    def archive(self, package_id, name):
        archive = self.state / 'windows-archive'; archive.mkdir(exist_ok=True)
        target = next(archive / f'{name}-sched-{package_id}-{n}' for n in range(1, 1000)
                      if not (archive / f'{name}-sched-{package_id}-{n}').exists())
        shutil.move(str(self.window_path(name)), str(target))
        return target

    # --- kernel (read-only) ---
    def _call(self, url, body=None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(url, data=data, method='GET' if body is None else 'POST',
                                         headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=8) as response: return json.load(response)

    def phone_ready(self, prep):
        try:
            status = self._call(self.kernel + '/kernel/status')['data']
            phones = self._call(self.kernel + '/', dict(fun='/input/status', data={}))['data']
        except OSError as error: return f'the kernel did not answer ({error})'
        return phone_ready(status, phones, prep)

    # --- the window tools ---
    def _run(self, package_id, label, argv, timeout):
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log = self.log_dir / f'{package_id}-{label}.txt'
        # Output goes straight to a file, never a pipe: Start-Window leaves a backend running that inherits
        # the tool's handles, and waiting on a pipe it holds never ends (4 Nov, slot 18). Only the tool's
        # own exit is awaited. A timed-out tool is left running (it may be following a live run).
        with open(log, 'wb') as handle:
            process = subprocess.Popen(argv, cwd=self.folder, stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT)
            try: code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired: code = None
        lines = [line.strip() for line in log.read_text(encoding='utf-8', errors='replace').splitlines() if line.strip()]
        if code is None:
            with open(log, 'a', encoding='utf-8') as handle: handle.write(f'\nTIMEOUT after {timeout} s (left running)\n')
            return None, f'{label} did not end within {timeout} s'
        return code, (lines[-1:] or [''])[0]   # Whole: a summary line is JSON (22:48 slot); messages cut it.

    def _powershell(self, script, name):
        return ['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                '-File', str(self.folder / script), '-Window', name]

    def start(self, package_id, name):
        code, tail = self._run(package_id, 'start-window', self._powershell('Start-Window.ps1', name), 90)
        return None if code == 0 else f'Start-Window: {tail[:300]}'

    def backend_running(self, name): return (self.window_path(name) / 'processes.json').exists()

    def start_screen(self, package_id, name, prep):
        window = self.window_path(name)
        argv = [self.python, str(ROOT / 'tools/farm_start_screen.py'), PLATFORMS[prep['platform']][1],
                str(window / 'start-screen-1'), str(window / 'creation-config.json')]
        code, tail = self._run(package_id, 'start-screen', argv, 240)
        return start_screen_problem(code, tail)

    def create(self, package_id, name):
        """run_window.py attempt 1; returns (run or None, problem)."""
        code, tail = self._run(package_id, 'run-window', [self.python, str(self.folder / 'run_window.py'),
                                                           '--window', name, '--attempt', '1'], 40 * 60)
        result = self.window_path(name) / 'attempt-1' / 'result.json'
        if code is None: return None, tail
        if not result.exists(): return None, f'run_window: {tail[:300]}'
        return json.loads(result.read_text(encoding='utf-8'))['run'], None

    def admitted(self, name):
        """Whether run_window got as far as admitting a run (its request is on disk)."""
        return (self.window_path(name) / 'attempt-1' / 'request.json').exists()

    def recheck(self, package_id, name, check=2):
        code, tail = self._run(package_id, f'verify-{check}', [self.python, str(self.folder / 'verify_window.py'), '--window', name,
                                                               '--attempt', '1', '--check', str(check)], 15 * 60)
        result = self.window_path(name) / 'attempt-1' / f'verification-{check}.json'
        if not result.exists(): return None, f'verify_window: {tail[:300]}'
        return json.loads(result.read_text(encoding='utf-8')), None

    def stop(self, package_id, name):
        code, tail = self._run(package_id, 'stop-window', self._powershell('Stop-Window.ps1', name), 60)
        return None if code == 0 else f'Stop-Window: {tail[:300]}'


def stage_window(steps, queue, name, account, package_id=None):
    """Move a freshly prepared, never started window into staging and queue its exact package (pending).
    Refused for a started or used window. Returns the queued package."""
    check_label(account, 'Account')
    window = steps.window_path(name)
    prep_path = window / 'preparation.json'
    if not prep_path.exists(): raise ValueError(f'No prepared window {name}.')
    prep = json.loads(prep_path.read_text(encoding='utf-8'))
    used = [p.name for p in window.iterdir() if p.name == 'processes.json' or p.name.startswith(('attempt-', 'start-screen', 'processes-'))]
    if used: raise ValueError(f'Window {name} was already started or run ({", ".join(sorted(used))}); only a fresh window is staged.')
    if Path(prep['config']).resolve() != (window / 'creation-config.json').resolve():
        raise ValueError('The window config does not live in the window folder; nothing was staged.')
    if prep['platform'] not in PLATFORMS: raise ValueError(f'No start screen for platform {prep["platform"]}.')
    if name != f'{prep["platform"]}-slot{prep["slot"]}': raise ValueError('Window name and preparation differ.')
    package_id = package_id or f'{prep["platform"].replace("-", "")}{prep["slot"]}-{prep["testToken"][:6]}'
    target = steps.staged(package_id)
    if target.exists(): raise ValueError(f'Package {package_id} is already staged.')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(window), str(target))
    try:
        return queue_staged(steps, queue, package_id, account)
    except Exception:
        shutil.move(str(target), str(window)); raise


def queue_staged(steps, queue, package_id, account):
    """A test window prepared straight into staging (prepare_window.py --into) enters the queue, pending."""
    check_label(account, 'Account')
    prep = steps.read_staged(package_id)
    name = f'{prep["platform"]}-slot{prep["slot"]}'
    source = {'kind': 'window', 'window': name, 'slot': prep['slot'], 'manifestSha256': prep['packageSha256'],
              'stagedFiles': [prep['downloadName']], 'testPackage': True, 'testToken': prep['testToken'],
              'backendSourceHash': prep['backendSourceHash']}
    return queue.submit(package_id, PLATFORMS[prep['platform']][0], FORMATS[prep['platform']], account, prep['caption'], source)


def prepare_command(platform, slot, phone_ip, handle, staging, python=sys.executable, folder=FOLDER, package_id=None, content=None, content_stage=None):
    """prepare_window.py straight into staging. Offline: no socket, no phone."""
    argv = [python, str(Path(folder) / 'prepare_window.py'), '--platform', platform, '--slot', str(slot), '--phone-ip', phone_ip, '--into', str(staging)]
    if handle: argv += ['--account', handle]
    if package_id is not None: argv += ['--package-id', str(package_id)]
    if content is not None: argv += ['--content', str(content), '--content-stage', str(content_stage)]
    return argv


def run_prepare(argv):
    """Runs prepare_window; returns its summary, or raises ValueError with its own reason."""
    done = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600)
    lines = [line for line in (done.stdout or '').splitlines() if line.strip()]
    if done.returncode: raise ValueError((done.stderr or done.stdout or 'prepare_window failed').strip().splitlines()[-1][:400])
    return json.loads(lines[-1])


def convert_package(steps, queue, package_id, slot, phone_ip, handle, stage_root, prepare=run_prepare):
    """An approved real package -> its staged window, bound in the queue. Local only; it runs when a slot is planned."""
    from farm_schedule_content import platform_of
    queue.reload()
    pkg = queue.state['packages'].get(str(package_id))
    if pkg is None: raise ValueError(f'No package {package_id} in the queue.')
    if pkg['state'] != 'approved': raise ValueError(f'Package {package_id} is {pkg["state"]}; only an approved package is converted.')
    if pkg['source'].get('kind') == 'window': raise ValueError(f'Package {package_id} already has a window.')
    platform = platform_of(pkg['format'])
    item = dict(pkg['source'], format=pkg['format'], platform=pkg['platform'], caption=pkg['caption'], id=pkg['id'])
    steps.staging.mkdir(parents=True, exist_ok=True)
    content = steps.staging / f'{package_id}.content.json'
    content.write_text(json.dumps(item), encoding='utf-8')
    try:
        summary = prepare(prepare_command(platform, slot, phone_ip, handle, steps.staging, package_id=package_id, content=content, content_stage=stage_root))
    finally: content.unlink(missing_ok=True)
    prep = steps.read_staged(package_id)
    if prep.get('caption') != pkg['caption'] or prep.get('testPackage') is not False: raise ValueError('The prepared window does not hold this package.')
    queue.bind_window(package_id, f'{platform}-slot{slot}', slot, prep['packageSha256'])
    return summary


@contextmanager
def phone_lock(path):
    """One runner per phone: a second runner process for the same phone is refused at once."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, 'a+b')
    try:
        if handle.tell() == 0: handle.write(b'\0'); handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ValueError(f'Another slot runner holds {path.name}.') from None
        yield
    finally: handle.close()


class SlotRunner:
    def __init__(self, queue, steps, phone, recheck=False, clock=time.time, sleep=time.sleep, log=lambda line: None,
                 rack_lock=None):
        self.queue, self.steps, self.phone, self.recheck = queue, steps, phone, recheck
        self.clock, self.sleep, self.log = clock, sleep, log
        # rack_lock(holder) -> context manager that raises farm_rack_lock.RackBusy when another run holds the rack.
        self.rack_lock, self.waiting_on = rack_lock, None

    def run_due(self):
        """Claims and runs the earliest due slot for this phone; returns its outcome record or None."""
        self.queue.lapse_stale()
        if self.queue.in_progress(self.phone):
            raise ValueError(f'Phone {self.phone} has a run without a recorded end; review it and `abandon` it first.')
        due = self.queue.due(self.phone)
        if not due: return None
        if self.rack_lock is None: return self._run(due[0]['id'])
        from farm_rack_lock import RackBusy
        try: lock = self.rack_lock(f'slot runner, phone {self.phone}, pkg {due[0]["id"]}'); lock.__enter__()
        except RackBusy as busy:
            # Not claimed: the slot waits within its grace, then lapses (never late). Logged once per holder.
            if busy.holder != self.waiting_on: self.log(f'pkg {due[0]["id"]}: waiting, {busy}')
            self.waiting_on = busy.holder
            return None
        self.waiting_on = None
        try: return self._run(due[0]['id'])
        finally: lock.__exit__(None, None, None)

    def _run(self, package_id):
        pkg = self.queue.claim(package_id, self.phone)
        self.log(f'pkg {pkg["id"]}: claimed slot on phone {self.phone}')
        try: outcome, reason, details = self._execute(pkg)
        except Exception as error:    # Unknown state after the claim: stop, never retry.
            outcome, reason, details = STOPPED_SAFELY, f'runner error: {type(error).__name__}: {error}'[:500], {}
        done = self.queue.finish(pkg['id'], outcome, reason, **details)
        self.log(f'pkg {pkg["id"]}: {outcome} - {reason}')
        return done['runs'][-1]

    def _execute(self, pkg):
        steps, source, pid = self.steps, pkg['source'], pkg['id']
        name = source.get('window')
        if source.get('kind') != 'window' or not name: return NOT_READY, 'the package names no prepared window', {}
        # Before any phone input: anything refused here leaves the window staged.
        try:
            prep = steps.read_staged(pid)
            expected = source.get('windowPackageSha256') or source.get('manifestSha256')   # A real package's batch manifest is not its window package.
            if prep.get('packageSha256') != expected or prep.get('slot') != self.phone or prep.get('caption', pkg['caption']) != pkg['caption']:
                raise PhoneNotReady('the staged window no longer holds the approved package')
            problem = steps.phone_ready(prep)
            if problem: raise PhoneNotReady(problem)
            steps.restore(pid, name)
        except PhoneNotReady as why: return NOT_READY, str(why), {}
        problem = steps.start(pid, name)
        if problem:
            if steps.backend_running(name):
                stop = steps.stop(pid, name)
                if stop: return STOPPED_SAFELY, f'{problem}; {stop} (window left in place)', {}
            steps.unstage_back(pid, name)
            return NOT_READY, problem, {}
        problem = steps.phone_ready(prep)
        if problem: return self._close(pid, name, NOT_READY, problem, {}, restage=True)
        # First phone input from here on.
        problem = steps.start_screen(pid, name, prep)
        if problem: return self._close(pid, name, STOPPED_SAFELY, problem, {})
        run, problem = steps.create(pid, name)
        if run is None:
            if problem and 'did not end' in problem:    # The backend may still drive the phone: leave it for review.
                return STOPPED_SAFELY, problem + '; window left running for review', {}
            return self._close(pid, name, STOPPED_SAFELY, problem, {})
        outcome, reason = outcome_of(run)
        details = {'runId': run.get('id'), 'runState': run.get('state'), 'savedDraftVerified': run.get('savedDraftVerified'),
                   'cleanup': run.get('cleanup')}
        if outcome != VERIFIED and saved_unverified(run):
            details['savedUnverified'] = True
            if self.recheck:
                result, problem = steps.recheck(pid, name, 2)
                details['recheck'] = {'check': 2, 'state': (result or {}).get('state'),
                                      'savedDraftVerified': (result or {}).get('savedDraftVerified'), 'problem': problem}
                if result and result.get('savedDraftVerified') is True:
                    outcome, reason = VERIFIED, 'saved by creation; verified by read-only check 2'
                else: reason = f'{reason}; read-only check 2: {problem or (result or {}).get("error") or (result or {}).get("state")}'[:500]
            else: reason = f'{reason}; draft saved, verifier stopped: verify_window.py --check 2 may recheck it (read-only)'[:500]
        return self._close(pid, name, outcome, reason, details)

    def _close(self, pid, name, outcome, reason, details, restage=False):
        problem = self.steps.stop(pid, name)
        if problem:
            return (STOPPED_SAFELY if outcome == NOT_READY else outcome), f'{reason}; {problem} (window left in place)', details
        if restage: self.steps.unstage_back(pid, name)
        else: details['archive'] = self.steps.archive(pid, name).name
        return outcome, reason, details

    def run(self, max_slots=1, wait_seconds=0):
        """Runs due slots one after another, waiting up to wait_seconds for the next one to come due."""
        records, deadline = [], self.clock() + wait_seconds
        while len(records) < max_slots:
            record = self.run_due()
            if record: records.append(record); continue
            upcoming = self.queue.next_slot(self.phone)
            if upcoming is None or upcoming > deadline: break
            self.sleep(max(5.0 if self.waiting_on is not None else 1.0, min(30.0, upcoming - self.clock())))
        return records
