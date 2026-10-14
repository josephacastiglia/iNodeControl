"""Record PE layout/imports/exports and bounded disassembly, without loading a DLL."""
from pathlib import Path
import hashlib
import json
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2] / '.tooling' / 'imouse-rea-20261014'
sys.path.insert(0, str(ROOT / 'python'))
import pefile
import capstone

def inventory():
    records = []
    for path in sorted((ROOT / 'targets').iterdir()):
        pe = pefile.PE(str(path))
        records.append({
            'name': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'machine': hex(pe.FILE_HEADER.Machine), 'image_base': hex(pe.OPTIONAL_HEADER.ImageBase),
            'sections': [{'name': s.Name.decode('ascii', errors='replace').rstrip('\0'),
                'rva': hex(s.VirtualAddress), 'file_bytes': s.SizeOfRawData,
                'entropy': s.get_entropy()} for s in pe.sections],
            'imports': [{'dll': d.dll.decode(), 'name': i.name.decode() if i.name else i.ordinal,
                'iat': hex(i.address)} for d in pe.DIRECTORY_ENTRY_IMPORT for i in d.imports],
            'exports': [{'address': hex(pe.OPTIONAL_HEADER.ImageBase+s.address),
                'name': s.name.decode(errors='replace') if s.name else s.ordinal}
                for s in getattr(getattr(pe, 'DIRECTORY_ENTRY_EXPORT', None), 'symbols', [])],
        })
    (HERE / 'static-inventory.json').write_text(json.dumps(records, indent=2), encoding='utf8')
    print('Recorded', len(records), 'static inventories')

def disassemble(address, length):
    pe = pefile.PE(str(ROOT / 'targets' / 'MouseKeyItem.dll'))
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    return '\n'.join(f'{i.address:08x}: {i.bytes.hex():24s} {i.mnemonic} {i.op_str}'
        for i in md.disasm(pe.get_data(address-pe.OPTIONAL_HEADER.ImageBase, length),address))

if __name__ == '__main__':
    if len(sys.argv) == 1:
        inventory()
    else:
        print(disassemble(int(sys.argv[1],0), int(sys.argv[2],0)))
