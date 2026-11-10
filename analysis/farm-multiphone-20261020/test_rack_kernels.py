"""Offline tests for rack_kernels.py: the kernel's one folder, rekernel, and the start/stop checks.
No kernel, receiver, socket or phone; placeholder phone IDs only.

  python -m unittest test_rack_kernels    (from this folder)
"""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rack_kernels as rk  # noqa: E402

BOARDS = ['C24C', 'C214', '3848', 'EE14', 'CD51']
DATA_FILES = ('devices.json', 'receivers.json', 'pointer-calibration.json')


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Fixture:
    """A preparation for five boards with its run data, and a kernel build to move it to."""

    def __init__(self, root):
        self.root = Path(root)
        source = self.root / 'output/candidate-runs/multiphone-racks-ab-bound-x/data'; source.mkdir(parents=True)
        port = {b: 7110 + 10 * i for i, b in enumerate(BOARDS)}
        rows = {
            'devices.json': [dict(deviceid=f'pending-{b}', pid=b, uid=b, name=f'Board {b}') for b in BOARDS],
            'receivers.json': [dict(DeviceId=f'pending-{b}', BoardPid=b, Name=f'iMouse2-{b}', Pipe=f'iMouse2-{b}-frames', Port=port[b],
                                    Mac=f'02:49:4D:32:{b[:2]}:{b[2:]}') for b in BOARDS],
            'pointer-calibration.json': [dict(Pid=b, Width=500, Height=1080) for b in BOARDS]}
        for name, r in rows.items(): (source / name).write_text(json.dumps(r), encoding='utf-8')
        self.kernel = self.root / 'output/rack-kernel/iMouse2.Kernel.exe'; self.kernel.parent.mkdir(parents=True)
        self.kernel.write_bytes(b'exe'); self.kernel.with_suffix('.dll').write_bytes(b'dll')
        csv = ','.join(BOARDS)
        self.base = dict(runDirectory=str(source.parent), kernel='old.exe', kernelSha256='0' * 64,
                         arguments=['http://127.0.0.1:9916/api/', '--data-dir', str(source), '--input-pid', csv,
                                    '--receivers', str(source / 'receivers.json'), '--receiver', 'uxplay.exe',
                                    '--receiver-runtime', 'runtime', '--hold-receivers', csv],
                         held=BOARDS, boards=BOARDS, inputEnabled=BOARDS,
                         receivers=[dict(board=b, name=f'iMouse2-{b}', port=port[b]) for b in BOARDS],
                         slots={'C24C': 18, 'C214': 20},
                         dataSha256={n: sha(source / n) for n in DATA_FILES})
        self.base_path = self.root / 'preparation.json'
        self.base_path.write_text(json.dumps(self.base), encoding='utf-8')


class FolderTests(unittest.TestCase):
    def test_the_kernel_has_one_folder(self):
        self.assertEqual(rk.kernel_folder(), rk.STATE / 'slots')


class RekernelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.f = Fixture(self.tmp.name)

    def tearDown(self): self.tmp.cleanup()

    def test_rekernel_changes_only_the_kernel(self):
        out = self.f.root / 'slots'; out.mkdir()
        prep = rk.rekernel(self.f.base_path, self.f.kernel, out)
        skip = ('kernel', 'kernelSha256', 'rekernelFrom')
        self.assertEqual({k: v for k, v in prep.items() if k not in skip}, {k: v for k, v in self.f.base.items() if k not in skip})
        self.assertEqual(prep['kernelSha256'], sha(self.f.kernel.with_suffix('.dll')))
        self.assertEqual(prep['rekernelFrom']['kernelSha256'], '0' * 64)
        with self.assertRaises(SystemExit): rk.rekernel(self.f.base_path, self.f.kernel, out)   # never overwrites

    def test_rekernel_refuses_changed_base_data(self):
        data = Path(self.f.base['runDirectory']) / 'data' / 'receivers.json'
        data.write_text(data.read_text(encoding='utf-8') + ' ', encoding='utf-8')
        out = self.f.root / 'slots'; out.mkdir()
        with self.assertRaises(SystemExit): rk.rekernel(self.f.base_path, self.f.kernel, out)
        self.assertFalse((out / 'preparation.json').exists())


def kernel(pid, port, data='x'):
    return dict(Name='iMouse2.Kernel.exe', ProcessId=pid, CommandLine=f'"iMouse2.Kernel.exe" "http://127.0.0.1:{port}/api/" "--data-dir" "{data}"')


def uxplay(pid, name, port):
    return dict(Name='uxplay.exe', ProcessId=pid, CommandLine=f'"uxplay.exe" -n {name} -nh -s 500x1080 -p {port} -m 02:00:00:00:00:01')


FARM = [dict(Name='python.exe', ProcessId=9, CommandLine='python tools/imouse_farm_server.py'), dict(Name='iMouse2.exe', ProcessId=8)]


class CheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); f = Fixture(cls.tmp.name)
        cls.rack = f.base
        # A sandbox as the off-rack trials write it: its own port, data folder, names and receiver ports.
        cls.box = dict(sandbox=True, arguments=['http://127.0.0.1:9936/api/', '--data-dir', str(f.root / 'sandbox-data')],
                       receivers=[dict(board='0F01', name='iMouse2-Z1', port=7900), dict(board='0F02', name='iMouse2-Z2', port=7910)])

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def reasons(self, prep, processes=(), listeners=(), stopping=False):
        return rk.conflicts(prep, dict(processes=list(processes), listeners=list(listeners)), stopping)[0]

    def test_clear_machine_starts(self):
        self.assertEqual(self.reasons(self.rack), [])
        self.assertEqual(self.reasons(self.box), [])

    def test_the_rack_kernel_refuses_any_kernel_receiver_farm_process_or_listener(self):
        self.assertTrue(self.reasons(self.rack, [kernel(1, 9936)]))                    # any kernel, also a sandbox's
        self.assertTrue(self.reasons(self.rack, [uxplay(1, 'iMouse2-B5', 7300)]))
        self.assertTrue(self.reasons(self.rack, FARM[:1])); self.assertTrue(self.reasons(self.rack, FARM[1:]))
        for port in (9916, 9917, 9913, 7110, 7112):
            self.assertTrue(self.reasons(self.rack, listeners=[port]), port)
        self.assertEqual(self.reasons(self.rack, listeners=[9936, 7900]), [])            # nobody's concern but a sandbox's

    def test_the_rack_kernel_is_stopped_only_when_no_kernel_or_receiver_remains(self):
        self.assertTrue(self.reasons(self.rack, [uxplay(2, 'iMouse2-anything', 1)], stopping=True))
        self.assertTrue(self.reasons(self.rack, [kernel(1, 9936)], stopping=True))
        self.assertTrue(self.reasons(self.rack, listeners=[9916], stopping=True))
        self.assertTrue(self.reasons(self.rack, listeners=[7121], stopping=True))
        self.assertEqual(self.reasons(self.rack, FARM, [9914, 9915], stopping=True), [])  # windows may outlive a stop check

    def test_a_sandbox_is_judged_only_against_itself(self):
        live = [kernel(1, 9916, 'C:/live/data'), uxplay(2, 'iMouse2-C24C', 7110), uxplay(3, 'iMouse2-C214', 7120)] + FARM
        listening = [9916, 9915, 9917, 7110, 7111, 7112]
        self.assertEqual(self.reasons(self.box, live, listening), [])
        self.assertEqual(self.reasons(self.box, live, listening, stopping=True), [])
        self.assertTrue(self.reasons(self.box, [kernel(1, 9936)]))                                   # its own kernel, by port
        self.assertTrue(self.reasons(self.box, [kernel(1, 9999, self.box['arguments'][2].upper())]))  # or by data folder
        self.assertTrue(self.reasons(self.box, [uxplay(2, 'iMouse2-Z2', 9999)]))                     # a lingering receiver by name
        self.assertTrue(self.reasons(self.box, [uxplay(2, 'iMouse2-old', 7911)]))                    # or by port
        self.assertTrue(self.reasons(self.box, listeners=[9936])); self.assertTrue(self.reasons(self.box, listeners=[7902]))
        self.assertTrue(self.reasons(self.box, [kernel(1, 9936)], stopping=True))
        self.assertTrue(self.reasons(self.box, listeners=[7900], stopping=True))

    def test_a_sandbox_may_not_sit_on_a_real_port(self):
        for port in rk.FARM_PORTS:
            with self.assertRaises(SystemExit): self.reasons(dict(self.box, arguments=[f'http://127.0.0.1:{port}/api/']))

    def test_a_preparation_must_start_a_loopback_kernel(self):
        with self.assertRaises(SystemExit): self.reasons(dict(self.rack, arguments=['http://192.168.4.26:9916/api/']))

    def test_snapshot_from_powershell_pipe_with_bom(self):
        self.assertEqual(rk.read_snapshot('\ufeff{"listeners": [9916]}'.encode('utf-8')), {'listeners': [9916]})
        self.assertEqual(rk.read_snapshot(b''), {})


class GoodbyePacketTests(unittest.TestCase):
    def test_python_goodbye_matches_the_kernel_bytes(self):
        # The kernel's MdnsGoodbye self-test pins the same hex: one packet, two implementations.
        import importlib.util
        spec = importlib.util.spec_from_file_location('mdns_goodbye', rk.ROOT / 'tools' / 'mdns_goodbye.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        self.assertEqual(module.goodbye_packet(dict(Name='iMouse2-T1', Mac='02:49:4D:32:C2:4C')).hex().upper(),
            '000084000000000200000000085F616972706C6179045F746370056C6F63616C00000C00010000000000200A694D6F757365322D5431085F'
            '616972706C6179045F746370056C6F63616C00055F72616F70045F746370056C6F63616C00000C000100000000002A17303234393444333243'
            '32344340694D6F757365322D5431055F72616F70045F746370056C6F63616C00')


if __name__ == '__main__':
    unittest.main()
