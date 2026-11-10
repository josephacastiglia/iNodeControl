"""Rack PowerShell scripts read today's folders with IMOUSE_FARM_DATA unset and the data folder when installed.

Each run is a sandbox copy whose first state file is missing, so the script stops on that read (the error names
the path it tried) before any process check, HTTP call or start. The kernel-API lines are evaluated on their own
with fake preparations: no request is ever sent.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = ('RackState.ps1', 'Start-Multiphone.ps1', 'Stop-Multiphone.ps1', 'Release-Receiver.ps1', 'Restart-Receiver.ps1',
           'Start-Window.ps1', 'Stop-Window.ps1')
RACK = 'rack'                                     # the scripts' folder in a checkout
DATA_STATE = 'analysis/farm-multiphone-20261020'  # their state folder inside IMOUSE_FARM_DATA


def ps(script, *args, env=None):
    clean = {k: v for k, v in os.environ.items() if not k.startswith('IMOUSE_FARM_')}
    run = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script), *args],
                         capture_output=True, text=True, timeout=120, env=clean | (env or {}), stdin=subprocess.DEVNULL)
    return run.returncode, re.sub(r'\s+', ' ', run.stdout + run.stderr)


@unittest.skipUnless(sys.platform == 'win32', 'Windows PowerShell')
class RackScriptState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name).resolve()
        self.main = base / 'proj' / RACK
        self.lane = base / 'proj.worktrees' / 'lane' / RACK
        self.data = base / 'data'
        for folder in (self.main, self.lane):
            folder.mkdir(parents=True)
            for name in SCRIPTS:
                shutil.copyfile(HERE / name, folder / name)
        self.installed = {'IMOUSE_FARM_DATA': str(self.data)}
        self.data_state = self.data / DATA_STATE

    def assertTried(self, out, path):
        # PowerShell wraps long error lines at the console width, so compare without whitespace.
        self.assertIn(re.sub(r'\s', '', str(path)).casefold(), re.sub(r'\s', '', out).casefold(), out[-600:])

    def test_the_kernel_scripts_read_one_folder_beside_themselves_and_the_data_folder_installed(self):
        for name, args in (('Start-Multiphone.ps1', []), ('Stop-Multiphone.ps1', []),
                           ('Release-Receiver.ps1', ['-Board', '0F01']), ('Restart-Receiver.ps1', ['-Board', '0F01'])):
            code, out = ps(self.lane / name, *args)
            self.assertNotEqual(code, 0)
            self.assertTried(out, self.lane / 'slots' / 'preparation.json')
            code, out = ps(self.lane / name, *args, env=self.installed)
            self.assertNotEqual(code, 0)
            self.assertTried(out, self.data_state / 'slots' / 'preparation.json')

    def test_the_removed_stage_and_rack_parameters_are_refused_not_ignored(self):
        # 'Stop-Multiphone.ps1 -Rack B' once meant "only rack B's kernel"; it must never stop the one kernel instead.
        for name, args in (('Start-Multiphone.ps1', ['-Rack', 'B']), ('Stop-Multiphone.ps1', ['-Rack', 'B']),
                           ('Start-Multiphone.ps1', ['-Stage', 'held']), ('Stop-Multiphone.ps1', ['-Stage', 'slots']),
                           ('Start-Multiphone.ps1', ['-Attached']),
                           ('Release-Receiver.ps1', ['-Board', '0F01', '-Rack', 'B']), ('Restart-Receiver.ps1', ['-Board', '0F01', '-Stage', 'slots'])):
            code, out = ps(self.lane / name, *args)
            self.assertNotEqual(code, 0, (name, args))
            self.assertIn('parameter', out.casefold(), (name, args, out[-300:]))
            self.assertNotIn('preparation.json', out, (name, args))   # stopped before reading any state

    def test_a_kernel_counts_as_started_only_when_it_came_up_as_prepared(self):
        import json
        prep = dict(kernelSha256='a' * 64, inputEnabled=['0F01'], held=['0F03'], receivers=[dict(board=b) for b in ('0F01', '0F02', '0F03')])

        def status(sha='a' * 64, allowed=('0F01',), states=('mirroring', 'mirroring', 'held'), pids=(11, 12, 0)):
            return dict(build_identity=dict(sha256=sha), allowed=list(allowed),
                        receivers=[dict(receiver_state=s, receiver_pid=p) for s, p in zip(states, pids)])

        cases = [(dict(status=status(), exited=False), ''),
                 (dict(status=status(), exited=True), 'exited during startup'),
                 (dict(status=None, exited=False), 'did not answer'),
                 (dict(status=status(sha='b' * 64), exited=False), 'identity or allow-list'),
                 (dict(status=status(allowed=()), exited=False), 'identity or allow-list'),
                 (dict(status=status(states=('mirroring',) * 3, pids=(11, 12, 13)), exited=False), 'Held receivers differ'),
                 (dict(status=status(states=('mirroring', 'starting', 'held'), pids=(11, 0, 0)), exited=False), '1 of 2 receivers')]
        data = self.main / 'cases.json'
        data.write_text(json.dumps(dict(prep=prep, cases=[c for c, _ in cases])), encoding='ascii')
        script = self.main / 'problem.ps1'
        script.write_text(". (Join-Path $PSScriptRoot 'RackState.ps1')\r\n"
                          "$d=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'cases.json') -Raw | ConvertFrom-Json\r\n"
                          "$out=foreach($c in $d.cases){ '[' + (Get-RackStartProblem $c.status $d.prep ([bool]$c.exited)) + ']' }\r\n"
                          "$out -join '|'\r\n", encoding='ascii')
        code, out = ps(script)
        self.assertEqual(code, 0, out)
        problems = [p.strip('[] ') for p in out.strip().split('|')]
        self.assertEqual(len(problems), len(cases), out)
        for (case, want), got in zip(cases, problems):
            self.assertTrue(got == '' if want == '' else want in got, (want, got))

    def test_the_record_follows_readiness_and_a_stop_is_marked_before_it_begins(self):
        # Order in the scripts themselves; the off-rack recovery trial runs both ends for real.
        start = (HERE / 'Start-Multiphone.ps1').read_text(encoding='ascii')
        launch = start.index('Invoke-CimMethod -ClassName Win32_Process -MethodName Create')
        self.assertLess(launch, start.index('Set-Content -LiteralPath $taskStarting'))
        self.assertLess(start.index('if(!$taskProblem){'), start.index("Rename-Item -LiteralPath $taskStarting -NewName 'processes.json'"))
        self.assertNotRegex(start, r'Set-Content[^\n]*\$taskProcessFile', 'processes.json is never written before the verdict')
        stop = (HERE / 'Stop-Multiphone.ps1').read_text(encoding='ascii')
        mark = stop.index('Set-Content -LiteralPath $taskStopping')
        self.assertLess(mark, stop.index('[IO.File]::WriteAllText([string]$taskProcs.stopFile'))
        self.assertLess(mark, stop.index('-File $taskHelper'))
        self.assertLess(stop.index("Rename-Item -LiteralPath (Join-Path $taskDir 'processes.json')"), stop.index('Remove-Item -LiteralPath $taskStopping'))

    def test_windows_state_and_the_main_folders_kernel_record(self):
        for name in ('Start-Window.ps1', 'Stop-Window.ps1'):
            code, out = ps(self.lane / name, '-Window', 'reel-slot18')
            self.assertNotEqual(code, 0)
            self.assertTried(out, self.lane / 'windows' / 'reel-slot18' / 'preparation.json')
            code, out = ps(self.lane / name, '-Window', 'reel-slot18', env=self.installed)
            self.assertTried(out, self.data_state / 'windows' / 'reel-slot18' / 'preparation.json')
        # Start-Window reads the kernel's record from the MAIN folder in a checkout (today's rule) ...
        window = self.lane / 'windows' / 'reel-slot18'
        window.mkdir(parents=True)
        config = window / 'creation-config.json'
        config.write_text('{}')
        import hashlib
        digest = hashlib.sha256(config.read_bytes()).hexdigest()
        rack_prep = self.main / 'slots' / 'preparation.json'
        (window / 'preparation.json').write_text(
            '{"config": %s, "configSha256": "%s", "rackPreparation": %s}' % (_j(config), digest, _j(rack_prep)))
        code, out = ps(self.lane / 'Start-Window.ps1', '-Window', 'reel-slot18')
        self.assertTried(out, self.main / 'slots' / 'processes.json')
        # ... and, installed, from beside the window's rack preparation in the data folder.
        dwindow = self.data_state / 'windows' / 'reel-slot18'
        dwindow.mkdir(parents=True)
        dconfig = dwindow / 'creation-config.json'
        dconfig.write_text('{}')
        drack = self.data_state / 'slots' / 'preparation.json'
        (dwindow / 'preparation.json').write_text(
            '{"config": %s, "configSha256": "%s", "rackPreparation": %s}' % (_j(dconfig), digest, _j(drack)))
        code, out = ps(self.lane / 'Start-Window.ps1', '-Window', 'reel-slot18', env=self.installed)
        self.assertTried(out, self.data_state / 'slots' / 'processes.json')
        # A preparation that names no rack preparation falls back to the data folder's one kernel folder.
        (dwindow / 'preparation.json').write_text('{"config": %s, "configSha256": "%s"}' % (_j(dconfig), digest))
        code, out = ps(self.lane / 'Start-Window.ps1', '-Window', 'reel-slot18', env=self.installed)
        self.assertTried(out, self.data_state / 'slots' / 'processes.json')

    def test_kernel_api_lines_follow_the_rack_preparation(self):
        lines = {}
        for name in ('Start-Window.ps1', 'Stop-Window.ps1'):
            text = (HERE / name).read_text(encoding='ascii')
            block = re.search(r"^\$taskApi='http://127\.0\.0\.1:9916/api'\r?\n^if\(\$taskPrep\.rackPreparation.*$", text, re.M)
            self.assertTrue(block, name)
            lines[name] = block.group(0)
        self.assertEqual(len(set(lines.values())), 1, 'both scripts compute the API the same way')
        rack = self.main / 'rack.json'
        rack.write_text('{"arguments": ["http://127.0.0.1:9916/api/", "--data-dir", "x"]}')
        other = self.main / 'other-port.json'
        other.write_text('{"arguments": ["http://127.0.0.1:9936/api/", "--data-dir", "x"]}')
        for prep, want in ((f"@{{rackPreparation='{rack}'}}", 'http://127.0.0.1:9916/api'),
                           (f"@{{rackPreparation='{other}'}}", 'http://127.0.0.1:9936/api'),
                           ("@{rackPreparation=''}", 'http://127.0.0.1:9916/api'),
                           (f"@{{rackPreparation='{self.main / 'missing.json'}'}}", 'http://127.0.0.1:9916/api')):
            script = self.main / 'api.ps1'
            script.write_text(f"$taskPrep=[pscustomobject]{prep}\r\n{lines['Start-Window.ps1']}\r\n$taskApi\r\n", encoding='ascii')
            code, out = ps(script)
            self.assertEqual((code, out.strip()), (0, want), prep)


def _j(path):
    import json
    return json.dumps(str(path))


if __name__ == '__main__':
    unittest.main()
