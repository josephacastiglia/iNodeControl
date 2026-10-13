# iNodeControl / iMouse 2.0: Durable Project Progress Record

- **Updated:** 12 October 2026
- **Latest session:** Codex; resumed the saved Omp/Orca and Claude work
- **Repository:** `https://github.com/josephacastiglia/iNodeControl`
- **Local Root:** `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0`
- **Active Worktrees:**
  - Main Checkout: `local/coordinator-work` (`01fb669`, with the 10 October harness changes uncommitted)
  - Integration: `.claude/worktrees/keyboard-spec-reconcile` (`claude/input-timeout-integration`, `d0c4ccf`)
  - Gate 4 v2: `.claude/worktrees/gate4-harness-v2` (`claude/gate4-harness-v2`, `2c98f44`)
  - FKA probe: `../iMouseXP-2.0-fka-passthrough-probe` (`local/fka-passthrough-probe`, base `d0c4ccf`, isolated source changes uncommitted)

## Recorded candidate preparation, 12 October

The existing candidate launcher now defaults to a read-only check, prepares a fresh isolated copy only when requested, and requires an explicit launch mode. It validates source/build records, endpoint, hover-off profile and the console's no-window startup result. Optional proxy startup verifies its port, own-process readiness receipt, response PID header and upstream identity; failure cleanup is scoped to that process and records unresolved cleanup. Installed startup files are unchanged.

**49 launcher checks pass in each of PowerShell 5.1 and 7; two proxy receipt checks pass.** The actual combined console passed its no-window validation on a separate copy, with no settings writes or connection. Fresh direct/proxy run folders are prepared and verified but not launched. Existing console/kernel manifests and all three installed binary hashes still match. No new physical gate passes. See `analysis/candidate-launcher-20261012/REPORT.md` and `tools/candidate-launcher/README.md`. Next: kernel candidate configuration/readiness using the existing tools.

## Console diagnostic export, 12 October

The combined console's existing Export diagnostics action now collects a bounded read-only snapshot: build identity, local state/preferences, cached and current phone/board mapping, input ownership, calibration/pacing, per-receiver delivery/restart/error details, bitmap metrics and process resource use. Independent failures produce a partial report; disconnected export makes no service calls. Atomic save preserves an existing report when replacement fails. Unknown API fields, ownership token fields and raw exception bodies are excluded.

**238 console self-tests and 114 kernel self-tests pass**, with clean builds. The 18 new console checks cover collection, failure/cancellation, field filtering and file preservation; three kernel checks cover actual build bytes, process identity and active calibration. No UI/phone test ran; the save-dialog/button workflow and real diagnostic capture remain unverified. Installed console/kernel/receiver hashes are unchanged. See `analysis/console-diagnostics-20261012/REPORT.md` and `docs/OPERATOR-GUIDE.md`. Earlier immutable packages still contain their recorded earlier builds.

## Isolated native runtime package, 12 October

The combined candidate can include 126 audited native runtime files (168.7 MiB), with receipts from 91 installed packages and their available notices. The existing video probe passed four isolated five-second raw/H.264 scenarios; both bridge cases received all 150 frames and no unexpected library locations were observed. 16 runtime-staging, 22 release-staging and nine probe tests pass. No application/receiver or phone was operated. Twenty-four local notice gaps remain explicit; nothing is published. See `analysis/runtime-capsule-20261012/REPORT.md`.

The diagnostic export was subsequently integrated as recorded above. Physical acceptance remains open.

## Runtime prerequisite inventory, 12 October

Inspected 127 native files through the patched receiver, scanner and selected plugin import graph; no missing imports in that scope. Nine audit regressions and 22 package tests pass. .NET 8 core/Desktop runtimes are present. Corrected the current guide: this receiver uses built-in mDNS, not an external Bonjour dependency. A dated process snapshot found the rack stopped; nothing was started. File presence is not live acceptance or redistribution permission. See `analysis/runtime-readiness-20261012/REPORT.md`.

## Bounded receiver logging, 12 October

