# iNodeControl / iMouse 2.0: Durable Project Progress Record

- **Updated:** 2 October 2026
- **Coordinator:** Omp / Orca Autonomous Coordinator
- **Repository:** `https://github.com/josephacastiglia/iNodeControl`
- **Local Root:** `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0`
- **Active Worktrees:**
  - Main Checkout: `claude/track-gate-evidence` (`900f5b4`)
  - Integration: `.claude/worktrees/keyboard-spec-reconcile` (`claude/input-timeout-integration`, `472bb04`)
  - Gate 4 v2: `.claude/worktrees/gate4-harness-v2` (`claude/gate4-harness-v2`, `2c98f44`)

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

## 2. Verified Builds & Hashes
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
2. **Gate 6 Console-to-Visible Latency Harness (PARTIAL / OFFLINE PREPARED):** Extended `analysis/gate6-release-validation-20260916/run_gate6.py` with threaded MAD poller (`first_visible_ms`, `settled_ms`), UIA action timing (`invoked_ms`), run directory isolation (`runs/<run_id>/`), C24C-only boundary enforcement, and miss-penalized percentiles. Approved by Opus review (`findings: []`). Scope limits: search category remains API-only; UIA button path is mock-tested offline and has not run live; search and home are visual-correctness-checked, while appswitch and controlcenter measure visible transition latency (MAD >= 18) without structural correctness verification.
3. **Gate 11 Full-Rack Configuration Validation (PASSED OFFLINE):** Verified `analysis/full-rack-config/` against physical 19-slot topology across hubs #0009, #0010, and #0011 using `tools/validate_rack_config.py` (all 19 unique slots, non-overlapping port windows, unique pipes, valid MACs, and calibration coverage verified).
4. **Gate 12 Diagnostic Tooling Audit (PASSED OFFLINE):** Audited `tools/export_diagnostics.py`. Verified read-only data collection (OS, RAM, binary hashes, listening ports, receiver stats, calibration) and confirmed strict credential isolation (never touches stored vendor credentials or `build/` files).
5. **Gate 4 Harness v2 (OFFLINE PREPARED):** `tools/gate4_v2/` copied into main checkout (untracked); `gate4_suite.py --self-check` passed (`sha256 a5382b...`); `test_gate4_v2.py` (14 mock-kernel tests) passed. Staged alongside historical `tools/gate4_1000_tap_suite.py`.
6. **Gate 5 FKA-On Typing Comparison (STAGED FOR LIVE):** Runner `fka_console_ab_runner.py` and `console_uia.ps1` prepared with 12 mock self-checks passed and Opus sign-off. Real UIA selection, Disconnect/Connect release, and live lease behavior remain mock-only until live execution. Live window requires preflight, FKA verification, desktop control approval, and physical Home gestures.
