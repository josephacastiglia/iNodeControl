# iNodeControl / iMouse 2.0: Durable Project Progress Record

- **Updated:** 14 October 2026
- **Latest session:** Codex; resumed the saved Omp/Orca and Claude work
- **Repository:** `https://github.com/josephacastiglia/iNodeControl`
- **Local Root:** `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0`
- **Active Worktrees:**
  - Combined candidate: `../iMouseXP-2.0-combined-candidate`, branch `local/combined-candidate-20261012`; authoritative for the current offline repairs
  - Main Checkout: `local/coordinator-work` (`01fb669`, with the 10 October harness changes uncommitted)
  - Integration: `.claude/worktrees/keyboard-spec-reconcile` (`claude/input-timeout-integration`, `d0c4ccf`)
  - Gate 4 v2: `.claude/worktrees/gate4-harness-v2` (`claude/gate4-harness-v2`, `2c98f44`)
  - FKA probe: `../iMouseXP-2.0-fka-passthrough-probe` (`local/fka-passthrough-probe`, base `d0c4ccf`, isolated source changes uncommitted)

## Reverse-engineering improvements integrated offline, 14 October

Offline follow-up: updated the existing Gate 5 runner for one explicitly selected
C24C navigation action with candidate/hash/lease checks, partial evidence and
safe cleanup. Its default performs no network calls. All 26 fake-API checks pass;
three removed-guard controls fail as intended. Historical results and candidate
binaries are unchanged. See `analysis/re-improvements-20261014/NAVIGATION-RUNNER.md`.

The user explicitly set the five-item target in `RE-IMPROVEMENTS-PLAN.md`.
Source commits `457f80d` and `373dd58` add managed DLL/PDB pairing protection,
direct Fn navigation choices, a strictly move-only A0 capability probe, and
console compatibility/reply diagnostics. Existing command-h Home is reused.
Defaults and installed files remain unchanged. Physical functionality is not
established by the new options; the goal remains active.

The final source builds cleanly and passes 290 kernel and 411 headless console
checks. Packaging has 74 checks, three disabled-guard controls and two separate
protocol guard-removal controls. `combined-re-improvements-20261014` preserves
698 verified entries, including unchanged native dependencies and matching
managed symbols. Its unused C24C profile validates without a window, listener,
receiver or phone input. Read `analysis/re-improvements-20261014/REPORT.md`.

New vendor evidence: A5 and A0/A1 signal the same host event; AF affects a 10 ms
reset delay, already present in our reset. No correlated ACK, automatic pacing
change or retry is justified. Absolute firmware support is unknown. Home and
App Switcher still require physical/real-console acceptance; typing stays
deferred. A navigation window was requested; recheck the user's answer before
any interruption. No live work ran in this implementation checkpoint.

## Incoming board replies validated on C24C, 14 October

Two bounded pointer-only checks through the unchanged release API captured 25
reports (23 A1 and two AF) from a separate read-only C24C handle. Both runs
released their leases and confirmed unchanged C241 state, release processes and
four protected file hashes. No clicks, typing, FKA change or restart occurred.
The installed PDB was stale; the actual DLL transport was audited before capture.

The combined source now has opt-in, board-scoped reply counters/state in kernel
status and diagnostic export, default off. Replies never gate/retry writes and
are not treated as iOS success. The kernel passed 245 tests; the shared capture
reader passed 30 overlapping checks plus six argument cases, and Python passed
23 export plus three capture-guard tests. The full new kernel is offline-tested;
the existing immutable package remains unchanged. Read
`analysis/hid-input-replies-20261014/REPORT.md` for scope, evidence and limits.

## Original vendor protocol investigated offline, 14 October

REA 6.5.0 and Ghidra decompiled 27 targeted functions from a hash-verified copy
of the original `MouseKeyItem.dll`. The investigation resolved the separate Fn
field, traced the generic Tab prelude, and identified movement/identifier reply
handlers plus an unvalidated absolute-coordinate path. The new saved-packet
decoder passes 13 offline tests and parses 221 historical output reports;
14 independent static checks verify cited DLL offsets. Read
`analysis/vendor-protocol-rea-20261014/REPORT.md` for provenance and limits.

