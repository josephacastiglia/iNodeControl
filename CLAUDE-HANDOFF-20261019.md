# iNodeControl / iMouse 2.0: Claude continuation handoff

Updated **19 October 2026**. Continue the existing Marketing Farm candidate; do
not rebuild the project from the older Gemini installer or restart completed
investigations. **Priorities 1 and 2 have scoped Instagram acceptance. Priority 3
is next. The complete marketing product is not ready for unattended use.**

## 1. Start here

| Item | Current location / revision |
|---|---|
| Private GitHub repository | <https://github.com/josephacastiglia/iNodeControl> |
| Working folder on this PC | `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-combined-candidate` |
| Development branch | `local/combined-candidate-20261012` |
| Checkpoint before this handoff | `37e51080118b035601dbc37d96b5814214a3b1f2` — pushed preservation-verification documentation |
| Latest product implementation | `e066acccc6651a0f1b3212cdc50238845177e0db` — saved-draft inspection and recovery |
| Latest phone acceptance record | `a8f726ff96cff791bfd57a50fd39d8294c1414f0` |
| Old default `main` | `ee445d7` — original import, **not the current candidate** |

The next documentation commit contains this handoff; use the development branch's
latest tip. Check status before changing anything. Do not switch the main working
folder to another branch, overwrite another worktree, or merge preservation
branches wholesale. The combined candidate's tracked tree was clean before this
document; ignored/untracked builds and evidence are intentional.

Read these records in order:

1. This document and [MARKETING-FARM-ACCEPTANCE.md](MARKETING-FARM-ACCEPTANCE.md).
2. The opening sections of [MARKETING-FARM-STATUS.md](MARKETING-FARM-STATUS.md).
3. [Priority 1: new content to a verified draft](analysis/farm-new-draft-20261019/README.md).
4. [Priority 2: live recovery results](analysis/farm-recovery-live-20261019/README.md)
   and [offline implementation](analysis/farm-recovery-20261019/README.md).
5. [GitHub preservation and branch map](GITHUB-SYNC-20261019.md).

`RESUME-NEXT.md`, `WORK-REMAINING.md`, `FINISH-CRITERIA.md`, `KEYBOARD-SPEC.md`
and `RE-IMPROVEMENTS-PLAN.md` describe the underlying control product. Their older
"next task", "not pushed" and rack-state statements do not supersede the dated
19 October marketing/preservation records. Earlier sections of the marketing
status file are historical checkpoints, not additional current blockers.

## 2. What we are building

iNodeControl is the repository for **iMouse 2.0**, a Windows .NET 8 WPF desktop
console, an independent C# kernel, and independent UxPlay AirPlay receivers.
The kernel sends input through USB HID boards attached to iPhones. The intended
rack has 19 boards; the principal test phones are C24C and C241.

```text
Native WPF console / Python farm backend -> HTTP kernel -> USB HID board -> iPhone
iPhone -> AirPlay over Wi-Fi -> UxPlay receiver -> paired frames -> observation
```

Video availability, input availability and ownership are separate. An input lease
prevents competing controllers from driving the same phone. A successful HTTP/HID
reply does not prove the app displayed or saved the intended result.

The active feature is the **Marketing Farm (Test Tab) in the native desktop
console**, originally developed through Gemini/Orca and then hardened here.
It includes content preparation, draft editing, media transfer, observed phone
workflows, scheduling and analytics foundations. It is an isolated, unpromoted
candidate, not a replacement for the installed release or merely a web mockup.

## 3. The original seven priorities: exact order and current status

These are the seven priorities given to the operator before Priority 1 began.
Keep this numbering; do not confuse it with the separate 12 core release gates.

