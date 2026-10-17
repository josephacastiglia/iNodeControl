# Instagram carousel draft candidate — 17 October 2026

The selected priority is a **draft**, not publishing. This pass completes the PC-side editor and strengthens farm job recovery. It does not establish that a carousel can be saved inside Instagram yet.

## Changes

- Native carousel editor: new/from-generated drafts, image picker, slide ordering/removal, caption and title, previews, save, reload and review ZIP export.
- Transactional SQLite draft and image storage, independent of generated-media cleanup or original source files. Optimistic revisions prevent two editors overwriting each other.
- Image decoder validation, 8 MiB/40 megapixel limits, EXIF orientation, static JPEG/PNG only, full-image fit to 1080×1350. No source image is modified. This candidate supports 2–10 slides.
- Captions up to the candidate's 2,200-character budget are kept exactly. Longer/unsupported phone captions are never truncated or sent to input. All exports explicitly say local draft, not saved in Instagram or published.
- Local unsaved-edit recovery in the candidate's own settings folder. Conflicts and unreadable recovery bytes are archived rather than silently replaced.
- Console pending-job bookmark saved before submission. Reopening restores the request ID without replay; incompatible modes refuse. A recovered live job leaves manual input paused and requires explicit Resume after completion.
- Existing Instagram carousel button opens the editor. Other platform simulations and live guards remain as before.

## Verification

| Check | Result |
|---|---|
| Full Python suite | 106 pass, including 17 draft tests and 8 actual HTTP tests against a private ephemeral simulation server |
| Generated content → draft | Actual template assets imported through HTTP, four images, generation/caption preserved |
| Export | Ordered images decoded, SHA-256 verified, caption exact, HTML escaped, no publication state fabricated |
| Native self-tests | 447 pass, including recovery and an unshown WPF editor render |
| Release build | 0 warnings, 0 errors |
| Candidate launcher | ValidateOnly passes; no processes started |
| PC control, real services, phones, account actions | Not used |

Intermediate failures were preserved: the restricted Python sandbox denied temporary replacements and loopback sockets; the unrestricted mock-only rerun passed. Two native test checks needed setup corrections (ownership disabled on a mock; root margin excluded from actual width). The final native exit code was 0 and its report records 447 passing checks. The editor render also exposed a library label fallback, which was fixed; the caption is now top-aligned.

## Build and preservation

- Candidate: `output/codex-farm-carousel-20261017`.
- DLL SHA-256: `4c1a49490c6f20e65c1f331aefcfb53ba6734caad5b4a6c3f86459ecd0933926`.
- Parent before this work: `c60cb56f4a1a3db82fe127f66a0b3f70683caa05`.
- Final commit and checksums: `checkpoint.json` and `source-inventory.json`.
- Exact files and binaries copied to `iMouseXP-2.0-evidence-archive/20261017-farm-carousel/` outside this checkout.
- No promotion, shortcut replacement, service restart, push or migration of the legacy farm database.

## Remaining work

1. Media-only delivery to C24C, avoiding exposure of the farm control server to the LAN.
2. Verify target Instagram account, selected media and caption against real observations; confirm a saved Instagram draft. Needs a designated test account and a coordinated phone check.
3. Extend accepted steps to the other platforms. Current 14-format tests exercise mock transport, not those apps.
4. Add real observation/account/recipient integration for analytics and explicitly authorized reply workflows; no fabricated OCR or view counts.
5. Validate real scheduling, lease handover, Stop/cancellation and restart recovery on the accepted build before unattended operation.

The installed release is unchanged. Live autonomous app actions remain disabled; no fake success bypass was added.
