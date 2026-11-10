"""Off-rack trial of unattended recovery, safe beside the live rack (same isolation as offrack_trial.py:
a sandbox kernel on :9936 ("sandbox": true in its preparation), stand-in receivers that advertise
nothing, test boards absent from USB, names iMouse2-Z1..Z3; the live kernel is only read).

  1. Start-Multiphone.ps1 launches the kernel detached (WMI): its parent is not this process
     tree, it has a stop file and a console log.
  2. Stop-Multiphone.ps1 stops it gracefully through the stop file (no Ctrl+C), leaves no
     process or listener, and withdraws the names.
  3. Watchdog: start again, kill the sandbox kernel (simulated death; its stand-in receivers are left
     behind). While a stop marker names that kernel (as Stop-Multiphone.ps1 writes before it asks the
     kernel to exit) `rack_recovery.py watch --once --no-bringup` must leave everything alone; without
     the marker it must stop exactly those orphans, start the kernel again and report 'restart'; a
     second check says 'healthy'; after a deliberate stop it says 'idle' and starts nothing.
  4. A start that does not come up as prepared (the preparation says one receiver is held, the kernel
     was told to run all three) must fail, leave no process record and no kernel, and keep its record
     as processes-failed-<time>.json.
  5. The live kernel's receivers, PIDs and restart counts are unchanged.

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kernel', required=True)
    kernel = Path(parser.parse_args().kernel).resolve()
    if os.environ.get('IMOUSE_FARM_DATA'): raise SystemExit('IMOUSE_FARM_DATA is set: the sandbox scripts would use the real data folder.')
    used = [p for p in [t.PORT] + [q for b in t.BOARDS for q in range(t.RECEIVER_PORTS[b], t.RECEIVER_PORTS[b] + 3)] if not t.port_free(p)]
    if used: raise SystemExit(f'Trial ports in use: {used}; nothing started.')
    if t.stand_ins(): raise SystemExit('Stand-in receivers from another trial are running; nothing started.')
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
    box = run / 'sandbox' / 'rack'; box.mkdir(parents=True)
    for script in ('RackState.ps1', 'Start-Multiphone.ps1', 'Stop-Multiphone.ps1', 'Release-Receiver.ps1', 'Restart-Receiver.ps1',
                   'rack_kernels.py', 'rack_recovery.py', 'bringup-plan.json', 'phone-slots.json', 'rack-b-slots.json'):
        shutil.copy2(t.RACK / script, box / script)
    (run / 'sandbox/tools/kernel-window').mkdir(parents=True)
    shutil.copy2(t.ROOT / 'tools/mdns_goodbye.py', run / 'sandbox/tools/mdns_goodbye.py')
    shutil.copy2(t.ROOT / 'tools/farm_paths.py', run / 'sandbox/tools/farm_paths.py')
    shutil.copy2(t.ROOT / 'tools/kernel-window/Stop-ConsoleProcessGracefully.ps1', run / 'sandbox/tools/kernel-window/')
    slots = box / 'slots'; slots.mkdir()   # The kernel's one state folder, as on the rack.
    arguments = [f'http://127.0.0.1:{t.PORT}/api/', '--data-dir', str(data), '--receivers', str(data / 'receivers.json'),
                 '--receiver', str(fake / 'offrack-receiver.exe'), '--receiver-runtime', str(runtime)]
    prep = dict(runDirectory=str(run), kernel=str(kernel), kernelSha256=t.sha(kernel.with_suffix('.dll')), arguments=arguments,
                api=t.API, held=[], boards=list(t.BOARDS), inputEnabled=[],
                receivers=[dict(board=b, name=t.NAMES[b], port=t.RECEIVER_PORTS[b]) for b in t.BOARDS],
                dataSha256={n: t.sha(data / n) for n in ('devices.json', 'receivers.json', 'pointer-calibration.json')},
                sandbox=True, offrackTrial=True, serviceStarted=False, phoneInput=False)
    (slots / 'preparation.json').write_text(json.dumps(prep, indent=2), encoding='utf-8')
    record = slots / 'processes.json'

    def stand_ins(): return t.stand_ins(fake)   # Only the ones started from this run's build.

    def all_running():
        rows = t.rows()
        return all(rows[n]['receiver_pid'] > 0 for n in t.NAMES.values())

    def watch_once():
        out = subprocess.run([sys.executable, str(box / 'rack_recovery.py'), 'watch', '--once', '--no-bringup'], cwd=box,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors='replace', timeout=600).stdout
        return json.loads(out.strip().splitlines()[-1])

    try:
        # 1. Detached start through the real script.
        code, out = t.ps(box / 'Start-Multiphone.ps1')
        t.check(code == 0 and record.exists(), 'Start-Multiphone starts the sandbox kernel: ' + out[-200:].replace('\n', ' | '))
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
        code, out = t.ps(box / 'Stop-Multiphone.ps1')
        console = Path(rec['consoleLog']).read_text(encoding='utf-8', errors='replace')
        t.check(code == 0 and 'Stopped:' in out and not record.exists(), 'Stop-Multiphone stops the detached kernel gracefully: ' + out[-200:].replace('\n', ' | '))
        t.check('Stop requested through' in console and not stand_ins() and t.port_free(t.PORT),
                'It stopped through its stop file, and its receivers and listener are gone')

        # 3. Watchdog after a kernel death.
        code, out = t.ps(box / 'Start-Multiphone.ps1')
        t.check(code == 0 and t.wait(all_running), 'Started again for the watchdog test')
        dead = json.loads(record.read_text(encoding='utf-8-sig'))['kernel']['pid']
        powershell(f'Stop-Process -Id {dead} -Force')   # The sandbox kernel only: simulated death.
        t.check(t.wait(lambda: proc(dead) is None) and len(stand_ins()) == 3, 'Kernel killed; its three stand-in receivers are left behind')
        marker = slots / 'stopping.json'
        marker.write_text(json.dumps(dict(utc='trial', pid=dead)), encoding='ascii')   # As a stop in progress would have it.
        entry = watch_once()
        t.check(entry.get('action') == 'stopping' and len(stand_ins()) == 3 and t.port_free(t.PORT) and record.exists()
                and not list(slots.glob('processes-died-*.json')),
                f'While a stop marker names the dead kernel the watchdog restarts nothing and touches nothing: {entry}')
        marker.unlink()
        entry = watch_once()
        t.check(entry.get('action') == 'restart' and entry.get('orphans_stopped') == 3 and entry.get('start') == 0,
                f"Watchdog stops the dead kernel's three receivers and starts it again: {entry}")
        new = json.loads(record.read_text(encoding='utf-8-sig'))['kernel']['pid']
        t.check(new != dead and t.wait(all_running), 'A new kernel runs every receiver again')
        died = list(slots.glob('processes-died-*.json'))
        t.check(len(died) == 1 and not (slots / 'watchdog-pending.json').exists(), "The dead kernel's record is archived; nothing pending")
        entry = watch_once()
        t.check(entry.get('action') == 'healthy', f'Next check: healthy ({entry})')
        code, out = t.ps(box / 'Stop-Multiphone.ps1')
        entry = watch_once()
        t.check(code == 0 and entry.get('action') == 'idle' and not record.exists() and t.port_free(t.PORT),
                f'After a deliberate stop the watchdog stays idle and starts nothing ({entry})')
        t.check(not (slots / 'stopping.json').exists() and len(list(slots.glob('processes-stopped-*.json'))) == 2,
                'Each deliberate stop renamed its record and removed its stop marker')
        (slots / 'watchdog-pause').write_text('trial', encoding='utf-8')
        t.check(watch_once().get('action') == 'paused', 'A watchdog-pause file pauses it')
        (slots / 'watchdog-pause').unlink()

        # 4. A start that does not come up as prepared: one receiver is prepared as held, the kernel runs all three.
        (slots / 'preparation.json').write_text(json.dumps(dict(prep, held=['0F03']), indent=2), encoding='utf-8')
        code, out = t.ps(box / 'Start-Multiphone.ps1')
        failed = list(slots.glob('processes-failed-*.json'))
        t.check(code != 0 and 'Held receivers differ' in out and not record.exists() and not (slots / 'processes-starting.json').exists()
                and len(failed) == 1, 'A kernel that did not come up as prepared is not recorded as started: ' + out[-160:].replace('\n', ' | '))
        t.check(t.wait(lambda: t.port_free(t.PORT) and not stand_ins(), 10) and proc(json.loads(failed[0].read_text(encoding='utf-8-sig'))['kernel']['pid']) is None
                if failed else False, 'and it was stopped again: no kernel, stand-in or listener of it remains')
        t.check(watch_once().get('action') == 'idle', 'The watchdog does not restart a kernel whose start failed')
    finally:
        if record.exists():
            code, out = t.ps(box / 'Stop-Multiphone.ps1')
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
