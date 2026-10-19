# New content to a verified Instagram draft

Priority 1: create a local carousel, transfer its media, select the correct slides,
paste the complete caption, save a phone draft, then independently reopen and
verify it. Scope: **C24C, Instagram @xs.halle.xo, draft only**.

**The fresh-content run passed without a review hold or manual intervention after
initial phone preparation.** It completed 60 actions, including import, exact
caption verification, Save and two independent reopen checks. All nine native
driver assertions and 96 retained image checks passed. The initially stopped rack
state is restored. Nothing is promoted or deployed.

## What the candidate implements

- **Create phone draft** in the native carousel editor uses an immutable saved
  revision. The backend binds the request ID, package checksum and private data
  store before starting. Lost responses retrieve that request, without replay.
- A C24C-only, expiring LAN page delivers three labelled JPEGs to Safari. Each
  Photos save requires recognized image/menu evidence. HTTP delivery alone
  never proves a Photos save.
- The picker requires three unique matching thumbnails and numbered selection
  badges in the saved order. Fixed preview/selection overlays have reduced
  comparison budgets; the matcher does not fit arbitrary colours or accept an
  indistinguishable duplicate. Full-size checks permit no thumbnail overlays.
- The phone copies the exact caption from the transfer page and pastes it into
  Instagram. **OK only closes the caption editor.** The full caption must match
  exactly on the details screen before Save. This avoids OCR mistakes from the
  blinking caret without repairing, ignoring case or changing any text.
- Every slide is checked before saving. A separate owned run opens the saved
  draft, checks all three slides and the complete caption twice, and returns to
  the exact account profile. Its sampled account history must be consistent.
- Stop, durable bookmarks and unknown-outcome holds remain active. A new,
  explicit continuation may reuse three confirmed Photos imports only before an
  editor opened, on the same receiver session and input generation. It resets
  only a recognized unedited picker; it never repeats an import or Save.
- The candidate stays disabled without its explicit configuration. Its farm
  routes cannot fall back to the installed kernel. Creation has fixed phase
  limits of 120 seconds and a 720-second total; independent verification retains
  its 120-second limit. The 1,500-ms per-frame evidence limit is unchanged.

## Live records

| Record | Outcome and scope |
|---|---|
| Attempt 13, `839f761a-05dc-412f-902e-52a0b2ab1510` | New-content draft saved and independently verified through the headless native interface. It continued from the confirmed imports in attempt 9 after explicit review holds. All nine driver assertions passed; 180 retained images across the five linked requests passed checksum checks. |
| Attempt 14, `d2823820-3a4a-4cba-b6d0-4c3ad9b04f6f` | Stopped before OK/Save because caption-editor OCR read a caret as a letter and changed a letter's case. The original job remains review-only. |
| `caption-recovery/` | Explicit diagnostic finish of that known unsaved caption: fresh ownership/context checks, OK, exact details, Save and independent verification passed. No Photos reimport, no prior command replay; the original job is unchanged. This is not an uninterrupted native-interface pass. |
| Attempt 15, `b8c155e2-1670-4f60-a090-aeff921e162e` | Passed in one fresh request on the corrected source: 41 creation actions plus 19 independent verification actions, all answered. Three Photos saves, exact three-slide order and caption, account boundaries, final profile and cleanup passed. All 210 collected evidence checks passed. |

The maximum recorded action-decision age in attempt 15 was 1,361.6 ms against the
unchanged 1,500-ms limit. It needed no Save-decision refresh. Earlier attempts and
failed negative controls remain preserved. Read-only
preflight failures did not send input. The continuation-generation check was
corrected to match the kernel: acquiring retains a generation; releasing advances
it. Thumbnail fixes include both independent overlays and their combination.
Empty selection rings are distinguished from numbered badges.

## Build and checks

- Native Release: `output/codex-farm-new-draft-20261019`, zero build warnings or
  errors; **556 headless checks passed**, using mock transport.
- Native DLL SHA-256:
  `7b1594ffef1334d4251a3b56710aaf4c7bbb2cbc22209e8e5dfbd528020e1f91`.
- Live backend fingerprint (product commit `0ada6fd`):
  `93cb953cd8b9a1fe449525122275067421f890c1570153c89a460d660b84c796`.
- Final backend fingerprint (commit `f25abdb`):
  `2eee84df1d687b540666ff9c8ce89340429acec950a9d4c1be0bdaa3d6c6bd69`.
- Unchanged private C24C kernel SHA-256:
  `c72fa4e0b02b82ec4f7a949c9a80375c69da68d7357084401c7bb422c194a873`.
- Complete Python regression: **436 passed**, zero failures/errors/skips, 323.36 s.
- Read-only metadata follow-up: **68 passed**, zero failures/errors/skips. These
  overlap the complete suite; they are not 68 additional unique test cases.
- Launcher ValidateOnly passed for simulation and explicit creation modes,
  without starting processes. Both report the final source fingerprint.

The only product change after the live run is in `CreationRuns.get()`: it exposes
the later verifier's release state as `finalInput` and retains
`creationFinalInput`. The raw creation journal remains unchanged. Offline
retrieval of the real completed run confirms generation 18; the original
creation phase ended at generation 17. AST comparison confirms every other
method and product file matches the live snapshot. `validation.json` records
that comparison, source hashes, tests and the exact result.

`attempt-15-preparation.json` and `attempt-15-source/` pin the live product
bytes. The native assembly was built from the uncommitted source in this pass;
its inherited version label is not a claim that the old base commit contains
these changes. The headless host calls the same native Start handler without
showing a window. It does not test physical Windows hit targets.

## Limits and remaining work

This is a scoped candidate for **three distinct slides and a short visible ASCII
caption**, one phone/account and the observed Instagram layout. Other image
formats/layouts, wrapped or hidden captions, ambiguous existing media, other
accounts and other phones require their own acceptance. Unsupported captions are
refused without truncation. A successful check proves the visible draft through
reopening, not app-restart or server persistence, continuous account observation,
or media-byte identity on iOS.

The HID first-space bug is still deferred; this caption path uses Copy/Paste.
Full Keyboard Access is unchanged. Other platform workflows, unattended recurring
phone execution, analytics, publishing and messaging are not completed by this
milestone. Publishing and messaging remain disabled.

## Restoration and evidence

All work used private ports 9915/9916 and the temporary C24C-only media port 9917.
The same kernel and receiver remained running throughout backend revisions;
C241 received no input. No PC control was used.

The backend and kernel stopped gracefully; the receiver exited with its kernel.
No test/rack processes or relevant listening ports remained. All 25 protected
installed-release/settings hashes matched. The installed console was never
started. See `restoration.json` and `final-live-state.json` (the latter captures
generation 18, free input, before shutdown).

Three labelled test carousels and nine new test images remain on C24C. No older
draft, image or note was deleted. The phone clipboard holds the last test caption:

```text
Fresh content acceptance
Three slides in order
Draft only
```

Preserve the local captures and SQLite evidence. The archive is outside this
repository under `iMouseXP-2.0-evidence-archive/20261019-farm-new-draft/`, with
checksums; `archive-summary.json` records its verified inventory.

Session scripts contain historical PIDs and are evidence, not general startup
instructions. The separate `Open Marketing Farm Candidate.ps1` defaults to
simulation. Its `-DraftCreationConfig` option requires a separately prepared
C24C-only kernel and isolated data; it does not restart the rack or update the
installed shortcuts.
