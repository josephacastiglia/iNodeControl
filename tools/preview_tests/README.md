# Offline selected-preview freshness checks

```powershell
dotnet run --project tools/preview_tests/PreviewTests.csproj -c Release
```

36 tests link the actual `ApiClient`, ownership client and `PreviewFreshness` source. Every HTTP handler is injected and refuses anything except a mock screenshot GET. No ownership client is activated, no socket fallback exists and no WPF window, phone or installed settings are used.

The parser validates all four delivery headers. Invalid, missing, duplicate or partial metadata leaves the image usable with unknown age. Request elapsed time is added conservatively to the server-reported delivery age; this is not a phone capture timestamp or exact network latency.

The tracker pairs metadata with presented content revisions. New BMP delivery with identical pixels updates the status without a redraw. Polling the same delivery cannot make it younger. A changed frame that was skipped or replaced cannot refresh a different image. Manual refresh and continuous polling keep separate comparison histories. Selection epochs and request order reject old-phone and late responses; pending content cannot overwrite a newer presented refresh.

The selected-phone header and Activity status show recent delivery, unknown age, a potentially old preview or failed updates. The existing five-second status timer ages the text even when there are no new images. Pausing preview explicitly labels it paused. No status starts input, takes ownership, restarts a receiver, toggles a setting or automatically changes Stop/Resume. The existing input-availability behavior remains separate.

This batch does not add freshness labels to the smaller wall tiles or prove physical frame presentation. WPF markup is build-checked; no interactive layout/phone acceptance test is claimed.
