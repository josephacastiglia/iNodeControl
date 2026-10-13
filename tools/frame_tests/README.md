# Offline frame delivery and presentation tests

Run from the repository root:

```powershell
dotnet run --project tools/frame_tests/FrameTests.csproj -c Release
```

The project links the production `FrameStore`, `FrameMetrics` and receiver info type. The default suite uses a fake monotonic clock and an in-memory fragmented stream. No window, HTTP listener, named pipe, HID transport, phone, receiver process or installed settings are used. There are 34 cases. The existing kernel self-tests separately exercise real, randomly named synthetic pipes and serialize API status without opening a listener.

An optional transport probe uses its own temporary loopback HTTP listener and a
synthetic 2048x2048 BMP:

```powershell
dotnet run --project tools/frame_tests/FrameTests.csproj -c Release -- --http-self-test
```

It calls the production screenshot response writer. Two TCP clients read headers
but stop reading their bodies; both must cancel after the five-second deadline.
The producer must keep advancing, a third transfer must be refused as busy, and
a later complete response must match the current bytes and sequence. The fixture
maps the busy result to HTTP 503; it is not the full kernel API server. It has no
HID, real receiver, phone or UI code. This probe may need local-listener permission.
It closes all sockets and its listener after success or failure and never uses
the installed rack endpoint.

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

Screenshot metadata and image bytes are captured together under the delivery
lock. A pooled copy is then written asynchronously outside that lock; a slow
client cannot block frame publication or status reads. At most two transfers per
phone retain copies; excess requests receive a temporary busy result without
queueing. Request cancellation, store shutdown or the five-second transfer
deadline aborts the HTTP response. Buffers return only after the writer finishes.
The frame age describes capture for that response, not time spent in transit.

Headers identify that captured image:

- `X-iMouse-Frame-Session`
- `X-iMouse-Frame-Sequence`
- `X-iMouse-Frame-Age-Ms` (invariant decimal formatting)
- `X-iMouse-Frame-Delivery`

Status diagnostics contain matching per-receiver fields and failure messages. The top-level frame fields retain the existing first-receiver convention. Diagnostic exports preserve these fields; missing fields on legacy kernels remain null.

The console rate expires during a stall, with the existing five-second status timer refreshing its text even when nothing is presented. Its FPS report keeps zero samples, resets meters after warm-up and describes its measurement scope. It does not measure physical display scans, source capture time, network delay or actual phone animation. The combined console consumes screenshot metadata for preview/tile freshness warnings; see the preview/wall freshness records. No physical video gate is passed by these tests.
