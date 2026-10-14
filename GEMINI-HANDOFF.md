# iNodeControl / iMouse 2.0 — Gemini handoff

Prepared 14 October 2026 for the next engineering session. Use this document to
continue the existing project, choose useful work and preserve its evidence.
This is a development handoff; it does not approve installation or a live test
window. Product/source baseline: `897f8981b33efd23785164a34f83aa8a7cde888e`.
The commit adding this document changes documentation only.

## 1. Start in this folder

Open this existing local checkout:

```text
C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-combined-candidate
```

Use branch `local/combined-candidate-20261012`. Its latest implementation commit
is `250e589`; `897f898` records the verified archive. Tracked files were clean
before this handoff. There are many intentional untracked build/evidence folders.
Preserve them. Inspect the checkout again before editing because another session
could have worked since this snapshot.

Repository: <https://github.com/josephacastiglia/iNodeControl>.
**The October combined candidate is local-only. A GitHub clone is insufficient
to recover this work.** The locally recorded `origin/main` is the old `ee445d7`
import; it is not the development starting point. No remote refresh or push was
performed for this handoff.

If Gemini runs on this PC with filesystem/tools access, work in the folder above.
If Gemini is a web-only or remote session, it needs the actual source and selected
evidence transferred first. Reading this document alone does not give it access
to the PC, phone APIs or latest source. Do not upload a whole checkout or backup
indiscriminately; local vendor/account material is excluded from Git deliberately.

Read these files in order, relative to the combined checkout:

1. `GEMINI-HANDOFF.md` — orientation and working boundaries.
2. `RESUME-NEXT.md` — exact package and continuation checkpoint.
3. `WORK-REMAINING.md` — concise remaining areas plus completed offline tasks.
4. `FINISH-CRITERIA.md` — authoritative release requirements.
5. `PROGRESS.md` — evidence and historical context; newer dated entries supersede
   older statements that work is pending or uncommitted.
6. `docs/CANDIDATE-ACCEPTANCE.md`, `docs/RELEASE-STAGING.md` and
   `tools/OFFLINE-VERIFICATION.md` — preparation, testing and release workflow.

Read `KEYBOARD-SPEC.md` and `analysis/HARDWARE.md` when working on input.
The hardware report describes the original vendor system and dated observations;
its process names/counts are not a live description of the independent app.
`ACCOUNT-HANDOFF.md` and `ORCA-RETURN-HANDOFF.md` explain September/early-October
history. Their pending experiments and branch-integration instructions are stale
where later records show completion. The root `README.md` also contains obsolete
launch/build advice: do not build into an installed `release/` folder from it.

## 2. Product and architecture

The goal is one dependable Windows app for the existing **19-iPhone rack**. The
operator opens one shortcut, recognizes each physical phone, sees fresh video,
controls the intended phone or an explicitly selected group, and can Stop and
recover without replaying uncertain commands. The supported app is **iMouse 2.0
— Independent AirPlay**. `iNodeControl` is the repository/project name.

Input and video travel through separate paths:

```text
WPF console -> local HTTP kernel -> USB HID board -> iPhone input
iPhone -> Wi-Fi/AirPlay -> UxPlay receiver -> kernel frames -> console
```

Healthy control does not prove healthy video, or vice versa. The independent
kernel replaces the vendor input service; UxPlay supplies independent AirPlay
receivers. Existing physical boards and Windows/native dependencies remain.

Use this source map:

| Component | Where to work | Responsibility |
|---|---|---|
| Windows desktop | `src/iMouse.Console/` | C#/.NET 8 WPF; selected preview, phone wall, controls, settings, diagnostics |
| Console input | `ApiClient.cs`, `InputLeaseClient.cs`, `InputControls.cs`, `ConnectionLifecycle.cs`, `PointerMovePump.cs` within that folder | Ordered commands, ownership, cancellation, text chunks, drag/hover and cleanup |
| Console video/timing | `LiveFrame.cs`, `PreviewFreshness.cs`, `TileStreams.cs`, `PhoneWall.cs`, `ResponseTiming.cs` | Bounded frame handling, freshness, independent tile streams and opt-in timing |
| Kernel | `src/iMouse.Kernel/` | C#/.NET 8 Windows HTTP service, HID access, configuration, input and video |
| Kernel input | `ApiServer.cs`, `InputSessions.cs`, `InputRouter.cs`, `HidProtocol.cs`, `DeviceStore.cs` | API, per-phone leases, board serialization, HID reports and binding persistence |
| Receiver lifecycle | `AirplaySupervisor.cs`, `ReceiverFleet.cs`, `ReceiverProcessLifetime.cs`, `FrameStore.cs` | Retry budgets, shutdown, process cleanup, frame delivery and status |
| Native receiver | `tools/airplay/uxplay/` | Modified UxPlay/GStreamer source and Windows build context |
| Test/release tools | `tools/`, `analysis/` | Existing accuracy/timing runners, simulated tests, manifests, staging and recorded evidence |

