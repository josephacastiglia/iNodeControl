"""Check cited offsets against the exact DLL, independently of Ghidra text."""
from pathlib import Path
import hashlib
import json
import struct
from static_inventory import ROOT, HERE
import pefile

target = ROOT / 'targets' / 'MouseKeyItem.dll'
digest = hashlib.sha256(target.read_bytes()).hexdigest()
assert digest == 'a57812aed066d1bcf3b665e97813cf0ddc58e8e5e7f425026a45dde424db4a45'
pe = pefile.PE(str(target))
base = pe.OPTIONAL_HEADER.ImageBase
checks = []

def bytes_at(address, expected, meaning):
    actual = pe.get_data(address-base, len(bytes.fromhex(expected)))
    assert actual == bytes.fromhex(expected), (hex(address), actual.hex())
    checks.append({'address':hex(address), 'bytes':actual.hex(), 'checked_fact':meaning})

usage, token, label, modifier = struct.unpack('<IIII', pe.get_data(0x10019a68-base,16))
assert usage == 0x201 and modifier == 2
assert pe.get_string_at_rva(token-base) == b'FN'
checks.append({'address':'0x10019a68','checked_fact':'FN token has pseudo-usage 0x201 and table modifier 2'})
bytes_at(0x1000c2a1, '81fa01020000', 'Shortcut parser compares token usage with 0x201')
bytes_at(0x1000c2ad, 'c744241c02000000', 'FN branch sets separate extension value to 2')
bytes_at(0x1000c261, '6a2b', 'Shortcut prelude pushes Tab usage 0x2b')
bytes_at(0x10002601, 'c6442439a2', 'USB keyboard writer sets command family A2')
bytes_at(0x1000d478, '3ca1', 'Report reader compares family with A1')
bytes_at(0x1000d480, '3ca0', 'Report reader compares family with A0')
bytes_at(0x1000d577, 'c7870102000001000000', 'Common A0/A1 branch marks context completion flag')
bytes_at(0x1000d581, 'ffb70d020000', 'Completion branch passes its per-context event handle')
bytes_at(0x1000d587, 'ff1574500110', 'Completion branch calls the SetEvent import')
bytes_at(0x10008265, '83bf2302000001', 'Movement chooses alternate mode when context+0x223 equals 1')
bytes_at(0x10008339, 'c68424a9000000a0', 'Alternate movement path builds an A0 report')
bytes_at(0x1000ca02, '0fb68119020000', 'UID getter reads first of six cached identifier bytes')
imports = {i.address:i.name for d in pe.DIRECTORY_ENTRY_IMPORT for i in d.imports}
assert imports[0x10015074] == b'SetEvent'
assert imports[0x10015058] == b'WriteFile'
bytes_at(0x10013676, 'ff1558500110', 'WriteFile call ends at RVA 0x1367c, consistent with historical caller address suffix')
result = {'target_sha256':digest,'checks':checks,
          'scope':'Static bytes and tables only. Does not execute vendor code or establish phone behavior.'}
(HERE/'verified-offsets.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(f'{len(checks)} static evidence checks passed')
