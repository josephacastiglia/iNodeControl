"""Rebuild UxPlay into a fresh scratch folder, without executing it.

Compare saved objects and PE sections. A matching section is scoped evidence,
not a claim that the entire historical toolchain has been authenticated.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "tools/airplay/uxplay"
RUNTIME = ROOT / "tools/airplay/msys64/ucrt64"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pe_sections(path):
    data = path.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3c)[0]
    if data[pe:pe+4] != b"PE\0\0":
        raise ValueError("not PE")
    count = struct.unpack_from("<H", data, pe+6)[0]
    optional_size = struct.unpack_from("<H", data, pe+20)[0]
    start = pe + 24 + optional_size
    result = {}
    for index in range(count):
        header = start + index * 40
        name = data[header:header+8].rstrip(b"\0").decode("ascii")
        size, offset = struct.unpack_from("<II", data, header+16)
        result[name] = {"bytes": size, "sha256": digest(data[offset:offset+size])}
    return result


def normalized_pe(path):
    """Ignore only COFF/export timestamps and the PE checksum."""
    data = bytearray(path.read_bytes())
    pe = struct.unpack_from("<I", data, 0x3c)[0]
    if data[pe:pe+4] != b"PE\0\0":
        raise ValueError("not PE")
    optional = pe + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic not in (0x10b, 0x20b):
        raise ValueError("unknown optional header")
    export_rva = struct.unpack_from("<I", data, optional + (112 if magic == 0x20b else 96))[0]
    offsets = [(pe+8, 4), (optional+64, 4)]
    count = struct.unpack_from("<H", data, pe+6)[0]
    sections = optional + struct.unpack_from("<H", data, pe+20)[0]
    for i in range(count):
        header = sections + i*40
        virtual_size, rva, raw_size, raw_offset = struct.unpack_from("<IIII", data, header+8)
        if export_rva and rva <= export_rva < rva+min(virtual_size, raw_size):
            offsets.append((raw_offset+export_rva-rva+4, 4))
    for offset, size in offsets:
        if offset+size > len(data): raise ValueError("truncated PE")
        data[offset:offset+size] = b"\0" * size
    return {"sha256": digest(data), "ignored_fields": offsets}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    installed = SRC / "build-imouse/uxplay.exe"
    before = digest(installed.read_bytes())
    source_hashes = {str(p.relative_to(SRC)): digest(p.read_bytes()) for p in SRC.rglob("*")
                     if p.is_file() and "build-imouse" not in p.parts and
                     (p.suffix in (".c", ".cpp", ".h", ".cmake") or p.name == "CMakeLists.txt")}
    env = os.environ.copy()
    env["PATH"] = str(RUNTIME / "bin") + os.pathsep + env.get("PATH", "")
    cmake = str(RUNTIME / "bin/cmake.exe")
    commands = [[cmake, "-S", str(SRC), "-B", str(out / "build"), "-G", "Ninja",
                 "-DCMAKE_BUILD_TYPE=Release", "-DUSE_MDNS=1"],
                [cmake, "--build", str(out / "build"), "-j", "2"]]
    for index, command in enumerate(commands):
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=180)
        (out / f"build-{index}.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"build step {index} failed; see log")
    rebuilt = out / "build/uxplay.exe"
    old_sections, new_sections = pe_sections(installed), pe_sections(rebuilt)
    objects = {}
    for old in (SRC / "build-imouse").rglob("*.obj"):
        rel = old.relative_to(SRC / "build-imouse")
        new = out / "build" / rel
        if new.exists():
            objects[str(rel)] = {"saved_sha256": digest(old.read_bytes()), "rebuilt_sha256": digest(new.read_bytes()),
                                 "equal": old.read_bytes() == new.read_bytes()}
    report = {"commands": commands, "source_sha256": source_hashes,
              "installed_sha256": before, "rebuilt_sha256": digest(rebuilt.read_bytes()),
              "installed_unchanged": before == digest(installed.read_bytes()),
              "sections": {name: {"saved": value, "rebuilt": new_sections.get(name), "equal": value == new_sections.get(name)}
                           for name, value in old_sections.items()}, "objects": objects}
    report["normalized_saved"] = normalized_pe(installed)
    report["normalized_rebuilt"] = normalized_pe(rebuilt)
    report["normalized_equal"] = report["normalized_saved"]["sha256"] == report["normalized_rebuilt"]["sha256"]
    (out / "comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"installed_unchanged": report["installed_unchanged"],
                      "objects_equal": sum(v["equal"] for v in objects.values()), "objects_compared": len(objects),
                      "sections_equal": {k: v["equal"] for k, v in report["sections"].items()}}))
    if not report["installed_unchanged"]:
        raise RuntimeError("installed receiver changed")


if __name__ == "__main__":
    main()
