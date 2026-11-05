"""A kernel per rack: rack A and rack B each on their own kernel and port, so stopping one rack
never drops the other. The single kernel for both racks (Stage 'slots') keeps working unchanged.

  python rack_kernels.py prepare --base slots/preparation.json --kernel <iMouse2.Kernel.exe>
                                 [--port-a 9916] [--port-b 9926]
      Offline; starts nothing. Splits a combined racks A+B preparation into rack-a/preparation.json
      and rack-b/preparation.json. Rack B is the boards in rack-b-boards.json; rack A is every other
      board. phone-slots.json boards must land on A and rack-b-slots.json boards on B. Each rack gets
      its own run folder under output/candidate-runs/ (devices, receivers and calibration filtered to
      its boards, never mixed), its own port and '--rack A|B' label. Rack A keeps 9916, so every farm
      tool that talks to 9916 keeps reaching rack A's phones. Refuses to overwrite.
  python rack_kernels.py rekernel --base slots/preparation-<archived>.json --kernel <exe> [--out slots]
      Offline. The same preparation (same run folder, data and arguments) on another kernel build:
      only kernel and kernelSha256 change. Moves the single kernel to a new build, and back.
  python rack_kernels.py check-start --prep <preparation.json> [--rack A|B]    < snapshot.json
  python rack_kernels.py check-stopped --prep <preparation.json> [--rack A|B]  < snapshot.json
      The snapshot is {"processes": [{Name, ProcessId, CommandLine}], "listeners": [port, ...]} from
      Start-/Stop-Multiphone.ps1. Prints {"ok", "reasons", "ports"}; exit 3 when not ok. With a rack,
      only what belongs to that rack (its kernel, its receivers' names and ports, its listeners) or
      the single kernel counts; the other rack's kernel and receivers are left alone.

Device IDs stay in the run folders under output/, never in the preparation or in Git.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import farm_paths  # noqa: E402
STATE = farm_paths.rack_state(HERE)  # rack-a/, rack-b/, slot and board maps: here in a checkout, the data folder when installed
RUNS = farm_paths.run_root(ROOT)    # output/candidate-runs/...
DATA_FILES = ('devices.json', 'receivers.json', 'pointer-calibration.json')
KERNEL_NAMES = {'iMouse2.Kernel.exe'}
RECEIVER_NAMES = {'uxplay.exe'}
FARM_NAMES = {'iMouse2.exe', 'ReelProbe.exe', 'TikTokProbe.exe', 'XProbe.exe'}
SINGLE_PORTS = (9911, 9913, 9914, 9915, 9916, 9917)   # Start-Multiphone.ps1's list before racks.
FARM_PORTS = (9911, 9913, 9914, 9915)                  # Console and farm backends: rack A's concern.
DEFAULT_PORTS = {'A': 9916, 'B': 9926}


def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def rack_dir(rack): return STATE / f'rack-{rack.lower()}'


def api_port(prep):
    match = re.match(r'^https?://127\.0\.0\.1:(\d+)/api/?$', prep['arguments'][0])
    if not match: raise SystemExit('The preparation does not start a loopback kernel.')
    return int(match.group(1))


def receiver_ports(prep):
    return sorted({p for r in prep['receivers'] for p in (r['port'], r['port'] + 1, r['port'] + 2)})


def _option(arguments, name):
    return arguments[arguments.index(name) + 1] if name in arguments else None


def split(base_path, kernel, rack_b_boards, slots_a, slots_b, ports=None, root=RUNS, now=None):
    """The two rack preparations and their data rows: {rack: (preparation, {file: rows})}. Writes nothing."""
    ports = dict(DEFAULT_PORTS, **(ports or {}))
    if ports['A'] == ports['B']: raise SystemExit('The two racks need different kernel ports.')
    base = load(base_path)
    source = Path(base['runDirectory']) / 'data'
    for name, digest in base['dataSha256'].items():
        if sha(source / name) != digest: raise SystemExit(f'Base {name} changed.')
    if _option(base['arguments'], '--rack'): raise SystemExit('The base is already one rack; split a combined preparation.')
    rows = {name: load(source / name) for name in DATA_FILES}
    keys = {'devices.json': 'pid', 'receivers.json': 'BoardPid', 'pointer-calibration.json': 'Pid'}
    boards = [d['pid'].upper() for d in rows['devices.json']]
    rack_b = {b.upper() for b in rack_b_boards}
    if len(rack_b) != len(rack_b_boards): raise SystemExit('Rack B boards repeat.')
    if not rack_b <= set(boards): raise SystemExit('A rack B board is not in the base preparation: ' + ', '.join(sorted(rack_b - set(boards))))
    racks = {'A': [b for b in boards if b not in rack_b], 'B': [b for b in boards if b in rack_b]}
    for rack, named in (('A', slots_a), ('B', slots_b)):
        stray = {b.upper() for b in named} - set(racks[rack])
        if stray: raise SystemExit(f'Slot boards not on rack {rack}: ' + ', '.join(sorted(stray)))
    for name, key in keys.items():
        for board in boards:
            if sum(1 for r in rows[name] if r[key].upper() == board) != 1: raise SystemExit(f'{board}: {name} row missing or repeated.')
    all_ports = set(receiver_ports(base))
    if set(ports.values()) & all_ports: raise SystemExit('A kernel port collides with a receiver port.')
    kernel = Path(kernel).resolve()
    kernel_sha = sha(kernel.with_suffix('.dll'))
    stamp = (now or datetime.now(timezone.utc)).strftime('%Y%m%dT%H%M%SZ')
    out = {}
    for rack, members in racks.items():
        if not members: raise SystemExit(f'Rack {rack} has no boards.')
        mine = set(members)
        run = Path(root) / f'output/candidate-runs/multiphone-rack-{rack.lower()}-{stamp}'
        data = run / 'data'
        rack_rows = {name: [r for r in rows[name] if r[keys[name]].upper() in mine] for name in DATA_FILES}
        arguments, previous = [], None
        for a in base['arguments']:
            if previous is None and a.startswith('http'): a = f'http://127.0.0.1:{ports[rack]}/api/'
            elif previous == '--data-dir': a = str(data)
            elif previous == '--receivers': a = str(data / 'receivers.json')
            elif previous in ('--input-pid', '--hold-receivers'):
                a = ','.join(b for b in a.split(',') if b.upper() in mine)
                if not a: raise SystemExit(f'Rack {rack}: {previous} would be empty.')
            arguments.append(a); previous = a
        arguments += ['--rack', rack]
        if str(source) in ' '.join(arguments): raise SystemExit('Kernel arguments were not rewritten.')
        prep = dict(base, runDirectory=str(run), kernel=str(kernel), kernelSha256=kernel_sha, arguments=arguments,
                    rack=rack, api=f'http://127.0.0.1:{ports[rack]}/api', otherRack=dict(rack='B' if rack == 'A' else 'A',
                    port=ports['B' if rack == 'A' else 'A']),
                    boards=members, inputEnabled=[b for b in (_option(arguments, '--input-pid') or '').split(',') if b],
                    held=[b for b in (_option(arguments, '--hold-receivers') or '').split(',') if b],
                    receivers=[dict(board=r['BoardPid'], name=r['Name'], port=r['Port']) for r in rack_rows['receivers.json']],
                    slots={b: s for b, s in (base.get('slots') or {}).items() if b.upper() in mine},
                    rackB=sorted(mine) if rack == 'B' else [],
                    derivedFrom=str(Path(base_path).resolve().relative_to(STATE)).replace('\\', '/') if Path(base_path).resolve().is_relative_to(STATE) else str(base_path),
                    serviceStarted=False, phoneInput=False)
        out[rack] = (prep, rack_rows)
    return out


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


def write(split_result, out_dirs=None):
    out_dirs = out_dirs or {r: rack_dir(r) for r in split_result}
    for rack, (prep, _) in split_result.items():
        if (out_dirs[rack] / 'preparation.json').exists(): raise SystemExit(f'rack-{rack.lower()}/preparation.json exists; archive it first.')
        if Path(prep['runDirectory']).exists(): raise SystemExit('The rack run folder exists; never overwrite it.')
    for rack, (prep, rack_rows) in split_result.items():
        data = Path(prep['runDirectory']) / 'data'; data.mkdir(parents=True)
        for name, rows in rack_rows.items(): (data / name).write_text(json.dumps(rows, indent=2), encoding='utf-8')
        prep['dataSha256'] = {n: sha(data / n) for n in DATA_FILES}
        out_dirs[rack].mkdir(exist_ok=True)
        (out_dirs[rack] / 'preparation.json').write_text(json.dumps(prep, indent=2), encoding='utf-8')


def _receiver(command):
    name = re.search(r'(?:^|\s)-n\s+"?([^\s"]+)', command or '')
    port = re.search(r'(?:^|\s)-p\s+"?(\d+)', command or '')
    return (name.group(1) if name else None, int(port.group(1)) if port else None)


def _kernel_rack(command):
    match = re.search(r'"?--rack"?\s+"?([A-Za-z0-9]+)', command or '')
    return match.group(1).upper() if match else None


def conflicts(prep, snapshot, rack=None, stopping=False):
    """Reasons this rack's kernel must not start (or, with stopping, is not fully stopped). Reads only."""
    if rack and prep.get('rack', '').upper() != rack.upper(): raise SystemExit(f'This preparation is not rack {rack}.')
    if not rack and prep.get('rack'): raise SystemExit('A rack preparation needs -Rack.')
    port = api_port(prep)
    names = {r['name'] for r in prep['receivers']}
    own_ports = set(receiver_ports(prep))
    # An off-rack sandbox (offrack_trial.py) runs beside the live single kernel, so that one rule is
    # waived for it; it must sit on a port no real kernel or farm service uses.
    sandbox = bool(prep.get('sandbox'))
    if sandbox and (port in set(SINGLE_PORTS) | set(DEFAULT_PORTS.values()) or not rack):
        raise SystemExit('A sandbox preparation needs a rack label and a port no real kernel uses.')
    data_dir = (_option(prep['arguments'], '--data-dir') or '').lower()
    reasons = []
    for p in snapshot.get('processes', []):
        name, command, pid = p.get('Name') or '', p.get('CommandLine') or '', p.get('ProcessId')
        if not rack:
            # The single kernel serves both racks: nothing of either may be running (the old rule).
            if name in KERNEL_NAMES | RECEIVER_NAMES or (not stopping and (name in FARM_NAMES or re.search(r'python[^\r\n]*imouse_farm_server\.py', command))):
                reasons.append(f'{name} {pid} is running.')
            continue
        if name in KERNEL_NAMES:
            other = _kernel_rack(command)
            mine = f'127.0.0.1:{port}/' in command or bool(data_dir and data_dir in command.lower())
            if other is None and not stopping and not sandbox: reasons.append(f'The single kernel ({pid}) is running; it already serves both racks.')
            elif other == rack.upper() or mine:
                reasons.append(f'Rack {rack.upper()} kernel {pid} is running.')
        elif name in RECEIVER_NAMES:
            receiver, receiver_port = _receiver(command)
            if receiver in names or receiver_port in own_ports:
                reasons.append(f'Receiver {receiver or pid} of rack {rack.upper()} is running.')
        elif not stopping and rack.upper() == 'A' and (name in FARM_NAMES or re.search(r'python[^\r\n]*imouse_farm_server\.py', command)):
            reasons.append(f'{name} {pid} is running against rack A.')
    watched = (set(SINGLE_PORTS) if not rack else {port} | (set(FARM_PORTS) if rack.upper() == 'A' and not stopping else set())) | own_ports
    if stopping and not rack: watched = {port} | own_ports
    busy = sorted(watched & {int(x) for x in snapshot.get('listeners', [])})
    if busy: reasons.append('Listening already: ' + ', '.join(map(str, busy)) + '.')
    return reasons, sorted(watched)


