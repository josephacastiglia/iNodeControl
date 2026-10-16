# iMouse 2.0 / iNodeControl — project handoff for Gemini

**Prepared:** 15 October 2026 · **Audience:** Gemini 4 Argon, joining the project for feature development

**Repository:** [josephacastiglia/iNodeControl](https://github.com/josephacastiglia/iNodeControl)

**Verified local source baseline:** `11b7d295093d0d4ad9f2240fafa7dc987e1e04a3`, on `local/combined-candidate-20261012`.

This is an engineering handoff, not a release approval. The application works on a small physical rack, but full product acceptance is incomplete. Nothing is promoted by this document. Source and historical records were inspected for this handoff; no new phone tests or current rack-state checks were performed.

## Read this first

1. **Start from the combined candidate, not `main`.** The latest combined work is local and ahead of the recorded GitHub branches. A plain GitHub clone does not contain all of it. A companion Git bundle preserves the committed core.
2. **Keep the installed release unchanged.** It is a separate, older build used by the operator. Build features into new output folders and use isolated candidate settings.
3. **Preserve existing evidence and worktrees.** Do not reset, clean, delete, or blindly merge them. Some captures and binaries exist only in local archives.
4. **Latest live result:** candidate Home worked once from Settings; candidate App Switcher failed. Testing stopped at that failure and the release was restored. These are bounded results, not a completed controls gate.
5. **Typing is deferred.** Fresh-field space loss with Full Keyboard Access remains unresolved as a general product feature. Several experiments already ran; do not restart them from old “pending” notes.
6. **Screen mirroring is not automatically recoverable today.** A historical coordinate-based recast helper would select the operator’s Bedroom TV in the latest observed menu. Do not run it unchanged.
7. **There is a separate untracked automation prototype in the checkout.** It is not part of the tested core or source bundle. In particular, its untracked C# file could enter a working-tree build through SDK default compilation. Use a clean feature worktree to avoid mixing it in accidentally.

## Contents

1. Product and terminology
2. Where the code lives and how to transfer it
3. Architecture and code map
4. Hardware, identity, and video
5. Input contract and recovery behavior
6. Implemented work
7. Exact candidate and latest physical validation
8. Open issues and corrected findings
9. Reverse-engineering findings
10. Portal and automation workstreams
11. Development and testing workflow
12. Product acceptance criteria
13. Where to implement new features
14. Live-test operating rules
15. Evidence and reference documents
16. First-session checklist and completion expectations

## 1. Product and terminology

The goal is a Windows application that lets an operator reliably view and control a rack of **19 iPhones**, with clear phone identity, accurate input, responsive video, group actions, immediate Stop, and predictable recovery. It should work independently of the original vendor application.

| Name | Meaning |
| --- | --- |
| **iNodeControl** | Git repository and overall project. |
| **iMouse 2.0** | The Windows desktop console and independent control stack being developed. |
| **Console** | WPF operator interface; executable `iMouse2.exe`. |
| **Kernel** | Local HTTP service, USB/HID input routing, leases, and receiver supervision; `iMouse2.Kernel.exe`. |
| **Board** | USB HID hardware that delivers input to its attached iPhone. |
| **Receiver** | One UxPlay AirPlay receiver instance associated with a phone. |
| **C24C / C241** | Rack board/phone labels used in test records, not Windows process IDs. |
| **FKA** | iOS Full Keyboard Access. Its keyboard focus behavior affects typing and shortcuts. |
| **NodeTheory / portal** | Separate web portal and rack-agent work on another branch. |
| **Installed release** | Operator’s current working installation. Despite some folder names containing “candidate,” it is distinct from the latest development candidate. |

The desired operator experience is simple: choose unmistakably identified phones, see current video and control status, issue an action, understand whether it succeeded or is uncertain, and recover without accidental replay or input to another phone.

The project is beyond a prototype, but it is **not a final, fully accepted 19-phone product**. Working foundations, automated tests, physical experiments, and historical gate claims must be kept separate.

## 2. Where the code lives and how to transfer it

### Authoritative development checkout

```text
C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-combined-candidate
```

This document calls that directory **CORE_ROOT**. Repository-relative paths below are relative to it unless another branch or location is stated. `CORE_ROOT` is descriptive notation, not a preconfigured environment variable.

| Source | Recorded revision | Purpose |
| --- | --- | --- |
| `local/combined-candidate-20261012` | `11b7d295093d0d4ad9f2240fafa7dc987e1e04a3` before this documentation update | Current integrated core and latest evidence records. Start here. |
| `local/coordinator-work` | `01fb669` | Earlier work in the original checkout. Preserve. |
| `claude/input-timeout-integration` | Local `d0c4ccf`; cached remote `472bb04` | Claude integration and return handoff history. Newer local work is not all on the recorded remote. |
| `claude/jovial-yonath-f044e9` | `a6e4a9b` | Original text-chunking work and reports. |
| `claude/funny-margulis-86e51b` | `43b43f7` | Test-settings isolation. |
| `claude/track-gate-evidence` | `900f5b4` | Preserved run records and corrected gate scope. |
| `claude/gate4-harness-v2` | `2c98f44` | Earlier offline accuracy-tool branch; later consolidated in the combined work. |
| `handoff/main-uncommitted-20260925` | `ba733c2` | Preserved earlier Orca/Codex work. |
| `local/fka-passthrough-probe` | `d0c4ccf` | Experimental typing/focus work; do not treat as a finished typing fix. |
| Cached `origin/claude/focused-noether-s600e0` | `6b24a96` | Portal and rack agent. |
| `main` | `ee445d7` | Original import, not the current integrated product. |
| `backup/input-timeout-integration-pre-redaction` | `544bda1` | Local sensitive-history backup. **Never push or distribute this branch.** |

Remote values above are locally recorded references. They were not refreshed from GitHub for this document. Inspect the actual checkout before editing; historical paths and commit tips can change.

The original checkout is:

```text
C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0
```

It also contains older Claude worktrees, including `.claude\worktrees\keyboard-spec-reconcile`. Do not use a worktree name as proof that its contents are the latest code.

### Gemini on this PC

Read this document, inspect Git status and worktrees, then create or reuse a clean feature worktree based on the current committed combined branch. Do not switch the operator’s original checkout or overwrite another session’s changes. Confirm another agent is not working on the same files or hardware.

### Gemini elsewhere

Use the accompanying **`iNodeControl-core.bundle`** and **`TRANSFER-RECEIPT.json`**. The bundle contains the committed history reachable from the combined branch, including this handoff. It does not include untracked prototypes, output binaries, raw evidence archives, unrelated branches, vendor credentials, or the sensitive backup branch.

Example transfer command, with both uppercase paths replaced:

```powershell
git clone --branch local/combined-candidate-20261012 "C:\TRANSFER_DIR\iNodeControl-core.bundle" "C:\NEW_CHECKOUT"
```

The receipt records the actual handoff commit and bundle hash. A source bundle is enough for code review and many offline changes; it is not a portable installation of the rack, native dependencies, or physical test evidence. A web chat without filesystem/build access cannot independently validate the application.

## 3. Architecture and code map

```text
Operator
  |
WPF desktop console
  | local HTTP, leased commands
Independent kernel (normally 127.0.0.1:9913)
  | serialized USB HID reports per board
USB input board -> attached iPhone

iPhone -- LAN AirPlay --> per-phone UxPlay receiver
                               |
                          frame pipe
                               |
                             kernel
                               |
                       console video tiles
```

Input and video are separate paths. A successful HID/API command does not prove the phone performed the intended action. A receiver process running does not prove video is connected, advancing, or displayed.

### Technology

- C# / .NET 8 Windows for the kernel and console; WPF for the console.
- Python tools for acceptance, evidence, manifests, diagnostics, and packaging.
- PowerShell for Windows launch and test workflows.
- UxPlay, GStreamer, and the MSYS2/UCRT native runtime for AirPlay video.
- Separate Node.js portal/rack-agent branch; see section 10.

### Files to know

| Area | Main files or directories | Responsibility |
| --- | --- | --- |
| Console startup | `src/iMouse.Console/App.xaml.cs` | Modes, explicit data directory/address, startup validation. |
| Main interface | `MainWindow.xaml`, `MainWindow.xaml.cs`, `PhoneWall.cs`, `Theme.cs` under the console | Controls, phone wall, operator feedback. |
| Input client | `ApiClient.cs`, `InputLeaseClient.cs`, `InputControls.cs` | Requests, ownership, sequences, outcome classification. |
| Input scheduling | `InputActionQueue.cs`, `DragInput.cs`, `PointerMovePump.cs` | Ordered actions, drag behavior, coalesced pointer movement. |
| Connection lifecycle | `ConnectionLifecycle.cs`, `ConnectionCleanup.cs`, `CleanupDiagnostics.cs` | Awaited shutdown/reconnect and retained cleanup failures. |
| Console state | `SettingsPersistence.cs`, `ConsoleBuildInfo.cs` | Settings and build identity. |
| Console video | `LiveFrame.cs`, `PreviewFreshness.cs`, `TileStreams.cs`, `FrameMetrics.cs` | Frame ownership, freshness, stream scheduling, measurements. |
| Console diagnostics | `ResponseTiming.cs`, `ConsoleDiagnostics.cs`, `MainWindowDiagnostics.cs` | Timings and diagnostic state. |
| Kernel startup | `src/iMouse.Kernel/Program.cs`, `KernelStartup.cs`, `ReceiverRuntime.cs` | Configuration, runtime checks, startup order. |
| HTTP and input ownership | `ApiServer.cs`, `InputSessions.cs`, `InputRouter.cs` under the kernel | Dispatch, leases, Stop, command serialization. |
| Board protocol | `HidProtocol.cs`, `HidConnection.cs`, `HidHost.cs` | HID reports and USB connections. |
| Incoming board reports | `HidInputReader.cs`, `HidInputReport.cs`, `HidReplyMonitor.cs` | Read/parse/observe replies without assuming undocumented ACK semantics. |
| Device identity | `DeviceStore.cs` | Configuration and board/phone bindings. |
| Receiver lifecycle | `ReceiverFleet.cs`, `AirplaySupervisor.cs`, `ReceiverProcessLifetime.cs`, `ReceiverLog.cs`, `FrameStore.cs` | Per-phone receiver supervision and frame transport. |
| Native receiver | `tools/airplay/uxplay/` | Receiver source and native build work. |
| Packaging | `tools/build_manifest.py`, `managed_symbols.py`, `stage_release.py`, `stage_receiver_runtime.py` | Identity, managed symbols, immutable bundles, native runtime staging. |

Read the actual implementation and tests before changing an interface. Some documents describe earlier revisions of the same paths.

## 4. Hardware, identity, and video

The original hardware exposes USB HID devices, with vendor ID `720A` recorded in the project. Device records associate a board with a phone identity, receiver identity, and calibration. The rack configuration has five explicit bindings and fourteen placeholders; this does not mean nineteen physical pairs are validated.

Most recent controlled work has used **C24C**. **C241 is a protected second phone** and must not receive input in a C24C-only window. Read the current configuration and identity checks rather than copying an old device identifier or PID from a report.

Preview coordinates are phone-image coordinates, not Windows desktop coordinates. Historical previews were approximately 500 × 1080 portrait, but read actual dimensions and calibration. The kernel’s relative-pointer position is an estimate based on issued movement and reset behavior, not an independently measured touch position.

Each phone has its own UxPlay process, identity, ports, and frame pipe. AirPlay discovery uses Bonjour/mDNS. After receiver restarts, rediscovery has varied from seconds to approximately 31 minutes. In one experiment, a cable replug coincided with discovery returning; that did not establish a cause or an approved recovery routine.

The kernel normally listens on **9913**. Port **9911** belongs to the vendor/default-service context and is not a safe candidate fallback. Keep the kernel on loopback; input leases are concurrency controls, not an HTTP authentication system.

## 5. Input contract and recovery behavior

### Ownership

An input lease gives a controller temporary authority over a specific phone. The console can take a lease through ordinary interaction, including hover tracking. This is why an agent may need the installed console to release a phone before using the API.

The kernel exposes acquire, renew, status, Stop, release, and Resume operations. Tokens and generations prevent stale commands or cleanup from affecting a new controller. Lease duration defaults to 30 seconds, with a bounded configurable range. Never bypass ownership by writing raw HID reports or stealing an active lease.

Commands are serialized for the relevant phone/board. Stop has a separate cancellation path so it does not wait behind the work it must stop. A paused or failed action must not be automatically resumed or replayed.

### Outcomes

Keep these outcomes distinct:

| Outcome | Meaning |
| --- | --- |
| Confirmed API completion | The kernel completed its command path; the phone’s visual result still needs verification where relevant. |
| Not sent | The action never reached transport, for example because an earlier queued action paused input. |
| Uncertain | The request may have partially or fully executed, but its outcome cannot be confirmed. Do not retry automatically. |
| Operator cancellation | Stop, selection change, disconnect, or shutdown cancelled local work. This is not automatically a timeout. |

The HTTP client and kernel command deadline are approximately eight seconds. A timeout pauses input, shows the reason, enables explicit recovery, and preserves uncertainty. Held-button cleanup is scoped to its own lease. The UI distinguishes confirmed cleanup from cleanup that could not be confirmed.

The text sender currently uses **12-character chunks** and a **temporary 200-character input limit**. Earlier 32-character chunks exceeded the deadline under host load, including a recorded 8,021 ms failure. Twelve is a measured improvement, not a guarantee under arbitrary load. A failed chunk is never retried automatically, and the UI reports confirmed progress separately from an uncertain partial chunk.

### API orientation

Common read paths include `/api/kernel/status`, `/api/input/status`, `/api/device/get`, and `/api/pic/screenshot` with the appropriate parameters. Commands use the existing API envelope; this is a schema illustration, **not a ready-to-run phone command**:

```json
{
  "fun": "/key/sendkey",
  "data": {
    "id": "VERIFIED_DEVICE_ID",
    "token": "CURRENT_LEASE_TOKEN",
    "fn_key": "Home"
  }
}
```

Check the actual route implementation for the endpoint, fields, and response shape. Inspect HTTP status, the application result code, and each phone’s result. HTTP 200 alone is not success.

Unsupported live operations must fail clearly. Current `/device/set` and AirPlay connect/disconnect handling intentionally refuse unsupported behavior instead of pretending to succeed. USB restart is not a completed control feature. The existing `force_recast.py` gesture helper is not a safe name-aware reconnection workflow.

## 6. Implemented work

These areas have implementation and bounded evidence in the combined branch. “Implemented” does not imply every release gate is signed off.

| Area | Improvements carried forward |
| --- | --- |
| Text and cancellation | Chunked sending, honest partial-progress reporting, first-click Stop, explicit timeout state, no automatic retry/replay. |
| Queue behavior | Waiting commands are reported as not sent after an earlier failure; ordinary operator cancellation remains distinct. |
| Drag cleanup | Scoped release after uncertain drag failure, stale-release protection, confirmed versus unconfirmed cleanup reporting. |
| Failure messages | Late renewal failures no longer overwrite the original failure that paused the phone. |
| Input lifecycle | Ordered actions, bounded/coalesced hover work, correct final drag position, captured cancellation/ownership context. |
| Connection cleanup | Awaited shutdown/reconnect, retained cleanup diagnostics, and work that does not silently outlive its connection. |
| Settings | Isolated automated tests and candidate data directories; explicit endpoints; atomic settings/binding writes. |
| Startup | Configuration and runtime checks, build identity, validation without launching the operator interface or hardware work. |
| Video | Frame age/session tracking, bounded streams and buffers, per-tile lifetime handling, isolation of slow consumers. |
| Receiver recovery | Bounded logs and retries, exhausted-retry reporting, root-process cleanup, joined fleet shutdown. |
| Native receiver | Parser/memory fixes with reproduction work, native dependency packaging and provenance records. |
| Diagnostics/release | Diagnostic exports, manifests, staging checks, managed DLL/PDB pairing, native runtime capsule checks, restore documentation. |
| Acceptance tooling | Maintained accuracy runner, honest timing/failure accounting, console-visible timing support, endurance failures retained in results. |
| Protocol work | Passive reply parsing/recording, guarded navigation variants, explicit experimental absolute-position path, targeted protocol tests. |

The latest integrated package records **290 kernel checks, 411 console headless checks, and 74 relevant packaging/symbol checks**. The later navigation runner records **30 fake-API checks and five guard-removal controls**. These are recorded results for identified revisions, not suites rerun for this document. Do not sum older counts or use mock results as physical acceptance.

## 7. Exact candidate and latest physical validation

### Candidate identity

Product source for the current review binaries:

```text
373dd58a6d5c1c541984e9b4ac8b76c9ed3e53e4
```

Package under CORE_ROOT:

```text
output\staging\combined-re-improvements-20261014
```

Recorded run folder:

```text
output\candidate-runs\re-improvements-20261014
```

| Item | SHA-256 |
| --- | --- |
| Kernel DLL | `572252ef7b30783a2d03612fb105099255f95f42b21e46f9b9a39e799e218e2c` |
| Console DLL | `609a95c946faed7d38d54fc8c040bfbb39c6df0948da5127c0cb5714d76e96ed` |
| Package manifest | `7d8f145c1726326fa1cbd419195399e6dde8e97bd65535f1f3b452e482f9689d` |

The package has 698 entries. Later commits include tools, reports, and archive receipts; do not assume the latest Git HEAD is the exact binary source. The untracked automation files are not in these binaries.

### Latest navigation window: 14 October local time

Source: `analysis/navigation-live-20261014/README.md`.

| Check | Observed result | Limit |
| --- | --- | --- |
| Starting FKA | On, visually verified, unchanged | No FKA-Off comparison. |
| Home using candidate `command-h` | One pass from the FKA Settings page; API approximately 306 ms | Not repeated, not from an active text field, not after idle, not through the real console button. |
| App Switcher using `direct-fn` | Failed; API approximately 245 ms, Home remained visible with an FKA focus outline | No app cards appeared; API completion was not a pass. |
| Further actions | Stopped at that failure | No fallback/retry, Control Centre, movement/Stop, typing, or absolute-position probe. |
| Incoming keyboard replies | Zero reports on two observed keyboard connections | Not proof of success or failure; no documented ACK expectation. |
| Restoration | Original release, console, and both receivers restored; both video streams advancing | Historical observation, not a current status query. |
| Isolation | C241 received no input; phones unowned/inactive afterward; 25 protected file hashes unchanged | Do not reuse historical PIDs as current identity. |

A still Settings page exposed a test-tool assumption: static content may not keep generating new frames. The runner can now accept an explicitly reviewed frame hash while still requiring the correct session/process/mapping/lease, and new frames after an action. One baseline attempt aborted because a clock changed the hash; it sent no key and released the lease.

Archive: `iMouseXP-2.0-evidence-archive\20261014-navigation-live`, alongside the repositories. It contains 122 files, 58,606,489 bytes, with a recorded checksum verification. Commit `11b7d29` records that archive receipt. It is a local archive, not an off-machine backup.

### Installed release to preserve

Under the original `iMouseXP-2.0` checkout:

```text
Open iMouse 2.0.ps1
release\iMouse2-two-phone-candidate\iMouse2.exe
release\iMouse2-kernel-two-phone\iMouse2.Kernel.exe
tools\airplay\uxplay\build-imouse\uxplay.exe
tools\airplay\msys64\ucrt64
analysis\two-phone-config
```

The operator shortcut is **iMouse 2.0 - Independent AirPlay**. Normal shared settings are under `%APPDATA%\iMouse2\settings.json`. Do not overwrite these binaries, configuration, shortcuts, or settings during feature development. Recheck live state before relying on any previous restoration report.

## 8. Open issues and corrected findings

| Issue | What is established | What remains |
| --- | --- | --- |
| **Home inserts a Tab** | The vendor Home sequence includes Tab before Command+H. This can alter a focused note. A candidate `command-h` variant avoids that report sequence and passed once from Settings. | Repeated checks from text editing, Settings, idle, and the actual console; verify no text mutation. Do not silently change the installed default. |
| **App Switcher** | Earlier FKA-Off trials failed. The latest candidate direct-Fn trial with FKA On also failed. | Determine the reliable sequence and focus requirements; validate visually. Do not infer success from code 0. |
| **Fresh-field space loss** | With FKA On, fresh text fields often lost the first space. A bounded FKA-Off check produced exact text in six short trials and a 100-character trial. | General reliable typing with intended accessibility settings. Mechanism is not proven. **User deferred this issue; do not resume phone typing experiments without a new decision.** |
| **Mirroring/recasting** | Receiver replacement can be ready while the phone lists nothing. Other phones sometimes see the same receiver. | A reliable observation and reconnection workflow, including unavailable video and wrong-target avoidance. No API presently guarantees a phone-side AirPlay selection. |
| **Pointer accuracy across rack** | Two phones have a historical 1,000-hit API run at one target. C24C reached lower-screen coordinates in a move-only test. | Varied targets, post-interruption behavior, actual tap results, and all required board/phone combinations. |
| **Scale and endurance** | Small-rack foundations and earlier probes exist. | Staged 4 → 8 → 19-phone validation and uninterrupted qualified 8/24-hour runs. |
| **Clean-PC distribution** | Package manifests, native staging, and symbol checks exist. A missing-video-components incident was repaired offline. | Real clean-PC dependency loading, redistributable notices, install/update/rollback verification. |

### Do not repeat or overstate these investigations

- **The six-note extra-click comparison already ran.** All trials produced `Hithere`; an extra pointer click did not solve the tested fresh-note issue. An old handoff saying this test is pending is stale.
- **FKA pass-through experiments also ran.** Prepared-field typing could become exact, including a real Send text button 100-character check, but the state did not reliably survive entering a fresh note. A yellow highlight was observed, not a verified named On/Off mode notification. FKA and the release were restored. This is not an accepted general typing fix.
- **Inline Predictions was tested On/Off/restored** with unchanged observed loss in that experiment. Do not present it as the established cause, or claim that one experiment explains every iOS keyboard behavior.
- **Intermittent console clicks remain unreproduced.** An earlier claim that shell-injected clicks proved an internal WPF fault was withdrawn: that shell path reported success without injecting mouse events. Tracing exists; no proven product fix came from that investigation.
- **Lower-screen pointer reach was demonstrated in one move-only test.** The earlier automation cursor limitation did not establish a kernel/phone reach defect. It also does not prove every lower-screen tap works.
- **One cable replug coincided with AirPlay recovery.** Charging and accessory/input state changed together. Do not label it a proven cause or unattended recovery procedure.
- **Older physical smoke results belong to older binaries.** For example, previous C24C movement, tap, swipe, Stop, and Resume checks do not validate the latest navigation changes or the full console flow.

The user wants useful forward progress without repeated, lengthy phone experiments. Prefer bounded offline implementation and meaningful tests. If a feature requires physical evidence, state exactly what remains unvalidated.

## 9. Reverse-engineering findings

The recent investigation used static analysis of vendor components plus narrowly scoped board observations. It did not replace the hardware firmware or establish a full protocol specification.

Primary records:

- `analysis/vendor-protocol-rea-20261014/REPORT.md`
- `analysis/hid-input-replies-20261014/REPORT.md`
- `analysis/re-improvements-20261014/PROTOCOL.md`
- `analysis/re-improvements-20261014/SYMBOLS.md`
- `RE-IMPROVEMENTS-PLAN.md`

| Finding | Engineering consequence |
| --- | --- |
| The Tab is part of host-side vendor Home policy. | It is reasonable to test an alternate host sequence; the board is not proven to require a leading Tab. |
| The A2 Fn field is distinct from the ordinary Shift modifier; the relevant Fn encoding includes byte 7 value `02`. | Preserve the actual report layout and test emitted bytes. A guessed modifier substitution is not equivalent. |
| A0/A1 and A5 can share an event path without a request correlation identifier. | Do not treat the next incoming report as the ACK for the last outgoing command. |
| AF counter changes appeared with successful input. | Do not turn every AF change into a board failure. Keep parsing and interpretation separate. |
| Existing reset timing already uses the observed 10 ms value. | Do not claim a new pacing fix where the implementation already matches. |
| `HT_SetIOSVer` appears to set a host-side flag. | It is not evidence of board negotiation or detected phone capabilities. |
| Vendor host code has an A0 absolute-coordinate path over 0–32767. | Board support and behavior remain unverified. The guarded move-only probe is experimental and was not run in the latest window. |
| Managed binary and symbol identity can diverge. | Pair DLL/PDB identity correctly; package validation now checks this rather than accepting filename matches. |

The inspected `MouseKeyItem.dll` has recorded hashes in the report. The protected service received limited PE inventory; it was not unpacked or executed as part of this investigation. Do not turn static-host-code observations into claims about undocumented firmware behavior.

The useful improvements are already being integrated through the normal leased command path, tests, and packaging. Raw replay bypasses lease-aware serialization and Stop; it is not an approved substitute for that path.

The existing active improvement target has **five parts**: Home without Tab, App Switcher compatibility, evidence-based movement reply/status handling, validated absolute positioning or an evidenced limitation, and matching binaries/symbols. The symbol guard is implemented and tested. Navigation alternatives and the absolute probe exist behind explicit candidate configuration, but physical acceptance is incomplete; reply handling remains observational. No ACK wait or pacing change was justified. Do not mark this overall target complete or silently discard it when starting a new feature.

## 10. Portal and automation workstreams

### Existing portal and rack agent

This work is on cached `origin/claude/focused-noether-s600e0` at `6b24a96`, not the current core branch. Read its `PORTAL-MILESTONE-1.md` and `WINDOWS-VALIDATION-HANDOFF.md` if assigned portal work.

Its recorded design uses Node.js 22, SQLite through `node:sqlite`, WebSocket communication, and a rack agent that initiates an outbound connection. It reuses kernel leases, renewal, Stop, and no-replay behavior. Authorization scopes phone/customer access, and audit records avoid storing typed text. Simulated/source-conformance checks exist; Windows physical validation remained pending in that milestone report.

Do not assume desktop fixes are automatically present in the portal. Earlier portal/rack-agent text chunk sizes were 32 and need reconciliation with the desktop’s measured 12-character policy. Remote connectivity needs the intended security and endpoint model; do not expose the local kernel publicly as a shortcut.

### Untracked automation prototype found during this handoff

These files exist in the combined checkout but are **not committed in the tested core**:

```text
IMOUSE_MARKETING_FARM_HANDOFF.md
src/iMouse.Console/FarmAutomationWindow.cs
tools/imouse_social_automation.py
tools/imouse_farm_server.py
tools/imouse_farm_command_center.html
tools/setup_imouse_farm.py
```

They describe a separate automation workstream with a local service, web command center, WPF window, SQLite state, simulator/live adapters, and account/media workflows. They were inventoried, not executed or accepted, for this handoff. The companion receipt records their hashes so later work can identify the exact files.

Important boundaries:

- Their own handoff contains claims that conflict with authoritative gate evidence and some file descriptions that no longer match the files. Treat it as a proposal needing review.
- A referenced `docs/imouse_social_automation_blueprint.md` was absent at inspection.
- No integration reference to `FarmAutomationWindow` was found in the main window files. Its presence alone is not proof of a usable integrated feature.
- .NET SDK default file inclusion can compile the untracked C# file if you build this dirty working directory. Use a clean committed feature worktree unless specifically assigned this prototype.
- Do not run its installer or live server just to learn about it. Do not start account actions, uploads, messages, purchases, or publication without the relevant user authorization.
- The Git bundle intentionally excludes these untracked files. If this is the feature work Gemini is assigned, obtain these exact source files separately and review their contracts before integrating them.

## 11. Development and testing workflow

### Start safely

1. Read the current Git status, branch, log, and worktree list. Read applicable `AGENTS.md` or other local instructions if present. None was found in the relevant core/root directories during this handoff.
2. Preserve untracked output, analysis, and prototype files. Never use `git clean -x` here.
3. Work from a clean feature worktree based on the committed combined branch. Record the base commit and the exact feature scope.
4. Prefer existing modules and harnesses. Do not rebuild the entire application or create another parallel acceptance framework.
5. Build into a new folder. Never use the installed `release\` folders as build output.

### Ordinary offline builds

Run from the feature checkout root. Replace `FEATURE` with a unique short feature name:

```powershell
dotnet build src/iMouse.Kernel/iMouse.Kernel.csproj -c Release -o output/gemini-FEATURE/kernel
dotnet build src/iMouse.Console/iMouse.Console.csproj -c Release -o output/gemini-FEATURE/console
dotnet output/gemini-FEATURE/kernel/iMouse2.Kernel.dll --self-test
dotnet output/gemini-FEATURE/console/iMouse2.dll --self-test
```

These core self-test entry points are intended for offline checks. Inspect the actual code if changing startup or tests. Read exit status and result files; do not report success because a process merely launched. Console tests write QA result/failure artifacts under the build output.

`--ui-test` uses mock input but opens a real WPF window. It can interfere with the operator’s desktop, so coordinate it. Live modes such as `--smoke-test`, `--wall-test`, `--mirror-test`, and `--fps-test` require an explicit address and are not interchangeable with offline self-tests.

Do not execute `build-console.ps1` with its historical default output merely to test a source edit: it can target an installed release directory. Test generated launcher source in scratch or use explicit safe output.

### Candidate startup and settings

Normal candidates need their own `--data-dir` and explicit `--address=http://127.0.0.1:9913` or the deliberately selected proxy endpoint. The console supports data-directory syntax with `=` or a separate value. Explicit normal-startup addresses require the isolated-directory path in the current design; inspect parsing rather than assuming older behavior.

- Set `"trackPointer": false` in candidate settings before connecting. Otherwise a passing mouse over a preview can take control and send pointer movement.
- Do not seed a candidate from operator settings without an explicit need. Do not write the adjacent legacy settings mirror.
- `--validate-startup` provides validation without opening the operator interface or starting hardware/network work.
- `tools/candidate-launcher/Start-iMouse2Candidate.ps1` has separate check, preparation, and launch behavior. Check-only is read-only; launch can contact the service and open the console. Read the script before selecting a mode.
- An isolated data directory does **not** by itself restrict a service to C24C. Identity/scope checks still apply.
- Launch and foreground a specific executable/process. Searching an app name previously opened an old, non-isolated candidate and rewrote shared settings.

### Reuse the maintained tools

| Task | Existing entry point / rule |
| --- | --- |
| Accuracy | `tools/gate4_1000_tap_suite.py`; older `tools/gate4_v2/gate4_suite.py` is a compatibility path. |
| Controls | `analysis/gate5-everyday-controls-20260916/run_controls.py`; latest one-action live runner uses explicit mode and build checks. |
| Responsiveness | `analysis/gate6-release-validation-20260916/run_gate6.py` and its tests. Extend this instead of inventing a duplicate harness. |
| Endurance | Existing `endurance_soak.py` / `analyze_endurance.py` tools; retain input failures and discontinuities, do not count duration alone. |
| Rack configuration | Existing `validate_rack_config` tool. Placeholder/structure checks are not physical identity acceptance. |
| Diagnostics | Existing export tools and unit coverage; an actual export may read a live service. |
| Binary identity | `tools/build_manifest.py` records/verifies source/build association. |
| Managed symbols | `tools/managed_symbols.py` checks actual managed identity/checksums. |
| Distribution | `tools/stage_release.py` and `stage_receiver_runtime.py`, with recorded manifests and explicit inputs. |

Use focused tests that exercise changed behavior and meaningful failure cases. Repeat or broaden testing when changes, failures, or unresolved risks justify it. A passing synthetic test is evidence for its modeled behavior, not proof of iOS behavior.

### Encoding and packaging

Some sessions used Windows PowerShell 5.1 with a GBK ANSI code page. Always read/write source and JSON with explicit UTF-8. A previous encoding round trip corrupted literals such as `·` and `未分组`.

Evidence JSONL files may require exact bytes for checksum verification; obey `.gitattributes`. Do not normalize archived records or regenerate their original measurements. Native files being present in a package is not proof that every DLL/plugin loads on a clean PC. Record both package validation and actual runtime validation separately.

## 12. Product acceptance criteria

`FINISH-CRITERIA.md` is the written acceptance contract. Read its current wording before changing a checkbox. The historical “11 of 12 gates passed” summary was not supported by the underlying files. Gates 1–2 have historical pass records; Gate 4 has a scoped two-phone result. Broader acceptance is incomplete.

| Gate | Required outcome | Present boundary / remaining work |
| --- | --- | --- |
| 1. Independence | Cold boot and operation without vendor processes/services. | Historical pass record exists. Recheck relevant changes; do not casually rerun disruptive cold-boot tests. |
| 2. One obvious app | Predictable launch, persistent settings, clear startup failure handling. | Historical pass plus later hardening. Latest package/install experience still needs appropriate acceptance. |
| 3. Identity | Every intended phone/board/receiver pair is unmistakable and persistently mapped. | Fourteen placeholders remain; guided physical verification and changed-binding behavior need completion. |
| 4. Accuracy | At least 995/1,000 single-tap hits across meaningful varied targets, with no wrong-phone input, stuck input, or double clicks. | Historical 1,000/1,000 on two phones targeted one point. Varied positions, interruption recovery, and the other pairs are not covered. |
| 5. Everyday controls | Actual console controls, correct gestures/release, exact text, and honest unsupported-action feedback. | Home, App Switcher, exact fresh-field typing, and broader console checks remain. Typing is deferred, not waived. |
| 6. Responsiveness | From console action to first correct visible response: ordinary action p95 ≤500 ms; reset p95 ≤2 s, with sufficient samples under the defined profile. | API dispatch duration is not the measurement. At least 100 per category and honest failure accounting remain necessary. |
| 7. Video | Display at least 95% of incoming unique frames up to configured cap; no >2 s freeze while valid frames arrive. | Compare received and displayed frames in the same workload/window; full acceptance still required. |
| 8. Group control | Explicit selected targets, isolation, Stop cancellation/release, no replay, unavailable members handled. | Implemented safeguards need the full physical group acceptance workload. |
| 9. Recovery | Bounded retries/exhaustion, process/input cleanup, useful status, and reconnection. | Offline coverage is stronger; physical rediscovery/recasting remains unreliable. |
| 10. Endurance | Uninterrupted qualified eight-hour run, then 24 hours, with working interactions and resource budgets. | An old eight-hour duration included failed interactions/discontinuities. It is not final endurance acceptance. |
| 11. Full rack | Staged 2 → 4 → 8 → 19-phone validation. | Five bindings/probes do not establish a validated 19-phone rack. |
| 12. Release | Useful diagnostics, repeatable builds, dependency notices, clean-PC install, update and rollback. | Tooling is substantially improved; clean-PC and operator release verification remain. |

The intended progression is **correct targeting → reliable recovery → consistent speed → scale → endurance**. Do not weaken the criteria to fit current results.

The historical Gate 4 API runner is valid within its scope; that gate does not require GUI clicks. Gates 5 and 6 do require the relevant actual-console behavior. Its 18 isolation flags were attributed by the audit to a harness baseline race, but the exact executed harness version was not preserved; pointer resets were inferred, not recorded. Carry those limits forward.

## 13. Where to implement new features

The user is handing Gemini the project to build features, but this handoff does not select a specific new feature. Confirm the assignment, inspect its existing implementation, and make a narrow plan before editing.

| Feature family | Start here | Important constraints |
| --- | --- | --- |
| Desktop usability/status | WPF main window, phone wall, input state, diagnostics modules | Show connection, video freshness, ownership, and paused/uncertain state distinctly. Keep implementation jargon out of ordinary operator flows. |
| Reconnection assistance | Receiver supervision/status plus a phone-side selection workflow | Match the intended receiver name; never use a fixed row that may be a TV. Plan how to observe the phone when mirroring itself is unavailable. |
| Identity/onboarding | `DeviceStore`, rack validation and existing guided-identification work | Do not overwrite live bindings or invent board/phone pairs. Offline UI can be built before physical binding. |
| Controls | `InputControls`, `InputLeaseClient`, kernel routing and HID protocol | Preserve Stop, leases, serialization, release, and uncertainty. New reports need emitted-byte tests and separately authorized physical checks. |
| Performance/video | Frame modules, receiver lifecycle, existing timing runner | Bound work/buffers; measure correct visible outcomes and failures, not just API latency. |
| Release experience | Startup, manifests, diagnostics, staging/runtime tools | Keep the installed release untouched. Fresh-PC validation cannot be claimed from this developer machine. |
| Portal | Portal/rack-agent branch and its Windows handoff | Reconcile contracts and chunk policy; retain authorization and no-replay behavior. |
| Automation prototype | The six untracked files in section 10 | Review and snapshot separately before adoption. No automatic inclusion in accepted core or live account activity. |

Useful offline work includes source fixes, unit/contract tests, bounded resource handling, diagnostics, UI implementation without interacting with the desktop, package verification, and documentation. Final visual/hardware acceptance may still require the operator. Do not repeatedly ask for approval for already authorized routine offline work, but do not treat past timed test windows as permanent control authorization.

## 14. Live-test operating rules

This document grants no fresh live-test window. The default for Gemini onboarding is **offline work with no desktop control**.

For a later explicitly coordinated window:

1. Confirm the user is available, other agents are idle for the target, and the exact scope/build is agreed. C24C only unless the user explicitly expands it. No input to C241.
2. Recheck process paths, build hashes, phone/board/receiver identity, ownership, and active commands. Do not trust historical PIDs or take control from another active controller.
3. Prepare isolated settings, an explicit endpoint, hover tracking off, evidence capture, and restoration before interrupting anything. Preserve protected configuration/settings hashes without logging private contents.
4. Use normal leased commands. Do not use raw HID replay, undocumented control bypasses, or a retry that can duplicate uncertain input.
5. Coordinate any kernel/receiver swap separately: it interrupts mirroring and may require physical recasting. Do not silently restart services, toggle Wi-Fi/FKA, unplug cables, or rely on a fixed screen coordinate to select a receiver.
6. Run the bounded checks; stop on the defined failure. Record command completion and visible outcome separately. No dummy spaces or hidden timing/mapping changes to conceal a defect.
7. Release the lease, close candidate/proxy/tools, restore the original release/configuration and agreed FKA state, verify both intended video streams, and report any restoration failure immediately.

The user has deferred the second-PC/VM setup and typing investigation. Do not revive either as a prerequisite for unrelated feature work. Never promote, deploy, overwrite the installed release, or modify its launcher without explicit authorization. Do not push the sensitive backup branch. Publication or external account actions need their own authorization.

## 15. Evidence and reference documents

### Read in this order

| Document | Use |
| --- | --- |
| This handoff | Current map, boundaries, and code entry points. |
| `RESUME-NEXT.md` | Latest checkpoint and immediate unresolved work. |
| `RE-IMPROVEMENTS-PLAN.md` | Integrated reverse-engineering improvement status. |
| `analysis/navigation-live-20261014/README.md` | Latest physical outcomes and restoration. |
| `FINISH-CRITERIA.md` | Written acceptance requirements. |
| `KEYBOARD-SPEC.md` | Keyboard behavior, limits, and history; reconcile with later reports. |
| `HANDOFF.md`, `ACCOUNT-HANDOFF.md`, `ORCA-RETURN-HANDOFF.md` | Historical continuity and cross-branch preservation. They can contain superseded “next task” statements. |
| `analysis/HARDWARE.md` | Hardware context and mappings; verify current identity before input. |
| `analysis/finish-criteria-audit-20260916/GAPS.md` | Earlier gate reconciliation; newer evidence may extend it. |

When records disagree, use the exact source revision and raw evidence for the stated claim, then update the summary. A recent date alone is not proof. Distinguish **observed**, **inferred**, **simulated**, **untested**, and **deferred**.

### Archives and privacy

The local evidence archive is beside the repositories:

```text
C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-evidence-archive
```

Recent records include `20261014-re-improvements`, `20261014-navigation-runner`, and `20261014-navigation-live`, with recorded checksums. The older `iMouseXP-2.0-handoff-backup-20260928` does not automatically include October evidence. Same-disk copies are preservation, not protection against disk loss.

Some screenshots and logs are Git-ignored. Do not remove their worktrees or run broad cleanup before verified archival. Keep run records byte-identical where checksums depend on them. The source bundle excludes output binaries and raw archives; consult the reports for the evidence needed for a particular feature.

Vendor install copies may contain stored credentials. Reports and captures may contain personal identifiers or phone content. The local pre-redaction backup branch contains a withheld identifier and must stay local. Before any later publication, review the exact proposed files/history rather than assuming an earlier scan covers new material.

## 16. First-session checklist and completion expectations

Gemini should begin with a brief, concrete statement of:

- The checkout/worktree, branch, and exact base commit it will use.
- The requested feature and the existing modules/tests it will extend.
- Any untracked or concurrent work it will preserve.
- Which checks it can complete offline and which acceptance evidence would require a coordinated window.

Then proceed with authorized offline implementation. Do not restart finished investigations, write another parallel harness, or mark a gate complete merely because the code compiles.

For each delivered feature, provide:

1. The operator-visible behavior and why it helps.
2. Focused code changes and tests, including relevant failure/cleanup cases.
3. Exact source/build identity and reproducible validation commands/results.
4. Clear remaining limits: mock versus physical, API versus console, one phone versus rack, tested versus deferred.
5. A concise record of changed files and a reviewable commit or patch, without merging/promoting/pushing beyond authorization.

The user should not need to relay status between agents. Keep a concise checkpoint in the existing project records so another engineer can resume, preserve evidence, and keep the installed app usable while the new features are developed.
