"""Copy an audited native runtime for local tests; never install or start it."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

# Set before importing a local helper: import may cache it before its code runs.
sys.dont_write_bytecode = True
import stage_release as package


def absolute(path):
    return Path(os.path.abspath(path)).resolve()


def fields(path):
    result, key = {}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("%") and line.endswith("%"):
            key = line.strip("%")
            if key in result:
                raise ValueError(f"Duplicate metadata field in {path.name}: {key}")
            result[key] = []
        elif key and line:
            result[key].append(line)
    return result


def is_notice(item):
    """Recognize package-listed notices, including projects that install them in doc/."""
    if item.endswith("/"):
        return False
    if "/share/licenses/" in item:
        return True
    basename = item.rsplit("/", 1)[-1].split(".", 1)[0].upper()
    return "/share/doc/" in item and basename in {"COPYING", "COPYRIGHT", "LICENSE", "LICENCE", "NOTICE"}


def verify(root):
    root = absolute(root)
    manifest = package.load(package.safe(root, "runtime.json"))
    if (manifest.get("schema_version") != 1 or manifest.get("status") != "local_test_only"
            or manifest.get("installation_allowed") is not False
            or manifest.get("redistribution_cleared") is not False):
        raise ValueError("Expected a local-test-only runtime manifest")
    expected = manifest.get("files")
    if not isinstance(expected, dict) or not expected:
        raise ValueError("Empty runtime inventory")
    for name in expected:
        package.safe(root, name)
    issues = package.bm.compare_rows(expected, package.inventory(root, "runtime.json"), "runtime")
    receipt = package.load(package.safe(root, "metadata/receipts.json"))
    described = set()
    for item in receipt["packages"]:
        for name in item["runtime_files"]:
            package.safe(root, name)
            if name in described:
                issues.append(f"Duplicate package ownership: {name}")
            described.add(name)
        for name in item["notices"] + item["metadata_files"]:
            if name not in expected:
                issues.append(f"Missing package record: {name}")
    if described != {name for name in expected if name.startswith("runtime/")}:
        issues.append("Runtime files and package ownership records disagree")
    gaps = [item["name"][0] for item in receipt["packages"] if not item["notices"] or item["missing_listed_notices"]]
    if manifest.get("notice_gaps") != gaps:
        issues.append("Notice-gap summary disagrees with package receipts")
    if manifest.get("package_count") != len(receipt["packages"]) or manifest.get("runtime_file_count") != len(described):
        issues.append("Runtime summary counts disagree with package receipts")
    return issues


def stage(repo, out, msys, audit_path, receiver):
    repo, out, msys, receiver = map(absolute, (repo, out, msys, receiver))
    runtime = package.safe(msys, "ucrt64")
    staging = package.safe(repo, "output/staging")
    if not out.is_relative_to(staging) or out == staging:
        raise ValueError("Output must be a new child of repo/output/staging")
    package.safe(repo, out.relative_to(repo).as_posix())
    if out.exists():
        raise ValueError("Output already exists")
    audit = package.load(audit_path)
    if audit.get("schema_version") != 1 or audit.get("files_consistent") is not True or audit.get("errors") != []:
        raise ValueError("Audit must record a successful file inventory")
    sources, needed = {}, {}
    def add(path, name, expected=None):
        package.safe(out, name)
        row = package.row(path)
        if expected is not None and row != expected:
            raise ValueError(f"Recorded bytes changed: {name}")
        if name in sources:
            raise ValueError(f"Duplicate destination: {name}")
        sources[name] = (path, row)
    receiver_seen = False
    for name, entry in audit["files"].items():
        path = absolute(name)
        if path == receiver:
            if package.row(path) != entry:
                raise ValueError("Audited receiver has changed")
            receiver_seen = True
            continue
        if not path.is_relative_to(runtime):
            raise ValueError("Audit contains a file outside the selected runtime")
        relative = path.relative_to(runtime).as_posix()
        package.safe(runtime, relative)
        if not (relative.startswith(("bin/", "lib/gstreamer-1.0/")) and path.suffix.lower() == ".dll"
                or relative == "libexec/gstreamer-1.0/gst-plugin-scanner.exe"):
            raise ValueError(f"Unexpected runtime payload: {relative}")
        key = "ucrt64/" + relative
        if key.casefold() in needed:
            raise ValueError("Case-colliding runtime path")
        needed[key.casefold()] = "runtime/" + relative
        add(path, "runtime/" + relative, entry)
    if not receiver_seen or not needed:
        raise ValueError("Audit must include the selected receiver and runtime files")
    owned, receipts = set(), []
    database = package.safe(msys, "var/lib/pacman/local")
    for directory in sorted(database.iterdir()):
        if not directory.is_dir() or not (directory / "files").is_file():
            continue
        package.safe(database, directory.name)
        listed = fields(directory / "files").get("FILES", [])
        matches = [item for item in listed if item.casefold() in needed]
        if not matches:
            continue
        if any(item.casefold() in owned for item in matches):
            raise ValueError("Multiple packages claim the same runtime file")
        owned.update(item.casefold() for item in matches)
        desc = fields(directory / "desc")
        if not desc.get("NAME") or not desc.get("VERSION"):
            raise ValueError("Package name/version missing")
        prefix = "metadata/packages/" + directory.name + "/"
        metadata = [prefix + key for key in ("desc", "files")]
        for key in ("desc", "files"):
            add(package.safe(directory, key), prefix + key)
        notices, missing = [], []
        for item in listed:
            if not is_notice(item):
                continue
            path = package.safe(msys, item)
            if not path.is_file():
                missing.append(item)
                continue
            target = prefix + "notices/" + item
            add(path, target)
            notices.append(target)
        receipts.append({"name": desc["NAME"], "version": desc["VERSION"],
                         "upstream_urls": desc.get("URL", []), "declared_licenses": desc.get("LICENSE", []),
                         "runtime_files": [needed[item.casefold()] for item in matches],
                         "metadata_files": metadata, "notices": notices, "missing_listed_notices": missing})
    if owned != set(needed):
        raise ValueError("Some runtime files have no package ownership record")
    add(audit_path, "metadata/native-audit.json")
    for source, name in ((Path(__file__), "verify_runtime.py"), (Path(package.__file__), "stage_release.py"),
                         (Path(package.bm.__file__), "build_manifest.py")):
        add(source, name)
    if len({name.casefold() for name in sources}) != len(sources):
        raise ValueError("Case-colliding output inventory")
    out.mkdir(parents=True, exist_ok=False)
    for name, (source, row) in sources.items():
        target = package.safe(out, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if package.row(target) != row:
            raise ValueError(f"Copy verification failed: {name}")
    (out / "metadata/receipts.json").write_text(json.dumps({"packages": receipts,
        "scope": "Installed package declarations and available notices; not a legal clearance or upstream attestation."}, indent=2), encoding="utf-8")
    manifest = {"schema_version": 1, "status": "local_test_only", "installation_allowed": False,
                "redistribution_cleared": False, "files": package.inventory(out, "runtime.json"),
                "package_count": len(receipts), "runtime_file_count": len(needed),
                "notice_gaps": [r["name"][0] for r in receipts if not r["notices"] or r["missing_listed_notices"]],
                "limits": ["File inventory is not complete application acceptance.",
                           "Upstream source archives, licensing obligations and clean-PC validation remain open.",
                           "No .NET runtime, Windows system DLLs, operator settings or test-only plugins are included."]}
    (out / "runtime.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    issues = verify(out)
    if issues:
        raise ValueError("Runtime verification failed: " + "; ".join(issues))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    verify_args = modes.add_parser("verify")
    verify_args.add_argument("--bundle", type=Path, required=True)
    stage_args = modes.add_parser("stage")
    for name in ("repo", "out", "msys", "audit", "receiver"):
        stage_args.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.mode == "verify":
            issues = verify(args.bundle)
            print("\n".join(issues) if issues else "Runtime bytes verified; local tests only, no installation or distribution approval.")
            return 1 if issues else 0
        result = stage(args.repo, args.out, args.msys, args.audit, args.receiver)
        print(f"Staged {result['runtime_file_count']} runtime files from {result['package_count']} packages; {len(result['notice_gaps'])} notice gaps.")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"Refused: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
