# Consolidated recovery package and offline preparation

13 October 2026. No product binary was rebuilt in this step. No desktop control,
rack request, candidate window, listener, receiver or phone input was started.
The installed release, operator settings and saved configuration are unchanged.
No gate is signed off and nothing is promoted or pushed.

## Result

New immutable package: `output/staging/combined-recovery-20261013`.
It contains 689 inventory files (185,985,466 bytes), plus `package.json`.

| Identity | SHA-256 |
|---|---|
| Package manifest | `3d9ea9cf85eb570f9b4154621bca1610f9e4aa4a4b9d1c50d5c375c2d1250106` |
| Kernel DLL | `a45b38a3c628acee07310345ac638c1cfdf553fa32927fd92bc73b6649828877` |
| Console DLL | `a49c5100aa24cf504a033b121380f3734101518b69e3212a8b244f1fc5a2b743` |
| Launcher source | `e7f8127b09581cabd3003b00028a089a274f54d4ea992500f227bebf39d6ddf9` |

The kernel is the exact final build from
`analysis/receiver-process-cleanup-20261013/`, including the earlier screenshot
backpressure and retry-reporting repairs. Its version stamp reflects the build's
base commit; byte hashes and the embedded source manifest identify the changes.
There is no claim that it is the earlier physically tested kernel.

615 console/receiver/runtime/provenance entries are byte-identical to the
previous package. The previous package still passes strict verification and
was not modified. The source/build provenance and native runtime are embedded,
including the existing notice/source limitations. The bundle has its own guide
with valid package-relative verification and operator-guide references.

## Packaging change and checks

`tools/stage_release.py --include-launcher-source` optionally preserves the
root launcher byte-for-byte at `source/launcher/Open iMouse 2.0.ps1.txt`.
Its declaration and independent source hash must agree with the inventory.
This is inert source, not a runnable entry point, an isolated candidate launcher
or installation of the startup-error repair. Existing packages remain valid.

All **28 packaging tests pass**, including six new checks for exact source
preservation, missing source, inventory/provenance divergence, deletion,
relocation without the repository and an invalid executable declaration.
The new package's standalone integrity/source verification and separate native
runtime verification both pass. See `stage-tests.txt`, `package-verify.txt`,
`runtime-verify.txt` and `package-result.json`.

## Preparation defect found and corrected

The older preparation ran `--validate-startup` directly in the intended console
run. That mode writes `startup-validation.json` beside the executable. The
candidate launcher's strict inventory then correctly refused the run with
`Unexpected prepared-run file: bin/startup-validation.json`.
The read-only reproduction is in `previous-run-check.txt`. It contacted no
service and did not alter the previous run.

The new preparation retains the strict guard. It validates a separate,
byte-verified console copy and leaves the intended run untouched. It also uses
the immutable package's embedded source and build records instead of a mutable
checkout when preparing the console. Final launcher `-CheckOnly` passes.

Fresh unused run: `output/candidate-runs/recovery-20261013`.

- Exactly C24C's saved receiver/device/calibration rows were selected and
  structurally validated. C241 is absent. The source configuration is unchanged.
- The console profile uses an explicit port-9913 endpoint, isolated data and
  `trackPointer: false`.
- The exact kernel reports saved configuration valid with no hardware,
  listener, receivers or settings writes. Home remains the vendor sequence.
- A byte-identical console validation copy reports the correct data directory,
  endpoint and build hash, with no connection or settings write.
- The final intended-run launcher check passes. `run-inventory.json` records
  its pristine contents; `PREPARED-NOT-LAUNCHED.json` is outside console/bin.
- Protected installed binaries, launcher, settings and configuration retain
  their restoration hashes. The two active receiver logs are explicitly
  excluded from the static-file comparison.

See `preparation.json` and `console-final-check.txt`. The setup script refuses
to reuse its run folder. These are saved-file checks, not live preflight or
physical acceptance. Validation copies are preserved in the local archive,
not added as binaries to Git.

## Preservation and remaining work

`archive_run.py` preserves this record, package, prepared run, supporting tools,
focused commit patch and current acceptance documents outside TEMP under
`iMouseXP-2.0-evidence-archive/20261013-consolidated-package`. It verifies every
copied hash, the relocated package and the prepared inventory. Its separate
`archive-verification.json` is the receipt; archive completion must not be
inferred merely from this planned path.

No offline checks here establish current process/port/lease state, physical
binding, native loading on a clean PC or interactive console behavior. The
new kernel needs an approved interruption/restoration window before rack use.
Prior scoped live results apply to their original binaries only. Console
controls/cleanup notices, actual diagnostic export, varied-target accuracy,
receiver recasting, latency/video under load, 19-phone scale and final endurance
remain open. Home/App Switcher defects remain; typing is deferred. The launcher
repair is preserved as source but is not installed. Native distribution and
corresponding-source obligations remain separate release requirements.
