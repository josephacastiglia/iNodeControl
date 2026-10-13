# Kernel startup errors survive the launcher

13 October 2026. Offline work on `local/combined-candidate-20261012`, following
`f835998`. No installed launcher, kernel, receiver, console, profile or phone was
changed or restarted. No gate advanced.

## Problem and change

The candidate kernel writes a useful refusal to stderr when required native
plugins are absent. The root launcher started it hidden without retaining that
stream, then rethrew a failed status request when the child exited. Source review
showed that the operator would lose the missing-file explanation.

The launcher source now redirects the error stream of its own newly started
kernel into a unique `launch-logs/kernel-<time>-<id>.stderr.txt`. On early exit,
the failure message includes the available exit code, the actual refusal and its
log path. Only the last 8 KiB is read into the message; full file contents remain
on disk. Missing/unreadable/empty logs have distinct explanations. Existing
services do not create a new attempt log. Timeout polling remains bounded and
neither kills nor relaunches the child; it identifies the process as possibly
still running. Settings reads and the latest failure report use explicit UTF-8.
A failed write of `launch-error.txt` no longer suppresses the original message.

Windows PowerShell 5.1 sometimes returns a null exit code for this fast-exiting
child. The first real probe caught that blank-code bug. The message now says
`exit code unavailable`, while retaining the refusal. It never invents a zero.

## Verification

- `tools/test_launcher.ps1 -Offline` passes **47 checks in each of Windows
  PowerShell 5.1 and PowerShell 7.6.5**. Existing executable/configuration/HTTP.sys
  identity tests remain; new startup tests replace all process/network adapters.
  This mode does not run the original script's environment or live-service checks.
- In both runtimes, the real, hash-verified guarded kernel was run only with
  `--validate-startup` against the preserved broken runtime. The launcher's real
  redirection captured the missing six plugins and package-repair instruction.
  Service reads were replaced with a throwing stub; no real endpoint was read.
  The child exited, and protected release/settings hashes matched before/after.
- Removing the refusal-log detail from a separate launcher copy causes three
  intended checks to fail in each runtime. No production source was rolled back
  for this negative control. See `negative-*.json` and `negative-launcher.ps1`.
- Synthetic hidden children wrote stderr before and after the parent launcher
  exited; both lines were preserved in each PowerShell runtime. Their completion
  marker confirms their scripts reached the end. The PowerShell 5.1 fixture also
  emitted module-loader progress XML; this is fixture output, not kernel output.
- `results.json` names the final actual-probe records and exact launcher hash.
  `redirection-results.json` records the synthetic child test. Earlier probe
  directories are retained, including the initial Windows blank-code observation.

The Python test runner initially inherited PowerShell 7's module path into 5.1,
so its report hashing could not find `Get-FileHash`. Direct invocations worked.
The runner now removes that environment key case-insensitively and lets each
runtime build its own module path. This was a test-launch issue, not a product
change. Older failed/partial probe directories are not claimed as final passes.

## Scope and remaining work

Only the candidate's root launcher source and its existing test suite changed.
The previously live-tested managed binaries/native package were not rebuilt or
modified. The launcher is not part of that immutable runtime review package; a
future approved release assembly must include and validate the revised launcher.
No deployment, push, settings change or screen control occurred.

This is not a normal full-service launch, visible dialog test, or clean-PC
acceptance. Errors emitted exclusively to stdout are not captured by the new
stderr file. The existing listener-failure console output falls in that category;
the launcher still gives its generic startup explanation if there is no stderr.
The full stderr files have no automatic rotation; they are retained per start,
not used for ordinary frame/command telemetry. Archive them as evidence before
manually removing old records.

Actual console controls, physical recovery, the failed upward Home gesture,
varied-target accuracy, full-rack performance and endurance remain open. Typing
stays deferred. The previous turn's confirmed restored rack state remains
historical; this offline work made no rack API calls or phone observations.

The final preservation check compares installed binaries, launcher, configuration
and operator settings with the previous restoration snapshot. The two active
receiver logs are explicitly excluded: their own running processes append to
them. The initial archive attempt incorrectly included those dynamic logs in
the unchanged-files assertion and stopped before creating an archive. No working
file was reverted. Raw Windows probe files retain CRLF byte-for-byte; Git may
flag those carriage returns as whitespace, so they were not normalized.
