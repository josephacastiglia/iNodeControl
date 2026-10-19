import json,sys,io
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];RUN=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
from imouse_social_automation import IMouseKernel
k=IMouseKernel('http://127.0.0.1:9913/api')
record={'phoneInput':False}
try:
    record['status']=k.kernel_status()
    record['preflight']=k.preflight_phone('C24C')
    raw,headers=k.shot('C24C'); record['headers']=headers
    Image.open(io.BytesIO(raw)).save(RUN/'live-before.png')
    record['endInput']=k.input_status()
    print(json.dumps({'ready':True,'pairedMetadata':any(key.lower().startswith('x-imouse-frame-session') for key in headers)}))
except Exception as error:
    record['error']=str(error); print(json.dumps({'ready':False,'reason':str(error)}))
finally:
    record['audit']=k.audit_log
    assert all(e['fun']=='/input/status' for e in k.audit_log)
    (RUN/'read-only-preflight.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