No vendor code, device handle, rack API or desktop control ran. Product sources
and staged binaries are unchanged; no physical defect or release gate is closed.
Raw evidence and target copies are preserved outside the repository. The next
protocol step is controlled validation of incoming reports before adding reply
handling; typing/FKA remains deferred.

## Latest combined timing candidate preserved, 13 October

`output/staging/combined-timing-20261013` now includes the latest console response timeline and actual-service hint with the preserved shutdown kernel. All 692 inventory files and embedded source/runtime records verify; the 610 native entries and previous package are unchanged. Both exact binaries pass no-window validation in a new isolated, hover-off C24C-only preparation, followed by the strict launcher and saved-profile checks. Read `analysis/combined-timing-package-20261013/REPORT.md`.

No app window, service, receiver or phone input started. This C24C-only smoke profile is not the two-stream Gate 6 workload. The exact package and unused run are archived separately with hashes; no physical release gate advances from this preparation.

## Candidate isolation and actual connection verification, 13 October

The existing Gate 6 runner now refuses unsafe ownership, wrong/stale receiver identity, missing second-phone streaming, mismatched candidate binaries/profiles and observer-phone activity. UIA requires the exact dedicated candidate and checks its actual connected service and hover-off state before actions. The console now exposes its active service origin through its connection tooltip/accessibility hint, clearing it during disconnect/reconnect/failure.

All 89 runner, 20 diagnostics and 409 headless console checks pass; five unsafe preflights fail on the old runner. Both generated helpers parse without execution. All 25 protected installed file hashes match the baseline. See `analysis/gate6-preflight-20261013/REPORT.md`. No screen control, live rack requests, phone input or release acceptance ran; snapshots do not establish continuous exclusivity or physical identity.

## Timing-runner console cleanup prepared offline, 13 October

The Gate 6 runner now treats an incomplete UIA reply as possible console ownership and attempts normal Disconnect once during finalization. Both explicit console completion and read-only target release status are needed for confirmed cleanup. Process identity includes the exact executable and creation FILETIME, checked within every helper. Failed or unavailable cleanup never triggers forced release, input replay or automatic reconnect. Original trial failure and cleanup uncertainty are recorded separately.

All 65 offline checks pass, with six initial cases failing on the prior runner, plus syntax-only parsing of both generated PowerShell helpers. No UI control, phone requests or new product build ran. See `analysis/gate6-console-cleanup-20261013/REPORT.md`. Desktop execution and isolation/preparation requirements remain open; the combined package remains unchanged.

## Console response timeline implemented offline, 13 October

An opt-in, bounded in-memory timeline now records console input-dispatch/command phases and successful selected-preview bitmap updates on one monotonic clock, with phone/epoch and receiver frame identity. It is included in the existing diagnostic export; it records no pixels, text payloads or lease tokens. The existing Gate 6 runner can analyze that export offline, rejects dropped/inconsistent events and does not infer correctness or physical display latency.

402 console checks, 56 preview/timing checks and 44 Python runner checks pass, plus the runner self-check and actual headless-console export/readback. Counts overlap for shared recorder cases. No native window, rack request, phone input or screen control was used. See `analysis/response-timing-20261013/REPORT.md`. The new standalone console is not yet in the immutable combined package below. Gate 6, live instrumentation overhead and physical release acceptance remain open.

## Timing-runner failure handling repaired, 13 October

The existing Gate 6 runner now stops on visual misses even when the API command succeeded, records renewal failures before any action, and cleans up known API tokens after partial acquisition. Run/cleanup records distinguish confirmed, unknown and unmanaged outcomes. Existing run folders and neighboring run evidence cannot be overwritten. All 35 offline tests and its self-check pass; ten initial new cases fail on the saved old runner. See `analysis/gate6-failure-handling-20261013/REPORT.md`.

This is tooling work only. It does not measure the console's actual presentation path, add missing correctness classifiers or release console-owned leases. No rack calls, screen control or phone input ran. The packaged candidate below is unchanged; current-build physical acceptance, scale/endurance and release clearance remain open.

## Latest combined review package prepared, 13 October