| Priority | Where we are | What remains |
|---|---|---|
| **1. New content through to a verified draft** | **Passed in the tested scope:** one uninterrupted C24C Instagram run created/imported three new slides, selected them in order, pasted the exact caption, saved and independently reopened/verified the draft. | Other slide counts, ambiguous media, long/hidden captions, accounts and formats need their own acceptance. HID first-space loss is deferred; this workflow uses Copy/Paste. |
| **2. Repeatability and recovery** | **Scoped recovery passed:** three inspections of the retained creation verified every slide/caption; deliberate Stop, native receive-error recovery, durable bookmarks and a terminal backend restart passed. Offline tests cover active crashes and faults at each inspection action. | Repeated *new-content* creations, independently evidenced app termination/relaunch, destructive live faults and broader prompts/layouts remain open. This is not general unattended recovery. |
| **3. Complete platform coverage** | **In progress (19 Oct, offline).** A per-format evidence matrix covers all 14 formats (`tools/farm_format_coverage.py`, [record](analysis/farm-reel-draft-20261019/README.md)). The Instagram Reel, TikTok video and X video draft-only candidates are implemented and tested offline ([TikTok record](analysis/farm-tiktok-draft-20261019/README.md), [X record](analysis/farm-x-draft-20261019/README.md)); their C24C windows are prepared but not run. X uses whichever account is signed in first (operator, 20 Oct). Permission prompts are recognized on every screen and stop the run with a one-time request until an input method is validated ([record](analysis/farm-permission-prompts-20261020/README.md)). Only the bounded Instagram carousel lifecycle has integrated live acceptance. | Live Reel, TikTok and X acceptance; a permission-prompt validation window; then YouTube Short, TikTok photo (sound kept unless testing no sound) and X image adapters, one at a time. Story, text, thread, long-video and community formats stay unsupported until a draft mechanism is observed. |
| **4. Scheduler and warmup** | Recurring **local content preparation** works with retained batches, pause/restart handling and tests. Schedule planning, cooldowns and warmup sequencing have simulation coverage. | Verified review queue, recurring phone execution, real timing/queues/budgets, app outcomes and unattended restart acceptance. Warmup is not an accepted live service. |
| **5. Analytics** | Validated submitted observations retain account/post/time evidence. Low-view rules can latch a preparation pause; missing data stays unknown. | An automatic, verified metric provider and comparison with real account/post data. Counts alone must not imply a platform restriction or automatically clear a pause. |
| **6. Publishing and messaging** | **Disabled by the operator's instructions. Not an authorized live task.** | Separate explicit scope and acceptance would be needed for recipients, publication outcomes, duplicate prevention and failure recovery. Do not enable these to finish the roadmap. |
| **7. Rack and release readiness** | Isolated settings, durable jobs, diagnostics/build tooling, source provenance, private evidence archives and GitHub preservation are in place. | More phones/accounts, isolation under load, longer unattended runs, actual interface usability, packaging, clean-PC install/update/rollback and final release acceptance. No promotion is approved. |

**Working direction:** start Priority 3 offline. Review-queue foundations for
Priority 4 can be reused, but do not silently skip the unfinished platform work.
Report progress by these seven priorities and by the exact scope tested.

## 4. What has already been completed

### Priority 1: fresh content through a verified Instagram carousel

The accepted native-handler run completed **60 phone actions** on C24C,
Instagram **@xs.halle.xo**, without a review hold or operator help after initial
phone preparation. It imported three labelled JPEGs through Safari/Photos,
matched unique picker thumbnails and numbered selection order, checked every
full-size slide, pasted the complete caption, saved and reopened twice for
independent verification. The final profile and ownership cleanup matched.

Evidence: **436 Python tests, 556 native headless checks, nine live driver
assertions, 210 collected evidence checks and 96 retained frames**. A later
read-only metadata correction passed 68 focused tests; those overlap the full
suite and are not 68 additional unique tests. Earlier held attempts remain
preserved and must not be represented as uninterrupted passes.

The retained source creation is `b8c155e2-1670-4f60-a090-aeff921e162e`, local draft
`6e390142-4d00-473a-b2ee-83f65da53cc7`, revision 5. Its caption is:

```text
Fresh content acceptance
Three slides in order
Draft only
```

Scope: three distinct slides, a short fully visible ASCII caption, one account
and the observed layout. It does not establish every carousel size, iOS media
byte identity, continuous account observation or server-side persistence.

### Priority 2: inspect saved content without repeating an uncertain operation

