"""Rack scripts keep state beside themselves in a checkout (IMOUSE_FARM_DATA unset: today's paths) and in the
data folder when installed. Imports each script in a fresh interpreter; nothing runs, no phone, no socket."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCRIPTS = ('run_window', 'verify_window', 'relaunch_check', 'auto_connect', 'card_survey', 'pointer_identify',
           'pointer_measure', 'rack_kernels', 'rack_recovery', 'prepare_window', 'prepare_rack_a', 'prepare_rack_b')


def probe(env, extra_argv=()):
    script = (
        'import sys, json, importlib\n'
        f'sys.path.insert(0, {str(HERE)!r})\n'
        f'sys.argv = ["probe", *{list(extra_argv)!r}]\n'
        'out = {}\n'
        f'for name in {list(SCRIPTS)!r}:\n'
        '    m = importlib.import_module(name)\n'
        '    out[name] = {k: str(getattr(m, k)) for k in ("HERE", "ROOT", "STATE", "RUNS", "OUT", "KERNEL", "FULL", "PC_LAN") if hasattr(m, k)}\n'
        'print(json.dumps(out))\n')
    clean = {k: v for k, v in os.environ.items() if not k.startswith('IMOUSE_FARM_')}
    run = subprocess.run([sys.executable, '-E', '-c', script], capture_output=True, text=True, timeout=120, env=clean | env, cwd=HERE)
    if run.returncode:
        raise AssertionError(run.stderr[-2000:])
    return json.loads(run.stdout.strip().splitlines()[-1])


class RackState(unittest.TestCase):
    def test_unset_keeps_todays_paths(self):
        got = probe({})
        for name, paths in got.items():
            self.assertEqual(paths['STATE'], str(HERE), name)
            if 'RUNS' in paths:
                self.assertEqual(paths['RUNS'], str(ROOT), name)
        self.assertEqual(got['prepare_rack_b']['OUT'], str(HERE / 'slots'))
        self.assertEqual(got['prepare_rack_b']['KERNEL'], str(ROOT / 'output/multiphone-kernel-20261029/iMouse2.Kernel.exe'))
        self.assertEqual(got['prepare_rack_a']['FULL'], str(ROOT.parent / 'iMouseXP-2.0/analysis/full-rack-config'))
        self.assertEqual(got['prepare_rack_a']['OUT'], str(HERE / 'slots'))
        self.assertEqual(got['prepare_window']['PC_LAN'], '192.168.4.26')

    def test_installed_state_runs_and_components_come_from_the_data_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp).resolve()
            kernel = data / 'versions/v1/kernel/iMouse2.Kernel.exe'
            got = probe({'IMOUSE_FARM_DATA': str(data), 'IMOUSE_FARM_KERNEL': str(kernel), 'IMOUSE_FARM_LAN': '192.168.77.5'},
                        ['--source', str(data / 'full-rack')])
            self.assertEqual(got['prepare_window']['PC_LAN'], '192.168.77.5')
            state = data / 'analysis' / 'farm-multiphone-20261020'
            for name, paths in got.items():
                self.assertEqual(paths['STATE'], str(state), name)
                if 'RUNS' in paths:
                    self.assertEqual(paths['RUNS'], str(data), name)
            self.assertEqual(got['prepare_rack_b']['OUT'], str(state / 'slots'))
            self.assertEqual(got['prepare_rack_b']['KERNEL'], str(kernel))
            self.assertEqual(got['prepare_rack_a']['FULL'], str(data / 'full-rack'))

    def test_installed_without_source_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(AssertionError, 'pass --source'):
                probe({'IMOUSE_FARM_DATA': tmp, 'IMOUSE_FARM_LAN': '192.168.77.5'})


if __name__ == '__main__':
    unittest.main()
