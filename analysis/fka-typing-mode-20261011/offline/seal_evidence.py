"""Copy this investigation's evidence to a new local archive and verify every copy."""
import hashlib
import shutil
from pathlib import Path


def main():
    investigation = Path(__file__).resolve().parent.parent
    workspace = investigation.parents[2]
    archive = workspace / "iMouseXP-2.0-evidence-archive/20261011-keyboard-reports-and-fka-focus"
    if archive.exists():
        raise SystemExit("Refusing to replace an existing evidence archive")
    selected = [p for p in investigation.iterdir() if p.is_file()]
    offline = investigation / "offline"
    selected.extend(p for p in offline.iterdir() if p.is_file())
    selected.extend(p for p in (offline / "run-1").iterdir() if p.is_file())
    selected.extend(p for p in (offline / "build").iterdir() if p.is_file())
    lines = []
    for source in sorted(selected):
        relative = source.relative_to(investigation)
        destination = archive / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        expected = hashlib.sha256(source.read_bytes()).hexdigest()
        actual = hashlib.sha256(destination.read_bytes()).hexdigest()
        if expected != actual:
            raise RuntimeError(f"Archive mismatch: {relative}")
        lines.append(f"{actual}  {relative.as_posix()}")
    (archive / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Archived and verified {len(lines)} files: {archive}")


if __name__ == "__main__":
    main()
