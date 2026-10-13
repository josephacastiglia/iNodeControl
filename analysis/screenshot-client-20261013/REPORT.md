# Console screenshot transfer repair

13 October 2026. Offline work only: no screen control, rack request, kernel or
receiver restart, settings change or phone input. The new console is not
installed, promoted, pushed or included in the preceding review package.

## Reproduced failures

The reusable image path used `ResponseHeadersRead`. The HTTP client's existing
eight-second timeout ended when headers arrived; subsequent stream reads used
only the caller's lifetime token. A stalled body therefore held the preview
request indefinitely until the caller cancelled. A test with a 13-second escape
ended only at that escape (13,014 ms). A second test delivered headers after
three seconds and body after another six: the old client accepted it at 9,025 ms.

The same reader set the reusable buffer's Length only at the end. When an
unknown-length response grew beyond the initial 2 MiB, `Ensure` copied zero
bytes and lost the prefix already downloaded. A larger synthetic response then
failed image recognition. The old code used 64 MiB only as a preallocation
condition, not a response limit, and could continue allocating/reading beyond it.

Eight focused checks were added to the existing preview suite. The original
product passes 38/44 overall: **six new cases fail**. Caller cancellation and
body I/O cleanup already pass. The failures and original linked source/build
are preserved in `before-tests.txt`, `before-source/`, `before-preview/` and
`before-manifest.json`.

## Repair

- One linked request deadline covers headers and the complete body, using the
  existing eight-second setting. Caller cancellation still ends it earlier.
- The buffer tracks received bytes while reading so growth preserves the
  prefix. Failure clears Length and metadata before control returns to the caller.
- Responses over **64 MiB** are refused, including streams without a stated
  length. A one-byte overflow probe distinguishes an exact-limit response
  from an oversized one without growing the buffer again.
- Responses and streams are disposed on every exit. Legacy base64 responses
  and metadata pairing remain supported.

This changes image fetching only. It does not pause input, retry input commands,
take a lease or change Stop/Resume behavior. Existing preview/tile callers keep
their retry policy. The separate allocating screenshot method already uses
fully buffered HTTP completion and its existing 32 MiB HTTP buffer limit; it
is unchanged. The new response limit is not a total process-memory bound.

## Validation

| Check | Result |
|---|---|
| Preview suite, final source | 44/44 pass; stalled body 8,009 ms, combined headers/body 8,008 ms; caller not cancelled |
| Existing wall scheduling/lifetime suite | 22/22 pass |
| Full console self-tests | 382/382 pass, all command transport mocked |
| Console, preview and wall builds | Zero warnings and errors |
| Real loopback HTTP probe | Body timeout 8,009 ms; HTTP 503 clears evidence; larger chunked response recovers with every byte preserved |

The headless fixtures check transport bytes, response disposal, bounds,
cancellation and freshness evidence. They do not decode or present the
synthetic image pattern. Exact-limit and over-limit streams are generated a
chunk at a time. The optional real HTTP probe binds only an ephemeral loopback
port, validates its own screenshot GETs and awaits server cleanup. It starts
no kernel or hardware component. It does not verify the WPF retry interval or
the server's busy-response implementation.

The first loopback attempt was blocked by the sandbox's socket permissions;
the first console suite was blocked replacing a temporary diagnostics file.
Those logs remain in `loopback-restricted.txt` and `self-test-restricted.txt`.
An initial automatic permission review timed out without a decision. The
single retry approved the narrowly scoped offline verification, which passed.
`run_verification.py` records the successful exits and checks protected installed
hashes before and after; it gives tests their own temporary folder. No UI tests
or live APIs ran. The stale first-attempt failure file remains with that tested
working output as evidence; the final success is `self-tests.json` and
`verification.json`, not absence of a failure filename.

## Exact build and preservation

`console-artifacts/` contains only the five byte-matched build artifacts copied
from the tested output. `console-manifest.json` records these plus 36 source
inputs. DLL SHA-256:
`1eaaf9beb41987c21f70a1ab5f79529bb1eb5d5f0ce753a4aae3078221b9e554`.
The version stamp names base `a170ff1`; the working source manifest identifies
this repair. Preview/wall manifests also include their explicitly linked
product source. The earlier `final-preview` output was an intermediate
44-check run before adding the opt-in loopback probe; `verified-preview` is
the final recorded test tool.

`archive_run.py` preserves this record, original and repaired binaries/source,
results, focused patch and supporting documents outside TEMP under
`iMouseXP-2.0-evidence-archive/20261013-screenshot-client`. Every copied hash
is checked. `archive-verification.json` records completion separately.

The existing `combined-recovery-20261013` package remains unchanged and contains
the older console. Reassemble into a new immutable package before claiming all
repairs were tested together. Actual console presentation, real rack/video load,
interactive export, clean-PC loading and physical acceptance remain open. No
gate advanced. Typing is still deferred and C241 remains outside input scope.