The combined candidate now caps each new receiver log at 4 MiB with one retained generation and handles file errors without throwing out of a background callback. Per-phone kernel status reports a logging warning until a later write succeeds. An existing oversized log is retained once. **20 focused recovery/logging checks and 111 kernel self-tests pass**; build is clean. Sandbox rename-denial failures are preserved beside the approved passing run. No real receiver or phone was used. See `analysis/receiver-logging-20261012/REPORT.md`.

## Combined candidate, 12 October

Active continuation is in `../iMouseXP-2.0-combined-candidate`, branch `local/combined-candidate-20261012`. The original main checkout is preserved. Combined main `01fb669`, Claude integration `d0c4ccf` and the October offline work. Deliberate conflict resolutions preserve both self-test lists and the kernel Home-sequence diagnostic. The text/timeout, isolated startup, frame/recovery and wall changes now coexist.

Added strict candidate path/address validation, an offline `--validate-startup` mode, actual DLL/module build identity in the console, and SDK-based `build-console.ps1` so isolation arguments are not dropped. **631 headless/simulated checks pass** across the suites listed in `analysis/combined-candidate-20261012/REPORT.md`. No UI suite or physical acceptance was run. Installed binaries and original working source are unchanged; no deployment or push.

Local checkpoints: integration `f5c70ec`, calibration/readiness `2c29852`. The valid planned rack configuration has five explicit bindings and 14 placeholders; the checker reports incomplete rather than physical readiness. Review bundle `output/staging/combined-review-20261012` contains 132 hashed files plus its manifest and verifies after ZIP extraction. An external archive preserves 74 files, both final managed builds and a standalone Git bundle; see `analysis/combined-candidate-20261012/ARCHIVE.json`. Native package sources retain original build bytes; the combined checkout differs only in newline encoding for all 79 inputs.

Continue from this combined checkout. Typing remains deferred. Remaining release work includes runtime/configuration checks and the physical gates, not another independent implementation of the preserved changes.

## Release review package, 12 October

Prepared `output/staging/offline-review-20261012/` plus a verified 1.33 MB ZIP. It includes the tested console/kernel, patched receiver, source snapshots, original provenance, portable integrity verifier and startup/rollback preparation guide. **31 checks pass** (22 new packaging tests and nine existing manifest regressions); the ZIP verifies after extraction. Installed hashes are unchanged. No GUI/rack/API/input/settings/restarts/deployment/commit/push.

The package is **review only**, with no launcher. The main checkout lacks the integration branch's isolated startup and text/timeout changes. External native and .NET dependencies and phone configuration are not a ready-to-run package. This gap is recorded as a release blocker rather than silently dropping Claude's work.

Report: `analysis/release-staging-20261012/REPORT.md`; guide: `docs/RELEASE-STAGING.md`; archive: `../iMouseXP-2.0-evidence-archive/20261012-release-staging/`. Next: reconcile the offline fixes with the integration branch in an isolated checkout and test the combined candidate offline. Typing investigation stays deferred.

## Phone-wall freshness and isolation, 12 October

Completed per-tile delivery labels, cancellable stream lifetimes, stale-completion rejection and a shared three-request screenshot limiter. A 19-phone simulation verifies independent states and peer progress through hangs, failures and cancellation. Timeout retries continue; image freshness does not change input readiness.

**201 tests pass:** 22 wall checks, 36 preview checks, 25 synthetic frame/metric checks and 118 console mock self-tests. The console builds with zero warnings/errors; its 17-source/six-output manifest verifies. Installed binary hashes are unchanged. No rack API, phone input, screen control, settings change, restart, deployment, commit or push. Physical tile rendering and rack performance remain untested.

Report: `analysis/wall-freshness-20261012/REPORT.md`. Archive: `../iMouseXP-2.0-evidence-archive/20261012-wall-freshness/`. Next offline priority is release staging and verification without changing the installed app. Typing remains deferred.

## Selected-preview freshness, 12 October

