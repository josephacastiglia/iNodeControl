# Exact candidate configuration and acceptance preparation

12 October 2026, offline. No desktop control, phone input, rack connection,
service/receiver start or installed-file change.

## Prepared configuration

The candidate's saved configuration was derived from the three files named by
the installed desktop launcher's source: `analysis/two-phone-config/` in the
original checkout. This was a read-only inspection; the launcher was not run.
The C24C receiver, device and calibration records were selected consistently.
Only C24C is present or enabled for input. C241 is absent from this prepared
candidate; the original two-phone configuration was not edited.

The review package is `output/staging/combined-runtime-provenance-final-20261012`.
The separate run folder is
`output/candidate-runs/combined-acceptance-checked-20261012`. It contains a kernel
binary copy, isolated kernel data and a console prepared with the existing
candidate launcher. Console hover tracking is off and the endpoint is explicitly
9913. No operator settings were used as a seed. Receiver/runtime paths refer to
the immutable review package; neither executable has been started as a receiver.

## Checks

`preparation.json` records the final result and exact hashes. The preparation
script requires all of these checks before writing that completion record:

- The original package verifies; copied managed binaries match its inventory.
- Both original and selected rack records pass the existing structure validator.
- Kernel `--validate-startup` reports one receiver, C24C-only input, complete
  saved bindings, default vendor Home, and no hardware/listener/receiver/settings
  work. Its reported DLL hash matches the package.
- Console `--validate-startup` reports the intended isolated data directory,
  explicit address, no connection/settings write and the package's exact DLL.
- Kernel files, isolated console settings, original saved configuration and
  previously protected installed hashes remain unchanged.

These are actual offline subprocess checks, not a new physical pass. No console
window was opened. Live port availability, ownership, native loading, physical
binding, pointer calibration and mirroring remain untested on this candidate.

## Preliminary attempts retained

The first attempt stopped during console preparation: Python inherited the
PowerShell 7 module path when invoking Windows PowerShell 5.1, making its
`Get-FileHash` unavailable. A read-only comparison confirmed that allowing the
child to initialize its own module path restored that command. Only the child's
environment was changed; the host, profiles and launcher source were untouched.

The next attempt completed both product validations but the record assembler
used `build.sha256` instead of the console's `build.Sha256`. That recorder error
was corrected. Both preliminary directories and outputs remain available; the
final run used a fresh folder and never overwrote an earlier prepared run.

## Acceptance record

`docs/CANDIDATE-ACCEPTANCE.md` separates completed offline checks from API-only
observation and the future coordinated console/phone window. It preserves the
written accuracy, latency, video, recovery, scale and endurance thresholds.
The Gate 4 criteria now link to the already consolidated harness instead of
instructing a future agent to repeat work on a parallel v2 implementation. No
requirement or gate checkbox was weakened or marked newly passed.

The Home Tab and FKA-Off App Switcher defects remain open, and the typing issue
stays deferred. A later kernel swap still needs an approved interruption and
restoration window. Historical release evidence cannot sign off the new build.

## Preservation

Preparation and the acceptance guide are committed locally as `5dec369`, not
pushed. The external `20261012-candidate-acceptance` archive contains 67 files,
18,198,792 bytes plus its inventory. All hashes, the prepared-run inventory and
the active-branch Git bundle verify. It includes both preliminary attempts and
a reference to the separately archived full review package. The final read-only
check found zero rack processes and no port-9913 listener; nothing was started.
