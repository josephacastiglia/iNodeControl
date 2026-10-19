"""Exercise only invalid startup paths, which exit before hardware enumeration."""
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent
binary = root / "build/iMouse2.Kernel.dll"
unused = root / "invalid-startup-must-not-create"
if unused.exists():
    raise SystemExit("Test sentinel directory already exists")
cases = [
    ["--fka-pass-through", "typo", "--data-dir", str(unused)],
    ["--data-dir", str(unused), "--fka-pass-through"],
    ["--fka-pass-through", "--data-dir", str(unused)],
]
results = []
for args in cases:
    run = subprocess.run(["dotnet", str(binary), *args], capture_output=True, text=True, timeout=5)
    assert run.returncode == 2, (args, run.returncode, run.stdout, run.stderr)
    assert "--fka-pass-through must be" in run.stdout, run.stdout
    assert "WCH boards" not in run.stdout
    assert not unused.exists(), "Invalid option reached data-directory initialization"
    results.append({"arguments": args, "exit_code": run.returncode, "stdout": run.stdout, "stderr": run.stderr})
(root / "invalid-startup-results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
print("3 invalid startup checks passed; data initialization was never reached")