`output/staging/combined-shutdown-20261013` now brings the fleet shutdown kernel and screenshot-client console repair together. All 689 inventory entries, embedded source records and native runtime verify; 610 receiver/runtime entries are unchanged from the prior package. A fresh unused C24C-only run at `output/candidate-runs/shutdown-20261013` passes both offline startup validations and the final launcher check, with isolated settings and hover tracking off. No window, service, receiver or phone was operated. See `analysis/combined-shutdown-package-20261013/REPORT.md`. The earlier package and pause archive remain intact. Physical acceptance and release clearance remain open.

## Receiver fleet shutdown joined and failures surfaced, 13 October

Work resumed at the operator's request. After repairing its fixture lifetime, the saved draft reproduced all five suspected lifecycle defects against the old source. The fleet now waits for disposal already in progress, starts peer cleanup independently, joins supervisor/frame tasks, shares shutdown completion and reports unconfirmed cleanup by receiver. Startup after disposal or a second Start is refused. The kernel closes API/input sessions before awaiting fleet shutdown and reports failure instead of success when cleanup is unknown.

All 41 recovery, 207 kernel, 34 frame and 14 fake receiver-lifetime checks pass. Exact source/builds and limits are in `analysis/fleet-shutdown-20261013/RESUMED-REPORT.md`. No live receiver, rack request, screen control or phone input was used; installed static hashes and settings match the restoration baseline. The combined review package above preserves this kernel for later acceptance.

## Historical pause for operator shutdown, 13 October

At the earlier shutdown checkpoint, all completed changes were saved on `local/combined-candidate-20261012`, with an unexecuted draft preserved separately and the ordinary recovery suite restored. That checkpoint and its archive remain intact. The later resume and repair above supersede its paused status. Start future continuation with `RESUME-NEXT.md`.

## Console image downloads bounded and buffer growth repaired, 13 October

The preview reader previously stopped enforcing its HTTP timeout after headers arrived. A simulated stalled body outlasted eight seconds and needed the test's 13-second escape. Unknown-length images over the initial buffer size also lost their first bytes during growth. The reader now keeps one eight-second deadline through the entire response, preserves the received prefix and enforces a 64 MiB response limit, clearing partial evidence on failure.

The old source fails six of eight added transfer cases; all **44 preview checks, 22 wall checks and 382 console self-tests pass** after repair. An explicit local HTTP probe confirms body timeout at about eight seconds, a clean HTTP-503 failure and exact recovery through a larger chunked response. No real service, desktop or phone was operated. Sandbox restrictions on localhost access and temporary file replacement were recorded; the bounded offline verification succeeded after permission review. See `analysis/screenshot-client-20261013/REPORT.md`. This is a separately recorded console build; the package below remains unchanged and does not contain this later repair. Actual display/physical acceptance remains open.

## Accumulated recovery repairs packaged and prepared offline, 13 October

`output/staging/combined-recovery-20261013` now preserves the latest kernel, unchanged console/receiver/runtime and the launcher's error-reporting source as inert text. Its 689-file inventory, embedded source provenance and native-runtime checks pass; 615 console/receiver/runtime entries are byte-identical to the previous package. All 28 packaging checks pass, including six new launcher-source preservation checks. Nothing was installed or launched on the rack.

A fresh C24C-only run at `output/candidate-runs/recovery-20261013` passes both binaries' saved-configuration validation and the candidate launcher's final `-CheckOnly`. Preparation exposed an old problem: console validation writes a report beside its executable, causing the strict launcher to reject the intended run. The new script validates a separate byte-identical copy and leaves the prepared run pristine. It uses package-contained source/build records, an explicit address, isolated settings and hover tracking off. Installed files, operator settings and source configuration remain unchanged. See `analysis/consolidated-package-20261013/REPORT.md`. Physical candidate acceptance, clean-PC loading and release obligations remain open; no gate advanced.

## Receiver exit and partial-start cleanup confirmed, 13 October

The candidate now waits up to five seconds for the receiver root to exit before disposal succeeds. Startup owns its child even if attaching stdout/stderr fails; confirmed cleanup permits the usual bounded retry, while unconfirmed cleanup preserves both errors and blocks every replacement. The original behavior failed eight of nine initial fake-process cases. **14 deterministic lifetime cases, six real hidden-child cases, 29 recovery/logging checks and 207 kernel checks pass.** All six final helper exits were verified from retained handles. No rack process, receiver, API, desktop or phone was operated.

