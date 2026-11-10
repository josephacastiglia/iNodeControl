"""Synthetic files only: the release builder must not launch anything, read rack state or package it."""
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import farm_release as fr
from test_managed_symbols import fixture as symbol_pair   # a synthetic .dll/.pdb pair that belongs together

RACK = fr.RACK_DIR
FAKE_UDID = '0000' + 'A1B2-' + '0011223344556677'  # UDID-shaped, built at run time so this file holds none


def make_repo(base):
    """A tiny checkout with the farm's entry points, rack scripts and private rack state beside them."""
    repo = Path(base) / 'dev checkout'
    tools, rack = repo / 'tools', repo / RACK
    (tools / 'kernel-window').mkdir(parents=True)
    (rack / 'slots').mkdir(parents=True)
    (rack / 'windows/reel-slot18').mkdir(parents=True)
    hashed = ('imouse_farm_server.py', 'farm_jobs.py', 'farm_controls.json')
    (tools / 'imouse_farm_server.py').write_text(
        'import hashlib\nfrom pathlib import Path\nimport farm_jobs\nimport importlib\nLANES = ("farm_lane_runs",)\n'
        'def h(source):\n    return hashlib.sha256(b"".join((source / name).read_bytes() for name in ('
        + ', '.join(f'"{n}"' for n in hashed) + '))).hexdigest()\n'
        'DB = Path("output/farm-data/v2")  # cwd-relative\n', encoding='utf-8')
    (tools / 'farm_jobs.py').write_text('"""Mentions old_tool.py in a docstring only."""\nimport json\n', encoding='utf-8')
    (tools / 'old_tool.py').write_text('print("never packaged: only a docstring names it")\n', encoding='utf-8')
    (tools / 'farm_lane_runs.py').write_text('X = 1\n', encoding='utf-8')
    (tools / 'farm_controls.json').write_text('{"controls": []}', encoding='utf-8')
    (tools / 'farm_schedule_cli.py').write_text('from farm_paths import MAIN\nQUEUE = MAIN / "output/farm-schedule/queue.json"\n', encoding='utf-8')
    (tools / 'farm_paths.py').write_text('from pathlib import Path\nHERE = Path(__file__).resolve().parents[1]\nSUFFIX = ".worktrees"\n', encoding='utf-8')
    (tools / 'farm_schedule_runner.py').write_text('import farm_schedule_queue\n', encoding='utf-8')
    (tools / 'farm_schedule_queue.py').write_text('Q = 1\n', encoding='utf-8')
    (tools / 'farm_photos_cleanup.py').write_text('P = 1\n', encoding='utf-8')
    (tools / 'mdns_goodbye.py').write_text('PORT = "127.0.0.1:9916"\n', encoding='utf-8')
    (tools / 'requirements-farm.txt').write_text('# pins\nPillow==9.5.0\nnumpy==2.3.1\n', encoding='utf-8')
    (tools / 'test_farm_jobs.py').write_text('import farm_jobs\n', encoding='utf-8')
    (tools / 'kernel-window/Stop-ConsoleProcessGracefully.ps1').write_text('param($Pid)\n', encoding='utf-8')
    (rack / 'Start-Multiphone.ps1').write_text(
        "$taskDir=Join-Path $PSScriptRoot 'slots'\n& python (Join-Path $PSScriptRoot 'rack_kernels.py')\n"
        "# preparation.json lives beside this script\n$p=Get-Content (Join-Path $taskDir 'preparation.json')\n", encoding='utf-8')
    (rack / 'Stop-Multiphone.ps1').write_text("& (Join-Path $PSScriptRoot '..\\..\\tools\\kernel-window\\Stop-ConsoleProcessGracefully.ps1')\n", encoding='utf-8')
    for name in ('Release-Receiver.ps1', 'Restart-Receiver.ps1', 'Stop-Window.ps1'):
        (rack / name).write_text('# fine\n', encoding='utf-8')
    (rack / 'Start-Window.ps1').write_text("$py='C:\\Users\\someone\\AppData\\Local\\Programs\\Python\\Python311\\python.exe'\n", encoding='utf-8')
    (rack / 'rack_kernels.py').write_text('import json\nSLOTS = "phone-slots.json"\n', encoding='utf-8')
    for name in ('prepare_window.py', 'run_window.py', 'verify_window.py'):
        (rack / name).write_text('from pathlib import Path\nHERE = Path(__file__).resolve().parent\nW = HERE / "windows"\n', encoding='utf-8')
    (rack / 'one_tap.py').write_text('# dev-only supervised helper\n', encoding='utf-8')
    (rack / 'test_rack_kernels.py').write_text('import rack_kernels\n', encoding='utf-8')
    (rack / 'phone-slots.json').write_text('{"slots": {"18": {"board": "C24C"}}}', encoding='utf-8')
    (rack / 'preparation.json').write_text('{"kernel": "C:\\\\dev\\\\kernel.exe"}', encoding='utf-8')
    (rack / 'slots/preparation.json').write_text('{}', encoding='utf-8')
    (rack / 'windows/reel-slot18/preparation.json').write_text('{}', encoding='utf-8')
    # The receiver's source, with what a developer's checkout also holds there and must never ship.
    airplay = tools / 'airplay'
    for name, text in (('UPSTREAM.md', 'UxPlay, GPL 3. Changes: patches/0001-frame-pipe.patch\n'), ('build-receiver.sh', 'cmake -S . -B build-imouse\n'),
                       ('patches/0001-frame-pipe.patch', '--- /dev/null\n'), ('uxplay/LICENSE', 'GNU GENERAL PUBLIC LICENSE Version 3\n'),
                       ('uxplay/CMakeLists.txt', 'project(uxplay)\n'), ('uxplay/uxplay.cpp', 'int main() {}\n'),
                       ('uxplay/lib/CMakeLists.txt', '# lib\n'), ('uxplay/lib/playfair/LICENSE.md', 'GPL 3\n'),
                       ('uxplay/lib/llhttp/LICENSE-MIT', 'MIT\n'), ('uxplay/renderers/imouse_frame_pipe.h', '/* frame pipe */\n'),
                       ('uxplay/build-imouse/uxplay.exe', 'build output'), ('msys64/ucrt64/bin/gcc.exe', 'toolchain'),
                       ('uxplay-source.tar.gz', 'download')):
        (airplay / name).parent.mkdir(parents=True, exist_ok=True)
        (airplay / name).write_text(text, encoding='utf-8')
    return repo


