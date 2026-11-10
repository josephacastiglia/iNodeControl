"""farm_paths: unset IMOUSE_FARM_DATA keeps today's paths exactly; set, every state path is in the data folder."""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent


def load_paths(module_file, env):
    """Import a farm_paths copy in a fresh interpreter and return its paths as strings."""
    code = ('import sys, json; sys.path.insert(0, sys.argv[1]); import farm_paths as p; '
            'print(json.dumps({k: str(getattr(p, k)) for k in ("HERE", "MAIN", "ARCHIVE", "STATE", "RACK")} | '
            '{"state_x": str(p.rack_state(sys.argv[2])), "run_x": str(p.run_root(sys.argv[2])), '
            '"kernel": str(p.installed("kernel", sys.argv[2]))}))')
    clean = {k: v for k, v in os.environ.items() if not k.startswith('IMOUSE_FARM_')}
    out = subprocess.run([sys.executable, '-E', '-c', code, str(Path(module_file).parent), 'X:/default'],
                         capture_output=True, text=True, timeout=60, env=clean | env, check=True)
    import json
    return json.loads(out.stdout)


def old_paths(here):
    """The 27 Oct definitions, for comparison; the rack folder is rack/ since 9 Nov."""
    SUFFIX = '.worktrees'
    MAIN = here.parent.with_name(here.parent.name[:-len(SUFFIX)]) if here.parent.name.endswith(SUFFIX) else here
    return {'MAIN': str(MAIN), 'ARCHIVE': str(MAIN.parent / 'iMouseXP-2.0-evidence-archive'),
            'RACK': str(MAIN / 'rack/slots')}


class FarmPaths(unittest.TestCase):
    def layout(self, base, lane):
        tools = (base / 'proj.worktrees' / 'lane' / 'tools') if lane else (base / 'proj' / 'tools')
        tools.mkdir(parents=True)
        (tools / 'farm_paths.py').write_bytes((TOOLS / 'farm_paths.py').read_bytes())
        return tools / 'farm_paths.py'

    def test_unset_is_exactly_todays_paths_in_main_folder_and_lane(self):
        with tempfile.TemporaryDirectory() as tmp:
            for lane in (False, True):
                module = self.layout(Path(tmp) / str(lane), lane)
                got = load_paths(module, {})
                want = old_paths(module.resolve().parents[1])
                for key in want:
                    self.assertEqual(got[key], want[key], (lane, key))
                self.assertEqual(got['state_x'], str(Path('X:/default')))
                self.assertEqual(got['run_x'], str(Path('X:/default')))
                self.assertEqual(got['kernel'], str(Path('X:/default')))
            self.assertTrue(got['MAIN'].endswith('proj'), 'a lane finds the main folder')

    def test_unset_ignores_installed_component_variables(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.layout(Path(tmp), True)
            got = load_paths(module, {'IMOUSE_FARM_KERNEL': 'Y:/installed/kernel.exe'})
            self.assertEqual(got['kernel'], str(Path('X:/default')))

    def test_set_puts_every_state_path_in_the_data_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = self.layout(Path(tmp), True)
            data = (Path(tmp) / 'data folder').resolve()
            got = load_paths(module, {'IMOUSE_FARM_DATA': str(data), 'IMOUSE_FARM_KERNEL': 'Y:/v1/kernel/k.exe'})
            self.assertEqual(got['MAIN'], str(data))
            self.assertEqual(got['ARCHIVE'], str(data / 'evidence-archive'))
            self.assertEqual(got['STATE'], str(data / 'analysis/farm-multiphone-20261020'))
            self.assertEqual(got['RACK'], str(data / 'analysis/farm-multiphone-20261020/slots'))
            self.assertEqual(got['state_x'], got['STATE'])
            self.assertEqual(got['run_x'], str(data))
            self.assertEqual(got['kernel'], str(Path('Y:/v1/kernel/k.exe')))
            self.assertNotIn('proj', got['MAIN'] + got['ARCHIVE'])

    def test_lan_address_unset_configured_and_refused(self):
        code = ('import sys; sys.path.insert(0, sys.argv[1]); import farm_paths as p\n'
                'try: print(p.lan_address("10.0.0.9"))\nexcept SystemExit as e: print("REFUSED", e)\n')
        with tempfile.TemporaryDirectory() as tmp:
            module = self.layout(Path(tmp), True)
            data = Path(tmp) / 'data'
            data.mkdir()

            def run(env):
                clean = {k: v for k, v in os.environ.items() if not k.startswith('IMOUSE_FARM_')}
                return subprocess.run([sys.executable, '-E', '-c', code, str(module.parent)], capture_output=True, text=True,
                                      timeout=60, env=clean | env, check=True).stdout.strip()
            self.assertEqual(run({}), '10.0.0.9', 'a checkout keeps its address')
            (data / 'machine.json').write_text('{"lanAddress": "192.168.50.2"}')
            self.assertEqual(run({'IMOUSE_FARM_DATA': str(data)}), '192.168.50.2')
            self.assertEqual(run({'IMOUSE_FARM_DATA': str(data), 'IMOUSE_FARM_LAN': '192.168.60.3'}), '192.168.60.3')
            (data / 'machine.json').write_text('{"lanAddress": "192.168.50"}')
            with self.assertRaises(subprocess.CalledProcessError):
                run({'IMOUSE_FARM_DATA': str(data)})
            (data / 'machine.json').unlink()
            out = run({'IMOUSE_FARM_DATA': str(data)})
            self.assertTrue(out.startswith('REFUSED') or out.count('.') == 3, out)

    def test_account_label_from_private_data(self):
        code = 'import sys; sys.path.insert(0, sys.argv[1]); import farm_paths as p; print(repr(p.account_label()))'
        with tempfile.TemporaryDirectory() as tmp:
            module = self.layout(Path(tmp), True)
            data = Path(tmp) / 'data'
            clean = {k: v for k, v in os.environ.items() if not k.startswith('IMOUSE_FARM_')}
            run = lambda: subprocess.run([sys.executable, '-E', '-c', code, str(module.parent)], capture_output=True, text=True,
                                         timeout=60, env=clean | {'IMOUSE_FARM_DATA': str(data)}, check=True).stdout.strip()
            self.assertEqual(run(), "''", 'no private file: no label, so no account check can pass')
            (data / 'evidence-archive/privacy').mkdir(parents=True)
            (data / 'evidence-archive/privacy/farm-accounts.json').write_text('{"v1CandidateAccount": "label.one"}')
            self.assertEqual(run(), "'label.one'")

    def test_data_layout_matches_the_installer(self):
        import farm_install
        self.assertIn('analysis/farm-multiphone-20261020/slots', farm_install.DATA_DIRS)
        self.assertIn('evidence-archive/privacy', farm_install.DATA_DIRS)


if __name__ == '__main__':
    unittest.main()
