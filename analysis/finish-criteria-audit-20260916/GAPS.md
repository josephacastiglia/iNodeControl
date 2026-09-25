# Evidence & Gap Matrix — 23 September 2026

Auditor: Grok 4.7. Offline update of [FINISH-CRITERIA.md](../../FINISH-CRITERIA.md) against artifacts on disk. No live hardware inputs. The Gate 10 soak was not restarted. Final analyzer pass 2026-09-24T04:34:31Z after the harness stopped on duration.

**None of the 12 gates are signed off.** An implemented feature, a tool, a schema, or a short live demonstration does not close a gate.

## Categories

| Label | Meaning |
|---|---|
| Demonstrated Foundation | Real on-disk evidence of a capability. Not gate closure. |
| Partial | Some gate bullets evidenced; others missing or too narrow. |
| Open | No qualifying evidence for the gate's acceptance metrics. |

## Current recorded identity (not a sign-off)

Read at audit time. A later functional change cannot inherit this record.

| Role | Path | Notes |
|---|---|---|
| Console | `release/iMouse2-two-phone-candidate/iMouse2.exe` | Live PID 11224. Window title in source is **iMouse 2.0 — Independent AirPlay**. Header badge `v2.0-rc1 · Independent AirPlay`. DLL SHA256 `CC8049B444998B1D95E8D8AEC41FB1DFE3552A9D4AA58E92F64D3289A5A038D2` (written 23 Sep 2026 21:08). |
| Console self-test | `release/iMouse2-two-phone-candidate/qa/self-tests.json` | **112 passed**, mock transport, 23 Sep 2026 21:08:52. Not a live input check. |
| Kernel | `release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe` | Live PID 4376. DLL SHA256 `BD1A68168E9270F029336CF8E13FF85E9B15FD67951EF545D1E973C2BFE634FC` (written 22 Sep 2026 20:36). Command line has no `--legacy`, `--precise-delay`, or `--precise-movement`. Source default is high-resolution **7 ms**. |
| Live config | `analysis/five-phone-config/` | `--input-pid C24C,C241,C214,724E,F215` |
| Everyday shortcut | [OPEN-THIS-APP.md](../../OPEN-THIS-APP.md) → `Open iMouse 2.0.ps1` | Still starts and accepts only `C24C,C241` and `analysis/two-phone-config`. It will refuse the live five-phone kernel as a different configuration. |
| Receiver | `tools/airplay/uxplay/build-imouse/uxplay.exe` | Independent UxPlay, not vendor AirPlay |
| Settings | `%APPDATA%\iMouse2\settings.json` | `ResolveDataPath()` in `MainWindow.xaml.cs`. Verified by `tools/test_persistent_settings.ps1` (script exists; this audit did not re-run it against the live console). |

Prior recorded hashes are historical, not the live bytes: console `B38645DB…6EC051` and `6D960FA0…F590B7`; kernel rollback `A995CF5B…7851BF`; Gate 6 validation kernel `277A24F3…4408B5`.

Rejected binaries stay rejected: `release/iMouse2-kernel-precise-candidate`, `release/iMouse2-kernel-click-candidate`. `--precise-movement` remains a deprecated flag.

## C241 3 ms regression (historical; not the live kernel)

The 16 September `--precise-movement` deployment (PID 12516) passed C24C 9/9 and failed C241 (3/5 cycle, 2/4 location, **0/5** targeted rerun). Rollback to the then-current legacy kernel restored short Search hits. Recast, Control Center, and focus state were reset during that cutover. This audit does **not** assert a C241 hardware limitation, and it does **not** treat 3 ms as the proven sole cause.

Later 7 ms runs did hit C241 Spotlight (probe 9/9; release-validation sample 5/5; five-phone isolated Search on retry). That does not explain the 3 ms miss, and it does not close Gate 4 or Gate 6.

Evidence: [HANDOFF.md](../pointer-reliability-20260915/HANDOFF.md), [legacy-control/results.json](../pointer-reliability-20260915/legacy-control/results.json), [precise-candidate-deploy verification.json](../precise-candidate-deploy-20260915/verification.json).

## Summary

