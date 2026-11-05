"""Off-rack trial of unattended recovery, safe beside the live rack (same isolation as offrack_trial.py:
a 'rack B' sandbox kernel on :9936, stand-in receivers that advertise nothing, test boards absent from
USB, names iMouse2-Z1..Z3; the live kernel is only read).

  1. Start-Multiphone.ps1 -Rack B launches the kernel detached (WMI): its parent is not this process
     tree, it has a stop file and a console log.
  2. Stop-Multiphone.ps1 -Rack B stops it gracefully through the stop file (no Ctrl+C), leaves no
     process or listener, and withdraws the names.
  3. Watchdog: start again, kill the sandbox kernel (simulated death; its stand-in receivers are left
     behind), `rack_recovery.py watch --once --no-bringup` must stop exactly those orphans, start the
     kernel again and report 'restart'; a second check says 'healthy'; after a deliberate stop it says
     'idle' and starts nothing.
  4. The live kernel's receivers, PIDs and restart counts are unchanged.

  python offrack/offrack_recovery_trial.py --kernel <candidate iMouse2.Kernel.exe>
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import offrack_trial as t  # noqa: E402


def powershell(command):
    return subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, errors='replace', timeout=120).stdout.strip()


def proc(pid):
    out = powershell(f"Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | Select-Object ProcessId,ParentProcessId,SessionId,ExecutablePath | ConvertTo-Json -Compress")
    return json.loads(out) if out else None


def stand_ins():
    out = powershell("@(Get-CimInstance Win32_Process -Filter \"Name='offrack-receiver.exe'\" | Select-Object ProcessId,ParentProcessId) | ConvertTo-Json -Compress")
    got = json.loads(out) if out else []
    return got if isinstance(got, list) else [got]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kernel', required=True)
    kernel = Path(parser.parse_args().kernel).resolve()
    if os.environ.get('IMOUSE_FARM_DATA'): raise SystemExit('IMOUSE_FARM_DATA is set: the sandbox scripts would use the real data folder.')
    used = [p for p in [t.PORT] + [q for b in t.BOARDS for q in range(t.RECEIVER_PORTS[b], t.RECEIVER_PORTS[b] + 3)] if not t.port_free(p)]
    if used: raise SystemExit(f'Trial ports in use: {used}; nothing started.')
    if stand_ins(): raise SystemExit('Stand-in receivers from an earlier trial are running; nothing started.')
    before = t.live_snapshot()
    if before and set(t.NAMES.values()) & set(before): raise SystemExit('A trial name is on the live kernel; nothing started.')
    present = powershell("@(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | Where-Object InstanceId -match 'VID_720A&PID_0F0[123]').Count")
    if present != '0': raise SystemExit(f'A trial board ID is present on USB ({present}); nothing started.')

    run = t.ROOT / f"output/offrack-recovery-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    fake = run / 'fake'
    subprocess.run(['dotnet', 'build', str(HERE / 'FakeReceiver'), '-c', 'Release', '-o', str(fake), '--nologo', '-v', 'q'],
                   check=True, stdin=subprocess.DEVNULL, capture_output=True, timeout=300)
    runtime = run / 'runtime'
    for rel in t.RUNTIME_FILES:
        (runtime / rel).parent.mkdir(parents=True, exist_ok=True); (runtime / rel).write_bytes(b'stand-in')
    (runtime / 'bin').mkdir(exist_ok=True)
    data = run / 'data'; data.mkdir(parents=True)
    devices = [dict(deviceid=f'offrack-{t.NAMES[b][8:]}', name=f'Trial {t.NAMES[b][8:]}', device_name='stand-in', width=414, height=896,
                    vid='720A', pid=b, uid=b, version='', gname='Off-rack') for b in t.BOARDS]
    receivers = [dict(DeviceId=f'offrack-{t.NAMES[b][8:]}', BoardPid=b, Name=t.NAMES[b], Pipe=f'{t.NAMES[b]}-recovery-frames',
                      Port=t.RECEIVER_PORTS[b], Mac=f'02:00:5A:00:0F:{b[2:]}') for b in t.BOARDS]
    for name, content in (('devices.json', devices), ('receivers.json', receivers), ('pointer-calibration.json', [])):
        (data / name).write_text(json.dumps(content, indent=2), encoding='utf-8')
    box = run / 'sandbox' / 'analysis' / 'rack'; box.mkdir(parents=True)
    for script in ('Start-Multiphone.ps1', 'Stop-Multiphone.ps1', 'Release-Receiver.ps1', 'Restart-Receiver.ps1', 'Watch-Rack.ps1',
                   'Bringup-Rack.ps1', 'rack_kernels.py', 'rack_recovery.py', 'bringup-plan.json', 'phone-slots.json', 'rack-b-slots.json'):
        shutil.copy2(t.RACK / script, box / script)
    (run / 'sandbox/tools/kernel-window').mkdir(parents=True)
    shutil.copy2(t.ROOT / 'tools/mdns_goodbye.py', run / 'sandbox/tools/mdns_goodbye.py')
    shutil.copy2(t.ROOT / 'tools/farm_paths.py', run / 'sandbox/tools/farm_paths.py')
    shutil.copy2(t.ROOT / 'tools/kernel-window/Stop-ConsoleProcessGracefully.ps1', run / 'sandbox/tools/kernel-window/')
    rack_b = box / 'rack-b'; rack_b.mkdir()
    arguments = [f'http://127.0.0.1:{t.PORT}/api/', '--data-dir', str(data), '--receivers', str(data / 'receivers.json'),
                 '--receiver', str(fake / 'offrack-receiver.exe'), '--receiver-runtime', str(runtime), '--rack', 'B']
    prep = dict(runDirectory=str(run), kernel=str(kernel), kernelSha256=t.sha(kernel.with_suffix('.dll')), arguments=arguments, rack='B',
                api=t.API, held=[], boards=list(t.BOARDS), inputEnabled=[],
                receivers=[dict(board=b, name=t.NAMES[b], port=t.RECEIVER_PORTS[b]) for b in t.BOARDS],
                dataSha256={n: t.sha(data / n) for n in ('devices.json', 'receivers.json', 'pointer-calibration.json')},
                sandbox=True, offrackTrial=True, serviceStarted=False, phoneInput=False)
    (rack_b / 'preparation.json').write_text(json.dumps(prep, indent=2), encoding='utf-8')
    record = rack_b / 'processes.json'

    def all_running():
        rows = t.rows()
        return all(rows[n]['receiver_pid'] > 0 for n in t.NAMES.values())

    def watch_once():
        out = subprocess.run([sys.executable, str(box / 'rack_recovery.py'), 'watch', '--rack', 'B', '--once', '--no-bringup'], cwd=box,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace', timeout=600).stdout
        return json.loads(out.strip().splitlines()[-1])

    try:
        # 1. Detached start through the real script.
        code, out = t.ps(box / 'Start-Multiphone.ps1', '-Rack', 'B')
        t.check(code == 0 and record.exists(), 'Start-Multiphone -Rack B starts the sandbox kernel: ' + out[-200:].replace('\n', ' | '))
        rec = json.loads(record.read_text(encoding='utf-8-sig'))
        kp = proc(rec['kernel']['pid'])
        parent = proc(kp['ParentProcessId']) if kp else None
        t.check(rec.get('launch') == 'detached' and rec.get('stopFile') and Path(rec['consoleLog']).exists(),
                'The record says detached, with a stop file and a console log')
        t.check(kp and (parent is None or Path(parent['ExecutablePath'] or '').name.lower() == 'wmiprvse.exe'),
                f"The kernel's parent is WMI, outside this session's process tree (parent {Path((parent or {}).get('ExecutablePath') or 'gone').name}, session {kp and kp['SessionId']})")
        t.check(t.wait(all_running), 'All three stand-in receivers run under the detached kernel')
        t.check(t.wait(lambda: t.rows()['iMouse2-Z1']['live']), 'Frames reach the detached kernel')

        # 2. Graceful stop through the stop file.
        code, out = t.ps(box / 'Stop-Multiphone.ps1', '-Rack', 'B')
        console = Path(rec['consoleLog']).read_text(encoding='utf-8', errors='replace')
        t.check(code == 0 and 'Stopped rack B' in out and not record.exists(), 'Stop-Multiphone -Rack B stops the detached kernel gracefully: ' + out[-200:].replace('\n', ' | '))
        t.check('Stop requested through' in console and not stand_ins() and t.port_free(t.PORT),
                'It stopped through its stop file, and its receivers and listener are gone')

        # 3. Watchdog after a kernel death.
        code, out = t.ps(box / 'Start-Multiphone.ps1', '-Rack', 'B')
        t.check(code == 0 and t.wait(all_running), 'Started again for the watchdog test')
        dead = json.loads(record.read_text(encoding='utf-8-sig'))['kernel']['pid']
        powershell(f'Stop-Process -Id {dead} -Force')   # The sandbox kernel only: simulated death.
        t.check(t.wait(lambda: proc(dead) is None) and len(stand_ins()) == 3, 'Kernel killed; its three stand-in receivers are left behind')
        entry = watch_once()
        t.check(entry.get('action') == 'restart' and entry.get('orphans_stopped') == 3 and entry.get('start') == 0,
                f"Watchdog stops the dead kernel's three receivers and starts it again: {entry}")
        new = json.loads(record.read_text(encoding='utf-8-sig'))['kernel']['pid']
        t.check(new != dead and t.wait(all_running), 'A new kernel runs every receiver again')
        died = list(rack_b.glob('processes-died-*.json'))
        t.check(len(died) == 1 and not (rack_b / 'watchdog-pending.json').exists(), "The dead kernel's record is archived; nothing pending")
        entry = watch_once()
        t.check(entry.get('action') == 'healthy', f'Next check: healthy ({entry})')
        code, out = t.ps(box / 'Stop-Multiphone.ps1', '-Rack', 'B')
        entry = watch_once()
        t.check(code == 0 and entry.get('action') == 'idle' and not record.exists() and t.port_free(t.PORT),
                f'After a deliberate stop the watchdog stays idle and starts nothing ({entry})')
        (rack_b / 'watchdog-pause').write_text('trial', encoding='utf-8')
        t.check(watch_once().get('action') == 'paused', 'A watchdog-pause file pauses it')
    finally:
        if record.exists():
            code, out = t.ps(box / 'Stop-Multiphone.ps1', '-Rack', 'B')
            t.check(code == 0, 'Cleanup stop: ' + out[-200:])
        left = stand_ins()
        for p in left: powershell(f"Stop-Process -Id {p['ProcessId']} -Force")   # Trial stand-ins only.
        powershell("Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'iMouse2.Kernel.exe' -and $_.CommandLine -match '127\\.0\\.0\\.1:9936/' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
        t.check(t.port_free(t.PORT) and not stand_ins(), 'No sandbox kernel, stand-in or listener remains')
        after = t.live_snapshot()
        t.check(before == after, 'The live kernel on :9916 is as before (same receivers, PIDs and restart counts)'
                if before is not None else 'No live kernel was running before or after')
        (run / 'trial-results.json').write_text(json.dumps(t.results, indent=2), encoding='utf-8')
    failed = [r for r in t.results if not r['ok']]
    print(json.dumps(dict(passed=len(t.results) - len(failed), failed=len(failed), run=str(run.relative_to(t.ROOT)))))
    if failed: raise SystemExit(1)


if __name__ == '__main__':
    main()
