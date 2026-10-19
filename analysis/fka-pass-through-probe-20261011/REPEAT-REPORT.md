# C24C repeated shortcut and console typing checks — 11 October 2026

**Live window complete; release and FKA restored. Gate 5 remains open.** The operator explicitly approved repeated C24C typing, the real Send text button, a temporary kernel swap and restoration of the release and original FKA state. C241 received no test input. This record supplements the earlier one-sequence result; it does not replace it or pool its unmatched waits with the new trials.

## Setup and method

- Release kernel 42780, receivers C24C 42720 / C241 24004 and installed console 804 were recorded before the window. C241 was free at generation 0. C24C had an idle lease; no phone command was active. The console closed normally and released it.
- Original FKA frame shows On, Auto-Hide 1s, Increase Size Off, High Contrast Off and Color Default. The operator was asked to leave these unchanged.
- Release/config/helper snapshots were hash-verified; every probe source and build file still matches `provenance.json`. The inherited release-source differences remain as recorded in the previous live report.
- The release kernel stopped by the approved, path-checked Ctrl+C helper at 02:38:30 EDT. Test kernel 11624 and its sole C24C receiver 42004 started with copied configuration and `--fka-pass-through probe`. The operator recast C24C; FKA On was visually checked again. C241 has no receiver or input path in this test configuration.
- The unchanged preserved `b0708e3` console was copied into a separate candidate folder, DLL SHA-256 `E5A51FC6204566FA3B48C650FC239A42B158217D8045D2712850173980303AC3`. Its isolated settings explicitly name port 9913 and disable hover tracking. It started by exact path as PID 40516, without automatic ownership or input.

Each field is physically prepared by the operator using physical Home and a fresh Notes note. A preliminary safety frame is inspected separately. For each API trial, a new measurement frame then starts a 30-second monotonic wait. The shortcut condition sends one explicit shortcut near the start of that wait; text starts after the same 30 seconds in all conditions. Actual command times are recorded. This clarifies the prepared protocol's “first frame”: the timed frame is the trial measurement frame, not the earlier safety-inspection frame.

Every text command is exactly `Hi there`, with normal leases and release. Shortcut and text use separate leases. No extra spaces, remapping, altered character timing, automatic retry or Resume. Read-only phone capture uses 5 fps for the first five seconds and then about 1 fps; captures have their usual request/encoding overhead. The operator watches for a mode message. Conditions without a confirmed message stay labelled “after one shortcut.” Physical FKA Off → On restores the displayed setting between sequences; the Off transition needs operator confirmation.

## Results

| Trial | Condition | Visible text | Status |
|---|---|---|---|
| R1-A | Original FKA On, no shortcut | `Hithere` | Baseline reproduced; code 0, lease released |
| R1-B | After one shortcut | `Hi there` | Exact; code 0, lease released. Operator saw only a yellow highlight, no named mode message |
| R1-C | After physical FKA reset | `Hithere` | Missing space returned; code 0, lease released |
| R2-A | Shared R1-C baseline | `Hithere` | Same recorded trial serves both comparisons; no duplicate send |
| R2-B | After one shortcut | `Hi there` | Exact; code 0, lease released; named mode not observed |
| R2-C | After physical FKA reset | `Hithere` | Missing space returned; code 0, lease released |

The five unique API fields show A/B/A/B/A: three baselines lost the space, both after-shortcut fields preserved it. The shared middle baseline is counted once. R2-B waited 30,031 ms and its text request took 1,406 ms; R2-C waited 30,031 ms and its request took 1,313 ms. These reversals support a repeatable effect of the shortcut in this setup, without identifying the iOS internal mode or establishing general compatibility.

After R2-B the operator requested “do it again” rather than naming a mode message. To avoid a blind second toggle, the operator physically reset FKA Off → On; `r2-fka-restored/before.png` verifies On and the original appearance options. R2-C then ran. A new fresh note was prepared for the real-console short test, and one deliberate shortcut was sent while the operator was asked to watch.

Real-console short text passed visibly: one coordinate mouse click on the actual Send text button at 06:59:14.501 UTC sent `Hi there`, and `console-short-button/after.png` shows that exact text in the fresh note. The candidate text box showed 8/200 before sending. Shortcut and console were not combined in one lease: the helper released its lease before the button. The operator later reported only the yellow highlight, again with no named mode message. No prefix, extra space, altered key timing or automatic toggle was added to the product.