| Gate | Name | Category | Foundation, not closure |
|---:|---|---|---|
| 1 | True independence | Partial | Vendor-string scan clean. Vendor processes still running. Cold boot not executed. |
| 2 | One obvious app | Partial | Branding, AppData settings, HTTP.sys parent check. Shortcut is still the two-phone entry. |
| 3 | Unmistakable phone identity | Partial | `identify_phone.py` live on C241. Hub #0010 slots mapped. 14 boards still unbound. |
| 4 | Accurate control | Partial | 18/18 Spotlight, 22/22 within 5 s, 100% isolation on a short two-phone sample. Not 995/1,000. |
| 5 | Complete everyday controls | Partial | Control Center, App Switcher, horizontal swipes, short typing. Not the full character set live. |
| 6 | Responsive operation | Partial | 7 ms Search-after-Home dispatch ~1.82–1.87 s on short samples. Not 100 observations, not console-click latency. |
| 7 | Smooth, honest live video | Partial | Kernel unique-vs-incoming 96.6–100% on 5 phones, max poll gap 37 ms. Not the console present path. |
| 8 | Predictable group control | Partial | 2- and 4-phone group pass. 5-phone Search pass. 5-phone Home snapshot missed. |
| 9 | Graceful recovery | Partial | C24C crash detected in 116 ms, relaunch in 2.1 s, post-recast Search hit. Retries and disconnect open. |
| 10 | All-day stability | Partial | 8-hour duration PASSED (8.05 h, two blocks, 0 restarts). 24-hour run still open. |
| 11 | Full-rack operation | Partial | Live 2 → 4 → 5. 19-slot schema validates. 8 and 19 not live. |
| 12 | Diagnostics and release | Partial | `export_diagnostics.py` wrote a bundle. User instructions and sign-off open. |

## Tools added for these gates

| Tool | Gate | What it does | What it does not do |
|---|---:|---|---|
| `tools/verify_independence.ps1` | 1 | Lists vendor processes, 9911/17000 owners, and vendor-string links in our binaries. | Does not reboot or stop vendor services. Report sets `cold_boot_not_executed`. |
| `tools/prepare_cold_boot.ps1` | 1 | Check-only plan. Backs up `iMouseService` without applying `start= disabled`. | Did not change service start mode. |
| `tools/restore_vendor_services.ps1` | 1 | Planned restore: `sc.exe config iMouseService start= auto`, then start. | `restore_applied` is false. |
| `tools/post_reboot_test.ps1` | 1 | Post-reboot input/video check. | `post_reboot_launched` is false. |
| `tools/identify_phone.py` | 3 | Opens Control Center on one phone, then Home. Other phones are not addressed. | Not run on the other 18 boards. |
| `tools/force_recast.py` | 9 | USB-HID Screen Mirroring reselect. Live pass on C241. | Not automatic iOS recasting. Not a Gate 9 close. |
| `tools/verify_video_pipeline.py` | 7 | Kernel BMP uniqueness vs sequence frames. | Does not sample the console present path. |
| `tools/analyze_endurance.py` | 10 | Read-only soak analyzer. Writes `DASHBOARD.md` and `dashboard.html`. | Re-run 2026-09-24T04:34:31Z. That pass is the completed soak, not the 01:01 UTC dashboard. |
| `tools/export_diagnostics.py` | 12 | One read-only JSON bundle. Does not acquire leases. | The saved bundle is not a release sign-off. |
| `tools/validate_rack_config.py` | 11 | Offline 19-slot schema check. Re-run this audit: **all checks passed**. | Not a live 19-phone run. |
| `tools/test_launcher.ps1` | 2 | Offline identity checks, including HTTP.sys child → parent PID. | Does not prove repeated desktop launches. |
| `tools/test_persistent_settings.ps1` | 2 | Confirms `%APPDATA%\iMouse2` across copied build folders. | Not re-run during this audit. |

---

## Gate 1 — True independence — Partial

**Demonstrated.** Our console, kernel, and UxPlay have no vendor-path string links. Direct HID and independent UxPlay are the live input/video path. Cold-boot tooling is ready and was not executed.

- [independence-audit/report.json](../independence-audit/report.json) at 23 Sep 2026 00:28: `zero_vendor_string_links: true`, `vendor_process_count: 4`, `cold_boot_not_executed: true`.
- Vendor processes still running then: `IMService.exe` (PIDs 2676 and 13164), `mDNSResponder.exe` (12932, under `C:\iMouseXP`), `AirplayMirroring.exe` (24940).
- Port 9911 owned by `IMService.exe`. Port 17000 owned by `AirplayMirroring.exe`.
- [cold-boot-plan.json](../independence-audit/cold-boot-plan.json): `cold_boot_executed: false`, `services_altered: false`, backup SHA256 `4F25AABD…9149BB`. HidUsb (VID `720A`) is protected and must not be disabled. The vendor service name is `iMouseService`, not `IMService`.
- Scripts: `tools/verify_independence.ps1`, `tools/prepare_cold_boot.ps1`, `tools/restore_vendor_services.ps1`, `tools/post_reboot_test.ps1`.
- Older foundation: [INDEPENDENT-KERNEL.md](../../INDEPENDENT-KERNEL.md), [TWO-PHONE-TEST.md](../../TWO-PHONE-TEST.md).

**Not established.** Fresh Windows restart with vendor console, vendor input service, and vendor AirPlay disabled, then a real input and video check. A missing vendor window is not proof. A clean string scan is not a cold boot.

