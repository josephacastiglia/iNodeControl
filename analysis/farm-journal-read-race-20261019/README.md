# Farm run journals: bounded read retry for Windows replacement (19 Oct 2026)

**Offline fix.** There was no phone input, kernel, receiver, backend, rack service, desktop automation, `--ui-test`, publishing, messaging, FKA change or installed-release change.

## 1. Problem

A run's worker thread replaces `record.json` through `atomic_json`, which writes a temporary file and then calls `replace`. A status GET reads the same file. `atomic_json` already retried its replace for up to 0.5 s on winerror 5, 32 or 33. The reader had no retry.

On 19 Oct, one complete suite run failed once in
`test_farm_creation.CreationTests.test_unknown_import_is_retained_and_same_id_or_restart_never_replays`
with `PermissionError: [Errno 13] Permission denied: ...record.json`, raised from `DraftRuns.get`
(`analysis/farm-tiktok-draft-20261019/python-full-transient-error.txt`). The test passed 6/6 when run alone and in the next full run.

In the live backend the same race would surface as a failed status GET while the native window polls.

## 2. What a Windows reader actually sees

`probe_read_refusal.py` uses local temp files only. Its output is in `probe-read-refusal.txt` (Python 3.11.6, this PC).

| Case | Reader error |
|---|---|
| Another handle denies read sharing | `PermissionError`, errno 13, `winerror=None` |
| The file is delete-pending | `PermissionError`, errno 13, `winerror=None` |
| `atomic_json`-style replace loop vs. `exists()` + read, 4 s | 471 refusals in about 17.9k reads, all errno 13 with `winerror=None`. `exists()` was never false and never raised. |

Python's `open()` on Windows reports the Windows code only as errno EACCES. That covers ERROR_ACCESS_DENIED (5, including delete-pending), ERROR_SHARING_VIOLATION (32) and ERROR_LOCK_VIOLATION (33). A copy of the writer's `winerror in (5, 32, 33)` filter would therefore never match the reader's error. The writer's `os.replace` errors do carry `winerror`.

## 3. Change

- `tools/farm_draft_runs.py`: new `read_journal(path)`.
  - It retries only that local file read, every 10 ms, within the writer's 0.5 s budget.
  - A refusal counts as transient when winerror is 5, 32 or 33. When the error has no winerror, errno EACCES counts as transient.
  - Any other error, or a refusal that outlasts the budget, raises unchanged.
  - No phone command is retried, and GET still never connects to the phone.
- `DraftRuns.get` reads `record.json` through `read_journal`. Every run service that inherits it is covered: carousel, creation (Priority 1/2), Reel, TikTok and recovery.
- `CreationRuns.get` reads the running verifier's `verification/record.json` through `read_journal`. That is the same race: a status GET reads it while the verifier's `atomic_json` replaces it.
- These journal reads happen only after a run is terminal, so they are unchanged:
  - `imported_proof`
  - recovery `source`
  - the worker's own post-run hash
- Behaviour is otherwise identical.

## 4. Tests

| Test | Proves |
|---|---|
| `test_farm_draft_runs` `test_transient_windows_read_refusal_still_returns_the_complete_record` | Three refusals followed by a good read return the complete verified record. This holds for the observed shape (errno 13, no winerror) and the writer's shape (winerror 32). |
| `test_farm_draft_runs` `test_lasting_or_unrelated_read_errors_still_raise` | A lasting refusal still raises after a bounded number of attempts and under 2 s. An unrelated error (EIO) raises on the first attempt. |
| `test_farm_draft_runs` `test_status_polls_during_real_journal_replacement_never_fail` | Windows only, no mocks. A running journal is replaced continuously for 0.5 s while `get()` polls it. |
| `test_farm_creation` `test_running_verifier_progress_survives_a_transient_windows_read_refusal` | The verifier-progress read survives three refusals. |

Each test was also checked against the old unguarded read:
- All four fail on it.
- The real-race test failed 10 of 10 runs on the old read and passed 10 of 10 with the fix.

## 5. Complete suite

`cd tools; python -m unittest discover -s . -p "test_farm*.py"` reported **531 passed, none skipped, 1,643.7 s, exit 0** (`python-full.txt`).

The count is the earlier 522 tests, plus the 4 above, plus 5 tests from another session's untracked `test_farm_permission_prompts.py`. That file and its module were already in the working tree when discovery ran at 22:03:29.

The same session edited several tracked files during the run. Every one of those edits is later than discovery. So the in-process tests ran the committed sources plus this change. The suite's child processes are either ffmpeg/ffprobe or Python children that import only modules those edits did not touch.

## 6. Prepared live windows

`farm_draft_runs.py` and `farm_creation_runs.py` are part of the backend source fingerprint. So the Reel and TikTok windows prepared on `f3e083ae…` are now stale.

- `Start-ReelWindow.ps1` and `Start-TikTokWindow.ps1` refuse offline with "Candidate source identity differs." They start nothing.
- `verify_preparation.py` checks product sources and binaries, not this fingerprint. It cannot catch the stale state on its own.

Neither window was re-prepared here. At commit time, uncommitted permission-prompt work in this checkout was still changing:
- the fingerprint list
- both `prepare_*_live.py` source lists
- several pinned sources

A preparation now would have pinned bytes that no commit contains. Re-prepare both windows once that work lands:
1. Delete the unused run folders and the dry-run output folders.
2. Run `prepare_reel_live.py` and `prepare_tiktok_live.py`.
3. Run both dry-run probes and `verify_preparation.py`.
4. Update the section 5 values in each README.
