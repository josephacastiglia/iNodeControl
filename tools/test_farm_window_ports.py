"""Window ports for any rack A slot (Fleet lane, 5 Nov): legacy slots unchanged, no collisions. Offline."""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from farm_creation_runs import LEGACY_PORTS, MEDIA_PORTS, creation_config, window_ports
from farm_phone_identity import PhoneIdentity

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'analysis/farm-multiphone-20261020'))
prepare_window = importlib.import_module('prepare_window')

# Ports the rack already uses: kernel API (9916), the planned rack B kernel (9926), the off-rack trial kernel (9936),
# the single-phone console/kernel ports and the candidate launcher (9911-9914, 9923), and the receivers' AirPlay ports.
SERVICE_PORTS = {9911, 9913, 9914, 9916, 9923, 9926, 9936}
RECEIVER_PORTS = range(7110, 7500)
SLOT10 = PhoneIdentity(board='374C', device_id='02:00:00:00:00:0A', receiver='iMouse2-10', slot=10)


class WindowPorts(unittest.TestCase):
    def test_legacy_slots_keep_their_ports_exactly(self):
        self.assertEqual({16: (9945, 9947), 17: (9935, 9937), 18: (9915, 9917), 20: (9925, 9927)},
                         {s: window_ports(s) for s in (16, 17, 18, 20)})
        self.assertEqual({18: 9915, 20: 9925, 17: 9935, 16: 9945}, {s: prepare_window.BACKEND_PORTS[s] for s in (16, 17, 18, 20)})
        self.assertEqual({0: 9917, 18: 9917, 20: 9927, 17: 9937, 16: 9947}, {s: MEDIA_PORTS[s] for s in LEGACY_PORTS})

    def test_every_rack_a_slot_has_its_own_ports(self):
        used = [p for s in range(1, 21) for p in window_ports(s)]
        self.assertEqual(len(used), len(set(used)))   # 20 slots x 2 ports, all distinct.
        for port in used:
            self.assertNotIn(port, SERVICE_PORTS); self.assertNotIn(port, RECEIVER_PORTS)
        self.assertEqual((9705, 9707), window_ports(10)); self.assertEqual((9795, 9797), window_ports(19))
        self.assertEqual({s: window_ports(s)[0] for s in range(1, 21)}, prepare_window.BACKEND_PORTS)
        self.assertEqual(window_ports(10)[1], MEDIA_PORTS[10])
        for bad in (21, -1, 'B5', None):
            with self.subTest(bad=bad), self.assertRaises(ValueError): window_ports(bad)

    def test_creation_config_takes_only_the_new_slots_own_media_port(self):
        def write(port):
            path = Path(tempfile.mkdtemp(prefix='fleet-port-')) / 'config.json'
            path.write_text(json.dumps(dict(version=2, api='http://127.0.0.1:9916/api', kernelSha256='a' * 64, expectedUid='U',
                                            phone=SLOT10.as_config(), allowed=['C24C', '374C'], account=None,
                                            mediaBind='192.168.4.26', mediaClient='192.168.4.30', mediaPort=port)), encoding='utf-8')
            return path
        self.assertEqual(9707, creation_config(write(9707), 'live')['mediaPort'])
        for port in (9917, 9927, 9717, 9705):
            with self.subTest(port=port), self.assertRaises(ValueError): creation_config(write(port), 'live')

    def test_image_platforms_run_on_xr_slots_only(self):
        self.assertTrue(set(prepare_window.XR_SLOTS) >= {16, 17, 18, 20})
        self.assertFalse(set(prepare_window.XR_SLOTS) & {2, 5, 6, 7, 8})
        for platform in prepare_window.IMAGE_PLATFORMS:
            account = ['--account', 'acct'] if prepare_window.PLATFORMS[platform][5] else []
            argv = ['prepare_window.py', '--platform', platform, '--slot', '5', '--phone-ip', '192.168.4.30', *account]
            with self.subTest(platform=platform), patch.object(sys, 'argv', argv), \
                    patch.object(prepare_window, 'load', side_effect=AssertionError('rack read')):
                with self.assertRaisesRegex(SystemExit, 'XR slot only'): prepare_window.main()


if __name__ == '__main__':
    unittest.main()
