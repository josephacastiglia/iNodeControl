# Review a staged iMouse package

For the developer preparing a candidate, this guide explains how to verify the packaged files and plan a reversible deployment. This bundle is for offline review. It does not replace the installed release, include a start script, or establish physical acceptance.

## Verify the package

You need Python 3.11 or later to run the verifier. Open a terminal in the package folder and run:

```powershell
python verify_package.py verify --bundle .
```

An intact package prints `Integrity verified. REVIEW ONLY: startup and deployment remain blocked.` and exits zero. Exit one means missing, altered, or unexpected files; exit two means an invalid record or an unreadable path. Do not repair a failed package in place. Rebuild it under a different name from the recorded inputs.

The verifier works after you move or extract the package. It compares every file with its recorded checksum, then checks the included source and selected runtime files against the embedded build records. It also checks the declared .NET runtime requirements. It does not open a window, query the rack, start a process, or modify settings. A checksum establishes integrity relative to the record; it is not a cryptographic signature or independent proof of the build process.

## Understand the contents

The package contains these areas:

| Path | Contents |
|---|---|
| `payload/console/` | SDK-built console assembly, executable, symbols, dependency file, and runtime declaration |
| `payload/kernel/` | SDK-built kernel assembly, executable, symbols, dependency file, and runtime declaration |
| `payload/receiver/` | Patched native UxPlay executable; external libraries are not included |
| `source/` | Exact recorded project/native source snapshots; includes source fixtures, not copied operator settings |
| `provenance/` | Original managed build manifests and native build comparison |
| `package.json` | File checksums, review-only status, and unresolved release requirements |

Runtime folders deliberately exclude copied `data/`, operator settings, test results, logs, and machine-specific receiver configuration. Source fixtures under `source/` are evidence; do not use them as live configuration. Local paths and device identifiers can appear in source, symbols, and provenance. Review the bundle before publishing it.

## Resolve the release requirements

Do not launch the executables in this bundle as a candidate. Complete these steps before scheduling installation:

1. Check the combined source record in `analysis/combined-candidate-20261012/REPORT.md`. This checkout preserves the integration branch's isolated startup, test isolation, and text/timeout work together with the offline fixes. Run the remaining interactive and physical acceptance checks on the exact candidate build; headless checks do not replace them.
2. Build the combined code into a fresh directory. Record its actual source and output bytes; do not reuse these manifests for different files.
3. Specify an isolated candidate data folder and service endpoint. Confirm normal startup honors both. An empty configuration must not silently target the vendor service. Keep hover tracking off for controlled tests.
4. Prepare and validate the intended phone/board bindings, calibration, receiver names, pipes, nonoverlapping ports, and receiver MACs. Start from a reviewed copy of the working configuration, never from the source fixtures. Do not alter the working copy.
5. Check the external runtime requirements on the target PC. The managed binaries require .NET 8; the console needs the Windows Desktop runtime. UxPlay also needs its matching native libraries, GStreamer plugins and plugin scanner. This recorded Windows receiver uses the built-in mDNS implementation (`USE_MDNS=1`), not Apple Bonjour; other builds may differ. The kernel sets the receiver's `PATH`, plugin directory, and scanner from its receiver-runtime directory. Directory existence alone does not prove those dependencies work. Dependency redistribution and license notices need review before an installer is published.
6. Produce a candidate-specific launcher with explicit executable paths and configuration. Review ownership, receiver discovery, and restoration behavior before it is run. Leave the installed launcher and shortcuts unchanged.
7. Complete the coordinated physical checks required by `FINISH-CRITERIA.md`. The remaining typing, Home, App Switcher, discovery, targeting, scale, and endurance issues are not passed by packaging tests.

There is no deployment command in this guide because the combined candidate has not completed interactive/physical acceptance and its live configuration is not validated. A package that passes integrity verification still has these startup blockers.

## Validate isolated startup without connecting

For a built combined console, use its offline preflight before considering a candidate launch:

```powershell
.\payload\console\iMouse2.exe --validate-startup --data-dir="C:\iMouse candidate\data" --address=http://127.0.0.1:9923
```

The example folder and port are illustrative; choose your intended candidate folder and endpoint. This command opens no window, creates no candidate settings directory, and makes no connection. It writes `startup-validation.json` beside the executable and exits zero only if the isolated folder and explicit address are structurally valid. It does not prove the service is reachable or the receiver configuration is correct. Run it from a disposable copy of the payload: its generated report would correctly count as an extra file during strict package verification.

## Prepare a rollback record

For the operator managing a later approved test window, record the following before changing running services:

1. Record the full paths, command lines, hashes, and roles of the installed console, kernel, and each receiver. Re-read the live process state at the start of the window; historical process IDs are not reliable.
2. Preserve the exact working binaries, launcher, configuration, calibration, and settings in a separate backup with checksums. Capture settings only while the corresponding application is stopped or otherwise cannot write them. Keep backup contents private.
3. Record which phones are mirroring, their original settings, and who holds control. Do not interrupt another controller's work. Keep candidate settings and outputs outside the working directories.
4. Agree on the interruption and recovery window. Receiver restarts can require manual recasting, and discovery has previously been delayed. Do not promise automatic or immediate recovery.

## Return to the working version

Use these steps only during the approved window if the candidate fails:

1. Stop candidate input and release its own leases through the supported path. Record an unconfirmed release as unresolved; do not assume it succeeded.
2. Close the candidate console normally. Stop only the verified candidate services through their supported graceful shutdown path. If a process does not stop, report its identity before using any different shutdown method.
3. Compare the working files with the pre-window hashes. If they are unchanged, leave them in place. If a working file was modified, restore only that identified file from the verified backup after its owner has stopped. Do not copy candidate settings over operator settings.
4. Relaunch the saved working configuration through the original launcher, when no conflicting kernel or receivers remain. Verify paths and identities before operating it.
5. Have the operator reconnect each phone's mirroring if needed. Verify the intended phone/board/receiver mapping, live video, lease state, and restored settings. If a receiver is missing from the phone's list, preserve the evidence and follow the agreed recovery plan; do not begin repeated restarts.
6. Record the final state and any unresolved failure. Keep the candidate package and logs for diagnosis. Restoration is complete only when the operator's working setup is confirmed usable again.

## Receiver log retention

The candidate retains `receiver-BOARD.log` plus `receiver-BOARD.log.1`. New output is limited to 4 MiB per generation; unusually long lines are marked truncated. An existing oversized log is retained for one generation before normal rotation replaces it. Archive test evidence separately before another run.

If a log cannot be written or rotated, the receiver keeps running and its per-phone kernel status carries a logging warning. A later successful write clears the warning. Missing lines cannot be recovered from this bounded log. Collect the warning and inspect disk space/permissions; it is not a reason to automatically restart the rack. Any test that reads by file offset must detect log rotation.

## Next step

Complete candidate configuration, dependency verification, and the remaining acceptance checks before preparing an installable release. Keep this review package as an immutable record of the offline work.
