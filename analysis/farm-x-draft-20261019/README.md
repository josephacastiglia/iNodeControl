# Priority 3: X post/video draft groundwork (no adapter yet)

Scope: offline study only. It used no phone input, service, desktop control,
publishing or messaging. **No X adapter was built.** The authorized X account
for C24C is an operator decision that has not been made (see section 3).

## 1. Evidence

- Retained 17 Oct supervised steps: the X image post (28–45) and the X video
  (114–130), on C24C.
- The 98 frames were re-read locally with the production Windows OCR
  (`ocr_retained.py`). The results are in the private archive
  `iMouseXP-2.0-evidence-archive/20261019-farm-x-offline` (outside Git; it contains
  personal and third-party feed content). Manifest SHA-256:
  `7286f446722732bdbb227a00747a7f475731729e63fe62920602affd10412231`.

## 2. Observed route and hazards

| Step | Observed screen | Notes for an adapter |
|---|---|---|
| Account | Avatar → side menu with display name, **@handle**, Profile, Communities, Download Grok, Settings and privacy (step 31); close returns to the feed | The production classifier already recognizes this menu (`account_menu`, `x`). The handle is the only identity proof; the feed shows none |
| Compose | Feed `+` → composer: **Cancel**, **Drafts** (only while empty), **Post** (publication), `What's happening?`; first-use tooltips (*Your drafts are here*, *Choose who can reply*) | Post must be a refused target. Tooltips overlay controls; settle or dismiss read-only |
| Text | Text first; media is added after | Use the validated Safari copy + paste route, never HID typing. The avatar overlaps the first letter in OCR (`MOUSE-…`) and the caret corrupts the end, so the composer is not an exact-text proof |
| Media | Toolbar gallery icon (bottom left) → the **system photo picker** (*Cancel, Photos/Collections, Add, Search your library*, newest first, *Select Items*) → tile → blue numbered badge at the tile's lower right, *Show Selected (1)*, *Select up to 4 items* → **Add** | The same picker iOS shows other apps, so it is reusable. Add is disabled until a selection exists |
| Attached | Composer with the video card (duration, `720p`, remove ×, edit), first-use *Mark your media as sensitive* tooltip, *Tag people* | Media match on the card; the × removes media and must not be a target |
| Save | **Cancel** → sheet *Save to drafts* / **Discard** / *Keep editing* → feed | Discard deletes the work: the shared guard already refuses `discard`. *Save to drafts* once |
| Drafts | Empty composer → **Drafts** → sheet (*Drafts / Scheduled*) listing each draft's full text and a media thumbnail | The **exact text proof** belongs here: the full line is read without the avatar or caret. 17 Oct still showed `l`/`I` confusion (`VlDEO`), so test text must avoid ambiguous capitals |
| Reopen | Row → composer with text; the **video preview is blank grey** until its play button is tapped (step 127 then shows the video) | Playback needs one read-only-safe tap on the card's play control; a blank card is not media proof |
| Keep | Cancel → *Save to drafts* again → feed | Same single-press rule as creation |

## 3. Decisions needed before an adapter

1. **Which X account is authorized for C24C drafts.** On 17 Oct the X app was
   signed in to a different handle than the Instagram/TikTok account
   (@xs.halle.xo). The handle appears only in the private OCR. It is not written
   into Git, and no adapter will assume it. Each candidate service currently pins
   one account constant, so X also needs that service setting to become
   per-format.
2. Whether a one-line text proof in the Drafts sheet, plus a matching thumbnail
   and visible playback after Play on reopen, is acceptable evidence for X.

## 4. What an adapter would reuse

- The Safari/Files video import (`ReelCreationWorkflow.import_video`).
- `Workflow.PLATFORM = 'x'`, settled taps, the configurable run service and the
  caret-retry pattern from the TikTok candidate.
- A system photo picker recognizer would be new. Other apps that present the iOS
  picker could reuse it; YouTube's own media picker was not compared.
