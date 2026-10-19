"""Read-only comparison of the archived vendor capture; no instrumentation is started."""
import hashlib
import json
from pathlib import Path


def main():
    repo = Path(__file__).resolve().parents[3]
    capture = repo / "analysis/hid-keys-20260914.jsonl"
    markers = repo / "analysis/hid-key-markers.jsonl"
    events = [json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines()]
    commands = [json.loads(line) for line in markers.read_text(encoding="utf-8").splitlines()]
    # One known six-character test string, before the next Home command.
    start = next(i for i, row in enumerate(commands) if row["action"] == "/key/sendkey?key=%20Ab%20Z%21")
    low, high = commands[start]["time"] / 1000, commands[start + 1]["time"] / 1000
    reports = []
    for row in events:
        payload = row.get("message", {}).get("payload", {})
        if not low <= row["time"] < high or payload.get("event") != "output" or payload.get("api") != "WriteFile":
            continue
        raw = bytes.fromhex(payload["hex"])
        if len(raw) == 9 and raw[:2] == b"\0\xa2":
            reports.append((row["time"], raw[1:].hex().upper()))
    down = [raw for _, raw in reports if raw[4:6] != "00"]
    expected = ["A2002C0000000000", "A202040000000000", "A200050000000000", "A2002C0000000000", "A2021D0000000000", "A2021E0000000000"]
    assert down == expected, down
    holds = []
    for i, (time, raw) in enumerate(reports):
        if raw == "A2002C0000000000":
            assert i + 1 < len(reports) and reports[i + 1][1] == "A200000000000000"
            holds.append(round((reports[i + 1][0] - time) * 1000, 3))
    result = {
        "offline": True,
        "boundary": "historical vendor user-mode WriteFile hook; not USB completion or iOS insertion",
        "text": " Ab Z!",
        "expected_down_reports_match": True,
        "space_down": "A2002C0000000000",
        "space_holds_ms": holds,
        "original_report_id": 0,
        "sources": [{"path": str(p.relative_to(repo)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in (capture, markers)],
    }
    path = Path(__file__).with_name("vendor-comparison.json")
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
