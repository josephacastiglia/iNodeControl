"""Validate external Portable PDBs against PE debug IDs and content checksums.

Read-only, standard-library only. Does not load/execute either file or resolve
the embedded PDB path. Scope: the .NET 8 external Portable PDB builds we ship.
Format references: dotnet/runtime docs/design/specs/{PE-COFF,PortablePdb-Metadata}.md.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

MAX_FILE_BYTES = 64 * 1024 * 1024


def span(data, offset, size):
    if offset < 0 or size < 0 or offset > len(data) - size:
        raise ValueError('Truncated or out-of-range symbol metadata')
    return data[offset:offset + size]


def number(data, offset, kind='I'):
    return struct.unpack('<' + kind, span(data, offset, struct.calcsize('<' + kind)))[0]


def pe_debug(data):
    if span(data, 0, 2) != b'MZ':
        raise ValueError('Assembly is not a PE file')
    pe = number(data, 0x3c)
    if span(data, pe, 4) != b'PE\0\0':
        raise ValueError('Invalid PE signature')
    count = number(data, pe + 6, 'H')
    optional_size = number(data, pe + 20, 'H')
    optional = span(data, pe + 24, optional_size)
    magic = number(optional, 0, 'H')
    if magic not in (0x10b, 0x20b) or not 1 <= count <= 96:
        raise ValueError('Unsupported PE header')
    directories = 96 if magic == 0x10b else 112
    if number(optional, directories - 4) <= 6:
        raise ValueError('Missing PE debug directory')
    rva, size = struct.unpack('<II', span(optional, directories + 6 * 8, 8))
    sections = [span(data, pe + 24 + optional_size + i * 40, 40) for i in range(count)]

    def file_offset(address, length):
        matches = []
        for section in sections:
            start = number(section, 12)
            raw_size, raw_at = struct.unpack('<II', section[16:24])
            delta = address - start
            if 0 <= delta and delta + length <= raw_size:
                span(data, raw_at + delta, length)
                matches.append(raw_at + delta)
        if len(matches) != 1:
            raise ValueError('Ambiguous or unmapped PE debug address')
        return matches[0]

    if not size or size % 28 or size > 28 * 128:
        raise ValueError('Invalid PE debug directory size')
    at = file_offset(rva, size)
    codeviews, checksums = [], []
    for i in range(size // 28):
        _, stamp, major, minor, kind, length, address, pointer = struct.unpack(
            '<IIHHIIII', span(data, at + i * 28, 28))
        if kind not in (2, 19):
            continue
        if not length or not pointer or file_offset(address, length) != pointer:
            raise ValueError('Invalid PE debug data location')
        payload = span(data, pointer, length)
        if kind == 2:
            if minor != 0x504d or span(payload, 0, 4) != b'RSDS' or number(payload, 20) != 1:
                raise ValueError('External Portable PDB with CodeView age 1 is required')
            if len(payload) <= 24 or b'\0' not in payload[24:]:
                raise ValueError('Malformed CodeView path')
            codeviews.append(payload[4:20] + struct.pack('<I', stamp))
        else:
            if (major, minor) != (1, 0):
                raise ValueError('Unsupported PDB checksum entry version')
            algorithm, separator, checksum = payload.partition(b'\0')
            algorithms = {b'SHA256': ('sha256', 32), b'SHA384': ('sha384', 48), b'SHA512': ('sha512', 64)}
            if not separator or algorithm not in algorithms or len(checksum) != algorithms[algorithm][1]:
                raise ValueError('Unsupported or malformed PDB checksum')
            checksums.append((algorithms[algorithm][0], checksum))
    if len(codeviews) != 1 or not checksums:
        raise ValueError('Exactly one Portable CodeView ID and a PDB checksum are required')
    return codeviews[0], checksums


def pdb_id_offset(data):
    if span(data, 0, 4) != b'BSJB':
        raise ValueError('Symbols are not an external Portable PDB')
    version_size = number(data, 12)
    if not version_size or version_size > 256:
        raise ValueError('Invalid Portable PDB version header')
    span(data, 16, version_size)
    at = (16 + version_size + 3) & ~3
    count = number(data, at + 2, 'H')
    if not 1 <= count <= 64:
        raise ValueError('Invalid Portable PDB stream count')
    at += 4
    streams = {}
    for _ in range(count):
        offset, size = struct.unpack('<II', span(data, at, 8))
        at += 8
        end = data.find(b'\0', at, min(at + 32, len(data)))
        if end < 0:
            raise ValueError('Invalid Portable PDB stream name')
        name = data[at:end]
        if not name or name in streams:
            raise ValueError('Missing or duplicate Portable PDB stream')
        span(data, offset, size)
        streams[name] = (offset, size)
        at = (end + 4) & ~3
    ranges = sorted((offset, offset + size) for offset, size in streams.values() if size)
    if any(start < at for start, end in ranges) or any(a[1] > b[0] for a, b in zip(ranges, ranges[1:])):
        raise ValueError('Overlapping Portable PDB metadata')
    if b'#Pdb' not in streams or b'#~' not in streams or streams[b'#Pdb'][1] < 32:
        raise ValueError('Required Portable PDB streams are missing')
    return streams[b'#Pdb'][0]


def verify_bytes(assembly, symbols):
    assembly, symbols = bytes(assembly), bytes(symbols)
    expected_id, checksums = pe_debug(assembly)
    at = pdb_id_offset(symbols)
    actual_id = symbols[at:at + 20]
    if expected_id != actual_id:
        raise ValueError('DLL/PDB identity mismatch (GUID or stamp)')
    # The format hashes the complete Portable PDB with its 20-byte ID zeroed.
    matched = []
    for algorithm, expected in checksums:
        digest = hashlib.new(algorithm)
        digest.update(symbols[:at]); digest.update(bytes(20)); digest.update(symbols[at + 20:])
        if digest.digest() == expected:
            matched.append(algorithm)
    if not matched:
        raise ValueError('DLL/PDB content checksum mismatch')
    return {'format': 'portable-pdb', 'pdb_id': actual_id.hex(),
            'checksum_algorithms': sorted(set(matched)), 'identity_matches': True, 'checksum_matches': True}


def verify_pair(assembly, symbols):
    def read(path):
        with Path(path).open('rb') as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise ValueError('Symbol verification file exceeds the 64 MiB limit')
        return data
    return verify_bytes(read(assembly), read(symbols))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('assembly', type=Path)
    parser.add_argument('symbols', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify_pair(args.assembly, args.symbols), indent=2))
        return 0
    except (ValueError, OSError) as error:
        print(f'Refused: {error}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
