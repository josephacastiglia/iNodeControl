"""Preserve this offline probe in a new archive; never replace an earlier record."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_archive(folder):
    count = 0
    for line in (folder / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        if sha(folder / relative) != expected:
            raise RuntimeError(f"Earlier archive mismatch: {relative}")
        count += 1
    return count


def main():
    record = Path(__file__).resolve().parent
    repo = record.parents[1]
    workspace = repo.parent
    main_repo = workspace / "iMouseXP-2.0"
    original = workspace / "iMouseXP-2.0-evidence-archive/20261011-keyboard-reports-and-fka-focus"
    archive = workspace / "iMouseXP-2.0-evidence-archive/20261011-fka-pass-through-probe"
    if archive.exists():
        raise SystemExit("Refusing to replace an existing probe archive")
    prior_count = verify_archive(original)
    git = ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo)]
    patch = subprocess.run([*git, "diff", "--binary"], capture_output=True, check=True).stdout
    (record / "candidate.patch").write_bytes(patch)
    sources = sorted((repo / "src/iMouse.Kernel").glob("*.cs"))
    sources.append(repo / "src/iMouse.Kernel/iMouse.Kernel.csproj")
    provenance = {
        "base_commit": subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip(),
        "branch": subprocess.run([*git, "branch", "--show-current"], capture_output=True, text=True, check=True).stdout.strip(),
        "uncommitted_source_patch_sha256": sha(record / "candidate.patch"),
        "source_sha256": {p.relative_to(repo).as_posix(): sha(p) for p in sources},
        "build_sha256": {p.name: sha(p) for p in sorted((record / "build").iterdir()) if p.is_file()},
        "offline_kernel_tests": 123,
        "new_probe_checks": 25,
        "invalid_startup_checks": 3,
        "prior_archive_verified_files": prior_count,
        "live_test_performed": False,
    }
    (record / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    selected = [(p, Path("record") / p.name) for p in record.iterdir() if p.is_file()]
    selected.extend((p, Path("build") / p.name) for p in (record / "build").iterdir() if p.is_file())
    selected.extend((p, p.relative_to(repo)) for p in sources)
    investigation = main_repo / "analysis/fka-typing-mode-20261011"
    for name in ("commands-page-4.bmp", "commands-page-4.png", "OFFLINE-INVESTIGATION.md"):
        selected.append((investigation / name, Path("phone-command-evidence") / name))
    selected.append((main_repo / "PROGRESS.md", Path("main-checkout/PROGRESS.md")))
    lines = []
    for source, relative in sorted(selected, key=lambda item: item[1].as_posix()):
        target = archive / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        expected = sha(source)
        if sha(target) != expected:
            raise RuntimeError(f"Copy mismatch: {relative}")
        lines.append(f"{expected}  {relative.as_posix()}")
    (archive / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert verify_archive(archive) == len(lines)
    assert verify_archive(original) == prior_count
    print(f"Probe archive: {len(lines)} files verified; original {prior_count}-file archive unchanged")
    print(archive)


if __name__ == "__main__":
    main()
