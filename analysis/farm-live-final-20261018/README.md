# Fresh C24C validation of the final library optimization

18 October 2026. **Offline preparation passed; fresh phone validation pending.**

This run continues the partial validation recorded in
`analysis/farm-live-transitions-20261018/README.md`. The candidate source is
`d173ee1fdfeca06f2cbdd2fbfae3e8bff9894a70`. The final optimization decodes a library
screenshot once per comparison, retains all ambiguity checks, and reports a
guard-refused action as `not_sent`. Those changes passed the previous complete
373-test product suite and 18 workflow checks, but have not yet completed a fresh
phone run.

## Scope and acceptance

- Use C24C and Instagram `xs.halle.xo` only, with the existing labelled three-slide
  test draft and its original caption. Do not import media, type, publish, message,
  switch accounts, change FKA or use PC control. C241 is excluded.
- Run the exact final diagnostic and product code. The diagnostic, fixture tests,
  control references and lifecycle scripts are byte-identical copies of the
  previous revision. Only preparation paths and the recorded source commit differ.
- A passing run must start on the authorized profile, open the unique test draft,
  verify every slide and the full caption, save once, locate and reopen it, verify
  every slide and caption again, preserve it on exit, and verify the same profile.
  It must complete under one ownership interval, with confirmed release and
  intact exported evidence.
- Keep the 120-second full-workflow admission budget, eight-second/four-capture
  read-only settling limit and 1,500 ms per-frame age limit. Unknown screens,
  changed accounts, ambiguous media, stale evidence and uncertain replies stop
  the run. Do not retry semantic actions or count a recovery as acceptance.
- One successful diagnostic does not establish crash recovery, server persistence,
  a native-button workflow or unattended production reliability. No live marketing
  endpoint is enabled by this test.

## Preparation results

- **56 tests passed**: 18 complete diagnostic workflow checks, 11 restricted
  transport checks, 14 transition checks and 13 library/account-continuity checks.
  These use synthetic or retained frames and send no phone input. No redundant
  full-suite rerun is counted; the prior 373-test product result remains historical.
- Actual Windows OCR recognized the retained profile, Create menu and exact Next
  evidence. Processing took 469, 437 and 531 ms respectively. These are local
  processing measurements, not fresh-phone timing or an acceptance result.
- All 29 frozen source files match; all 25 protected installed files match both
  the current baseline and the previous restored state. The four lifecycle scripts
  parse. Candidate startup validation confirms one C24C receiver and no hardware
  access, listeners, started receivers or settings writes during validation.
- The first preparation-only OCR probe omitted the required caption field and
  stopped with `KeyError`. The corrected probe reads the exact package caption;
  no product source changed, and the failed probe is retained separately.
- `preparation-validation.json` records the results. Native binaries, product
  Python modules, installed release files and operator settings are unchanged.

## Runtime and restoration

The read-only initial preflight found no rack processes or occupied rack/test
ports. Keep the installed console closed. Only a private C24C kernel and receiver
may start; there is no release kernel swap in this window.

- API: `http://127.0.0.1:9916/api/`.
- Receiver name: **iMouse2-C24C**.
- Kernel: preserved `output/codex-farm-live-kernel-20261018/iMouse2.Kernel.exe`.
- Kernel DLL SHA-256:
  `c72fa4e0b02b82ec4f7a949c9a80375c69da68d7357084401c7bb422c194a873`.
- Private runtime/data: `output/candidate-runs/farm-live-final-20261018/`.
- `preparation.json` records runtime/configuration hashes;
  `validation-sources.json` freezes diagnostic and product source bytes;
  `protected-files.json` records installed-file hashes without settings contents.

After preparation passes, start the guarded private kernel and ask the operator
to connect C24C, dismiss Control Centre and open the authorized Instagram profile.
Recheck exact runtime, phone mapping, current frames and free ownership before
input. Run `validate_workflow.py --out <new-attempt-directory>`; existing output
directories are refused. A file named `STOP` inside that directory requests
cancellation and scoped cleanup.

After the live window, release C24C and stop only the recorded test kernel through
normal shutdown. Restore the initially stopped rack state, verify all protected
files, retain every attempt and archive the evidence with hashes. Do not overwrite
the prior validation or archive. Nothing is promoted or pushed.
