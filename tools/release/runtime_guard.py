"""Run an installed farm entry point under a Python audit hook and report what it touched.

  python -E runtime_guard.py --forbid <dev folder> --report <json> [--import-all <tools dir>] -- <script> [args]

The hook records every opened path, refuses to start any process (subprocess, os.system, startfile)
and refuses any socket connection except to a port this same process bound (the farm server's own
self-check). So the guarded code cannot reach the live kernel, a receiver or a phone. At the end the
report lists opened paths, loaded module files and sys.path entries under the forbidden folder: all
three must be empty for "the dev folder was not read at runtime".
"""
import json
import os
import runpy
import sys
import traceback
from pathlib import Path

args = sys.argv[1:]
split = args.index('--') if '--' in args else len(args)
opts, target = args[:split], args[split + 1:]
forbid = [os.path.normcase(os.path.abspath(opts[i + 1])) for i, a in enumerate(opts) if a == '--forbid']
report_path = opts[opts.index('--report') + 1]
import_all = opts[opts.index('--import-all') + 1] if '--import-all' in opts else None

opened, refused, bound = [], [], set()
LOOPBACK = ('127.0.0.1', 'localhost', '::1')
FARM_PORTS = set(range(9911, 9950))  # kernels (9913/9916), backends and media servers


def under_forbidden(path):
    try:
        p = os.path.normcase(os.path.abspath(os.fsdecode(path)))
    except (TypeError, ValueError):
        return False
    return any(p == f or p.startswith(f + os.sep) for f in forbid)


def hook(event, hook_args):
    if event == 'open' and hook_args and isinstance(hook_args[0], (str, bytes, os.PathLike)):
        opened.append(os.fsdecode(hook_args[0]))
    elif event in ('os.listdir', 'os.scandir', 'os.chdir', 'os.mkdir', 'os.rename', 'os.remove', 'shutil.copyfile', 'shutil.rmtree'):
        if hook_args and isinstance(hook_args[0], (str, bytes, os.PathLike)):
            opened.append(os.fsdecode(hook_args[0]))
    elif event in ('subprocess.Popen', 'os.system', 'os.startfile', 'os.posix_spawn', 'os.spawn', '_winapi.CreateProcess'):
        refused.append(f'{event}: {str(hook_args)[:120]}')
        raise PermissionError(f'runtime guard: no processes ({event})')
    elif event == 'socket.connect' and len(hook_args) > 1 and isinstance(hook_args[1], tuple):
        host, port = hook_args[1][0], hook_args[1][1]
        # Allowed only: loopback, to a port a socket of this process bound (the self-check's own server).
        # Never a kernel, backend, media or receiver port.
        if host not in LOOPBACK or port not in bound or port in FARM_PORTS or 7100 <= port <= 7599:
            refused.append(f'socket.connect {host}:{port}')
            raise PermissionError(f'runtime guard: connection to {host}:{port} refused')


import socket  # noqa: E402
_bind = socket.socket.bind


def _recording_bind(self, address):
    """Record the port the OS actually gave a loopback socket (port 0 = any free port)."""
    _bind(self, address)
    if isinstance(address, tuple) and address[0] in LOOPBACK:
        bound.add(self.getsockname()[1])


socket.socket.bind = _recording_bind

# Nothing from this guard's folder or the current directory may be imported.
sys.path[:] = [p for p in sys.path if p and os.path.abspath(p) != os.path.dirname(os.path.abspath(__file__))]
sys.addaudithook(hook)
result = {'target': target, 'exit': None, 'error': None, 'imported': []}
try:
    if import_all:
        sys.path.insert(0, import_all)
        for module in sorted(Path(import_all).glob('*.py')):
            if module.name.startswith('test_'):
                continue
            try:
                __import__(module.stem)
                result['imported'].append(module.stem)
            except SystemExit:
                result['imported'].append(module.stem)
            except Exception as error:  # an import that needs a phone or the rack is reported, not fatal
                result.setdefault('import_errors', {})[module.stem] = f'{type(error).__name__}: {error}'[:200]
    if target:
        sys.path.insert(0, os.path.dirname(os.path.abspath(target[0])))
        sys.argv = list(target)
        try:
            runpy.run_path(target[0], run_name='__main__')
            result['exit'] = 0
        except SystemExit as stop:
            result['exit'] = stop.code if isinstance(stop.code, int) else (0 if stop.code is None else 1)
except BaseException as error:
    result['error'] = ''.join(traceback.format_exception_only(type(error), error)).strip()[:500]
finally:
    modules = [getattr(m, '__file__', None) for m in list(sys.modules.values())]
    modules = [m for m in modules if m]
    result.update(
        opened_count=len(opened), modules_loaded=len(modules), refused=refused,
        forbidden_opened=sorted({p for p in opened if under_forbidden(p)}),
        forbidden_modules=sorted({m for m in modules if under_forbidden(m)}),
        forbidden_sys_path=sorted({p for p in sys.path if p and under_forbidden(p)}),
        opened_roots=sorted({str(Path(os.path.abspath(p)).parents[min(3, len(Path(os.path.abspath(p)).parents) - 1)]) for p in opened if os.path.isabs(os.path.abspath(p))})[:40],
    )
    with open(report_path, 'w', encoding='utf-8') as handle:
        json.dump(result, handle, indent=1)
