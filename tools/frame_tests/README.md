# Offline frame delivery and presentation tests

Run from the repository root:

```powershell
dotnet run --project tools/frame_tests/FrameTests.csproj -c Release
```

The project links the production `FrameStore`, `FrameMetrics` and receiver info type. Tests use a fake monotonic clock and an in-memory fragmented stream. No window, HTTP listener, named pipe, HID transport, phone, receiver process or installed settings are used. There are 25 cases. The existing kernel self-tests separately exercise real, randomly named synthetic pipes and serialize API status without opening a listener.

## What the measurements mean

| Measurement | Meaning |
|---|---|
| Kernel `frames` / screenshot sequence | Complete validated BMP deliveries; identical images count again |
| `frame_session` | FrameStore instance identity; sequence stays cumulative through pipe reconnects |
| `frame_age_ms` | Monotonic time since the last complete validated BMP; null before any frame |
| `frame_pipe_connected` | Whether a producer connection is currently being read |
| `frame_delivery` | `waiting`, `flowing`, `quiet`, `stopped`, `disconnected`, `invalid_frame`, `io_error` or `reader_error` |
| Console updates/s | WPF bitmap presentation calls after pixel deduplication |
| Console presentation intervals | Last 240 completed gaps, including gaps longer than five seconds |
| `sinceLastPresentationMs` | Current unfinished gap, distinct from completed intervals |

`quiet` means no new BMP for at least two seconds while a cached picture is still available. It is a diagnostic threshold, not a freeze verdict, automatic restart or input cancellation. An unchanged phone can be legitimate. Original `live` and `receiver_state` semantics stay compatible: availability of a cached picture does not prove that delivery or the phone has advanced. Age is retained after disconnect/stop to explain the last received frame; availability is false.

Screenshot headers are added while holding the same lock as the image write:

- `X-iMouse-Frame-Session`
- `X-iMouse-Frame-Sequence`
- `X-iMouse-Frame-Age-Ms` (invariant decimal formatting)
- `X-iMouse-Frame-Delivery`

Status diagnostics contain matching per-receiver fields and failure messages. The top-level frame fields retain the existing first-receiver convention. Diagnostic exports preserve these fields; missing fields on legacy kernels remain null.

The console rate expires during a stall, with the existing five-second status timer refreshing its text even when nothing is presented. Its FPS report keeps zero samples, resets meters after warm-up and describes its measurement scope. It does not measure physical display scans, source capture time, network delay or actual phone animation. The console does not yet consume the new screenshot metadata for an operator-facing freshness warning. No physical video gate is passed by these tests.
