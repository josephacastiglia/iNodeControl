# Preference and binding save failures

12 October 2026. Offline source changes and tests only. No desktop control,
service restart, receiver launch, phone input, installation or push.

## Changes and scope

The console previously overwrote settings.json in place when connecting or
changing theme. It now writes and flushes a complete UTF-8 document to a unique
sibling file, then replaces the destination. An unsuccessful replacement keeps
the previous settings. Theme-save failures now appear in Activity rather than
being silently ignored.

The operator preferences file remains authoritative. Its separate launcher copy
is updated only after the primary save succeeds. A mirror failure keeps the
successful primary save and explicitly reports the older launcher copy. The two
files are not a multi-file transaction. Isolated candidates still write only to
their selected folder; absent trackPointer remains absent, preserving the legacy
preference shape and default behavior.

DeviceStore binding saves now replace the complete file before publishing the
new in-memory snapshot. A failed save leaves both old assignments intact. Other
phone metadata and Unicode names are retained. This is a library repair, **not
an enabled live binding feature**: /device/set still refuses changes in the
ownership kernel. The production route did not expose the old save bug; existing
lease tests use the method to simulate a changed binding.

During actual offline preparation, the launcher returned Prepared=false after
successfully creating and verifying its folder. Its result now reports the
completed preparation. No launch behavior or installed script was changed.

## Validation

| Check | Result |
|---|---|
| Release builds | Console and kernel: zero warnings, zero errors |
| Console self-tests | 256 passed, including 18 new persistence checks |
| Kernel self-tests | 179 passed, including 12 new binding checks |
| Focused persistence control | All 30 checks passed using temporary files only |
| Negative settings control | Direct overwrite reintroduced: fails the expected primary-replacement check |
| Negative binding control | In-memory publication before save reintroduced: fails the expected memory-preservation check |
| Launcher regression suite | 49 passed in PowerShell 7 and 49 in Windows PowerShell 5.1; no process/network adapters used |
| Build/source manifests | Both exact source snapshots and all ten build files verify |
| Review package | 555 files verified during staging; never launched |
| Protected installed files | Kernel, console, receiver and operator settings hashes and timestamps unchanged |

The lock fixtures deliberately permit ordinary writes but deny file replacement.
They prove the implementation does not fall back to truncating the old document
when replacement fails. Tests also cover mirror failure/retry, primary failure
without a mirror write, path spaces, missing directories, unrelated file
preservation, legacy preference shape, hover-off profiles and temporary cleanup.
These are Windows local-filesystem checks, not power-loss or remote-filesystem
durability certification. Sudden termination can leave a temporary sibling file;
permission changes can also prevent cleanup. Existing files are never deleted
as a workaround for replacement failure.

The first sandbox runs stopped at existing tests: console diagnostic-file rename
and kernel synthetic named-pipe access were denied. Their failures are retained.
Approved reruns passed using the same binaries. Neither suite opened an app
window, real HID transport or real receiver. UI settings dialogs, theme Activity
messages on screen, and physical acceptance were not exercised.

The initial negative-control preparation hit a CRLF/LF text-match assertion;
those partial copies were left untouched and corrected controls were generated
under controls/. A hash-check script also compared parsed DateTime values to
strings and incorrectly marked timestamps changed. The before/after timestamp
strings were identical; the corrected comparison and original output are both
retained. No protected file changed.

## Recorded candidates

| Artifact | SHA-256 |
|---|---|
| final-console/iMouse2.dll | 2f83edafd7ffafecdcd09bfc1e44d310aecb77e97256d0aaaae69f01547655f4 |
| final-kernel/iMouse2.Kernel.dll | 6585cd5ceb2d2e8762a3a863e536b3f66d94621446864b67b9e3c01e90d2601f |

console-manifest.json and kernel-manifest.json record the exact tested source,
including changes not yet committed when built. Their informational base is
3d3883f; the manifests do not pretend that base commit alone contains this fix.
Final build folders contain only the five runtime/build files each, excluding
the retained earlier self-test failure report.

- Immutable review package: output/staging/combined-persistence-final-20261012/.
  This includes the new managed builds and the already recorded receiver/runtime.
  Native runtime notice gaps, clean-PC validation and physical gates remain open.
- Prepared isolated console: output/candidate-runs/persistence-ready-20261012/.
  It has hover tracking off and an explicit 9913 endpoint; it has **not launched**.
  Earlier prepared candidates retain their older hashes and are not this build.
- controls/ contains deliberately broken test-only copies. They are not candidate
  application builds and must never replace the actual products.

## Next work

The console still offers Bind, Unbind and Auto-bind while the ownership kernel
explicitly refuses /device/set. Auto-bind can consequently misreport this
unsupported operation as a cable or pointer problem. Reconcile those controls
with the existing kernel capability, keeping live rebinding disabled. This can
be developed and checked offline; guided physical rack identification is still
a separate unfinished requirement. Missing-space work remains deferred.
