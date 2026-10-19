import json
import re
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[2]
git = ['git', '-c', 'safe.directory=' + root.as_posix()]
diff = subprocess.check_output(git + ['diff', '--cached', '--unified=0'], cwd=root).decode('utf-8')
added = '\n'.join(line[1:] for line in diff.splitlines() if line.startswith('+') and not line.startswith('+++'))
patterns = [r'(?i)\b(?:sk|ghp|github_pat)-[a-z0-9_]{20,}', r'(?i)-----BEGIN .*PRIVATE KEY-----',
            r'(?i)\b(?:password|api_key|access_token)\s*[:=]\s*[\"\'][^\"\']{8,}[\"\']',
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b']
hits = sum(len(re.findall(pattern, added)) for pattern in patterns)
print(json.dumps({'addedLineSecretOrEmailPatternHits': hits, 'rawPrivateEvidenceStaged': False}))
if hits: raise SystemExit('Inspect staged content locally before committing; values not printed.')