Connected delivery metadata to the selected-phone preview. Persistent status now distinguishes recent receipt, unknown age on legacy services, potentially old image, paused preview and failed updates. Metadata follows actually presented content; still pixels can refresh on new deliveries, while cached identities continue aging. Epoch/request/content guards reject late responses and obsolete presentations. Screenshot timeouts stay in the read-only retry loop rather than silently ending it.

**173 tests pass** (36 new preview/parser/API checks, 25 existing synthetic frame cases, 112 console mock self-tests). The console scratch build and manifest verify; installed hashes are unchanged. No rack API, phone input, desktop control, restart, deployment or push. Source remains local and uncommitted. A quiet image is not automatically treated as a frozen phone, and input readiness rules are unchanged.

Report: `analysis/preview-freshness-20261012/REPORT.md`. Archive: `../iMouseXP-2.0-evidence-archive/20261012-preview-freshness/`. Wall-tile freshness and synthetic multi-phone scheduling are the next offline extension. Typing remains deferred.

## Frame delivery and presentation diagnostics, 12 October

Completed offline: kernel frame instance/sequence/age and delivery reason, atomic screenshot metadata, per-phone recovery messages, diagnostics export fields with unknown values for legacy services. Repaired console rate expiry and long-gap accounting; FPS reports retain zero samples and describe bitmap-update scope. Both original measurement defects were reproduced before repair.

**231 tests pass:** 25 focused synthetic frame/metric cases, 74 kernel self-tests (four new API status checks), 112 console mock self-tests and 20 exporter tests. Kernel and console scratch builds are clean and their source/build manifests verify. Installed kernel/console/receiver hashes are unchanged. No rack API, phone input, screen control, receiver advertisement, restart, deployment or push. Source remains uncommitted.

`quiet` means no new receiver frame for two seconds, not a proven freeze. Legacy cached-image availability is unchanged. The console does not yet consume the new metadata for a freshness warning; that is the next offline task. Report: `analysis/frame-freshness-20261012/REPORT.md`. Archive: `../iMouseXP-2.0-evidence-archive/20261012-frame-freshness/`. Typing remains deferred and physical gates remain open.

## Accuracy consolidation and receiver recovery, 12 October

Consolidated the prepared accuracy suite into `tools/gate4_1000_tap_suite.py`; the v2 path is now a compatibility shim. Preserved the prior source snapshots and historical results. Run IDs/calibration cannot overwrite prior evidence; unknown ownership/recovery state is refused; command or cleanup failures stop the run; suspect isolation/stuck/double-click results stop before follow-up Home; short runs cannot pass the 1,000-trial criterion. Tests use registered in-process mocks with no socket fallback.

Repaired `AirplaySupervisor`: cancelled runs report stopped, child disposal is single-owner, wait exceptions use bounded retries, cleanup failures block replacements and remain visible, and duplicate runs are refused. **113 tests pass**: 14 accuracy scenarios, 17 evidence/safety guards, 12 focused fake-receiver cases and 70 existing kernel self-tests. The scratch kernel builds with zero warnings/errors and its source/build manifest verifies. The kernel's synthetic pipe tests needed sandbox escalation; they then passed without hardware initialization.

Report: `analysis/accuracy-recovery-20261012/REPORT.md`. Evidence archive: `../iMouseXP-2.0-evidence-archive/20261012-accuracy-recovery/`. No phone input, screen control, running-service request, receiver advertisement, installed-process restart, deployment or push. Source remains uncommitted; installed hashes are unchanged. Physical gate acceptance remains open. Next offline work is frame freshness/display accounting and failure diagnostics; typing stays deferred.

## Receiver memory fix, 12 October

The offline native investigation found a concrete leak in UxPlay's periodic streaming-report handling: each parsed property-list tree was left allocated. Source now frees the root after optional FPS logging. A native regression extracts the actual source case and uses real libplist: four valid-report cases leaked 10,000/10,000 roots before the fix (about 55 MiB per case), and all eight valid/malformed/logging/trailer combinations pass afterward (all parsed roots freed; at most 69,632 bytes measured growth). Eight additional tool tests pass. This is a demonstrated leak repair, not yet proof that every cause of the historical receiver growth is fixed.

