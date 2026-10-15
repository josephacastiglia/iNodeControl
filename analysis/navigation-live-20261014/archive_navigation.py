"""Preserve this completed navigation window locally; no rack/desktop access."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

record = Path(__file__).resolve().parent
repo = record.parents[1]
archive = repo.parent / "iMouseXP-2.0-evidence-archive/20261014-navigation-live"
assert not archive.exists(), "Archive already exists; never overwrite it"
restored = json.loads((record / "restoration-confirmed.json").read_text(encoding="utf-8"))
assert restored["both_mirrors_live_and_advancing"] and restored["both_unowned"]
protected = json.loads((record / "protected-after.json").read_text(encoding="utf-8"))
assert len(protected) == 25 and all(row["unchanged"] for row in protected)
archive.mkdir(parents=True)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


entries = []


def preserve(source, relative):
    destination = archive / relative
    assert destination.resolve().is_relative_to(archive.resolve())
    destination.parent.mkdir(parents=True, exist_ok=True)
    before = sha(source)
    shutil.copy2(source, destination)
    assert before == sha(source) == sha(destination), str(source)
    entries.append({"path": relative.as_posix(), "bytes": destination.stat().st_size, "sha256": before})


for directory, prefix in ((record, Path("live-record")),
                          (repo / "analysis/re-improvements-20261014/live-navigation", Path("actions"))):
    for source in sorted(directory.rglob("*")):
        if source.is_file() and source.name != "archive-verification.json":
            preserve(source, prefix / source.relative_to(directory))

for name in (
    "analysis/gate5-everyday-controls-20260916/run_controls.py",
    "tools/test_gate5_navigation.py", "tools/gate4_1000_tap_suite.py",
    "tools/force_recast.py", "tools/kernel-window/Stop-ConsoleProcessGracefully.ps1",
    "analysis/re-improvements-20261014/verify_navigation_runner.py",
    "analysis/re-improvements-20261014/NAVIGATION-RUNNER.md",
    "analysis/re-improvements-20261014/LIVE-ACCEPTANCE.md",
    "analysis/re-improvements-20261014/COMPLETION-AUDIT.md",
    "analysis/re-improvements-20261014/preparation.json",
    "analysis/re-improvements-20261014/run-inventory.json",
    "analysis/re-improvements-20261014/package-result.json",
    "src/iMouse.Kernel/InputRouter.cs", "src/iMouse.Kernel/HidProtocol.cs",
    "RE-IMPROVEMENTS-PLAN.md", "RESUME-NEXT.md",
):
    preserve(repo / name, Path("source") / name)

git = ["git", "-c", "safe.directory=" + repo.as_posix(), "-C", str(repo)]
revision = subprocess.check_output(git + ["rev-parse", "HEAD"], text=True).strip()
bundle = archive / "active-branch.bundle"
subprocess.run(git + ["bundle", "create", str(bundle), "HEAD"], check=True, capture_output=True)
subprocess.run(git + ["bundle", "verify", str(bundle)], check=True, capture_output=True)
entries.append({"path": bundle.name, "bytes": bundle.stat().st_size, "sha256": sha(bundle)})
manifest = archive / "SHA256SUMS.json"
manifest.write_text(json.dumps({"revision": revision, "entries": entries}, indent=2), encoding="utf-8")
assert all(sha(archive / row["path"]) == row["sha256"] for row in entries)
receipt = {"archive": str(archive), "source_revision": revision, "files": len(entries),
           "bytes": sum(row["bytes"] for row in entries), "manifest_sha256": sha(manifest),
           "all_copies_verified": True, "git_bundle_verified": True, "off_machine_backup": False,
           "candidate_product_source": "373dd58a6d5c1c541984e9b4ac8b76c9ed3e53e4"}
(record / "archive-verification.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt, indent=2))
