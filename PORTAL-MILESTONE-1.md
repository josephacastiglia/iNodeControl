# NodeTheory customer portal — Milestone 1

> **Status (25 September 2026): implemented and tested in simulation; waiting for Windows and physical-phone validation. Milestone 2 is paused.**
> Codex runs the Windows validation from [WINDOWS-VALIDATION-HANDOFF.md](WINDOWS-VALIDATION-HANDOFF.md), against code commit `c945512b4cadd2d5d0732db2d942b11e1d31e778`.

Written 25 September 2026. Built on `claude/focused-noether-s600e0` from base commit
`ee445d70e5f7e3cd9497a9162fc89ba9f6061e4a` ("Import iMouse 2.0 source and development records").
Kernel integration was written against that commit's `src/iMouse.Kernel/ApiServer.cs`,
`InputSessions.cs`, `InputRouter.cs`, `FrameStore.cs`, `ReceiverFleet.cs`, and the console's
`ApiClient.cs` / `InputLeaseClient.cs`. Where documents disagreed, the source won
(see "Findings" below).

## The milestone path

**Customer login → authorized phone list → live preview → take control → supported action → release / Stop → audit record.**

| Part | Where |
|---|---|
| Customer portal (backend and web app) | [`portal/`](portal/README.md) |
| Rack agent (Windows rack PC, outbound connection) | [`rack-agent/`](rack-agent/README.md) |
| Simulated kernel for cloud development | `rack-agent/sim/` |
| Real-kernel-source conformance harness | `rack-agent/conformance/KernelHarness` |

## Evidence level — read this first

| Level | Status |
|---|---|
| **Implemented and tested with the simulator** | **Yes.** Everything in this milestone. |
| **Checked against the real kernel source** (compiled on Linux, fake HID, synthetic frames) | **Yes, for the ownership contract and long-text handling** (10 tests). This is not a Windows build and not Windows validation. |
| **Integrated with the actual Windows kernel** | **No.** Not run on Windows. See the checklist below. |
| **Verified on physical phones** | **No.** |

No result here counts as Windows or hardware validation. Scratch runs with Windows functions stubbed out are not counted anywhere.

## What was built

**Rack agent** (`rack-agent/`, Node.js 22, dependencies `ws` and `jpeg-js`)
- Outbound WebSocket to the portal, authenticated with `rack_<id>.<secret>`. It requires `wss://` except for a portal on the same PC. The kernel address must be loopback.
- Refuses input unless `/kernel/status` has `input_protocol: 1` and `input_leases_required: true`.
- One lane per phone:
  - acquires a lease (30 s) and renews it every 10 s on its own timer;
  - releases, stops, and resumes only with `expected_generations`;
  - runs commands strictly in order, and at most one is active per phone;
  - Stop skips the queue and cancels pending work;
  - a failed or cancelled command is treated as the kernel's latched Stop;
  - an unconfirmed command is never retried and stops the phone;
  - it detects when an operator stops the phone outside the portal.
- Every kernel reply is checked: envelope `status`, then `data.code`, then per-phone `results`.
- Inventory reports control and video separately. Video includes the frame counter and when it last advanced. Board presence comes from `/config/usb/get` and failures there are tolerated.
- Preview bridge: raw BMP from `/pic/screenshot`, with the content type checked (`image/bmp`, or JSON code 25/1).
  - One capture loop per watched phone.
  - Grid previews are 144 px at about 1 fps; the focused phone is 360 px at up to about 8 fps.
  - JPEG encoding runs on worker threads.
  - Frames are dropped under backpressure; identical frames are not re-encoded; watches expire.
- On portal disconnect, every held phone is released immediately and nothing is replayed.

