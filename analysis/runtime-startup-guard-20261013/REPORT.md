# Refuse incomplete receiver runtimes before starting the rack

13 October 2026. Offline follow-up to the failed candidate window. No screen
control, service restart, phone input, FKA change, push or promotion.

The saved broken runtime passed the old kernel's startup validation because it
only checked directories and the scanner. Its real receiver then used all five
retries on missing plugins. The runtime itself was repaired in the preceding
[record](../candidate-live-20261013/REPORT.md); this change prevents the kernel
from starting with that known incomplete file set again.

## Change and evidence

`ReceiverRuntime.ValidateFiles` checks the scanner and eleven GStreamer plugin
files used by the fixed appsink/fakesink launch mode. Missing, empty or directory
substitutes are refused with a list of files and repair guidance. Both normal
startup and `--validate-startup` call it before listener, board enumeration or
receiver startup. External frame-pipe hosting does not need a local runtime.

| Check | Result |
|---|---|
| Release build | No warnings or errors |
| Kernel self-tests | 206 passed, 27 new; fake HID transport only |
| New tests against old product | Failed as expected on the missing-scanner diagnostic |
| Actual old kernel + saved broken runtime | Validation incorrectly returned 0 |
| Guarded kernel + saved broken runtime | Exit 2; all six omitted plugins named; no components started |
| Guarded kernel + repaired runtime | Exit 0 in validation mode; no components started |
| Saved input packages/configuration/protected release hashes | Unchanged through CLI comparison and preparation |

The first sandbox self-test attempt failed at a synthetic named pipe before
reaching the regression; it is retained as `before-tests.txt`. The same before
binary was then run with local execution permission and reached the expected
test failure (`before-tests-unrestricted.txt`). The fixed suite passes in
`self-tests.txt`. Do not count the sandbox failure as the regression reproduction.

## Exact candidate

- Kernel DLL: `e0f00fa86c217e2c00913e22adc04c7c9c5477e670078b7a94f19e9d5af92e16`.
- Source/output record: `kernel-manifest.json`; source includes the uncommitted
  guard on parent `e3317b2`. The record, rather than the embedded version stamp,
  identifies the tested source.
- Review package: `output/staging/combined-runtime-guard-20261013`, 687 files
  plus `package.json`; manifest hash
  `8a22ca7b5dd081f8e723ccb8430dad29ff28d58a6c65d9424260e7e12ed44561`.
- Prepared run: `output/candidate-runs/runtime-guard-20261013`, C24C-only kernel
  and isolated console settings with hover tracking off. See `preparation.json`.

The console, native receiver and repaired runtime bytes are unchanged. The
687-file package includes the new kernel source, binaries and updated preparation
guidance. Both exact startup validation modes are used during preparation, with
no normal app/window or service launch. Prior packages and evidence are retained.

## Limits and next step

This guard checks file presence and size only. It does not prove native imports
load, reject a nonempty corrupt DLL, attest a build, establish discovery or measure
physical video/input. The prior production-renderer probe remains the separate
offline loading check for the unchanged receiver/runtime. Actual receiver launch,
the short coordinated C24C smoke checks and the rest of release acceptance remain
pending. No gate advanced. Typing remains deferred; C241 input remains excluded.

The last physical restoration record remains the preceding window's 04:31 UTC
observation: both installed receivers live and both phones unowned. Historical
PIDs must be rechecked before any future window. No further rack change was made
by this offline follow-up. See `archive-verification.json` for preservation.
