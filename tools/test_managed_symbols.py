"""Synthetic PE/debug metadata only; these fixtures contain no executable code."""
import hashlib
import struct
import unittest

import managed_symbols as symbols


def fixture(seed=1, pe64=False):
    identity = bytes(range(seed, seed + 20))
    pdb = bytearray(120)
    struct.pack_into('<4sHHII', pdb, 0, b'BSJB', 1, 1, 0, 12)
    pdb[16:28] = b'PDB v1.0\0\0\0\0'
    struct.pack_into('<HH', pdb, 28, 0, 2)
    struct.pack_into('<II8s', pdb, 32, 64, 32, b'#Pdb\0\0\0\0')
    struct.pack_into('<II4s', pdb, 48, 96, 24, b'#~\0\0')
    checksum = hashlib.sha256(pdb).digest()
    pdb[64:84] = identity

    pe = bytearray(1536)
    pe[:2] = b'MZ'
    struct.pack_into('<I', pe, 0x3c, 0x80)
    pe[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<H', pe, 0x86, 1)
    optional, optional_size = 0x98, 240 if pe64 else 224
    struct.pack_into('<H', pe, 0x94, optional_size)
    struct.pack_into('<H', pe, optional, 0x20b if pe64 else 0x10b)
    directories = optional + (112 if pe64 else 96)
    struct.pack_into('<I', pe, directories - 4, 16)
    struct.pack_into('<II', pe, directories + 48, 0x2000, 56)
    section = optional + optional_size
    pe[section:section + 8] = b'.debug\0\0'
    struct.pack_into('<IIII', pe, section + 8, 1024, 0x2000, 1024, 512)
    codeview = b'RSDS' + identity[:16] + struct.pack('<I', 1) + b'Z:/never/read/fixture.pdb\0'
    check = b'SHA256\0' + checksum
    at = 512 + 56
    check_at = (at + len(codeview) + 3) & ~3
    struct.pack_into('<IIHHIIII', pe, 512, 0, struct.unpack('<I', identity[16:])[0],
                     0x100, 0x504d, 2, len(codeview), 0x2000 + at - 512, at)
    struct.pack_into('<IIHHIIII', pe, 540, 0, 0, 1, 0, 19, len(check), 0x2000 + check_at - 512, check_at)
    pe[at:at + len(codeview)] = codeview
    pe[check_at:check_at + len(check)] = check
    return bytes(pe), bytes(pdb)


class SymbolTests(unittest.TestCase):
    def test_matching_pe32_and_pe64_with_content_checksum(self):
        for pe64 in (False, True):
            with self.subTest(pe64=pe64):
                result = symbols.verify_bytes(*fixture(pe64=pe64))
                self.assertTrue(result['identity_matches'] and result['checksum_matches'])
                self.assertEqual(result['checksum_algorithms'], ['sha256'])

    def test_wrong_pdb_refused_even_if_both_files_are_well_formed(self):
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            symbols.verify_bytes(fixture(1)[0], fixture(2)[1])

    def test_same_guid_different_stamp_refused(self):
        pe, pdb = fixture()
        changed = bytearray(pdb); changed[83] ^= 1
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            symbols.verify_bytes(pe, changed)

    def test_content_change_with_unchanged_id_refused(self):
        pe, pdb = fixture()
        changed = bytearray(pdb); changed[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            symbols.verify_bytes(pe, changed)

    def test_unexpected_age_refused(self):
        pe, pdb = fixture(); changed = bytearray(pe)
        struct.pack_into('<I', changed, 568 + 20, 2)
        with self.assertRaisesRegex(ValueError, 'age 1'):
            symbols.verify_bytes(changed, pdb)

    def test_missing_checksum_refused(self):
        pe, pdb = fixture(); changed = bytearray(pe)
        struct.pack_into('<I', changed, 540 + 12, 16)
        with self.assertRaisesRegex(ValueError, 'checksum are required'):
            symbols.verify_bytes(changed, pdb)

    def test_unsupported_checksum_refused(self):
        pe, pdb = fixture(); changed = bytearray(pe)
        at = struct.unpack_from('<I', pe, 540 + 24)[0]
        changed[at:at + 6] = b'FAKE00'
        with self.assertRaisesRegex(ValueError, 'checksum'):
            symbols.verify_bytes(changed, pdb)

    def test_old_or_unrecognised_pdb_refused(self):
        with self.assertRaisesRegex(ValueError, 'Portable PDB'):
            symbols.verify_bytes(fixture()[0], b'Microsoft C/C++ MSF 7.00' + bytes(100))

    def test_truncated_files_refused_as_validation_errors(self):
        pe, pdb = fixture()
        for size in (0, 1, 20, 63, 100, 200, 512, 560, 600):
            with self.subTest(pe=size), self.assertRaises(ValueError):
                symbols.verify_bytes(pe[:size], pdb)
        for size in (0, 1, 16, 28, 36, 60, 83, 119):
            with self.subTest(pdb=size), self.assertRaises(ValueError):
                symbols.verify_bytes(pe, pdb[:size])

    def test_overlapping_pdb_streams_refused(self):
        pe, pdb = fixture(); changed = bytearray(pdb)
        struct.pack_into('<I', changed, 48, 68)
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            symbols.verify_bytes(pe, changed)

    def test_unmapped_debug_rva_refused(self):
        pe, pdb = fixture(); changed = bytearray(pe)
        struct.pack_into('<I', changed, 0x98 + 96 + 48, 0x80000000)
        with self.assertRaisesRegex(ValueError, 'unmapped'):
            symbols.verify_bytes(changed, pdb)


if __name__ == '__main__':
    unittest.main()