The native **Inspect saved draft · no Save** action creates a separate request
bound to the original immutable creation/package/journal. It opens the unique
matching saved cover, verifies all three slides and the complete caption, and
releases C24C. It sends **no Save, import or typing** and finishes on draft details.
It never turns matching content into a claim that an uncertain original Save
succeeded. A new explicit request is required for further input.

The live pass recorded three complete seven-action inspections and one deliberate
Stop after the first answered action. Cleanup was confirmed; the stopped record
stayed terminal while a new request ran. Suppressed admission/status replies
recovered the same identity without duplicate submission. After terminal work,
a graceful backend restart and a new native window recovered the bookmark using
GETs only. All **58 collected checks, 40 retained frames and 52 native assertions**
passed. All **441 original source-data files and 25 protected installed files**
remained byte-identical.

The unchanged product's offline validation is **452 Python tests, 564 native
headless checks and eight retained-layout tests**. It includes a real child
process exiting mid-work, plus lost replies, Stop, disconnects and receiver
changes at every one of the seven inspection action boundaries. Retained images
and simulated HID are not fresh-phone acceptance.

Important limits:

- The operator reported ready after instructions to force-close/relaunch
  Instagram. There is no independent iOS termination telemetry;
  **`appRestartVerified: false` remains correct**.
- The live backend restart happened **between terminal requests**. Active backend
  death and lost kernel-command answers were not injected destructively live.
- Client receive errors were injected after a real backend response. They do
  not prove recovery from every kind of network packet loss.
- Repeated inspection of one creation is not repeated creation or scheduled use.
- Unknown dialogs still stop for review. No generic click-through, automatic
  Resume, automatic force-quit or replay was added.

### Other foundations to reuse

- Recoverable native carousel editing: slide ordering, full captions, import,
  export, revision conflicts, local persistence and unsaved-edit preservation.
- Real decodable JPEG/MP4 templates, immutable manifests/checksums, video
  preparation and expiring private media links. **External AI generation is not
  configured.** Existing automation must not pretend templates are AI output.
- Exact account/caption checks, source-image matching, retained decision frames,
  all-slide/page-dot checks and paired session/sequence/delivery freshness.
- Bounded settling for observed loading/autoplay changes; exact OCR remains
  required at action boundaries. Do not repair captions or guess account text.
- Durable request IDs, cancellation, worker exclusivity, evidence retention,
  unknown-outcome holds and explicit status recovery.
- Supervised photo/video drafts saved and reopened on Instagram, TikTok, X and
  YouTube. Those records support the next adapters; they are not proof that all
  native automation routes already work.

## 5. Next task for Claude: Priority 3, offline first

Build on the current modules rather than adding a parallel farm engine. First
produce a per-format capability/evidence matrix using the actual `UploadFormat`
enum and historical reports:

| Platform | Existing format IDs |
|---|---|
| Instagram | `ig_reel`, `ig_carousel`, `ig_post`, `ig_story` |
| TikTok | `tt_video`, `tt_photo_carousel`, `tt_story`, `tt_text` |
| X | `x_post`, `x_video`, `x_thread` |
| YouTube | `yt_short`, `yt_video`, `yt_community_post` |

For each, distinguish simulation, supervised phone evidence, integrated offline
implementation and fresh integrated live acceptance. A story/community/thread
path with no verified draft mechanism must stay unsupported; never post content
as a substitute for saving a draft.

**Recommended first extension: Instagram Reel draft-only**, because video
preparation/transfer and supervised Reel save/reopen already have evidence. This
is a recommendation, not a claim that a Reel adapter has already been built.

1. Read the existing video/media and supervised platform reports. Reuse durable
   jobs, observation binding, guarded transport and immutable media packages.
2. Implement bounded format-specific states, exact account/media/caption checks
   and independently observed save/library/reopen verification. Keep capabilities
   disabled until their requirements are met; explain unavailable features in
   the native interface instead of showing false success.
3. Test wrong accounts/media, ambiguous covers, stale/frozen frames, changing
   sessions/ownership, prompts, Stop, lost replies and process interruption.
   Unknown Save outcomes must never cause another Save or another import.
4. Prepare fresh isolated configuration, source/binary hashes, test media, an
   evidence directory and a finite live acceptance plan before asking the
   operator to connect C24C. Keep the real Share/Publish boundary unreachable.