**To close.**

- Prerequisites: authorized reboot window; do not delete `C:\iMouseXP`; do not disable HidUsb.
- Method: `prepare_cold_boot.ps1` → reboot → do not start vendor console / IMService / AirplayMirroring → `post_reboot_test.ps1` → recast if asked → `restore_vendor_services.ps1`.
- Metrics: boot time after the backup; `iMouseService` present with Start dword 4; no process under `C:\iMouseXP`; 9911 and 17000 not listening; kernel on 9913; boards discovered; per-phone click and Home code 0; one live BMP per phone. Evidence file named in the plan: `analysis/independence-audit/cold-boot-evidence.json` (not present; the test was not launched).

## Gate 2 — One obvious app — Partial

**Demonstrated.** One shortcut name, visible product branding, persistent settings path, startup error dialog, and a launcher that refuses a competing 9913 occupant.

- Title: `src/iMouse.Console/MainWindow.xaml` — `iMouse 2.0 — Independent AirPlay`. Badge: `v2.0-rc1 · Independent AirPlay`.
- Self-test: 112/112 mock checks in `release/iMouse2-two-phone-candidate/qa/self-tests.json`.
- Settings: `ResolveDataPath()` uses `%APPDATA%\iMouse2\settings.json`. `tools/test_persistent_settings.ps1` resolves the candidate and two copied folders to that path and checks the file is not rewritten by the other folders.
- Launcher: `Open iMouse 2.0.ps1`. Occupied 9913 is checked with `Get-NetTCPConnection`. A user-mode listener must match release kernel path, two-phone args, and no `--precise-movement`. Name-only `iMouse2.Kernel.exe` matching is not used.
- HTTP.sys (PID 4): `Get-VerifiedKernelPids` reads `/api/kernel/status`, checks receiver IDs, then verifies each `receiver_pid` child's `ParentProcessId` with `Test-ReleaseKernelIdentity`.
- `tools/test_launcher.ps1` covers that correlation and rejects wrong executable, missing 9913 URL, wrong `--data-dir`, missing `--receivers` / `--receiver` / `--receiver-runtime`, missing C241, duplicate or conflicting `--input-pid`, a wrong first HTTP prefix, quoted and unquoted `--precise-movement`, HTTP.sys `receiver_pid` 0, missing pid, missing child, wrong child executable, a second parent, divergent parents, and an empty listen list. This audit did not re-run it, because 9913 is the live soak kernel.

**Not established.** Repeated-launch and double-open proof on the desktop shortcut. Failure-path proof for a missing binary. The shortcut still hardcodes `C24C,C241` and `analysis/two-phone-config`. The live fleet is five phones on `analysis/five-phone-config` (kernel PID 4376). Opening the shortcut against that kernel is specified to throw and not open a second console. That is correct for the two-phone guard, and it means the everyday entry point is not yet the five-phone app.

**To close.**

- Prerequisites: one shortcut, **iMouse 2.0 - Independent AirPlay**. No second launcher. Do not retarget the shortcut onto the soak kernel while PID 12272 is running.
- Method: launch from stopped state; reopen; concurrent double-open; missing binary; occupied competing 9913; change a preference, restart, open the same shortcut from another build folder.
- Metrics: one controller; exact console path; competing 9913 never adopted; settings survive without picking development folders; startup failures explain themselves. The supported phone set in the shortcut must match the signed-off rack before Gate 2 can close for that rack.

## Gate 3 — Unmistakable phone identity — Partial

**Demonstrated.** Persistent phone ID / board / receiver triples for the five live phones. Guided identify on C241. Physical hub slots for the live five, plus the rest of the rack as a map.

- Live five: C24C `86:1D:4A:04:2F:F6` / `iMouse2-C24C` / 7110; C241 `FE:A9:BC:D7:A0:44` / `iMouse2-C241` / 7120; C214 `8A:23:B5:71:35:8D` / `iMouse2-C214` / 7130; 724E `3A:DC:15:FB:DD:EC` / `iMouse2-724E` / 7140; F215 airplay MAC `D6:5E:EE:14:38:88` / `iMouse2-Phone5` / 7150, device id `*` in the five-phone API. [gate11-five-phone-validation/results.json](../gate11-five-phone-validation/results.json).
- Hub #0010 ([HARDWARE.md](../HARDWARE.md)): port 1 `C24C`, 2 `C241`, 3 `C214`, 4 empty, 5 `724E`, 6 `F215`, 7 `9515`. The five live phones are ports 1, 2, 3, 5, and 6.
- `tools/identify_phone.py` flashes Control Center on the named phone only, then Home. Live C241 result: [diagnostics/identify-c241/result.json](../diagnostics/identify-c241/result.json). Peak MAD 51.24 on C241, 0.04 on C24C. Lease released. That is one-phone isolation, not a 19-phone identify pass.
- Older C241 binding still stands: [C241-binding-evidence.json](../two-phone-config/C241-binding-evidence.json).

