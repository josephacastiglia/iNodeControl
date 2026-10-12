"""Preserve this completed offline run; refuses an existing archive."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

RECORD = Path(__file__).resolve().parent
ROOT = RECORD.parents[1]
ARCHIVE = ROOT.parent / "iMouseXP-2.0-evidence-archive/20261012-receiver-memory"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    summary = json.loads((RECORD / "run-180s/summary.json").read_text(encoding="utf-8"))
    assert summary["installed_receiver_unchanged"]
    release = json.loads((RECORD / "release-checksums.json").read_text(encoding="utf-8"))
    assert all(sha(ROOT / name) == expected for name, expected in release.items())
    if ARCHIVE.exists(): raise FileExistsError(ARCHIVE)
    snapshot = RECORD / "source-snapshot"
    snapshot.mkdir(exist_ok=False)
    src = ROOT / "tools/airplay/uxplay"
    provenance = json.loads((RECORD / "patched-build/comparison.json").read_text(encoding="utf-8"))
    for relative, expected in provenance["source_sha256"].items():
        path = src / relative
        assert sha(path) == expected, path
        dest = snapshot / "uxplay" / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
    for path in (ROOT / "tools/receiver_memory_probe").iterdir():
        if path.is_file() and path.suffix in (".c", ".py", ".md"):
            dest = snapshot / "probe" / path.name
            dest.parent.mkdir(exist_ok=True)
            shutil.copy2(path, dest)
    for name in ("PROGRESS.md", "WORK-REMAINING.md"):
        shutil.copy2(ROOT / name, snapshot / name)
    patch = subprocess.check_output(["git", "diff", "--", "tools/airplay/uxplay/lib/raop_rtp_mirror.c"], cwd=ROOT)
    (RECORD / "receiver-fix.patch").write_bytes(patch)
    status = subprocess.check_output(["git", "status", "--short"], cwd=ROOT)
    (RECORD / "working-tree-status.txt").write_bytes(status)
    shutil.copytree(RECORD, ARCHIVE)
    entries = []
    for path in sorted(RECORD.rglob("*")):
        if path.is_file():
            relative = path.relative_to(RECORD)
            expected = sha(path)
            assert sha(ARCHIVE / relative) == expected, relative
            entries.append(f"{expected}  {relative.as_posix()}")
    (ARCHIVE / "SHA256SUMS.txt").write_text("\n".join(entries) + "\n", encoding="utf-8")
    print(json.dumps({"archive": str(ARCHIVE), "files_verified": len(entries),
                      "release_hashes_unchanged": True}))


if __name__ == "__main__":
    main()
