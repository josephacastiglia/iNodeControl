"""The rack kernel's preparation: where it lives, moving it to another kernel build, and the checks
Start-Multiphone.ps1 and Stop-Multiphone.ps1 make before a start and after a stop. One kernel serves
both racks.

  python rack_kernels.py rekernel --base slots/preparation-<archived>.json --kernel <exe>
      Offline. The same preparation (same run folder, data and arguments) on another kernel build:
      only kernel and kernelSha256 change. Writes slots/preparation.json; refuses to overwrite it.
  python rack_kernels.py check-start --prep <preparation.json>    < snapshot.json
  python rack_kernels.py check-stopped --prep <preparation.json>  < snapshot.json
      The snapshot is {"processes": [{Name, ProcessId, CommandLine}], "listeners": [port, ...]} from
      Start-/Stop-Multiphone.ps1. Prints {"ok", "reasons", "ports"}; exit 3 when not ok.

A sandbox preparation ("sandbox": true) is what the off-rack trials and the release rehearsal write: a
kernel on a port no real kernel or farm service uses, with stand-in receivers and absent test boards.
It is checked only against its own kernel, receivers and ports, so it can run beside the live rack.

Device IDs stay in the run folders under output/, never in the preparation or in Git.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import farm_paths  # noqa: E402
STATE = farm_paths.rack_state(HERE)  # slots/, windows/, slot and board maps: here in a checkout, the data folder when installed
KERNEL_NAMES = {'iMouse2.Kernel.exe'}
RECEIVER_NAMES = {'uxplay.exe'}
FARM_NAMES = {'iMouse2.exe', 'ReelProbe.exe', 'TikTokProbe.exe', 'XProbe.exe'}
# The loopback ports a start has always required free: the vendor service, the desktop app's kernel,
# the rack kernel and the first farm backends.
FARM_PORTS = (9911, 9913, 9914, 9915, 9916, 9917)


def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def kernel_folder():
    """The one folder that holds the kernel's preparation, process record, logs and ledgers
    (RackState.ps1's Get-RackState 'slots')."""
    return STATE / 'slots'


def api_port(prep):
    match = re.match(r'^https?://127\.0\.0\.1:(\d+)/api/?$', prep['arguments'][0])
    if not match: raise SystemExit('The preparation does not start a loopback kernel.')
    return int(match.group(1))


def receiver_ports(prep):
    return sorted({p for r in prep['receivers'] for p in (r['port'], r['port'] + 1, r['port'] + 2)})


def _option(arguments, name):
    return arguments[arguments.index(name) + 1] if name in arguments else None


def rekernel(base_path, kernel, out_dir):
    base = load(base_path)
    source = Path(base['runDirectory']) / 'data'
    for name, digest in base['dataSha256'].items():
        if sha(source / name) != digest: raise SystemExit(f'Base {name} changed.')
    target = Path(out_dir) / 'preparation.json'
    if target.exists(): raise SystemExit(f'{target} exists; archive it first.')
    kernel = Path(kernel).resolve()
    prep = dict(base, kernel=str(kernel), kernelSha256=sha(kernel.with_suffix('.dll')), rekernelFrom=dict(kernel=base['kernel'],
                kernelSha256=base['kernelSha256'], preparation=Path(base_path).name))
    target.write_text(json.dumps(prep, indent=2), encoding='utf-8')
    return prep


def _receiver(command):
    name = re.search(r'(?:^|\s)-n\s+"?([^\s"]+)', command or '')
    port = re.search(r'(?:^|\s)-p\s+"?(\d+)', command or '')
    return (name.group(1) if name else None, int(port.group(1)) if port else None)


def conflicts(prep, snapshot, stopping=False):
    """Reasons the kernel must not start (or, with stopping, is not fully stopped). Reads only.

    The rack's kernel has the machine to itself: nothing of the farm may run when it starts, and no
    kernel or receiver may remain once it has stopped. A sandbox preparation is judged only against
    its own kernel (by port or data folder), its receivers' names and ports, and its listeners."""
    port = api_port(prep)
    names = {r['name'] for r in prep['receivers']}
    own_ports = set(receiver_ports(prep))
    sandbox = bool(prep.get('sandbox'))
    if sandbox and port in FARM_PORTS:
        raise SystemExit('A sandbox preparation needs a port no real kernel or farm service uses.')
    data_dir = (_option(prep['arguments'], '--data-dir') or '').lower()
    reasons = []
    for p in snapshot.get('processes', []):
        name, command, pid = p.get('Name') or '', p.get('CommandLine') or '', p.get('ProcessId')
        if not sandbox:
            if name in KERNEL_NAMES | RECEIVER_NAMES or (not stopping and (name in FARM_NAMES or re.search(r'python[^\r\n]*imouse_farm_server\.py', command))):
                reasons.append(f'{name} {pid} is running.')
        elif name in KERNEL_NAMES:
            if f'127.0.0.1:{port}/' in command or bool(data_dir and data_dir in command.lower()):
                reasons.append(f'The sandbox kernel {pid} is running.')
        elif name in RECEIVER_NAMES:
            receiver, receiver_port = _receiver(command)
            if receiver in names or receiver_port in own_ports:
                reasons.append(f'Sandbox receiver {receiver or pid} is running.')
    watched = {port} | own_ports | (set() if sandbox or stopping else set(FARM_PORTS))
    busy = sorted(watched & {int(x) for x in snapshot.get('listeners', [])})
    if busy: reasons.append('Listening already: ' + ', '.join(map(str, busy)) + '.')
    return reasons, sorted(watched)


def read_snapshot(raw):
    # Windows PowerShell 5.1 starts piped native stdin with a UTF-8 BOM.
    return json.loads(raw.decode('utf-8-sig', errors='replace') or '{}')


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    r = sub.add_parser('rekernel')
    r.add_argument('--base', required=True)
    r.add_argument('--kernel', required=True)
    for command in ('check-start', 'check-stopped'):
        sub.add_parser(command).add_argument('--prep', required=True)
    args = parser.parse_args()
    if args.command == 'rekernel':
        prep = rekernel(STATE / args.base, args.kernel, kernel_folder())
        print(json.dumps(dict(kernel=prep['kernel'], kernelSha256=prep['kernelSha256'], receivers=len(prep['receivers']))))
        return
    snapshot = read_snapshot(sys.stdin.buffer.read())
    reasons, ports = conflicts(load(args.prep), snapshot, stopping=args.command == 'check-stopped')
    print(json.dumps(dict(ok=not reasons, reasons=reasons, ports=ports)))
    if reasons: raise SystemExit(3)


if __name__ == '__main__':
    main()
