# Kernel startup validation and ordering

12 October 2026. Product-source changes validated offline. No desktop control,
phone input, release service restart, receiver launch, deployment or push.

## What changed

The kernel now parses all normal-service options and validates saved configuration
before hardware work. Explicit malformed movement timing, missing/repeated values,
unknown flags, ambiguous board lists and conflicting timing modes fail clearly
instead of silently starting with another configuration. Defaults remain 7 ms
movement pacing, vendor Home and no input-enabled boards. Existing space-separated
options still work; valued options also accept `--name=value`.

Configuration checks reuse receiver identity/port and pointer-calibration rules.
They reject duplicate JSON properties, null records, duplicate phone/board
bindings and missing enabled-board calibration/receiver mappings. Discovery or
placeholder identities cannot enable input. A requested receiver must exist and
have an explicit runtime with its bin, plugin directory and scanner. Presence is
not a dependency-loading test. Validated phone records are passed to DeviceStore
as a snapshot instead of rereading a file after validation.

`--validate-startup` uses that same path, prints JSON and exits without creating
directories, enumerating/opening boards, reserving an HTTP endpoint, opening frame
pipes, starting receivers or writing settings. It reports incomplete bindings
separately: a read-only discovery configuration can be structurally valid.
Use only the recorded candidate build; older releases do not recognize this flag.

Normal startup binds its HTTP endpoint before board enumeration and receiver
startup. A binding failure or cancellation before that step starts no receiver.
The API server's post-bind callback provides this order; its test-only listener
adapter permits failure/cancellation checks without a real port. Existing explicit
raw HID tools remain separate modes and were not run.

## Evidence

| Check | Result |
|---|---|
| Final Release build | Clean, zero warnings/errors |
| Final kernel self-tests | 167 passed, including 53 new startup checks |
| Real validation-mode subprocesses | 7 passed: saved two-phone configuration, invalid timing, misspelled flag, missing directory/runtime, local runtime, read-only 19-slot template |
| Saved configuration preservation | All six input files unchanged; missing directory was not created |
| Negative control: restore silent timing fallback | Failed the new invalid-delay check as expected |
| Negative control: start receiver callback before listen | Failed the new listener-failure check as expected |
| Existing cleanup harness | S1–S9 all passed against simulated boards and private loopback services |
| Build/source record | 22 source inputs and 5 kernel outputs match `kernel-manifest.json` |
| Installed kernel, console and UxPlay | Recorded hashes unchanged |

Final kernel DLL SHA-256:
`41c01cad2d5819b358609193a3b619e064c53868461a6e42cb3890614466bf95`.
Its informational revision is the prior committed base; the manifest records
the exact uncommitted source snapshot used to build it.

The two negative controls were separate source/build copies, never installed or
used with hardware. The initial self-test attempt was blocked by the sandbox's
private named-pipe restriction; the passing run used only fake HID and private
synthetic pipes outside that restriction. A test string initially had an invalid
C# path escape and was corrected before running the suite. The harness's first
parallel build failed without a diagnostic; a single-node build succeeded cleanly.
These preliminary logs remain preserved.

The cleanup harness validates API/input behavior, not Program startup. It used
the same final API/router source; the subsequent Program refinement moved normal
board enumeration into the post-bind callback. The final kernel self-test and
seven actual CLI checks were then run on the final binary. No physical result is
inferred from any of these checks.

## Package and limits

The new immutable review folder is
`output/staging/combined-startup-final-20261012/`. It pairs this kernel with the
unchanged recorded diagnostics console and patched receiver/runtime. Earlier
packages keep their own earlier builds. Package verification checks exact files,
not readiness to install or permission to run them.

The validation mode does not assess live port availability, URL permissions,
frame-pipe availability, native loading, correct physical bindings, phone
discovery, input accuracy or displayed latency. Listener tests inject failure;
the service was not started against the live rack. Full-rack and physical
acceptance remains open. The first-space investigation remains deferred.

Next offline source issue: DeviceStore currently edits its in-memory binding
before saving and writes the destination JSON directly. A failed save can leave
the reported binding inconsistent with disk; investigate atomic save/failure
handling with temporary files and simulated failures before any live change.
