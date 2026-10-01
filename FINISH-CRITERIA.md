# iMouse 2.0 — Independent AirPlay: definition of finished

Updated: 1 October 2026.

## Our goal

Build a dependable Windows app that controls the entire 19-phone iPhone rack
through the existing hardware and our own AirPlay system. The user opens one
shortcut, recognizes every phone, and can trust that each action goes exactly
where intended.

The product is **iMouse 2.0 — Independent AirPlay**. Development folders and
internal builds do not create separate products for the user. The everyday
entry point stays the same as the software improves; see [Open this app](OPEN-THIS-APP.md).

**Finished means all release gates below pass on the actual release build and
supported rack configuration, with recorded evidence.** An implemented feature,
a successful mock test, or a short live demonstration alone does not close a gate.

This document defines the completion criteria. It does not claim the current
build meets them, and creating it does not authorize new live hardware tests.

## Completion checklist

### 1. True independence

- [x] After a fresh Windows restart, the app starts, discovers the configured
  boards, receives video, and controls the supported phones with vendor console,
  vendor input service, and vendor AirPlay processes disabled for the test.
- [x] Our app has no runtime dependency on those vendor processes. Existing
  physical boards, normal Windows drivers, and documented third-party receiver
  components remain part of the supported setup.
- [x] Record process identities and the result of a real input/video check;
  a missing vendor window alone is not proof of independence.

Passed 24 September 2026. Evidence: [cold-boot-evidence.json](analysis/independence-audit/cold-boot-evidence.json).

### 2. One obvious app

- [x] One desktop shortcut starts the required components and opens the correct
  console. Opening it again does not create competing controllers.
- [x] The app is visibly recognizable as our independent version, and its build
  identity is available in diagnostics.
- [x] Settings and phone names survive app restarts and updates. Updating or
  rolling back does not require the user to choose development folders.
- [x] A startup problem produces a useful explanation instead of silently failing.

Passed 24 September 2026. Evidence: [gate2-evidence.json](analysis/gate2-single-app/gate2-evidence.json).

### 3. Unmistakable phone identity

- [ ] Each physical phone has a persistent friendly name tied to its phone ID,
  board identity, and receiver name.
- [ ] A guided identification action lets the user match a physical phone to its
  app entry without tracing cables; only the selected phone responds.
- [ ] A changed or missing binding is clearly flagged. Reconnecting, reordering
  the list, or switching the master view cannot silently redirect input.

### 4. Accurate control

- [ ] At least **995 of 1,000 single-tap attempts** land on the intended target
  in a documented suite covering varied positions, distances, and screen
  transitions for every supported phone model/settings profile.
- [x] There are **zero unintended-phone actions, accidental double-clicks, or
  stuck mouse buttons/keys** in the entire acceptance run. Any such event blocks
  release, even if the overall tap percentage passes.
- [x] Define the expected visible effect for each tap before the run. A single
  attempt must produce that effect within five seconds; a timeout or incorrect
  target is a failure. Retries cannot turn the original failure into a pass.
  Report results per phone as well as for each supported profile.
- [ ] Include taps after Home, app switching, long movements, and recovery from
  interruption. Repeating only one easy target is insufficient.
- [ ] Every physical board/phone pair passes an identity and targeting check.
  Success on one phone is not evidence that another board is correctly bound.
- [ ] Pointer recovery remains dependable; speed changes cannot remove required
  resynchronization merely to improve timing results.

**Passed within its scope on 25 September 2026; the release criterion above is not
yet met.** Boxes are checked only where this run demonstrates the bullet as written.

*Scope.* Two phones, C24C and C241 (iPhone XR, one settings profile), driven through
the kernel API at `http://127.0.0.1:9913/api` with one device id per command and
mirror-to-all off. Every tap aimed at a single target, the Search control at
(250, 900) on the Home screen, reached from four setups of 250 trials each: straight
after Home; after a pointer move from one of four start points; after the App
Switcher; and after horizontal swipes.

*Result.* 1,000 / 1,000 target hits (C24C 500 / 500, C241 500 / 500), all within
5 s (p50 2,216.6 ms, p95 2,419.2 ms), no retries, 0 stuck inputs, 0 accidental
double-clicks, 0 wrong-target hits. The run flagged 18 trials as not isolated; the
suite's isolation audit attributes all 18 to a baseline-capture race in the harness
(the non-target phone photographed while still dismissing the previous trial), not
to cross-phone input, which gives 0 unintended phone actions. The run and its audit
were produced by the same agent and have not been independently reviewed
(`ACCOUNT-HANDOFF.md` section 2, on branch `claude/input-timeout-integration`).

*What the written criterion still requires:*

