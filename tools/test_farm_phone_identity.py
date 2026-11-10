"""Multi-phone windows: each window drives only its own phone. In-memory transports only."""
import json
import tempfile
import unittest
from pathlib import Path

import farm_draft_transport as step
from farm_creation_runs import creation_config
from farm_draft_runs import load_config, phone_of
from farm_live_verification import validate_runtime
from farm_phone_identity import LEGACY_C24C, PhoneIdentity, PhoneIdentityError, own_receiver
from imouse_social_automation import IMouseKernel, KernelSafetyError
# Fixture device IDs (locally administered addresses), not real phones; slot 18 is the pre-rack C24C identity.

SLOT20 = PhoneIdentity(board='C214', device_id='02:00:00:00:00:20', receiver='iMouse2-20', slot=20)
SLOT18 = PhoneIdentity(board='C24C', device_id=LEGACY_C24C.device_id, receiver='iMouse2-18', slot=18)
SLOT17 = PhoneIdentity(board='724E', device_id='02:00:00:00:00:17', receiver='iMouse2-17', slot=17)
ALLOWED = ['C24C', 'C214', '724E', 'F215']
HASH = 'a' * 64


def rack_status(receivers=None):
    rows = receivers if receivers is not None else [
        dict(deviceid=p.device_id, name=p.receiver, live=True, frames=10) for p in (SLOT18, SLOT20, SLOT17)]
    return dict(code=0, build_identity=dict(sha256=HASH), input_leases_required=True, allowed=ALLOWED,
                process=dict(pid=7, started_utc='fixture'), receivers=rows)


def rack_devices():
    return [dict(deviceid=p.device_id, pid=p.board, uid=p.board + 'UID') for p in (SLOT18, SLOT20, SLOT17)]


class IdentityTests(unittest.TestCase):
    def test_identity_is_strict(self):
        for bad in (dict(board='c214', device_id=SLOT20.device_id, receiver='iMouse2-20', slot=20),
                    dict(board='C214', device_id='02:00:00:00:00:2a', receiver='iMouse2-20', slot=20),   # Lower case.
                    dict(board='C214', device_id=SLOT20.device_id, receiver='iMouse2-18', slot=20),
                    dict(board='C214', device_id=SLOT20.device_id, receiver='iMouse2-20', slot=21)):
            with self.subTest(bad=bad), self.assertRaises(PhoneIdentityError): PhoneIdentity(**bad)
        self.assertEqual(SLOT20, PhoneIdentity.from_config(SLOT20.as_config()))
        self.assertTrue(SLOT20.targets('c214') and SLOT20.targets(SLOT20.device_id))
        self.assertFalse(SLOT20.targets('C24C') or SLOT20.targets(SLOT18.device_id))

    def test_own_receiver_never_takes_the_first_row_or_a_renamed_one(self):
        status = rack_status()
        self.assertEqual('iMouse2-20', own_receiver(status, SLOT20)['name'])   # Second row, not receivers[0].
        renamed = rack_status([dict(r, name='iMouse2-C214') if r['deviceid'] == SLOT20.device_id else r for r in status['receivers']])
        duplicated = rack_status(status['receivers'] + [dict(deviceid=SLOT20.device_id, name='iMouse2-20')])
        missing = rack_status([r for r in status['receivers'] if r['deviceid'] != SLOT20.device_id])
        for bad in (renamed, duplicated, missing):
            with self.assertRaises(PhoneIdentityError): own_receiver(bad, SLOT20)


