# Marketing Farm feature validation

**Result: the new farm features are only partly functional. They are not ready for live unattended use.**

Tested 16 October 2026 against the current combined-candidate working tree, based on
`70f18285d2f845ea154bbc3f46436673d6e19b51`. This is the source after the earlier
execution-mode and C24C boundary fixes, not a test of the historical running r4 binary.
This validation added tests and records only; it made no product-code fixes.

## Results

| Check | Result | What it establishes |
| --- | --- | --- |
| Release console build | Pass; zero warnings/errors | Source compiles into a separate output folder |
| Console headless self-tests | 417 passed | Existing console logic and mock input checks |
| Farm execution-boundary tests | 17 passed | Explicit simulation, live refusal, C24C targeting, guarded proxy, DB cleanup |
| Expanded farm feature tests | **18 passed, 14 failed**; zero errors/skips | The feature failures below are reproducible without a phone |
| Existing server self-check | Pass, simulation only | Routes execute against mock data; it does **not** prove OCR, DMs or real uploads |
| Additional HTTP checks | Completed on a disposable server | Confirmed zero-session warmup, directory traversal and malformed-JSON failure through actual HTTP |
| Physical input, actual WPF clicks, account actions | Not run | No claim of phone or on-screen acceptance |

All feature fixtures used temporary databases and media folders. A network guard
blocked every network destination for the in-process tests. HTTP checks allowed
only the temporary loopback server; the existing server self-check blocked rack
ports and external destinations. No PC control, phone input, shared-settings
change, installed-release change, deployment or push occurred. Temporary servers
closed after testing.

## What works in the tested scope

- Simulation is clearly identified, and state/scheduler status return the expected
  fixture data without sending input. Scheduler dry runs dispatch nothing.
- With the persona name `C24C`, warmup and upload execute simulated command
  sequences and release their leases. An already-owned phone is refused; a
  failure early in upload stops later steps and releases the lease.
- A Stop during simulated warmup causes an error and lease cleanup. Stopping one
  mock phone leaves the other mock phone's lease intact. These checks do not
  establish complete job cancellation or persistent Stop behavior.
- A 100-character string reaches the mock transport unchanged in nine chunks of
  at most 12 characters. A timed-out second chunk is not retried. This does not
  revalidate the deferred iOS/FKA first-space issue.
- Generated media decode locally: four 540×675 JPEGs and a 360×640 MP4 with video
  frames. The exported Shortcut plist parses and references the intended test
  manifest; importing or running it on iOS remains untested.
- Requests with a disallowed Origin are refused, and ordinary staged-media
  responses preserve their file bytes.

## Reproduced failures

Each numbered row below corresponds to one failed test. Failures remain ordinary
test failures, not suppressed or marked as accepted behavior.

| # | Feature | Observed failure | Location |
| --- | --- | --- | --- |
| 1 | Warmup from the console | The hardware ID supplied by the UI returns HTTP 200 with `sessionsRun: 0`; persona-name `C24C` works. | `imouse_farm_server.py:400–411` |
| 2 | Upload from the console | The same hardware ID returns HTTP 500, “Unknown persona device_id.” | `imouse_farm_server.py:377`; `imouse_social_automation.py:2279` |
| 3 | Funnel button | Its payload routes to pin-comment, although the UI advertises Comment-to-DM. The routing test stubs leaf actions; no message was sent. | `MainWindow.FarmTab.cs:340`; `imouse_farm_server.py:442` |
| 4 | Mixed live-mode wave | With a fake transport, C24C receives a swipe before the wave refuses C241. Individual target protection works, but the whole selection is not checked before starting. | `imouse_farm_server.py:413` |
| 5 | Stop confirmation | An empty kernel reply is reported as successful Stop because a missing result code defaults to zero. | `imouse_farm_server.py:462` |
| 6 | Stop test fidelity | The mock clears ownership but always reports `stopped: false`; it immediately permits another preflight. This is a mock defect, not proof of a real-kernel defect. | `imouse_social_automation.py:3237,3263` |
| 7 | Keyword recognition | A completely white image with no text is reported as matching `TESTWORD`. | `imouse_social_automation.py:2091` |
| 8 | View-count recognition | A uniform gray image produces invented view counts `[180,270,360]`. | `imouse_social_automation.py:2103` |
| 9 | Text length | A 201-character input is silently cut to 200 rather than refused. | `imouse_social_automation.py:2168` |
| 10 | On-screen keyboard text | An unsupported emoji is silently dropped without reporting an error. | `imouse_social_automation.py:2200` |
| 11 | Media file access | `/stage/../outside.txt` returns a file outside the staging folder. Confirmed through HTTP using only a harmless marker in a disposable directory. | `imouse_farm_server.py:306` |
| 12 | Invalid request handling | Malformed JSON escapes the handler; HTTP closes without a structured error response. | `imouse_farm_server.py:357–359` |
| 13 | Missing video encoder | Simulating unavailable OpenCV produces a supposed MP4 which ffprobe rejects: “moov atom not found.” The normal installed-encoder path passes. | `imouse_social_automation.py:1180` |
| 14 | Media checksum | `manifest.sha256Hex` contains a 16-character digest, not the actual 64-character SHA-256 of its staged video. | `imouse_social_automation.py:1537–1546` |

## Repair order

1. Close staging-path traversal; validate request bodies and require explicit
   Stop confirmation. Prevent unverified image observations from authorizing
   public actions or messages.
2. Fix UI-to-server identity and action contracts; preflight entire target
   selections before dispatch. Add proper console/backend control handover and
   cancellable jobs. The latter are still implementation gaps, not established
   by a successful simulated Stop response.
3. Refuse unsupported/oversize text, correct media checksums, and report missing
   encoders clearly. Make the mock model persistent Stop before relying on it
   for cancellation acceptance.
4. Rerun these tests after fixes. Only then schedule narrowly scoped UI/phone
   checks for preview targeting, real media import/upload, observed state and
   control handover. Current tests authorize no posting or messaging.

## Evidence and reproduction

- `results.json`: every expanded test result, failure traceback, dependency
  versions and source SHA-256 values.
- `feature-tests.txt`: final 32-test output. Earlier probe outputs are retained
  separately; the final run supersedes their counts.
- `http-boundary-results.json`: actual HTTP responses from the isolated server.
- `console-self-tests.json`, `console-build.txt`, `execution-safety-tests.txt`,
  `server-self-check.txt`: established-suite results.
- `verification.json`: tested source/binary inventory and preservation record.

Console output: `output/codex-farm-validation-20261016`. It was run only with
`--self-test`, never launched as the working console. The initial sandbox denied
a temporary-file rename and loopback socket access; those infrastructure failures
are retained separately. The same headless/mock checks then completed with the
required filesystem/socket permissions.

From the repository root, with the project's Python dependencies installed:

```powershell
python tools/test_farm_feature_validation.py --report analysis/farm-feature-validation-20261016/results.json
python -m unittest discover -s tools -p test_farm_execution_safety.py -v
python analysis/farm-feature-validation-20261016/verify-http-boundary.py
```

The first command intentionally returns exit code 1 while the documented defects
remain. Do not turn these assertions into unconditional passes to obtain a green
report. No ordinary UI test or desktop automation was used.
