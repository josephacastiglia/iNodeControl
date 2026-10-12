# Console diagnostic export

12 October 2026. Candidate source only; no desktop control, phone input, service start, receiver restart or deployment.

## Change

Settings → Export diagnostics now produces schema 3. It snapshots UI state before asynchronous work and reads only four existing GET routes: kernel status, devices, USB boards and input status. Those requests share a five-second budget. Each section has its own timestamp, duration and result; timeout, disconnect, refusal or malformed data does not discard other sections or the local snapshot. A disconnected console sends no requests. Saving uses a temporary sibling file, replacing the destination only after serialization/write succeeds.

The report includes console build identity; process memory/CPU/uptime; selected/checked phones; live-view, pointer-tracking and mirror preferences; cached/current mappings; local pause state; bitmap-update metrics and freshness; recent activity; kernel and receiver health, restart count and errors. Updated kernels additionally provide their startup assembly identity, process resource use and active calibration/movement pacing. Older kernels leave unsupported fields absent, not fabricated as zero or healthy.

Service fields are explicitly selected. Ownership tokens, unknown credential/serial fields and exception bodies are excluded. Identifiers, names, addresses and selected free-text activity/messages remain local diagnostic data: review before sharing. No screenshot or Send text box content is collected. Section samples are not atomic; bitmap timings are not physical-display latency. This is a snapshot, not an endurance measurement.

The concise operator guide covers everyday use, status/recovery, diagnostics, known limits and returning to the working version. It describes the candidate and does not authorize installation.

## Validation

| Check | Result |
|---|---|
| Release console/kernel builds | Clean, zero warnings/errors |
| Console headless self-tests | 238 passed (18 new diagnostics checks) |
| Kernel fake-board self-tests | 114 passed (3 new diagnostics checks) |
| Read-only collection | Exactly four GET routes; no lease acquisition, input or screenshots |
| Independent failure, timeout, cancellation, malformed data, legacy status | Passed |
| Credential/unknown-field filtering and mapping/recovery/calibration preservation | Passed |
| JSON save, locked destination, replacement and temporary-file cleanup | Passed |
| Installed console, kernel and native receiver | SHA-256 unchanged; `installed-files.json` |

Restricted runs first hit sandbox rename/pipe denials. Those observations are preserved separately. Approved runs outside the restriction used only fake transports and a private synthetic pipe. The locked-file regression initially expected only IOException; Windows returned UnauthorizedAccessException. The test now recognizes both failure forms and verifies the original contents and cleanup. Product saving correctly reported failure in both cases.

## Limits

No live app window, save dialog or physical-phone test was run. UI integration compiles but its real button workflow remains a later check. No gate is signed off by this report. The native-runtime package archived earlier is immutable and retains its earlier console/kernel; it does not inherit this change. New build manifests and a separate review package identify these bytes.

The deferred typing issue, Home Tab, FKA-Off App Switcher, phone discovery and full-rack acceptance remain open. No candidate was pushed, installed or promoted.
