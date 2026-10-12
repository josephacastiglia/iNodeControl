# Combined candidate: integration checkpoint

12 October 2026. Work takes place in the separate checkout `iMouseXP-2.0-combined-candidate`, branch `local/combined-candidate-20261012`. The original main checkout and Claude worktree are preserved. No deployment or physical acceptance is claimed.

## Combined source

The checkout starts from the main line at `01fb669` and merges `claude/input-timeout-integration` at `d0c4ccf`. The recorded working patch carries the October offline diagnostics, timing/endurance, accuracy, receiver-memory, frame-freshness and phone-wall work. New source/test files are copied with hashes recorded in the original checkout's `analysis/combined-candidate-20261012/`.

Two text conflicts were resolved deliberately: both sets of console self-tests are retained; kernel status uses the new frame-status method and retains the integration branch's `home_sequence` field. A regression verifies that field remains present. The chunk size remains 12, the cap remains temporary, the original Home sequence remains the default, and the deferred missing-space issue is not worked on or marked fixed.

## Further repairs in this checkout

- Candidate startup rejects drive/share roots, duplicate data folders, Windows reserved names and trailing-dot/space aliases. The drive-root regression failed before repair. A subsequent test caught Windows normalizing names before validation; the original spelling is now checked too.
- An isolated candidate's address is validated before constructing a window, creating a directory or saving settings. Empty, duplicate, portless and malformed addresses are refused. A port embedded in an IPv6 host cannot masquerade as an explicit service port; explicit ports 80 and 443 remain explicit instead of falling back to 9911. Saved candidate settings are read only when an explicit address is absent.
- `--validate-startup` performs offline candidate preflight with no window or connection. It writes a report beside the executable, not into candidate or operator settings. This is structural validation, not a live service check.
- The visible console build label and exported diagnostics identify the actual managed DLL and loaded module. The identity is captured at startup; a fixed label no longer makes different builds indistinguishable. The old string `build` field is retained with the actual version and an additional structured `build_identity` field (diagnostics schema 2).
- `build-console.ps1` builds the authored SDK project and its standard apphost. The legacy custom launcher dropped isolation arguments and used separately generated XAML. The script now produces the same managed bytes as the direct SDK build and forwards arguments unchanged. It requires the .NET SDK and does not launch an application. Its historical output default is unchanged; this work passes only scratch output paths.

- Invalid pointer origins and scales that overflow the movement coordinate conversion are now rejected before any hardware handle opens. The regression failed against the old constructor; seven new kernel checks pass. Normal calibration/pointer behavior is unchanged.
- The existing rack checker now distinguishes structural validity, incomplete bindings and physical acceptance. It checks duplicate mappings, port collisions, malformed JSON and calibration arithmetic, permits per-phone calibration values, and never rewrites configuration. Its default planned-rack run exits 2: 19 receivers, five explicit saved bindings, 14 unbound. Physical readiness remains unassessed.

## Validation

| Suite | Passing checks |
|---|---:|
| Combined console self-tests | 220 |
| Combined kernel self-tests | 110 |
| Selected-preview parser/API | 36 |
| Wall lifecycle and simulated 19-phone scheduler | 22 |
| Frame store and metrics | 25 |
| Receiver supervision | 12 |
| Input cleanup harness | 33 across nine scenarios |
| Diagnostics exporter | 20 |
| Build manifests | 9 |
| Endurance analysis | 15 |
| Endurance runner safeguards | 16 |
| Timing runner | 22 |
| Package staging | 22 |
| Accuracy evidence guards | 17 |
| Accuracy scenarios | 14 |
| Receiver analysis tools | 8 |
| Rack configuration validation | 18 |
| No-window data-path probes | 4 |
| No-window startup-validation probes through SDK apphost | 8 |

631 checks in total, with test scopes as named. No physical phone was addressed. Kernel self-tests use fake HID transports and synthetic frame pipes. The sandbox refused a private pipe; the same suite passed under the approved unrestricted test invocation. The cleanup harness uses private loopback listeners, synthetic video and simulated boards; all nine scenarios pass, including delayed/failed answers, confirmed/unconfirmed cleanup, lease expiry and stale-release isolation. An initial parallel harness build failed without a diagnostic; its serial build passed with zero warnings/errors. Those logs are retained.

The Python driver initially named a nonexistent receiver `test_probe.py`; it was not counted as a pass. The actual `test_tools.py` was subsequently run and passes eight checks. Existing native leak tests are preserved from the previous source-equivalent record, not claimed as rerun here.

No UI automation suite was run: it opens windows. The displayed label, layout, real typing, App Switcher and Home behavior still require the appropriate later acceptance work. Tests of the simulated Home variants do not prove iOS behavior.

## Preserved state and next work

The original main working files and three installed binaries were hash-checked unchanged. No screen control, phone input, receiver advertisement, operator settings change, installed-process restart, upload, or push. Test processes finish; no development server is left intentionally running.

The combined candidate remains unpromoted. Packaging is review-only until runtime/configuration and interactive/physical acceptance are complete. Continue offline with rack-configuration validation and release readiness, preserving the written gate requirements. Source/build manifests and an external archive record the final checkpoint separately.

## Local checkpoint

The source integration merge is `f5c70ec`. Follow-up calibration/readiness fixes are committed separately. The final console build passes 220 self-tests; the final kernel passes 110. No-window probes and non-product harness results above retain their individual build records; this total is not a claim that every test was rerun on every binary. Imported October evidence is stored without Git newline conversion.

## Review package and preservation

Checkpoints `f5c70ec` and `2c29852` are local only. `output/staging/combined-review-20261012/` contains 132 verified files plus its manifest. Its ZIP passes the included verifier after extraction (SHA-256 `ef2e6963c5f8ce594a97bb192953d4a216463ac31b545b7e00ffed76e98117cd`). See `ARCHIVE.json` for the 74-file external archive, tested binaries and Git bundle. The receiver build sources in the package use exact original bytes; all 79 combined-checkout native inputs differ only by CRLF/LF encoding. An initial staging refusal correctly caught that byte difference.

The original working source and installed DLLs/receiver were rechecked unchanged. Only a continuation pointer was then intentionally added to the original checkout's PROGRESS.md. The archive was created before this final packaging addendum; this addendum and final archive metadata remain in Git. No live readiness or product acceptance is implied by file integrity.
