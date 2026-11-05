"""Offline tests for rack_kernels.py: the split into one kernel per rack and the start/stop checks.
No kernel, receiver, socket or phone; placeholder phone IDs only.

  python -m unittest test_rack_kernels    (from this folder)
"""
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rack_kernels as rk  # noqa: E402

A_BOARDS, B_BOARDS = ['C24C', 'C214', '3848'], ['EE14', 'CD51']
NOW = datetime(2026, 11, 4, 23, 0, tzinfo=timezone.utc)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Fixture:
    def __init__(self, root):
        self.root = Path(root)
        boards = A_BOARDS + B_BOARDS
        source = self.root / 'output/candidate-runs/multiphone-racks-ab-bound-x/data'; source.mkdir(parents=True)
        port = {b: 7110 + 10 * i for i, b in enumerate(A_BOARDS)} | {b: 7300 + 10 * i for i, b in enumerate(B_BOARDS)}
        rows = {
            'devices.json': [dict(deviceid=f'pending-{b}', pid=b, uid=b, name=f'Board {b}', gname='Rack B' if b in B_BOARDS else 'Rack A') for b in boards],
            'receivers.json': [dict(DeviceId=f'pending-{b}', BoardPid=b, Name=f'iMouse2-{b}', Pipe=f'iMouse2-{b}-frames', Port=port[b],
                                    Mac=f'02:49:4D:32:{b[:2]}:{b[2:]}') for b in boards],
            'pointer-calibration.json': [dict(Pid=b, Width=500, Height=1080) for b in boards]}
        for name, r in rows.items(): (source / name).write_text(json.dumps(r), encoding='utf-8')
        self.kernel = self.root / 'output/rack-kernel/iMouse2.Kernel.exe'; self.kernel.parent.mkdir(parents=True)
        self.kernel.write_bytes(b'exe'); self.kernel.with_suffix('.dll').write_bytes(b'dll')
        csv = ','.join(boards)
        self.base = dict(runDirectory=str(source.parent), kernel='old.exe', kernelSha256='0' * 64,
                         arguments=['http://127.0.0.1:9916/api/', '--data-dir', str(source), '--input-pid', csv,
                                    '--receivers', str(source / 'receivers.json'), '--receiver', 'uxplay.exe',
                                    '--receiver-runtime', 'runtime', '--hold-receivers', csv],
                         held=boards, boards=boards, inputEnabled=boards,
                         receivers=[dict(board=b, name=f'iMouse2-{b}', port=port[b]) for b in boards],
                         slots={'C24C': 18, 'C214': 20}, rackB=B_BOARDS,
                         dataSha256={n: sha(source / n) for n in rk.DATA_FILES})
        self.base_path = self.root / 'preparation.json'
        self.base_path.write_text(json.dumps(self.base), encoding='utf-8')

    def split(self, **kw):
        args = dict(rack_b_boards=B_BOARDS, slots_a=['C24C', 'C214'], slots_b=['CD51'], root=self.root, now=NOW)
        args.update(kw)
        return rk.split(self.base_path, self.kernel, **args)


class SplitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.f = Fixture(self.tmp.name)

    def tearDown(self): self.tmp.cleanup()

    def test_each_rack_gets_only_its_boards_rows_and_port(self):
        result = self.f.split()
        a, a_rows = result['A']; b, b_rows = result['B']
        self.assertEqual(a['boards'], A_BOARDS); self.assertEqual(b['boards'], B_BOARDS)
        for prep, rows, boards in ((a, a_rows, A_BOARDS), (b, b_rows, B_BOARDS)):
            self.assertEqual([r['pid'] for r in rows['devices.json']], boards)
            self.assertEqual([r['BoardPid'] for r in rows['receivers.json']], boards)
            self.assertEqual([r['Pid'] for r in rows['pointer-calibration.json']], boards)
            self.assertEqual(rk._option(prep['arguments'], '--input-pid').split(','), boards)
            self.assertEqual(rk._option(prep['arguments'], '--hold-receivers').split(','), boards)
            self.assertEqual(prep['held'], boards)
            self.assertNotIn(str(Path(self.f.base['runDirectory']) / 'data'), ' '.join(prep['arguments']))
        self.assertEqual(rk.api_port(a), 9916)   # Farm tools that talk to 9916 keep reaching rack A.
        self.assertEqual(rk.api_port(b), 9926)
        self.assertEqual(rk._option(a['arguments'], '--rack'), 'A')
        self.assertEqual(rk._option(b['arguments'], '--rack'), 'B')
        self.assertEqual(a['slots'], {'C24C': 18, 'C214': 20}); self.assertEqual(b['slots'], {})
        self.assertEqual(a['kernelSha256'], sha(self.f.kernel.with_suffix('.dll')))
        self.assertNotEqual(a['runDirectory'], b['runDirectory'])
        self.assertFalse(set(rk.receiver_ports(a)) & set(rk.receiver_ports(b)))

    def test_write_records_hashes_and_refuses_to_overwrite(self):
        result = self.f.split()
        outs = {r: self.f.root / f'rack-{r.lower()}' for r in result}
        rk.write(result, outs)
        for rack in 'AB':
            prep = json.loads((outs[rack] / 'preparation.json').read_text(encoding='utf-8'))
            data = Path(prep['runDirectory']) / 'data'
            self.assertEqual(prep['dataSha256'], {n: sha(data / n) for n in rk.DATA_FILES})
        with self.assertRaises(SystemExit): rk.write(self.f.split(), outs)

    def test_refuses_inconsistent_inputs(self):
        with self.assertRaises(SystemExit): self.f.split(rack_b_boards=B_BOARDS + ['FFFF'])
        with self.assertRaises(SystemExit): self.f.split(slots_a=['CD51'])        # a rack B board named on rack A
        with self.assertRaises(SystemExit): self.f.split(slots_b=['C24C'])
        with self.assertRaises(SystemExit): self.f.split(rack_b_boards=A_BOARDS + B_BOARDS)   # rack A left empty
        with self.assertRaises(SystemExit): rk.split(self.f.base_path, self.f.kernel, B_BOARDS, [], [], dict(A=9930, B=9930), self.f.root, NOW)
        with self.assertRaises(SystemExit): rk.split(self.f.base_path, self.f.kernel, B_BOARDS, [], [], dict(B=7300), self.f.root, NOW)

    def test_rekernel_changes_only_the_kernel(self):
        out = self.f.root / 'slots'; out.mkdir()
        prep = rk.rekernel(self.f.base_path, self.f.kernel, out)
        self.assertEqual({k: v for k, v in prep.items() if k not in ('kernel', 'kernelSha256', 'rekernelFrom')}, self.f.base)
        self.assertEqual(prep['kernelSha256'], sha(self.f.kernel.with_suffix('.dll')))
        self.assertEqual(prep['rekernelFrom']['kernelSha256'], '0' * 64)
        with self.assertRaises(SystemExit): rk.rekernel(self.f.base_path, self.f.kernel, out)   # never overwrites

    def test_refuses_changed_base_data_or_an_already_split_base(self):
        data = Path(self.f.base['runDirectory']) / 'data' / 'receivers.json'
        data.write_text(data.read_text(encoding='utf-8') + ' ', encoding='utf-8')
        with self.assertRaises(SystemExit): self.f.split()
        f = Fixture(Path(self.tmp.name) / 'again')
        f.base['arguments'] += ['--rack', 'A']; f.base_path.write_text(json.dumps(f.base), encoding='utf-8')
        with self.assertRaises(SystemExit): f.split()


def kernel(pid, port, rack=None, data='x'):
    command = f'"iMouse2.Kernel.exe" "http://127.0.0.1:{port}/api/" "--data-dir" "{data}"' + (f' "--rack" "{rack}"' if rack else '')
    return dict(Name='iMouse2.Kernel.exe', ProcessId=pid, CommandLine=command)


def uxplay(pid, name, port):
    return dict(Name='uxplay.exe', ProcessId=pid, CommandLine=f'"uxplay.exe" -n {name} -nh -s 500x1080 -p {port} -m 02:00:00:00:00:01')


class CheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); f = Fixture(cls.tmp.name)
        result = f.split()
        cls.a, cls.b, cls.single = result['A'][0], result['B'][0], f.base

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def reasons(self, prep, processes=(), listeners=(), rack=None, stopping=False):
        return rk.conflicts(prep, dict(processes=list(processes), listeners=list(listeners)), rack, stopping)[0]

    def test_clear_machine_starts_every_mode(self):
        for prep, rack in ((self.single, None), (self.a, 'A'), (self.b, 'B')):
            self.assertEqual(self.reasons(prep, rack=rack), [])

    def test_rack_b_starts_beside_a_running_rack_a(self):
        running_a = [kernel(1, 9916, 'A', self.a['runDirectory']), uxplay(2, 'iMouse2-C24C', 7110), uxplay(3, 'iMouse2-C214', 7120)]
        listening_a = [9916, 7110, 7111, 7112, 9914]
        self.assertEqual(self.reasons(self.b, running_a, listening_a, 'B'), [])
        self.assertEqual(self.reasons(self.b, running_a, listening_a, 'B', stopping=True), [])

    def test_rack_refuses_its_own_kernel_receivers_or_ports(self):
        self.assertTrue(self.reasons(self.b, [kernel(1, 9926, 'B')], rack='B'))
        self.assertTrue(self.reasons(self.b, [kernel(1, 9926, 'Z')], rack='B'))           # same port, other label
        self.assertTrue(self.reasons(self.b, [uxplay(2, 'iMouse2-CD51', 9999)], rack='B'))  # a lingering receiver by name
        self.assertTrue(self.reasons(self.b, [uxplay(2, 'iMouse2-old', 7310)], rack='B'))   # or by port
        self.assertTrue(self.reasons(self.b, listeners=[9926], rack='B'))
        self.assertTrue(self.reasons(self.b, listeners=[7301], rack='B'))

    def test_either_rack_refuses_the_single_kernel(self):
        single = [kernel(1, 9916)]
        self.assertTrue(self.reasons(self.a, single, rack='A'))
        self.assertTrue(self.reasons(self.b, single, rack='B'))

    def test_single_kernel_refuses_any_rack_kernel_or_receiver(self):
        self.assertTrue(self.reasons(self.single, [kernel(1, 9926, 'B')]))
        self.assertTrue(self.reasons(self.single, [uxplay(1, 'iMouse2-B5', 7300)]))
        self.assertTrue(self.reasons(self.single, listeners=[9917]))

    def test_farm_processes_block_rack_a_and_the_single_kernel_only(self):
        farm = [dict(Name='python.exe', ProcessId=9, CommandLine='python tools/imouse_farm_server.py'), dict(Name='iMouse2.exe', ProcessId=8)]
        self.assertTrue(self.reasons(self.single, farm))
        self.assertTrue(self.reasons(self.a, farm, rack='A'))
        self.assertTrue(self.reasons(self.a, listeners=[9914], rack='A'))
        self.assertEqual(self.reasons(self.b, farm, [9914], rack='B'), [])
        self.assertEqual(self.reasons(self.a, farm, [9914], rack='A', stopping=True), [])   # stopping rack A ignores the farm

    def test_stop_check_sees_only_this_racks_leftovers(self):
        self.assertTrue(self.reasons(self.a, [uxplay(2, 'iMouse2-C24C', 7110)], rack='A', stopping=True))
        self.assertEqual(self.reasons(self.a, [kernel(1, 9926, 'B'), uxplay(2, 'iMouse2-EE14', 7300)], [9926], 'A', stopping=True), [])
        self.assertTrue(self.reasons(self.single, [uxplay(2, 'iMouse2-anything', 1)], stopping=True))

    def test_stopping_a_rack_ignores_an_unrelated_single_kernel(self):
        # A single kernel elsewhere is not this rack's leftover; one on this rack's port is.
        self.assertEqual(self.reasons(self.b, [kernel(1, 9936)], rack='B', stopping=True), [])
        self.assertTrue(self.reasons(self.b, [kernel(1, 9926)], rack='B', stopping=True))

    def test_snapshot_from_powershell_pipe_with_bom(self):
        self.assertEqual(rk.read_snapshot('﻿{"listeners": [9926]}'.encode('utf-8')), {'listeners': [9926]})
        self.assertEqual(rk.read_snapshot(b''), {})

    def test_rack_and_preparation_must_agree(self):
        with self.assertRaises(SystemExit): self.reasons(self.a, rack='B')
        with self.assertRaises(SystemExit): self.reasons(self.a)
        with self.assertRaises(SystemExit): self.reasons(self.single, rack='A')


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
