"""Rack-wide run lock: one opted-in phone run on the rack at a time.

Parallel lanes' runs share one PC; their screen reading (Windows OCR) under load aged decisions past
the 1.5 s frame limit (A18, 4 Nov: 'DecisionExpired 1740 ms', 'FrameNotRecent'). The limit stays; runs
that hold this lock simply do not overlap. It is an OS lock on a file (farm_paths.RUN_LOCK), so it is
released when its holder exits or dies; a side file names the holder for whoever waits.

    with rack_run_lock('slot runner phone 18 pkg reel18-abc123'):
        ...   # the whole run: backend start, start screen, creation, verifier, stop

The tools a person or a lane runs by hand (run_window, verify_window, relaunch_check, farm_start_screen) use
hold_rack: it waits for the rack, says so once, and exits clearly before any phone input when the wait runs out
(IMOUSE_RACK_WAIT seconds, default 30 min). A tool started by the holder joins its hold: the holder's token goes
to its child processes through the environment, and only counts while that holder still holds the lock. A hold
ends with its tool; a backend run its tool started keeps going if the tool is killed, and its own phone lease
still protects that phone. The lock lives in the main folder (farm_paths), so every lane folder shares it.

Nothing here touches a phone or the kernel.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from farm_paths import RUN_LOCK  # noqa: E402


TOKEN_ENV = 'IMOUSE_RACK_LOCK_TOKEN'
DEFAULT_WAIT = 1800


class RackBusy(Exception):
    """Another opted-in run holds the rack."""
    def __init__(self, holder): super().__init__(f'The rack is busy: {holder or "another run"}.'); self.holder = holder


def _holder_path(path): return Path(path).with_suffix('.holder.json')


def current_holder(path=RUN_LOCK):
    """Who holds the lock, as its holder wrote it (informational; the OS lock decides)."""
    try: return json.loads(_holder_path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError): return None


def _try_lock(handle):
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError: return False


def _unlock(handle):
    if os.name == 'nt':
        import msvcrt
        handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def rack_run_lock(holder, path=RUN_LOCK, wait=0.0, poll=1.0, sleep=time.sleep, clock=time.monotonic, on_wait=None):
    """Hold the rack for one run; waits up to `wait` seconds, then raises RackBusy. Started by the holder (its
    token in the environment, and it still holds the lock): joins that hold."""
    path = Path(path)
    inherited = os.environ.get(TOKEN_ENV)
    if inherited and (current_holder(path) or {}).get('token') == inherited:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, 'a+b')
    try:
        if handle.tell() == 0: handle.write(b'\0'); handle.flush()
        handle.seek(0)
        deadline, waited = clock() + wait, False
        while not _try_lock(handle):
            busy = current_holder(path)
            if clock() >= deadline: raise RackBusy(busy.get('holder') if busy else None)
            if on_wait and not waited: on_wait(busy.get('holder') if busy else None)
            waited = True
            sleep(poll); handle.seek(0)
        token = uuid.uuid4().hex
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump({'holder': str(holder), 'pid': os.getpid(), 'since': time.time(), 'token': token}, out)
        os.replace(tmp, _holder_path(path))
        before, os.environ[TOKEN_ENV] = os.environ.get(TOKEN_ENV), token
        try: yield
        finally:
            if before is None: os.environ.pop(TOKEN_ENV, None)
            else: os.environ[TOKEN_ENV] = before
            try: _holder_path(path).unlink()
            except OSError: pass
            try: _unlock(handle)
            except OSError: pass   # Closing the handle below releases it too; a finished run is never failed for this.
    finally: handle.close()


@contextmanager
def hold_rack(holder, path=RUN_LOCK, wait=None, poll=2.0, sleep=time.sleep, clock=time.monotonic):
    """rack_run_lock for a hand-run tool: waits (saying so once), then exits before any phone input."""
    if wait is None: wait = float(os.environ.get('IMOUSE_RACK_WAIT', DEFAULT_WAIT))
    notice = lambda who: print(f'Waiting for the rack: {who or "another run"} holds it (up to {wait:.0f} s).', file=sys.stderr, flush=True)
    lock = rack_run_lock(holder, path, wait=wait, poll=poll, sleep=sleep, clock=clock, on_wait=notice)
    try: lock.__enter__()
    except RackBusy as busy: raise SystemExit(f'{busy} Waited {wait:.0f} s. Nothing was sent to a phone; run it again later.') from None
    try: yield
    except BaseException:
        if not lock.__exit__(*sys.exc_info()): raise
    else: lock.__exit__(None, None, None)
