# Native carousel transfer and marketing acceptance audit

17 October 2026. Continues `f770b34` on `local/combined-candidate-20261012`.

## Delivered

- Native carousel editor's **Transfer to C24C** dialog: saved revision/account selection, explicit PC/phone private IPv4 addresses, expiring link, delivery counts, status recovery and Stop. Closing requests cleanup; inability to confirm is reported with the original expiry bound. No clipboard injection or phone command is sent by this dialog.
- Durable media-session journal, immutable package bytes, request-ID deduplication, restart-as-interrupted behavior, single listener across backend instances and expiry. URLs exist in memory only and are removed from closed status responses. Image GETs remain separate from Photos/Instagram saves.
- The control server remains loopback-only and exclusively binds its port before initializing runtime data. The LAN listener serves only selected media, never the farm API.
- Feature readiness is available from the native tab and `/api/farm/capabilities`; unaccepted automation is labelled and remains refused.
- Corrected phase-one warmup planning and schedule daily-budget time handling.
- Reworked low-view review: raw counts are insufficient; structured observations require account/platform, distinct post IDs and timestamps. The newest three submitted posts must be at least 24 hours old at observation, with observations no more than 24 hours old. Records are retained; low views can latch a pause, never clear it or diagnose a platform restriction. Lifetime totals do not replace `views_24h`.

## Evidence

| Check | Final result |
|---|---|
| Python full suite | 149 passed, no skips |
| Native Release build | 0 warnings, 0 errors |
| Native self-test | 459 passed; all command transports mocked |
| Engine and server self-checks | Both passed with a loopback-only test network guard |
| Regression controls | 3/3 new cases fail as assertions against old `f770b34`; current engine passes |
| Candidate launcher | ValidateOnly passed; no processes started |
| Transfer view | Headless render inspected; no visible/native window created |
| Real phone / desktop interactions in this pass | None; only read-only kernel status |

Candidate: `output/codex-farm-transfer-20261017`.

Native DLL SHA-256: `81dd034a5910edd95b0fec8bc92a6f1e6df5236def7569c7def0b1274472a591`.

Backend source hash (server, engine, jobs, drafts, media server, transfers, capabilities in launcher order): `d7bab410367d8ef27681fa4448c88597eee786fdc58fd51e141cbaad3092d63a`.

Build was compiled from working changes on `f770b34`; its DLL hash and source inventory identify this build. Do not use a pre-commit version stamp alone as source provenance.

The installed console, kernel and receivers were left running as they were. The live status read showed C24C still mirroring and C241 still offline with unchanged receiver PIDs/restart counts. This pass did not change the previous phone draft, Photos images, FKA or account settings. Test listeners use ephemeral loopback ports and are closed.

## Test limitations and intermediate failures

- Initial Python run exposed an open SQLite connection and sandbox denial of loopback connections. Connection disposal was fixed; guarded HTTP tests were then run with socket permission.
- The first native run hit the sandbox's atomic-file replacement restriction before farm checks. Its failure record is preserved in this folder. The approved headless rerun and final build pass.
- One intermediate slow-client assertion required closure under two seconds. Windows completed the blocked receive after about 2.02 seconds. The contract is bounded cleanup, so the final check uses the documented four-second Stop boundary and still requires the listener to be closed. Request handling also has a three-second absolute connection budget.
- No interactive UI test, automatic app-state recognition, publishing or messaging acceptance is claimed. One supervised Instagram draft pass belongs to the prior report, not to this new build's native controls.

## Reproduce

```powershell
python -m unittest discover -s tools -p 'test_farm_*.py' -v
python analysis/farm-native-transfer-20261017/run_engine_checks.py
python analysis/farm-native-transfer-20261017/check_prior_regressions.py
dotnet build src/iMouse.Console/iMouse.Console.csproj -c Release -o output/codex-farm-transfer-20261017 --no-restore
dotnet output/codex-farm-transfer-20261017/iMouse2.dll --self-test
& '.\Open Marketing Farm Candidate.ps1' -ValidateOnly
```

Negative control script succeeds only when the three selected old-code regressions fail as expected. It loads old code in memory and never changes working source.

## Submitted analytics API

`POST /api/farm/shadowban-scan` remains the legacy route name. Use `device_id: "C24C"` and `observations`, a list of 3–20 objects with `post_id`, `account`, `platform`, integer `views`, and timezone-qualified ISO `published_at` / `observed_at`. This is labelled `operator_submitted`. It performs no phone input and does not require a running kernel. The raw `recent_views` form reports incomplete evidence and leaves state unchanged. Automatic screenshot extraction currently has no configured observation provider and remains unavailable.

## Remaining work

See `MARKETING-FARM-ACCEPTANCE.md`. Finish observed draft workflows for designated accounts before enabling unattended app actions. Scheduling needs an actual durable recurring service; analytics needs a validated observation source; messages and publication remain outside current authorization. Keep all previous evidence and the installed release intact.
