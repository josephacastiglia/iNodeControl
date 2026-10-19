from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
for name in ('tools/imouse_farm_server.py','Open Marketing Farm Candidate.ps1'):
    p=ROOT/name; s=p.read_text(encoding='utf-8')
    if name.endswith('.py'):
        s=s.replace('"farm_draft_verification.py")))','"farm_draft_verification.py", "farm_draft_media.py")))')
        s=s.replace('"draftVerificationVersion": 1','"draftVerificationVersion": 2')
    else:
        s=s.replace("'farm_draft_verification.py'))", "'farm_draft_verification.py', 'farm_draft_media.py'))")
        s=s.replace('codex-farm-verification-20261018','codex-farm-continuity-20261018')
    p.write_text(s,encoding='utf-8')
p=ROOT/'tools/farm_capabilities.py';s=p.read_text(encoding='utf-8')
s=s.replace('Real library-thumbnail matching remains unresolved.','Supports the recorded carousel thumbnail overlay and full-size slide position/count checks. Audits all stored observations between account screens, including unselected interruptions. Activity between samples remains unproven.')
p.write_text(s,encoding='utf-8')
