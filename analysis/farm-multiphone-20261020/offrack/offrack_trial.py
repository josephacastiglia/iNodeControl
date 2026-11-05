"""Off-rack trial of per-receiver restart and the per-rack scripts, safe to run while the live rack runs.

A second kernel ('rack B' label) on 127.0.0.1:9936 with three stand-in receivers (offrack-receiver.exe:
no AirPlay, no mDNS advertisement; it holds its port and feeds BMP frames to the kernel's pipe), test
names iMouse2-Z1..Z3, ports 7900-7922, and board IDs that no WCH board on this PC has, so no input
board is ever opened. The real scripts run from a sandbox copy (output/offrack-rack-<time>/sandbox/),
so they only ever see this trial's preparation and process record.

Before starting it refuses if any trial port is in use, a trial name is on the live kernel, or a trial
board ID is present. The live kernel (:9916) is only read (GET /kernel/status) before and after, to
prove its receivers were untouched. The only network traffic is the AirPlay goodbye for the Z names
(which no phone ever listed) when they are withdrawn and when the trial kernel stops.

  python offrack/offrack_trial.py --kernel <candidate iMouse2.Kernel.exe>
"""
import argparse
import hashlib
import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RACK = HERE.parent                    # analysis/farm-multiphone-20261020
ROOT = RACK.parents[1]
PORT = 9936
LIVE = 'http://127.0.0.1:9916/api/kernel/status'
API = f'http://127.0.0.1:{PORT}/api'
BOARDS = ('0F01', '0F02', '0F03')
NAMES = {b: f'iMouse2-Z{i + 1}' for i, b in enumerate(BOARDS)}
RECEIVER_PORTS = {b: 7900 + 10 * i for i, b in enumerate(BOARDS)}
RUNTIME_FILES = ('libexec/gstreamer-1.0/gst-plugin-scanner.exe',) + tuple(f'lib/gstreamer-1.0/libgst{n}.dll' for n in (
    'app', 'coreelements', 'libav', 'videoparsersbad', 'videoconvertscale', 'playback', 'autodetect', 'audioconvert',
    'audioresample', 'volume', 'level'))
results = []


def check(ok, label):
    results.append(dict(ok=bool(ok), check=label))
    print(('PASS ' if ok else 'FAIL ') + label, flush=True)
    return ok


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def get(url, timeout=3):
    with urllib.request.urlopen(url, timeout=timeout) as r: return json.load(r)['data']


def post(body, timeout=30):
    req = urllib.request.Request(API + '/', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r: return json.load(r)['data']


def rows():
    return {r['name']: r for r in get(API + '/kernel/status')['receivers']}


def live_snapshot():
    # PIDs and crash-restart counts only: mirror state changes with the lanes' phone work, not with this trial.
    try: return {r['name']: (r['receiver_pid'], r['receiver_restarts']) for r in get(LIVE)['receivers']}
    except OSError: return None


def port_free(port):
    """No listener answers on the port (real receivers listen on every interface, the stand-in on loopback)."""
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5): return False
    except OSError: return True


def ps(script, *args):
    """Runs a sandbox copy of a rack script; returns (exit code, output)."""
    # Output to a file, not a pipe: a kernel Start-Multiphone launches would inherit and hold a pipe open.
    log = Path(script).parent / 'script-output.txt'
    with open(log, 'w', encoding='utf-8') as out:
        run = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script), *args],
                             stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, timeout=180)
    return run.returncode, log.read_text(encoding='utf-8', errors='replace').strip()


def wait(predicate, seconds=20):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if predicate(): return True
        except OSError: pass
        time.sleep(0.3)
    return False