Before changing source, a scratch native rebuild matched all 34 saved objects and the installed executable apart from its two timestamps and PE checksum. The patched receiver builds separately; only the expected report-handler object changes. Neither executable was launched as a receiver. Generated-video comparisons use a separate probe with the unchanged frame callback and a private self-consumed pipe; see `analysis/receiver-memory-20261012/REPORT.md` for final results and limits. Installed kernel, console and receiver hashes remain unchanged. No phone input, screen control, service request, receiver advertisement, restart, promotion or push. Changes remain uncommitted.

All four 180-second synthetic video runs completed: raw paths had zero measured post-warm-up slope; H.264 paths trimmed about 224 KiB over the interval. Both bridge runs received every frame (5,401 raw / 5,402 H.264). This excludes transport, audio, reconnects and actual iPhone stream variations; it does not establish complete receiver stability. The full record is archived locally under `../iMouseXP-2.0-evidence-archive/20261012-receiver-memory/` with checksums.

Next offline work: consolidate the existing accuracy harness and strengthen simulated recovery checks. Later live receiver-memory validation needs a coordinated window; do not restart the rack to install this scratch build. Typing remains deferred.

## Current direction: offline work; typing deferred, 11 October

The operator asked to skip the missing-space issue and continue work that needs no screen control. The issue remains unresolved and is deferred, not accepted as fixed. No further typing experiments or phone-setting changes are planned in this phase. Continue with offline test-tool reliability, diagnostics and release preparation; physical acceptance remains separate. The concise backlog is [WORK-REMAINING.md](WORK-REMAINING.md).

### Extended offline run

Completed diagnostics failure handling and settings/build identity, a source/build checksum verifier, honest endurance analysis, and safer soak preflight/failure handling. The final combined validation passes **80 tests**: diagnostics 18, build manifest nine, endurance analysis 15, soak safeguards 16, and the earlier timing runner 22. Main-checkout kernel and console each build twice cleanly with SDK 8.0.424; all output bytes match between the repeated builds. These are scratch builds, not the installed release or an accepted candidate.

The September telemetry reanalysis keeps its original files intact and reports the resumed block's 64/64 failed interactions as failure. Memory growth is concentrated in the five receivers (about 18–19 MB/hour private memory each); kernel/console trends are roughly flat. This attributes recorded growth to processes, not to a code-level cause. A static frame-bridge ownership review finds balanced sample releases and a bounded reusable BMP buffer; no receiver product fix is justified by that inspection alone.

One initial soak test escaped isolation, briefly used the read-only host sampler, attempted a kernel status socket request blocked by Windows error 10013, and appended one test row to old telemetry. No input phase ran. The row is preserved separately; the original telemetry and status checksums were restored/verified, and the test PID marker removed. Final tests replace host/UI/network boundaries and isolate their output. The report records this incident explicitly.

Report and evidence: `analysis/offline-backlog-20261011/REPORT.md`. Usage: `tools/OFFLINE-VERIFICATION.md`. Changes remain uncommitted and unpushed. Installed kernel, console and receiver hashes match the recorded working release; no phone input, desktop-control action, setting change, restart, deployment or promotion occurred.

Completed the next offline task in the existing Gate 6 runner: its console helper now has one 20-second deadline covering output reading and process exit, with bounded cleanup of that helper only. Invocation timestamps remain streamed, and success requires an exact `ok` completion line plus a zero exit code and timestamp. Silence, an open output pipe, excessive output and failed cleanup cannot silently count as success. Killing the helper does not cancel an action already accepted by the console; failures remain unknown outcomes with no automatic retry or API fallback.

Two new regressions failed before the repair. All **22 offline regressions (10 new)** and the built-in self-check now pass, including real Python-child pipe/cleanup checks. No Windows UI helper, phone API, desktop control, kernel/receiver restart or installed-app change was used. This repairs test tooling; it does not pass Gate 6. Source changes remain uncommitted. See `analysis/gate6-release-validation-20260916/OFFLINE-UPDATE-20261011.md`.

## Latest live result: repeated C24C shortcut and real-console tests, 11 October

