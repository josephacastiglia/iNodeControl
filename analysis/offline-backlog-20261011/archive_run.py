"""Preserve this offline run locally; refuse any existing archive."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

record = Path(__file__).resolve().parent
repo = record.parents[1]
archive = repo.parent / "iMouseXP-2.0-evidence-archive/20261011-offline-backlog"
assert not archive.exists(), "Refusing to replace an existing archive"
files = {Path("run") / path.relative_to(record): path for path in record.rglob("*") if path.is_file() and "__pycache__" not in path.parts}
for name in ("export_diagnostics.py", "test_export_diagnostics.py", "build_manifest.py", "test_build_manifest.py", "analyze_endurance.py", "test_analyze_endurance.py", "endurance_soak.py", "test_endurance_soak.py", "OFFLINE-VERIFICATION.md"):
    files[Path("tools") / name] = repo / "tools" / name
for name in ("PROGRESS.md", "WORK-REMAINING.md", "FINISH-CRITERIA.md"):
    files[Path("project-record") / name] = repo / name
for name in ("kernel", "console"):
    manifest = json.loads((record / (name + "-build.json")).read_text(encoding="utf-8"))
    for relative in manifest["sources"]:
        source = (repo / relative).resolve()
        assert source.is_relative_to(repo), relative
        files[Path("source") / relative] = source
for name in ("run_gate6.py", "test_run_gate6.py", "README.md", "OFFLINE-UPDATE-20261011.md", "OFFLINE-VALIDATION-20261011.txt"):
    files[Path("timing-tool") / name] = repo / "analysis/gate6-release-validation-20260916" / name
patch = subprocess.run(["git", "diff", "--binary"], cwd=repo, capture_output=True, check=True).stdout
status = subprocess.run(["git", "status", "--short"], cwd=repo, capture_output=True, check=True).stdout
archive.mkdir(parents=True)
(archive / "tracked-working-tree.patch").write_bytes(patch)
(archive / "working-tree-status.txt").write_bytes(status)
lines = []
for relative, source in sorted(files.items(), key=lambda pair: pair[0].as_posix()):
    target = archive / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == expected, relative
    lines.append(f"{expected}  {relative.as_posix()}")
for name in ("tracked-working-tree.patch", "working-tree-status.txt"):
    lines.append(f"{hashlib.sha256((archive / name).read_bytes()).hexdigest()}  {name}")
(archive / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"Preserved {len(lines)} files; every copy hash-verified.\n{archive}")