The first real-test runner had a cleanup-scope bug; that run is retained and not accepted. Two deliberately unconfirmed children had a 20-second failsafe; a later process inventory was empty. The corrected runner explicitly cleans all helpers and requires matching created/exited inventories. Process-tree termination remains requested, but the wait attests the receiver root only, not all descendants or phone rediscovery. See `analysis/receiver-process-cleanup-20261013/REPORT.md`. Installed files are unchanged; this is another separately recorded scratch kernel, not a promotion or gate sign-off.

## Receiver retries retain accurate counts and failure reasons, 13 October

The supervisor no longer reports a phantom retry at exhaustion or counts a wait cancelled before replacement. It retains the latest startup/wait failure, preserves an exhausted failure during disposal, and keeps a clearly labelled last known PID when cleanup fails. Nine focused cases now cover these paths; seven of the first eight failed on the old product. **29 recovery/logging checks and 207 kernel checks pass**, including status serialization. No rack API, receiver, desktop or phone was operated. The kernel is a separate scratch build, not a replacement of the previously tested package. See `analysis/receiver-retry-status-20261013/REPORT.md`.

Next offline recovery boundary: verify actual child-process exit before replacement. `AirplayProcess.Dispose` currently requests termination without an explicit confirmation wait, and partial startup cleanup needs review. These are source findings, not a proved cause of phone rediscovery failures. No gate advanced.

## Stalled screenshot clients no longer block frame delivery, 13 October

Reproduced a delivery-lock stall: the old screenshot path performed synchronous network output while holding the producer/status lock. The added test failed before repair. The kernel now captures a matching image/metadata snapshot into a pooled copy under the short lock and sends it asynchronously outside the lock. Two transfers per phone may retain copies; excess requests get HTTP 503 with a retry hint. Each transfer has a five-second deadline and responds to request/store cancellation. Buffers are returned only after writers finish, preventing reuse while bytes are still being sent.

**34 frame tests and 206 kernel self-tests pass**, plus all nine existing mock input-cleanup scenarios. A real loopback probe with two readers that stop consuming their 12 MiB image bodies keeps publishing frames, cancels both responses at about 5.06 seconds and then serves the correct new image. A deliberately aliased-buffer build fails the new byte/metadata integrity check (33/34). The fixed kernel/source manifest is recorded separately; it has not run against phones or been placed in a replacement release package. No rack API, receiver restart, screen control, FKA change or C241 input occurred. See `analysis/screenshot-backpressure-20261013/REPORT.md`. Full-rack load, physical display and live recovery acceptance remain open; no gate advanced.

## Launcher preserves startup refusals, 13 October

The candidate launcher now retains its own kernel's stderr in a separate file per start and includes the refusal in its early-exit message. This exposes the missing-plugin names instead of losing them behind a connection error. Error text is bounded in the message; full files remain preserved. A missing Windows PowerShell exit code is explicitly unknown, and timeout messages identify a possibly still-running process without killing or relaunching it. Failed saving of the latest failure report no longer hides the original message.

**47 offline launcher checks pass in each PowerShell runtime**, including existing identity checks. The real guarded kernel's validation-only refusal is captured in both runtimes; a deliberately stripped-diagnostic copy fails the intended checks. Synthetic children preserve redirected errors across parent exit. No installed file, managed binary, review package, service or phone was changed; no real API, UI or live-startup acceptance occurred. The root launcher source still needs inclusion in a future approved release assembly. See `analysis/launcher-startup-errors-20261013/REPORT.md` and its exact scope/limitations. No gate advanced.

## Repaired candidate starts and mirrors; API smoke recorded, 13 October

The operator authorized a second C24C-only window. The guarded candidate kernel and repaired receiver runtime started successfully, received 6,715 frames and had zero receiver restarts. Upper/lower pointer moves, opening Calculator, left/right Home-page swipes and API Stop/Resume/release passed their small smoke checks. Stop acknowledged in 4.15 ms; this is not measured physical release latency. A bottom-edge upward swipe returned code 0 but did **not** return Calculator to Home; that visible-effect failure is preserved, and the operator returned Home physically. No retry was substituted for the failure.

