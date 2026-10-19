import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools'))
from farm_observations import WindowsOcr, classify
from farm_draft_rehearsal import save_prompt
frame=ROOT/'analysis/farm-phone-transfer-20261017/45-draft-exit-menu/after.png'
raw=frame.read_bytes(); text=WindowsOcr().read(raw)
result=dict(source='archived_phone_frame_not_current_live_validation',frameSha256=hashlib.sha256(raw).hexdigest(),
    promptRecognized=save_prompt(text),classification=classify(text,dict(platform='instagram',account='simulation.account',caption=''))['screen'],text=text)
(Path(__file__).parent/'saved-prompt-check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='text'}))
