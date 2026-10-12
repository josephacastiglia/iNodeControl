"""Stage or verify an offline review bundle. Never start, install or stop software."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True
import build_manifest as bm

MANAGED = {"console": "iMouse2", "kernel": "iMouse2.Kernel"}
SUFFIXES = (".dll", ".exe", ".deps.json", ".runtimeconfig.json", ".pdb")
BLOCKERS = [
    "Combined source still needs interactive console and physical acceptance on this build; headless tests are not release sign-off.",
    "Native runtime, GStreamer plugins/scanner, Bonjour and .NET Desktop runtime are external prerequisites, not bundled or attested here.",
    "Per-phone bindings, calibration, receiver identities/ports and isolated console settings require a reviewed candidate configuration.",
    "Physical display, input, recovery, scale and endurance acceptance remains open; this is not a release sign-off.",
]


def safe(root, name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError(f"unsafe package path: {name}")
    parts = name.split("/")
    if any(p in ("", ".", "..") or p.endswith((".", " ")) or
           re.match(r"^(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\.|$)", p, re.I)
           for p in parts) or PurePosixPath(name).is_absolute():
        raise ValueError(f"unsafe package path: {name}")
    root = Path(root).resolve()
    result = root.joinpath(*parts)
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ValueError(f"linked path refused: {name}")
    if not result.resolve().is_relative_to(root):
        raise ValueError(f"path escapes root: {name}")
    return result


def row(path):
    return {"sha256": bm.sha256(path), "bytes": Path(path).stat().st_size}


def load(path):
    def unique(pairs):
        values = {}
        for key, value in pairs:
            if key in values:
                raise ValueError(f"duplicate JSON key: {key}")
            values[key] = value
        return values
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique)


def inventory(root):
    result, names = {}, set()
    for p in sorted(Path(root).rglob("*")):
        relative = p.relative_to(root).as_posix()
        safe(root, relative)
        if not p.is_file():
            continue
        if relative.casefold() in names:
            raise ValueError(f"case-colliding path: {relative}")
        names.add(relative.casefold())
        if relative != "package.json":
            result[relative] = row(p)
    return result


def verify(bundle):
    bundle = Path(bundle).resolve()
    manifest = load(safe(bundle, "package.json"))
    if manifest.get("schema_version") != 1 or manifest.get("status") != "review_only" or manifest.get("launch_allowed") is not False:
        raise ValueError("This verifier accepts review-only bundles; no launch approval is recorded")
    if manifest.get("blockers") != BLOCKERS:
        raise ValueError("Missing or changed review blockers")
    expected = manifest.get("files")
    if not isinstance(expected, dict) or not expected:
        raise ValueError("Empty or malformed package inventory")
    for name in expected:
        safe(bundle, name)
    if len({p.casefold() for p in expected}) != len(expected):
        raise ValueError("Case-colliding inventory")
    issues = bm.compare_rows(expected, inventory(bundle), "package")
    required = {"README.md", "verify_package.py", "build_manifest.py", "payload/receiver/uxplay.exe", "provenance/receiver.json"}
    for component, assembly in MANAGED.items():
        required.add(f"provenance/{component}.json")
        required.update(f"payload/{component}/{assembly}{s}" for s in SUFFIXES)
    issues += [f"required file missing from inventory: {name}" for name in sorted(required - expected.keys())]
    if issues:
        return issues
    for component, assembly in MANAGED.items():
        record = load(safe(bundle, f"provenance/{component}.json"))
        if record.get("schema_version") != 1 or not record.get("sources") or not record.get("artifacts"):
            raise ValueError(f"Malformed {component} provenance")
        for name, data in record["sources"].items():
            target = f"source/{name}"
            if expected.get(target) != data:
                issues.append(f"source provenance mismatch: {target}")
        for suffix in SUFFIXES:
            name = assembly + suffix
            if expected.get(f"payload/{component}/{name}") != record["artifacts"].get(name):
                issues.append(f"build provenance mismatch: {component}/{name}")
        config = load(safe(bundle, f"payload/{component}/{assembly}.runtimeconfig.json"))
        opts = config.get("runtimeOptions", {})
        frameworks = opts.get("frameworks", []) + ([opts["framework"]] if "framework" in opts else [])
        needed = "Microsoft.WindowsDesktop.App" if component == "console" else "Microsoft.NETCore.App"
        if not any(f.get("name") == needed and str(f.get("version", "")).startswith("8.") for f in frameworks):
            issues.append(f"unexpected runtime requirements: {component}")
    native = load(safe(bundle, "provenance/receiver.json"))
    if not native.get("source_sha256") or not native.get("rebuilt_sha256"):
        raise ValueError("Malformed native provenance")
    if expected["payload/receiver/uxplay.exe"]["sha256"] != native["rebuilt_sha256"]:
        issues.append("receiver build provenance mismatch")
    for name, digest in native["source_sha256"].items():
        target = "source/receiver/" + name.replace("\\", "/")
        safe(bundle, target)
        if expected.get(target, {}).get("sha256") != digest:
            issues.append(f"native source provenance mismatch: {target}")
    permitted_payload = {p for p in required if p.startswith("payload/")}
    issues += [f"unapproved runtime asset: {name}" for name in expected if name.startswith("payload/") and name not in permitted_payload]
    return issues


def stage(repo, output, managed, native_exe, native_record, native_source, guide):
    repo, output = Path(repo).resolve(), Path(output)
    # All creation stays in a new child of this checkout's output/staging directory.
    staging = safe(repo, "output/staging")
    resolved = output.resolve()
    if not resolved.is_relative_to(staging) or resolved == staging:
        raise ValueError("Output must be a new directory below repo/output/staging")
    safe(repo, resolved.relative_to(repo).as_posix())
    if output.exists():
        raise ValueError("Output already exists; bundles are never overwritten")
    copies = {}

    def add(source, relative, expected=None):
        safe(resolved, relative)
        source = Path(source)
        data = row(source)
        if expected is not None and data != expected:
            raise ValueError(f"Changed source or build input: {relative}")
        if relative in copies and copies[relative][1] != data:
            raise ValueError(f"Conflicting source copies: {relative}")
        copies[relative] = (source, data)

    if set(managed) != set(MANAGED):
        raise ValueError("Console and kernel components are both required")
    for component, (build, manifest_path) in managed.items():
        record = load(manifest_path)
        issues = bm.verify(record, repo, build)
        if issues:
            raise ValueError("Build no longer matches its record: " + "; ".join(issues))
        assembly = MANAGED[component]
        for suffix in SUFFIXES:
            name = assembly + suffix
            if name not in record["artifacts"]:
                raise ValueError(f"Missing runtime artifact: {component}/{name}")
            add(safe(build, name), f"payload/{component}/{name}", record["artifacts"][name])
        for name, data in record["sources"].items():
            add(safe(repo, name), f"source/{name}", data)
        add(manifest_path, f"provenance/{component}.json")
    native = load(native_record)
    if not native.get("source_sha256") or bm.sha256(native_exe) != native.get("rebuilt_sha256"):
        raise ValueError("Receiver no longer matches native build record")
    for name, digest in native["source_sha256"].items():
        name = name.replace("\\", "/")
        source = safe(native_source, name)
        if bm.sha256(source) != digest:
            raise ValueError(f"Native source changed: {name}")
        add(source, f"source/receiver/{name}")
    add(native_exe, "payload/receiver/uxplay.exe")
    add(native_record, "provenance/receiver.json")
    add(guide, "README.md")
    add(Path(__file__), "verify_package.py")
    add(Path(bm.__file__), "build_manifest.py")
    if len({name.casefold() for name in copies}) != len(copies):
        raise ValueError("Case-colliding package paths")
    # Preflight is complete. On copy failure leave the incomplete folder for inspection;
    # no manifest is written, no existing files are deleted, and nothing is launched.
    resolved.mkdir(parents=True, exist_ok=False)
    for name, (source, expected) in copies.items():
        target = safe(resolved, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if row(target) != expected:
            raise ValueError(f"File changed while staging: {name}")
    manifest = {"schema_version": 1, "status": "review_only", "launch_allowed": False,
                "blockers": BLOCKERS, "files": {name: data for name, (_, data) in sorted(copies.items())},
                "scope": "Integrity and recorded local provenance; not a signature, dependency attestation or physical acceptance."}
    with (resolved / "package.json").open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)
    issues = verify(resolved)
    if issues:
        raise ValueError("Staged bundle verification failed: " + "; ".join(issues))
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    v = sub.add_parser("verify")
    v.add_argument("--bundle", type=Path, required=True)
    s = sub.add_parser("stage")
    for key in ("repo", "out", "console-build", "console-manifest", "kernel-build", "kernel-manifest", "receiver-exe", "receiver-record", "receiver-source", "guide"):
        s.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.mode == "verify":
            issues = verify(args.bundle)
            for issue in issues:
                print(issue)
            print("Integrity FAILED" if issues else "Integrity verified. REVIEW ONLY: startup and deployment remain blocked.")
            return 1 if issues else 0
        result = stage(args.repo, args.out, {c: (getattr(args, c+"_build"), getattr(args, c+"_manifest")) for c in MANAGED},
                       args.receiver_exe, args.receiver_record, args.receiver_source, args.guide)
        print(f"Staged {len(result['files'])} verified files. REVIEW ONLY: no process was started.")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"Refused: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
