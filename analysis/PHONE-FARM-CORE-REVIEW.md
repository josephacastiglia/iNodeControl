# Phone Farm iOS Core: lessons for iMouse 2.0

Reviewed: 16 September 2026.

Repository: [Git-Agni/prod-FARM-IOS-Core](https://github.com/Git-Agni/prod-FARM-IOS-Core).
Reviewed commit: [`3e936babd80723b49b3e594f9403b25363078e64`](https://github.com/Git-Agni/prod-FARM-IOS-Core/tree/3e936babd80723b49b3e594f9403b25363078e64).
The checkout was downloaded into `analysis/references/prod-FARM-IOS-Core` for
static inspection. No dependencies were installed, no upstream code/tests were
executed, no phones were controlled, and no iMouse application code was changed.

## Verdict

This is a useful engineering reference. Its strongest transferable ideas are
guided registration, explicit device identity, execution ownership, structured
health, versioned jobs, and targeted regression tests. It is not evidence that
our Windows rack can achieve 30/60 FPS or run 19 phones reliably, and it does not
decode our board protocol or fix our pointer calibration.

Keep our Windows console, HID input, and UxPlay receivers. Adapt the relevant
operating practices around them. A wholesale migration would change the setup
and introduce requirements outside our current hardware approach.

## Different foundations

| Area | Their implementation | Our implementation / implication |
|---|---|---|
| Host and setup | macOS, Xcode, signed WebDriverAgent, trusted developer-enabled phones | Windows and existing HID boards; their setup is not a drop-in replacement. |
| Input | WDA HTTP commands, plus Appium for workflows | Relative HID movement with calibrated position estimates; their absolute-touch patch cannot be sent to our boards. |
| Video | WDA MJPEG for the selected device, periodic screenshots for the grid | UxPlay decoding into per-phone raw BMP streams; preserve this transport pending measurements. |
| Product structure | Web dashboard, WDA supervisor, worker, Appium, PostgreSQL | Native console, independent kernel, separate receiver processes; do not add their whole service stack just to improve reliability. |

Their [architecture](https://github.com/Git-Agni/prod-FARM-IOS-Core/blob/3e936babd80723b49b3e594f9403b25363078e64/docs/architecture.md)
and [getting-started guide](https://github.com/Git-Agni/prod-FARM-IOS-Core/blob/3e936babd80723b49b3e594f9403b25363078e64/docs/getting-started.md)
describe that setup. The absolute-touch implementation uses Apple's test-event
machinery inside WDA and explicitly constructs portrait events:
[patch](https://github.com/Git-Agni/prod-FARM-IOS-Core/blob/3e936babd80723b49b3e594f9403b25363078e64/Patches/appium-webdriveragent-8.9.1-absolute-touch.patch).

## Recommended implementation priorities

### 1. Guided phone-to-board setup — highest user-visible value

**What they do:** registration has separate readiness checks, specific corrective
messages, port allocation, and a final readiness gate before completion.
[Source](https://github.com/Git-Agni/prod-FARM-IOS-Core/blob/3e936babd80723b49b3e594f9403b25363078e64/src/devices/registration.ts).

**Adapt for us:** a setup flow showing Board detected → Physical phone identified
→ Phone/board binding confirmed → Matching AirPlay receiver selected → Live video
→ Calibration verified. Assign a friendly name such as Rack 01, display its board
suffix alongside it, and keep a visible maintenance/disabled state. Identification
must use one explicitly selected board plus operator confirmation; this is our
adaptation, not a hardware-identification feature demonstrated by their code.

**Existing foundation:** `ReceiverFleet.Validate` already rejects duplicate
identities, overlapping ports, and mismatched saved bindings. Expose these checks
through a usable workflow instead of making the user manage JSON and names.

**Acceptance:** deliberately mismatched binding cannot become Ready; names persist
after restart; identifying one phone leaves the others untouched. Maps to finish
criteria 2, 3, 11, and 12. Feasible with our existing transport.

### 2. Device ownership and a real Stop — highest reliability value

**What they do:** one scheduler queue per device; manual remote input returns a
conflict while an execution is active; tasks receive a cancellation signal.
[Queue](https://github.com/Git-Agni/prod-FARM-IOS-Core/blob/3e936babd80723b49b3e594f9403b25363078e64/src/scheduler/queue.ts),
[manual-input route](https://github.com/Git-Agni/prod-FARM-IOS-Core/blob/3e936babd80723b49b3e594f9403b25363078e64/src/api/app.ts#L404-L410).

**Adapt and strengthen:** give each board one command owner spanning the whole
gesture, not just an individual HTTP call. Serialize ownership acquisition and
dispatch together. Add cancellation/deadlines, a bounded queue, release-on-stop,
and a session generation so old queued actions cannot execute after rebinding
or recovery. Coalesce obsolete hover moves; never silently discard a click or
button-up. Preserve per-phone results for group actions.

**Existing gap:** our `InputRouter.BoardState.Gate` serializes individual commands,
but separate down/move/up requests are not one ownership transaction. Dispatch
has no cancellation parameter and HID sends use `CancellationToken.None`.

**Acceptance:** two clients cannot interleave a drag; Stop cancels pending work
and releases held input; reconnect never replays stale actions; other boards
continue independently. Maps to criteria 4, 5, 8, 9. Feasible, but merits careful
design and regression tests rather than a quick patch.

### 3. Better health and receiver recovery

**What they do:** separate physical connection, WDA, Appium, retry count, and
diagnostic message; reconcile saved devices with connected hardware; progressively
space supervisor restarts at 2, 5, 10, and 30 seconds.
[Source](https://github.com/Git-Agni/prod-FARM-IOS-Core/blob/3e936babd80723b49b3e594f9403b25363078e64/src/devices/connection-manager.ts).

**Adapt:** separate board presence, binding validity, calibration validity, input
ownership, receiver process, AirPlay session, and frame delivery. Include last
error and next retry time. Extend our existing bounded supervisor with graduated
backoff and a targeted retry action; retain a restart cap. At rack scale, stagger
retries so all receivers do not restart together.

Do not restart a healthy stream solely because successive pictures look identical.
Track transport/frame arrival and session state separately. Manual iPhone recasting
remains a documented recovery step; this project does not remove that requirement
from our AirPlay setup.

**Acceptance:** one failed receiver does not disturb another; retry exhaustion
has a clear recovery path; a static Home Screen stays healthy; true pipe loss
clears live status. Maps to criteria 9–12. Incremental work on our existing design.

### 4. Versioned calibration and durable device settings

**What they do:** named coordinate profiles, per-device overrides, bounds checking,
explicit cached-client invalidation, and serialized writes using temporary files
followed by rename.
[Profiles](https://github.com/Git-Agni/prod-FARM-IOS-Core/blob/3e936babd80723b49b3e594f9403b25363078e64/src/devices/coordinates.ts),
[registry](https://github.com/Git-Agni/prod-FARM-IOS-Core/blob/3e936babd80723b49b3e594f9403b25363078e64/src/devices/registry.ts),
[cache test](https://github.com/Git-Agni/prod-FARM-IOS-Core/blob/3e936babd80723b49b3e594f9403b25363078e64/test/remote-cache.test.ts).

**Adapt:** record board UID, phone ID, image dimensions, orientation, pointer
settings, profile version, and last successful calibration check. Invalidate
remembered pointer state and affected cached clients when a binding/profile
changes. Show Recalibration required rather than continuing with stale assumptions.
Write validated configuration via an atomic replacement with a recoverable backup
and one writer. Our `DeviceStore.Save` currently writes directly to the live file.

Their app-target coordinates are not the same thing as our HID pixels-per-unit
calibration. Borrow the profile lifecycle, not the numeric coordinates.

**Acceptance:** changed bindings/settings force the correct recheck; interrupted
saving leaves a valid old or new file; concurrent updates are not lost. Maps to
criteria 3, 4, 12. Suitable for a bounded implementation task.

### 5. Video lifecycle and measurements — keep our raw-frame path

**What they do:** a stream connect deadline is separate from the lifetime of the
viewer; an abort signal closes the upstream feed; clients/screen metadata are
cached per device. The grid uses lower-frequency stills rather than a full live
view for every tile.
[Source](https://github.com/Git-Agni/prod-FARM-IOS-Core/blob/3e936babd80723b49b3e594f9403b25363078e64/src/devices/wda-remote.ts),
[test](https://github.com/Git-Agni/prod-FARM-IOS-Core/blob/3e936babd80723b49b3e594f9403b25363078e64/test/mjpeg-stream.test.ts).

**Adapt:** verify our existing console cancellation on master switch/minimize/close;
bound outstanding frame requests; retain only the newest useful frame. Cancel
obsolete view work without stopping the shared AirPlay receiver unnecessarily.
Give each frame a sequence and arrival time so received/displayed FPS and lag
can be compared honestly. Profile tile work separately from the selected view.

Our `FrameStore.WriteFrame` holds the same lock used by ingestion while writing
the response. This remains a plausible contention point, not a proven cause of
the earlier C241 slowdown. Instrument lock waiting/holding before changing buffer
ownership. Their MJPEG implementation supplies no proof that JPEG would improve
our local BMP transport, and no evidence of vendor-speed parity.

**Acceptance:** repeated view switches do not accumulate requests/memory; slow
consumers cannot build unlimited backlog; paired timing captures distinguish
input delay from frame delay. Maps to criteria 6, 7, 10.

### 6. Verify outcomes and classify retries

**What they do:** targeted screenshot/pixel checks distinguish selected UI state;
workflow retries are separated from a final action that should not be duplicated.
[Pixel check](https://github.com/Git-Agni/prod-FARM-IOS-Core/blob/3e936babd80723b49b3e594f9403b25363078e64/src/tiktok/pixel.ts),
[workflow retry boundary](https://github.com/Git-Agni/prod-FARM-IOS-Core/blob/3e936babd80723b49b3e594f9403b25363078e64/src/tiktok/post.ts#L219-L278).

**Adapt:** a test command records intended target, dispatch result, and a subsequent
visual observation. Start with tightly scoped checks such as Spotlight open,
known page transition, or expected Notes text. Save evidence when a result is
uncertain. Do not call a click successful merely because bytes were sent, and
do not double-click because a screenshot is ambiguous.

Treat automatic retry policy as part of each action: observing status is
different from reissuing a tap or typed text. Avoid a generic retry wrapper around
all commands. Add screenshot assertions to testing first, then consider automation.

**Acceptance:** an ambiguous screenshot is inconclusive, not a pass; an interrupted
action is not silently replayed. Maps to criteria 4, 6, 8, 9. Vision checks need
their own false-positive/false-negative evaluation.

### 7. Durable, versioned workflows — later, after the console is dependable

**What they do:** task identity includes plugin ID, task type, and version; execution
history and attempts are stored; schedule materialization uses a database
transaction and row locking together with queue insertion.
[Contract](https://github.com/Git-Agni/prod-FARM-IOS-Core/blob/3e936babd80723b49b3e594f9403b25363078e64/src/plugin.ts),
[repository](https://github.com/Git-Agni/prod-FARM-IOS-Core/blob/3e936babd80723b49b3e594f9403b25363078e64/src/scheduler/repository.ts#L198-L239).

**Adapt later:** keep app-specific workflows outside the hardware/video core.
Store explicit workflow versions and record runs, cancellation, results, and
uncertain outcomes. Existing workflows should not silently acquire new behavior
after an update. Choose local persistence based on our deployment needs; a
PostgreSQL server is not required merely because their project uses one.

This is a future capability, not an additional prerequisite silently added to
[our completion checklist](../FINISH-CRITERIA.md).

## Quality assessment and limits

There are substantive positive signs: 29 test declarations across 13 test files,
dependency injection in important services, explicit target checks, coordinate
validation, response redaction, atomic registry replacement, versioned task
validation, and browser-origin write protection. The package provides typecheck
and test commands. Those are meaningful engineering choices.

The following limits matter when judging or adapting it:

- **Tests were inspected, not run.** Mocked API/service tests are not a measured
  19-phone soak or performance certificate. No `.github/workflows` directory is
  present in this reviewed snapshot, despite the README's hosted-CI policy.
- **Release label:** `package.json` says `0.1.0-review.0`; that is a label, not
  proof of either bad or production-ready software.
- **Device coverage:** the bundled coordinate table contains one iPhone 8 profile.
  Unknown/default layouts require care; these coordinates do not cover our XR rack.
- **Ownership is not fully atomic:** the manual-action route checks active work,
  then dispatches separately. That is a useful guard but not proof that a scheduler
  cannot acquire the device between those operations.
- **Stop is cooperative:** execution polls stop requests once per second; the
  subprocess runner sends SIGTERM without a forced-kill escalation in that function.
  WDA tap/swipe primitives do not receive the execution cancellation signal.
  Therefore its Stop design is not evidence of immediate end-to-end cancellation.
  See [executor](https://github.com/Git-Agni/prod-FARM-IOS-Core/blob/3e936babd80723b49b3e594f9403b25363078e64/src/scheduler/executor.ts).
- **A job success is not universal outcome proof:** the posting path logs submission
  after a tap and waits; do not interpret that as a general exactly-once external
  side-effect guarantee.
- **Plugins are trusted code**, explicitly not a sandbox. Keep any future plugin
  boundary honest. [Plugin guidance](https://github.com/Git-Agni/prod-FARM-IOS-Core/blob/3e936babd80723b49b3e594f9403b25363078e64/PLUGIN_DEVELOPMENT.md).
- **Local API protection is worth adopting:** their API checks browser origins and
  rejects a non-loopback bind without an authentication provider. Our inspected
  `ApiServer` does not currently implement comparable origin/auth checks. Treat
  this as an explicit API-hardening task; do not expand network access as part
  of borrowing the design. [Bind guard](https://github.com/Git-Agni/prod-FARM-IOS-Core/blob/3e936babd80723b49b3e594f9403b25363078e64/src/security.ts).

The repository declares Apache-2.0 and includes LICENSE/NOTICE. Preserve upstream
provenance for any actual code reuse and review those files and dependency notices
before redistribution. This review imports no upstream implementation into our app.

## Recommended next work

Newer evidence discovered during implementation: the precise-movement deployment
failed repeatable C241 checks and was rolled back. See
[deployment verification](precise-candidate-deploy-20260915/verification.json).
The earlier isolated success does not establish acceptance of that build.

1. Keep established movement timing; investigate the rejected speed change separately.
2. Implement device ownership, gesture boundaries, cancellation, and stale-work rejection.
3. Implement guided binding/profile setup and atomic device configuration.
4. Improve per-phone health/retry controls and add the specific regression cases above.
5. Measure video/frame lifecycle under 2, 4, 8, then 19 phones before optimizing it.
   Our current `ReceiverFleet.Validate` explicitly limits configuration to two
   receivers; expanding that is a controlled development step, not just adding rows.
6. Add durable workflows only after the core completion criteria are met.

Grok can handle bounded follow-ups such as atomic saves, profile validation,
readiness messages, and targeted tests with a precise handoff. Device ownership,
cancellation, and measured frame-buffer changes deserve a deeper design/review pass.
