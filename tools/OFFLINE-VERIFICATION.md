# Verify tooling without operating the rack

Use this guide to check diagnostics, build records, and endurance reporting from the repository root. The regression commands use synthetic data and temporary files. They don't operate phones or open application windows.

## Before you begin

Use Windows and Python 3.11 or later. The diagnostics and soak modules load Windows libraries, even when tests replace their collectors. Build verification needs existing output folders; recording build metadata also needs Git and the .NET SDK.

## Run offline regressions

Run the focused suites:

```powershell
python tools/test_export_diagnostics.py
python tools/test_build_manifest.py
python tools/test_analyze_endurance.py
python tools/test_endurance_soak.py
python analysis/gate6-release-validation-20260916/test_run_gate6.py
```

The recorded 11 October run passes 18, nine, 15, 16, and 22 tests respectively: 80 in total. Each command returns exit code zero and prints `OK`. These tests establish tool behavior, not physical release acceptance.

## Verify an existing build record

To compare source inputs and output bytes with a recorded manifest, run:

```powershell
python tools/build_manifest.py verify --repo . `
  --build "BUILD_DIR" --manifest "MANIFEST_JSON"
```

Replace `BUILD_DIR` with the output directory and `MANIFEST_JSON` with its saved manifest. A matching build prints `All recorded inputs and build bytes match` and exits zero. Missing, added, or changed files produce exit code one. Unsafe manifest paths are rejected.

To record an existing build, run:

```powershell
python tools/build_manifest.py record --repo . `
  --build "BUILD_DIR" --project "PROJECT_FILE" `
  --manifest "MANIFEST_JSON"
```

Replace `PROJECT_FILE` with the repository-relative `.csproj` path. Use a manifest filename that doesn't exist and keep it outside the build directory. The tool records actual source bytes, including uncommitted files, build outputs, Git revision, and SDK version. It excludes generated `bin` and `obj` source directories.

This checksum record doesn't sign the build or independently attest external dependencies. Identical rebuilds from one checkout don't establish reproducibility on another PC or equivalence with the installed release.

## Analyze saved endurance data

To preserve earlier dashboards and raw evidence, write a separate report:

```powershell
python tools/analyze_endurance.py --dir "SAVED_RUN_DIR" `
  --out "REPORT_DIR"
```

Replace `SAVED_RUN_DIR` with the folder containing `telemetry.jsonl` and `status.json`. Replace `REPORT_DIR` with a separate output folder. The analyzer writes `DASHBOARD.md`, `dashboard.html`, and `analysis.json`; it doesn't start or contact the soak runner.

The exit codes describe sampled conditions:

| Exit code | Meaning |
|---|---|
| `0` | No failures observed in the implemented checks |
| `1` | Recorded failures, malformed evidence, or a fleet mismatch |
| `2` | Insufficient observations or unverified input releases |

Every result keeps `gate10_acceptance: false`. Kernel frame counters don't measure console presentation. Full-session memory slopes include warm-up, and the `FLAT` label isn't a predeclared resource budget.

## Diagnostics and hardware boundaries

The actual diagnostics command collects read-only service and host data; use the regression suite when you need a completely offline check. Exports default to no window inspection. `--include-ui-state` opts into read-only window and mirror-state collection. `--console-pid` resolves multiple-console ambiguity.

Schema version two preserves partial reports after collection failures, uses explicit candidate data folders or operator AppData settings, and records the managed console DLL hash. Persisted addresses aren't proof of an active connection. Two exports don't overwrite each other. Known credential fields and string patterns are filtered, but reports still contain local paths and rack identifiers; review them before sharing.

The soak runner requires `--live` and explicit, repeated `--phone` names. Use an empty output folder and a coordinated, authorized hardware window. It refuses occupied, paused, releasing, or unresolved phones, never automatically resumes them, and stops after failed input or unconfirmed release. Its group contains only the named phones. Offline fixtures don't validate its physical behavior.

## Verify completion

Check the test exit codes and review manifest differences before treating the tooling as ready for a hardware window. See [the offline run report](../analysis/offline-backlog-20261011/REPORT.md) for measured results and the preserved test-isolation incident. The missing-space investigation remains deferred.

## Verify release staging

Run the packaging and manifest regressions without starting apps:

```powershell
python tools/test_stage_release.py
python tools/test_build_manifest.py
```

The 12 October run passes 22 and nine cases. Packaging operates on recorded build bytes; it never compiles, launches, installs, or stops software. Output must be a new directory below `output/staging/`.

Verify the prepared review bundle:

```powershell
python tools/stage_release.py verify --bundle output/staging/offline-review-20261012
```

The verifier returns zero for intact review files; it does not approve launching or deploying them. See [Review a staged iMouse package](../docs/RELEASE-STAGING.md) for its contents, remaining integration requirements, and rollback preparation. For a relocated bundle, use its included `verify_package.py`.