**Repeatable success inside a prepared field; persistence failed. Gate 5 remains open.** Five unique fields with matched 30-second measurement waits produced Hithere / Hi there / Hithere / Hi there / Hithere. Both shortcut conditions preserved the space; all three baselines lost it. The middle baseline was shared and counted once. No named mode message was confirmed; the operator saw a yellow highlight. Physical FKA Off → On restored the baseline between comparisons.

The unchanged `b0708e3` console's actual Send text button produced exact short text and exact 100-character text when one shortcut was applied inside that same fresh note. A separate 100-character send in a new note after physical Home/app navigation, without another shortcut, lost its first space (99/100). A planned six-character append click produced no visible change or completion entry and remains unverified; no repeat click or API substitution was sent. No character padding, remapping, changed HID timing or automatic toggle was added.

FKA On and original appearance options were visually restored. The candidate closed normally and released its lease; test kernel 11624 and receiver 42004 exited. The unchanged release restarted as kernel 10892 with receivers C24C 38684 / C241 4760. Both phones were recast and the installed console restored as PID 43684. Final verification at 07:20:07 UTC confirmed both streams live, both phones free at generation 0, correct process paths and unchanged release/configuration/launcher/settings content hashes. The installed console's normal save moved only the settings timestamp. C241 had no device/receiver/input path in the temporary test configuration and received no test input. No promotion, deployment or push.

Latest report: `../iMouseXP-2.0-fka-passthrough-probe/analysis/fka-pass-through-probe-20261011/REPEAT-REPORT.md`. Repeat evidence archive: `../iMouseXP-2.0-evidence-archive/20261011-fka-pass-through-repeat/`, with per-file checksums and the completed restoration record. The earlier single sequence, its unmatched waits and completed restoration remain preserved in `LIVE-REPORT.md` and `20261011-fka-pass-through-live/`. A future typing fix would need an explicitly controlled workflow that keeps the phone's mode unknown and does not infer readiness across navigation/focus changes, plus trace evidence for the uncertain append click. That work is now deferred at the operator's request. More live testing needs coordination. Do not repeat the completed extra-click or matched-wait comparisons as pending work.


---

## 10 October continuation

Read the current branches, Claude's return handoff, the integration reports and Orca's latest work. The last main-checkout commits were on 7 October; the integration branch includes the 2 October FKA UIA runner. The two development lines remain separate. The installed release has not been promoted to the candidate.

The process inventory during this check found no running iMouse kernel, console or UxPlay receiver. This is a point-in-time observation, not an instruction to start or restart them. No phone API calls or desktop control were used in this session.

Continued offline by repairing `analysis/gate6-release-validation-20260916/run_gate6.py`. Seven new regressions failed before the repair. All 12 final regressions and the corrected built-in self-check pass. The repair prevents API fallback after rejected console input, separates first change from first correct frame, rejects unchanged/late frames as successful responses, retains failed trials and aborts further input, and separates percentiles by phone and input route. See that folder's README for the remaining limitations. This is test-tool work, not a Gate 6 pass or a product fix.

**Next product task as of this offline check:** the six-note C24C FKA-On comparison was pending. It was subsequently completed in the live continuation below; see `analysis/fka-typing-mode-20261011/REPORT.md`. Fresh-field first-space loss, Home inserting Tab, App Switcher with FKA Off, and receiver rediscovery remain open. The gate table below summarizes saved evidence; this session did not repeat every gate audit or acceptance run.

## Live continuation, 10–11 October

The operator started the release rack and authorized the C24C-only comparison. All six trials are complete in the prepared A-B-B-A-A-B order. FKA was visually verified On and left unchanged. A1/A2/A3 (no extra body click) and B1/B2/B3 (one extra body click) submitted `Hi there` through the original `b0708e3` candidate's real Send text button and visibly produced `Hithere`: 3/3 space losses in each condition. The extra click is not a demonstrated workaround under this procedure; the mechanism remains unresolved. A3 logged an additional "Still typing" warning despite one requested Send text click; the proxy confirms only one text command was delivered.