**Portal** (`portal/`, Node.js 22, dependency `ws`, SQLite via `node:sqlite`)
- Migrations (`server/migrations/001_initial.sql`) cover customers, users, sessions (stored hashed), agents (secret stored hashed), phones, allocations, commands, group actions and the audit log.
- Authentication and authorization are described in [portal/README.md](portal/README.md#security-model). Ownership is checked on every route, again before dispatch, and again by the agent when the command reaches the front of the phone's queue.
- Control sessions: one portal controller per phone. A teammate sees "In use by <name>"; the desktop console shows as "In use by NodeTheory". The browser heartbeats; a session ends after 35 s without one, and the browser releases on page close.
- Actions have individual results: Sent (`succeeded`), Not sent (`not_sent`) or Uncertain (`uncertain`), with step and character progress (see the update below). History and audit record them without typed text.
- Groups: explicit selection mode with a visible warning bar and per-phone outcomes. **Retry** sends only to phones where nothing was sent. Sent and uncertain phones are skipped server-side.
- Customer **Stop all** covers only their own phones. Staff **Emergency stop** requires typing STOP and covers every enabled phone, including ones the console holds.
- Staff console:
  - rack credentials, shown once and revocable;
  - phone inventory with *Unverified → In service* before a phone can be assigned (a plan size is not inventory);
  - customers, users, plans and suspension;
  - a read-only support view and the audit log.
- Web app in the website's graphite/coral system (Manrope, DM Sans, same tokens and favicon):
  - Overview, Phones grid, focused phone view, Activity, Staff.
  - On the phone screen: click to tap, drag to swipe, hold to long-press. Buttons for Home, App switcher, Control Centre, swipe pad, text box with an alphabet check, Return/Delete/Tab/Esc and Reset pointer.
  - Control and Video status are shown separately.
  - A "Not available remotely yet" list, and Diagnostics behind a disclosure.
  - Coordinate mapping accounts for letterboxing and the difference between JPEG size and source size.
  - Strict CSP and no inline styles.
  - Accounts, Content and Automations appear as disabled "soon" items.

## Validation-preparation update (25 September 2026)

**Three action outcomes, used end to end** (agent, portal, database, UI, group results):

| Outcome | Meaning | Retry |
|---|---|---|
| **Sent** (`succeeded`) | The kernel confirmed every step. HID was written; this is not proof of the screen result. | — |
| **Not sent** (`not_sent`) | Confirmed that nothing reached the phone. | Only this state may be retried, and only by a person. Group retry sends only to these phones. |
| **Uncertain** (`uncertain`) | No reply, a failure or cancellation during execution, or partly complete. | Never retried. The phone is stopped or handed back. |

- Results carry step progress. Text results carry characters confirmed / uncertain / not sent.
- Migration `002_command_outcomes.sql` rebuilds the commands table; old rows map `rejected → not_sent` and everything else unsuccessful to `uncertain`.

**Long text**
- The whole text is validated before the first chunk.
- Chunks run back to back in one queued operation under one lease, so other input waits and never interleaves.
- Lease renewal keeps running throughout. This was tested on the real kernel source: a roughly 9 s send on a 2 s lease.
- Stop interrupts the chunk in flight. Real kernel source: Stop returned promptly with 32 characters confirmed, 32 uncertain and 32 not sent, and no key-down followed Stop.

**Isolation review**
- Preview long-polls re-check ownership after waiting.
- A controlling user's name is shown only within their own customer.
- New tests: activity scoping, audit attribution, and a portal restart with no replay and no silent restore of control.

**Validation support**
- Agent single-instance lock, PID logging and Ctrl+Break handling.
- Receiver fps and process stats.
- A browser measurement panel with JSON export.
- A PowerShell process sampler, which ran under PowerShell 7 on Linux (not yet under Windows PowerShell 5.1).
- `npm run bootstrap-validation`.
- Node 22.13 or newer required.

**Unchanged:** kernel, desktop console, launch scripts, `KEYBOARD-SPEC.md`.

## Tests actually run (Linux container)

The container ran Ubuntu 24.04, Node 22.22.2 and the .NET SDK 8.0.131.

| Command | Result |
|---|---|
| `cd rack-agent && npm test` | **33 passed, 0 failed** (23 simulator/unit and 10 real-kernel-source conformance). Run 3 times on 25 Sep. The first build had 23. |
| `cd portal && npm test` | **38 passed, 0 failed.** Run 3 times on 25 Sep, and again after the final UI change. The first build had 31. |
| Headless Chromium UI run (Playwright) | Login, overview, grid, focus, take control, tap, text, Stop, Resume, group control, group Home, activity, and staff pages; widths 1440 and 390. No page errors (one expected 401 before sign-in), no horizontal overflow at 390 px. The tap at the Notes icon produced `Tap at 75, 159` and opened Notes on the simulated phone. |

The five required acceptance areas:

| Requirement | Tests |
|---|---|
| Customer A cannot access Customer B's devices, images, files or jobs | `portal/test/isolation.test.mjs`: 13 cross-customer endpoints return 404 and nothing reaches any phone; group retry across customers is refused; Stop all is scoped; roles, CSRF and Origin. *Files: the content library is Milestone 2; its isolation tests come with it.* |
| Portal and desktop ownership conflicts | `safety.test.mjs` (both directions, teammate conflict, operator Stop); `conformance.test.mjs` (real kernel source) |
| Stop, lease expiry and connection loss prevent stale input | `safety.test.mjs`: Stop cancels queued actions with zero input afterwards; stale-generation Resume is refused; lease expiry; network drop mid-action → `uncertain`, lease released, nothing replayed, control not restored; an unconfirmed action runs exactly once; portal restart; revocation. Also in `agent-units` and `conformance`. |
| Group failures preserve individual outcomes | `groups-previews.test.mjs`: a 3-phone Home gives Sent / Not sent / Uncertain. The retry reaches only the Not-sent phone, so every phone received Home at most once. Group text keeps per-phone character progress, and a partly typed phone is never retried. |
| Slow previews do not create an unlimited backlog | `groups-previews.test.mjs` (stalled viewer, one frame per tier, capped waiters); `agent-units` (backpressure drops with zero encoder queue; watch expiry) |

## Findings from the source that change behaviour

1. **Long text latches Stop on the ownership kernel.**
   - `InputSessions.ExecuteAsync` cancels each command after 8 s, and a cancelled command latches Stop. Typing costs 140–170 ms per character, so one `/key/sendkey` safely carries only about 50 characters. `KEYBOARD-SPEC.md` says 1–1000.
   - Confirmed against the real kernel source: a 64-character send returned 499 and stopped the phone.
   - The agent sends text in 32-character chunks (max 200 per send).
   - **The desktop console has the same problem.** It sends up to 2,000 characters in one command. This is filed as a separate task.
2. **Board enumeration can fail on its own.** `/config/usb/get` calls into USB enumeration on every request. The agent treats its failure as "board status unknown", not as a phone fault.
3. **Stopping an idle phone also latches Stop.** The kernel creates the slot and marks it stopped, so every Stop needs an explicit Resume. The UI says so.
4. **`/input/status` lists only input-enabled phones.** Phones missing from it show as "Controls unavailable".
5. **Command HTTP timeout.** It must exceed the kernel's 8 s deadline, so the agent uses 12 s. A timeout is treated as *uncertain* and the phone is stopped.

## Known limitations

- **No Windows or hardware validation yet.** Simulator timings are approximate.
- **Single portal instance.**
  - Control sessions and the agent hub are in memory, so a portal restart ends all control sessions. That is safe: the agent releases every phone when the link drops.
  - Scaling out needs a shared session/hub store and a move from SQLite to PostgreSQL.
- **`node:sqlite` is marked experimental in Node 22.** The npm scripts silence its warning.
- **Accounts:**
  - staff create users with a temporary password;
  - no self-service password reset, invitation email or MFA yet — MFA for staff is recommended before launch.
- **Drags are sent when the pointer is released.** The whole path is sent as down → moves → up in one queued action, not streamed live. That is safer over the internet but less immediate.
- **Previews are pulled JPEG stills, not a video stream.** HTTP/2 at the proxy is recommended. Frame rate and latency on the real rack are unmeasured.
- **"No new frames" can't distinguish a still screen from a stalled receiver**, so it is shown as information, not as an error.
- **Staff-only operations.** Recasting AirPlay, USB restart and live rebinding stay with staff at the rack; the kernel returns code 41 for them. Portrait only.
- **Keyboard limits.** English (US) printable ASCII only. Typing Mode, Smart Punctuation and auto-correction apply on the phone (see `KEYBOARD-SPEC.md`).
- **Browser crash.** If the browser crashes without closing the page, control lingers up to about 35 s before the portal releases it. The kernel lease also expires on its own if the agent dies.
- **Not in Milestone 1:**
  - account registry, content library and media delivery;
  - scheduling, automation recipes, publishing and analytics;
  - SIM/IP provisioning (separate infrastructure).

## Decisions needed (they don't block Milestone 1)

1. **Media delivery to phones (blocks Milestone 2 "delivered to phone").** How should uploaded files reach an iPhone? Options:
   - iCloud Photos or a shared album the phones sync;
   - Apple Configurator or Finder over USB on the rack PC;
   - an MDM or app-based pull.

   Until this is decided, the content workflow will stop at "uploaded / processed", never "on phone".
2. **Portal hosting (blocks customer launch).** Where the public portal runs (VM or provider), its domain, and backups for the database.
3. **Staff sign-in hardening.** Whether to add TOTP MFA ourselves or use an identity provider.

## Windows validation

The checklist originally in this section has been replaced by [WINDOWS-VALIDATION-HANDOFF.md](WINDOWS-VALIDATION-HANDOFF.md). That document covers:
- the exact commit, prerequisites, commands, configuration and rollback;
- separate simulator and real-rack steps;
- a staged checklist: one phone, then two phones and two customers;
- the measurement methods.

## Next milestones (proposed)

1. **Accounts:**
   - per-phone account registry (platform, handle, notes, status);
   - credentials in a separate encrypted table with an envelope key outside the database;
   - reveal and use are audited, and credentials are never in lists or logs.

   **Content:**
   - upload with progress, and a processing pipeline (validation, transcode checks);
   - a `MediaDelivery` adapter interface whose implementation depends on decision 1;
   - status shown honestly: *uploaded → processed → awaiting delivery method*.
2. **Scheduling and automation:**
   - schedules in the customer's time zone, with a visible per-phone queue shared by every account on that phone;
   - versioned recipes made of supported actions plus explicit screen checks;
   - run history, a retry decision per step, and an audit log;
   - ownership re-checked when each job runs;
   - automation workers take the same per-phone control as people, so a phone never has two controllers.
3. **Publishing and analytics.** Only through integrations that are implemented and verified, and labelled as such.
