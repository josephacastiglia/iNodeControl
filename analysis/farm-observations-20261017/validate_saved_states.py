"""Check screen patterns against labelled, private captured evidence. No phone calls."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from farm_observations import classify

RUN = Path(__file__).resolve().parent
states = {7: ('tiktok', 'profile'), 31: ('x', 'account_menu'), 51: ('youtube', 'profile'),
          84: ('instagram', 'sharing_dialog'), 87: ('instagram', 'share_sheet'),
          107: ('tiktok', 'profile'), 108: ('tiktok', 'draft_library'), 111: ('tiktok', 'draft_details'),
          124: ('x', 'draft_library'), 125: ('x', 'draft_details'), 132: ('youtube', 'permission_prompt'),
          147: ('youtube', 'draft_library'), 149: ('youtube', 'draft_details'), 154: ('instagram', 'profile'),
          164: ('instagram', 'draft_library'), 165: ('instagram', 'draft_details'), 166: ('instagram', 'draft_preview'), 168: ('instagram', 'home')}
reports = []
for file in sorted(RUN.glob('*-ocr.json')):
    number = int(file.name.split('-')[0]); platform, expected_state = states[number]
    result = classify(json.loads(file.read_text(encoding='utf-8')), {'platform': platform, 'account': 'unrelated.test.account', 'caption': 'IMOUSE-VIDEO-DRAFT-TEST-20261017'})
    reports.append({'frame': file.name, 'expectedState': expected_state, 'actualState': result['screen'],
                    'matched': result['screen'] == expected_state, 'accountAccepted': result['accountStatus'] == 'exact_text_match',
                    'captionStatus': result['captionStatus'], 'inputAllowed': result['automaticInputAllowed']})
(RUN / 'saved-state-results.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')
print(json.dumps({'screensMatched': sum(r['matched'] for r in reports), 'total': len(reports),
                  'wrongAccountsAccepted': sum(r['accountAccepted'] for r in reports), 'inputsAllowed': sum(r['inputAllowed'] for r in reports),
                  'mismatches': [r for r in reports if not r['matched']]}))