def last_record(path): return json.loads(Path(path).read_text(encoding='utf-8-sig').strip().splitlines()[-1])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kernel', required=True)
    kernel = Path(parser.parse_args().kernel).resolve()

    # --- Safety: nothing this trial uses may belong to the live rack. ---
    used = [p for p in [PORT] + [q for b in BOARDS for q in range(RECEIVER_PORTS[b], RECEIVER_PORTS[b] + 3)] if not port_free(p)]
    if used: raise SystemExit(f'Trial ports in use: {used}; nothing started.')
    before = live_snapshot()
    if before and set(NAMES.values()) & set(before): raise SystemExit('A trial name is on the live kernel; nothing started.')
    present = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                              "@(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object InstanceId -match 'VID_720A&PID_0F0[123]').Count"],
                             capture_output=True, text=True, timeout=60).stdout.strip()
    if present != '0': raise SystemExit(f'A trial board ID is present on USB ({present}); nothing started.')
    print(json.dumps(dict(live_kernel_receivers=len(before) if before else 'not answering', trial_ports_free=True)), flush=True)

    run = ROOT / f"output/offrack-rack-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    fake = run / 'fake'
    subprocess.run(['dotnet', 'build', str(HERE / 'FakeReceiver'), '-c', 'Release', '-o', str(fake), '--nologo', '-v', 'q'],
                   check=True, capture_output=True, timeout=300)
    receiver_exe = fake / 'offrack-receiver.exe'
    runtime = run / 'runtime'
    for rel in RUNTIME_FILES:
        (runtime / rel).parent.mkdir(parents=True, exist_ok=True); (runtime / rel).write_bytes(b'stand-in')
    (runtime / 'bin').mkdir(exist_ok=True)
    data = run / 'data'; data.mkdir(parents=True)
    devices = [dict(deviceid=f'offrack-{NAMES[b][8:]}', name=f'Trial {NAMES[b][8:]}', device_name='stand-in', width=414, height=896,
                    vid='720A', pid=b, uid=b, version='', gname='Off-rack') for b in BOARDS]
    receivers = [dict(DeviceId=f'offrack-{NAMES[b][8:]}', BoardPid=b, Name=NAMES[b], Pipe=f'{NAMES[b]}-offrack-frames',
                      Port=RECEIVER_PORTS[b], Mac=f'02:00:5A:00:0F:{b[2:]}') for b in BOARDS]
    calibration = [dict(Pid='0F01', Width=500, Height=1080, OriginX=14, OriginY=14, PixelsPerUnitX=5.12, PixelsPerUnitY=5.09)]
    for name, content in (('devices.json', devices), ('receivers.json', receivers), ('pointer-calibration.json', calibration)):
        (data / name).write_text(json.dumps(content, indent=2), encoding='utf-8')

    # Sandbox: the real scripts, at the same relative layout, seeing only this trial's preparation.
    box = run / 'sandbox' / 'analysis' / 'rack'
    box.mkdir(parents=True)
    for script in ('Start-Multiphone.ps1', 'Stop-Multiphone.ps1', 'Release-Receiver.ps1', 'Restart-Receiver.ps1', 'rack_kernels.py'):
        shutil.copy2(RACK / script, box / script)
    (run / 'sandbox/tools/kernel-window').mkdir(parents=True)
    shutil.copy2(ROOT / 'tools/mdns_goodbye.py', run / 'sandbox/tools/mdns_goodbye.py')
    shutil.copy2(ROOT / 'tools/kernel-window/Stop-ConsoleProcessGracefully.ps1', run / 'sandbox/tools/kernel-window/')
    rack_b = box / 'rack-b'; rack_b.mkdir()
    arguments = [f'http://127.0.0.1:{PORT}/api/', '--data-dir', str(data), '--input-pid', '0F01', '--receivers', str(data / 'receivers.json'),
                 '--receiver', str(receiver_exe), '--receiver-runtime', str(runtime), '--hold-receivers', '0F03', '--rack', 'B']
    prep = dict(runDirectory=str(run), kernel=str(kernel), kernelSha256=sha(kernel.with_suffix('.dll')), arguments=arguments, rack='B',
                api=API, held=['0F03'], boards=list(BOARDS), inputEnabled=['0F01'],
                receivers=[dict(board=b, name=NAMES[b], port=RECEIVER_PORTS[b]) for b in BOARDS],
                dataSha256={n: sha(data / n) for n in ('devices.json', 'receivers.json', 'pointer-calibration.json')},
                offrackTrial=True, serviceStarted=False, phoneInput=False)
    (rack_b / 'preparation.json').write_text(json.dumps(prep, indent=2), encoding='utf-8')

    # --- Start through the real script. Beside the live single kernel it must refuse and start nothing. ---
    code, out = ps(box / 'Start-Multiphone.ps1', '-Rack', 'B')
    single_running = before is not None
    if single_running:
        check(code != 0 and 'single kernel' in out and not (rack_b / 'processes.json').exists() and port_free(PORT),
              'Start-Multiphone -Rack B refuses beside the running single kernel and starts nothing')
        # Start the trial kernel exactly as the script would, then write its process record.
        # The kernel inherits its launcher's handles, so the launcher's output goes to a file, not a pipe.
        pid_file = rack_b / 'trial-kernel-pid.txt'
        launch = ('$p=Start-Process -FilePath "{k}" -ArgumentList \'{a}\' -WorkingDirectory "{w}" -WindowStyle Hidden -PassThru '
                  '-RedirectStandardOutput "{o}" -RedirectStandardError "{e}"; Set-Content -LiteralPath "{f}" -Value $p.Id').format(
            k=kernel, a=' '.join(f'"{x}"' for x in arguments), w=kernel.parent, o=rack_b / 'kernel.stdout.txt', e=rack_b / 'kernel.stderr.txt', f=pid_file)
        subprocess.run(['powershell.exe', '-NoProfile', '-Command', launch], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=60, check=True)
        pid = int(pid_file.read_text(encoding='utf-8-sig').strip())
        (rack_b / 'processes.json').write_text(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(), kernel=dict(pid=pid, path=str(kernel)),
                                                                rack='B', api=API, phoneInput=False)), encoding='utf-8')
    else:
        check(code == 0, 'Start-Multiphone -Rack B starts the trial kernel (no live kernel running): ' + out[-200:])
    try:
        check(wait(lambda: rows()['iMouse2-Z1']['receiver_pid'] > 0 and rows()['iMouse2-Z2']['receiver_pid'] > 0
                   and rows()['iMouse2-Z1']['live'] and rows()['iMouse2-Z2']['live']),
              'Trial kernel up: Z1 and Z2 running with live frames')
        status = get(API + '/kernel/status')
        check(status['rack'] == 'B' and rows()['iMouse2-Z3']['receiver_state'] == 'held', 'Status reports rack B, and Z3 held')
        start = rows()

        # --- Restart one receiver through Restart-Receiver.ps1. ---
        z2_frames = start['iMouse2-Z2']['frames']
        code, out = ps(box / 'Restart-Receiver.ps1', '-Rack', 'B', '-Board', '0F01')
        rec = last_record(rack_b / 'restarts.jsonl')
        check(code == 0 and rec['code'] == 0 and rec['withdrawn'] and rec['generation_after'] == 2
              and rec['pid_after'] > 0 and rec['pid_after'] != rec['pid_before'] and rec['others_changed'] == [],
              'Restart-Receiver restarts Z1 alone: new child, generation 2, goodbye sent, others unchanged')
        check(wait(lambda: rows()['iMouse2-Z1']['live']), 'Z1 frames come back after its restart')
        now = rows()
        check(now['iMouse2-Z2']['receiver_pid'] == start['iMouse2-Z2']['receiver_pid'] and now['iMouse2-Z2']['frames'] > z2_frames
              and now['iMouse2-Z2']['live'], "Z2's child and frames ran on through Z1's restart")

        # --- Withdraw, then release again. ---
        code, out = ps(box / 'Restart-Receiver.ps1', '-Rack', 'B', '-Board', '0F02', '-Withdraw')
        rec = last_record(rack_b / 'restarts.jsonl')
        check(code == 0 and rec['state'] == 'held' and rec['pid_after'] == 0 and rec['others_changed'] == [],
              'Restart-Receiver -Withdraw stops and withdraws Z2 alone')
        check(not port_free(RECEIVER_PORTS['0F01']) and port_free(RECEIVER_PORTS['0F02']), "Z2's port is released; Z1's is still held")
        code, out = ps(box / 'Release-Receiver.ps1', '-Rack', 'B', '-Board', '0F02')
        rel = last_record(rack_b / 'releases.jsonl')
        check(code == 0 and rel['started'] and rel['receiver_pid'] > 0, 'Release-Receiver -Rack B advertises the withdrawn Z2 again')
        code, out = ps(box / 'Release-Receiver.ps1', '-Rack', 'B', '-Board', '0F03')
        check(code == 0 and last_record(rack_b / 'releases.jsonl')['receiver_pid'] > 0, 'Release-Receiver starts the held-at-start Z3')
        code, out = ps(box / 'Restart-Receiver.ps1', '-Rack', 'B', '-Board', '0F03', '-Hold')
        check(code == 0 and last_record(rack_b / 'restarts.jsonl')['state'] == 'held', 'Restart-Receiver -Hold leaves Z3 withdrawn')

        # --- The lease guard: a leased phone's receiver is not cut without that lease's token. ---
        lease = post(dict(fun='/input/acquire', data=dict(id='offrack-Z1', lease_ms=20000)))
        token = lease['leases'][0]['token']
        z1 = rows()['iMouse2-Z1']
        code, out = ps(box / 'Restart-Receiver.ps1', '-Rack', 'B', '-Board', '0F01')
        check(code != 0 and 'input lease' in out and rows()['iMouse2-Z1']['receiver_pid'] == z1['receiver_pid'],
              'Restart of a leased phone is refused without its token; nothing stopped')
        code, out = ps(box / 'Restart-Receiver.ps1', '-Rack', 'B', '-Board', '0F01', '-Token', token)
        check(code == 0 and last_record(rack_b / 'restarts.jsonl')['generation_after'] == 3, 'The lease holder can restart its own phone')
        check(post(dict(fun='/input/renew', data=dict(id='offrack-Z1', token=token)))['code'] == 0, 'The lease is intact after the restart')
        check(post(dict(fun='/device/airplay/restart', data=dict(pid='0F09')))['code'] == 36, 'An unknown board is refused')

        # --- A rack start beside its own running kernel is refused. ---
        code, out = ps(box / 'Start-Multiphone.ps1', '-Rack', 'B')
        check(code != 0 and 'process record' in out, 'Start-Multiphone refuses a second rack B kernel')
    finally:
        # --- Stop through the real script: graceful stop, rack-scoped leftover check, goodbye. ---
        code, out = ps(box / 'Stop-Multiphone.ps1', '-Rack', 'B')
        check(code == 0 and 'Stopped rack B' in out, 'Stop-Multiphone -Rack B stops the trial kernel: ' + out[-300:].replace('\n', ' | '))
        if code != 0:
            # Last resort, only this trial's own processes: the :9936 kernel and its stand-in receivers.
            subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                            "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'iMouse2.Kernel.exe' -and $_.CommandLine -match '127\\.0\\.0\\.1:9936/') "
                            "-or $_.Name -eq 'offrack-receiver.exe' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        left = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                               "@(Get-CimInstance Win32_Process -Filter \"Name='offrack-receiver.exe'\").Count"],
                              capture_output=True, text=True, timeout=60).stdout.strip()
        check(left == '0' and port_free(PORT) and all(port_free(p) for p in RECEIVER_PORTS.values()),
              'No trial kernel, stand-in receiver or listener remains')
        after = live_snapshot()
        check(before == after, 'The live kernel on :9916 is as before (same receivers, PIDs and restart counts)'
              if before is not None else 'No live kernel was running before or after')
        (run / 'trial-results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    failed = [r for r in results if not r['ok']]
    print(json.dumps(dict(passed=len(results) - len(failed), failed=len(failed), run=str(run.relative_to(ROOT)))))
    if failed: raise SystemExit(1)


if __name__ == '__main__':
    main()