5. When a live window is available, verify actual visible results, cleanup and
   protected hashes. A successful API reply is insufficient. Preserve failures
   as well as passes; update the same seven-priority record.

Continue useful offline work autonomously. Ask the operator only for genuinely
missing account information, a required physical phone action or a disruptive
window. Do not restart the missing-space/FKA investigation: it is deferred.

## 6. Current code, builds and offline checks

| Area | Main files |
|---|---|
| Native marketing tab and jobs | `src/iMouse.Console/MainWindow.FarmTab.cs`, `MainWindow.FarmJobs.cs`, `FarmAutomationWindow.cs`, `FarmApiClient.cs` |
| Native draft run/recovery | `src/iMouse.Console/FarmDraftRunWindow.cs`, `FarmDraftRunTests.cs`, `FarmJobRecovery.cs` |
| Native preparation/review | `src/iMouse.Console/FarmPreparationWindow.cs`, `FarmObservationWindow.cs`, `FarmDraftVerificationWindow.cs` |
| Server, engine and jobs | `tools/imouse_farm_server.py`, `imouse_social_automation.py`, `farm_jobs.py`, `farm_capabilities.py` |
| Draft storage/creation/recovery | `tools/farm_drafts.py`, `farm_draft_creation.py`, `farm_creation_runs.py`, `farm_draft_runs.py`, `farm_draft_recovery.py` |
| Recognition and guarded actions | `tools/farm_observations.py`, `farm_frame_evidence.py`, `farm_screen_layout.py`, `farm_transitions.py`, `farm_draft_transport.py`, `farm_draft_workflow.py`, `farm_live_verification.py` |
| Media, inspection and scheduling | `tools/farm_media_transfer.py`, `farm_video.py`, `farm_draft_media.py`, `farm_carousel_inspection.py`, `farm_preparation_schedule.py` |

Paths in this table are relative to the current working folder, not the older
Claude worktrees. Some legacy source comments mention ports 9913/9914; the
isolated candidate's actual configuration below takes precedence.

| Component | Accepted candidate identity |
|---|---|
| Native output | `output/codex-farm-recovery-20261019` |
| Native `iMouse2.dll` SHA-256 | `f2df511f1ad77269a724c016f9e95324718860c09efc0d7030f0a9f281f6f47c` |
| Private kernel output | `output/codex-farm-live-kernel-20261018` |
| Kernel DLL SHA-256 | `c72fa4e0b02b82ec4f7a949c9a80375c69da68d7357084401c7bb422c194a873` |
| Backend source fingerprint | `e3ab6368c348cd5091d6b7ca4db09a9342c9508999d4faa8de86d92a54d13bd0` |
| Farm backend | `http://127.0.0.1:9915` |
| Private C24C kernel | `http://127.0.0.1:9916/api` |
| Temporary creation media service | Explicit port 9917, expiring and scoped to the selected package |

The installed independent kernel normally uses 9913; the legacy farm uses 9914.
Never silently fall back to vendor port 9911. The C24C binding in the accepted
configuration is device `86:1D:4A:04:2F:F6`, board UID `C24CBFBD`; recheck actual
identity before input rather than relying on the label alone.

Python on this PC is
`C:\Users\joey_\AppData\Local\Programs\Python\Python311\python.exe`.
Dependencies are recorded in `tools/requirements-farm.txt`; video preparation
also requires `ffmpeg`/`ffprobe` with the required codec support. Windows OCR uses
the existing PowerShell bridge. Missing dependencies must fail clearly.

From the working folder, these checks do not start a rack service or send input:

```powershell
$taskPython = 'C:\Users\joey_\AppData\Local\Programs\Python\Python311\python.exe'
& $taskPython -m unittest discover -s tools -p 'test_farm*.py' -v
& '.\Open Marketing Farm Candidate.ps1' -ValidateOnly -PythonPath $taskPython
```

The latest full suite passed 452 tests. Run relevant tests after changes; avoid
repeating unchanged suites merely to produce another progress update. For a new
native build, use a fresh scratch output and the existing hidden `--self-test`
pattern. Do not run interactive `--ui-test` or desktop automation. Do not rebuild
over the exact accepted output or overwrite dated test records.