The candidate console was not opened: these results do not close console-button, timeout-notice, diagnostic-export or latency acceptance. No typing, FKA changes or C241 input occurred. Candidate processes stopped gracefully; the original launcher restored the release. At **05:08:09 UTC**, both original receivers were live, zero restarts; both phones were free/inactive at generation 0. Installed/settings/configuration hashes are unchanged. C241 had initially been left disconnected and the operator connected it; no missing-name report in this retry restoration. See `analysis/candidate-retry-20261013/REPORT.md`, visual review and final restoration record. No gate advanced; startup is now tested for this exact package, and it should not be rerun without a relevant reason.

## Incomplete receiver runtimes refused before startup, 13 October

The kernel now checks the scanner and all eleven startup/pipeline plugin files for presence and nonzero length before normal startup can open hardware, bind a listener or start a receiver. It names missing files and asks for dependency-package repair. The check also applies to `--validate-startup`; external frame-pipe hosting still needs no local runtime. This is file validation, not native DLL loading or dependency attestation.

**206 kernel checks pass**, including 27 new checks. The old kernel accepts the actual broken runtime in its validation mode; the guarded kernel refuses it with all six missing plugins named, and accepts the repaired runtime. The new tests fail on the old product. A fresh review package and isolated C24C-only run are recorded under `analysis/runtime-startup-guard-20261013/`. Console, receiver and repaired runtime bytes are unchanged. No service/window/hardware input was started in this offline follow-up. Physical candidate acceptance and recasting reliability remain open; no gate was advanced.

## Candidate window: runtime startup repaired, 13 October

The user explicitly authorized the C24C-only API window. The candidate kernel started, but the reduced receiver runtime omitted UxPlay's mandatory playback/autodetect plugins and its audio pipeline plugins. The receiver exhausted its initial start plus five retries before video; no phone input or candidate console test occurred. The candidate was stopped gracefully and the original launcher restored the release. Both phones were confirmed mirroring at 04:31 UTC, unowned and generation 0. C241 initially did not list its receiver, then reappeared without another restart or setting/cable change. Installed/configuration/settings bytes are unchanged; ordinary release receiver logs grew.

The runtime audit now seeds six additional plugins. A new bounded **offline production-renderer startup check** fails with the old runtime and passes with the repaired one using exact preserved renderer source, without server/discovery/HID code. Ten audit tests, 22 runtime-staging tests and nine probe-helper tests pass. The 132-file runtime preserves the previous 126 binary hashes and all 104 supplemental provenance/notice files. Added files match two signed local package archives; the extra gst-plugins-good notice/source gap remains explicit.

`output/staging/combined-runtime-startup-final-20261013` contains 686 verified files plus its manifest; both standalone verifiers pass. Its console/kernel/receiver executables are unchanged. A fresh C24C-only run is prepared at `output/candidate-runs/runtime-startup-20261013`, with isolated hover-off settings and both no-hardware startup validations passing. It is **not launched or physically accepted**. The failed package and all attempts remain preserved. See `analysis/candidate-live-20261013/REPORT.md`, preparation, final restoration and archive records. This turn made packaging/regression/restoration progress; no gate was advanced. The next live dependency is confirming the repaired receiver starts and then completing the existing short API smoke checks. Typing remains deferred; no C241 input or FKA changes.

## Retryable scope release, 12–13 October

Reproduced a lost-release recovery failure: the client discarded its token before the reply, so Resume could not finish releasing a still-owned phone. The test transport also omitted the real kernel's refusal to resume while owned; that simulation is corrected. Scope release now retains unconfirmed ownership, shares duplicate attempts, releases independent phones together and applies replies only to the original token/lifetime. Normal close and explicit Resume can retry their own release; input is never replayed.

**382 console checks pass**, including ten new checks. The original product fails the new Resume test, and a separate copy with the stale-token guard removed fails the newer-Stop test. Exact source/output records, a 677-file review package and a prepared but unlaunched C24C configuration are under `analysis/scope-release-20261012/`. The kernel/receiver/runtime and installed content hashes are unchanged. These are offline lifetime checks, not physical recovery acceptance or a claim that every delayed UI notice ordering is verified. See its `REPORT.md` and verified 852-file archive receipt.

