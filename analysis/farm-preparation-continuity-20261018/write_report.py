import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]; RUN = Path(__file__).resolve().parent
log = (RUN / 'python-verified.txt').read_text(encoding='utf-8-sig')
assert re.search(r'^OK\s*$', log, re.M) and not re.search(r'^(FAIL|ERROR|FAILED)[: (]', log, re.M)
count = int(re.search(r'^Ran (\d+) tests', log, re.M)[1])
native = json.loads((RUN / 'native-self-tests.json').read_text(encoding='utf-8-sig'))
assert native['allCommandsUsedMockTransport'] is True
checks = native['passed']
build = json.loads((RUN / 'build-source.json').read_text(encoding='utf-8-sig'))
exercise = json.loads((RUN / 'render-exercise-final.json').read_text(encoding='utf-8'))
launcher = json.loads((RUN / 'launcher-validation.json').read_text(encoding='utf-8-sig'))
assert launcher['SourceHash'] == exercise['backendSourceHash']
output = 'output/codex-farm-preparation-20261018'
digest = hashlib.sha256((ROOT / output / 'iMouse2.dll').read_bytes()).hexdigest()
report = f'''# Scheduled preparation continuity and job recovery — 18 October 2026

This pass completes the local path from recurring preparation to reviewable carousel/video drafts. It does not enable unattended app operation. No phone input, rack API, PC control, publishing, messaging, installed-release changes or operator-settings writes were needed.

## Result

- Code commit: `{build['commit']}` on `local/combined-candidate-20261012`, local only.
- Candidate: `{output}`; DLL SHA-256 `{digest}`. Built from that committed source; report changes do not alter the product.
- Backend source hash: `{launcher['SourceHash']}`. The separate launcher checks this exact source, uses simulation on loopback 9915, separate settings and hover tracking off.
- **{count} Python tests, no skips; {checks} native headless checks.** Clean Release build, zero warnings/errors. No desktop window was shown by the native checks.

## What changed

### Every prepared batch stays reviewable

Previously a scheduled run retained filenames, but editors selected the latest manifest. A newer render could therefore make an older run inconvenient or impossible to open correctly.

Each generation now retains its own checksum-pinned manifest. Successful C24C preparation also snapshots the carousel images and complete caption into the existing draft store. A missing/changed manifest or damaged/duplicate/incomplete image batch fails the run and holds future preparation; it never substitutes the latest batch. Later local edits survive repeated retrieval of the original preparation request.

The preparation window shows recent runs and opens the selected run's carousel, or prepares its original video and caption for the chosen destination. Old records without batch identity remain readable but cannot silently open newer content. The window shows the latest 30 run records; older records and source assets remain on disk, and saved carousels remain in the normal library. No automatic deletion was added.

Opening a scheduled carousel archives unrelated unsaved editor work first. Video requests pin generation, manifest hash and source bytes through response recovery. Missing/changed source files stop new video preparation; already saved video copies remain usable. Repeated exports of an unchanged carousel or video revision now have identical bytes/checksums instead of inheriting the current ZIP timestamp.

### Jobs remain recoverable around cancellation and crashes

Cancellation can arrive before submission and is recorded durably before acknowledgement. A delayed request with that ID cannot start, even after a backend restart. Cancellation and admission are serialized in SQLite; a worker also checks cancellation before calling its action. A second process cannot execute another job against the same journal while its worker lock is held. Reads distinguish another active backend from an interrupted process; a completion committed during the ownership check is recovered correctly.

Thread-start failures release the worker lock and leave a failed, non-replayable request. A crashed process releases the OS lock but its accepted work remains unknown/interrupted and is never replayed. Cancellation from another registry reaches a cooperative active worker through the journal. This does not forcibly interrupt an in-progress codec; it prevents subsequent cooperative work and reports the outcome.

A regression run caught a monitor race: it could wake before completion, acquire the registry lock after completion, and rewrite the terminal status to cancelling. The monitor now rechecks completion under that lock. The native client also retains the request bookmark after server/transport uncertainty instead of treating HTTP 500 or a conflicting response as proof that nothing was accepted.

## Evidence

| Check | Result and scope |
|---|---|
| Full guarded Python suite | {count} passed; `python-verified.txt`. Ephemeral loopback mocks only; external/rack networking forbidden. |
| Native headless checks | {checks} passed; `native-self-tests.json`. Screens rendered from unshown WPF trees, no native window/PC control. |
| Real local preparation | Two background runs generated separate four-slide/MP4 batches. The first carousel stayed intact after the next batch. Worker stopped at its run limit. |
| Real video preparation | The older batch's source encoded and fully decoded for TikTok, X, YouTube Short and Instagram Reel draft packages. Two-second test video; no transfer listener or app action. |
| Lost replies and source changes | Original IDs recover saved copies without overwriting edits or generating duplicate drafts; damaged/missing batches refuse. |
| Actual process boundaries | Separate child worker excluded a competing process and observed durable cancellation; a deliberate child crash exited 73, released its lock, and was not replayed. |
| Negative controls | Cancel-before-admission, the terminal-monitor race and stable export checks fail on preserved `91dfda8` source and pass now. See `negative-controls.json`. |
| Initial failures kept | The earlier focused log contains the ZIP timestamp mismatch and terminal-status race. The initial sandbox-only job run hit TEMP rename restrictions; the authorized offline reruns pass. |

Reproducers are `exercise_preparation.py` (real local media, all networking forbidden) and `negative_controls.py` (preserved-source comparison). Full logs, generated media, databases, candidate and exact source are preserved locally outside Git at `iMouseXP-2.0-evidence-archive/20261018-farm-preparation-continuity`, with checksums. Nothing was pushed or promoted.

## What still needs live acceptance

1. Validate paired screenshot freshness on the compatible candidate kernel against an actual phone stream. The known installed release lacks the required metadata; this pass did not start or swap a kernel.
2. Validate the real app transition adapter through account, media selection, complete caption, Save draft, library and reopen checks. Existing synthetic rehearsals and earlier supervised phone saves remain separate evidence.
3. Exercise interruptions and recovery on those real workflows, including app/version changes and account identity. No unverified result authorizes phone input.
4. Add genuine account/post observations for analytics. Unattended publishing and messaging remain outside the approved scope and disabled.

The next live window is C24C only and must preserve the installed release. No test service or background schedule from this pass is left running. The current phone/mirroring state was not inspected or changed.
'''
(RUN / 'README.md').write_text(report, encoding='utf-8')
status = ROOT / 'MARKETING-FARM-STATUS.md'; text = status.read_text(encoding='utf-8')
text = text.replace('## Latest candidate: offline draft save/reopen and recovery', '## Earlier candidate: offline draft save/reopen and recovery', 1)
intro = f'''## Latest candidate: saved preparation batches and durable job recovery

Candidate `{output}`, built from `{build['commit'][:12]}`, DLL SHA-256 `{digest}`. **{count} Python tests and {checks} native headless checks pass**, with a clean Release build. The installed release and operator settings remain unchanged. This pass used no phone input, rack API, PC control, publishing or messaging.

Each completed local preparation retains its exact generation and an editable carousel snapshot. The preparation window opens that run's carousel or original video/caption after later batches have been generated. Manifest/source changes refuse instead of substituting newer content. Unrelated unsaved edits are preserved; saved copies recover without duplication. Unchanged revisions now export with stable checksums.

Cancellation survives delayed job submission and backend restarts. An OS lock prevents competing workers sharing a journal. Real process-crash tests confirm no replay; a late heartbeat cannot rewrite a finished result. HTTP server uncertainty keeps the console's pending request available for inspection.

Two actual local background renders and four older-batch video preparation/decoding paths passed without a phone or transfer service. **Unattended phone automation is still not accepted:** real-stream freshness and the real app save/reopen adapter need live validation. Publishing and messaging stay disabled. See [this pass's report](analysis/farm-preparation-continuity-20261018/README.md).

'''
text = text.replace('# Marketing Farm candidate — 18 October 2026\n\n', '# Marketing Farm candidate — 18 October 2026\n\n' + intro, 1)
status.write_text(text, encoding='utf-8')
acceptance = ROOT / 'MARKETING-FARM-ACCEPTANCE.md'; text = acceptance.read_text(encoding='utf-8')
text = re.sub(r'- Native output: .*', f'- Native output: `{output}`, code commit `{build["commit"][:12]}`, DLL SHA-256 `{digest}`.', text, count=1)
text = re.sub(r'- \*\*294 Python tests\*\*.*', f'- **{count} Python tests**, no skips; **{checks} native headless checks**. Clean Release build. Two real local scheduled renders and four older-batch video preparation/decoding paths passed. Actual process cancellation/crash checks and three negative controls passed. No desktop or rack interaction. Earlier OCR and frame-transport evidence remains unchanged; it was not rerun.', text, count=1)
text = text.replace('Latest report and checks: `analysis/farm-verification-20261018/README.md`.', 'Latest report and checks: `analysis/farm-preparation-continuity-20261018/README.md`.')
text = text.replace('Explicit bounded schedule', 'Exact batch manifests and saved carousel/video review; explicit bounded schedule')
text = re.sub(r'^\| Recurring local preparation \|.*$', '| Recurring local preparation | Each run retains its generation/manifest and editable carousel; native history opens that carousel or its original video/caption. Two actual background runs, batch preservation, failure holds, pause and restart tests pass | Latest 30 runs in the schedule window; older data retained. No days-long soak or unattended phone execution. Requires explicit configuration and a running backend; never transfers, publishes or messages |', text, flags=re.M)
text = re.sub(r'^\| Jobs and Stop \|.*$', '| Jobs and Stop | Durable cancellation before admission, cooperative cancellation across processes, exclusive worker ownership, no replay after actual process crash, recovered completion and late-monitor race tested; uncertain server responses retain the native job bookmark | Marketing-specific live console/backend handover remains unverified. Cancellation cannot forcibly interrupt an in-progress codec |', text, flags=re.M)
text = text.replace('needs review queue, actual timing and restart acceptance', 'needs a verified live review queue, actual timing and restart acceptance')
acceptance.write_text(text, encoding='utf-8')
print(json.dumps(dict(pythonTests=count, nativeChecks=checks, codeCommit=build['commit'], candidateDllSha256=digest)))