The archived original candidate was restored into an evidence folder because its old TEMP copy was incomplete. It uses an isolated settings directory, hover tracking Off and an unarmed logging proxy. Windows actions use Computer Use rather than the prepared PowerShell UIA helper. Interactive visual checks made the waits longer than the original plan: release-to-click-invocation ranged from 163,371 to 178,713 ms. B clicks opened an edit menu. This is a modified exploratory comparison, not an exactly matched short-wait acceptance run.

Evidence, exact build hashes, frames, console events, proxy logs and restoration checks are in `../iMouseXP-2.0-evidence-archive/20261010-typing-mode-ab/REPORT.md`. After the final trial the candidate closed normally, released its lease and the proxy stopped. The installed console was restored as PID 29160. Both phones are free; C24C generation 14 and mirroring, C241 unaddressed at generation 0 with its receiver running but not mirroring. Kernel PID 43928 and receiver PIDs 2360 / 18176 were unchanged. Operator settings and release hashes were verified unchanged. No phone-setting changes, kernel/receiver restarts, promotion, deployment or push occurred. Six new test notes remain. Next: offline first-space HID/focus review; the six-note comparison must not be treated as pending.

---

## 1. Major Goal & Acceptance Criteria
Deliver a dependable iNodeControl system for the agreed 19-phone rack and customer portal, satisfying all written criteria in `FINISH-CRITERIA.md` without weakening requirements.

### Truth-in-Evidence Gate Status (Correcting the Stale "11/12 Passed" Summary)
The earlier chat summary claiming "11 of 12 gates passed" is **stale and unsupported by saved evidence**. No gate is formally signed off for production release. The audited, evidence-backed status is:

