# Pointer reliability and movement pacing — 15 September 2026

Implemented an opt-in high-resolution movement timer while retaining post-Home invalidation, corner reset, the captured one-unit mouse packets, existing calibration, and click settling. The actual candidate InputRouter passed 14 live Home→Search checks per phone, plus continuous movement checks. Completion fell from approximately 3.02 seconds to 1.17 seconds. The running kernel has not been replaced; console-level deployment validation is next.

## 1. What the remembered position means

`Known` represents the cumulative relative reports successfully written by the PC. The current transport reads no iOS pointer-position acknowledgement. It is an estimate, not measured phone state. Home, AppSwitch and ControlBar invalidate it; a transport exception releases buttons/keys, invalidates it and disposes the handle. Initial connections start unknown. Calibration assumes unchanged portrait dimensions, pointer settings, and exclusive input ownership.

Other keyboard commands, app-driven pointer/focus changes, changed phone bindings, physical input or another controller are not generally observable by this estimate. Keeping it across arbitrary UI transitions is not proven safe. The failed keep-Known candidate remains rejected.

The earlier statement that the pointer physically moved onto FaceTime is not established by a highlighted icon. In the live C241 probe:

1. Corner reset put the visible pointer near (15,14).
2. The legacy walk put it near Search (250,900).
3. Home highlighted FaceTime.
4. One right unit followed by twelve up/right units exposed the cursor near (314,839), consistent with its previous Search position, not FaceTime.

Evidence: `01-*` through `05-*`. The failed prior screenshot has a blue focus outline around FaceTime. Keyboard focus and mouse-pointer coordinates must be distinguished. A separate zero-motion click trial and a nonzero wake trial both opened Spotlight this session (`06-*`, `07-*`); neither establishes the cause of all earlier intermittent failures. Input-mode/focus interaction is a hypothesis. Do not re-enable preservation across Home on this evidence.

Apple documents that Full Keyboard Access highlights the focused item and uses Tab navigation: [Control iPhone with an external keyboard](https://support.apple.com/en-euro/guide/iphone/ipha4375873f/ios). The vendor Home sequence includes Tab before GUI+H. This supports investigating focus, not assuming the highlight is a mouse coordinate.

## 2. Reliable recovery used here

Retained the known working recovery: release mouse/keyboard, four (-127,-127) corner reports with existing waits, then walk from the calibrated origin. Every Home invalidates the estimate. Every tested post-Home Search used a fresh corner reset. No calibration, Home packet, reset delay, 120 ms settle request or 80 ms button hold was shortened.

Added regression checks for reset after Home and recovery after a failed movement write. They exercise legacy and precise pacing with mock transports. Packet-equivalence tests confirm the same reset, movement, Home, click and swipe bytes. All **41 kernel checks passed** with no real HID opened by the self-tests.

## 3. Measured speed improvement

The old `Task.Delay(3)` movement loop actually waited approximately 13–15 ms per report on this host. A hardware-free timing experiment measured:

| Requested delay | Task.Delay mean | High-resolution waitable timer mean |
|---|---:|---:|
| 3 ms | 15.56 ms | 3.27 ms |
| 6 ms | 15.58 ms | 6.31 ms |
| 10 ms | 15.49 ms | 10.27 ms |
| 15 ms | 16.50 ms | 15.31 ms |

80 observations per cell; raw gaps and process CPU-time measurements are in `timing.json`. This was not a total-system CPU benchmark. Microsoft documents the coarse clock used by [Task.Delay](https://learn.microsoft.com/en-us/dotnet/api/system.threading.tasks.task.delay?view=net-8.0) and the supported [high-resolution waitable timer](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-createwaitabletimerexw). The existing timeBeginPeriod call does not fix Task.Delay's clock granularity.

Implementation: `MovementDelay.cs` uses an unnamed auto-reset high-resolution timer and asynchronous thread-pool wait, with per-move lifetime and no busy-spin. `InputRouter` opts in only for unheld, duration-zero movement. Held-button/drag movement retains legacy timing. Native errors use the existing fail-and-reset handling. Legacy pacing remains the default unless `--precise-movement` is supplied.

### Live results

The console was closed to exclude hover input. Only C24C and C241 were touched. The existing kernel PID 28896 and UxPlay PIDs 37656/29980 supplied unchanged live BMPs. The isolated runner invoked the actual candidate InputRouter and HidConnection against the physical board, then resynchronized the running kernel with `/mouse/reset`. No receiver restart or recast was needed for these tests.

| Test | C24C | C241 |
|---|---:|---:|
| Legacy Home→Search completion, median of 2 | 3008 ms | 3020 ms |
| Precise Home→Search completion, median of 14 | 1170 ms | 1169 ms |
| Precise completion range | 1149–1176 ms | 1159–1176 ms |
| Visually confirmed Spotlight | 14/14 | 14/14 |
| Of those: after movement elsewhere, then Home | 4/4 | 4/4 |

Times are InputRouter dispatch completion, not HTTP round-trip or first visible response. Screenshots were deliberately taken about 450 ms after completion (~1.60–1.65 s after send for precise). They establish visible success by capture time, not exact onset or settled-animation latency. Both single-click packets and outcomes were checked; image difference alone was not used to identify Spotlight. Other-phone image differences were <=0.030 mean channel levels, consistent with its animated clock; its Home page remained unchanged.

Movement-only comparison preserved visible endpoints: C241 (250,800) took 2401→772 ms; C24C (350,820) took 2458→792 ms. Same relative steps and calibration.

Continuous routes exercised 15 forward/backward movements without intervening Home/reset, ending with a successful Search on each phone. Repeated final endpoints appeared at the same coordinates. C241's first route captured two moving/intermediate frames with a 150 ms observation wait; repeated with a 600 ms observation wait, all three endpoint captures aligned (`c241-settled-endpoints.png`). This changes only the diagnostic observation delay. No accumulated displacement was visible in these short routes; it is not a long-duration drift guarantee.

All sampled receiver states remained live during the test suites, counters advanced, and restart counts stayed zero. Sampling does not exclude brief unsampled stalls. Video performance optimization and vendor parity were not tested.

## Candidate and remaining work

- Candidate: `release/iMouse2-kernel-precise-candidate/iMouse2.Kernel.exe`.
- Required flag: **`--precise-movement`**. Without it, behavior stays legacy.
- Launcher: `Start Precise Movement Candidate.ps1` (refuses occupied 9913; never kills processes).
- Console: `release/iMouse2-two-phone-candidate/iMouse2.exe` on 9913.
- Rollback kernel: `release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe`, without the precise flag.
- Rejected binary remains `release/iMouse2-kernel-click-candidate`; do not use it.

Candidate DLL SHA256: `EFB6A8C0EDDE97BA6377670C6ACB5DED639F5A031C40F598647DF06276873823`. The live runner and published candidate used the same kernel DLL hash.

The remaining routine step is to switch the independent kernel, recast both phones, and verify actual console clicks, pointer tracking, and swipes on the new process. Do not call this deployed or daily-use ready before that check. See `HANDOFF.md`. No application performance change has been activated in the current console session.