**Not established.** A friendly name stored for every physical phone and flagged when the binding changes. Reconnect, reorder, and master switch cannot silently retarget. Identify has not been run down the rack. Fourteen boards in the 19-slot schema still use placeholder device ids.

**To close.**

- Prerequisites: friendly-name store tied to phone ID + board UID + receiver name; identify action that only the selected phone answers.
- Method: identify each phone; swap USB order and master; disconnect one board; reconnect.
- Metrics: only the selected phone responds; a broken binding is flagged; zero silent redirects.

## Gate 4 — Accurate control — Partial

**Demonstrated.** Short two-phone Search/Home targeting on the then-live rollback kernel (PID 31944, DLL `A995CF5B…7851BF`, no `--precise-movement`). Not a GUI image click. Console was minimized. Mirror-to-all off.

- [gate4-targeting-baseline-20260916/results.json](../gate4-targeting-baseline-20260916/results.json): C24C Spotlight 9/9, C241 Spotlight 9/9, 22/22 scored actions within 5 s (18 Search + 4 swipe captures), reciprocal isolation 11/11 and 11/11, stuck keys/buttons 0, accidental double-clicks 0, unintended-phone actions 0.
- The file's own conclusion: this is a short baseline, not the 995/1,000 close.
- Rejected keep-Known: [click-after-home REPORT](../click-after-home-20260915/REPORT.md). Rejected 3 ms precise deploy: [precise-candidate-deploy results.json](../precise-candidate-deploy-20260915/results.json).

**Not established.** 995/1,000 varied taps per supported model/settings profile. Zero unintended-phone actions, double-clicks, or stuck buttons across that suite. Taps after Home, app switch, long movement, and interruption recovery at that volume. Every physical board/phone pair. Pointer recovery was not removed in the 7 ms default (`known=False` after Home and corner reset remain in the 7 ms probe invariants). That preservation is necessary and is not the 1,000-tap proof.

**To close.**

- Prerequisites: authorized live window after the soak; predeclared targets (phones do not share Home coordinates); frozen binaries; Home invalidation and corner reset unchanged.
- Method: actual console, not HTTP-only and not an isolated InputRouter. Write the expected visible effect first. A miss stays a miss.
- Metrics: ≥995/1000 intended-target hits per profile; **zero** wrong-phone, double-click, or stuck input; each attempt ≤5 s to the pre-written effect; per-phone report.

## Gate 5 — Complete everyday controls — Partial

**Demonstrated.** On the two-phone rollback kernel, Mirror-to-all off:

- [gate5-everyday-controls-20260916/results.json](../gate5-everyday-controls-20260916/results.json): both phones passed Control Center, App Switcher, swipe left (Home page 2), and swipe right (Home page 1). Isolation 20/20. Stuck keys/buttons 0.
- C24C typing: Spotlight text exactly `iMouse2026`, then four Backspaces left `iMouse`.
- C241 typing in that suite failed: Spotlight opened with a cursor, `iMouse2026` never appeared, API code 0. Full Keyboard Access was on. Not a character-set bug.
- Later C241 clean typing: [c241-clean-typing/results.json](../c241-clean-typing/results.json). Field exactly `hello2026`, then four Backspaces left `hello`, then Home. C24C was not addressed. Mirror stayed off.
- Character set and iOS settings: [KEYBOARD-SPEC.md](../../KEYBOARD-SPEC.md). ASCII 32–126, US QWERTY HID usages, Enter/Backspace/Tab/Escape, and the Home / ControlBar / AppSwitch chords. Documentation only. It says so.

**Not established.** On the current five-phone console, for every phone: long press, real drag/release, vertical swipe, exact text with spaces, numbers, punctuation, and Enter, and a canceled long press that does not become a double-click. Live Settings screenshots for English (US), Smart Punctuation off, and autocorrect off. Spaces must be scored in Notes, not Spotlight. Unsupported console buttons (`WIN+v`, `TAB+b`, `TAB+l`, `OPENKeyboard`, `SwitchIme`) must keep reporting failure.

**To close.**

- Prerequisites: safe Notes field; recorded keyboard settings; Mirror-to-all off unless the case is group; FKA either off or Typing Mode explicitly entered.
- Method: one predeclared visible outcome per advertised control; watch the other phones; include cancel/release.
- Metrics: every advertised control has a repeatable live pass on each supported phone; unsupported controls are explicit; no stuck buttons or keys.

## Gate 6 — Responsive operation — Partial

**Demonstrated.** Search-after-Home dispatch on the 7 ms path is under the 2.0 s ceiling on short samples. This is HTTP elapsed of the blocking click, or kernel `total=`, not a user's console click to first visible change, and not 100 observations.

