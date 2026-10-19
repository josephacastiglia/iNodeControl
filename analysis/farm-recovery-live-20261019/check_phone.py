"""Read-only C24C identity, ownership and profile before the live inspection."""
import hashlib
import io
import json
from pathlib import Path
import sys
from PIL import Image

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from farm_live_verification import ReadOnlyKernel, validate_runtime, idle
from farm_observations import WindowsOcr, classify
prep=json.loads((HERE/'preparation.json').read_bytes())
processes=json.loads((HERE/'processes.json').read_text(encoding='utf-8-sig'))
kernel=ReadOnlyKernel('http://127.0.0.1:9916/api')
status=kernel.kernel_status();devices=kernel.devices()
identity=validate_runtime(status,devices,prep['kernelSha256'],prep['expectedUid'])
if status['process']['pid']!=processes['kernel']['pid']:raise RuntimeError('Kernel PID changed.')
state=kernel.input_status()[prep['expectedDeviceId']]
if not idle(state):raise RuntimeError('C24C is not free. No takeover is permitted.')
raw,headers=kernel.shot('C24C')
text=WindowsOcr().read(raw)
result=classify(text,dict(platform='instagram',account='xs.halle.xo',caption=''),raw)
record=dict(kernel=status,devices=devices,input=state,headers=headers,text=text,result=result,
    frameSha256=hashlib.sha256(raw).hexdigest(),phoneInput=False,desktopControl=False,
    freshnessClaim=False,meaning='Read-only profile admission only; action decisions must obtain new owned frames.')
(HERE/'profile-before.bmp').write_bytes(raw)
with Image.open(io.BytesIO(raw)) as image:image.convert('RGB').save(HERE/'profile-before.png')
(HERE/'phone-preflight.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
if result['screen']!='profile' or result['accountStatus']!='exact_text_match':
    raise RuntimeError('The exact authorized Instagram profile is not recognized.')
print(json.dumps(dict(ready=True,account='xs.halle.xo',generation=state['generation'],
    kernelPid=status['process']['pid'],receiverPid=status['receivers'][0]['receiver_pid'],phoneInput=False)))
