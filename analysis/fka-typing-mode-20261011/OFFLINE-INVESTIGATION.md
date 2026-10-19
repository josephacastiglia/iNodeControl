# Missing first space: keyboard reports and FKA focus

11 October 2026. **The host preserves Space; the shortcut repeatedly helps within a prepared field, but its effect did not carry reliably to a new note.** The installed release is unchanged. A separate, disabled-by-default test-kernel probe was prepared and run in explicitly approved C24C windows; see the live supplements below.

## Latest repeated and real-console supplement

Five distinct fresh fields with matched 30-second measurement waits gave Hithere / Hi there / Hithere / Hi there / Hithere. Both shortcut conditions preserved the space; all three baseline/reset fields lost it. The shared middle baseline is counted once. Preliminary safety-inspection frames were separate from the trial measurement frames. Shortcut and text used separate leases, unchanged key timing and no retry. The operator saw a yellow highlight but no named mode acknowledgement.

The unchanged preserved `b0708e3` console's actual Send text button then delivered exact short text and exact 100-character text when one shortcut was applied inside the same fresh note. A separate 100-character send after physical Home/app navigation to a new note, with no additional shortcut, lost its first space (99/100). This demonstrates a limit to the effect, without isolating which focus/navigation transition caused it. A six-character existing-field append click produced no visible change or completion entry and remains unverified; it was not retried or replaced by an API send.

Original FKA On and appearance options are visually restored, and the test candidate/kernel have exited. The release kernel 10892, receivers C24C 38684 / C241 4760 and installed console 43684 are restored. Final verification at 07:20:07 UTC confirmed both phones mirroring and free at generation 0, correct process paths, no test processes and unchanged binary/configuration/launcher/settings content hashes. C241 received no test input. Latest report: `../iMouseXP-2.0-fka-passthrough-probe/analysis/fka-pass-through-probe-20261011/REPEAT-REPORT.md`; the separate repeat archive preserves its evidence and checksums. The completed tests must not be described as pending. No automatic toggle, text padding, key remapping or timing workaround was added. Fresh-field typing acceptance remains open; an explicitly controlled, observable workflow is needed before any product fix can be claimed.

## First live supplement (preserved historical result)

On 11 October, three physically prepared fresh Notes fields gave `Hithere` with FKA On, `Hi there` after one Control–Option–Command–P shortcut, and `Hithere` after the operator physically cycled FKA Off → On. Every request was exactly `Hi there`. A named mode message was not confirmed, so the successful condition is “after one shortcut,” not verified Pass-Through On. It was one sequence through the leased API, with unmatched waits and separate shortcut/text leases. No key mapping, character timing or compensating space changed. This is a promising lead requiring repeated trials and real-console acceptance.

FKA On and its original display settings were visually verified. The test kernel exited normally and the original release, both live receivers and installed console were restored; binary/config/settings content hashes match. C241 received no test input. Three new dedicated notes remain. Both phones were free immediately after console restoration; a later idle C24C lease was recorded without disturbing it. No test process remains and nothing was promoted or pushed.

Full report: `../iMouseXP-2.0-fka-passthrough-probe/analysis/fka-pass-through-probe-20261011/LIVE-REPORT.md` from the main repository's parent workspace. The separate archive is `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-evidence-archive\20261011-fka-pass-through-live\`. The following sections preserve the preceding offline investigation; their untested statements describe that stage.

## What was established

The test loaded the exact preserved candidate `b0708e3` console DLL and the installed release kernel DLL as libraries. It did not start either application. `ApiClient.SendTextAsync` used an in-process HTTP handler, and `InputRouter` used an injected recording `IHidTransport`. There were no sockets, real phone IDs, USB handles, app windows or operator-settings reads in the harness.

| Check | Result |
|---|---|
| Both loaded DLLs match recorded SHA-256 values | Passed |
| `Hi there` payload and explicit eight key-down reports | Passed; Space is present |
| First send versus repeated send through the same router | Keyboard report bytes identical |
| Leading, repeated and trailing spaces | All preserved |
| Space at either side of the 12-character chunk boundary | All preserved |
| Uppercase letters followed by Space | Shift released; Space has modifier zero |
| Separate `Hi`, ` `, `there` sends | Same eight key-down reports |
| Enter before `Hi there` | Text reports unchanged |
| Cancellation during Space | Later letters not sent; neutral keyboard report at cleanup |

**60 assertions passed across 11 recorded sequences.** Each completed character has neutral / key-down / neutral reports. Every Space is `A2 00 2C 00 00 00 00 00`. Completed Space holds in this idle offline run were 91.5–95.0 ms; source schedules 90 ms.

Results: `offline/run-1/results.json`. Per-sequence `.jsonl` records are local evidence, ignored by Git and preserved in the separate evidence archive. The decoder is an unchanged copy from the existing cleanup harness (SHA-256 `085B86FEE0BE651F6FEEDD2E25CADF3AA0B5CCCF052422C4FED052A1401A90ED`). The explicit expected `Hi there` bytes and stroke framing are checked independently of that decoder.

The historical vendor `WriteFile` capture for ` Ab Z!` also contains this exact Space report, with report-ID zero preceding it. Its two observed holds were 38.399 and 45.606 ms. `offline/compare_vendor_reports.py` verifies this from the existing capture and command markers; it starts no instrumentation. Different timing is a remaining variable, not evidence that shorter holds would fix the loss.

