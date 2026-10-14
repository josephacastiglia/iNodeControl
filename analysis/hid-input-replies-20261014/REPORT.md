# Incoming board replies: C24C validation and candidate diagnostics

Date: 14 October 2026. Worktree: `iMouseXP-2.0-combined-candidate`, branch
`local/combined-candidate-20261012`, starting commit `567bded`.

## Result

Two short C24C-only captures collected **25 input reports: 23 A1 movement
signals and two AF status reports**. This confirms that this board produces
readable input reports while the installed kernel controls it. It does not
establish a command acknowledgement, successful iOS action, or round-trip time.

The candidate now has optional, board-scoped reply diagnostics. Its normal
startup remains unchanged: reading replies is **off by default**. The installed
release, settings, kernel, console and receivers were not replaced or restarted.
No C241 input, screen control, keyboard trial or FKA change occurred.

## Method and provenance

The user reconnected C24C and left it on Home. Preflight checked its saved
phone/board/receiver binding, live video, free input state, release process
identities and executable hashes. The reader refuses any live board argument
except C24C. C241 rejection is tested by a pure argument parser without opening
a device.

The installed kernel's PDB does **not** match its DLL. A source checksum in that
PDB therefore cannot establish the running source. The recorded static IL audit
instead inspected `HidConnection` and its nested state-machine types in the actual
installed DLL: writes/flushes are present, with no input-read call in that
transport. This is a scoped audit, not proof that no other program could read
the device. Preflight also found no running vendor service or capture helper.
See `release-il-audit.json` and the per-run audit records.

Each capture used a separate `GENERIC_READ` handle with shared access, verified
HID capabilities (usage page FF00, 17-byte input, 9-byte output), and asynchronous
reads. It made no USB writes, polling changes or queue flushes. All writes went
through the unchanged release's normal lease API:

1. Acquire C24C for 30 seconds and start a bounded reader.
2. Record an idle interval, reset the pointer, and make four small moves near
   the calibrated top-left origin. No button was pressed.
3. Release the lease in finalization, drain briefly, stop/join the reader, and
   verify both phones' ownership and release processes/files.