The 13 October 00:05 local process/listener check found the rack stopped (zero relevant processes and zero port-9913 listeners). The user subsequently authorized the C24C window; its startup failure, repair and restoration are recorded above. This earlier offline preparation does not imply physical acceptance.

## Cleanup history in one diagnostic export, 12 October

The real Export diagnostics collector now reads both bounded cleanup receipts from the active profile, including after Disconnect has cancelled the old connection token. It preserves historical timestamps and confirmation scope, reports missing/invalid/unreadable sections independently, and strips unknown fields, URL credentials and raw errors. No current phone state is inferred from an old receipt.

**372 console self-tests pass**, including 24 new checks and a window-collector test with no shown window/native handle or network access. A separate copy with the active profile deliberately omitted fails the intended check. The exact console is recorded with 36 source inputs and five output files. `output/staging/combined-cleanup-diagnostics-20261012` contains 677 files plus its manifest and reuses the unchanged kernel, receiver and runtime. See `analysis/cleanup-diagnostics-20261012/REPORT.md`, its preparation and verified 808-file archive receipt. The real export dialog and physical candidate acceptance remain pending. Installed hashes are unchanged; typing remains deferred.

The subsequent scope-release reproduction and repair are recorded above. Do not repeat the completed export/package checks without a change.

## Exact candidate acceptance preparation, 12 October

The consolidated review package now has a separate prepared C24C-only kernel configuration and hover-off console profile. Both exact binaries pass their actual no-window startup validation modes. Saved configuration, kernel files, isolated settings and installed hashes are unchanged. No service, receiver or app window was started. See `analysis/candidate-acceptance-20261012/REPORT.md`, `preparation.json` and `docs/CANDIDATE-ACCEPTANCE.md`.

The acceptance guide retains the written thresholds and identifies the remaining physical window, scale and endurance work. Gate 4's narrative now points to the already consolidated harness; no gate checkbox changed. A fresh read-only process/listener check confirms the rack is still stopped. Live candidate acceptance therefore remains pending, typing stays deferred, and the installed release is untouched.

## Native package notices and provenance, 12 October

The runtime stager now includes package-listed notices under `share/doc` and verifies its receipt/count summaries. All 91 exact cached binary packages have valid signatures against the selected local public keyring; 229 payload/notice members match the staged bytes. Twenty-two signed source archives have recipes matching the binary build metadata. Fifty-five supplemental source notices cover all 23 remaining local-notice gaps, without erasing those gaps or claiming complete distribution clearance.

**58 tooling checks pass.** Product/runtime binaries and source are unchanged. A reproduced standalone-verifier cache-write defect is also fixed; checking a package leaves its bytes unchanged. The new `output/staging/combined-runtime-provenance-final-20261012/` package adds notices, provenance and updated preparation guidance; it remains review-only and unlaunched. See `analysis/runtime-provenance-20261012/REPORT.md` and its preservation receipt. Physical acceptance, clean-PC loading and complete release obligations remain open. Next: exact candidate configuration and acceptance preparation; typing stays deferred.

## Awaited disconnect, reconnect and close, 12 October

The console now waits for retired clients to finish bounded, ownership-scoped cleanup. A release already in flight remains tracked after its token is detached; failed or missing confirmation is recorded rather than mistaken for success. Rapid reconnect activates only the newest client after prior cleanup. Normal window close and test exits await cleanup, with isolated atomic receipts and visible warnings for unresolved normal closure.

**348 console checks pass**, including 34 new checks and actual window-lifecycle tests that never show a window or create its native handle. Both deliberately broken copies fail the intended checks. See `analysis/input-cleanup-20261012/REPORT.md`. The latest console, unchanged kernel and preserved native runtime are consolidated in `output/staging/combined-input-cleanup-20261012/`, review-only and unlaunched. Installed hashes remain unchanged; no hardware gate was advanced. The 717-file external archive verifies. A subsequent read-only process/listener check at 22:39 local found the rack software stopped; nothing was started. Next: native-runtime notice/provenance gaps and offline acceptance preparation, without resuming the deferred typing investigation.

