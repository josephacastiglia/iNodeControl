"""Clean-machine rehearsal of the Marketing Farm release, entirely inside one new temporary folder tree.

  python tools/farm_release_rehearsal.py --kernel DIR --console DIR --receiver-exe FILE --receiver-runtime DIR
         [--work DIR] [--keep]

Steps: build package A from this checkout and package B from a temporary copy with one changed farm
file; make a fake per-machine data folder with fake rack state; install A; run installed code under the
runtime guard (all farm modules imported, the farm server's offline --self-check) with the data folder
as the working directory; run the launcher (status, preflight, a blocked command's refusal); update to B;
roll back to A; check a tampered version is refused; uninstall; prove the data folder is unchanged.

Never starts the kernel, a receiver or a farm backend; the guard refuses every process start and every
connection except to the self-check's own port. Runs at below-normal priority.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import farm_install as fi  # noqa: E402
import farm_release as fr  # noqa: E402

# An archived preparation, as the rack keeps beside the current one (the sandbox step writes slots/preparation.json).
FAKE_PREPARATION = {'note': 'rehearsal fake: no real device', 'receivers': [{'board': 'FAKE', 'name': 'iMouse2-FAKE', 'port': 7110}]}


def below_normal():
    try:
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)
    except (AttributeError, OSError):
        pass


def tree_hash(root, skip=()):
    digest = hashlib.sha256()
    for p in sorted(Path(root).rglob('*')):
        rel = p.relative_to(root).as_posix()
        if p.is_file() and rel not in skip:
            digest.update(rel.encode() + b'\0' + fr.sha256(p).encode() + b'\n')
    return digest.hexdigest()


def run(cmd, cwd, timeout=300, env=None):
    started = time.monotonic()
    clean = {k: v for k, v in os.environ.items() if not k.startswith('IMOUSE_FARM_')}
    done = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=clean | (env or {}),
                          stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0))
    return {'exit': done.returncode, 'seconds': round(time.monotonic() - started, 1),
            'stdout': done.stdout[-40000:], 'stderr': done.stderr[-4000:]}


def copy_sources(dest):
    """A throwaway copy of the farm sources (tools/ and the rack scripts), with one changed file."""
    for rel in ('tools', fr.RACK_DIR):
        shutil.copytree(REPO / rel, dest / rel, ignore=shutil.ignore_patterns(
            '__pycache__', '*.pyc', 'slots', 'windows', 'windows-archive', 'identify', 'autoconnect',
            'measure', 'card-survey', 'protocol-deps', '*.png', '*.jpg', '*.bmp', '*.log', '*.jsonl',
            # tools/airplay is the receiver's source and ships; its downloaded toolchain and build output do not.
            'msys64', 'build-imouse', '*.tar.*'))
    marker = dest / 'tools' / 'mdns_goodbye.py'
    marker.write_text(marker.read_text(encoding='utf-8') + '\n# rehearsal B: this line marks the updated version\n', encoding='utf-8')
    return dest


def farm_env(root, version, data, python):
    """The variables Farm.ps1 sets for a command of this version."""
    v = Path(root) / 'versions' / version
    return {'IMOUSE_FARM_HOME': str(v / 'farm'), 'IMOUSE_FARM_DATA': str(data), 'IMOUSE_FARM_VERSION': version,
            'IMOUSE_FARM_KERNEL': str(v / 'kernel/iMouse2.Kernel.exe'), 'IMOUSE_FARM_RECEIVER': str(v / 'receiver/uxplay.exe'),
            'IMOUSE_FARM_RECEIVER_RUNTIME': str(v / 'receiver/runtime'), 'IMOUSE_FARM_PYTHON': str(python),
            'PYTHONPYCACHEPREFIX': str(Path(data) / 'cache/pycache')}


def guarded(python, guard, forbid, report, cwd, script=None, import_all=None, args=(), env=None):
    # As Farm.ps1 runs Python: -E, with bytecode caches in the data folder.
    prefix = ['-X', f"pycache_prefix={(env or {}).get('PYTHONPYCACHEPREFIX')}"] if (env or {}).get('PYTHONPYCACHEPREFIX') else ['-B']
    cmd = [python, '-E', *prefix, str(guard), '--forbid', str(forbid), '--report', str(report)]
    if import_all:
        cmd += ['--import-all', str(import_all)]
    if script:
        cmd += ['--', str(script), *args]
    outcome = run(cmd, cwd, env=env)
    outcome['report'] = json.loads(Path(report).read_text(encoding='utf-8'))
    return outcome


def powershell(script, *args, cwd, env=None, timeout=300):
    return run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script), *args], cwd,
               timeout=timeout, env=env)


# --- Sandbox rack: the installed rack scripts against an off-rack kernel (the Rack lane's offrack pattern) ---
SANDBOX_PORT = 9956                                   # not a farm port (9911-9949) and not the off-rack trial's 9936
SANDBOX_BOARDS = ('0F11', '0F12', '0F13')             # no WCH board on this PC has these IDs (checked before start)
SANDBOX_NAMES = {b: f'iMouse2-Y{i + 1}' for i, b in enumerate(SANDBOX_BOARDS)}
SANDBOX_PORTS = {b: 7950 + 10 * i for i, b in enumerate(SANDBOX_BOARDS)}


def _port_free(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5):
            return False
    except OSError:
        return True


def _sandbox_api(path):
    import urllib.request
    with urllib.request.urlopen(f'http://127.0.0.1:{SANDBOX_PORT}/api{path}', timeout=3) as r:  # the sandbox kernel only
        return json.load(r)['data']


def _wait(predicate, seconds=25):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if predicate():
                return True
        except OSError:
            pass
        time.sleep(0.5)
    return False


def sandbox_rack(root, data, scratch, env, launcher, step, checks):
    """A sandbox kernel in the data folder's one kernel folder, driven only through the installed Farm.ps1.
    Never reads or calls :9916."""
    used = [p for p in [SANDBOX_PORT] + [q for b in SANDBOX_BOARDS for q in range(SANDBOX_PORTS[b], SANDBOX_PORTS[b] + 3)] if not _port_free(p)]
    present = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                              "@(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object InstanceId -match 'VID_720A&PID_0F1[123]').Count"],
                             capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL).stdout.strip()
    if used or present != '0':
        step('sandbox rack (not run)', {'ports_in_use': used, 'sandbox_boards_present': present})
        checks['sandbox rack ran'] = False
        return
    fake = scratch / 'stand-in-receiver'
    subprocess.run(['dotnet', 'build', str(REPO / fr.RACK_DIR / 'offrack/FakeReceiver'), '-c', 'Release', '-o', str(fake), '--nologo', '-v', 'q'],
                   check=True, capture_output=True, timeout=300, stdin=subprocess.DEVNULL,
                   creationflags=getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0))
    receiver = fake / 'offrack-receiver.exe'
    runtime = scratch / 'stand-in-runtime'
    for rel in fr.RECEIVER_RUNTIME_REQUIRED:   # the files the kernel insists on, as empty stand-ins
        (runtime / rel).parent.mkdir(parents=True, exist_ok=True)
        (runtime / rel).write_bytes(b'stand-in')
    (runtime / 'bin').mkdir(exist_ok=True)
    kernel = Path(env['IMOUSE_FARM_KERNEL'])  # the INSTALLED kernel
    run_dir = data / f"output/candidate-runs/sandbox-rack-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    run_data = run_dir / 'data'
    run_data.mkdir(parents=True)
    devices = [dict(deviceid=f'sandbox-{SANDBOX_NAMES[b][8:]}', name=f'Sandbox {SANDBOX_NAMES[b][8:]}', device_name='stand-in', width=414, height=896,
                    vid='720A', pid=b, uid=b, version='', gname='Sandbox') for b in SANDBOX_BOARDS]
    receivers = [dict(DeviceId=f'sandbox-{SANDBOX_NAMES[b][8:]}', BoardPid=b, Name=SANDBOX_NAMES[b], Pipe=f'{SANDBOX_NAMES[b]}-sandbox-frames',
                      Port=SANDBOX_PORTS[b], Mac=f'02:00:5A:00:0F:{b[2:]}') for b in SANDBOX_BOARDS]
    calibration = [dict(Pid='0F11', Width=500, Height=1080, OriginX=14, OriginY=14, PixelsPerUnitX=5.12, PixelsPerUnitY=5.09)]
    for name, rows in (('devices.json', devices), ('receivers.json', receivers), ('pointer-calibration.json', calibration)):
        (run_data / name).write_text(json.dumps(rows, indent=2), encoding='utf-8')
    api = f'http://127.0.0.1:{SANDBOX_PORT}/api'
    arguments = [api + '/', '--data-dir', str(run_data), '--input-pid', '0F11', '--receivers', str(run_data / 'receivers.json'),
                 '--receiver', str(receiver), '--receiver-runtime', str(runtime), '--hold-receivers', '0F13']
    slots = data / fr.RACK_DIR / 'slots'
    prep = dict(runDirectory=str(run_dir), kernel=str(kernel), kernelSha256=fr.sha256(kernel.with_suffix('.dll')), arguments=arguments,
                api=api, held=['0F13'], boards=list(SANDBOX_BOARDS), inputEnabled=['0F11'],
                receivers=[dict(board=b, name=SANDBOX_NAMES[b], port=SANDBOX_PORTS[b]) for b in SANDBOX_BOARDS],
                dataSha256={n: fr.sha256(run_data / n) for n in ('devices.json', 'receivers.json', 'pointer-calibration.json')},
                sandboxRehearsal=True, serviceStarted=False, phoneInput=False)
    (slots / 'preparation.json').write_text(json.dumps(prep, indent=2), encoding='utf-8')

    # 1. Start through the installed Start-Multiphone, as a real preparation: while any other kernel, receiver or
    # farm process runs it must refuse and start nothing. From then on the preparation is a sandbox, which the
    # scripts check only against its own kernel, receivers and ports.
    start = powershell(launcher, 'start-rack', cwd=scratch, timeout=180)
    started_by_script = start['exit'] == 0
    step('Farm.ps1 start-rack (installed Start-Multiphone, state in the data folder)',
         {'exit': start['exit'], 'tail': (start['stdout'] + start['stderr']).strip()[-400:]})
    (slots / 'preparation.json').write_text(json.dumps(dict(prep, sandbox=True), indent=2), encoding='utf-8')
    if not started_by_script:
        checks['installed Start-Multiphone refuses while something of the farm runs, starts nothing'] = (
            'Nothing was stopped or started' in start['stdout'] + start['stderr'] and not (slots / 'processes.json').exists() and _port_free(SANDBOX_PORT))
        # Start the sandbox kernel with the script's arguments (the installed kernel, the data folder's preparation).
        # Created through WMI, outside this process tree: processes under an agent session inherit "ignore Ctrl+C",
        # and Stop-Multiphone stops a kernel only with Ctrl+C (a kernel it started from an operator's shell is fine).
        line = '"{}" {}'.format(kernel, ' '.join(f'"{x}"' for x in arguments))
        create = ("$r=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{{CommandLine='{c}';CurrentDirectory='{w}'}}; "
                  "if($r.ReturnValue){{throw \"Win32_Process.Create returned $($r.ReturnValue)\"}}; $r.ProcessId").format(
            c=line.replace("'", "''"), w=str(kernel.parent).replace("'", "''"))
        pid_file = scratch / 'sandbox-kernel-pid.txt'
        with open(pid_file, 'w', encoding='utf-8') as handle:  # a file, not a pipe: nothing may hold this process's output open
            subprocess.run(['powershell.exe', '-NoProfile', '-Command', create], stdin=subprocess.DEVNULL, stdout=handle,
                           stderr=subprocess.DEVNULL, timeout=60, check=True)
        pid = int(pid_file.read_text(encoding='utf-8-sig').strip().splitlines()[-1])
        (slots / 'processes.json').write_text(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(), kernel=dict(pid=pid, path=str(kernel)),
                                                              api=api, phoneInput=False)), encoding='utf-8')
    try:
        up = _wait(lambda: all(r['receiver_pid'] > 0 for r in _sandbox_api('/kernel/status')['receivers'] if r['name'] != SANDBOX_NAMES['0F13']))
        checks['sandbox kernel (installed build) up with stand-in receivers'] = up
        # 2. Restart one receiver through the installed Restart-Receiver.
        restart = powershell(launcher, 'restart-receiver', '-Board', '0F11', cwd=scratch, timeout=120)
        record_file = slots / 'restarts.jsonl'
        record = json.loads(record_file.read_text(encoding='utf-8-sig').strip().splitlines()[-1]) if record_file.exists() else {}
        step('Farm.ps1 restart-receiver -Board 0F11 (installed Restart-Receiver)',
             {'exit': restart['exit'], 'record': {k: record.get(k) for k in ('code', 'withdrawn', 'generation_after', 'others_changed', 'state')},
              'tail': restart['stderr'].strip()[-300:]})
        checks['installed Restart-Receiver restarts one stand-in, record in the data folder'] = (
            restart['exit'] == 0 and record.get('code') == 0 and record.get('generation_after') == 2 and record.get('others_changed') == [])
        # 3. Release the held one through the installed Release-Receiver.
        release = powershell(launcher, 'release-receiver', '-Board', '0F13', cwd=scratch, timeout=120)
        checks['installed Release-Receiver starts the held stand-in'] = release['exit'] == 0 and (slots / 'releases.jsonl').exists()
    finally:
        # 4. Stop through the installed Stop-Multiphone: graceful stop, leftover check, goodbye for the Y names.
        stop = powershell(launcher, 'stop-rack', cwd=scratch, timeout=180)
        step('Farm.ps1 stop-rack (installed Stop-Multiphone)', {'exit': stop['exit'], 'tail': (stop['stdout'] + stop['stderr']).strip()[-300:]})
        checks['installed Stop-Multiphone stops the sandbox kernel'] = stop['exit'] == 0 and 'Stopped:' in stop['stdout']
        if stop['exit'] != 0:  # last resort: only this sandbox's kernel (its port is in its command line) and stand-ins
            subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                            f"Get-CimInstance Win32_Process | Where-Object {{ ($_.Name -eq 'iMouse2.Kernel.exe' -and $_.CommandLine -match '127\\.0\\.0\\.1:{SANDBOX_PORT}/') "
                            f"-or ($_.Name -eq 'offrack-receiver.exe' -and $_.ExecutablePath -like '{fake}*') }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        left = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                               f"@(Get-CimInstance Win32_Process | Where-Object {{ $_.ExecutablePath -like '{fake}*' -or ($_.Name -eq 'iMouse2.Kernel.exe' -and $_.CommandLine -match ':{SANDBOX_PORT}/') }}).Count"],
                              capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL).stdout.strip()
        checks['nothing of the sandbox remains'] = left == '0' and _port_free(SANDBOX_PORT) and all(_port_free(p) for p in SANDBOX_PORTS.values())
    stopped = sorted(p.name for p in slots.glob('processes-stopped-*.json'))
    issues = fr.verify(Path(root) / 'versions' / env['IMOUSE_FARM_VERSION'])  # strict: any file written into the install shows
    step('sandbox rack state', {'data_slots': sorted(p.name for p in slots.iterdir()), 'install_issues': issues[:20]})
    checks['rack state written only in the data folder'] = bool(stopped) and not issues


def rehearse(kernel, console, receiver_exe, receiver_runtime, work, sandbox=False, package_zip=None):
    below_normal()
    work = Path(work)
    pc = work / 'clean-pc'
    packages, root, data, scratch = pc / 'packages', pc / 'LocalAppData/Programs/iMouseFarm', pc / 'LocalAppData/iMouseFarm', pc / 'scratch'
    for p in (packages, scratch):
        p.mkdir(parents=True)
    steps, checks = [], {}

    def step(name, value):
        steps.append({'step': name, 'utc': datetime.now(timezone.utc).isoformat(), **value})
        return value

    tokens, accounts = fr.privacy_tokens(), fr.account_labels()
    if package_zip:  # A = the real release zip, extracted as an operator would; never the tree
        import zipfile
        with zipfile.ZipFile(package_zip) as z:
            bad = z.testzip()
            if bad:
                raise SystemExit(f'zip CRC failed: {bad}')
            for name in z.namelist():
                fr.safe_name(name)
            z.extractall(packages / 'farm-A')
        a = fr.load_json(packages / 'farm-A' / 'release.json')
        checks['release zip extracts and verifies'] = not fr.verify(packages / 'farm-A')
        checks['release zip names no account handle'] = not a.get('account_labels_in')
    else:
        a = fr.build(REPO, packages / 'farm-A', kernel, console, receiver_exe, receiver_runtime, version='rehearsal-a',
                     tokens=tokens or (), accounts=accounts)
    va = a['version']
    b_src = copy_sources(work / 'source-copy-B')
    b = fr.build(b_src, packages / 'farm-B', kernel, console, receiver_exe, receiver_runtime, version='rehearsal-b',
                 tokens=tokens or (), accounts=accounts)
    step('build', {'A': {'files': len(a['files']), 'bytes': sum(r['bytes'] for r in a['files'].values())},
                   'B': {'files': len(b['files'])}, 'privacy_lists_used': tokens is not None,
                   'dev_path_blockers': a['dev_path_findings'], 'ready': [c for c, s in a['commands'].items() if s['ready']],
                   'blocked': [c for c, s in a['commands'].items() if not s['ready']]})
    shutil.rmtree(b_src)
    checks['packages verify'] = not fr.verify(packages / 'farm-A') and not fr.verify(packages / 'farm-B')

    # Fake per-machine data folder, with fake rack state the release must never carry or touch.
    fi.init_data(data)
    (data / f'{fr.RACK_DIR}/slots/preparation-earlier.json').write_text(json.dumps(FAKE_PREPARATION), encoding='utf-8')
    (data / f'{fr.RACK_DIR}/phone-slots.json').write_text('{"slots": {"1": {"board": "FAKE"}}}', encoding='utf-8')
    (data / 'evidence-archive/privacy/withheld-candidates.txt').write_text('# fake\n', encoding='utf-8')
    data_before = {p.relative_to(data).as_posix(): fr.sha256(p) for p in data.rglob('*') if p.is_file() and p.name != 'data.json'}

    step('install A', fi.install(packages / 'farm-A', root, data, python=sys.executable))
    version_a = root / 'versions' / va
    guard = scratch / 'runtime_guard.py'
    shutil.copyfile(HERE / 'release/runtime_guard.py', guard)
    dev = REPO.parent.parent if REPO.parent.name.endswith('.worktrees') else REPO.parent  # ...\Desktop\Claude Code

    env_a = farm_env(root, va, data, sys.executable)  # what Farm.ps1 sets for a command of version A
    imports = guarded(sys.executable, guard, dev, scratch / 'imports-A.json', cwd=data, import_all=version_a / 'farm/tools', env=env_a)
    step('import every installed farm module (guarded)', {k: imports[k] for k in ('exit', 'seconds')} | {
        k: imports['report'].get(k) for k in ('imported', 'import_errors', 'forbidden_opened', 'forbidden_modules', 'forbidden_sys_path', 'refused', 'opened_count')})
    selfcheck = guarded(sys.executable, guard, dev, scratch / 'selfcheck-A.json', cwd=data,
                        script=version_a / 'farm/tools/imouse_farm_server.py', args=['--self-check'], env=env_a)
    step('farm server --self-check from the install (guarded)', {k: selfcheck[k] for k in ('exit', 'seconds')} | {
        'stdout_tail': selfcheck['stdout'][-300:], 'stderr_tail': selfcheck['stderr'][-600:]} | {
        k: selfcheck['report'].get(k) for k in ('exit', 'error', 'forbidden_opened', 'forbidden_modules', 'forbidden_sys_path', 'refused', 'opened_count')})
    paths = guarded(sys.executable, guard, dev, scratch / 'paths-A.json', cwd=data,
                    script=_paths_probe(scratch, version_a / 'farm/tools'), env=env_a)
    step('farm_paths as installed (guarded)', {'stdout': paths['stdout'].strip()[-800:], 'exit': paths['exit']})
    seen = dict(line.split(' ', 1) for line in paths['stdout'].strip().splitlines() if ' ' in line)
    checks['installed farm_paths point at the data folder'] = (
        Path(seen.get('MAIN', '')) == data.resolve() and Path(seen.get('ARCHIVE', '')) == data.resolve() / 'evidence-archive'
        and Path(seen.get('RACK', '')) == data.resolve() / fr.RACK_DIR / 'slots')
    checks['dev folder not read (imports)'] = not any(imports['report'][k] for k in ('forbidden_opened', 'forbidden_modules', 'forbidden_sys_path'))
    checks['dev folder not read (self-check)'] = not any(selfcheck['report'][k] for k in ('forbidden_opened', 'forbidden_modules', 'forbidden_sys_path'))
    checks['self-check passed'] = selfcheck['report'].get('exit') == 0 and 'OK' in selfcheck['stdout']
    checks['guard refused nothing'] = not selfcheck['report']['refused'] and not imports['report']['refused']

    launcher = root / 'Farm.ps1'
    status = powershell(launcher, 'status', cwd=scratch)
    step('Farm.ps1 status', {'exit': status['exit'], 'stdout': status['stdout'].strip()[-1200:]})
    preflight = powershell(launcher, 'preflight', '-Json', cwd=scratch)
    try:
        pf = json.loads(preflight['stdout'][preflight['stdout'].index('{'):])
        step('Farm.ps1 preflight (read-only)', {'exit': preflight['exit'], 'seconds': preflight['seconds'],
                                               'not_ok': [(c['id'], c['status']) for c in pf['checks'] if c['status'] != 'ok']})
    except (json.JSONDecodeError, ValueError):
        step('Farm.ps1 preflight (read-only)', {'exit': preflight['exit'], 'stdout': preflight['stdout'][-800:], 'stderr': preflight['stderr'][-400:]})
    checks['every launcher command ready (0 dev-path blockers)'] = all(s['ready'] for s in a['commands'].values())
    if sandbox:
        sandbox_rack(root, data, scratch, env_a, launcher, step, checks)

    step('update to B', fi.update(packages / 'farm-B', root))
    checks['update switched'] = fi.status(root)['version'] == 'rehearsal-b' and fi.status(root)['previous'] == va
    checks['B has its change'] = 'rehearsal B' in (root / 'versions/rehearsal-b/farm/tools/mdns_goodbye.py').read_text(encoding='utf-8')
    imports_b = guarded(sys.executable, guard, dev, scratch / 'imports-B.json', cwd=data, import_all=root / 'versions/rehearsal-b/farm/tools',
                        env=farm_env(root, 'rehearsal-b', data, sys.executable))
    checks['dev folder not read (B imports)'] = not any(imports_b['report'][k] for k in ('forbidden_opened', 'forbidden_modules', 'forbidden_sys_path'))
    status_b = powershell(launcher, 'status', cwd=scratch)
    checks['launcher follows the switch'] = 'rehearsal-b' in status_b['stdout']

    (version_a / 'console/startup-state.json').write_text('{"written by": "the console beside itself"}', encoding='utf-8')
    step('roll back to A', fi.rollback(root))
    checks['rollback switched'] = fi.status(root)['version'] == va and fi.status(root)['previous'] == 'rehearsal-b'
    checks['launcher follows the rollback'] = va in powershell(launcher, 'status', cwd=scratch)['stdout']

    tampered = root / 'versions/rehearsal-b/farm/tools/farm_jobs.py'
    tampered.write_bytes(tampered.read_bytes() + b'\n# tampered\n')
    try:
        fi.rollback(root)
        checks['tampered version refused'] = False
    except fi.Refused as error:
        step('roll back to a tampered B (must refuse)', {'refused': str(error)[:200]})
        checks['tampered version refused'] = fi.status(root)['version'] == va

    state = fi.read_json(data / 'data.json')
    step('uninstall', fi.uninstall(root))
    checks['install root removed'] = not root.exists()
    checks['data folder kept; its earlier files unchanged'] = (
        all((data / n).is_file() and fr.sha256(data / n) == h for n, h in data_before.items()) and state['last_version'] == va)
    checks['package carries no private state'] = not [n for n in a['files'] if fr.is_private(n) and not n.startswith(fr.THIRD_PARTY)]
    return {'utc': datetime.now(timezone.utc).isoformat(), 'source': a['source'], 'passed': all(checks.values()),
            'checks': checks, 'steps': steps}


def _paths_probe(scratch, tools):
    probe = Path(scratch) / 'paths_probe.py'
    probe.write_text(
        'import sys\nsys.path.insert(0, %r)\nimport farm_paths as p\n'
        'print("MAIN", p.MAIN)\nprint("ARCHIVE", p.ARCHIVE)\nprint("RACK", p.RACK)\n' % str(tools), encoding='utf-8')
    return probe


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for key in ('kernel', 'console', 'receiver-exe', 'receiver-runtime'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--work', type=Path, help='a new folder (default: a new temporary folder)')
    parser.add_argument('--report', type=Path, help='write the JSON report here (default: output/release-rehearsal-<utc>.json)')
    parser.add_argument('--keep', action='store_true', help='keep the temporary tree for inspection')
    parser.add_argument('--package-zip', type=Path, help='install version A from this release zip instead of building it from the tree')
    parser.add_argument('--sandbox-rack', action='store_true', help='also drive an off-rack kernel (port 9956, stand-in receivers) with the installed rack scripts')
    args = parser.parse_args(argv)
    work = Path(args.work) if args.work else Path(tempfile.mkdtemp(prefix='farm-clean-pc-'))
    if args.work:
        work.mkdir(parents=True, exist_ok=False)
    try:
        result = rehearse(args.kernel, args.console, args.receiver_exe, args.receiver_runtime, work, args.sandbox_rack, args.package_zip)
    finally:
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
    report = args.report or REPO / 'output' / f"release-rehearsal-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=1), encoding='utf-8')
    for name, ok in result['checks'].items():
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"Rehearsal {'passed' if result['passed'] else 'FAILED'}; report {report}")
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
