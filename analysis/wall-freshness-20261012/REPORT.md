# Phone-wall delivery status and isolation

12 October 2026. Completed offline on `local/coordinator-work`, base `01fb669`; source remains uncommitted. This extends the selected-preview freshness work already present in this checkout.

## Result

Each small phone tile now shows Recent, May be old, Age unknown, Waiting, No updates, Paused or Offline. Its tooltip preserves the phone identity and control state alongside the delivery explanation. Update rates use `/s`, describing changed bitmap presentations rather than source FPS. The fixed-size overlay cannot intercept clicks. Input readiness and following rules are unchanged.

Every tile has its own cancellable stream and delivery/rate state. Removal, reconnection, disconnect and window close retire old streams. Reference checks prevent late completions from publishing into or removing a replacement for the same phone. A shared limiter allows three screenshot requests; decoding, UI work and retry delays occur outside its slots. Screenshot timeouts show a delivery failure and retry instead of silently ending the tile pump. Skipped or undecodable presentations invalidate pixel deduplication so a later identical image can still be shown.

## Validation

| Check | Result |
|---|---|
| Wall lifecycle, scheduler and 19-phone simulation | 22 passed |
| Selected-preview metadata/API regression | 36 passed |
| Synthetic frame and metric regression | 25 passed |
| Console mock self-tests, including six new tile-model checks | 118 passed |
| Release console scratch build | Zero warnings/errors |
| Source/build manifest | 17 source inputs and six output files verified |
| Installed kernel, console and receiver hashes | All unchanged |

Total: **201 passing checks**. See the adjacent logs and `console-build/qa/self-tests.json`.

The simulated rack demonstrates independent status, a three-request ceiling, progress by 18 peers while one is held, queued/active cancellation, timeout recovery, failed-slot recovery and rejection of late results. Tests use actual scheduler/API code with injected handlers; no sockets, phone input or ownership requests. Registry tests do not execute the WPF pump itself; markup and its integration compile, and the view-model bindings have mock self-tests.

## Limits and preserved state

No GUI test or visual layout inspection was run. Synthetic 19-phone scheduling is not physical 19-phone performance acceptance. A quiet stream can be a still screen, so it is labelled potentially old rather than declared frozen. Legacy services report unknown age. Status aging uses the existing five-second timer between incoming images. The limiter cannot forcibly end a transport that ignores cancellation; the production HTTP client supplies its timeout.

No live rack API, desktop control, phone input, setting changes, receiver advertisements, restart, install, promotion, commit or push. No missing-space/FKA work was resumed. Other existing checkout changes were preserved.

Before snapshots and a focused patch accompany this record. A full source/build/evidence copy is preserved under `../iMouseXP-2.0-evidence-archive/20261012-wall-freshness/`, with SHA-256 checksums. Physical display/latency/load and release acceptance remain open.

## Next offline priority

Prepare a verifiable release staging bundle from the tested scratch outputs: explicit source manifests, required runtime assets, startup/configuration checks and rollback documentation. Keep installed paths untouched; packaging is not deployment or a declaration that the open physical gates pass.
