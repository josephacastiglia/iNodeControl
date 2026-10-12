"""Inspect receiver/runtime files without starting UxPlay or GStreamer.

Uses objdump only to read PE imports. Does not load DLLs or validate discovery,
decoding, dynamic plugins, Windows loader resolution, or redistribution rights.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

PLUGIN_FILES = ("libgstapp.dll", "libgstcoreelements.dll", "libgstlibav.dll",
                "libgstvideoparsersbad.dll", "libgstvideoconvertscale.dll")


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def imports(objdump, path):
    result = subprocess.run([str(objdump), "-p", str(path)], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=15)
    if result.returncode or "file format pei-x86-64" not in result.stdout:
        raise ValueError(f"Not a readable x64 PE: {path.name}")
    names = re.findall(r"DLL Name:\s*(\S+)", result.stdout)
    if any(not re.fullmatch(r"[A-Za-z0-9_+.-]+\.dll", name, re.I) for name in names):
        raise ValueError("Unsafe DLL name in import table")
    return names


def audit(receiver, runtime, system_dir, inspect):
    receiver, runtime, system_dir = map(Path, (receiver, runtime, system_dir))
    errors, files, dependencies, contracts = [], {}, [], set()
    def directory_index(folder):
        if not folder.is_dir():
            errors.append(f"Missing directory: {folder}")
            return {}
        result = {}
        for path in folder.iterdir():
            if path.is_file():
                name = path.name.casefold()
                if name in result:
                    errors.append(f"Case-colliding file: {folder / name}")
                result[name] = path
        return result
    bins = directory_index(runtime / "bin")
    system = directory_index(system_dir)
    root_files = directory_index(receiver.parent)
    plugins = runtime / "lib/gstreamer-1.0"
    pending = [receiver, runtime / "libexec/gstreamer-1.0/gst-plugin-scanner.exe"]
    pending += [plugins / name for name in PLUGIN_FILES]
    seen = set()
    while pending:
        path = pending.pop()
        key = str(path.absolute()).casefold()
        if key in seen:
            continue
        seen.add(key)
        if len(seen) > 512:
            errors.append("Dependency graph exceeded 512 files")
            break
        if not path.is_file():
            errors.append(f"Missing file: {path}")
            continue
        try:
            names = inspect(path)
            files[str(path)] = {"sha256": sha(path), "bytes": path.stat().st_size}
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            errors.append(f"Inspection failed for {path.name}: {error}")
            continue
        local = directory_index(path.parent)
        for name in names:
            if not re.fullmatch(r"[A-Za-z0-9_+.-]+\.dll", name, re.I):
                errors.append(f"Invalid import name in {path.name}")
                continue
            lowered = name.casefold()
            if lowered.startswith(("api-ms-win-", "ext-ms-win-")):
                contracts.add(lowered)
                continue
            found = local.get(lowered) or root_files.get(lowered) or bins.get(lowered)
            if found:
                dependencies.append({"from": path.name, "dll": name, "resolved": str(found), "kind": "candidate_file"})
                pending.append(found)
            elif lowered in system:
                dependencies.append({"from": path.name, "dll": name, "resolved": str(system[lowered]), "kind": "system_file_present"})
            else:
                errors.append(f"Unresolved import: {path.name} -> {name}")
    return {"schema_version": 1, "files_consistent": not errors, "launch_ready": False,
            "receiver_started": False, "dlls_loaded": False, "errors": errors,
            "files": files, "dependencies": dependencies, "windows_api_contracts": sorted(contracts),
            "limits": ["This is a bounded file/dependency inventory, not Windows loader emulation.",
                       "System files and API-set contracts are not recursively validated or attested.",
                       "Only the selected software-video pipeline plugins are seeded; dynamic/optional plugins can need more files.",
                       "No discovery, networking, plugin loading, decoding, phone input or license acceptance is tested."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("receiver", "runtime", "system-dir", "objdump", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    # Refuse before invoking the inspection utility if evidence already exists.
    if args.out.exists():
        parser.error("output already exists; choose a new evidence file")
    report = audit(args.receiver, args.runtime, args.system_dir, lambda p: imports(args.objdump, p))
    report["inspector"] = {"path": str(args.objdump), "sha256": sha(args.objdump)}
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    print(f"{len(report['files'])} native files inspected; {len(report['errors'])} errors; no receiver started.")
    for error in report["errors"]:
        print(error)
    return 0 if report["files_consistent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