- Probe, kernel PID 31944 untouched, `preciseDelayMs: 7`, 174 steps, delay 1218 ms, corner reset kept: [gate6-7ms-c24c/results.json](../pointer-reliability-20260915/gate6-7ms-c24c/results.json) Spotlight 9/9, dispatch 1857.4–1873.1 ms; [gate6-7ms-c241/results.json](../pointer-reliability-20260915/gate6-7ms-c241/results.json) Spotlight 9/9, dispatch 1858.5–1870.2 ms. Reciprocal isolation 100% both ways.
- Release-binary sample, different DLL `277A24F3…4408B5`, PID 38748, source default 7 ms: [gate6-release-validation-20260916/results.json](../gate6-release-validation-20260916/results.json). Dispatch 1820.0–1844.1 ms, isolation 100%, stuck inputs 0. C24C Spotlight **4/5** (cycle 2 stayed Home after a completed click). C241 5/5. `accepted: false`. The miss counts. Do not quote this file as a Gate 6 pass.
- Later five-phone kernel (the DLL now on disk, `BD1A6816…E634FC`) logged Search `total` about 1818–1819 ms. Visible-effect timestamps in that run were about 2.8–2.9 s because the capture waited 1.0 s after the click. That is not a 500 ms ordinary-click measurement.
- Source: `Program.cs` uses 7 unless `--legacy` or `--precise-delay` is set. Live PID 4376 has neither flag.

**Not established.** 95% of ordinary clicks visibly respond within 500 ms. 95% of reset-required clicks visibly respond within 2 s, measured from console click to first clearly correct visible response. 100 observations per category per profile. Median and 95th percentile. Misses kept. Supported rack workload. The 4/5 C24C miss on the earlier 7 ms binary is an open targeting residual, not a dropped trial.

**To close.**

- Prerequisites: Gate 4 baseline on the same binary that will be signed off. Do not drop Home invalidation or corner reset.
- Method: console action → first clearly correct visible response. Log command completion and settled animation separately. Include misses.
- Metrics: ≥100 observations per category/profile; 95% within 500 ms (ordinary) and 2 s (reset-required); report median/p95; no dropped trials.

## Gate 7 — Smooth, honest live video — Partial

**Demonstrated.** `tools/verify_video_pipeline.py` sampled the kernel BMP store for 30 s on all 5 live phones. [gate7-video-accounting/report.json](../gate7-video-accounting/report.json).

| Phone | Sequence frames | Unique hashes | Unique vs expected | Poll gap max | Gaps >2 s | Errors | Restarts |
|---|---:|---:|---:|---:|---:|---:|---:|
| C24C | 563 | 560 | 99.47% | 32.2 ms | 0 | 0 | 0 |
| C241 | 529 | 511 | 96.60% | 34.3 ms | 0 | 0 | 0 |
| C214 | 604 | 604 | 100% | 37.2 ms | 0 | 0 | 0 |
| 724E | 603 | 602 | 99.83% | 28.6 ms | 0 | 0 | 0 |
| Phone 5 | 614 | 612 | 99.67% | 32.1 ms | 0 | 0 | 0 |

Unique-vs-expected is unique BMP hashes divided by `min(sequence frames, 30 × duration)`. Incoming sequence rate was about 18–20 fps, so the 30 fps ceiling did not bind. Delivery ratio against a 30 fps display ceiling was 57–68%. That is incoming rate, not a dropped-frame claim. The kernel store keeps the latest BMP only, so this run cannot show a display backlog. The report says it samples the kernel, not the console present path.

Older two-phone received-FPS notes (~19–20) remain in [two-phone-live-test REPORT](../two-phone-live-test-20260914/REPORT.md) and [console-compare REPORT](../console-compare-20260915/REPORT.md). 30/60 fps and vendor parity are **not** promises.

**Not established.** 95% of incoming unique frames displayed by the selected console view, up to the configured display limit, on a moving-screen workload. Matched received vs displayed counts in the same window. No unexplained freeze over 2 s while valid frames arrive, judged on the console. No growing present backlog. Video delay logged separately from input timing. Both phones as master, then the same check at each larger tile layout.

**To close.**

- Prerequisites: Activity/FrameStatus visible; moving-screen workload; configured display limit recorded.
- Method: same phone and window; count a frame once; compare incoming unique vs displayed vs `min(incoming, limit × duration)`.
- Metrics: ≥95% unique-frame display up to the limit; freeze ≤2 s; backlog non-increasing; FPS, gaps, and delay separate from input.

## Gate 8 — Predictable group control — Partial

**Demonstrated.**

