# Completion audit: physical validation required

**Later 14 October update:** the operator authorized the navigation window. One
Home-from-Settings check passed, but direct Fn+Up failed to open App Switcher with
FKA On; the sequence stopped and the release was restored. Read
[the live record](../navigation-live-20261014/README.md) for mirroring-restoration
status and scope. The five-item goal remains incomplete. The text below is the
preserved pre-window audit, not current authorization or a claim that no run exists.

14 October 2026. Audited worktree: `local/combined-candidate-20261012`,
`bc1668e`. Exact product source/build: `373dd58`. **The five-item goal is not
complete.** No promotion, deployment or new physical run occurred.

The preceding goal turn made concrete progress: it replaced unsafe historical
runner assumptions, added 26 passing fake-API checks and three detected negative
controls, committed the work and verified its archive. This audit inspected the
current source, saved build/test results and package bytes. It found no concrete
offline defect requiring another product change before the bounded phone check.

| Goal requirement | Authoritative evidence inspected | Completion verdict / next evidence needed |
|---|---|---|
| Reliable Home without an inserted Tab | `InputRouter.cs` Home branches and `HidProtocol.cs`; 290-check final kernel log; navigation negative-control record | **Incomplete.** Direct variants omit Tab in emitted reports. The exact candidate must reach Home reliably from the prepared field, Settings and idle cases; preserved note text must be observed, then real-console operation accepted. The installed default still uses the vendor sequence. |
| Usable App Switcher across claimed FKA modes | Direct Fn branch and reported compatibility in `InputRouter.cs`; `PROTOCOL.md`; final console build/test record | **Incomplete.** No-Tab Fn+Up and explanatory guidance are implemented. Current-candidate visible results are missing. FKA-Off remains an unestablished capability, not a newly demonstrated hardware limitation or supported mode. |
| Evidence-based reply handling and pacing | `HidConnection.cs`, bounded monitor tests, `PROTOCOL.md`, recorded C24C capture and vendor follow-up | **Offline implementation verified; combined physical acceptance incomplete.** Observation does not drive retries or write completion. Shared vendor events justify keeping pacing unchanged. Record the new candidate's actual replies and cleanup without mistaking counters for iOS success. |
| Absolute positioning only if hardware supports it | `HidProtocol.AbsoluteProbe`, router validation/cleanup, startup profile and negative controls | **Incomplete / support unknown.** Encoding and isolation are tested with fake transport. No live A0 input has established board support. A separately coordinated move-only probe must precede any supported-mode implementation, button/orientation/recovery acceptance or hardware-limitation conclusion. |
| Reject mismatched binaries/debug symbols | `SYMBOLS.md`, parser/package test record, negative controls and final `package-result.json` | **Complete within the new managed package workflow.** 74 relevant checks pass; three removed-guard controls detect faults. Both final managed pairs validate. Broader clean-PC and release acceptance are separate, still-open project work. |

## Evidence and preservation checks

- Release build logs record zero warnings/errors for both projects.
- The exact candidate has 290 passing kernel mock checks and 411 headless
  console checks. These are not phone or WPF interaction acceptance.
- Read-only hashes of the current packaged kernel DLL, console DLL and
  `package.json` still match `package-result.json` and `preparation.json`.
- The latest navigation validation records 26 passing fake-API tests and three
  expected assertion failures when guards are removed. No live-navigation
  evidence directory exists in this record.
- `archive-verification.json` and `navigation-archive-verification.json`
  preserve the binaries, prepared run, source and tooling. They are local
  archives, not off-machine backups. The latest preservation check confirmed
  all 25 protected installed files/settings unchanged.
- This audit used no rack request, desktop control, phone input, service launch,
  restart, FKA change or repeated test suite.

## Blocking dependency and exact resumption

The same pending dependency has been recorded in the implementation turn, the
navigation-runner turn and this audit: the operator has not answered the
coordinated C24C window question. The earlier two turns made offline progress;
that work is now prepared. More simulated successes cannot supply the missing
physical evidence, and an unanswered question is not approval to interrupt
mirroring. No live process/job is being awaited in place of that approval.

When the operator authorizes a window and is available, use
`LIVE-ACCEPTANCE.md` and `NAVIGATION-RUNNER.md`. Recheck current process identity,
hashes, mapping and ownership; do not rely on historical PIDs. Use the prepared
C24C-only profile, unchanged FKA and the normal leased API. Send no input to
C241; keep typing deferred. Stop at unexpected behavior and restore the
installed release and both mirrors. The absolute-position probe remains a
separate coordinated window. No further general permission is needed for
offline fixes justified by evidence from those checks.

Do not replace the full goal with “build passes,” enable unvalidated defaults,
call absent hardware evidence a limitation, or mark the five improvements done.
