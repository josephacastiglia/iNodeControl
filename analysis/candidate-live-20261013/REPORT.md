# Candidate startup failure and runtime repair

13 October 2026. Authorized C24C-only window; APIs only, no desktop automation.
**Live controls were not reached.** The candidate receiver failed startup, the
installed release was restored, and the missing runtime components were fixed
and checked offline. No promotion, deployment or push.

## Live window and restoration

| Event | Observed result |
|---|---|
| Preflight | Rack stopped; no console/kernel/receiver processes or relevant listeners. Exact package and prepared-run inventories matched. Restoration files copied and hashed. |
| Candidate startup, 04:18:11 UTC | Kernel PID 41732; exact recorded DLL `6585cd5c…2601f`; C24C-only configuration. No candidate console was opened. |
| Receiver failure | UxPlay reported missing `playback` and `autodetect` plugins. Six starts (initial plus five automatic retries) exited; supervisor reported failed, no live frames. |
| Candidate shutdown, 04:18:46–47 UTC | Verified graceful Ctrl+C; kernel exited, no children remained. No force kill. |
| Release restoration | Original launcher started kernel 20432, receivers 35256/18808 and installed console 36940 from original paths. |
| Recasting | C24C reconnected. C241 initially did not list its receiver, then appeared after the operator closed/reopened Screen Mirroring. No additional receiver restart, cable change or settings change was performed. |
| Final check, 04:31:01 UTC | Both original receivers mirroring, zero restarts; both phones unowned/inactive/not stopped, generation 0. |

No input command, acquisition, Home, typing, FKA change or C241 input was sent
in this window. The candidate did enumerate connected boards during normal
startup. Operator settings, installed binaries, launcher and saved binding/
calibration content remained unchanged. Normal receiver logs grew during the
release startup; the console may save the same settings bytes on startup.

C241's PC-side Bonjour record resolved on Ethernet and VMnet1 and its receiver
was listening. A bounded passive listener later saw a query from the address
used by C241 (`192.168.4.85`) at 04:30:37 UTC. This is not proof of the cause of
the missing list entry or a validated recovery procedure. The listener and
the two short Bonjour queries have exited. Historical PIDs above must not be
used for a later window without rechecking identity.

## Cause and fix

The reduced runtime audit seeded only five video plugins. The synthetic
decoding test exercised those plugins, but did not call UxPlay startup.
`audio_renderer.c:gstreamer_init()` requires `playback` and `autodetect` even
with the configured `appsink`/`fakesink` arguments. Startup then initializes AAC
and ALAC pipelines requiring audio conversion, resampling, volume and level.

The audit now includes all six omitted plugins and follows their native imports.
The corrected capsule has **132 runtime files from 92 packages**. The previous
126 runtime binaries are byte-identical. The six additions match files in two
signed cached MSYS2 packages against the previously selected local public
keyring. No installation or network download was needed.

All **104 prior supplemental provenance/notice files** are retained, with their
original scope. `metadata/runtime-extension.json` identifies the new bytes and
their checks separately. The additional gst-plugins-good package leaves an
explicit source/local-notice gap; redistribution remains uncleared. Earlier
packages, including the failed one, remain unchanged.

## Tests and their limits

| Check | Result |
|---|---|
| Missing-startup-plugin regression | All six cases failed against the old audit; all pass after the fix. Native-audit suite: 10 tests pass. |
| Existing runtime staging | 22 tests pass. |
| Existing probe helpers | 9 tests pass. |
| Exact production renderer source + old runtime | Exit 2; reproduces the missing playback/autodetect messages offline. |
| Same source + repaired runtime | Exit 0; AAC/ALAC fakesink and H.264 appsink initialization/teardown pass, no unexpected loaded modules. |

`tools/receiver_memory_probe/check_startup.py` compiles the selected, recorded
production renderer sources and logger into a bounded test executable. It does
not link UxPlay's server/discovery code, read a phone, play sound, open a window
or use the installed frame pipe. Runtime search paths and the plugin registry
are isolated. Sources and loaded libraries are hashed. Both final comparison
runs use the receiver source preserved in the original package, matching that
receiver's manifest. Compiler warnings in unchanged renderer sources are saved.

One preliminary test-tool attempt omitted the logger callback and asserted.
The tool was corrected and both conditions rerun into fresh evidence folders;
that attempt is retained, not treated as a product failure. A preliminary
package omitted old supplemental metadata and was superseded by the final
preserving package. A staging attempt using the checkout's differently hashed
native files was refused before creating output; final staging uses the exact
archived receiver source. The signature utility could not initialize inside the
sandbox; normal-permission verification passed without relaxing signature checks.

The repaired package has not been started as a real receiver. These checks do
not cover AirPlay discovery/transport, live audio/video, clean-PC installation,
physical input, the actual console buttons or endurance. Managed console/kernel
tests were not rerun: their binaries are unchanged from the recorded 382/179
checks. No gate has advanced from this startup failure.

## Next candidate

`output/staging/combined-runtime-startup-final-20261013` keeps the same console,
kernel and patched receiver executables, with the expanded runtime and preserved
provenance. Both standalone integrity verifiers pass. The **686-file** package
(plus its manifest) is prepared in a fresh C24C-only run at
`output/candidate-runs/runtime-startup-20261013`; both exact binaries pass
`--validate-startup` with no service, receiver, window or hardware access.
The console uses isolated settings and hover tracking off. See `preparation.json`
and `run-inventory.json`. This is not the failed `scope-release-20261012` run.

At the next coordinated window, first confirm the corrected receiver remains
running before requesting a recast. Then perform the existing C24C-only API
smoke plan. Keep typing deferred, FKA unchanged and C241 free of input. Actual
console-button acceptance remains distinct from API tests. Restore the original
release as before. Do not relaunch the known-incomplete package.

## Preservation

Fix and primary records are committed locally as `80a181b`, not pushed.
`../iMouseXP-2.0-evidence-archive/20261013-candidate-runtime-startup` preserves
864 files (225,676,996 bytes), plus its checksum inventory: the failed window,
all probe attempts, exact source inputs, the corrected package, prepared run,
restoration snapshot and single-branch Git bundle. All copied hashes, the
bundle and the archived package verify. See `archive-verification.json`.
