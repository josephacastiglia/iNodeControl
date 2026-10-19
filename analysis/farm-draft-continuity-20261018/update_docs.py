from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=ROOT/'MARKETING-FARM-STATUS.md';s=p.read_text(encoding='utf-8')
s=s.replace('## Latest candidate: account, media and reopened-draft evidence','## Earlier candidate: account, media and reopened-draft evidence',1)
head='''## Latest candidate: complete slide checks and account-history audit

Candidate `output/codex-farm-continuity-20261018`, DLL SHA-256 `70ab2b31cf2beb5258febd3a5c28d27331a8634c2084e20358c7d8b7dbfc8bc4`. **234 Python tests and 505 native headless checks pass**; clean Release build. The candidate launcher uses separate settings and a simulation backend. No PC control, publishing, messaging or installed-release changes.

Library matching now accounts for the observed gradient/badge and searches the visible grid, requiring a unique cover. Full-size editor images must match every source slide and their page-dot positions/count. All stored account-interval observations are audited, including unselected switches, interruptions and pruned/failed captures. The native review displays coverage and intervening evidence.

**Live C24C component checks passed:** exact account-before, library cover in the second cell, all three reopened slides in order and full saved caption. Another controller acquired C24C before the account-after check; preflight stopped our input. Our lease was released, and no further phone input was sent. C241 received no input. The installed kernel lacks paired frame-age metadata, so **full saved-draft/account-continuity acceptance remains incomplete**. Sampled history never proves activity between captures. See [the report](analysis/farm-draft-continuity-20261018/README.md).

'''
pos=s.index('## Earlier candidate: account')
s=s[:pos]+head+s[pos:];p.write_text(s,encoding='utf-8')
p=ROOT/'MARKETING-FARM-ACCEPTANCE.md';s=p.read_text(encoding='utf-8')
s=s.replace('output/codex-farm-verification-20261018','output/codex-farm-continuity-20261018',1)
s=s.replace('36c8645d0bebb5d92c928a2cce85e5970e8d7ae4056409b45edb4c6976b9c188','70ab2b31cf2beb5258febd3a5c28d27331a8634c2084e20358c7d8b7dbfc8bc4',1)
s=s.replace('**223 Python tests**','**234 Python tests**',1).replace('**502 native headless checks**','**505 native headless checks**',1)
s=s.replace('This pass used saved C24C images and isolated mocks only, with no rack API calls or PC control.','This pass inspected the existing C24C test draft through leased APIs, with no PC control. Another controller acquired C24C before the account-after check; no further input was sent.')
old=next(line for line in s.splitlines() if line.startswith('| Carousel evidence comparison |'))
new='| Carousel evidence comparison | Unique library-cover matching across the supported grid, full-size slides plus page-dot count/order, exact caption, all stored observations between account boundaries, immutable source/screens and recovery. Live C24C account-before, moved cover, all three reopened slides and caption match | Account-after interrupted by another controller; paired age unavailable on release. Full saved-draft acceptance remains open. Sampled history is not continuous account tracking; save transitions and independent broader-layout testing still needed. No input enabled by review |'
s=s.replace(old,new);p.write_text(s,encoding='utf-8')
