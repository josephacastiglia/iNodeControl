"""Run offline capture tests and prove selected guards matter, with fake APIs only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import re

record = Path(__file__).resolve().parent
repo = record.parents[1]
source = repo / "analysis/gate5-everyday-controls-20260916/run_controls.py"
tests = repo / "tools/test_gate5_navigation.py"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, help="New analysis folder; previous validation records are never overwritten")
args = parser.parse_args()
record = (args.out or record / ("navigation-validation-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))).resolve()
assert record.is_relative_to(repo / "analysis"), "Validation output must be under analysis"
record.mkdir(parents=True, exist_ok=False)
baseline = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tools",
                           "-p", tests.name, "-v"], cwd=repo, capture_output=True, text=True, timeout=30)
(record / "navigation-runner-tests.txt").write_text(baseline.stdout + baseline.stderr, encoding="utf-8")
assert baseline.returncode == 0, "Offline baseline failed"
count = re.search(r"Ran (\d+) tests?", baseline.stderr)
assert count, "Missing test count"
original = source.read_text(encoding="utf-8")
mutations = [
    ("build_identity", '    require(status.get("build_identity", {}).get("sha256") == plan["kernel_sha256"], "Running kernel hash mismatch")',
     '    # Negative control: build check removed', "CaptureTests.test_bad_candidate_or_scope_refused_before_acquire"),
    ("explicit_live", '    require(live is True, "Live execution requires an explicitly coordinated window and --live")',
     '    # Negative control: live switch removed', "CaptureTests.test_explicit_live_flag_required_before_any_call"),
    ("new_owner_cleanup", '                elif generation is None or row.get("generation") == generation:',
     '                elif True:  # Negative control: generation check removed', "CaptureTests.test_new_owner_after_command_is_left_alone"),
    ("still_baseline_identity", 'require(not confirmed_still or result["frames"][-1]["sha256"] == confirmed_baseline_sha256,',
     'require(True,', "CaptureTests.test_confirmed_quiet_baseline_requires_matching_reviewed_image"),
    ("new_video_evidence", '        require(result["post_command_frames_verified"], "No new frame within five seconds; visual result is unscored")',
     '        # Negative control: new-frame requirement removed', "CaptureTests.test_no_new_after_frame_remains_unscored_and_releases_without_retry"),
]
program = r'''
import importlib.util, pathlib, sys, unittest
spec = importlib.util.spec_from_file_location("navigation_tests", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
# Only the fake-API test's module is changed. No source, service or build is changed.
exec(compile(sys.stdin.read(), str(module.SOURCE), "exec"), module.runner.__dict__)
result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName(sys.argv[2], module))
raise SystemExit(0 if result.wasSuccessful() else 1)
'''
results = []
for name, old, new, test in mutations:
    assert original.count(old) == 1, name
    changed = original.replace(old, new)
    check = subprocess.run([sys.executable, "-B", "-c", program, str(tests), test], input=changed,
                           cwd=repo, capture_output=True, text=True, timeout=30)
    log = check.stdout + check.stderr
    (record / ("navigation-negative-" + name + ".txt")).write_text(log, encoding="utf-8")
    assert check.returncode == 1 and "FAIL:" in log and "ERROR:" not in log, name + " did not fail its assertion"
    results.append({"guard_removed": name, "test": test, "mutated_source_sha256": hashlib.sha256(changed.encode()).hexdigest(),
                    "failed_expected_assertion": True})
plan = subprocess.run([sys.executable, "-B", str(source)], cwd=repo, capture_output=True, text=True, timeout=30)
assert plan.returncode == 0, plan.stderr
offline = json.loads(plan.stdout)
assert offline["rack_contacted"] is False
report = {"baseline_exit": baseline.returncode, "tests": int(count.group(1)), "negative_controls": results,
          "offline_plan": offline, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
          "tests_sha256": hashlib.sha256(tests.read_bytes()).hexdigest(),
          "rack_contacted": False, "live_run": False, "product_binaries_changed": False}
(record / "navigation-runner-validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