def make_builds(base):
    base = Path(base)
    kernel, console, runtime = base / 'kernel build', base / 'console build', base / 'receiver runtime'
    for seed, (folder, names, frameworks) in enumerate(((kernel, fr.KERNEL_FILES, ['Microsoft.NETCore.App']),
                                                        (console, fr.CONSOLE_FILES, ['Microsoft.NETCore.App', 'Microsoft.WindowsDesktop.App'])), 1):
        (folder / 'data').mkdir(parents=True)
        dll, pdb = symbol_pair(seed)
        for n in names:
            (folder / n).write_bytes(dll if n.endswith('.dll') else pdb if n.endswith('.pdb') else b'binary ' + n.encode())
        config = next(n for n in names if n.endswith('.runtimeconfig.json'))
        (folder / config).write_text(json.dumps({'runtimeOptions': {'frameworks': [{'name': f, 'version': '8.0.0'} for f in frameworks]}}))
        (folder / 'data/devices.json').write_text('{"private": "bindings"}')  # never packaged
    (runtime / 'bin').mkdir(parents=True)
    for name in fr.RECEIVER_RUNTIME_REQUIRED:
        (runtime / name).parent.mkdir(parents=True, exist_ok=True)
        (runtime / name).write_bytes(b'runtime ' + name.encode())
    (runtime / 'bin/libgstreamer-1.0-0.dll').write_bytes(b'gst')
    receiver = base / 'receiver build/uxplay.exe'
    receiver.parent.mkdir()
    receiver.write_bytes(b'uxplay')
    return kernel, console, receiver, runtime


