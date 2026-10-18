# Autoplay and ambiguous OCR — offline fixes

18 October 2026. Based on `cb6178395053e5dc1322cc5d23abf95431635de8` on `local/combined-candidate-20261012`.

**The candidate now handles the observed autoplay picker and incomplete editor OCR in offline checks. Live unattended save/reopen remains unaccepted and disabled.** This pass made no rack API calls, phone input, PC-control actions, publishing, messaging or installed-release changes.

## What changed

- **Autoplay:** the Save/reopen rehearsal now follows Save → media picker → Drafts → library → reopen. Before navigating from the picker, it requires two independently recognized, fresh frames under the same authenticated lease/stream. It compares the controls, grid and home indicator, excluding only the fixed preview rectangle and status bar. Preview motion alone no longer prevents the model workflow from continuing. Control movement, overlays, stale frames, changed streams and cancellation still stop it.
- **Ambiguous editor OCR:** five separately positioned toolbar words, page dots and the visible button geometry corroborate the supported editor layout. This does not repair `ext` into `Next`, rewrite captions or infer an account.
- **Exact Next verification:** when the whole-frame OCR misses Next, Windows OCR reads one enlarged, fixed button crop from the same image. Its source pixels, crop bounds, image hash and exact word must agree. An unresolved label prevents the details action. The crop is separate evidence; full-frame OCR remains unchanged. There are no repeated recognition attempts or relaxed freshness limits.
- **Recovery:** a lost Save reply can inspect the resulting picker once, but cannot click Drafts, repeat Save or declare the draft saved. A lost navigation reply stops before reopening. Journaling, cancellation and scoped lease cleanup remain in place.
- **Review history:** the recognized Save sheet and picker are accepted as intermediate screens. Unknown screens, permission dialogs and account/stream changes remain blockers. This is sampled visual evidence, not continuous account identity or proof of persistence.
- **Candidate integration:** the candidate backend and launcher include `farm_screen_layout.py` in their source identity. Native console/kernel binaries were not changed or rebuilt.

## Evidence and limits

| Check | Result |
|---|---|
| Complete Python regression suite | **353 passed**, no skips, 163.776 s; includes 23 added checks |
| Retained live frames, compared with the exact prior code | 47 replayed; 17 previously unknown captures now recognized: 8 editors, 5 pickers, 4 Save sheets |
| Actual Windows OCR on the eight ambiguous editor frames | Exact cropped Next in 8/8; 0.94–1.07 s processing per image |
| Earlier OCR regression set | All 36 outcomes preserved |
| Retained autoplay pair after Save | Preview changed; protected controls/grid agreed; accepted as visual stability evidence |
| Second retained picker pair | Held: protected-region mean difference 0.00516 exceeds 0.002. No threshold was relaxed to make it pass |
| Negative controls | Four deliberate in-memory regressions were caught: absent layout corroboration, no autoplay exclusion, bypassed control stability and bypassed exact Next requirement |
| Installed files | All 25 hashes match the preceding protected-file baseline, including operator settings and release binaries |

The first full run was blocked by Windows sandbox restrictions on temporary-file replacement and local sockets (351 tests before the two final history checks). Its failure log is retained. The final 353-test run passed outside that sandbox; the suite's connection guard allowed only its own ephemeral loopback servers. There were no rack or external connections. Launcher `-ValidateOnly` passed without starting processes; backend source SHA-256 is `234b585d6773dabd89db4a720bd45128970bb6321fcd6358432359cbebc11625`.

The saved frames informed these rules. They are development fixtures, **not an independent accuracy set**. All eight ambiguous frames contain only two distinct button crops. The comparison pair that passed spans retained captures, not a new live run. Processing times exclude a live download and its original frame age; the complete observation must still fit the unchanged 1,500 ms limit. Slow recognition remains a hold.

The new pixel patterns support the observed English, dark, 500×1080 portrait picker/editor. Other themes, resolutions, app versions and unseen overlays require review. Stable pixels do not prove that a phone is currently live; frame metadata and ownership checks remain separate. The action route remains a synthetic app model, with no live adapter or coordinates exposed by this change.

## Reproduction

Use the configured Python 3.11 environment with Pillow and NumPy:

```powershell
python -m unittest discover -s tools -p 'test_farm*.py' -v
python analysis/farm-layout-stability-20261018/replay.py
python analysis/farm-layout-stability-20261018/ocr_replay.py
python analysis/farm-layout-stability-20261018/negative_controls.py
& '.\Open Marketing Farm Candidate.ps1' -ValidateOnly
```

The replay scripts require the retained local evidence from `analysis/farm-live-verification-20261018/` and the earlier OCR set. They never capture a phone or send input. The OCR script starts hidden Windows OCR processes that read local files only. The negative controls change functions in the test process, not source files.

Raw screenshots, OCR, test output and checksums stay in the sibling `iMouseXP-2.0-evidence-archive/20261018-farm-layout-stability` folder; they are not staged with the code. The archive also records the final commit and source copies. Historical native/kernel test results apply only to their unchanged binaries and are not counted as new tests here.

## Next acceptance step

Run a short, coordinated C24C-only check of the new recognizer and stability decisions on fresh frames, including the total capture/OCR age. Keep account, all-slide, caption, saved-library and reopened-content checks. Then validate a bounded live adapter and interruption handling before enabling unattended operation. None of that ran in this offline pass, and no phone connection is required to preserve these changes.