def read_snapshot(raw):
    # Windows PowerShell 5.1 starts piped native stdin with a UTF-8 BOM.
    return json.loads(raw.decode('utf-8-sig', errors='replace') or '{}')


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--base', required=True)
    p.add_argument('--kernel', required=True)
    p.add_argument('--port-a', type=int, default=DEFAULT_PORTS['A'])
    p.add_argument('--port-b', type=int, default=DEFAULT_PORTS['B'])
    r = sub.add_parser('rekernel')
    r.add_argument('--base', required=True)
    r.add_argument('--kernel', required=True)
    r.add_argument('--out', default='slots')
    for command in ('check-start', 'check-stopped'):
        c = sub.add_parser(command)
        c.add_argument('--prep', required=True)
        c.add_argument('--rack', choices=['A', 'B', 'a', 'b'])
    args = parser.parse_args()
    if args.command == 'prepare':
        rack_b = [b['board'] for b in load(STATE / 'rack-b-boards.json')['boards']]
        slots_a = [v['board'] for v in load(STATE / 'phone-slots.json')['slots'].values()]
        slots_b = [v['board'] for v in load(STATE / 'rack-b-slots.json')['slots'].values()]
        result = split(STATE / args.base, args.kernel, rack_b, slots_a, slots_b, dict(A=args.port_a, B=args.port_b))
        write(result)
        print(json.dumps({r: dict(port=api_port(p), boards=len(p['boards']), run=str(Path(p['runDirectory']).relative_to(RUNS)))
                          for r, (p, _) in result.items()}))
        return
    if args.command == 'rekernel':
        prep = rekernel(STATE / args.base, args.kernel, STATE / args.out)
        print(json.dumps(dict(kernel=prep['kernel'], kernelSha256=prep['kernelSha256'], receivers=len(prep['receivers']))))
        return
    snapshot = read_snapshot(sys.stdin.buffer.read())
    reasons, ports = conflicts(load(args.prep), snapshot, args.rack, stopping=args.command == 'check-stopped')
    print(json.dumps(dict(ok=not reasons, reasons=reasons, ports=ports)))
    if reasons: raise SystemExit(3)


if __name__ == '__main__':
    main()