### Limits

These records end at the argument to `IHidTransport.SendAsync`. They are not a capture from the physical board, its firmware, or iOS. The harness deliberately bypasses HTTP sockets and leases to characterize text conversion; it does not validate the ownership protocol or WPF button routing. Loading the actual binaries prevents source-version drift, but does not simulate a fresh Notes field or FKA. A successful API response still does not prove insertion.

## What the focus review says

Apple's [iOS 18 Full Keyboard Access guide](https://support.apple.com/guide/iphone/ipha4375873f/18.0/ios/18.0) identifies the highlight as keyboard focus and Space as Activate. Apple's [WWDC21 demonstration](https://developer.apple.com/videos/play/wwdc2021/10120/) distinguishes navigation from editing and uses Control-Tab to leave editing. Neither source establishes the mechanism of this first-space defect.

The product has no readback of iOS's selected accessibility element or editing mode. Its input acknowledgement reports command completion. A visible caret and a pointer click therefore cannot establish FKA editing readiness.

Relevant local observations:

- FKA-Off historical trials kept spaces; FKA-On fresh-field trials lost them. This implicates the setting in the tested configuration, while the mechanism remains unresolved.
- The completed 10–11 October A/B comparison lost the first space in all six notes, with and without the extra body click. That workaround failed under its recorded preparation and longer-wait method.
- The older C241 navigation/activation trial inserted `hi`, which contains no space. Its before frame highlights both the Search region and AutoFill; it does not establish a universal six-Tab entry procedure or exact typing after activation.
- “All character keys are accessibility commands until Typing Mode” is too broad for C24C: its letters arrive before the missing Space. The interpretation of that Space must be observed directly.

Do not prepend a dummy Space, double the first Space, guess a fixed Tab count, or reduce holds and call that a fix. Those approaches can alter already-working fields or activate another control. The pass-through shortcut was confirmed in C24C's command list and subsequently tested once as described in the live supplement; reliable switching and console typing remain unvalidated.

## Phone command identified during offline preparation

The operator opened C24C's FKA Commands page manually. A read-only mirrored frame (`commands-page-1.png`) confirms **Activate = Space**, **Move forward = Tab**, **Move backward = Shift-Tab**, and **Home = Fn-H**. The next frames show Interaction and Device. After the operator scrolled again, **`commands-page-4.png` confirms Pass-Through Mode = Control–Option–Command–P**, without Shift. This is evidence of the available command, not proof that it preserves Space or acknowledgment of the current phone mode. No assignments or settings were changed.

The operator then pointed out more rows below. `commands-page-5.png` reaches Restore Defaults at the bottom: Keyboard Gestures is Tab–G, and the touch/swipe/zoom/rotation/two-finger commands show no assigned shortcuts. No additional typing-entry command appears there. Restore Defaults was not activated. This was another read-only review, not approval for the proposed phone test; see `COMMANDS-BOTTOM.md`.

A separate worktree, `../iMouseXP-2.0-fka-passthrough-probe`, on `local/fka-passthrough-probe` from integration base `d0c4ccf`, now has a test-only `fn_key=FkaPassThrough` command. It is disabled by default and needs explicit startup opt-in. It uses the existing lease/board/Stop path, rejects multiple phones or accompanying text, and does not automatically prefix typing or retry an uncertain toggle. Its Release build is clean, **123 kernel self-tests passed (25 new probe checks)**, and three invalid-startup checks passed. All transports were simulated. The first full-suite attempt encountered a sandbox named-pipe restriction; the same build passed outside that restriction.

The probe's README contains the coordinated phone-window method and its restoration limits. Reading Commands did not authorize a test-kernel swap or temporary FKA mode changes; the operator subsequently gave explicit approval for that window. The receiver-source provenance differences were rechecked and recorded before the swap. The installed binaries and launchers were not changed. The single visible success is recorded in the live supplement, with no production fix claimed.

The six-note A/B comparison is complete and must not be rerun as pending work. Fresh-field exact typing and Gate 5 acceptance remain open.

Local preservation: `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-evidence-archive\20261011-keyboard-reports-and-fka-focus\`, with 41 hash-verified files. That first-stage archive is unchanged; the later command frame and probe are preserved separately in `20261011-fka-pass-through-probe`. Release kernel, original candidate and operator-settings hashes matched their recorded values after the offline tests. During that offline stage there was no phone input, lease acquisition, desktop control, restart or settings change; the operator navigated Commands manually and only mirrored frames were read. The later approved live window is recorded separately above.

## Reproduce the offline checks

From the repository root, with the original archive and release binaries available:

```powershell
dotnet build analysis/fka-typing-mode-20261011/offline/KeyboardReports.csproj -c Release -o analysis/fka-typing-mode-20261011/offline/build
dotnet analysis/fka-typing-mode-20261011/offline/build/KeyboardReports.dll analysis/fka-typing-mode-20261011/offline/run-new
python analysis/fka-typing-mode-20261011/offline/compare_vendor_reports.py
```

The harness refuses an existing output directory and rejects changed DLL hashes. It accepts only its simulated ID through its in-process handler.