## Drag lifetime and complete-action ordering, 12 October

Each drag now owns its pending coordinate and release state. A newer press cannot reset the older stroke; final coordinates are published before mouse capture is released. Complete console input actions are ordered through button-up, so a following drag, tap or key cannot interleave inside a held stroke. Stop and Resume remain outside that queue, and every queued action retains its original cancellation context. Failed owned input reports later queued work as not sent; the pause notice's own cancellation does not disguise the timeout.

**314 console self-tests pass**, including 25 new checks. Two separate negative builds fail the intended ordering/final-coordinate checks. Exact source/build evidence is in `analysis/drag-ordering-20261012/REPORT.md`. No window or hardware test ran, and no installed file changed. Next: audit asynchronous console-client disposal on disconnect/reconnect/close, including whether cleanup completion is observed before the app exits.

## Hover queue ordering and cancellation, 12 October

The console now captures coordinates, mirror targets, client and cancellation tokens in one request. Its hover pump atomically coalesces pending moves and goes idle, prevents an old scope's failure from dropping a new phone's work, and clears unsent hover before a gesture or when tracking is disabled. Dispatched moves retain the existing ownership queue; no fixed drag delay or automatic retry was added.

**289 console self-tests pass**, including 18 new checks. Two deliberately broken scratch copies fail the intended new checks. The exact console component and isolated, unlaunched preparation are recorded in `analysis/pointer-queue-20261012/REPORT.md`. This addresses source-level races, not a claimed reproduction of an earlier physical pointer incident. No UI or hardware test ran. Next: audit the drag worker's shared pending/release fields and delayed capture of control lifetimes with simulated input.

## Unsupported service actions, 12 October

The console now disables live binding, remote casting and board-restart controls for its ownership connection, shows the supported setup/mirroring path, and blocks stale action requests locally. Auto-bind no longer mistakes the kernel's refusal for a cable or pointer failure. Explicit legacy/test behavior and supported input paths are retained.

**271 console self-tests pass**, including 15 new service-policy checks. A deliberately unguarded copy fails the expected transport check. Five prepared UI checks are compiled but unrun; no window or hardware was used. The exact tested console component and isolated preparation are recorded in `analysis/binding-policy-20261012/REPORT.md`. The prior full review package retains its older console. Next: reproduce and repair any unsynchronized hover-pump lost-update or stale-target interleavings with fake transport.

## Atomic preference and binding saves, 12 October

Console preferences are now replaced from a complete, flushed sibling file. Primary-save failure preserves the old file; failure of the separate launcher copy is reported as a partial save. Isolated profiles and the legacy optional-hover setting remain unchanged. DeviceStore publishes new bindings only after saving successfully; the ownership API still disables live rebinding.

**256 console self-tests and 179 kernel self-tests pass**, including 30 new persistence checks. Separate deliberately broken copies fail the intended regression checks. The launcher preparation result now reports successful preparation accurately; all 49 launcher checks pass in each PowerShell runtime. Exact builds and a new immutable 555-file review package are recorded. Installed binaries and operator settings hashes/timestamps are unchanged. See `analysis/persistence-20261012/REPORT.md`. Next: binding controls must reflect the ownership kernel's disabled live-binding capability rather than offering commands it refuses.

## Kernel startup checks, 12 October

The combined kernel rejects invalid startup options/configuration before hardware work, including malformed timing, duplicate/null records and input-enabled boards without explicit receiver bindings/calibration. Its new `--validate-startup` reads saved configuration and exits without boards, sockets, frame pipes, receivers or settings writes. Normal startup claims the HTTP endpoint before board enumeration and receiver startup.

**167 kernel self-tests, seven actual validation-mode checks and all nine cleanup-harness scenarios pass.** Separate negative controls reintroducing silent timing fallback or pre-bind receiver startup failed the intended checks. Final build/source bytes are recorded, and a new immutable review package pairs the kernel with the existing combined console/runtime. Installed hashes remain unchanged. No physical gate was passed. See `analysis/kernel-startup-20261012/REPORT.md`. The persistence follow-up is completed above; the live binding API remains disabled.

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
