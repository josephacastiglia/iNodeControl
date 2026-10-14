"""Synthetic parser checks, not physical protocol validation."""
import unittest
from vendor_hid_decode import decode_report


class VendorHidDecodeTests(unittest.TestCase):
    def test_windows_report_id_is_removed_exactly_once(self):
        usb = bytes.fromhex('a1 00 81 7f 00 00 00 00')
        a = decode_report(usb, direction='out', framing='usb')
        b = decode_report(b'\0'+usb, direction='out', framing='windows')
        self.assertEqual(a['payload_hex'], b['payload_hex'])
        self.assertEqual((a['dx'], a['dy']), (-127, 127))

    def test_unknown_mouse_fields_survive(self):
        row = decode_report(bytes.fromhex('a1 01 00 00 11 22 33 44'), direction='out', framing='usb')
        self.assertEqual(row['unknown_tail_hex'], '11 22 33 44')

    def test_fn_is_separate_from_shift(self):
        row = decode_report(bytes.fromhex('a2 00 52 00 00 00 00 02'), direction='out', framing='usb')
        self.assertEqual(row['modifier'], 0)
        self.assertTrue(row['vendor_fn'])
        self.assertEqual(row['usages'][0], 0x52)

    def test_shift_does_not_imply_fn(self):
        row = decode_report(bytes.fromhex('a2 02 04 00 00 00 00 00'), direction='out', framing='usb')
        self.assertFalse(row['vendor_fn'])

    def test_unknown_keyboard_bits_survive(self):
        row = decode_report(bytes.fromhex('a2 00 04 05 06 07 ff 82'), direction='out', framing='usb')
        self.assertEqual(row['unknown_extended_value'], 0x82)
        self.assertIsNone(row['vendor_fn'])
        self.assertEqual(row['unassigned_byte6'], 0xff)
        self.assertEqual(row['usages'], [4, 5, 6, 7])

    def test_completion_never_claims_ios_success_or_position(self):
        for family in (0xa0, 0xa1):
            row = decode_report(bytes([family])+bytes(15), direction='in', framing='usb')
            self.assertEqual(row['kind'], 'vendor_movement_completion_signal')
            self.assertIn('not established', row['ios_outcome'])
            self.assertNotIn('x_raw', row)
            self.assertIn('No sequence ID', row['correlation'])

    def test_direction_changes_meaning(self):
        out = decode_report(bytes.fromhex('a0 01 ff 7f 00 40 00 00'), direction='out', framing='usb')
        self.assertEqual((out['x_raw'], out['y_raw']), (32767, 16384))
        self.assertIn('not validated', out['support'])

    def test_identifier_is_six_bytes_and_retains_unknown_tail(self):
        row = decode_report(bytes.fromhex('a5 01 02 03 04 05 06')+bytes([0xcc])*9,
                            direction='in', framing='usb')
        self.assertEqual(row['identifier_hex'], '010203040506')
        self.assertEqual(row['unknown_tail_hex'], ' '.join(['cc']*9))
        self.assertIn('not proven', row['identity_scope'])

    def test_status_cause_remains_unknown(self):
        for family in (0xa6, 0xaf):
            row = decode_report(bytes([family])+bytes(15), direction='in', framing='usb')
            self.assertEqual(row['kind'], 'vendor_status_event')
            self.assertIn('unverified', row['meaning'])

    def test_unknown_family_is_preserved(self):
        row = decode_report(bytes.fromhex('ef 11 22 33 44 55 66 77'), direction='out', framing='usb')
        self.assertEqual(row['kind'], 'unknown')
        self.assertEqual(row['payload_hex'], 'ef 11 22 33 44 55 66 77')

    def test_rejects_wrong_sizes(self):
        for direction, framing, length in [('in', 'usb', 15), ('in', 'windows', 16),
                ('out', 'usb', 9), ('out', 'windows', 8), ('in', 'usb', 17)]:
            with self.subTest(direction=direction, framing=framing, length=length):
                with self.assertRaises(ValueError):
                    decode_report(bytes(length), direction=direction, framing=framing)

    def test_rejects_nonzero_report_id(self):
        with self.assertRaises(ValueError):
            decode_report(bytes([1])+bytes(8), direction='out', framing='windows')

    def test_requires_explicit_valid_direction_and_framing(self):
        for direction, framing in [('auto', 'usb'), ('out', 'auto')]:
            with self.assertRaises(ValueError):
                decode_report(bytes(8), direction=direction, framing=framing)


if __name__ == '__main__':
    unittest.main()
