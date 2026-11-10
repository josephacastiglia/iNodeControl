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


def schema_1_data(data):
    """A data folder as a version with data schema 1 left it: the rack state in the old place, none in the new."""
    old = Path(data) / fi.OLD_RACK_STATE
    (old / 'slots').mkdir(parents=True)
    (old / 'windows/reel-slot18').mkdir(parents=True)
    (old / 'slots/preparation.json').write_text('{"fake": "kernel preparation"}')
    (old / 'windows/reel-slot18/preparation.json').write_text('{"fake": "window preparation"}')
    (old / 'phone-slots.json').write_text('{"slots": {}}')
    for d in fi.DATA_DIRS:
        if not d.startswith(fi.RACK_STATE + '/'):
            (Path(data) / d).mkdir(parents=True, exist_ok=True)
    fi.write_json_atomic(Path(data) / 'data.json', {'schema_version': fi.SCHEMA, 'data_schema': 1, 'created_utc': fi.now(), 'last_version': '0.9.0'})
    return old


def snapshot(root):
    """Every folder and file under root with its bytes: equal snapshots mean nothing was moved or changed."""
    root = Path(root)
    return {p.relative_to(root).as_posix(): (p.read_bytes() if p.is_file() else None) for p in sorted(root.rglob('*'))}


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
        (self.data / f'{fi.RACK_STATE}/slots/preparation.json').write_text('{"fake": true}')
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
        self.assertEqual((self.data / f'{fi.RACK_STATE}/slots/preparation.json').read_text(), '{"fake": true}')
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


class RealProcessCheck(Base):
    """Every other test passes a stand-in for the process check, which is how the real one came to count the
    installer itself as "the farm running" (found 9 Nov). These use the real check."""
    def test_the_installer_and_whoever_launched_it_are_not_the_farm(self):
        root = str(self.root.resolve())
        rows = [{'ProcessId': 1, 'ParentProcessId': 0, 'Name': 'explorer.exe', 'ExecutablePath': r'C:\Windows\explorer.exe', 'CommandLine': 'explorer'},
                {'ProcessId': 10, 'ParentProcessId': 1, 'Name': 'powershell.exe', 'ExecutablePath': 'ps', 'CommandLine': f'Install-Farm.ps1 -Update -Root "{root}"'},
                {'ProcessId': 11, 'ParentProcessId': 10, 'Name': 'python.exe', 'ExecutablePath': 'py', 'CommandLine': f'farm_install.py update --root "{root}"'},
                {'ProcessId': 20, 'ParentProcessId': 1, 'Name': 'iMouse2.Kernel.exe', 'ExecutablePath': root + r'ersions.0.0\kernel\iMouse2.Kernel.exe', 'CommandLine': 'k'},
                {'ProcessId': 21, 'ParentProcessId': 1, 'Name': 'python.exe', 'ExecutablePath': 'py', 'CommandLine': root + r'\currentarm	ools\imouse_farm_server.py'}]
        self.assertEqual(fi.own_lineage(rows, 11), {11, 10, 1})
        self.assertEqual([r['ProcessId'] for r in fi.from_install(rows, self.root, 11)], [20, 21])
        loop = [{'ProcessId': 5, 'ParentProcessId': 6}, {'ProcessId': 6, 'ParentProcessId': 5}]   # a reused PID must not hang it
        self.assertEqual(fi.own_lineage(loop, 5), {5, 6})

    def cli(self, *args):
        return subprocess.run([sys.executable, str(Path(fi.__file__)), *map(str, args)], capture_output=True, text=True, timeout=180)

    def test_update_rollback_and_uninstall_work_from_the_command_line(self):
        self.install()
        for args, version in ((('update', '--package', self.pkg_b, '--root', self.root), '1.1.0'), (('rollback', '--root', self.root), '1.0.0')):
            done = self.cli(*args)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual(fi.status(self.root)['version'], version)
        done = self.cli('uninstall', '--root', self.root)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertFalse((self.root / 'versions').exists())
        self.assertTrue((self.data / 'data.json').is_file())   # the operator's data stays

    def test_a_real_process_started_from_the_install_still_blocks_the_command_line(self):
        self.install()
        marker = self.root / 'current-marker-for-test.txt'
        farm = subprocess.Popen([sys.executable, '-c', 'import sys, time; time.sleep(120)', str(marker)])
        try:
            done = self.cli('update', '--package', self.pkg_b, '--root', self.root)
            self.assertNotEqual(done.returncode, 0)
            self.assertIn(f'pid {farm.pid}', done.stdout + done.stderr)
            self.assertEqual(fi.status(self.root)['version'], '1.0.0')
        finally:
            farm.kill(); farm.wait(timeout=30)


