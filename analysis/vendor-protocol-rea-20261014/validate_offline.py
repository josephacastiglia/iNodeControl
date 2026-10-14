"""Repeat this audit's bounded checks using saved files only; no device access."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import runpy
import sys
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / 'tools'))
from vendor_hid_decode import decode_report


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    targets = json.loads((HERE / 'targets.json').read_text(encoding='utf-8-sig'))
    for target in targets:
        expected = target['sha256'].lower()
        if digest(target['source']) != expected or digest(target['copy']) != expected:
            raise ValueError(f"Target mismatch: {target['name']}")

    runpy.run_path(str(HERE / 'verify_findings.py'), run_name='__main__')
    suite = unittest.defaultTestLoader.discover(str(REPO / 'tools'), pattern='test_vendor_hid_decode.py')
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    (HERE / 'decoder-tests.txt').write_text(output.getvalue(), encoding='utf-8')
    if not result.wasSuccessful():
        raise RuntimeError(output.getvalue())

    captures = json.loads((HERE / 'decoder-capture-checks.json').read_text(encoding='utf-8'))
    for capture in captures:
        source = REPO.parent / 'iMouseXP-2.0' / 'analysis' / capture['file']
        if digest(source) != capture['sha256']:
            raise ValueError(f"Capture hash mismatch: {capture['file']}")
        rows = []
        for line in source.read_text(encoding='utf-8-sig').splitlines():
            payload = json.loads(line).get('message', {}).get('payload', {})
            if payload.get('event') == 'output':
                rows.append(decode_report(bytes.fromhex(payload['hex']), direction='out', framing='windows'))
        actual = (len(rows), dict(Counter(row['kind'] for row in rows)),
                  sum(row.get('vendor_fn') is True for row in rows))
        expected = (capture['output_reports'], capture['decoded_kinds'], capture['fn_reports'])
        if actual != expected:
            raise ValueError(f"Capture decoding mismatch: {capture['file']}: {actual}")

    record = {
        'verified_at_utc': datetime.now(timezone.utc).isoformat(),
        'vendor_originals_and_copies_verified': len(targets),
        'static_checks': len(json.loads((HERE / 'verified-offsets.json').read_text())['checks']),
        'decoder_tests': result.testsRun,
        'historical_output_reports': sum(row['output_reports'] for row in captures),
        'scope': 'Saved files and synthetic cases only; no vendor execution, rack access or physical tests',
    }
    (HERE / 'validation.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
