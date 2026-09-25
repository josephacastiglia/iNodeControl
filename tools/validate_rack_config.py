"""Gate 11 rack checks. Mirrors ReceiverFleet.Validate plus the 19-slot map."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "analysis" / "full-rack-config"
PIPE = re.compile(r"^[A-Za-z0-9-]+$")
MAC = re.compile(r"^02(:[0-9A-Fa-f]{2}){5}$")
# HARDWARE.md hubs. Port 10-04 and 11-05 are empty and must not appear.
SLOTS = [
    (9, 1, "E414"), (9, 2, "3523"), (9, 3, "C415"), (9, 4, "764E"),
    (9, 5, "374C"), (9, 6, "3848"), (9, 7, "D446"),
    (10, 1, "C24C"), (10, 2, "C241"), (10, 3, "C214"),
    (10, 5, "724E"), (10, 6, "F215"), (10, 7, "9515"),
    (11, 1, "7949"), (11, 2, "704E"), (11, 3, "694E"), (11, 4, "1248"),
    (11, 6, "1814"), (11, 7, "D142"),
]
KNOWN = {
    "C24C": "86:1D:4A:04:2F:F6",
    "C241": "FE:A9:BC:D7:A0:44",
    "C214": "8A:23:B5:71:35:8D",
    "724E": "3A:DC:15:FB:DD:EC",
    "F215": "D6:5E:EE:14:38:88",
}


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def main():
    receivers, devices, cals = load("receivers.json"), load("devices.json"), load("pointer-calibration.json")
    errors = []

    def check(ok, msg):
        print(("ok  " if ok else "FAIL") + " " + msg)
        if not ok:
            errors.append(msg)

    pids = [pid for _, _, pid in SLOTS]
    by_pid = {r["BoardPid"]: r for r in receivers}
    dev_by_pid = {d["pid"]: d for d in devices}
    cal_by_pid = {c["Pid"]: c for c in cals}

    check(len(receivers) == 19 and len(by_pid) == 19, f"19 unique receiver boards ({len(receivers)})")
    check(len(devices) == 19 and len(dev_by_pid) == 19, f"19 unique devices ({len(devices)})")
    check(sorted(by_pid) == sorted(pids), "receiver PIDs match the 19-slot rack")

    for hub, port, pid in SLOTS:
        label = f"Slot {hub:02d}-{port:02d} ({pid})"
        check(dev_by_pid.get(pid, {}).get("name") == label, f"slot label {label}")

    for c in receivers:
        pid = c["BoardPid"]
        discovery = c["DeviceId"] in ("*", "")
        window_ok = not (c["Port"] <= 5353 <= c["Port"] + 2)
        ident = (
            (discovery or str(c["DeviceId"]).strip() != "")
            and str(c["Name"]).startswith("iMouse2-")
            and PIPE.fullmatch(c["Pipe"] or "")
            and MAC.fullmatch(c["Mac"] or "")
            and 1024 <= c["Port"] <= 65533
            and window_ok
        )
        check(ident, f"identity/ports {pid}")
        check(c["Name"] == f"iMouse2-{pid}" and c["Pipe"] == f"iMouse2-{pid}-frames", f"name/pipe {pid}")
        if pid in KNOWN:
            check(c["DeviceId"] == KNOWN[pid], f"known device id {pid}")
        elif not discovery:
            check(c["DeviceId"] == f"unbound-{pid}", f"placeholder device id {pid}")
        if not discovery:
            hits = [d for d in devices if d["deviceid"] == c["DeviceId"] and d["pid"] == pid]
            check(len(hits) == 1, f"phone/board binding {pid}")

    for key in ("DeviceId", "BoardPid", "Name", "Pipe", "Mac"):
        vals = [str(c[key]) for c in receivers]
        check(len({v.casefold() for v in vals}) == len(vals), f"unique {key}")

    occupied = [p for c in receivers for p in range(c["Port"], c["Port"] + 3)]
    check(len(set(occupied)) == len(receivers) * 3, "port windows do not overlap")
    check(sorted(c["Port"] for c in receivers) == list(range(7110, 7300, 10)), "ports 7110..7290 step 10")

    check(len(cals) == 19 and set(cal_by_pid) == set(pids), "calibration covers all 19 PIDs")
    for pid in pids:
        cal = cal_by_pid.get(pid, {})
        check(
            cal.get("Width") == 500 and cal.get("Height") == 1080
            and cal.get("OriginX") == 14 and cal.get("OriginY") == 14
            and cal.get("PixelsPerUnitX") == 5.1 and cal.get("PixelsPerUnitY") == 5.1,
            f"calibration {pid}",
        )

    if errors:
        print(f"{len(errors)} check(s) failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