class DataMigration(unittest.TestCase):
    """Data schema 2 keeps the rack state in <data>/rack; a schema 1 folder is moved there once."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name) / 'pc/iMouseFarm'
        self.old, self.new = self.data / fi.OLD_RACK_STATE, self.data / fi.RACK_STATE

    def test_old_only_is_moved_once_and_recorded(self):
        schema_1_data(self.data)
        before = snapshot(self.old)
        record = fi.migrate_data(self.data)
        self.assertEqual((record['moved'], record['to'], record['data_schema']), (fi.OLD_RACK_STATE, fi.RACK_STATE, 2))
        self.assertEqual(snapshot(self.new), before, 'the same folders and bytes, in the new place')
        self.assertFalse(self.old.exists())
        self.assertFalse(self.old.parent.exists(), 'the emptied parent folder goes too')
        info = fi.read_json(self.data / 'data.json')
        self.assertEqual((info['data_schema'], info['migrations'], info['last_version']), (2, [record], '0.9.0'))
        after = snapshot(self.data)
        self.assertIsNone(fi.migrate_data(self.data), 'a second run finds nothing to move')
        self.assertEqual(snapshot(self.data), after)
        self.assertEqual(fi.init_data(self.data)['migrations'], [record], 'and init-data adds no second record')
        self.assertFalse(list(self.data.rglob('*.tmp')))

    def test_new_only_is_untouched(self):
        fi.init_data(self.data)
        (self.new / 'slots/preparation.json').write_text('{"fake": true}')
        before = snapshot(self.data)
        self.assertIsNone(fi.migrate_data(self.data))
        self.assertEqual(snapshot(self.data), before)
        self.assertNotIn('migrations', fi.read_json(self.data / 'data.json'))

    def test_both_places_are_refused_with_both_named_and_nothing_moves(self):
        schema_1_data(self.data)
        (self.new / 'slots').mkdir(parents=True)
        (self.new / 'slots/preparation.json').write_text('{"fake": "newer"}')
        before = snapshot(self.data)
        for attempt in (lambda: fi.migrate_data(self.data), lambda: fi.init_data(self.data)):
            with self.assertRaises(fi.Refused) as refused:
                attempt()
            message = str(refused.exception)
            self.assertIn('rack state in two places', message)
            self.assertIn(str(self.old), message)
            self.assertIn(str(self.new), message)
            self.assertIn('Nothing was moved', message)
            self.assertEqual(snapshot(self.data), before)
        # An empty new folder counts too: the installer never guesses which of the two is current.
        shutil.rmtree(self.new)
        self.new.mkdir()
        with self.assertRaisesRegex(fi.Refused, 'two places'):
            fi.migrate_data(self.data)
        self.new.rmdir()
        self.assertIsNotNone(fi.migrate_data(self.data), 'with the other one removed the move goes ahead')

    def test_a_version_that_reads_the_old_layout_and_newer_data_move_nothing(self):
        schema_1_data(self.data)
        before = snapshot(self.data)
        self.assertIsNone(fi.migrate_data(self.data, package_schema=1), 'a schema 1 version still reads the old place')
        self.assertEqual(snapshot(self.data), before)
        marker = self.data / 'data.json'
        marker.write_text(json.dumps(dict(fi.read_json(marker), data_schema=99)))
        before = snapshot(self.data)
        self.assertIsNone(fi.migrate_data(self.data), 'data newer than this version is left for the schema refusal')
        self.assertEqual(snapshot(self.data), before)

    def test_a_move_that_cannot_be_recorded_is_undone(self):
        schema_1_data(self.data)
        before = snapshot(self.data)
        with patch('farm_install.write_json_atomic', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                fi.migrate_data(self.data)
        self.assertEqual(snapshot(self.data), before, 'not recorded, so not moved')
        self.assertIsNotNone(fi.migrate_data(self.data), 'a retry works')

    def test_other_files_beside_the_old_folder_stay_where_they_are(self):
        schema_1_data(self.data)
        (self.old.parent / 'operator-notes.txt').write_text('mine')
        fi.migrate_data(self.data)
        self.assertEqual((self.old.parent / 'operator-notes.txt').read_text(), 'mine')
        self.assertFalse(self.old.exists())
        self.assertTrue((self.new / 'slots/preparation.json').is_file())

    def test_a_folder_without_a_marker_or_a_file_in_the_old_place_is_refused(self):
        self.data.mkdir(parents=True)
        with self.assertRaisesRegex(fi.Refused, 'no data.json'):
            fi.migrate_data(self.data)
        schema_1_data(self.data / 'second')
        old = self.data / 'second' / fi.OLD_RACK_STATE
        shutil.rmtree(old)
        old.write_text('not a folder')
        with self.assertRaisesRegex(fi.Refused, 'not a plain folder'):
            fi.migrate_data(self.data / 'second')
        self.assertEqual(old.read_text(), 'not a folder')

    def test_cli_moves_reports_and_refuses(self):
        schema_1_data(self.data)
        cli = [sys.executable, '-E', str(Path(fi.__file__)), 'migrate-data', '--data', str(self.data)]
        out = subprocess.run(cli, capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(json.loads(out.stdout)['moved']['to'], fi.RACK_STATE)
        self.assertTrue((self.new / 'phone-slots.json').is_file())
        out = subprocess.run(cli, capture_output=True, text=True, timeout=60)
        self.assertEqual((out.returncode, json.loads(out.stdout)), (0, {'moved': None}))
        (self.old / 'slots').mkdir(parents=True)
        out = subprocess.run(cli, capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 2)
        self.assertIn('two places', json.loads(out.stdout)['refused'])

    def test_the_layout_names_agree_everywhere(self):
        # One new place and one old place, named in four files: the installer, farm_paths (Python state),
        # RackState.ps1 (PowerShell state) and the launcher's check for a data folder still in the old layout.
        self.assertEqual(fr.DATA_SCHEMA, fi.RACK_STATE_SCHEMA)
        self.assertEqual({d.split('/')[0] for d in fi.DATA_DIRS if 'slots' in d or 'windows' in d}, {fi.RACK_STATE})
        launcher = (RELEASE / 'Farm.ps1').read_text(encoding='utf-8')
        self.assertIn("(Join-Path $data '%s')" % fi.OLD_RACK_STATE.replace('/', '\\'), launcher)
        self.assertIn("'install\\farm_install.py') migrate-data --data $data", launcher)
        rack_state = (Path(fr.REPO) / fr.RACK_DIR / 'RackState.ps1').read_text(encoding='utf-8')
        self.assertIn("Join-Path $env:IMOUSE_FARM_DATA '%s'" % fi.RACK_STATE, rack_state)
        self.assertNotIn(fi.OLD_RACK_STATE.split('/')[-1], rack_state)


class DataMigrationOnInstall(Base):
    """The installer moves a schema 1 data folder when a schema 2 version takes it over, and only then."""

    def setUp(self):
        super().setUp()
        with patch.object(fr, 'DATA_SCHEMA', 1):   # a package as an earlier release built it
            _, self.pkg_old, _ = build_package(self.base, repo=self.repo, version='0.9.0')
        self.old, self.new = self.data / fi.OLD_RACK_STATE, self.data / fi.RACK_STATE

    def install_old(self):
        """Version 0.9.0 installed and used, with the data folder laid out as that version made it."""
        fi.install(self.pkg_old, self.root, self.data, python=sys.executable, processes=idle)
        self.assertEqual(fi.read_json(self.data / 'data.json')['data_schema'], 1)
        self.old.parent.mkdir()
        self.new.rename(self.old)
        (self.old / 'slots/preparation.json').write_text('{"fake": "kernel preparation"}')
        (self.old / 'windows/reel-slot18').mkdir()
        (self.old / 'windows/reel-slot18/preparation.json').write_text('{"fake": "window preparation"}')

    def test_update_moves_the_rack_state_once_and_the_earlier_version_is_then_refused(self):
        self.install_old()
        before = snapshot(self.old)
        state = fi.update(self.pkg_a, self.root, processes=idle)
        self.assertEqual((state['version'], state['previous']), ('1.0.0', '0.9.0'))
        self.assertEqual(snapshot(self.new), before)
        self.assertFalse(self.old.parent.exists())
        info = fi.read_json(self.data / 'data.json')
        self.assertEqual((info['data_schema'], info['last_version'], len(info['migrations'])), (2, '1.0.0', 1))
        self.assertEqual(info['migrations'][0]['moved'], fi.OLD_RACK_STATE)
        with self.assertRaisesRegex(fi.Refused, 'data schema 1.*schema 2.*older version must not open newer data'):
            fi.rollback(self.root, processes=idle)
        self.assertEqual(fi.status(self.root)['version'], '1.0.0')
        self.assertEqual(snapshot(self.new), before, 'the refused rollback moved nothing back')
        fi.update(self.pkg_b, self.root, processes=idle)   # a later update finds nothing left to move
        self.assertEqual(len(fi.read_json(self.data / 'data.json')['migrations']), 1)
        self.assertEqual(snapshot(self.new), before)

    def test_update_is_refused_while_both_places_exist_and_the_version_does_not_switch(self):
        self.install_old()
        (self.new / 'slots').mkdir(parents=True)
        before = snapshot(self.data)
        with self.assertRaisesRegex(fi.Refused, 'rack state in two places'):
            fi.update(self.pkg_a, self.root, processes=idle)
        self.assertEqual(fi.status(self.root)['version'], '0.9.0')
        self.assertEqual(snapshot(self.data), before)
        shutil.rmtree(self.new)   # the operator's decision: the old place is the current one
        self.assertEqual(fi.update(self.pkg_a, self.root, processes=idle)['version'], '1.0.0')
        self.assertTrue((self.new / 'slots/preparation.json').is_file())

    def test_install_onto_a_schema_1_data_folder_moves_it_before_making_folders(self):
        old = schema_1_data(self.data)
        before = snapshot(old)
        self.install()
        for d in fi.DATA_DIRS:
            self.assertTrue((self.data / d).is_dir(), d)
        self.assertEqual(snapshot(self.new), before)
        self.assertFalse(old.exists())
        info = fi.read_json(self.data / 'data.json')
        self.assertEqual((info['data_schema'], info['last_version'], len(info['migrations'])), (2, '1.0.0', 1))

    def test_a_package_that_fails_verification_leaves_a_schema_1_data_folder_alone(self):
        schema_1_data(self.data)
        before = snapshot(self.data)
        (self.pkg_a / 'farm/tools/farm_jobs.py').write_text('evil')
        with self.assertRaisesRegex(fi.Refused, 'failed verification'):
            self.install()
        self.assertEqual(snapshot(self.data), before)
        self.assertFalse(self.root.exists())

    def test_an_earlier_version_keeps_the_layout_it_reads(self):
        self.install_old()
        before = snapshot(self.data / fi.OLD_RACK_STATE)
        with patch.object(fr, 'DATA_SCHEMA', 1):
            _, pkg_old_b, _ = build_package(self.base, repo=self.repo, version='0.9.1')
        fi.update(pkg_old_b, self.root, processes=idle)
        self.assertEqual(snapshot(self.old), before)
        self.assertFalse(self.new.exists())
        self.assertNotIn('migrations', fi.read_json(self.data / 'data.json'))


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

    def test_launcher_moves_a_schema_1_rack_state_before_a_command_and_refuses_two_places(self):
        repo = make_repo(self.base / 'ran-probe')
        (repo / 'tools/imouse_farm_server.py').write_text(
            (repo / 'tools/imouse_farm_server.py').read_text(encoding='utf-8') +
            'if __name__ == "__main__":\n    open("server-ran.txt", "a").write("ran\\n")\n', encoding='utf-8')
        _, pkg, _ = build_package(self.base / 'ran-probe', repo=repo, version='2.0.0')
        fi.install(pkg, self.root, self.data, python=sys.executable, processes=idle)
        old, new, ran = self.data / fi.OLD_RACK_STATE, self.data / fi.RACK_STATE, self.data / 'server-ran.txt'
        # The data folder comes back in the earlier layout (an older backup restored over it, say).
        old.parent.mkdir()
        new.rename(old)
        (old / 'slots/preparation.json').write_text('{"fake": "kernel preparation"}')
        before = snapshot(old)
        run = powershell('-File', str(self.root / 'Farm.ps1'), 'server', cwd=self.base)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(snapshot(new), before)
        self.assertFalse(old.parent.exists())
        self.assertEqual(len(fi.read_json(self.data / 'data.json')['migrations']), 1)
        self.assertEqual(ran.read_text(), 'ran\n', 'the command ran, after the move')
        self.assertEqual(fr.verify(self.root / 'versions/2.0.0'), [], 'the move wrote nothing into the version folder')
        # Both places: the launcher refuses, names both, and starts nothing.
        (old / 'slots').mkdir(parents=True)
        (old / 'slots/preparation.json').write_text('{"fake": "another"}')
        both = snapshot(self.data)
        run = powershell('-File', str(self.root / 'Farm.ps1'), 'server', cwd=self.base)
        self.assertNotEqual(run.returncode, 0)
        said = ''.join(run.stderr.split())   # PowerShell wraps long error lines at the console width
        for need in ('rack state in two places', str(old), str(new), 'Nothing was moved', 'Nothing was started'):
            self.assertIn(''.join(need.split()), said, run.stderr[-800:])
        self.assertEqual(snapshot(self.data), both, 'nothing moved and the command did not run again')
        status = powershell('-File', str(self.root / 'Farm.ps1'), 'status', cwd=self.base)
        self.assertEqual(status.returncode, 0, 'status still answers, so the operator can see what is installed')


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
