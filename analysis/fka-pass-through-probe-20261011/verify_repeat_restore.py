"""Read-only final verification of the repeated typing window."""
import hashlib
import json
import os
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

record=Path(__file__).resolve().parent
repo=record.parents[1]
main=repo.parent/'iMouseXP-2.0'
live=record/'live-repeat-20261011'
out=live/'restoration-verified.json'
assert not out.exists(), 'Refusing to overwrite restoration evidence'
def load(name): return json.loads((live/name).read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def get(p): return json.loads(urllib.request.urlopen('http://127.0.0.1:9913/api/'+p,timeout=5).read())['data']
before=load('preflight-hashes.json')
restored=load('release-kernel-restored.json')
console=load('console-restored.json')
paths={
 'operator_settings_sha256':Path(os.environ['APPDATA'])/'iMouse2/settings.json',
 'release_kernel_sha256':main/'release/iMouse2-kernel-two-phone/iMouse2.Kernel.dll',
 'release_console_sha256':main/'release/iMouse2-two-phone-candidate/iMouse2.dll',
 'receiver_sha256':main/'tools/airplay/uxplay/build-imouse/uxplay.exe',
 'candidate_kernel_sha256':record/'build/iMouse2.Kernel.dll',
 'candidate_console_sha256':live/'candidate/iMouse2.dll',
}
hashes={k:sha(p) for k,p in paths.items()}
assert all(hashes[k]==before[k] for k in hashes), 'Binary/settings hash changed'
stable=[]
for line in (live/'release-snapshot/SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
 digest,relative=line.split('  ',1)
 if relative.startswith('release/') or relative in ('Open iMouse 2.0.ps1','analysis/two-phone-config/devices.json','analysis/two-phone-config/receivers.json','analysis/two-phone-config/pointer-calibration.json'):
  assert sha(main/relative)==digest, relative
  stable.append(relative)
command="$ErrorActionPreference='Stop'; @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('iMouse2.Kernel.exe','iMouse2.exe','uxplay.exe') } | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine) | ConvertTo-Json -Depth 4"
processes=json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-Command',command],text=True,encoding='utf-8-sig'))
kernel=get('kernel/status')
states=get('input/status')
assert kernel['allowed']==['C24C','C241'] and len(kernel['receivers'])==2 and all(r['live'] for r in kernel['receivers'])
assert {r['deviceid'] for r in kernel['receivers']}=={'86:1D:4A:04:2F:F6','FE:A9:BC:D7:A0:44'}
expected={restored['kernel_pid']:main/'release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe',console['console']['ProcessId']:main/'release/iMouse2-two-phone-candidate/iMouse2.exe'}
for receiver in kernel['receivers']: expected[receiver['receiver_pid']]=paths['receiver_sha256']
assert len(processes)==4 and {p['ProcessId'] for p in processes}==set(expected), 'Unexpected rack/test process'
for process in processes:
 assert Path(process['ExecutablePath'])==expected[process['ProcessId']]
 if process['ProcessId'] in {r['receiver_pid'] for r in kernel['receivers']}:
  assert process['ParentProcessId']==restored['kernel_pid']
assert len(states['phones'])==2
assert not any(p['active'] or p['stopped'] or p['releasing'] or p['release_failed'] for p in states['phones'])
other=next(p for p in states['phones'] if p['id']=='FE:A9:BC:D7:A0:44')
assert not other['owned'] and other['generation']==0, 'Unexpected C241 history'
assert (live/'fka-final-restored/before.png').is_file(), 'Final FKA frame missing'
result={'utc':datetime.now(timezone.utc).isoformat(),'hashes':hashes,'stable_files_verified':stable,'processes':processes,'kernel':kernel,'input':states,'settings_content_unchanged':True,'settings_mtime_ns_before':before['operator_settings_mtime_ns'],'settings_mtime_ns_after':paths['operator_settings_sha256'].stat().st_mtime_ns,'both_phones_mirroring':True,'test_processes_gone':True,'FKA_restoration_frame':'fka-final-restored/before.png','C241_test_input':'None; not in test configuration or any test request'}
out.write_text(json.dumps(result,indent=2),encoding='utf-8')
print('Release, mirroring, FKA evidence, no test processes and unchanged binary/config/settings hashes verified.')
print('Later release phone ownership:',json.dumps([(p['id'],p['owned']) for p in states['phones']]))

