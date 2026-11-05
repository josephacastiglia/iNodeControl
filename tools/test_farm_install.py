"""Install/update/rollback/uninstall in temporary folders only; the launcher and preflight are checked
without changing this PC (the preflight is parsed for mutating commands and run read-only once)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import farm_install as fi
import farm_release as fr
from test_farm_release import build_package, make_repo

RELEASE = Path(__file__).resolve().parent / 'release'
IDLE = staticmethod(lambda root: [])


def idle(root):
    return []


def powershell(*args, cwd=None):
    return subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', *args],
                          capture_output=True, text=True, timeout=120, cwd=cwd)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo = make_repo(self.base)
        _, self.pkg_a, _ = build_package(self.base, repo=self.repo, version='1.0.0')
        (self.repo / 'tools/farm_jobs.py').write_text('import json\nVERSION = 2\n', encoding='utf-8')
        _, self.pkg_b, _ = build_package(self.base, repo=self.repo, version='1.1.0')
        self.root = self.base / 'pc/Programs/iMouseFarm'
        self.data = self.base / 'pc/iMouseFarm'

    def install(self):
        return fi.install(self.pkg_a, self.root, self.data, python=sys.executable, processes=idle)


class Lifecycle(Base):
    def test_install_update_rollback_uninstall(self):
        state = self.install()
        self.assertEqual((state['version'], state['previous']), ('1.0.0', None))
        self.assertTrue((self.root / 'Farm.ps1').is_file())
        for d in fi.DATA_DIRS:
            self.assertTrue((self.data / d).is_dir(), d)
        (self.data / f'{fr.RACK_DIR}/slots/preparation.json').write_text('{"fake": true}')
        state = fi.update(self.pkg_b, self.root, processes=idle)
        self.assertEqual((state['version'], state['previous']), ('1.1.0', '1.0.0'))
        self.assertIn('VERSION = 2', (self.root / 'versions/1.1.0/farm/tools/farm_jobs.py').read_text())
        self.assertNotIn('VERSION = 2', (self.root / 'versions/1.0.0/farm/tools/farm_jobs.py').read_text())
        state = fi.rollback(self.root, processes=idle)
        self.assertEqual((state['version'], state['previous']), ('1.0.0', '1.1.0'))
        state = fi.rollback(self.root, processes=idle)  # roll forward again: previous is kept
        self.assertEqual(state['version'], '1.1.0')
        history = fi.read_json(self.root / 'current.json')['history']
        self.assertEqual([h['action'] for h in history], ['install', 'update', 'rollback', 'rollback'])
        self.assertEqual(fi.read_json(self.data / 'data.json')['last_version'], '1.1.0')
        result = fi.uninstall(self.root, processes=idle)
        self.assertFalse(self.root.exists())
        self.assertEqual(result['data_kept'], str(self.data.resolve()))
        self.assertEqual((self.data / f'{fr.RACK_DIR}/slots/preparation.json').read_text(), '{"fake": true}')
        self.assertFalse(list(self.base.rglob('*.tmp')))

    def test_install_refusals(self):
        with self.assertRaisesRegex(fi.Refused, 'contain each other'):
            fi.install(self.pkg_a, self.root, self.root / 'data', processes=idle)
        checkout = self.base / 'checkout'
        (checkout / '.git').mkdir(parents=True)
        with self.assertRaisesRegex(fi.Refused, 'source checkout'):
            fi.install(self.pkg_a, checkout / 'farm', self.data, processes=idle)
        self.root.mkdir(parents=True)
        (self.root / 'someone else.txt').write_text('x')
        with self.assertRaisesRegex(fi.Refused, 'not empty'):
            self.install()
        (self.root / 'someone else.txt').unlink()
        self.install()
        with self.assertRaisesRegex(fi.Refused, 'use update'):
            self.install()
        with self.assertRaisesRegex(fi.Refused, 'already current'):
            fi.update(self.pkg_a, self.root, processes=idle)
        with self.assertRaisesRegex(fi.Refused, 'no previous'):
            fi.rollback(self.root, processes=idle)

    def test_data_folder_must_be_new_or_marked(self):
        self.data.mkdir(parents=True)
        (self.data / 'stray.txt').write_text('x')
        with self.assertRaisesRegex(fi.Refused, 'no data.json'):
            self.install()

    def test_running_farm_blocks_switches(self):
        self.install()
        busy = lambda root: [{'Name': 'iMouse2.Kernel.exe', 'ProcessId': 42, 'ExecutablePath': str(root / 'versions/1.0.0/kernel/iMouse2.Kernel.exe')}]
        for action in (lambda: fi.update(self.pkg_b, self.root, processes=busy), lambda: fi.uninstall(self.root, processes=busy)):
            with self.assertRaisesRegex(fi.Refused, 'pid 42'):
                action()
        self.assertEqual(fi.status(self.root)['version'], '1.0.0')

    def test_process_filter_matches_only_this_install(self):
        rows = [{'Name': 'a', 'ExecutablePath': str(self.root / 'versions/x/kernel/k.exe')},
                {'Name': 'b', 'CommandLine': f'python "{self.root}\\versions\\x\\farm\\tools\\s.py"'},
                {'Name': 'c', 'ExecutablePath': 'C:\\other\\k.exe', 'CommandLine': None}]
        with patch('subprocess.run') as run:
            run.return_value.stdout = json.dumps(rows)
            self.assertEqual([r['Name'] for r in fi.farm_processes(self.root)], ['a', 'b'])

    def test_older_version_never_opens_newer_data(self):
        self.install()
        marker = self.data / 'data.json'
        info = fi.read_json(marker)
        info['data_schema'] = 99
        marker.write_text(json.dumps(info))
        with self.assertRaisesRegex(fi.Refused, 'schema'):
            fi.update(self.pkg_b, self.root, processes=idle)
        self.assertEqual(fi.status(self.root)['version'], '1.0.0')

    def test_failed_copy_leaves_current_untouched(self):
        self.install()
        real = shutil.copyfile
        calls = {'n': 0}

        def flaky(src, dst, *a, **k):
            calls['n'] += 1
            if calls['n'] == 5:
                raise OSError('disk full')
            return real(src, dst, *a, **k)
        with patch('farm_install.shutil.copyfile', side_effect=flaky):
            with self.assertRaises(OSError):
                fi.update(self.pkg_b, self.root, processes=idle)
        state = fi.status(self.root)
        self.assertEqual((state['version'], state['versions'], state['leftover_partials']), ('1.0.0', ['1.0.0'], []))
        fi.update(self.pkg_b, self.root, processes=idle)  # a retry works

    def test_tampered_package_and_tampered_installed_version(self):
        (self.pkg_b / 'farm/tools/farm_jobs.py').write_text('evil')
        self.install()
        with self.assertRaisesRegex(fi.Refused, 'failed verification'):
            fi.update(self.pkg_b, self.root, processes=idle)
        self.assertEqual(fi.status(self.root)['versions'], ['1.0.0'])

    def test_rollback_tolerates_files_the_apps_wrote_but_not_changed_code(self):
        self.install()
        fi.update(self.pkg_b, self.root, processes=idle)
        (self.root / 'versions/1.0.0/console/startup-state.json').write_text('{}')
        fi.rollback(self.root, processes=idle)
        fi.rollback(self.root, processes=idle)
        (self.root / 'versions/1.0.0/kernel/iMouse2.Kernel.dll').write_bytes(b'patched')
        with self.assertRaisesRegex(fi.Refused, 'changed: kernel/iMouse2.Kernel.dll'):
            fi.rollback(self.root, processes=idle)
        self.assertEqual(fi.status(self.root)['version'], '1.1.0')

    def test_prune_keeps_current_and_previous(self):
        self.install()
        fi.update(self.pkg_b, self.root, processes=idle)
        (self.repo / 'tools/farm_jobs.py').write_text('VERSION = 3\n', encoding='utf-8')
        _, pkg_c, _ = build_package(self.base, repo=self.repo, version='1.2.0')
        fi.update(pkg_c, self.root, processes=idle)
        self.assertEqual(fi.prune(self.root, processes=idle), ['1.0.0'])
        self.assertEqual(fi.status(self.root)['versions'], ['1.1.0', '1.2.0'])

    def test_uninstall_refuses_foreign_files(self):
        self.install()
        (self.root / 'notes.txt').write_text('operator notes')
        with self.assertRaisesRegex(fi.Refused, 'notes.txt'):
            fi.uninstall(self.root, processes=idle)
        self.assertTrue((self.root / 'versions/1.0.0').is_dir())

    def test_atomic_json_never_leaves_temp_files(self):
        target = self.base / 'state.json'
        fi.write_json_atomic(target, {'a': 1})
        fi.write_json_atomic(target, {'a': 2})
        self.assertEqual(fi.read_json(target), {'a': 2})
        self.assertEqual([p.name for p in self.base.iterdir() if p.name.endswith('.tmp')], [])

    def test_cli_reports_refusals_as_json(self):
        out = subprocess.run([sys.executable, '-E', str(Path(fi.__file__)), 'status', '--root', str(self.root)],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(json.loads(out.stdout), {'installed': False})
        out = subprocess.run([sys.executable, '-E', str(Path(fi.__file__)), 'rollback', '--root', str(self.root)],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 2)
        self.assertIn('nothing installed', json.loads(out.stdout)['refused'])


@unittest.skipUnless(sys.platform == 'win32', 'Windows PowerShell')
class Launcher(Base):
    def test_status_ready_command_and_blocked_command(self):
        self.install()
        # The synthetic server stub is 'ready'; replace it in the installed copy is not allowed, so the
        # package's own stub runs: it must see the data folder as cwd and the IMOUSE_FARM_* variables.
        probe = self.root / 'versions/1.0.0/farm/tools/imouse_farm_server.py'
        self.assertTrue(probe.is_file())
        status = powershell('-File', str(self.root / 'Farm.ps1'), 'status', cwd=self.base)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn('1.0.0', status.stdout)
        self.assertIn('start-rack', status.stdout)
        blocked = powershell('-File', str(self.root / 'Farm.ps1'), 'start-rack', cwd=self.base)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn('not ready', blocked.stderr)
        self.assertIn('Nothing was started', blocked.stderr.replace('\n', ' ').replace('  ', ' ') + blocked.stderr)

    def test_ready_python_command_runs_from_current_version_in_the_data_folder(self):
        repo = make_repo(self.base / 'env-probe')
        (repo / 'tools/imouse_farm_server.py').write_text(
            (repo / 'tools/imouse_farm_server.py').read_text(encoding='utf-8') +
            'import os, json, sys\nif __name__ == "__main__":\n'
            '    print(json.dumps({"cwd": os.getcwd(), "file": __file__, "argv": sys.argv[1:],'
            ' **{k: v for k, v in os.environ.items() if k.startswith("IMOUSE_FARM_")}}))\n', encoding='utf-8')
        _, pkg, _ = build_package(self.base / 'env-probe', repo=repo, version='2.0.0')
        fi.install(pkg, self.root, self.data, python=sys.executable, processes=idle)
        run = powershell('-File', str(self.root / 'Farm.ps1'), 'server', '--port', '1', cwd=self.base)
        self.assertEqual(run.returncode, 0, run.stderr)
        seen = json.loads(run.stdout.strip().splitlines()[-1])
        self.assertEqual(Path(seen['cwd']).resolve(), self.data.resolve())
        self.assertEqual(Path(seen['file']).resolve(), (self.root / 'versions/2.0.0/farm/tools/imouse_farm_server.py').resolve())
        self.assertEqual(seen['argv'], ['--port', '1'])
        self.assertEqual(seen['IMOUSE_FARM_VERSION'], '2.0.0')
        self.assertEqual(Path(seen['IMOUSE_FARM_DATA']).resolve(), self.data.resolve())
        self.assertEqual(Path(seen['IMOUSE_FARM_KERNEL']).resolve(), (self.root / 'versions/2.0.0/kernel/iMouse2.Kernel.exe').resolve())


class RuntimeGuard(unittest.TestCase):
    def test_guard_refuses_kernel_connections_and_processes_and_reports_forbidden_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            forbidden = tmp / 'dev folder'
            forbidden.mkdir()
            (forbidden / 'secret.json').write_text('{}')
            script = tmp / 'probe.py'
            script.write_text(
                'import socket, subprocess, json\nout = {}\n'
                'server = socket.socket(); server.bind(("127.0.0.1", 0)); server.listen()\n'
                'own = server.getsockname()[1]\n'
                'for label, port in (("own", own), ("kernel", 9916)):\n'
                '    c = socket.socket()\n'
                '    try: c.connect(("127.0.0.1", port)); out[label] = "connected"\n'
                '    except PermissionError: out[label] = "refused"\n'
                '    except OSError: out[label] = "os error"\n'
                'try: subprocess.run(["cmd", "/c", "echo"]); out["process"] = "ran"\n'
                'except PermissionError: out["process"] = "refused"\n'
                'open(%r).read()\nprint(json.dumps(out))\n' % str(forbidden / 'secret.json'), encoding='utf-8')
            report = tmp / 'report.json'
            run = subprocess.run([sys.executable, '-E', str(RELEASE / 'runtime_guard.py'), '--forbid', str(forbidden),
                                  '--report', str(report), '--', str(script)], capture_output=True, text=True, timeout=60)
            seen = json.loads(run.stdout.strip().splitlines()[-1])
            self.assertEqual(seen, {'own': 'connected', 'kernel': 'refused', 'process': 'refused'})
            result = json.loads(report.read_text())
            self.assertEqual(result['exit'], 0)
            self.assertEqual(len(result['forbidden_opened']), 1)
            self.assertTrue(any('9916' in r for r in result['refused']))
            self.assertTrue(any('Popen' in r or 'CreateProcess' in r for r in result['refused']))


class PowerShellScripts(unittest.TestCase):
    MUTATING = {'new-netfirewallrule', 'set-netfirewallrule', 'enable-netfirewallrule', 'remove-netfirewallrule', 'netsh',
                'set-service', 'start-service', 'stop-service', 'restart-service', 'new-service', 'sc.exe', 'sc',
                'set-itemproperty', 'new-itemproperty', 'remove-itemproperty', 'new-item', 'remove-item', 'set-content',
                'add-content', 'out-file', 'copy-item', 'move-item', 'set-executionpolicy', 'start-process', 'pnputil',
                'enable-pnpdevice', 'disable-pnpdevice', 'set-netconnectionprofile', 'setx', 'msiexec', 'winget',
                'install-package', 'install-module', 'invoke-webrequest', 'invoke-restmethod', 'start-bitstransfer', 'reg', 'reg.exe'}

    def commands(self, path):
        script = (
            "$t=$null;$e=$null;$a=[System.Management.Automation.Language.Parser]::ParseFile('%s',[ref]$t,[ref]$e);"
            "if($e.Count){'ERRORS:'+($e|%%{$_.Message}) -join ';';exit 3};"
            "$a.FindAll({param($n) $n -is [System.Management.Automation.Language.CommandAst]},$true)|%%{$_.GetCommandName()}|?{$_}|Sort-Object -Unique" % str(path).replace("'", "''"))
        out = powershell('-Command', script)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        return {line.strip().casefold() for line in out.stdout.splitlines() if line.strip()}

    @unittest.skipUnless(sys.platform == 'win32', 'Windows PowerShell')
    def test_preflight_never_runs_a_changing_command(self):
        used = self.commands(RELEASE / 'Preflight-Farm.ps1')
        self.assertFalse(used & self.MUTATING, used & self.MUTATING)
        self.assertIn('get-netfirewallrule', used)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows PowerShell')
    def test_launcher_and_installer_parse_and_change_no_system_setting(self):
        for name in ('Farm.ps1', 'Install-Farm.ps1'):
            used = self.commands(RELEASE / name)
            self.assertFalse(used & (self.MUTATING - {'start-process'}), (name, used & self.MUTATING))

    @unittest.skipUnless(sys.platform == 'win32' and os.environ.get('FARM_PREFLIGHT_LIVE', '1') == '1', 'read-only live preflight')
    def test_preflight_runs_read_only_and_reports_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = powershell('-File', str(RELEASE / 'Preflight-Farm.ps1'), '-InstallRoot', str(Path(tmp) / 'root'),
                             '-DataRoot', str(Path(tmp) / 'data'), '-Json')
            report = json.loads(out.stdout[out.stdout.index('{'):])
            self.assertTrue(report['readOnly'])
            ids = {c['id'] for c in report['checks']}
            for need in ('windows', 'dotnet', 'python', 'python-packages', 'ffmpeg', 'ocr', 'bonjour', 'usb-boards',
                         'vendor-service', 'firewall-receivers', 'firewall-media', 'folders', 'ports'):
                self.assertIn(need, ids)
            self.assertEqual(out.returncode, 0 if report['ok'] else 1)
            self.assertFalse((Path(tmp) / 'root').exists() or (Path(tmp) / 'data').exists(), 'preflight created a folder')
            for c in report['checks']:
                if c['status'] != 'ok':
                    self.assertTrue(c['step'], c['id'])

    @unittest.skipUnless(sys.platform == 'win32', 'Windows PowerShell')
    def test_preflight_flags_a_dev_folder_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(tmp) / 'checkout'
            (checkout / '.git').mkdir(parents=True)
            out = powershell('-File', str(RELEASE / 'Preflight-Farm.ps1'), '-InstallRoot', str(checkout / 'farm'),
                             '-DataRoot', str(checkout / 'farm/data'), '-Json')
            report = json.loads(out.stdout[out.stdout.index('{'):])
            folders = next(c for c in report['checks'] if c['id'] == 'folders')
            self.assertEqual(folders['status'], 'fail')
            self.assertIn('source checkout', folders['detail'])
            self.assertIn('contain each other', folders['detail'])
            self.assertEqual(out.returncode, 1)


if __name__ == '__main__':
    unittest.main()
