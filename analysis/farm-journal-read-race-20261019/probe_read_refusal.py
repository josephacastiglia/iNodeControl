"""What a Windows reader sees while a journal is replaced. Local temp files only; no socket or phone.

Prints errno/winerror for: a handle that denies read sharing, a delete-pending
file, and a replace-versus-read loop shaped like atomic_json against a status GET
(exists() then read). Run: python probe_read_refusal.py [seconds]
"""
import ctypes
import ctypes.wintypes as w
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
k32.CreateFileW.restype = w.HANDLE
k32.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, w.LPVOID, w.DWORD, w.DWORD, w.HANDLE]
k32.SetFileInformationByHandle.argtypes = [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD]
k32.CloseHandle.argtypes = [w.HANDLE]
GENERIC_READ, DELETE, SHARE_ALL, OPEN_EXISTING, NORMAL = 0x80000000, 0x10000, 7, 3, 0x80


class Disposition(ctypes.Structure):
    _fields_ = [('DeleteFile', w.BOOLEAN)]


def shape(action):
    try:
        action(); return 'no error'
    except OSError as error:
        return dict(type=type(error).__name__, errno=error.errno, winerror=getattr(error, 'winerror', 'absent'))


def main(seconds):
    root = Path(tempfile.mkdtemp(prefix='journal-read-probe-'))
    try:
        target = root / 'record.json'; target.write_text('{}')
        handle = k32.CreateFileW(str(target), GENERIC_READ, 0, None, OPEN_EXISTING, NORMAL, None)
        print('read while another handle denies sharing:', shape(target.read_bytes))
        k32.CloseHandle(handle)
        handle = k32.CreateFileW(str(target), DELETE, SHARE_ALL, None, OPEN_EXISTING, NORMAL, None)
        mark = Disposition(True)
        marked = k32.SetFileInformationByHandle(handle, 4, ctypes.byref(mark), ctypes.sizeof(mark))
        print('read while delete is pending (marked=%s):' % bool(marked), shape(target.read_bytes))
        k32.CloseHandle(handle)

        target.write_text('{}'); stop = time.monotonic() + seconds
        counts = dict(reads=0, exists_false=0, exists_raised=0, refusals={})
        def writer():
            n = 0
            while time.monotonic() < stop:
                temporary = target.with_suffix('.writing'); temporary.write_text(json.dumps({'n': n})); n += 1
                while True:  # Same retry as atomic_json's replace.
                    try: temporary.replace(target); break
                    except OSError as error:
                        if getattr(error, 'winerror', None) not in (5, 32, 33): raise
                        time.sleep(.001)
        def reader():
            while time.monotonic() < stop:
                try:
                    if not target.exists(): counts['exists_false'] += 1; continue
                except OSError: counts['exists_raised'] += 1; continue
                try: json.loads(target.read_bytes()); counts['reads'] += 1
                except OSError as error:
                    key = '%s errno=%s winerror=%s' % (type(error).__name__, error.errno, getattr(error, 'winerror', 'absent'))
                    counts['refusals'][key] = counts['refusals'].get(key, 0) + 1
        threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        print('replace-versus-read for %ss:' % seconds, json.dumps(counts))
        print(sys.version.split()[0])
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == '__main__':
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 4)