- Two phones, comma-list id, rollback DLL: [gate8-group-control-20260916/results.json](../gate8-group-control-20260916/results.json). `pass: true`. Both phones got Spotlight, Home, swipe left, and swipe right. Results listed only the two selected ids. Stuck inputs 0. A down+up at the resting pointer clicked before release was visible (C24C Productivity folder, C241 App Switcher). Group Home cleared both. Not a stuck button. `input_stop_in_rollback_dll` was false on DLL `A995CF5B…`.
- Four phones: [gate11-four-phone-validation/results-final.json](../gate11-four-phone-validation/results-final.json). One group Search opened Spotlight on all 4 within 2.9 s. One group Home returned all 4 to Home. `pass: true` for that milestone. C214's 1.17 s frame was still dismiss blur; the settled frame was Home.
- Five phones: [gate11-five-phone-validation/results.json](../gate11-five-phone-validation/results.json). One comma-list Search opened Spotlight on all 5 within 2.9 s, twice. Kernel logged all 5 boards in the same 1819 ms click. The specified 0.8 s group-Home capture did **not** show all 5 at Home. A later 4.6 s capture did. `pass: false`.
- Source now has `POST /input/stop` and `/input/release` (`ApiServer.cs`). That is not a measured cancel-to-release time on the live fleet. This audit did not call stop.

**Not established.** Group off means only the selected phone, proven again on the five-phone console rather than by API id lists alone. Active group and mode always visible. Stop cancels queued work and releases held input on reachable phones, with timing, and does not replay after reconnect. Unreachable-member behavior. One failed member must not block the others. The five-phone Home miss at the specified snapshot stays a miss.

**To close.**

- Prerequisites: stop/cancel through console → API → InputRouter; membership visible; soak finished so leases are not contested.
- Method: group off / on / partial membership; stop mid-gesture; reconnect after stop; one member unreachable.
- Metrics: zero extra phones; no replay; recorded release timing; unrelated phones keep working.

## Gate 9 — Graceful recovery — Partial

**Demonstrated.** C24C receiver kill on the two-phone kernel, sibling left alone, then a manual-path recast and a targeted Search.

- [gate9-recovery-20260916/results.json](../gate9-recovery-20260916/results.json): C24C `live: false` at 116.7 ms, screenshot code 25 `Receiver restarting` (not a stale BMP). New uxplay PID 49160 at about 2.1 s. Restart count became 1. C241 stayed live, restart count 0, frames advanced. Relaunch screenshot named `iMouse2-C24C` and did not return a BMP. Kernel PID 31944 unchanged.
- Post-recast targeting: [post-recast-results.json](../gate9-recovery-20260916/post-recast-results.json). C24C Spotlight opened. C241 stayed Home. Reciprocal isolation 100%.
- `tools/force_recast.py --phone C241`: [force-recast-mapping/test-results.json](../force-recast-mapping/test-results.json). `passed: true`. Checked-row tap stopped the cast; the second select restored live frames (14-frame delta). C24C MAD stayed ≤0.028. Kernel PID 38748 was not restarted.
- Older notes: [UXPLAY-AUTORESTART-TEST.md](../UXPLAY-AUTORESTART-TEST.md), [UXPLAY-RECONNECT-TEST.md](../UXPLAY-RECONNECT-TEST.md). Bounded restart policy in source is 5 tries, 2 s (`AirplaySupervisor.DefaultMaxRestarts` / `DefaultDelay`).

**Not established.** Crash isolation on the five-phone fleet. Phone disconnect/reconnect. Exhausted retries ending in a clear stopped state instead of a loop. No queued click released onto the wrong screen after reconnect. Automatic iOS recasting is **not** a promise. `force_recast.py` is an operator tool over USB-HID, not a silent recovery.

**To close.**

- Prerequisites: authorized fault window after the soak; one phone at a time.
- Method: kill one UxPlay; disconnect/reconnect the phone; exhaust retries; then a targeted tap.
- Metrics: other phones stay live; stale frames never shown as live; recast names the correct receiver; post-recovery tap hits the pre-written target; retry cap produces a clear stopped state.

## Gate 10 — All-day stability — Partial

**8-hour run: PASSED and demonstrated.** Combined recorded sampling is 8.05 hours (28,965 s across two blocks: 2.75 h + 5.30 h). The 24-hour run remains the subsequent final gate before full production release. This does not sign off Gate 10.

Final artifacts, read after stop: [status.json](../gate10-endurance-20260916/status.json) (`running: false`, `remaining_s: 0`, `stop_reason: duration`, `at` 2026-09-24T04:04:24Z) and analyzer pass 2026-09-24T04:34:31Z ([DASHBOARD.md](../gate10-endurance-20260916/DASHBOARD.md), `dashboard.html`). The harness was not restarted for this update.