The independent endpoint is normally `http://127.0.0.1:9913/api/`. Port **9911**
is the vendor-service default; do not silently fall back to it. Inspect the exact
candidate configuration before connecting.

An **input lease** means one controller owns a phone's commands temporarily.
The console and another API client cannot independently drive that phone at the
same time. The installed console's hover tracking can acquire a lease just by
moving the PC cursor over a preview. Normal Disconnect releases that console's
ownership; it does not stop the separate mirroring service.

## 3. Work already completed

The combined checkout incorporates the desktop work from Claude and Orca/Codex,
followed by October reliability repairs. Reuse it; do not blindly merge old topic
branches or reapply fixes that are already present.

The main completed implementation areas are:

- **Input:** 12-character text chunks under the existing eight-second command
  deadline; the 200-character UI cap remains temporary. Timeout pauses are
  visible, explicit Resume is available, queued unsent work is distinguished
  from uncertain input, and timed-out text is never automatically retried.
- **Ordering and cleanup:** first-click Stop, drag final-point/queue ordering,
  hover coalescing, scoped held-input cleanup and awaited disconnect/reconnect/
  close. Failed cleanup stays visible and is retained in diagnostics.
- **Isolation and startup:** isolated test settings, explicit normal candidate
  data folders/addresses, atomic settings and binding saves, build identity,
  startup/configuration checks and missing-runtime refusal before hardware.
- **Video and recovery:** frame freshness/session identity, per-phone tile
  scheduling, bounded screenshot download/write behavior, corrected image buffer
  growth, bounded logs, accurate retry counts, confirmed receiver-root cleanup
  and joined fleet shutdown.
- **Native/release work:** a demonstrated native report-parser leak repaired,
  native build/runtime provenance and plugin inventory, dependency notice
  collection, immutable review packages and isolated preparation scripts.
- **Test quality:** existing accuracy harness consolidated; timing runner
  failures, cleanup and candidate preflight repaired; bounded console response
  timeline/export added. Endurance analysis preserves failed input rather than
  labelling duration alone a pass.

The latest focused results are **409 console self-tests**, **89 timing-runner
checks** and **20 diagnostics checks**, all passing offline. Earlier unchanged
kernel evidence includes **207 kernel**, **41 recovery**, **34 frame** and
**14 fake process-lifetime** checks. Counts overlap and belong to recorded builds;
do not sum all historical counts or call them physical release acceptance.

The last combined live smoke used an **older** candidate on 13 October: C24C
mirroring, pointer moves, a Calculator tap, horizontal swipes and API
Stop/Resume/release passed. An upward bottom-edge swipe failed to achieve Home.
The operator restored Home physically. Both original phones were restored.
This was neither acceptance of the latest package nor real-console UI validation.

### Typing investigation: preserve and defer

The user explicitly asked to stop spending time on missing-first-space typing.
It remains unresolved. Do not reopen it as Gemini's first task.

The six-note extra-click comparison has already run: all six produced `Hithere`.
Later controlled FKA pass-through shortcut checks preserved the space inside
the prepared field, including a real Send text button and a 100-character send.
That state did not reliably survive navigation to a new note. The operator saw
a yellow highlight, not a confirmed named mode. FKA was restored after testing.
These results do not establish a general fix. Do not add padding spaces, change
keyboard mappings or alter HID timing to conceal the failure.

The six-note report is in the original checkout at
`../iMouseXP-2.0/analysis/fka-typing-mode-20261011/REPORT.md`.
See the dated October entries in `PROGRESS.md` and the separate FKA worktree's
`analysis/fka-pass-through-probe-20261011/REPEAT-REPORT.md`. Its source changes
remain separate from the accepted development line.

## 4. Exact candidate and installed app

These paths are relative to the combined checkout:

| Role | Path |
|---|---|
| Immutable review package | `output/staging/combined-timing-20261013` |
| Prepared, unused candidate | `output/candidate-runs/timing-20261013` |
| Package evidence | `analysis/combined-timing-package-20261013/REPORT.md` |
| Latest preflight evidence | `analysis/gate6-preflight-20261013/REPORT.md` |

Exact identities are:

```text
Kernel DLL SHA-256:
cd0f2129993f93158f7fcf183e590a9c1fe1be4c329de0903a2aef3de1dd7486
Console DLL SHA-256:
ebf52cd77bc55e2a5ee4790ffdcd1c47d78783a9e6bf73a44d4500b6597eccc4
Package manifest SHA-256:
9a2b786637f6f2ea262ee0d2a6c082508c0e6e66e67a0a06c070821bdba11b54
```

