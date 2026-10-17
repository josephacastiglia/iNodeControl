"""Preserve this candidate without changing previous checkpoints or operator data."""
from pathlib import Path
import hashlib
import json
import subprocess

root = Path(__file__).resolve().parents[2]
record = Path(__file__).resolve().parent
archive = root.parent / "iMouseXP-2.0-evidence-archive/20261017-farm-carousel"
git = ["git", "-c", f"safe.directory={root.as_posix()}"]
names = [
    "tools/farm_drafts.py", "tools/imouse_farm_server.py", "tools/imouse_social_automation.py", "tools/farm_jobs.py",
    "tools/test_farm_drafts.py", "tools/test_farm_http_jobs.py", "tools/requirements-farm.txt",
    "src/iMouse.Console/CarouselDraft.cs", "src/iMouse.Console/CarouselDraftWindow.xaml",
    "src/iMouse.Console/CarouselDraftWindow.xaml.cs", "src/iMouse.Console/CarouselDraftTests.cs",
    "src/iMouse.Console/FarmJobRecovery.cs", "src/iMouse.Console/MainWindow.FarmJobs.cs",
    "src/iMouse.Console/MainWindow.FarmTab.cs", "src/iMouse.Console/FarmTests.cs",
    "src/iMouse.Console/FarmApiClient.cs", "src/iMouse.Console/InputControls.cs",
    "src/iMouse.Console/MainWindow.xaml", "src/iMouse.Console/MainWindow.xaml.cs", "src/iMouse.Console/SelfTests.cs",
    "Open Marketing Farm Candidate.ps1", "MARKETING-FARM-STATUS.md",
]


def copy(source, target):
    data = source.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != data:
        raise RuntimeError(f"Refusing to replace a preserved file: {target}")
    if not target.exists(): target.write_bytes(data)
    assert hashlib.sha256(data).digest() == hashlib.sha256(target.read_bytes()).digest()


inventory = []
for name in names:
    source = root / name
    copy(source, record / "source" / name)
    inventory.append({"path": name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "bytes": source.stat().st_size})
(record / "source-inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
binary = root / "output/codex-farm-carousel-20261017"
for name in ("iMouse2.dll", "iMouse2.exe", "iMouse2.pdb", "iMouse2.deps.json", "iMouse2.runtimeconfig.json"):
    copy(binary / name, record / "candidate-binaries" / name)
copy(binary / "qa/self-tests.json", record / "console-self-tests.json")
copy(binary / "qa/carousel-editor-headless.png", record / "carousel-editor-headless.png")
for name, target in (("farm-carousel-full-tests-20261017.txt", "python-tests.txt"),
                     ("farm-carousel-tests-20261017.txt", "sandbox-restricted-tests.txt"),
                     ("farm-carousel-build-20261017.txt", "build.txt")):
    copy(root / "analysis" / name, record / target)
commit = subprocess.check_output(git + ["rev-parse", "HEAD"], cwd=root, text=True).strip()
checkpoint = {"commit": commit, "base": "c60cb56f4a1a3db82fe127f66a0b3f70683caa05",
              "nativeChecks": 447, "pythonTests": 106, "phoneInput": False, "desktopControl": False,
              "dllSha256": hashlib.sha256((binary / "iMouse2.dll").read_bytes()).hexdigest()}
(record / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
for source in record.rglob("*"):
    if source.is_file() and "__pycache__" not in source.parts:
        copy(source, archive / source.relative_to(record))
files = sorted(p for p in archive.rglob("*") if p.is_file() and p.name != "SHA256SUMS.txt")
(archive / "SHA256SUMS.txt").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(archive).as_posix()}\n" for p in files), encoding="utf-8")
print(json.dumps({"archive": str(archive), "files": len(files), "commit": commit}))
