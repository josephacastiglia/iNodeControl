"""Read-only status and C24C screenshot headers; never acquire or send input."""
import hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; RUN=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tools'))
from imouse_social_automation import IMouseKernel
kernel=IMouseKernel(); result=dict(phoneInput=False,desktopControl=False)
settings=Path(os.environ['APPDATA'])/'iMouse2/settings.json'
result['operatorSettingsSha256']=hashlib.sha256(settings.read_bytes()).hexdigest() if settings.exists() else None
try:
    result['status']=kernel.kernel_status(); result['inputBefore']=kernel.input_status()
    resolved=kernel.resolve_device_id('C24C')
    receiver=next(r for r in result['status']['receivers'] if r['deviceid']==resolved)
    result['c24cLive']=receiver.get('live'); result['c24cOwned']=result['inputBefore'].get(resolved,{}).get('owned')
    if result['c24cLive']:
        raw,headers=kernel.shot('C24C')
        result['screenshotBytes']=len(raw)
        result['pairedHeaderNames']=[k for k in headers if k.lower().startswith('x-imouse-frame-')]
        result['pairedHeadersPresent']=all(any(k.lower()=='x-imouse-frame-'+name for k in headers) for name in ('session','sequence','age-ms','delivery'))
    result['inputAfter']=kernel.input_status()
    result['inputGenerationsUnchanged']=all(result['inputAfter'].get(k,{}).get('generation')==v.get('generation') for k,v in result['inputBefore'].items())
except Exception as error: result['error']=str(error)
assert all(row['fun']=='/input/status' for row in kernel.audit_log)
(RUN/'rack-readonly.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:result.get(k) for k in ('phoneInput','c24cLive','c24cOwned','pairedHeadersPresent','inputGenerationsUnchanged','error')}))