Windows supports input reads through a handle opened on a HID collection.
Its input buffering also means a small capture cannot establish that every
device report was received. See Microsoft's [HID collection guidance](https://learn.microsoft.com/en-us/windows-hardware/drivers/hid/opening-hid-collections)
and [report troubleshooting guidance](https://learn.microsoft.com/en-us/windows-hardware/drivers/hid/troubleshooting-hid-reports).

## Observations

| Run | Pattern | A1 | AF | Cleanup |
| --- | --- | ---: | ---: | --- |
| `live-01` | Reset; right, down, left, up | 11 | 1 | Confirmed |
| `live-03` | Reset; positive/negative diagonal, right, left | 12 | 1 | Confirmed |

`live-02` aborted during preflight because this session's offline kernel
self-test was still running and the strict process check found two kernel
processes. It acquired no lease, opened no reader and sent no phone command.

Both successful captures returned only 17-byte reports with report ID zero.
Every small move's receipt window contained two A1 reports. The reset windows
contained three and four A1 reports respectively, plus one AF each. The idle
and release/drain windows contained none. These are temporal windows measured
by the capture process, not uniquely correlated command responses.

For the 23 A1 samples, payload bytes 1–3 are consistent with button/delta echoes,
and byte 4 equals `(0x80 + byte1 + byte2 + byte3) modulo 256`. That expression is
an observation, **not a validated integrity check**, and the parser does not
enforce it. Trailing bytes vary between zero and FF and remain uninterpreted.
`live-analysis.json` preserves every observed payload pattern and window count.

AF occurred in both otherwise successful pointer checks. Its meaning is unknown;
there is no basis here for treating it as an error or triggering recovery. No
A0, A5 or A6 input report was observed. Reset/cleanup includes key releases, but
ordinary typing was not tested and no A2 input report appeared.

No command sequence number or iOS-completion signal was established. These
captures do not measure packet loss, exact pointer accuracy, USB round-trip
latency, or general performance. No timing or retry optimization follows from
them. Before/after frames showed C24C remaining on Home.

## Candidate changes

- `HidInputReport` strictly checks Windows framing and classifies the known
  vendor families, preserving unknown families for diagnostics.
- `HidInputReader` opens the separate read-only handle. `HidReplyMonitor` reads
  independently of output and joins shutdown. Silence, EOF, open failures and
  unconfirmed shutdown remain distinguishable.
- `--hid-replies-pid C24C` enables observation for explicitly enabled input
  boards only. Invalid, duplicate, disabled or raw-mode combinations are
  rejected before hardware access. Without the flag, no reader is opened.
- `/api/kernel/status` exposes fixed-size per-board counts, reader state,
  connection generation, last family/age and error type. It retains no raw
  payloads, identifiers, input text or lease tokens. Counters reset on a fresh
  connection so old observations cannot look like new replies.
- The existing diagnostic exporter retains only those bounded fields and
  treats absent support as unavailable. It does not infer command success.

No read result gates a write, changes output bytes, retries a command, pauses
input or resumes it automatically. A read failure leaves writes independent;
incomplete reader shutdown is reported honestly rather than called successful.
The separate research capture tool stores raw bytes only in its explicit local
evidence output.

The final reader/monitor implementation was exercised through the live-03
capture helper; a later cleanup-error guard and additional tests were validated
offline. **The final full candidate kernel has not been started on hardware.**
The immutable `combined-timing-20261013` package has not been updated and does
not contain this feature. No release gate advances from this work.

## Verification

| Check | Result |
| --- | --- |
| Final kernel Release build | 0 warnings, 0 errors |
| Final capture-helper Release build | 0 warnings, 0 errors |
| Kernel `--self-test` | 245 passed; no real HID transport opened |
| Capture-helper `--self-test` | 30 parser/monitor checks + 6 pure argument cases |
| Diagnostic-export Python tests | 23 passed |
| Capture-guard Python tests | 3 passed |

The helper's 30 parser/monitor checks overlap the full kernel suite; they are not
30 additional independent kernel cases. Coverage includes malformed/unknown
reports, omitted identifiers, bounded storage, stale connection data, silent
input, EOF, cancellation, unjoined shutdown, unchanged output framing, and a
key-release write after reader failure.

The initial restricted-shell kernel test stopped at a mock named-pipe permission
error. Its partial output is preserved. Rerunning with permission to create the
mock pipes passed; the final source passed all 245 checks. An earlier proposed
live-helper invocation naming C241 solely to test argument rejection was blocked
by automatic review and never ran. The guard was instead verified entirely
offline, and only C24C was opened live.

## Restoration and preservation

Both successful runs confirmed C24C released, free and not stopped; C241's input
status unchanged; and the same kernel, console and both receiver processes.
The reader exited normally with its closed record. No test process is left
running. The four protected files (operator settings, installed kernel DLL,
console DLL and UxPlay executable) had identical hashes before and after each
run. FKA was not changed. C24C remained on Home; its pointer was returned near
the reset origin by the final small move.

Historical process IDs for these captures: kernel 35052, console 34848,
C24C receiver 23440, C241 receiver 31880. Recheck current identities before
another live action; these numbers are not standing authority to operate them.

Raw JSONL, frames, run records and the exact helper binaries used in each run
are kept outside Git in the dated evidence archive. Live-01's initial helper
source was not separately snapshotted before refactoring; its DLL/PDB were
preserved. The final source and final standalone build are archived separately
and hash-recorded. See `validation.json` and `archive-verification.json`.

Archive: `../iMouseXP-2.0-evidence-archive/20261014-hid-input-replies`.
This is a verified local copy, not an off-machine backup. Raw data is deliberately
not published. Nothing was pushed, installed or promoted.

## Next work

Use the observation feature during a future coordinated candidate acceptance
window, with explicit board scope and the existing ownership safeguards.
Do not turn it into acknowledgement-based control until response semantics and
correlation are demonstrated. Continue the existing controls/recovery, accuracy,
timing, scaling and release work; missing-space/FKA remains deferred.
