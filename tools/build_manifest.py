"""Record/verify local build bytes and source inputs. Never build, launch or deploy."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def under(root, relative):
    name = PurePosixPath(relative)
    if name.is_absolute() or ".." in name.parts or "\\" in relative or ":" in relative:
        raise ValueError(f"unsafe manifest path: {relative}")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError(f"path escapes recorded root: {relative}")
    return path


def snapshot(folder, relative_to=None, exclude_generated=False):
    folder = Path(folder).resolve()
    root = Path(relative_to or folder).resolve()
    rows = {}
    for path in sorted(folder.rglob("*")):
        if exclude_generated and any(part in ("bin", "obj") for part in path.relative_to(folder).parts):
            continue
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            checked = under(root, relative)
            rows[relative] = {"sha256": sha256(checked), "bytes": checked.stat().st_size}
    return rows


def source_snapshot(repo, project):
    project = under(repo, project)
    if project.suffix != ".csproj" or not project.is_file():
        raise ValueError("project must be an existing .csproj within the repository")
    rows = snapshot(project.parent, repo, exclude_generated=True)
    folder = project.parent
    while folder.is_relative_to(repo):
        for name in ("Directory.Build.props", "Directory.Build.targets", "Directory.Packages.props", "global.json", "NuGet.config"):
            path = folder / name
            if path.is_file():
                key = path.relative_to(repo).as_posix()
                checked = under(repo, key)
                rows[key] = {"sha256": sha256(checked), "bytes": checked.stat().st_size}
        if folder == repo:
            break
        folder = folder.parent
    return rows


def record(repo, build, project, metadata=None):
    repo, build = Path(repo).resolve(), Path(build).resolve()
    if not build.is_dir():
        raise ValueError("build directory does not exist")
    artifacts = snapshot(build)
    if not artifacts or not any(name.endswith(".dll") for name in artifacts):
        raise ValueError("build directory must contain a managed assembly")
    return {"schema_version": 1, "recorded_at": datetime.now(timezone.utc).isoformat(),
            "project": project, "metadata": metadata or {},
            "sources": source_snapshot(repo, project), "artifacts": artifacts,
            "scope": "project files, common build inputs and output bytes; external dependencies are not independently attested"}


def compare_rows(expected, actual, label):
    issues = []
    for name, entry in expected.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("sha256"), str) or len(entry["sha256"]) != 64:
            raise ValueError(f"invalid hash record: {name}")
        if name not in actual:
            issues.append(f"{label} missing: {name}")
        elif entry != actual[name]:
            issues.append(f"{label} changed: {name}")
    for name in actual.keys() - expected.keys():
        issues.append(f"{label} unrecorded: {name}")
    return issues


def verify(manifest, repo, build):
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("sources"), dict) or not isinstance(manifest.get("artifacts"), dict):
        raise ValueError("unsupported or malformed build manifest")
    repo, build = Path(repo).resolve(), Path(build).resolve()
    for key in manifest["sources"]:
        under(repo, key)
    for key in manifest["artifacts"]:
        under(build, key)
    if not manifest["sources"] or not manifest["artifacts"]:
        raise ValueError("empty manifest cannot verify a build")
    return compare_rows(manifest["sources"], source_snapshot(repo, manifest["project"]), "source") + compare_rows(manifest["artifacts"], snapshot(build), "artifact")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("record", "verify"))
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--project", help="repository-relative .csproj; required when recording")
    args = parser.parse_args(argv)
    if args.mode == "record":
        if not args.project:
            parser.error("record requires --project")
        if args.manifest.resolve().is_relative_to(args.build.resolve()):
            parser.error("manifest must live outside the build directory")
        git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=args.repo, capture_output=True, text=True, check=True, timeout=10)
        sdk = subprocess.run(["dotnet", "--version"], capture_output=True, text=True, check=True, timeout=10)
        manifest = record(args.repo, args.build, args.project, {"git_head": git.stdout.strip(), "sdk_version": sdk.stdout.strip(), "source_snapshot_includes_uncommitted_files": True})
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        with args.manifest.open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2)
        print(f"Recorded {len(manifest['sources'])} source inputs and {len(manifest['artifacts'])} build files")
        return 0
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    issues = verify(manifest, args.repo, args.build)
    for issue in issues:
        print(issue)
    print("Verification failed" if issues else "All recorded inputs and build bytes match")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
