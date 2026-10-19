"""Preserve the exact working-tree overlay, tested binaries and bounded evidence."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

root = Path(__file__).resolve().parents[2]
record = Path(__file__).resolve().parent
source_names = [
    "src/iMouse.Console/InputControls.cs", "src/iMouse.Console/MainWindow.xaml",
    "src/iMouse.Console/MainWindow.xaml.cs", "src/iMouse.Console/SelfTests.cs",
    "src/iMouse.Console/FarmApiClient.cs", "src/iMouse.Console/FarmAutomationWindow.cs",
    "src/iMouse.Console/FarmTargetPolicy.cs", "src/iMouse.Console/FarmTests.cs",
    "src/iMouse.Console/MainWindow.FarmJobs.cs", "src/iMouse.Console/MainWindow.FarmTab.cs",
    "tools/imouse_farm_server.py", "tools/imouse_social_automation.py", "tools/farm_jobs.py",
    "tools/imouse_farm_command_center.html", "tools/setup_imouse_farm.py",
    "tools/test_farm_execution_safety.py", "tools/test_farm_feature_validation.py",
    "tools/test_farm_jobs.py", "tools/test_farm_content.py", "tools/test_farm_http_jobs.py",
    "tools/requirements-farm.txt", "Open Marketing Farm Candidate.ps1",
    "Open Marketing Farm.ps1", "FARM-CONTINUATION.md", "MARKETING-FARM-STATUS.md",
    "IMOUSE_MARKETING_FARM_HANDOFF.md", "IMOUSE2_MARKETING_FARM_COMPLETION_HANDOFF.md",
    "docs/imouse_social_automation_blueprint.md",
]


def copy_verified(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = source.read_bytes()
    if destination.exists() and destination.read_bytes() != data:
        raise RuntimeError(f"Refusing to overwrite a different preserved file: {destination}")
    if not destination.exists():
        destination.write_bytes(data)
    if hashlib.sha256(destination.read_bytes()).digest() != hashlib.sha256(data).digest():
        raise RuntimeError(f"Copy did not verify: {destination}")


inventory = []
for name in source_names:
    source = root / name
    copy_verified(source, record / "source" / name)
    inventory.append({"path": name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "bytes": source.stat().st_size})
git = ["git", "-c", f"safe.directory={root.as_posix()}"]
base = subprocess.check_output(git + ["rev-parse", "HEAD"], cwd=root, text=True).strip()
(record / "tracked-overlay.patch").write_bytes(subprocess.check_output(git + ["diff", "--binary", "--", "src/iMouse.Console"], cwd=root))
(record / "source-inventory.json").write_text(json.dumps({"base": base, "files": inventory}, indent=2), encoding="utf-8")
binary_root = root / "output/codex-farm-functional-20261017"
for source in binary_root.iterdir():
    if source.is_file() and source.suffix in (".exe", ".dll", ".pdb", ".json"):
        copy_verified(source, record / "candidate-binaries" / source.name)
copy_verified(binary_root / "qa/self-tests.json", record / "console-self-tests.json")

archive = root.parent / "iMouseXP-2.0-evidence-archive/20261017-farm-functionality"
for source in record.rglob("*"):
    if source.is_file() and "__pycache__" not in source.parts:
        copy_verified(source, archive / source.relative_to(record))
files = [p for p in archive.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt"]
manifest = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(archive).as_posix()}\n" for p in sorted(files))
(archive / "SHA256SUMS.txt").write_text(manifest, encoding="utf-8")
print(json.dumps({"archive": str(archive), "verifiedFiles": len(files), "sourceFiles": len(inventory), "base": base}))