| Gate | Status | Ground-Truth Scope & Saved Evidence | What Still Blocks Release Acceptance |
|---|---|---|---|
| **1. True Independence** | **Passed (within scope)** | Cold boot with zero vendor runtime verified (`analysis/independence-audit/cold-boot-evidence.json`). | Repeatable automated test after any binary cutover. |
| **2. One Obvious App** | **Passed (within scope)** | Single-instance, persistent `%APPDATA%\iMouse2`, startup diagnostics (`analysis/gate2-single-app/gate2-evidence.json`). | Full release installer packaging. |
| **3. Unmistakable Identity** | **Partial** | Guided visual identification script verified on one phone (`tools/identify_phone.py` on C241, `analysis/diagnostics/identify-c241/result.json`). | 14 boards still use placeholder IDs (`unbound-*`); full 19-phone rack mapping and visual indicators under rack load pending. |
| **4. Accurate Control** | **Scoped Pass** | 1,000/1,000 taps on 2 phones (C24C, C241) at single target `(250, 900)` (`analysis/gate4-1000-tap/results.jsonl`, `ISOLATION-AUDIT.md`). | Varied positions/distances, recovery from interruption, testing across all 19 pairs; Gate 4 v2 offline harness prepared. |
| **5. Everyday Controls** | **In Progress** | Short API-driven controls passed (`analysis/gate5-everyday-controls-20260916/`). | Console-level typing, fresh-field first space loss (FKA On), Home Tab side effect, App Switcher under FKA Off. |
| **6. Responsive Operation** | **Partial** | API HTTP dispatch measured (`1,820–1,844 ms`); pointer pacing `7 ms` (`pointer-reliability-20260915/gate6-7ms-*`); C24C Spotlight 4/5 (`accepted: false`). | True console-to-visible-response latency, $\ge 100$ ops/category, p50/p95, misses kept, second phone streaming. |
| **7. Smooth Live Video** | **Partial** | Kernel-store frame sampling verified on 5 phones (`analysis/gate7-video-accounting/report.json`). | Console's actual presentation path under multi-phone load, zero freezes. |
| **8. Predictable Group Control** | **Partial** | 2- and 4-phone parallel group dispatch and isolation verified. | Full 19-phone group control, cancellation under load. |
| **9. Graceful Recovery** | **Partial** | Crash detection (116 ms) and auto-relaunch (2.1 s) verified on single receiver. | Graceful recovery across multi-receiver fleet without orphan processes or frozen streams. |
| **10. All-Day Stability** | **Partial** | 8.05h duration passed across two kernels (`analysis/gate10-endurance-20260916/`); prior-block interactions 29/33 ok. | Resumed-block interactions 0/64 (409 conflict), memory slope $+90\text{ MB/h}$, Phone 5 freeze, 24h uninterrupted endurance. |
| **11. Full-Rack Operation** | **In Progress** | 19 physical phones mounted on 3 populated hubs (#0009, #0010, #0011 per `analysis/HARDWARE.md`); schema generated in `analysis/full-rack-config/`. | 14 boards use placeholder `unbound-*` IDs; 5-phone run (`analysis/gate11-five-phone-validation/`) had `pass: false` (Phone 5 Search missed, Group Home failed at 0.8s); full 19-phone live run pending. |
| **12. Diagnostics & Release** | **Partial** | Single-command diagnostic bundle exporter built (`tools/export_diagnostics.py`). | Release build reproducibility, source-to-binary provenance closure. |

---

## 2. Historically Verified Builds & Hashes

These are the handoff values, not a new 10 October binary/settings verification.
- **Installed Kernel:** `release\iMouse2-kernel-two-phone\iMouse2.Kernel.dll` (`BD1A68168E9270F029336CF8E13FF85E9B15FD67951EF545D1E973C2BFE634FC`)
- **Installed Console:** `release\iMouse2-two-phone-candidate\iMouse2.exe` (`46B9732947BA21ECFBEB57EFE2786B83DEA1FF4DDF3C456F1F85EFCF5F7AEAD5`)
- **Operator Settings:** `%APPDATA%\iMouse2\settings.json` (`72F51CC0BEE805F722D73BC024CAD771B19A68E2E7C04D9D47F8E9E4A8A5E5BA`)
- **Candidate-5 Console (b0708e3):** `%TEMP%\claude\imouse-candidate-5\iMouse2.exe` (`2A0D5CB94AF84226269507C2442BAC3DDAE524DB6E1EED4306B7C2AF79945253`), DLL (`E5A51FC6204566FA3B48C650FC239A42B158217D8045D2712850173980303AC3`)

---

## 3. Operating Boundaries & Inviolable Safeguards
- **Target Phone Scope:** C24C (`86:1D:4A:04:2F:F6`) only for authorized test windows.
- **Untouchable Targets:** C241 (`FE:A9:BC:D7:A0:44`) must receive zero input and zero lease acquisition without explicit authorization.
- **Required Approvals:**
  - Phone setting changes, kernel/receiver restarts, and desktop-control windows require **explicit user approval**.
  - Obtain explicit user approval before any desktop control or live testing that interrupts user workstation use.
- **Data & Process Isolation:**
  - Candidates run only with isolated data folders (`"trackPointer": false`) and hover tracking Off.
  - Never push `backup/*` branches or bring their unredacted contents into published work.
  - Never expose the withheld personal device identifier `(withheld: personal device)`.
- **Restoration Obligations:**
  - Restore the installed working setup (installed console on `%APPDATA%\iMouse2`) after each authorized test window.
  - No promotion, deployment, installed-launcher changes, pushes or destructive cleanup without authorization.

---

## 4. Continuation Mechanisms & Orchestration Limits
- **In-Turn Autonomous Execution:** Within this session, the coordinator operates autonomously across task analysis, implementation, review delegation, and validation cycles using tool chaining and background subagents (`task`, `reviewer`) with `wait`.
- **Continuation Limits (No Across-Turn Persistence Daemon):** Bounded demonstration verified in-turn task chaining and reviewer resolution. When a coordinator turn yields, execution halts until user input or a registered process event occurs. No background daemon or blind timer loop is configured to inject across-turn prompts. Active in-flight subprocesses terminate on CLI exit, window closure, or OS reboot. All durable state (evidence, builds, gate assessments, task queues) is persisted directly to Git and `PROGRESS.md` for immediate resumption.
- **Orchestration State Disclosure:** During setup testing, `orca orchestration reset --all` was executed. Pre-reset contents were not captured; nothing else was visible beforehand. Verified immediately afterward: legacy placeholder recreated (`tasks: 0`, `messages: 0`), demo run removed. Inviolable rule re-anchored: never run destructive resets without explicit user authorization.
- **Live Hardware Boundary:** Live tests requiring manual physical interaction (physical Home gesture, phone setting changes) are staged offline; they pause only their own live execution window, never the coordinator's offline progress queue.

---

## 5. Current Priority Queue & Status
1. **Coordinator Setup & Continuation Verification (PASSED):** Bounded hardware-free demonstration executed; reviewer findings resolved internally; continuation limits documented (in-turn only; no across-turn daemon).
2. **Gate 6 Timing Harness (PARTIAL / OFFLINE REPAIRED 10–11 OCT):** Extended the existing runner, with 22 offline regressions and its self-check passing. It records `first_visible_ms` and `first_correct_ms` separately, refuses implicit API fallback, keeps error rows, and separates phone/input-route percentiles. The console helper's output and process waits now share a bounded deadline; failure cleanup targets only that helper, and exact completion is required. It measures kernel screenshot arrival, not console presentation. Search still requires explicit API mode; Home in UIA mode needs a prepared Search screen per trial. Correctness classifiers, console display timing, repeated UIA setup and console-owned lease cleanup still need work before unattended live acceptance. The earlier empty reviewer report did not establish those requirements.
3. **Gate 11 Full-Rack Configuration (CONFIG CONSISTENCY ONLY):** Verified self-consistency of `analysis/full-rack-config/` against 19 physical slots via existing `tools/validate_rack_config.py` (ee445d7). 14 placeholder `unbound-*` IDs, Phone 5 Search miss / Group Home failure, and full 19-phone live run remain unverified.
4. **Gate 12 Diagnostics and Build Tooling (OFFLINE REPAIRED; ACCEPTANCE PARTIAL):** Diagnostics has 18 passing fixture tests covering partial collection, settings paths, managed build identity, known-credential filtering and non-overwriting export. A source/build manifest verifier passes nine tests; repeated scratch kernel/console output bytes match. No actual service export, cross-PC reproducibility or installed-release provenance sign-off was performed. See the extended offline report; future diagnostics reports still require review before sharing.
5. **Gate 4 Harness (OFFLINE CONSOLIDATED 12 OCT):** The prepared v2 work now lives at `tools/gate4_1000_tap_suite.py`; the v2 entry point imports it. Fourteen mock scenarios and 17 run/evidence guards pass. Old source snapshots are preserved. No physical accuracy acceptance was run; see the latest accuracy/recovery report.
6. **Gate 5 FKA Typing (DEFERRED BY OPERATOR; REPEATS COMPLETE):** The original six-note extra-click comparison lost the first space in all six notes. Exact-binary offline checks passed 60 assertions and preserved Space at the transport boundary. The separate default-disabled probe passed 123 simulated kernel tests and three invalid-startup checks. Five matched-wait fields later reproduced the shortcut/reset reversal twice (shared middle baseline). Real-console short and 100-character typing passed when the shortcut was applied inside that fresh note; a new note without another shortcut lost the space again. An append click was unverified. Mode acknowledgement, dependable focus/navigation handling and broader typing acceptance remain open. See the latest live result above and `REPEAT-REPORT.md`; no automatic prefix, mapping or timing change, promotion or push. Do not repeat completed comparisons or resume this issue without new direction from the operator.
7. **Gate 10 Reporting and Preflight (OFFLINE REPAIRED; PHYSICAL RUNS OPEN):** Analyzer 15 tests and soak safeguards 16 tests pass. Soak requires explicit live/phone selection and fresh evidence output, rejects occupied/paused/unknown targets without automatic Resume, stops after failed input, limits release to its returned approved tokens, and cleans its PID marker even if status writing fails. Saved telemetry is reanalyzed separately and original checksums match. No soak or phone interaction was run. Warm-up/resource budgets, native receiver memory investigation and full physical endurance remain open.