All **692 inventory entries** verified. Both binaries passed no-window startup
validation, and the prepared-launcher and saved-profile checks passed. The
profile is **C24C-only**, separately addressed and hover-off; C241 is absent.
It cannot satisfy the Gate 6 runner's separate **two-stream** workload.
No normal launch or physical acceptance has run on this package.

The operator's installed app stays in the other checkout:

```text
C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0
  release\iMouse2-two-phone-candidate\iMouse2.exe
  release\iMouse2-kernel-two-phone\iMouse2.Kernel.exe
  Open iMouse 2.0.ps1
```

The desktop shortcut is **iMouse 2.0 - Independent AirPlay**. Its release files,
launcher and `%APPDATA%\iMouse2\settings.json` are not your build output. Their
25 protected static hashes matched the recorded baseline at the last completed
run. No live rack/process status was queried for this handoff; all older PIDs and
lease states must be rechecked before hardware work.

## 5. What remains before the finished product

The historical claim "11 of 12 gates passed" is unsupported. Gates 1–2 have
historical scoped pass records. Gate 4 has 1,000/1,000 API taps on two phones at
one target, not the full varied-target/rack criterion. Changed binaries need
their own relevant acceptance.

| Area | Remaining acceptance | Work possible independently |
|---|---|---|
| Identity/accuracy | Fourteen placeholder bindings remain in the planned rack; physically verify every pair, varied targets and interruption recovery; at least 995/1,000 taps with zero unintended-phone/stuck/double input | Saved-config checks and existing harness improvements; physical mapping needs the operator |
| Everyday controls | Home inserts Tab; App Switcher with FKA Off is unaccepted; finish actual-console controls/cleanup/diagnostic export; typing is deferred | Source/simulated work with honest limits; live behavior needs a coordinated window |
| Speed/video | True console-action-to-correct-visible-response timing, 100 observations/category/profile, specified 500 ms/2 s percentile rules; displayed versus incoming frames/freezes under load | Review correctness/timing evidence in the existing runner; UIA invocation and a later bitmap alone are insufficient |
| Recovery | Actual native failures, exhausted retries, cleanup and phone rediscovery/recasting on the exact candidate | Fault simulations and remaining cleanup analysis; real interruptions need restoration support |
| Scale/endurance | 2 → 4 → 8 → 19 phones, then uninterrupted final 8-hour and 24-hour runs with working interactions and declared budgets | Existing log analysis and workload preparation; operator supplies connected hardware and reserved uptime |
| Release | Clean-PC native/.NET loading, dependency redistribution clearance, real setup/update/rollback and operator acceptance | Improve prerequisite detection and verify staged operations in disposable folders; a clean Windows environment is still required |

Receiver restarts have sometimes left iPhones unable to rediscover their names
for up to about 31 minutes; one recovery followed a cable replug. That observation
does not establish a cause or an automatic recovery procedure. An eight-hour
elapsed run with failed interactions is not an endurance pass.

Follow the acceptance order in `FINISH-CRITERIA.md`: **correct targeting → reliable
recovery → consistent speed → full-rack scale → endurance**. Preserve measured
results separately from source-based inferences and hypotheses.

## 6. Gemini's first work and operating rules

First confirm the checkout/branch and read the short records. Summarize the next
concrete task, then proceed with authorized offline engineering without asking
the operator to choose routine implementation details.

**Recommended independent starting task:** review the remaining clean-PC/runtime
and staged update/rollback gaps in `docs/RELEASE-STAGING.md`,
`tools/stage_release.py`, `tools/stage_receiver_runtime.py`,
`tools/candidate-launcher/`, and `src/iMouse.Kernel/KernelStartup.cs`.
Reuse the recorded package and tests. Close the next reproducible offline gap;
do not regenerate an already verified package without a relevant change or call
same-PC simulation clean-PC acceptance. Timing correctness preparation is another
available track, in `analysis/gate6-release-validation-20260916/run_gate6.py`.

Use these working rules:

- Continue coding, analysis, scratch builds and relevant offline tests
  autonomously. Do not rerun finished phone experiments or start a parallel
  timing/accuracy harness. Keep `tools/gate4_1000_tap_suite.py` as the accuracy
  entry point and extend the existing Gate 6 runner.
- Build into a **fresh** scratch/output directory. Keep review packages and
  prepared runs immutable. Never overwrite an installed release or run a root
  launch script just to test a build.
- The user previously allowed API work on an available rack. Check identity and
  `/api/input/status` before input; keep testing scoped to C24C. Do not take over
  an active controller. Read-only/API access does not grant desktop control,
  C241 input, destructive fault tests or kernel/receiver restart permission.
