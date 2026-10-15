"""Check cited static facts against the recorded vendor DLL; never execute it."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'vendor-protocol-rea-20261014'))
from static_inventory import ROOT
import pefile

target = ROOT / 'targets/MouseKeyItem.dll'
digest = hashlib.sha256(target.read_bytes()).hexdigest()
assert digest == 'a57812aed066d1bcf3b665e97813cf0ddc58e8e5e7f425026a45dde424db4a45'
pe = pefile.PE(str(target))
rows = [
    (0x1000d42c, 'ffb70d020000', 'A5 identifier branch uses context event +0x20d'),
    (0x1000d432, 'ff1574500110', 'A5 branch calls SetEvent'),
    (0x1000d581, 'ffb70d020000', 'A0/A1 movement branch uses the same context event'),
    (0x1000d587, 'ff1574500110', 'A0/A1 branch calls SetEvent'),
    (0x1000d444, 'c787f90100000a000000', 'AF sets context +0x1f9 to 10'),
    (0x1000d44f, 'c787fd01000001000000', 'AF sets context +0x1fd to 1; physical meaning unknown'),
    (0x1000d45e, 'c787ed010000e8030000', 'AF sets context +0x1ed to 1000'),
    (0x1000d549, 'c787ed010000e8030000', 'A6 sets context +0x1ed to 1000'),
    (0x100048cd, 'ffb3f9010000', 'Relative reset loop passes context +0x1f9'),
    (0x100048d3, 'ff156c500110', 'Reset loop calls Sleep with that value'),
    (0x10003546, '83bb2302000001', 'LeftDown selects its alternate path when mode +0x223 is 1'),
    (0x10003706, '83bb2302000001', 'LeftUp selects the same alternate path'),
    (0x1000ca79, '8988230200005dc20800', 'SetIOSVer stores its argument then returns; it sends no board report'),
]
checks = []
for address, expected, meaning in rows:
    actual = pe.get_data(address - pe.OPTIONAL_HEADER.ImageBase, len(bytes.fromhex(expected)))
    assert actual == bytes.fromhex(expected), hex(address)
    checks.append(dict(address=hex(address), bytes=actual.hex(), checked_fact=meaning))
imports = {i.address: i.name for d in pe.DIRECTORY_ENTRY_IMPORT for i in d.imports}
assert imports[0x10015074] == b'SetEvent' and imports[0x1001506c] == b'Sleep'
(HERE / 'verified-vendor-followup.json').write_text(json.dumps({
    'target_sha256': digest, 'checks': checks,
    'scope': 'Static bytes only; no hardware or iOS behavior established.'}, indent=2), encoding='utf-8')
print(f'{len(checks)} static instruction checks passed')