class KernelGateTests(unittest.TestCase):
    def kernel(self, phone):
        sent = []
        def wire(method, url, body, timeout):
            sent.append(body)
            if url.endswith('/kernel/status'): return json.dumps(dict(status=200, data=rack_status())).encode(), {}
            return b'{"status":200,"data":{"code":0}}', {}
        k = IMouseKernel('http://127.0.0.1:9916/api', transport=wire, phone=phone)
        k._is_live_http = True
        return k, sent

    def test_a_window_refuses_every_other_phone(self):
        k, _ = self.kernel(SLOT20)
        for other in ('C24C', SLOT18.device_id, '724E', 'C214,C24C'):
            with self.subTest(other=other), self.assertRaises(KernelSafetyError):
                k._validate_post_target('/mouse/click', dict(id=other))
        with self.assertRaises(KernelSafetyError): k._validate_post_target('/input/acquire', dict(id='C214', tokens={'C24C': 't'}))
        k._validate_post_target('/mouse/click', dict(id=SLOT20.device_id))

    def test_board_resolves_only_through_its_own_receiver(self):
        k, _ = self.kernel(SLOT20)
        self.assertEqual(SLOT20.device_id, k.resolve_device_id('C214'))
        with self.assertRaises(KernelSafetyError): k.resolve_device_id('C24C')
        k17, _ = self.kernel(PhoneIdentity(board='F215', device_id='02:00:00:00:00:16', receiver='iMouse2-16', slot=16))
        with self.assertRaises(KernelSafetyError): k17.resolve_device_id('F215')   # Its receiver is not in this status.

    def test_step_kernel_for_one_phone_never_forwards_another(self):
        calls = []
        def transport(*args): calls.append(args); return b'{}', {}
        client = step.StepKernel('http://127.0.0.1:9916/api', transport=transport, phone=SLOT20)
        client._transport('POST', client.url + '/', dict(fun='/mouse/click', data=dict(id=SLOT20.device_id)), 1)
        for other in (SLOT18.device_id, SLOT17.device_id, 'C214'):
            with self.subTest(other=other), self.assertRaises(KernelSafetyError):
                client._transport('POST', client.url + '/', dict(fun='/mouse/click', data=dict(id=other)), 1)
        self.assertEqual(1, len(calls))
        with self.assertRaises(TypeError): step.StepKernel('http://127.0.0.1:9916/api', transport=transport)


class RuntimeTests(unittest.TestCase):
    def test_multi_phone_kernel_needs_its_exact_allow_list_and_one_mapping(self):
        self.assertEqual((7, 'fixture'), validate_runtime(rack_status(), rack_devices(), HASH, 'C214UID', SLOT20, ALLOWED))
        with self.assertRaises(KernelSafetyError): validate_runtime(rack_status(), rack_devices(), HASH, 'C214UID', SLOT20, ALLOWED[:3])
        with self.assertRaises(KernelSafetyError): validate_runtime(rack_status(), rack_devices(), HASH, 'C214UID', SLOT20)   # Single-phone rule.
        with self.assertRaises(KernelSafetyError): validate_runtime(rack_status(), rack_devices(), HASH, 'C24CUID', SLOT20, ALLOWED)
        clash = rack_devices() + [dict(deviceid=SLOT20.device_id, pid='F215', uid='x')]
        with self.assertRaises(KernelSafetyError): validate_runtime(rack_status(), clash, HASH, 'C214UID', SLOT20, ALLOWED)
        twin = rack_status(rack_status()['receivers'] + [dict(deviceid='02:00:00:00:00:16', name='iMouse2-20')])
        with self.assertRaises(KernelSafetyError): validate_runtime(twin, rack_devices(), HASH, 'C214UID', SLOT20, ALLOWED)

    def test_single_phone_kernel_still_validates_as_before(self):
        status = dict(rack_status([dict(deviceid=LEGACY_C24C.device_id, name='iMouse2-C24C')]), allowed=['C24C'])
        devices = [dict(deviceid=LEGACY_C24C.device_id, pid='C24C', uid='U')]
        self.assertEqual((7, 'fixture'), validate_runtime(status, devices, HASH, 'U'))


class ConfigTests(unittest.TestCase):
    def write(self, value):
        folder = tempfile.mkdtemp(prefix='farm-phone-config-'); path = Path(folder) / 'config.json'
        path.write_text(json.dumps(value), encoding='utf-8'); return path

    def base(self, **changes):
        value = dict(version=2, api='http://127.0.0.1:9916/api', kernelSha256=HASH, expectedUid='C214UID',
                     phone=SLOT20.as_config(), allowed=ALLOWED, account='tiktok.handle')
        value.update(changes); return value

    def test_version_2_names_one_allowed_phone(self):
        self.assertEqual(SLOT20, phone_of(load_config(self.write(self.base()), 'live')))
        self.assertIsNone(load_config(self.write(self.base(account=None)), 'live')['account'])
        for bad in (self.base(allowed=['C24C']), self.base(allowed=ALLOWED + ['C214']), self.base(account='@handle'),
                    self.base(phone=dict(SLOT20.as_config(), receiver='iMouse2-C214')), self.base(version=1)):
            with self.subTest(bad=bad), self.assertRaises(ValueError): load_config(self.write(bad), 'live')

    def test_media_port_belongs_to_the_slot(self):
        media = dict(mediaBind='192.168.4.26', mediaClient='192.168.4.27')
        self.assertEqual(9927, creation_config(self.write(self.base(**media, mediaPort=9927)), 'live')['mediaPort'])
        for port in (9917, 9937, 8080):
            with self.subTest(port=port), self.assertRaises(ValueError):
                creation_config(self.write(self.base(**media, mediaPort=port)), 'live')


if __name__ == '__main__':
    unittest.main()