def build_package(base, repo=None, version='t1', out=None, **kw):
    repo = repo or make_repo(base)
    kernel, console, receiver, runtime = make_builds(Path(base) / f'builds-{version}')
    out = out or Path(base) / 'packages' / f'farm-{version}'
    with patch.object(fr, 'git_identity', return_value={'head': 'f' * 40, 'tracked_changes': False}):
        return fr.build(repo, out, kernel, console, receiver, runtime, version=version, **kw), out, repo


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)


class FarmFileSet(Base):
    def test_closure_follows_imports_named_files_and_importlib_strings(self):
        files, private = fr.farm_files(make_repo(self.base))
        names = {n[5:] for n in files}
        for need in ('tools/farm_jobs.py', 'tools/farm_lane_runs.py', 'tools/farm_controls.json', 'tools/farm_paths.py',
                     'tools/farm_schedule_queue.py', f'{RACK}/rack_kernels.py', 'tools/kernel-window/Stop-ConsoleProcessGracefully.ps1'):
            self.assertIn(need, names)
        self.assertNotIn('tools/old_tool.py', names, 'a docstring mention must not pull a file in')
        self.assertNotIn('tools/test_farm_jobs.py', names)
        self.assertNotIn(f'{RACK}/test_rack_kernels.py', names)
        self.assertNotIn(f'{RACK}/one_tap.py', names, 'dev-only helpers stay out')
        self.assertIn(f'{RACK}/phone-slots.json', private)
        self.assertFalse(any(fr.is_private(n) for n in files))

    def test_private_patterns(self):
        for name in (f'farm/{RACK}/slots/preparation.json', f'farm/{RACK}/windows/x/backend/runs.db', 'farm/tools/x.log',
                     f'farm/{RACK}/rack-b-boards.json', 'kernel/data/devices.json', 'farm/tools/IMService.json', 'farm/a/capture.png'):
            self.assertTrue(fr.is_private(name), name)
        for name in ('farm/tools/farm_jobs.py', 'farm/tools/farm_reel_controls.json', 'kernel/iMouse2.Kernel.dll'):
            self.assertFalse(fr.is_private(name), name)

    def test_safe_names(self):
        for bad in ('../x', 'a/../b', 'C:/x', 'a\\b', '/abs', 'a/CON', 'a/b.', ''):
            with self.assertRaises(ValueError):
                fr.safe_name(bad)


