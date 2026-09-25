# FPS and latency optimization audit — 14 September 2026

## Conclusion

The current two-phone console retains the earlier console's core FPS and
anti-lag optimizations. No missing optimization was found among the reviewed
paths. This is a source and compiled-instruction audit, not a new live latency
benchmark. Two-phone input tests were paused at the user's request; no phone
commands were sent during this audit.

The visible app is `release/iMouse2-two-phone/iMouse2.exe`, process 2804.
The independent kernel is `release/iMouse2-kernel-two-phone/iMouse2.Kernel.exe`,
process 32328. AirPlay video comes from our modified UxPlay, with a separate
receiver for each phone.

## Compiled comparison

The local utility in `tools/performance-audit/` reads PE metadata and method IL
without executing the compared applications. It resolves ordinary metadata
tokens to names and compares selected method instructions. Generic signature
blobs retain metadata indices, so they may report differences after compiler
metadata renumbering. This is not an equivalence proof for the whole program.

| Baseline under release/ | Selected methods | Matching normalized instructions | Missing |
|---|---:|---:|---:|
| iMouse2 | 51 | 50 | 0 |
| iMouse2-net | 51 | 46 | 0 |
| iMouse2-independent | 51 | 51 | 0 |

Against the first iMouse2 build, the only changed selected method is the master
frame pump: it now refreshes the input freshness timestamp when a successfully
fetched frame has unchanged pixels. The existing deduplication and pacing remain.
The iMouse2-net differences also include generic signature metadata renumbering.
Full results, binary SHA-256 hashes, and instruction differences are saved in
`binary-comparison.json` and `differences/`.

## Retained optimizations

| Optimization | Evidence in current source |
|---|---|
| Raw BMP over loopback, no JPEG in the live loop | ApiClient.ScreenshotIntoAsync called with jpeg=false |
| Reused HTTP receive buffers | FrameBuffer; two alternating buffers per master/tile pump |
| Avoid HttpClient's extra whole-body buffer | ResponseHeadersRead and streaming into existing arrays |
| Pooled decoded pixels | LiveFrame.Rent/Recycle, pool capped at four buffers |
| Reuse display bitmap | LiveFrame.Present creates a WriteableBitmap only on format/size change |
| Background preparation | PumpAsync and TilePumpAsync prepare frames off the UI thread |
| Latest-frame presentation instead of a backlog | One pending master frame; superseded buffer recycled |
| Prompt presentation | Render-priority dispatch plus CompositionTarget.Rendering backstop |
| Skip duplicate pictures | Full-byte SequenceEqual; avoids missing small pointer changes |
| Short polling and idle backoff | 5 ms default polling, progressively backs off on unchanged screens |
| Short transient-error recovery | First 12 failures retry after 8 ms; prolonged failures back off |
| Fine timer resolution | Console and kernel request 1 ms resolution, release at shutdown |
| Separate master/tile FPS settings | Rate_Changed and WallRate_Changed; current UI shows 30 FPS for both |
| Bounded wall load | At most three tile fetches in flight; per-tile period also considers wall size |
| Smaller tile rendering | Box-average reduction on worker before presenting small thumbnails |
| No tile pause during dragging | TilePumpAsync explicitly keeps preview polling during gestures |
| Coalesced hover/drag movement | Latest requested point wins; stale movements do not accumulate |
| Background input loop | Pointer and drag HTTP work runs off the UI thread |
| Diagnostics | Rolling FPS and p50/p95 presentation-gap meter retained |

## Limits of the independent backend

- Running UxPlay arguments include `-fps 30` and `-avdec`: a 30 FPS request and
  forced software decoding. The console's Maximum setting cannot by itself
  raise that receiver request. No GPU-decoder performance comparison was run.
- The bridge uses reusable BMP memory and appsink settings max-buffers=1,
  drop=true, sync=false. These help keep the most recent decoded picture.
- The bridge still performs blocking named-pipe writes in the sample callback.
  FrameStore holds its per-phone lock while writing a BMP to HTTP. A slow
  reader can therefore create backpressure; no timing bound was established.
- Tile reduction happens in the console, after the full 500x1080 BMP is fetched.
  It reduces rendering work, not loopback transfer volume.
- Direct HID movement uses relative steps with at least 3 ms between reports.
  Mouse click/down/swipe settlement adds 120 ms; a click holds for 80 ms.
  These deliberate reliability delays differ from the old vendor input path.
  Retained console coalescing does not remove backend execution time.
- Historical measurements are not an apples-to-apples speed comparison:
  the old iMouse2-net fps.json records 19.9 presented FPS over eight seconds;
  the later stability run reports about 20.5 received frames/sec over 45 minutes.
  They measured different quantities under different conditions.

## Cleanup performed

A hidden duplicate two-phone console (PID 33044) from an earlier launch remained
running alongside visible PID 2804. It used about 200 MB working set and had
accumulated CPU time. Its exact executable path was verified and that duplicate
alone was terminated. The visible console, kernel, and receivers stayed up.
This removes redundant process load; no FPS improvement was measured or claimed.

No application source or production build was changed during this audit. Only
the audit utility/results were added and the duplicate process was removed.
The next performance work, if requested, should measure receive-to-present
timing and input latency separately before changing the receiver or HID delays.
