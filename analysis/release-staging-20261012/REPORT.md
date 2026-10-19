# Offline release staging

12 October 2026. Completed on `local/coordinator-work`, base `01fb669`. Packaging/tooling changes are local and uncommitted; product source and the installed release were not changed in this batch.

## Delivered

A verified review bundle at `output/staging/offline-review-20261012/` and ZIP at `analysis/release-staging-20261012/imouse-offline-review-20261012.zip`. It contains 131 inventoried files plus `package.json`, totaling 1,328,351 compressed bytes. Source snapshots and original build records accompany the console, kernel and patched receiver. The included verifier works without the original checkout.

The bundle is explicitly `review_only`, with `launch_allowed: false`. There is no launcher or installer. Executables are preserved for review; the flag is a packaging policy, not an operating-system execution restriction. Operator configuration, calibration, receiver setup, runtime logs and test outputs are omitted from runnable payload folders. Source fixtures remain in source provenance only.

## Important integration gap

The recent offline improvements live in the main checkout. This console's `App.xaml.cs` does not support the integration branch's explicit data-directory startup or isolated UI test setup. It also lacks that branch's integrated text/timeout work. The integration worktree at `.claude/worktrees/keyboard-spec-reconcile` contains those changes. Do not promote this main-checkout package as if it included both lines of work.

The staged receiver requires external native runtime libraries, GStreamer plugins/scanner and Bonjour. They are not bundled or independently attested here. .NET 8 Desktop is also external; its local inventory is saved in `dotnet-runtimes.txt`. Package integrity does not mean these dependencies or live configuration are ready.

## Validation

| Check | Result |
|---|---|
| New packaging tests, synthetic files only | 22 passed |
| Existing build-manifest regressions | 9 passed |
| Original console/kernel build records | Source and output hashes match |
| Patched receiver | All 79 recorded source hashes and executable match native record |
| Bundle verification from its own folder | Passed |
| ZIP CRC and verification after extraction to a path with spaces | Passed |
| Installed kernel, console and receiver hashes | Unchanged |

The new cases cover relocation after deleting the synthetic source checkout, existing-folder refusal, output boundary checks, stale source/build/native files, missing runtime artifacts, copy failure, alteration during copying, payload corruption, missing/extra files, altered review status, required-file removal, provenance mismatch, unsafe paths, duplicate JSON keys, missing blockers and an incorrect .NET framework declaration. Process creation is mocked to fail in the valid staging test, establishing that packaging does not invoke applications.

The tool checks all input records before creating output, copies only approved runtime artifacts and source records, verifies copied bytes, then writes its manifest. A copy failure leaves an incomplete directory without a completion manifest; a retry must use another directory. A failure in final structural verification exits nonzero; the presence of `package.json` alone is never acceptance. Nothing is deleted or overwritten by the tool.

Checksums are integrity records, not signatures. A coordinated replacement of the files and all their manifests is outside this verifier's threat model. The external ZIP checksum in `package-checksums.json` provides a separate reference to retain with backups.

## Documentation and preservation

`docs/RELEASE-STAGING.md` explains offline verification, included/excluded assets, integration/startup prerequisites, and how to prepare and verify rollback during a later approved window. It supplies no live launch command for this unintegrated package. Documentation self-review: 10/10 checklist items; no unresolved instruction presented as an executable procedure. Physical release blockers remain explicit.

The report, ZIP, checksums, scripts, tests and guide are copied to `../iMouseXP-2.0-evidence-archive/20261012-release-staging/`, with verified SHA-256 sums. The original scratch builds and previous evidence archives are retained.

No application window, rack API, phone input, operator settings access, service restart, receiver advertisement, deployment, commit or push. No missing-space/FKA investigation resumed.

## Next

Reconcile the offline patches with `claude/input-timeout-integration` in an isolated checkout, preserving its startup isolation and typing/timeout work, then rerun affected mock suites. Do this before creating a runnable candidate or expanding physical acceptance work.
