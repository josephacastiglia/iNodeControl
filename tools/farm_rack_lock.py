"""Rack-wide run lock: one opted-in phone run on the rack at a time.

Parallel lanes' runs share one PC; their screen reading (Windows OCR) under load aged decisions past
the 1.5 s frame limit (A18, 4 Nov: 'DecisionExpired 1740 ms', 'FrameNotRecent'). The limit stays; runs
that hold this lock simply do not overlap. It is an OS lock on a file (farm_paths.RUN_LOCK), so it is
released when its holder exits or dies; a side file names the holder for whoever waits.

    with rack_run_lock('slot runner phone 18 pkg reel18-abc123'):
        ...   # the whole run: backend start, start screen, creation, verifier, stop

Nothing here touches a phone or the kernel.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from farm_paths import RUN_LOCK  # noqa: E402


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
def rack_run_lock(holder, path=RUN_LOCK, wait=0.0, poll=1.0, sleep=time.sleep, clock=time.monotonic):
    """Hold the rack for one run; waits up to `wait` seconds, then raises RackBusy."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, 'a+b')
    try:
        if handle.tell() == 0: handle.write(b'\0'); handle.flush()
        handle.seek(0)
        deadline = clock() + wait
        while not _try_lock(handle):
            if clock() >= deadline:
                busy = current_holder(path); raise RackBusy(busy.get('holder') if busy else None)
            sleep(poll); handle.seek(0)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            json.dump({'holder': str(holder), 'pid': os.getpid(), 'since': time.time()}, out)
        os.replace(tmp, _holder_path(path))
        try: yield
        finally:
            try: _holder_path(path).unlink()
            except OSError: pass
            _unlock(handle)
    finally: handle.close()
