"""Offline preparation for the C24C permission-prompt validation window. No socket, phone or service.

Creates an isolated run folder holding two byte-identical copies of the verified C24C-only
kernel mapping: part A for the normal private kernel, part B for the same kernel with the
move-only absolute probe (--hid-replies-pid C24C --absolute-probe-pid C24C). It pins the
kernel, the receiver, every Python source the window steps load and the protected installed
files. It refuses to overwrite a prepared window, reads no operator settings and starts nothing.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/'tools'))
P2 = ROOT/'analysis/farm-recovery-live-20261019'
RUN = ROOT/'output/candidate-runs/prompt-validation-20261020'
PYTHON = r'C:\Users\joey_\AppData\Local\Programs\Python\Python311\python.exe'
PROBE_ARGUMENTS = ['--hid-replies-pid', 'C24C', '--absolute-probe-pid', 'C24C']
# UTF-16 strings of the 14 Oct probe (commit 373dd58) that the kernel build must contain.
PROBE_STRINGS = ('--absolute-probe-pid', 'Absolute probe permits pointer moves and reset only',
                 'EXPERIMENTAL absolute probe on ')
MAPPING = ('devices.json', 'receivers.json', 'pointer-calibration.json')


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def c24c_only(folder, uid, device):
    devices, receivers, calibration = (load(Path(folder)/name) for name in MAPPING)
    return (len(devices) == 1 and devices[0]['pid'] == 'C24C' and devices[0]['uid'] == uid and devices[0]['deviceid'] == device
            and len(receivers) == 1 and receivers[0]['DeviceId'] == device and receivers[0]['Name'] == 'iMouse2-C24C'
            and len(calibration) == 1 and calibration[0].get('Pid') == 'C24C'
            and (calibration[0].get('Width'), calibration[0].get('Height')) == (500, 1080))


def main():
    live = HERE/'live'
    if RUN.exists() or (live/'preparation.json').exists():
        raise SystemExit('This window is already prepared; never overwrite or reuse it.')
    previous = load(P2/'preparation.json')
    kernel = Path(previous['kernel'])
    if sha(kernel.with_suffix('.dll')) != previous['kernelSha256']: raise SystemExit('The verified private kernel changed.')
    image = kernel.with_suffix('.dll').read_bytes()
    if not all(text.encode('utf-16-le') in image for text in PROBE_STRINGS):
        raise SystemExit('This kernel build does not contain the move-only absolute probe.')
    source = Path(previous['runDirectory'])/'data'
    if not c24c_only(source, previous['expectedUid'], previous['expectedDeviceId']): raise SystemExit('C24C-only mapping changed.')
    protected = load(P2/'protected-before.json')
    for value in protected:
        if sha(value['path']) != value['sha256']: raise SystemExit('Protected installed file changed: ' + value['path'])
    original = previous['arguments']
    receiver, runtime = Path(original[original.index('--receiver')+1]), Path(original[original.index('--receiver-runtime')+1])
    if not receiver.is_file() or not runtime.is_dir(): raise SystemExit('The verified private receiver or its runtime is missing.')
    if original[0] != 'http://127.0.0.1:9916/api/' or original[original.index('--input-pid')+1] != 'C24C':
        raise SystemExit('The verified kernel arguments are not the isolated C24C kernel on 9916.')

    parts = {}
    for part, extra in (('A', []), ('B', PROBE_ARGUMENTS)):
        data = RUN/('data-' + part); data.mkdir(parents=True)
        for name in MAPPING:
            shutil.copyfile(source/name, data/name)
            if sha(data/name) != sha(source/name): raise SystemExit('Mapping copy is not byte-identical.')
        arguments = [str(data) if a == str(source) else str(data/'receivers.json') if a == str(source/'receivers.json') else a
                     for a in original] + extra
        if str(source) in ' '.join(arguments): raise SystemExit('Kernel arguments still reference the previous window.')
        parts[part] = dict(arguments=arguments, data=str(data), mapping={name: sha(data/name) for name in MAPPING},
                           absoluteProbe=bool(extra), kernel='move-only absolute probe' if extra else 'normal private kernel')
    (RUN/'trials').mkdir()

    import farm_prompt_validation as steps  # Loads every module the window steps use; no socket or service.
    tools = (ROOT/'tools').resolve()
    loaded = sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == tools})
    sources = {path.relative_to(ROOT).as_posix(): sha(path) for path in loaded}
    sources['tools/Read-FarmImageText.ps1'] = sha(ROOT/'tools/Read-FarmImageText.ps1')
    preparation = dict(
        prepared=datetime.now(timezone.utc).isoformat(), root=str(ROOT), runDirectory=str(RUN), windowRecord=str(HERE/'window'),
        python=PYTHON, kernel=str(kernel), kernelSha256=previous['kernelSha256'], kernelProbeStrings=list(PROBE_STRINGS),
        kernelSource='9fa7a859bbeb60495cdbbda326d25010c3ba7961 (contains probe commit 373dd58)', kernelUrl=steps.KERNEL_URL,
        expectedDeviceId=previous['expectedDeviceId'], expectedUid=previous['expectedUid'], receiver=str(receiver),
        receiverSha256=sha(receiver), receiverRuntime=str(runtime), parts=parts, productSources=sources,
        probePoints=[list(p) for p in steps.PROBE_POINTS], protectedFiles=len(protected), mappingFrom=str(source),
        serviceStarted=False, phoneInput=False, desktopControl=False, backend=None)
    live.mkdir(exist_ok=True)
    (live/'preparation.json').write_text(json.dumps(preparation, indent=2), encoding='utf-8')
    (live/'protected-before.json').write_text(json.dumps(protected, indent=2), encoding='utf-8')
    print(json.dumps(dict(prepared=True, run=str(RUN), sources=len(sources), protectedFiles=len(protected),
                          serviceStarted=False, phoneInput=False)))


if __name__ == '__main__':
    main()
