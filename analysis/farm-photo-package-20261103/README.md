# Shared photo-package layer (3 Nov, offline)

Built once for the two blocked priority-3 lanes, X image (A17, board 724E) and TikTok photo with its sound kept
(A20, board C214), so that each lane only has to add its own workflow, verifier and runs class. No phone, rack,
kernel or socket beyond loopback tests was used. Nothing here has been run on a phone.

## What lanes plug into

| Piece | Name |
|---|---|
| Formats | `farm_image.IMAGE_FORMATS` = `x_image` (X), `tt_photo` (TikTok); `SLIDES` = 1..1 and 2..10 |
| Canvas | `farm_image.CANVAS`: `x_image` 1080x1350 on white, `tt_photo` 1080x1920 on black; each image is fitted whole, never cropped |
| Draft store | `farm_image.ImageDrafts(database, stage_root, board)`: `sources()`, `create(request)`, `export(id, revision)`, `get`, `list` |
| Create request | `id`, `device_id`, `format`, `images` = ordered `[{name, sha256}]` from the board's stage manifest, `title`, `caption`, optional `source_generation` + `manifest_sha256` |
| Package | stored zip: `manifest.json`, `caption.txt`, `01.jpg` ... `NN.jpg` |
| Manifest | `id`, `revision`, `title`, `caption`, `deviceId`, `format`, `platform`, `published: false`, `savedInApp: false`, `assets[]` = `file`, `sha256`, `bytes`, `width`, `height`, `sourceName`, `sourceSha256`, `sourceWidth`, `sourceHeight`, `fitted`, `upscaled` |
| Delivery | `farm_media_transfer.TransferPackage(raw, board)`: `images` (ordered `{'01.jpg': bytes}`), `caption`, `title` (`X image draft` / `TikTok photo draft`), `format`, `app`, `board`, `download_name` (`imouse-xi-xxxxxx` / `imouse-tp-xxxxxx`) |
| Transfer page | the carousel layout: index `Open slide N of M`, `Copy caption`; slide page `Slide N of M`, touch and hold the image, `Save to Photos`, `Next slide →` / `Back to caption`; index also shows `Package <download_name>` |
| Per-image counting | `MediaTransferServer.image_requests`; `farm_media_transfer.image_delivery(events, files)` -> `imageRequests`, `imagesDelivered`, `everyImageDelivered`, `photosSaveProvenByHttp: false` |
| Reference | `farm_image.ImageReference(images)`: `models[name] = (shape, targets)` for `fill`, `square`, `portrait`, `card` (centre crops, same shapes as `TikTokReference`) and `fit` (whole image on black, 9:16); `fill`, `square`; a matcher's `index` is the 0-based slide; `slide(i)` = slide i only; `hashes`, `count` |
| Runs base | `farm_reel_runs.ImageCreationRuns`; content identity `farm_reel_runs.image_content(package)` |
| Lane classes | `farm_x_runs.XImageCreationRuns` (FORMAT `x_image`), `farm_tiktok_photo_runs.TikTokPhotoCreationRuns` (FORMAT `tt_photo`); `farm_reel_runs.LANE_RUNS` names them |
| Routes | `/api/farm/x-image-creations`, `/api/farm/tiktok-photo-creations` (eligibility, list, run, frames, start, cancel); `/api/farm/image-sources`, `/api/farm/image-drafts` |
| Capabilities | health `xImageCreation`, `tiktokPhotoCreation`, `imageDraftsVersion`; coverage rows `x_post` and `tt_photo_carousel` carry the routes and `draftFormat` |
| Windows | `prepare_window.py --platform x-image --slot 17` (1 test slide), `--platform tiktok-photo --slot 20 --account <handle>` (3 slides); window names `x-image-slot17`, `tiktok-photo-slot20`; preparation names `draftId` |

A lane class sets `FORMAT`, `LABEL`, `action_name` (`create-x-image-draft`, `create-tiktok-photo-draft`),
`workflow`, `verifier`, `committing` (the purpose prefixes that may have saved a photo or a draft),
`caption_supported`, `PINNED_ACCOUNT` (X False, TikTok True) and its reason texts. Until it does, the route
reports `enabled: false`, 'not built yet', and refuses to start; `verify_window.py` refuses before reading anything.

Calls the base makes:

```
workflow(folder, kernel, store, images, caption, references(), kernelSha256, expectedUid,
         transfer_url=..., transfer_title=..., package_name=..., slides=['01.jpg', ...],
         account=..., package_hash=..., cancelled=..., allowed=...)
verifier(folder, kernel, store, images, caption, references(), kernelSha256, expectedUid,
         account=..., package_hash=..., cancelled=..., allowed=...)
```

The verifier runs only if creation returned `created_unverified` with cleanup and evidence export confirmed and
every slide was requested over HTTP at least once.

## Unchanged

- The C24C carousel: `TransferPackage(raw)` still requires C24C and `ig_carousel`; its pages are byte-identical
  (golden hashes in `tools/test_farm_image.py`), and a carousel package is refused for any other board.
- Video runs: `ReelCreationRuns.execute` now goes through hooks (`transfer_package`, `media_reference`,
  `workflow_media`, `delivery`); the workflow keywords and the `mediaDelivery` record are the same (regression
  test in `tools/test_farm_image.py`).
- `farm_transfers.CarouselTransfers` (the supervised C24C transfer) was not changed.

## Re-prepare

`farm_reel_runs.py`, `farm_media_transfer.py`, `farm_format_coverage.py` and the server changed and
`farm_image.py` is now fingerprinted (server and `Open Marketing Farm Candidate.ps1`), so every prepared window's
`backendSourceHash` is stale: re-prepare windows after this merges.

## Not validated

Nothing on a phone: touch and hold plus Save to Photos on A17/A20 Safari, the slide page geometry on those
models, how X and TikTok show these canvases, and whether the crop models match the apps' tiles.
