# Priority 2: C24C draft inspection and recovery

The bounded recovery candidate passed this live check on **C24C / Instagram
@xs.halle.xo**. This record lets the next developer assess the result and locate
its evidence. It accepts inspection of the retained three-slide creation, not
general unattended marketing, recurring phone execution or other accounts.

## Result

Three separate requests opened the unique saved carousel, checked all three
full-size slides in order and the exact complete caption, then released C24C.
They sent **no Save, import or typing**. A fourth request was deliberately stopped
after its first completed navigation action; it retained review status and
released control. The original creation journal and all 441 original source-data
files stayed byte-identical.

The native interface recovered a suppressed admission reply and a suppressed
status reply using the same request. Only one admission reached the backend.
After both initial inspections completed, the private backend was gracefully
restarted. A newly constructed native window loaded its retained bookmark and
retrieved the result using GETs only. Reposting that exact completed request ID
also returned the retained result without changing input generation or evidence.

These are the live acceptance results:

| Check | Result |
|---|---|
| Inspection 1 | Passed; seven answered navigation actions |
| Inspection 2 | Passed after the operator's Instagram close/reopen; seven answered actions and both receive-failure checks |
| Native/backend recovery | Passed; nine native assertions, GET-only bookmark recovery, unchanged evidence and phone generation |
| Inspection 3: Stop | Passed; cancelled after one answered action, confirmed cleanup, retained review bookmark, Start disabled |
| Inspection 4 | Passed after a new explicit request; seven answered actions |
| Stopped record during inspection 4 | Stayed terminal/cancelled across three status reads while the other request was running |
| Collected validation | 58 checks, 40 retained phone frames, 52 native-driver assertions |
| Original source data | All 441 file hashes match the preparation snapshot |
| Installed release/settings | All 25 protected file hashes match |
| Restoration | Private services stopped gracefully; initial stopped rack state restored |

`validation.json` contains the checks, counts, request IDs and source hashes.
`acceptance-1.json`, `acceptance-2.json` and `acceptance-4.json` each contain
36 collected checks and 13 retained frames. `acceptance-3.json` contains the
eight deliberate-Stop checks. Native assertions total 10 + 12 + 11 + 10 for the
four requests, plus nine for bookmark recovery. Dry-run assertions are separate.

## Scope and limits

- The operator was instructed to swipe Instagram away in the app switcher and
  relaunch it, then replied **ready**. The exact profile was rechecked before
  inspection 2. There is no independent iOS process-termination telemetry.
  The product continues to report `appRestartVerified: false`.
- Reply loss was injected in a test-only HTTP handler **after the real backend
  answered successfully**. This tests native receive-error handling and durable
  identity; it is not a claim of TCP packet loss or a lost kernel command.
- The live backend restart occurred after terminal requests with confirmed
  cleanup. Active process death, lost command answers, disconnects and receiver
  changes remain covered by the offline boundary tests, not by destructive live
  faults in this window.
- Every successful run checked the same retained creation and current library
  content. This does not establish repeated new-content creation, other app
  layouts/accounts, continuous account history or automatic force-quit/relaunch.
- The saved content check never resolves an uncertain original Save by guessing.
  Unknown prompts/outcomes still stop; it does not repeat Save or resume an editor.

The prior [offline implementation and test record](../farm-recovery-20261019/README.md)
contains the 452 Python tests, 564 native headless checks, eight retained-layout
tests and negative controls. Product input source and native/kernel binaries
were unchanged throughout this live pass.

## Exact candidate

Product source: `e066acccc6651a0f1b3212cdc50238845177e0db`, branch
`local/combined-candidate-20261012`. Native output:
`output/codex-farm-recovery-20261019`. These are SHA-256 hashes:

| Component | SHA-256 |
|---|---|
| Native `iMouse2.dll` | `f2df511f1ad77269a724c016f9e95324718860c09efc0d7030f0a9f281f6f47c` |
| Private kernel DLL | `c72fa4e0b02b82ec4f7a949c9a80375c69da68d7357084401c7bb422c194a873` |
| Backend source fingerprint | `e3ab6368c348cd5091d6b7ca4db09a9342c9508999d4faa8de86d92a54d13bd0` |

All requests inspect creation `b8c155e2-1670-4f60-a090-aeff921e162e`, local draft
`6e390142-4d00-473a-b2ee-83f65da53cc7`, revision 5. Its original Save was already
answered and verified before this window. The immutable package and original
journal hashes are pinned in `preparation.json` and checked on each request.

The backend used loopback 9915 and the C24C-only kernel used 9916. Kernel PID
57748 and receiver PID 17096 stayed unchanged with zero receiver restarts. Only
the private backend restarted, from PID 26976 to 33512. Those PIDs are historical;
recheck identities before a future window. Both receiver and input configuration
contained C24C only. No C241 input, desktop control, publishing, messaging, FKA
change, installed-release change, promotion or push occurred.

## Preparation issue and preservation

The first kernel start refused before hardware access because the staged folder
lacked `pointer-calibration.json`. The refused process/logs are preserved in
`startup-attempt-1/`. A byte-identical copy of C24C's verified calibration fixed
the staging. `prepare_live.py` now copies it, and `Start-Candidate.ps1` runs
`--validate-startup` before starting a service. The validation passed without
hardware access, settings writes or a listener. This was a staging fix, not a
change to kernel calibration or input behavior.

The first admission frame showed Control Centre. No input was sent; that capture
is preserved in `profile-preflight-1/`. The operator opened the exact profile
before inspection 1.

`NativeProbe` from the offline preparation drove inspections 1 and 4.
`NativeFaultProbe/` drove receive failures, Stop and bookmark recovery without
showing a desktop window. The original reply-loss version's source and binaries
are retained separately; `fault-reply-loss-preparation.json` identifies it.
Both apphost and managed driver DLL hashes are recorded. `Run-Inspection.ps1`
refuses existing attempt folders rather than replaying an earlier request.

## Final state and evidence

The last observed phone screen is Instagram's carousel details page with the
unchanged test caption. No additional draft or media was created in this window.
FKA was not toggled. C24C's generation was 4 and its lease was free before
shutdown. The installed console was not started: the rack was initially stopped,
and that same state is restored. Reconnecting mirroring is necessary for a future
live window.

`restoration.json` records the empty process/port inventory and the 25 protected
file hashes. `archive-summary.json` locates the local evidence archive and its
checksum manifest. It includes private screenshots/logs, backend journals and the
exact candidate/driver binaries; these are not uploaded to Git.

To recheck the completed local evidence without phone or desktop access, run
from the repository root:

```powershell
python analysis/farm-recovery-live-20261019/final_validation.py
```

The script verifies the recorded source, frames, results and restoration; it
opens no socket and sends no input. Do not rerun the live startup or inspection
scripts against these retained attempt folders. A future live window needs fresh
preparation, fresh identity/ownership checks and new evidence.

The next engineering work is a verified review queue and explicit recurring
draft execution. Broader layouts, other formats/accounts, arbitrary prompt
recovery and live process-death cases require their own scoped acceptance.
Publishing and messaging remain disabled.