| Block | Kernel | Samples | Duration | Restarts | Freezes >2 s | Frames gained |
|---|---|---|---|---|---|---|
| Prior | 34032 | 656 | 9,885 s (2.75 h) | 0 | Phone 5 stalled 6,961 s (461 samples) at frame 97,090 | 755,820 |
| Resumed | 4376 | 1,272 | 19,080 s (5.30 h) | 0 | 0 | 1,731,776 |
| Combined | two kernels | 1,928 | 28,965 s (8.05 h) | 0 | not 0 | 2,487,596 |

Samples were collected every 15 s. 1,272 + 656 = 1,928. Zero receiver restarts across all 5 streams in both blocks. Resumed-block analyzer gates: 0 freezes >2 s, 0 stuck keys, processes alive. Combined frames gained are 2,487,596, over 1.69 million. Resumed end counters: 299,070 + 297,825 + 388,367 + 382,938 + 395,185 = 1,763,385. These are two kernels, not one process. Prior ended 2026-09-23T04:13:16Z. Resumed ran 2026-09-23T22:46:24Z to 2026-09-24T04:04:24Z.

Do not call memory leak-free. Resumed-block slope is working set **+89.9 MB/h** and private **+92.8 MB/h**, RISING, and not a warmup artifact (last 30 m still +54.9 / +56.9 MB/h). Kernel and console were flat. Each uxplay was about +18 MB/h. Do not call the resumed 409s a completed interaction workload: search-click success 0/64, all acquire 409. Prior-block interactions were 29/33 ok. That does not repair the resumed block.

**Not established.** The 24-hour run. Memory settled after warm-up. Interactive stability on the resumed block (no lease acquired). A clean combined freeze record: prior-block Phone 5 stayed marked live while frames sat at 97,090 for 1.93 h.

**To close.**

- Prerequisites: 24-hour window on the final rack. Investigate the uxplay slope, the prior Phone 5 stall, and the 409 lease conflict before signing anything.
- Method: 24-hour run. The 8-hour duration is already demonstrated.
- Metrics: no unplanned console/kernel crash; no accumulating pointer errors; memory settles; frame progress, restarts, input results, CPU, and memory sampled throughout.

## Gate 11 — Full-rack operation — Partial

**Demonstrated.** Scale stopped at five live phones. The 19-slot map exists and validates offline.

- Two-phone starting point: [TWO-PHONE-TEST.md](../../TWO-PHONE-TEST.md).
- Four phones (C24C, C241, C214, 724E), 7 ms, `pass: true`: [gate11-four-phone-validation/results-final.json](../gate11-four-phone-validation/results-final.json). Four-way isolation 12/12 non-target Home. Group Search and group Home within 5 s. Zero restarts. Cutover did restart a kernel (PID 29564 → 5620). That was a previous session, not the current soak.
- Five phones, kernel PID 34032, same 7 ms family: [gate11-five-phone-validation/results.json](../gate11-five-phone-validation/results.json). All five mirroring, zero restarts. Single-target isolation held (20/20 first-run non-targets Home). Phone 5's first isolated Search did not open Spotlight; the retry did, with the other four still Home. Group Search passed. Group Home at 0.8 s failed. `pass: false`. Do not drop that miss.
- Hub map: [HARDWARE.md](../HARDWARE.md). Hub #0010 ports 1, 2, 3, 5, 6 are the live five. Port 4 empty. Port 7 is `9515`, not in the live five.
- Schema: `analysis/full-rack-config/` (`receivers.json`, `devices.json`, `pointer-calibration.json`). Ports 7110–7290 step 10, three-port windows, non-overlapping. `python tools/validate_rack_config.py` on 23 Sep 2026: **all checks passed** (19 receivers, 19 devices, 19 calibrations, slot labels, unique ids/names/pipes/MACs). Fourteen device ids are still placeholders (`unbound-…`). F215's known airplay MAC is in the schema; the live API id remains `*`.

**Not established.** 8 phones, then all 19, with identity, isolation, accuracy, responsiveness, video, and resource checks at each stage. One disconnected phone must not disrupt the others, measured rather than assumed. PC, network, iOS versions, board types, pointer/keyboard settings, resolution, active-view, and tile settings recorded as the signed-off profile. A smaller rack must not be redefined as completion.

**To close.**

- Prerequisites: Gates 4/5/6/7/8/9 holding on the current live set; soak finished; documented profile.
- Method: 5 → 8 → 19. Repeat the stage checks. Bind real phone ids before treating a slot as operated.
- Metrics: all 19 meet the agreed profile together. If hardware or network capacity blocks a stage, record the limit and the required change.

## Gate 12 — Useful diagnostics and a repeatable release — Partial

**Demonstrated.**