1. **Varied tap positions and distances.** All 1,000 taps aimed at one point
   (measured: every row of `results.jsonl` has target (250, 900)). The first bullet asks
   for varied positions and distances, and the fourth states that repeating one easy
   target is insufficient.

   The four setups may not have varied the pointer's path either. Measured: in every
   row, Home is the last setup step timed in `setup_ms`. That includes the 250
   `off_location` rows, whose recorded start points were reached by a move before
   Home. Inferred, not measured: the kernel's Home handler marks the pointer position
   unknown (`InputRouter.cs`, `state.Known = false`), so each scored click would have
   begun with a corner reset and travelled corner → (250, 900). The inference rests on
   kernel source (the release kernel's `InputRouter.cs` matches the repository) and on
   kernel logs of the same sequence on another day (15 Sep: `click … known=False …
   steps=174` after Home). It cannot be checked for this run: the run's kernel log was
   not kept, the run's harness version is not preserved (see *Provenance*), and the
   results do not record resets.
2. **Taps after recovery from interruption.** Not among the four setups.
3. **Every physical board/phone pair.** Two of the rack's 19 pairs were checked; each
   of the others needs its own identity and targeting check, and every phone model
   and settings profile in the rack must be covered.
4. **Pointer recovery, demonstrated in the record.** The run records no pointer resets
   or resynchronisation. If the inference in item 1 holds, every scored click followed a
   corner reset, and the 1,000 hits would bear on the sixth bullet. Because that rests on
   inference rather than on this run's record, it stays unchecked. A run that logs its
   resets, or exercises recovery explicitly, would close it.

The written gate does not require taps to be issued through the console; that
requirement belongs to Gates 5 and 6, and an API-driven suite is a valid method here.

*Provenance.* The harness that produced these results is not in the repository in that
form. The only copy of `tools/gate4_1000_tap_suite.py` was written at 01:50:35 on 25 Sep,
after the run finished (01:08) and after its isolation audit (01:48), and the audit quotes
code the file no longer contains. No earlier version is in git or the 28 Sep backup.

A revised harness addressing items 1-4 and the isolation race, tested offline but not yet
run on a phone, is on branch `claude/gate4-harness-v2` (`tools/gate4_v2/`).

Before a qualifying rerun, lengthen the harness's 350 ms pause after dismissing each
trial (`tools/gate4_1000_tap_suite.py`) so the non-target phone is photographed only
after it settles. Otherwise the second bullet will again rest on an after-the-fact
audit rather than on the run itself.

Evidence: [status.json](analysis/gate4-1000-tap/status.json), [results.jsonl](analysis/gate4-1000-tap/results.jsonl), [ISOLATION-AUDIT.md](analysis/gate4-1000-tap/ISOLATION-AUDIT.md).

### 5. Complete everyday controls

- [ ] Verify taps, long presses, drags, horizontal and vertical swipes, Home,
  app switching, and Control Centre through the actual console.
- [ ] Verify typing, spaces, numbers, punctuation, Enter, and Backspace with
  exact expected text. Document the supported character set and keyboard settings.
- [ ] Gesture duration and button release behave correctly, including after a
  canceled or failed action. A long press must not become a double-click.
- [ ] Each control advertised as supported has a repeatable live acceptance case.
  Unsupported actions are clearly identified rather than reporting false success.

### 6. Responsive operation

- [ ] At least **95% of ordinary clicks visibly respond within 500 ms** when a
  full pointer reset is unnecessary.
- [ ] At least **95% of reset-required clicks visibly respond within 2 seconds**,
  including a Search click after Home.
- [ ] Measure from the user's console click to the first clearly correct visible
  response. Record command completion and settled-animation timing separately.
- [ ] Use at least 100 observations in each timing category per supported profile,
  report median/95th percentile, and include misses as failures. Do not drop slow
  or failed trials from the results.
- [ ] Repeat under the supported rack workload, not only with one idle phone.

### 7. Smooth, honest live video

- [ ] During a repeatable moving-screen workload, the selected view displays at
  least **95% of incoming unique frames, up to its configured display limit**.
- [ ] Compare received and displayed counts for the same phone and time window.
  Count a frame once; repeatedly drawing an old image does not increase useful FPS.
  The expected count is the smaller of incoming unique frames and the configured
  display limit multiplied by the window duration. Use frame sequence IDs where
  available, since identical-looking frames can still be new frames.
- [ ] No unexplained visible freeze exceeds **two seconds while valid frames are
  arriving**, and the display does not accumulate an increasing backlog.
- [ ] Record displayed FPS, frame gaps, and measured video delay separately from
  input-command timing. A slow pointer movement is not automatically video lag.
- [ ] Check both phones as master at the two-phone stage; check switching between
  phones and the agreed tile layout again at each larger rack stage.

### 8. Predictable group control

- [ ] With group control off, only the selected phone receives actions.
- [ ] With group control on, exactly the explicitly selected members receive
  them. The active group and mode are always visible.
- [ ] A stop control immediately cancels queued work and initiates release of held
  inputs on reachable phones. It must not replay old input after reconnection.
- [ ] Record cancellation-to-release timing and behavior for unreachable phones.
  Stopping cannot undo an action a phone has already completed.
- [ ] One unavailable group member does not block unrelated phones indefinitely.

### 9. Graceful recovery

- [ ] A crashed receiver restarts automatically within the configured bounded
  retry policy, without restarting the console or interrupting other phones.
- [ ] Lost video becomes visibly unavailable; the app never presents an old frame
  as a live feed. Receiver state and reported process identity remain accurate.
- [ ] If iOS needs manual recasting, the app names the correct receiver and explains
  the action. Recovery completes in the same console after the user recasts.
- [ ] Test receiver crash, phone disconnect/reconnect, and exhausted retries.
  Exhausted retries produce a clear state rather than an endless restart loop.
- [ ] Reconnecting never releases previously queued clicks onto the wrong screen.

### 10. All-day stability

- [ ] Pass an **8-hour run, then a 24-hour run** on the final supported configuration.
- [ ] No unplanned console/kernel crashes, accumulating pointer errors, or unresolved
  input failures occur. Planned fault-injection intervals are recorded separately.
- [ ] Sample frame progress, receiver restarts, input results, CPU, and memory.
  Record the warm-up period, sampling interval, and resource budgets before testing.
- [ ] Memory settles after warm-up instead of continually growing. Preserve
  ten-minute medians and peaks; investigate any sustained upward trend before sign-off.
- [ ] Include idle periods, periodic interactions, master switching, and supported
  group actions. A long idle-only run does not establish interactive stability.

### 11. Full-rack operation

- [ ] Progress through **2 → 4 → 8 → all 19 phones**, checking identity, isolation,
  input accuracy, responsiveness, video behavior, and resource use at each stage.
- [ ] Document the tested PC, network, iOS versions, board types, pointer/keyboard
  settings, resolution, active-view settings, and tile settings.
- [ ] All 19 phones meet the agreed operating profile together. One disconnected
  or failed phone does not disrupt the others.
- [ ] If hardware or network capacity prevents a gate from passing, record the
  limit and required change. Do not silently redefine a smaller rack as completion.

### 12. Useful diagnostics and a repeatable release

- [ ] The status view distinguishes board connection, input readiness, and live
  mirroring, and provides understandable guidance for each failure.
- [ ] One diagnostic export includes build identity, device/board mapping, relevant
  settings, timestamps, performance measurements, errors, and receiver restarts.
- [ ] The release has concise setup, identification, recasting, recovery, update,
  and rollback instructions. A user can follow them without development tools.
- [ ] Record the exact tested binaries and settings. A later functional change
  requires the affected checks to be repeated before that build inherits sign-off.

## What the existing evidence establishes

These are demonstrated foundations, not completed full-rack release gates.

| Evidence | What it establishes | What it does not establish |
|---|---|---|
| Two-phone live checks and user confirmation | C24C/C241 mirroring, targeting, and selected-phone/group isolation worked in the tested setup. | All 19 phones, all-day operation, or independence after a vendor-disabled cold boot. |
| Receiver crash/recast test | The helper restarted and the same console recovered after manual iPhone recasting. | Automatic iOS recasting or every retry-limit/failure scenario. |
| Matched console measurements | Roughly 19–20 received FPS in the measured two-phone conditions. | Sustained 30/60 displayed FPS or vendor speed parity. |
| Pointer timing and live movement checks | Isolated InputRouter path completed Search-after-Home in about 1.17 seconds versus 3.02 seconds, with 14/14 successes per phone. The 16 September `--precise-movement` console deployment (PID 12516) passed C24C 9/9 but regressed on C241 (0/5 targeted rerun) and was rolled back to legacy pacing (`release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe`, PID 31472). See [HANDOFF](analysis/pointer-reliability-20260915/HANDOFF.md). | End-to-end console latency, 1,000-trial accuracy, or final deployment acceptance of the precise-movement candidate. |

The movement timing result came from an isolated runner using the actual input
components. It is not a measurement from a user's click in the delivered console.

Source reports:

- [Two-phone status and evidence](TWO-PHONE-TEST.md)
- [Receiver restart and recovery](analysis/UXPLAY-AUTORESTART-TEST.md)
- [Matched console comparison](analysis/console-compare-20260915/REPORT.md)
- [Follow-up master-view measurements](analysis/c241-master-20260915/REPORT.md)
- [Pointer reliability and movement timing](analysis/pointer-reliability-20260915/REPORT.md)

**Sustained 30/60 FPS, vendor speed parity, and automatic iPhone recasting are
not established promises.** Record and investigate these separately. They must
not replace the accuracy, recovery, and usable-performance gates above.

## How we sign off

Work in this order: **correct targeting → reliable recovery → consistent speed
→ full-rack scale → final endurance run**.

For every gate, record the build, configuration, date, test method, raw evidence,
observed result, and remaining issues. Mark it passed only when its requirements
are demonstrated; a blocked or untested requirement remains open.

| Sign-off item | Status |
|---|---|
| Exact release build and settings recorded | Not signed off |
| Gates 1–12 passed with linked evidence | Not signed off |
| Full 19-phone configuration validated | Not signed off |
| Final 8-hour and 24-hour runs passed | Not signed off |
| Setup/recovery instructions and rollback checked | Not signed off |
| User confirms the final everyday workflow | Not signed off |

The application is finished for this scope when this table is complete. Future
features can then be planned without confusing them with unfinished core behavior.
