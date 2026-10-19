# Priority 2: repeatability and recovery

This record explains the recovery candidate and the remaining live checks for
the Marketing Farm developer. Scope: **C24C, Instagram @xs.halle.xo, draft only**.
Offline preparation is complete. **Fresh-phone validation and app-restart
persistence are pending.** No desktop or phone input occurred in this pass.

Product source: local commit `e066acc` on
`local/combined-candidate-20261012`. The native assembly was built before that
commit; its exact hash and source snapshot are recorded in `validation.json`.

## What changed

The creation window offers **Inspect saved draft · no Save** when the retained
creation records a started Instagram Save. The button opens a separate check;
opening it only reads local status. Explicit Start is required before phone input.

The check opens Create → Post → Drafts, locates a unique matching cover, checks
all three full-size slides in order and the complete visible caption, then
releases C24C. It sends no Save, import, caption entry, publishing or messaging.
It leaves the phone on draft details rather than sending extra actions to exit.

The original creation journal, uncertain outcomes and duplicate-creation hold
stay unchanged. The inspection request pins the source creation ID, store,
revision, journal hash and immutable package. Editing the local carousel does
not replace that source. Missing/duplicate covers, wrong captions/accounts,
permissions, stale evidence and changed ownership/receiver context stop the check.
After a disconnect, a separate explicit inspection requires the phone to be free
and the exact account profile visible. It never takes an active lease or resumes
the interrupted editor.

Two related fixes:

- A crashed job could appear nonterminal again while another job held the worker
  lock. Interruption is now committed while holding that lock. Later reads stay
  terminal and never rerun the old callback.
- Creation inserts caption operations between Details and Back, so the existing
  unsent-Save refresh did not accept its history. Creation now requires its exact
  slide/caption sequence and a later exact Details observation. One fresh decision
  is allowed only after local expiry **before transport**. Lost Save replies,
  changed prompts, cancellation and a second expiry still stop without replay.

The candidate remains disabled without the explicit isolated creation config.
Its only kernel endpoint is `http://127.0.0.1:9916/api`; source identity is checked.
The installed release, settings and shortcuts are unchanged. FKA was not changed;
C241 was not addressed. Nothing was promoted, pushed, published or messaged.

## Offline verification

| Check | Result and scope |
|---|---|
| Complete Python farm suite | 452 tests, zero failures/errors/skips, 317.5 seconds; fixture kernels and disposable loopback servers |
| Native Release build | Zero warnings/errors; output `output/codex-farm-recovery-20261019` |
| Native headless suite | 564 checks; no desktop window/physical hit testing |
| Retained-layout suite | Eight tests, 46.406 seconds; actual observer/guards with archived C24C images/OCR and simulated HID |
| Boundary matrix | Lost reply, last-dispatch Stop, disconnect and receiver-session change at each of seven inspection actions; no later semantic action or Save |
| Additional retained cases | Three protocol repeats; wrong account/caption, stale delivery, failed OCR and app returning to profile mid-inspection; no app-restart success inferred |
| Creation prompt cases | One local expiry sends Save once from a new exact frame; persistent expiry sends none; lost reply remains unknown |
| Negative controls | Preserved pre-fix job status fails the hard-process-exit test; old prompt-history rule refuses the new creation's unsent Save. Source files are not changed by the controls |
| Installed files | All 25 before/after hashes match |

Results: `full-tests.json`, `native-summary.json`, `retained-tests.json`,
`negative-controls.json`. Detailed logs and the headless inspection render are in
this folder. The candidate DLL hash is in `native-summary.json`. The earlier
95-test focused run preceded the additional HTTP tests; the 452-test full run
includes them. Retained-layout fixtures reference the preserved 18 October
archive; they do not measure OCR accuracy on a fresh app version.

The real completed creation `b8c155e2-1670-4f60-a090-aeff921e162e` also passes
offline recovery admission. All 441 source data files were copied and checked
before opening the isolated copy; the original files remain unchanged. The
headless native inspection driver compiled cleanly and passed its dry run
(assembly hash, inspection route and zero window handles), without HTTP or a
running backend. This checks preparation, not a phone draft.

The reports, current runtime source, exact native/driver binaries and copied
backend evidence are preserved locally under
`iMouseXP-2.0-evidence-archive/20261019-farm-recovery-offline`. See
`archive-summary.json` for file totals and the checksum-manifest hash. Nothing is
uploaded. The rack remains stopped, matching its starting state.

To repeat the offline checks, run from the repository root:

```powershell
python analysis/farm-recovery-20261019/run_tests.py --full
python analysis/farm-recovery-20261019/run_retained_tests.py
python analysis/farm-recovery-20261019/run_controls.py
./analysis/farm-recovery-20261019/Build-And-Test-Native.ps1
```

The Python runners write their summaries/logs here. The native script builds only
the separate output and starts `--self-test` hidden with isolated temporary data.
None of these commands starts a rack service or contacts a phone.

## API and interface

`/api/farm/draft-recoveries` supports explicit Start, status/history, retained
frames and store-bound cancellation. GET/eligibility never connects to the phone.
Health exposes the disabled-by-default `draftRecovery` capability. Origin checks
and cancellation outside the operation lock match the other bounded draft routes.

A Start request contains the ordinary saved draft fields plus `creation_id`,
`creation_store_id` and `creation_record_sha256`. All are checked against the
retained creation before any transport is constructed. A repeated ID retrieves
the same request; a changed payload is refused. Native bookmarks preserve that
identity before POST and after a lost reply or window restart. The interface
reports **Matching saved draft observed**, not that an uncertain original Save
succeeded.

The separate candidate launcher defaults to simulation. Its live validation
uses `-DraftCreationConfig` and the isolated creation/inspection data. It does not
start or replace a kernel/receiver, alter the installed launcher or promote a
build. `launcher-simulation.json` and `launcher-live.json` record ValidateOnly;
neither starts processes.

## Next live validation

Before starting, check process identities, free ports, C24C's binding/ownership,
the exact candidate hashes and protected installed files. Preserve the original
creation data; use an isolated copy, never rewrite historical evidence. Use the
private C24C-only kernel/receiver and the headless native handler, with FKA
unchanged and C241 untouched. The operator initially connects mirroring and opens
the authorized Instagram profile.

1. Inspect the known saved three-slide creation. Confirm every slide/caption,
   its retained frames, no Save/import/typing commands and ownership release.
2. Repeat using fresh request IDs and fresh phone evidence; return to the profile
   before each run. Prior success does not authorize reusing old frames.
3. Check lost admission/status responses and a bounded backend interruption;
   retrieve the original request and inspect separately, without replay.
4. Verify app-restart persistence separately after a demonstrable Instagram
   termination/relaunch. Returning Home or reopening an editor does not prove
   a restart. This pass implements no force-quit gesture and records
   `appRestartVerified: false`.
5. End with confirmed release and stop only the private services started for the
   window. Recheck all protected hashes and report the phone's final screen.

Unknown iOS dialogs still require review. This work does not add generic prompt
click-through, recurring phone execution, new platform formats or automatic
publication/messaging. Priority 2 remains partial until the live checks pass.