- Coordinate screen control or a kernel/receiver swap with the operator, who
  must be available to recast phones. Use isolated candidate settings, an explicit
  endpoint and hover tracking Off. Restore the installed release and original
  phone settings afterward; report any incomplete restoration.
- Keep input inside the lease-aware kernel path. No raw HID bypass, automatic
  retry of uncertain actions or automatic Resume. Do not change FKA or resume
  typing experiments. Home's Tab side effect can contaminate an editable field.
- Do not install a VM or change host virtualization/networking. That separate-PC
  idea was deferred by the operator.
- Commit focused, reviewed changes locally and update continuation records.
  No push, merge to main, deployment or promotion is requested by this handoff.
  Never push `backup/*`; never run `git clean -x`, delete worktrees, or wipe
  ignored evidence. Check for another active editor before sharing the checkout;
  if work will overlap, arrange a separate branch/worktree before editing.
- Use explicit UTF-8 for source/doc IO. Windows PowerShell 5.1's default encoding
  has previously damaged non-ASCII literals on this machine. Keep raw evidence
  byte-exact and retain failed attempts. Do not weaken checks because a sandbox
  denies filesystem operations; document the denial and use an appropriate
  permitted execution environment.

For orientation, these commands inspect Git and run existing offline tooling
from the combined checkout. They do not start UIA or contact the rack:

```powershell
git status --short --untracked-files=no
git branch --show-current
git log -3 --oneline
python -B tools/test_export_diagnostics.py
python -B analysis/gate6-release-validation-20260916/test_run_gate6.py
python -B analysis/gate6-release-validation-20260916/run_gate6.py --self-check
```

Do not rerun the suites solely to reproduce their recorded counts. If Git rejects
ownership, use a command-scoped `-c safe.directory=PATH` for this verified checkout;
do not disable safe-directory protection globally. The Python suites print `OK`
on success. Read `tools/OFFLINE-VERIFICATION.md` before selecting further tests.
Normal console launch, `--ui-test` and live test modes are not the headless
`--self-test` path; inspect flags and test boundaries before executing them.

## 7. Other worktrees, portal and preservation

These are related but should not replace the combined checkout:

| Location/branch | Purpose and treatment |
|---|---|
| Original `iMouseXP-2.0`, `local/coordinator-work` at `01fb669` | Earlier Orca/Codex checkout and installed rack. Preserve its uncommitted files |
| Original checkout's `.claude/worktrees/keyboard-spec-reconcile`, `claude/input-timeout-integration` at `d0c4ccf` | Older Claude integration; remote-tracking tip is only `472bb04` |
| `claude/jovial-yonath-f044e9` at `a6e4a9b` | Historical text chunking; already incorporated, don't reapply |
| `claude/funny-margulis-86e51b` at `43b43f7` | Historical settings isolation; already incorporated |
| `claude/track-gate-evidence` at `900f5b4` and `claude/gate4-harness-v2` at `2c98f44` | Historical records/tool work; consolidated harness work came later |
| Sibling `iMouseXP-2.0-fka-passthrough-probe` | Separate experimental kernel and typing evidence; deferred and not promoted |
| `backup/input-timeout-integration-pre-redaction` | Local history containing a withheld personal-device identifier; never publish |

There is also a **NodeTheory customer portal and rack agent**, separately recorded
at `origin/claude/focused-noether-s600e0`, tip `6b24a96`. It has `portal/`
(Node.js, SQLite, web UI) and `rack-agent/` (outbound WebSocket connection to the
portal and loopback access to the rack kernel). Its milestone covers customer
access, assigned phones, previews, control/Stop and audit records. Its source
report says simulator/conformance validation, with Windows/physical validation
pending. Do not assume the desktop repairs are applied there or deploy it.
Consult that branch's `PORTAL-MILESTONE-1.md` and
`WINDOWS-VALIDATION-HANDOFF.md` if the operator assigns portal work. Desktop release
acceptance is the present development focus.

Important local preservation locations are:

```text
C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-evidence-archive
C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-handoff-backup-20260928
```

The latest archive is `20261013-timing-preflight-combined`: **861 files**,
193,596,294 bytes, per-file checksums verified; relocated package and prepared
inventory also verified. Its receipt is
`analysis/combined-timing-package-20261013/archive-verification.json`, tied to
commit `250e589`. Later evidence is not automatically in the September backup.
These are local-disk copies, not off-machine backups. The archive deliberately
predates this new handoff document.

At the end of each work batch, record what changed, exact builds/tests, remaining
limits and any restoration obligations in `PROGRESS.md` and `RESUME-NEXT.md`.
Give the operator a concise outcome. Ask for physical help only when the next
action actually requires it; never mark a deferred or untested criterion passed.