- `tools/export_diagnostics.py` writes one JSON bundle and does not acquire leases or restart processes. Sample: [diagnostics/diagnostics-20260922-235250.json](../diagnostics/diagnostics-20260922-235250.json) at 2026-09-23T03:52:49Z. It includes kernel command line, pacing 7 ms, console PID and title, receiver rows, board list, binary hashes, system memory/Windows version, settings, and a Gate 10 slice. That sample's kernel was PID 34032, not the current PID 4376. It recorded `iMouse2-Phone5 frames stalled at 97090`. Do not treat the file as clean.
- Status overlay and recast hint remain from the earlier console. Per-receiver logs still exist under the config dirs.
- Setup pointer: [OPEN-THIS-APP.md](../../OPEN-THIS-APP.md). It is not a user recovery manual.
- Build identity in the UI badge is `v2.0-rc1 · Independent AirPlay`. Live DLL hashes are in the identity table above. [app-identification/build-hashes.json](../app-identification/build-hashes.json) is the older pair and must not be copied forward as the current release identity.

**Not established.** One export that a later tester can use to reproduce the signed-off session, taken on the signed-off binaries. Concise identification, recasting, recovery, update, and rollback instructions a user can follow without development tools. The sign-off rule: a later functional change reruns the affected checks before inheriting sign-off.

**To close.**

- Prerequisites: export schema frozen against the release binaries; command lines and config files hashed beside them.
- Method: trigger each failure class; export once; follow setup, recovery, update, and rollback as a user.
- Metrics: the export is sufficient to reproduce the session; instructions work without a developer; any functional change reruns affected gates.

---

## Simplifier backlog — deferred milestones, not deletions

Ponytail ultra review of P0–P5 does **not** remove FINISH-CRITERIA requirements. Cuts are sequencing. Evidence landing inside a package does not close the package.

| Package | Astra scope | Disposition after this audit | When it becomes the job |
|---|---|---|---|
| **P0** | Everyday-control acceptance on the signed-off pacing (taps, drags, swipes, typing, Control Center, Home) | Short Gate 4 baseline and a partial Gate 5 suite now exist. Do **not** delete Gate 4 or Gate 5. 995/1,000 and the full character set are still open. | After the soak, on the frozen 7 ms binary. Fill the missing controls. Do not start a 1,000-tap run against a moving kernel. |
| **P1** | Stop/cancel, receiver crash isolation, disconnect/reconnect, exhausted retries | C24C crash isolation and `force_recast.py` exist. `/input/stop` exists in source. Five-phone group Home missed its snapshot. Do **not** delete Gates 8 or 9. | After P0 holds on the same binary. Reuse AirplaySupervisor and the existing stop API. No new orchestration layer. |
| **P2** | Pacing sweep, then Gate 6 measurement | 7 ms is the source default. The 3 ms candidate stays rejected. A 15/10/8/6 matrix is still a science project. Do **not** delete Gate 6 or drop Home invalidation/reset. | After P0/P1. Measure 100 observations per category. Do not tune pacing to buy the 2 s number. |
| **P3** | Finish Gate 2 on the existing shortcut | Branding, AppData settings, and HTTP.sys parent checks landed. The shortcut is still two-phone. Do **not** delete Gate 2. Do not add a second launcher or installer. | After the live rack size is the one the shortcut should start. Must not replace the soak kernel. |
| **P4** | Diagnostics, vendor-disabled independence, scale 2→4→8→19 | Tooling and a 19-slot schema exist. Live scale is 5. Cold boot was not run. Do **not** shrink the 19-phone goal. | After accepted controls, recovery, pacing, and entry point. |
| **P5** | 8 h then 24 h, sign-off table, user workflow | 8 h duration is demonstrated (Gate 10). It is not P5. 24 h remains. Do **not** delete Gate 10 or the sign-off table. | After all 19 phones meet the agreed profile, and after the uxplay slope, prior Phone 5 stall, and lease 409s are understood. |

### Soak has ended

Harness PID 12272 stopped on duration at 2026-09-24T04:04:24Z (`remaining_s: 0`). Do not restart it to pad Gate 10. Still open: cold boot (needs a user reboot), the 995/1,000 tap suite, Gate 6's 100 observations, 8 then 19 phones, exhausted retries, the 24-hour run, and user-facing recovery docs.

Order remains targeting → recovery → speed → scale → endurance. This audit does not authorize the next live window.

---

## Sign-off table (unchanged: not signed off)

| Sign-off item | Status |
|---|---|
| Exact release build and settings recorded | Not signed off. Live hashes are recorded above and are not a sign-off. |
| Gates 1–12 passed with linked evidence | Not signed off |
| Full 19-phone configuration validated | Not signed off. Schema check passed. Live fleet is 5. |
| Final 8-hour and 24-hour runs passed | 8-hour duration demonstrated (8.05 h, two blocks). 24-hour run not run. Not signed off. |
| Setup/recovery instructions and rollback checked | Not signed off |
| User confirms the final everyday workflow | Not signed off |
