# Grok handoff: deploy and verify precise movement candidate

Read `analysis/pointer-reliability-20260915/REPORT.md` first. Codex completed the input-state review and a speed fix that **retains reset after Home**. All 41 self-tests and 14 live Home→Search checks per phone passed. Completion is ~1.17 s instead of ~3.02 s. The live test runner used the actual candidate InputRouter/HidConnection but the old kernel remained the video server. At that time, actual console-level candidate deployment was still outstanding.

Work only on C24C (86:1D:4A:04:2F:F6) and C241 (FE:A9:BC:D7:A0:44). Mirror-to-all off. Leave all other phones and vendor services untouched.

1. Verify current executable paths and command lines; recorded PIDs are not durable. The last kernel was 28896, UxPlay 37656/29980. Confirm both board bindings/UIDs and save current receiver status.
2. Close only the independent kernel and its verified two UxPlay children to free 9913 and the receiver ports. Preserve the rollback files. Keep the candidate console, or reopen that exact console if needed.
3. Run `Start Precise Movement Candidate.ps1`. It launches `release/iMouse2-kernel-precise-candidate/iMouse2.Kernel.exe` with the required **--precise-movement** flag and existing two-phone config. Confirm startup log says high-resolution 3 ms. Do not launch the failed keep-Known click-candidate.
4. Have the user recast iMouse2-C24C and iMouse2-C241. Verify both live before input. Kernel replacement drops the old sessions; don't claim automatic recast.
5. On the actual console, verify Home→single Search click at least five times per phone, after moving to different places, plus safe horizontal swipes and pointer tracking. Confirm Spotlight visually and the other phone unchanged. Expect first post-Home clicks around 1.2 s at the kernel; don't confuse console hover timing with kernel-only dispatch timing.
6. Run a short two-phone stability check, record live frames, restarts, CPU/memory and failures. Preserve existing calibration, reset, settle, hold and drag timing. Do not add unrelated speed changes.
7. If a reproducible targeting regression appears, restore the old two-phone kernel without --precise-movement, recast and document the failure. Otherwise record the candidate as validated for controlled use, with exact paths and remaining limits.

Source changes: `src/iMouse.Kernel/MovementDelay.cs`, opt-in pacing in `InputRouter.cs`, command flag in `Program.cs`, regression checks in `SelfTests.cs`. Root cause of earlier keep-Known failures is not fully proven: Home's focus highlight did not necessarily represent the actual mouse position. Never remove Home invalidation on this evidence.

## Fresh deployment — 16 September 2026

Historical notes above (Codex review, self-tests, last recorded PIDs 28896 / 37656 / 29980) remain the prior record. This section is the live cutover, not a re-run of those results.

### Actions

1. Legacy kernel PID 7004 and UxPlay PIDs 16396 / 41308 terminated cleanly.
2. Candidate launched via `Start Precise Movement Candidate.ps1`: `release/iMouse2-kernel-precise-candidate/iMouse2.Kernel.exe` PID **12516** with `--precise-movement`.
3. `analysis/pointer-reliability-20260915/candidate-kernel.stdout.log` contains: `Pointer movement pacing: high-resolution 3 ms; reset/drag/settle unchanged`.
4. Fresh UxPlay receivers: PID **37964** (`iMouse2-C24C`, port 7110), PID **25016** (`iMouse2-C241`, port 7120). `http://127.0.0.1:9913/api/kernel/status` returned HTTP 200 post-cutover (`receiver_pid` 37964; both receivers offline / frames 0).
5. Pre-input safety gate active: **0 clicks / movements sent** while receivers are offline.
6. Rollback kernel preserved: `release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe`.

### Live candidate validation

Evidence preserved (untouched) under `analysis/precise-candidate-deploy-20260915/` (BMPs + `results.json` + `c241-targeted-rerun/` + `verification.json`).

- Timing: HTTP click RTT ~945–982 ms (kernel-internal dispatch was not measured in this deployment; separate isolated InputRouter benchmark references were ~3.02 s legacy and ~1.17 s precise).
- C24C: **9/9** Spotlight successes (5/5 cycle, 4/4 location); left swipe passed.
- C241: **regressed / failed acceptance** — 3/5 cycle, 2/4 location, **0/5** targeted rerun. Stayed on Home. AssistiveTouch and FaceTime focus ring observed.
- Isolation: **100%** held in both directions (18/18 other-phone captures stayed Home).
- Frame rates: both streams remained live with **0 restarts**.

Candidate not accepted. Step 5 rollback required.

### Rollback — Step 5

Restored known-good kernel **without** `--precise-movement`:

- Stopped candidate kernel PID **12516** and UxPlay children **37964** / **25016**.
- Ports 9913 / 7110 / 7120 were free, then relaunched `release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe`.
- Rollback kernel PID **31472**. Command line has no `--precise-movement`. Legacy pacing (stdout has no high-resolution 3 ms line).
- `http://127.0.0.1:9913/api/kernel/status` → HTTP 200. Fresh UxPlay: PID **35988** (`iMouse2-C24C`), PID **24824** (`iMouse2-C241`); both offline / frames 0 until recast.
- Logs: `analysis/pointer-reliability-20260915/rollback-kernel.stdout.log`, `rollback-kernel.stderr.log`.

### Operational acceptance resolved; mechanism unresolved

**Closed by legacy control trial** on rollback kernel PID **31472** (no `--precise-movement`). Evidence: `analysis/pointer-reliability-20260915/legacy-control/`.

- Streams live: C24C and C241 frames advancing, **0 restarts**.
- C241 Spotlight: **5/5** (100%).
- C24C Spotlight: **2/2** (100%).
- Isolation: 100% (C24C stayed on Home 5/5 during C241; C241 stayed on Home 2/2 during C24C).

Root cause: C241’s targeted Home→Search result changed from 0/5 under the deployed --precise-movement candidate to 5/5 after rollback. This provides strong empirical evidence associating the targeting regression with the candidate deployment and fully justifies the rollback. However, it does not prove that 3 ms pacing was the sole physical mechanism because recast, Control Center interaction, and device focus state were reset during cutover. Run3 confirms C241 is functional in the restored legacy state without ruling out intermittent or state-dependent device/focus effects.

Rollback kernel `release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe` (PID **31472**) is live; both phones verified functional.