The offline record contains `run_tests.py`, `run_retained_tests.py`,
`run_controls.py` and `Build-And-Test-Native.ps1` as reproducibility references.
Those helpers write into their dated records/outputs: preserve the originals and
adapt new-run output paths before reusing them. Retained-frame checks and
`analysis/farm-recovery-live-20261019/final_validation.py` require the private local
artifacts; a GitHub-only clone does not include screenshots, databases or builds.

`Open Marketing Farm Candidate.ps1` defaults the **farm transport** to simulation,
but normal launch can still connect the console to kernel 9913. Simulation alone
does not isolate every console control. Use `-ValidateOnly` for offline
preparation. Its `-DraftCreationConfig` path requires the verified separate kernel
on 9916; the launcher does not start that kernel, reconnect mirroring or install
anything. No ordinary candidate window is needed for headless tests.

## 7. Live boundaries and recorded rack state

The operator's continuing constraints are:

- **C24C only; no input to C241 or other phones.** Use APIs, not PC screen control.
- **No publishing or messaging**, purchases/trials, new account activity outside
  the approved draft task, or automatic account changes.
- **Leave the installed release, shortcuts, launchers and shared settings
  unchanged.** Use explicit private data directories and `trackPointer: false`.
- **Leave FKA and other phone settings unchanged.** The first-space issue is
  deferred; use only validated caption entry. No dummy spaces or hidden text fixes.
- Confirm the service/binary identity, C24C binding, `/api/input/status`, free
  ownership and fresh paired video before input. Never steal another lease.
- Preserve Stop, cleanup, bounded deadlines and no replay. Status/eligibility
  reads and reopening a bookmark must not initiate phone actions.
- A fresh decision can replace a locally expired **unsent** action only within
  the implemented verified rules. A dispatched action with a lost answer stays
  uncertain. No automatic Resume or guessing through arbitrary iOS prompts.
- Do not interrupt an active rack or restart shared kernels/receivers without a
  coordinated window. Previous temporary-swap approvals applied to those tests.
- Restore the window's actual initial state, stop only owned private processes
  gracefully and verify protected hashes. Do not open the installed console
  automatically when its initial state was stopped.
- No deployment or promotion. Commit reviewed changes and push only the intended
  development branch for preservation; never force-push or push `backup/*`.

**Last recorded state:** the Priority 2 window ended with the private backend,
kernel and receiver stopped, restoring an initially stopped rack. C24C was free
with generation 4 before shutdown, on Instagram's carousel details with the test
caption. No new media/draft was created during recovery; three labelled test
drafts and nine test images from Priority 1 remain. The Share button may be
visible on details; it is not an authorized action. FKA was unchanged. C241 was
not addressed, and all 25 protected files matched. The later GitHub audit sent
no phone input or service commands. **This is historical state: recheck current
processes, ports, identity and ownership before a new window; do not reuse PIDs.**

The operator can reconnect mirroring initially and handle a genuinely blocked
physical prompt. A prior suggestion to automatically select a receiver by fixed
row is unsafe: a Bedroom TV can occupy that row. Do not run `tools/force_recast.py`
or claim AirPlay has a verified force-connect API. Receiver rediscovery after
restarts has sometimes taken up to 31 minutes.

Live helper scripts deliberately refuse existing attempt folders. Use new IDs,
fresh evidence, isolated copies of source data and a validated configuration.
The latest staging fix copies `pointer-calibration.json` and runs
`--validate-startup` before starting the private kernel. Do not omit calibration
or regenerate it during a marketing test.

## 8. Preserved cross-agent work: do not merge every branch

The completed 19 October audit pushed all discovered safe project source,
scripts, reports and reviewed text records to the private GitHub repository.
It preserved **3,309 previously uncommitted files**, verified all **15 publishable
local branch tips**, and left `main` unchanged. This is preservation, not feature
acceptance. The full audit distinguishes saved local work from inaccessible
cloud-only conversations.