The operator physically used Home and prepared another fresh note without resetting FKA. Its empty state was visually checked. The actual Send text button was pressed once at 07:02:49.990 UTC, with the box showing 100/200 and the exact string `('Hi there. ' * 9) + 'Hi there!?'`. No additional shortcut was sent. This tests persistence of the after-shortcut typing state across physical app navigation, rather than a newly toggled condition.

**Persistence check failed:** `console-100-button/after.png` shows `Hithere.` followed by eight `Hi there.` groups and the final `Hi there!?`: 99 visible characters, with only the first space missing. The console reports “100 characters in 9 chunk(s)” at 03:03:05, confirming transport completion, not visible text exactness. No click was repeated. The short test's effect did not carry reliably to this newly prepared field. This does not isolate whether physical navigation, new-field focus or some other state transition ended it.

The candidate was disconnected normally before any further helper shortcut, and C24C became free. One final, distinct fresh-field 100-character trial used a physical FKA reset and a shortcut inside that same new field, to separate direct-condition success from persistence. A preparation frame showed FKA Off despite the first ready reply; the operator turned it On and `console-final-fka-on/before.png` verified On and original appearance options. No phone input was sent while its state was uncertain.

**Direct-condition 100-character check passed:** after physical Home and a visually empty new note, one shortcut was sent in that field and released. The existing candidate reconnected with hover tracking Off, without taking a lease before Send text. One actual mouse click at 07:08:54.210 UTC sent the same 100-character string. `console-direct-100-button/after.png` visibly matches all nine `Hi there.` groups and the final `Hi there!?`, including all spaces and punctuation. Activity reports “100 characters in 9 chunk(s)” at 03:09:09. There was no phone navigation between shortcut and typing, no retry, and no altered HID timing. This is one direct-condition long-text success, not general acceptance.

**Existing-field append is unverified:** the text box was set to ` Next.` (six characters; visible counter 6/200) and one actual mouse click was requested at 07:10:28.715 UTC. The phone's before/after text remained the same 100 characters, Activity had no append or failure entry, and no active command was observed in the capture. This does not establish where the click was lost or whether a command reached the transport. No second click was sent. The broader click issue remains unresolved; this record must not claim an append pass or silently substitute an API send.

| Console check | Visible outcome | Verdict |
|---|---|---|
| Fresh short text, shortcut inside the same note | `Hi there` | Passed once |
| New note after physical app navigation, no new shortcut | First space missing; 99/100 | Failed persistence check |
| Fresh 100 characters, shortcut inside that note | Exact 100 characters | Passed once |
| Same-field append ` Next.` | No visible change or completion entry | Unverified; no retry |

All four button attempts used the exact original `b0708e3` console, isolated settings, and coordinate mouse clicks from Windows Computer Use. Text was entered into the console with its supported editable value pattern; no phone input was synthesized through Windows shell tools. The test kernel remains the separately recorded probe build. No product fix, automatic mode inference or Gate 5 release acceptance is claimed.

After R1-B the operator replied “i only saw a yellow highlight. Ready.” in response to the mode-observation and physical FKA Off → On restoration request. `r1-fka-restored/before.png` verifies On with all original appearance options. The shortcut condition remains labelled “after one shortcut.” No second toggle was sent.

The operator asked whether the tests were repeating old work. To reduce physical preparation while retaining reversal controls, the method was narrowed to A1/B1/A2/B2/A3: R1-C also serves as R2-A. It is five distinct fields, not six independently measured trials. This change was stated before R1-C ran; the shared control must not be counted twice in totals.

## Restoration and evidence

The operator physically reset FKA Off → On after the final attempt. `fka-final-restored/before.png` verifies On, Auto-Hide 1s, Increase Size Off, High Contrast Off and Color Default. The candidate closed normally and released its idle lease. The verified Ctrl+C helper stopped test kernel 11624 at 03:12:52 EDT; no child process remained. The unchanged release restarted as kernel 10892 with C24C receiver 38684 and C241 receiver 4760. After the operator recast both phones, the installed console was restored as PID 43684 without interaction. At 07:20:07 UTC, `restoration-verified.json` confirmed both streams live, both phones free at generation 0, correct process paths and receiver parentage, and no remaining test processes. Release binaries, configuration, launcher and operator-settings content hashes match the preflight record. The installed console's normal save moved the settings timestamp without changing its content.

Raw evidence is in the ignored `live-repeat-20261011/`. The separate repeat archive is `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-evidence-archive\20261011-fka-pass-through-repeat\`; its `SHA256SUMS.txt` records each preserved file. The earlier `live-20261011/` and its 246-file external archive are unchanged. Eight distinct disposable Notes fields were prepared in this repeat window and left in place; none was deleted. No promotion, deployment or push.
