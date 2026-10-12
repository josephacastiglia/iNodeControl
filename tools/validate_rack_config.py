"""Check saved rack configuration offline, without contacting or opening hardware.

Exit 0: valid configuration with explicit bindings (or --structure-only).
Exit 1: invalid input. Exit 2: valid structure, incomplete bindings.
No outcome establishes physical identity, calibration accuracy, or gate acceptance.
"""
import argparse
import json
import math
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


def read_records(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON property: {key}")
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError(f"non-finite JSON number: {value}")
    data = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=pairs,
                      parse_constant=reject_constant)
    if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
        raise ValueError(f"{path.name} must contain an array of objects")
    return data


def valid_axis(size, origin, scale):
    def number(n):
        try:
            return type(n) in (int, float) and math.isfinite(n)
        except OverflowError:
            return False
    if type(size) is not int or not 2 <= size <= 2147483647:
        return False
    if not number(origin) or not number(scale) or scale <= 0:
        return False
    first, last = -origin / scale, (size - 1 - origin) / scale
    return (math.isfinite(first) and math.isfinite(last)
            and round(first) > -2147483648 and round(last) < 2147483647)


def validate(receivers, devices, calibrations, template=False):
    errors, blockers = [], []
    def require(ok, message):
        if not ok:
            errors.append(message)
    def index(rows, key, label):
        result = {}
        for i, row in enumerate(rows):
            value = row.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{label} row {i + 1}: missing {key}")
                continue
            value = value.casefold()
            if value in result:
                errors.append(f"{label}: duplicate {key}")
            result[value] = row
        return result
    def unique(rows, key):
        values = [r.get(key) for r in rows]
        require(all(isinstance(v, str) for v in values), f"receiver {key} must be text")
        strings = [v.casefold() for v in values if isinstance(v, str)]
        require(len(strings) == len(set(strings)), f"duplicate receiver {key}")
    require(1 <= len(receivers) <= 19, "receiver count must be 1 through 19")
    by_board = index(receivers, "BoardPid", "receiver")
    by_device_board = index(devices, "pid", "device")
    by_cal_board = index(calibrations, "Pid", "calibration")
    index(devices, "deviceid", "device")
    require(set(by_board) == set(by_device_board), "device boards must match receiver boards")
    require(set(by_board) == set(by_cal_board), "calibration boards must match receiver boards")
    for key in ("DeviceId", "BoardPid", "Name", "Pipe", "Mac"):
        unique(receivers, key)
    ports = set()
    incomplete = []
    for i, receiver in enumerate(receivers):
        label = f"receiver row {i + 1}"
        board, device = receiver.get("BoardPid"), receiver.get("DeviceId")
        if isinstance(board, str) and board.strip():
            label = board
        require(isinstance(board, str) and re.fullmatch(r"[0-9A-Fa-f]{4}", board) is not None,
                f"{label}: board PID must be four hexadecimal characters")
        require(isinstance(device, str), f"{label}: DeviceId must be text")
        discovery = device in ("*", "")
        placeholder = isinstance(device, str) and device.casefold().startswith("unbound-")
        require(discovery or isinstance(device, str) and bool(device.strip()), f"{label}: blank identity")
        if discovery or placeholder:
            incomplete.append(label)
        for key, pattern in (("Name", r"iMouse2-.+"), ("Pipe", r"[A-Za-z0-9-]+"),
                             ("Mac", r"02(:[0-9A-Fa-f]{2}){5}")):
            value = receiver.get(key)
            require(isinstance(value, str) and re.fullmatch(pattern, value) is not None,
                    f"{label}: invalid {key}")
        port = receiver.get("Port")
        if type(port) is not int or not 1024 <= port <= 65533:
            errors.append(f"{label}: invalid port")
        else:
            window = set(range(port, port + 3))
            require(5353 not in window, f"{label}: port window includes mDNS")
            require(not ports.intersection(window), f"{label}: overlapping port window")
            ports.update(window)
        if not discovery:
            matches = [d for d in devices if d.get("deviceid") == device and d.get("pid") == board]
            require(len(matches) == 1, f"{label}: receiver must match one exact phone/board binding")
    for i, cal in enumerate(calibrations):
        require(valid_axis(cal.get("Width"), cal.get("OriginX"), cal.get("PixelsPerUnitX"))
                and valid_axis(cal.get("Height"), cal.get("OriginY"), cal.get("PixelsPerUnitY")),
                f"calibration row {i + 1}: invalid dimensions, origin or scale")
    if template:
        require(set(by_board) == {pid.casefold() for _, _, pid in SLOTS}, "boards must match all 19 planned slots")
        for hub, port, pid in SLOTS:
            row = by_device_board.get(pid.casefold(), {})
            require(row.get("name") == f"Slot {hub:02d}-{port:02d} ({pid})", f"{pid}: wrong planned slot label")
        for board, expected_id in KNOWN.items():
            require(by_board.get(board.casefold(), {}).get("DeviceId") == expected_id,
                    f"{board}: known template binding differs")
    if incomplete:
        blockers.append(f"{len(incomplete)} receiver(s) use discovery or unbound identities")
    return {"schema_version": 1, "configuration_valid": not errors,
            "bindings_complete": not errors and not incomplete,
            "receiver_count": len(receivers), "explicit_binding_count": len(receivers) - len(incomplete),
            "incomplete_boards": incomplete, "errors": errors, "blockers": blockers,
            "hardware_contacted": False, "physical_readiness": "not_assessed", "gate11_acceptance": False,
            "limits": ["Saved identities are not proof of physical phone/board mapping.",
                       "Calibration values are checked for valid arithmetic, not targeting accuracy.",
                       "Ports are checked within this file; active listeners, runtimes and mirroring are not inspected."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path, help="saved candidate folder; default checks the planned 19-slot template")
    parser.add_argument("--structure-only", action="store_true", help="allow placeholders in the exit status; report still lists them")
    parser.add_argument("--report", type=Path, help="write JSON to a new file; never overwrite an existing record")
    args = parser.parse_args(argv)
    folder = args.config_dir or ROOT
    try:
        report = validate(*(read_records(folder / name) for name in
                          ("receivers.json", "devices.json", "pointer-calibration.json")),
                          template=args.config_dir is None)
    except (OSError, ValueError, OverflowError) as error:
        print(f"Invalid configuration: {error}", file=sys.stderr)
        return 1
    if args.report:
        try:
            with args.report.open("x", encoding="utf-8") as handle:
                json.dump(report, handle, indent=2, allow_nan=False)
                handle.write("\n")
        except OSError as error:
            print(f"Report not saved: {error}", file=sys.stderr)
            return 1
    for error in report["errors"]:
        print("FAIL: " + error)
    for blocker in report["blockers"]:
        print("INCOMPLETE: " + blocker)
    print(f"{report['receiver_count']} receivers; {report['explicit_binding_count']} explicit saved bindings.")
    print("Structure " + ("valid" if report["configuration_valid"] else "INVALID") + "; physical readiness NOT assessed.")
    if not report["configuration_valid"]:
        return 1
    return 0 if report["bindings_complete"] or args.structure_only else 2


if __name__ == "__main__":
    sys.exit(main())
