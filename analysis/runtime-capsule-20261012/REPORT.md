# Isolated native runtime and combined candidate package

12 October 2026. Local preparation and synthetic video only; no phone, receiver, kernel, console window or installed configuration was operated.

## Result

The candidate can now carry its audited native dependencies instead of referring to the development toolchain. `output/staging/native-runtime-local-20261012/` contains **126 runtime files, 176,888,742 bytes (168.7 MiB)**, from **91 installed packages**. Available notices and exact package metadata are preserved. The stager refuses changed inputs, unknown ownership, unsafe paths and existing output folders.

The release stager optionally embeds that capsule into the same review package as the console, kernel and patched receiver. It verifies the capsule first and refuses one audited for a different receiver. The portable verifier checks both inventories after relocation; it does not install, launch or approve the candidate.

## Functional runtime check

The existing generated-video probe was extended to compile with the development toolchain and execute against a separate runtime. It receives a restricted PATH, a private GStreamer registry and explicit scanner/plugin paths. Synthetic video source/encoder support is held separately; it is not included in the product runtime. Runtime/test DLL name collisions are refused.

| Five-second scenario | Frames processed | Frames received by private pipe | Result |
|---|---:|---:|---|
| Raw, discard | 151 | Not used | Pass |
| Raw, production frame bridge | 150 | 150 | Pass |
| H.264, discard | 150 | Not used | Pass |
| H.264, production frame bridge | 150 | 150 | Pass |

All four child processes exited successfully. There were no invalid frames. The module record contains 126 distinct runtime/test-support files and no unexpected modules outside those declared folders, the probe itself and Windows. Module capture is a snapshot at teardown, not a complete history of every library loaded and unloaded. The installed receiver hash remained unchanged.

Five seconds is deliberately a functional smoke check. The analyzer reports `insufficient_samples` for memory trends; no new stability or endurance pass is claimed. AirPlay transport, audio and physical iPhone behavior are outside this test.

## Tool validation

- Runtime staging: **16 tests pass**, including combined-package integration and rejection of an unrelated receiver audit.
- Existing release staging: **22 tests pass**.
- Native probe guards/analysis: **nine tests pass**, including protection against inherited toolchain search paths.

## Distribution and acceptance limits

The 91 package receipts contain installed version and declared license metadata; **24 packages have no notice file in the local package records**. These gaps remain explicit. The metadata is not legal clearance, upstream authentication, or a corresponding-source archive. No package has been published. A local test package remains distinct from a distribution-ready installer.

The .NET/Windows runtimes remain external. A clean-PC check, reviewed live configuration, physical controls/video/recovery tests, all 19 bindings and the final endurance runs remain outstanding. The first-space investigation is still deferred. No release gate was changed by this work.

Next product work: connect the complete diagnostic snapshot to the console's existing Export diagnostics button. Its current export records build/counts/activity but does not yet satisfy the full one-click diagnostic requirement.