| Branch | Purpose |
|---|---|
| `local/combined-candidate-20261012` | Continue development here; integrated product and current marketing acceptance |
| `local/coordinator-work` | Earlier Orca/OMP coordinator work |
| `claude/input-timeout-integration` | Claude control/timeout/UIA/FKA history through `d0c4ccf` |
| `claude/jovial-yonath-f044e9` | Earlier text chunking |
| `claude/funny-margulis-86e51b` | Earlier settings isolation |
| `claude/focused-noether-s600e0` | Cloud portal and rack agent; reference, not the current native farm |
| `claude/track-gate-evidence`, `claude/gate4-harness-v2` | Core evidence and experimental harness history |
| `handoff/orca-working-tree-20261019` | Snapshot `4eef760f66df`; 458 selected files, including original checkout edits |
| `handoff/gemini-and-local-records-20261019` | Snapshot `3d95ec846a82`; 2,825 selected historical/source/report files, including sanitized dedicated Orca export |
| `handoff/fka-probe-working-tree-20261019` | Snapshot `ff5fde280634`; 26 selected probe files |
| `handoff/orca-coordinator-reflog-20261002` | Preserved otherwise unreferenced coordinator commit `b946b942c82d` |

The separate `C:\Users\joey_\orca\projects\iMouse2Automations` folder contained
two handoff/export documents, not another missing implementation. They are
preserved in the Gemini/local-records snapshot. Do not confuse unrelated
`installed-marketing` or `sites/keystone-cards` projects with this app.

**Never run legacy `tools/setup_imouse_farm.py` or `Open Marketing Farm.ps1` to
recreate the farm:** the preserved installer can overwrite the hardened source.
Inspect historical code for a specifically missing feature instead of replaying
setup or blindly applying old diffs.

## 9. Private evidence and backup rules

Raw screenshots, databases, binaries, session data and toolchains are not on
GitHub. Their records/manifests are versioned; private artifacts remain under:

```text
C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-evidence-archive\
  20261019-farm-new-draft\
  20261019-farm-recovery-offline\
  20261019-farm-recovery-live\
  20261019-cross-agent-preservation\
```

The Priority 2 live archive contains **681 files**, with checksum-manifest SHA-256
`191dfc778bbcd0f574b5835a97892e878ddde9d7a2d72176698e97f71c3644ed`.
The offline archive contains 546 files; use each record's `archive-summary.json`.
The 28 September handoff backup is older and does **not** include October work.
Preserve all dates; never run `git clean -x`, delete ignored evidence or remove
worktrees before verifying and retaining their artifacts elsewhere.

**`backup/input-timeout-integration-pre-redaction` must never be pushed.** The
private cross-agent Git bundle includes that withheld history and must never be
uploaded either; heed `NEVER-UPLOAD-THIS-BUNDLE.txt`. Keep authentication stores,
vendor login/configuration, private device identifiers and general account chat
data out of Git. Review and explicitly stage intended files; never `git add .`,
`git add -A`, `git push --all` or `git push --mirror` in this repository.

## 10. Underlying product work still open

Marketing progress does not close the original control/rack release gates.
Outstanding work includes physical Home field-preservation/repeatability and
App Switcher compatibility, deferred HID/FKA first-space loss, reliable recasting,
varied-target accuracy and additional bindings, console-to-visible response
measurements, actual displayed frames/freezes under load, 4/8/19-phone scale,
uninterrupted endurance, and clean-PC installation/update/rollback validation.

Direct Home/App Switcher alternatives and reverse-engineered board findings have
offline implementations and limited physical observations. Do not promote them
as universal fixes or turn reply observations into invented acknowledgement
pacing. See `RE-IMPROVEMENTS-PLAN.md` and its dated acceptance reports if needed.
The earlier "11 of 12 gates passed" claim was not supported by the recorded
scope. Keep core release criteria separate from this seven-priority marketing
roadmap and use measured evidence for every claim.

**Claude's first response should briefly confirm the branch, the scoped results
for priorities 1–2 and the offline Priority 3 task it will perform, then do that
work.** Do not request another general planning approval, restart historical
tests without a reason, enable publishing/messaging, or ask for desktop control.