class Build(Base):
    def test_build_verifies_and_excludes_private_state(self):
        with patch('subprocess.Popen', side_effect=AssertionError('no process may start')):
            manifest, out, _ = build_package(self.base)
        self.assertEqual(fr.verify(out), [])
        self.assertEqual(manifest['version'], 't1')
        names = set(manifest['files'])
        self.assertIn('kernel/iMouse2.Kernel.exe', names)
        self.assertIn('receiver/runtime/libexec/gstreamer-1.0/gst-plugin-scanner.exe', names)
        self.assertIn('install/Preflight-Farm.ps1', names)
        self.assertNotIn('kernel/data/devices.json', names)
        self.assertFalse([n for n in names if 'preparation' in n or 'phone-slots' in n or '/windows/' in n])
        self.assertEqual(manifest['components']['farm']['pins'], {'Pillow': '9.5.0', 'numpy': '2.3.1'})
        self.assertEqual(manifest['components']['kernel']['sha256'], manifest['files']['kernel/iMouse2.Kernel.dll']['sha256'])
        self.assertFalse(manifest['components']['receiver']['redistribution_cleared'])
        self.assertFalse(manifest['commands']['start-rack']['ready'])
        self.assertTrue(manifest['commands']['server']['ready'])
        self.assertFalse(out.with_name(out.name + '.partial').exists())

    def test_the_receiver_ships_with_its_licence_notice_and_source(self):
        manifest, out, repo = build_package(self.base)
        names = set(manifest['files'])
        for need in fr.RECEIVER_SOURCE_REQUIRED + ('receiver/source/patches/0001-frame-pipe.patch',):
            self.assertIn(need, names)
        self.assertEqual((out / 'receiver/LICENSE').read_bytes(), (repo / 'tools/airplay/uxplay/LICENSE').read_bytes())
        self.assertEqual((out / 'receiver/NOTICE.md').read_bytes(), (repo / 'tools/airplay/UPSTREAM.md').read_bytes())
        self.assertFalse([n for n in names if 'build-imouse' in n or 'msys64' in n or n.endswith('.tar.gz')],
                         'build output, the toolchain and downloads are not source')
        receiver = manifest['components']['receiver']
        self.assertEqual((receiver['licence'], receiver['notice'], receiver['source']), ('receiver/LICENSE', 'receiver/NOTICE.md', 'receiver/source'))
        self.assertEqual(receiver['sha256'], manifest['files']['receiver/uxplay.exe']['sha256'])

    def test_a_receiver_without_its_licence_source_or_a_named_patch_refuses_the_build(self):
        for gone in ('uxplay/LICENSE', 'UPSTREAM.md', 'uxplay/uxplay.cpp', 'build-receiver.sh', 'patches/0001-frame-pipe.patch'):
            base = self.base / gone.replace('/', '-')
            repo = make_repo(base)
            (repo / 'tools/airplay' / gone).unlink()
            with self.assertRaisesRegex(ValueError, 'licence, notice and source must ship'):
                build_package(base, repo=repo)
            self.assertFalse((base / 'packages').exists(), 'nothing is written before the refusal')

    def test_a_pdb_that_is_not_its_dlls_refuses_the_build(self):
        repo = make_repo(self.base)
        kernel, console, receiver, runtime = make_builds(self.base / 'b')
        (console / 'iMouse2.pdb').write_bytes((kernel / 'iMouse2.Kernel.pdb').read_bytes())   # well formed, another build's
        with self.assertRaisesRegex(ValueError, r'console: iMouse2\.pdb does not belong to iMouse2\.dll'):
            fr.build(repo, self.base / 'p1', kernel, console, receiver, runtime, version='x')
        kernel, console, receiver, runtime = make_builds(self.base / 'c')
        (kernel / 'iMouse2.Kernel.pdb').write_bytes(b'not a pdb')
        with self.assertRaisesRegex(ValueError, 'kernel: iMouse2.Kernel.pdb does not belong'):
            fr.build(repo, self.base / 'p2', kernel, console, receiver, runtime, version='x')
        self.assertFalse((self.base / 'p1').exists() or (self.base / 'p2').exists())

    def test_zip_is_named_after_the_whole_folder_and_holds_the_package(self):
        import zipfile
        manifest, out, _ = build_package(self.base, version='2026.11.05-abc', out=self.base / 'packages/farm-2026.11.05-abc', make_zip=True)
        archive = self.base / 'packages/farm-2026.11.05-abc.zip'
        self.assertTrue(archive.is_file(), sorted(p.name for p in archive.parent.iterdir()))
        with zipfile.ZipFile(archive) as z:
            self.assertIsNone(z.testzip())
            self.assertEqual(set(z.namelist()), set(manifest['files']) | {'release.json'})

    def test_existing_output_and_checkout_output_rules(self):
        _, out, repo = build_package(self.base)
        kernel, console, receiver, runtime = make_builds(self.base / 'again')
        with self.assertRaisesRegex(ValueError, 'never overwritten'):
            fr.build(repo, out, kernel, console, receiver, runtime, version='t2')
        with self.assertRaisesRegex(ValueError, 'under output/'):
            fr.build(repo, repo / 'tools/pkg', kernel, console, receiver, runtime, version='t2')

    def test_private_content_is_refused_before_anything_is_written(self):
        repo = make_repo(self.base)
        (repo / 'tools/farm_jobs.py').write_text(f'DEVICE = "{FAKE_UDID}"\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'device id'):
            build_package(self.base, repo=repo)
        self.assertFalse((self.base / 'packages').exists())

    def test_withheld_value_is_refused(self):
        repo = make_repo(self.base)
        (repo / 'tools/farm_lane_runs.py').write_text('ACCOUNT = "withheldvalue1234"\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'withheld value'):
            build_package(self.base, repo=repo, tokens=['WithheldValue1234'])

    def test_account_handles_refuse_the_build_unless_review_only(self):
        repo = make_repo(self.base)
        (repo / 'tools/farm_lane_runs.py').write_text('START = "on @somelabel\'s profile"\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'account handle .* farm/tools/farm_lane_runs.py'):
            build_package(self.base, repo=repo, accounts=['SomeLabel'])
        self.assertFalse((self.base / 'packages').exists(), 'nothing is written before the refusal')
        manifest, _, _ = build_package(self.base / 'review', repo=repo, accounts=['SomeLabel'], strict_privacy=False)
        self.assertEqual(manifest['account_labels_in'], ['farm/tools/farm_lane_runs.py'])
        manifest, _, _ = build_package(self.base / 'clean', accounts=['SomeLabel'])
        self.assertEqual(manifest['account_labels_in'], [])

    def test_wrong_framework_unpinned_requirement_and_missing_hashed_file(self):
        repo = make_repo(self.base)
        kernel, console, receiver, runtime = make_builds(self.base / 'b')
        (console / 'iMouse2.runtimeconfig.json').write_text(json.dumps({'runtimeOptions': {'framework': {'name': 'Microsoft.NETCore.App', 'version': '8.0.0'}}}))
        with self.assertRaisesRegex(ValueError, 'WindowsDesktop'):
            fr.build(repo, self.base / 'p1', kernel, console, receiver, runtime, version='x')
        kernel, console, receiver, runtime = make_builds(self.base / 'c')
        (repo / 'tools/requirements-farm.txt').write_text('Pillow>=9\n')
        with self.assertRaisesRegex(ValueError, 'not pinned'):
            fr.build(repo, self.base / 'p2', kernel, console, receiver, runtime, version='x')
        (repo / 'tools/requirements-farm.txt').write_text('Pillow==9.5.0\n')
        (repo / 'tools/farm_controls.json').unlink()
        with self.assertRaisesRegex(ValueError, 'source-hash files missing'):
            fr.build(repo, self.base / 'p3', kernel, console, receiver, runtime, version='x')

    def test_a_runtime_missing_any_file_the_kernel_requires_refuses_the_build(self):
        repo = make_repo(self.base)
        for n, missing in enumerate(('libexec/gstreamer-1.0/gst-plugin-scanner.exe', 'lib/gstreamer-1.0/libgstplayback.dll')):
            kernel, console, receiver, runtime = make_builds(self.base / f'b{n}')
            (runtime / missing).unlink()
            with self.assertRaisesRegex(ValueError, 'receiver runtime: missing ' + missing):
                fr.build(repo, self.base / f'p{n}', kernel, console, receiver, runtime, version='x')

    def test_the_required_runtime_files_are_the_kernels_list(self):
        source = (fr.REPO / 'src/iMouse.Kernel/ReceiverRuntime.cs').read_text(encoding='utf-8')
        block = re.search(r'RequiredFiles\s*=\s*\[(.*?)\];', source, re.S).group(1)
        self.assertEqual(tuple(re.findall(r'"([^"]+)"', block)), fr.RECEIVER_RUNTIME_REQUIRED)

    def test_invalid_version(self):
        repo = make_repo(self.base)
        kernel, console, receiver, runtime = make_builds(self.base / 'b')
        with self.assertRaisesRegex(ValueError, 'invalid version'):
            fr.build(repo, self.base / 'p', kernel, console, receiver, runtime, version='../evil')


class Verify(Base):
    def test_changed_missing_unrecorded(self):
        _, out, _ = build_package(self.base)
        (out / 'farm/tools/farm_jobs.py').write_text('changed')
        (out / 'console/iMouse2.pdb').unlink()
        (out / 'console/startup-state.json').write_text('{}')
        issues = fr.verify(out)
        self.assertIn('changed: farm/tools/farm_jobs.py', issues)
        self.assertIn('missing: console/iMouse2.pdb', issues)
        self.assertIn('unrecorded: console/startup-state.json', issues)
        relaxed = fr.verify(out, allow_unrecorded=True)
        self.assertNotIn('unrecorded: console/startup-state.json', relaxed)
        self.assertIn('changed: farm/tools/farm_jobs.py', relaxed)

    def test_a_package_without_the_receivers_licence_fails_verification(self):
        _, out, _ = build_package(self.base)
        manifest = json.loads((out / 'release.json').read_text())
        for name in ('receiver/LICENSE', 'receiver/source/uxplay/uxplay.cpp'):
            manifest['files'].pop(name)
            (out / name).unlink()
        (out / 'release.json').write_text(json.dumps(manifest))
        issues = fr.verify(out)
        self.assertIn('required file absent: receiver/LICENSE', issues)
        self.assertIn('required file absent: receiver/source/uxplay/uxplay.cpp', issues)

    def test_manifest_tampering(self):
        _, out, _ = build_package(self.base)
        manifest = json.loads((out / 'release.json').read_text())
        manifest['files']['farm/../escape'] = {'sha256': '0' * 64, 'bytes': 1}
        (out / 'release.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            fr.verify(out)
        manifest['files'].pop('farm/../escape')
        manifest['kind'] = 'other'
        (out / 'release.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'not a Marketing Farm'):
            fr.verify(out)


class Lint(Base):
    def test_rules_find_dev_paths_and_block_commands(self):
        files, _ = fr.farm_files(make_repo(self.base))
        findings = fr.lint(files)
        rules = {(f['file'].split('/')[-1], f['rule']) for f in fr.blockers(findings)}
        self.assertIn(('Start-Window.ps1', 'absolute user path'), rules)
        self.assertIn(('Start-Window.ps1', 'pinned interpreter path'), rules)
        self.assertIn(('farm_paths.py', 'lane worktree discovery (.worktrees)'), rules)
        self.assertNotIn(('farm_schedule_cli.py', 'state under the code folder (output/)'), rules, 'MAIN is the data-aware state root')
        self.assertIn(('prepare_window.py', 'state beside the rack scripts (__file__)'), rules)
        self.assertIn(('Start-Multiphone.ps1', 'state beside the rack scripts ($PSScriptRoot)'), rules)
        self.assertIn(('run_window.py', 'state beside the rack scripts (__file__)'), rules)
        infos = {(f['file'].split('/')[-1], f['rule']) for f in findings if f['level'] == 'info'}
        self.assertIn(('mdns_goodbye.py', 'hard-coded kernel port'), infos)
        self.assertTrue(any(r.startswith('cwd-relative') for _, r in infos))
        ready = fr.command_readiness(fr.COMMANDS, findings, files)
        self.assertFalse(ready['start-rack']['ready'])
        self.assertIn(f'farm/{RACK}/Start-Multiphone.ps1', ready['start-rack']['blocked_by'])
        self.assertFalse(ready['schedule']['ready'], 'farm_paths blocks the schedule CLI')
        self.assertTrue(ready['server']['ready'])

    def test_dev_fallback_marker_and_docstrings_do_not_block(self):
        text = ('def f():\n    """Lives in C:\\Users\\x\\Desktop\\Claude Code\n    over lines."""\n'
                'A = ".worktrees"  # release-lint: dev-fallback\n')
        findings = fr.lint_text('farm/tools/x.py', text)
        self.assertTrue(findings)
        self.assertEqual(fr.blockers(findings), [])
        self.assertTrue(any(f['level'] == 'info' and 'dev-fallback' in f['rule'] for f in findings))

    def test_comment_lines_do_not_block(self):
        findings = fr.lint_text('farm/x.ps1', "# C:\\Users\\someone\\Desktop\\Claude Code\\notes\n$a=1\n")
        self.assertTrue(findings and all(f['comment'] for f in findings))
        self.assertEqual(fr.blockers(findings), [])


class ReceiverSourceRecord(unittest.TestCase):
    """tools/airplay: the receiver's source is upstream UxPlay plus the recorded patches (UPSTREAM.md)."""
    AIRPLAY = fr.REPO / 'tools' / 'airplay'

    def test_every_patch_describes_the_tracked_source(self):
        patches = sorted((self.AIRPLAY / 'patches').glob('*.patch'))
        self.assertEqual(len(patches), 3)
        for patch in patches:
            text = patch.read_bytes().decode('utf-8')
            self.assertNotIn('\r', text, f'{patch.name} must keep LF line endings to apply to upstream')
            target = re.search(r'^\+\+\+ b/(\S+)', text, re.M).group(1)
            tracked = (self.AIRPLAY / 'uxplay' / target).read_bytes().decode('utf-8').replace('\r\n', '\n')
            hunks = re.split(r'^@@ .* @@.*\n', text, flags=re.M)[1:]
            self.assertTrue(hunks, patch.name)
            for hunk in hunks:
                lines = [l for l in hunk.split('\n') if l]
                self.assertFalse([l for l in lines if l.startswith('-')], f'{patch.name} only adds lines')
                after = '\n'.join(l[1:] for l in lines if l[0] in ' +')
                self.assertIn(after, tracked, f'{patch.name}: {target} no longer holds this change')

    def test_the_record_names_upstream_the_patches_and_the_licences(self):
        record = (self.AIRPLAY / 'UPSTREAM.md').read_text(encoding='utf-8')
        for need in ('github.com/FDH2/UxPlay', '44024fe', 'General Public License', *[p.name for p in (self.AIRPLAY / 'patches').glob('*.patch')]):
            self.assertIn(need, record)
        for licence in ('uxplay/LICENSE', 'uxplay/lib/playfair/LICENSE.md', 'uxplay/lib/llhttp/LICENSE-MIT'):
            self.assertTrue((self.AIRPLAY / licence).is_file(), licence)
            self.assertIn(licence, record)
        self.assertEqual(fr.scan_private_content(self.AIRPLAY / 'UPSTREAM.md'), [], 'the notice ships in every package')

    def test_the_build_script_does_not_tune_the_binary_to_the_build_pc(self):
        script = (self.AIRPLAY / 'build-receiver.sh').read_text(encoding='utf-8')
        self.assertIn('-DNO_MARCH_NATIVE=ON', script)
        self.assertIn('NOT NO_MARCH_NATIVE', (self.AIRPLAY / 'uxplay/lib/CMakeLists.txt').read_text(encoding='utf-8'),
                      'upstream still guards -march=native with this option')


class OperatorInstructions(unittest.TestCase):
    def test_every_tool_the_shipped_scripts_and_the_guide_name_is_in_the_package(self):
        # An operator on an installed PC has the package and nothing else: an instruction that names a
        # tools/ file must name one that ships.
        files, _ = fr.farm_files(fr.REPO)
        shipped = {n[len('farm/'):] for n in files}
        for doc in ('tools/release/Preflight-Farm.ps1', 'tools/release/Farm.ps1', 'tools/release/Install-Farm.ps1', 'docs/INSTALL-FARM.md'):
            text = (fr.REPO / doc).read_text(encoding='utf-8')
            for path in re.findall(r'(?<![\w.-])(tools[\\/][\w./\\-]+\.(?:ps1|py|txt|json))', text):
                self.assertIn(path.replace('\\', '/'), shipped, f'{doc} names {path}, which a package does not contain')


class ThisCheckout(unittest.TestCase):
    def test_no_packaged_file_reads_state_from_the_code_folder(self):
        # The rehearsal's 'every launcher command ready' check, without building a package: one blocker line
        # in a file a command pulls in makes Farm.ps1 refuse that command on an installed PC.
        files, _ = fr.farm_files(fr.REPO)
        findings = fr.lint(files)
        self.assertEqual([f"{f['file']}:{f['line']} {f['rule']}" for f in fr.blockers(findings)], [])
        self.assertEqual([c for c, s in fr.command_readiness(fr.COMMANDS, findings, files).items() if not s['ready']], [])


if __name__ == '__main__':
    unittest.main()
