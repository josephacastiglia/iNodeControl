# Test build 1 implementation decisions

- WPF on .NET 8, native Windows controls, Segoe UI, dark surfaces and a teal accent. The UI/UX Pro Max skill was applied; its generated landing-page pattern was not applicable to a desktop utility, so the implementation follows the skill's native-control, visible-label, focus-state, contrast, and feedback guidance.
- Reuse the documented XP service over HTTP. No source changes to the original binaries, no service registration, and no firmware changes.
- Poll device status every five seconds. Image polling is restricted to one selected online phone; each request finishes before another image request begins.
- Mutations are explicit user actions with a captured list of target IDs. Batch selection requires a separate mode. Offline input targets are skipped, while casting requests may target offline records.
- Service-generation checks and selected-device checks reject stale async results. Connection changes are disabled while an explicit command is in flight. Closing cancels the request lifetime; it does not issue stop-casting commands.
- Mouse coordinates scale from the letterboxed preview into device logical dimensions. Actual image orientation determines width/height ordering. This is unit-tested but needs physical alignment verification.
- Build tooling: official SDK download attempts failed DNS resolution. The delivered build instead uses Roslyn 5.0 bundled with PowerShell and installed .NET 8.0.14 assemblies. Generated XAML field/event wiring is kept under `.tools/generated`. The authored WPF project remains suitable for an ordinary SDK workflow.
- The launcher uses .NET Framework to run the .NET 8 WPF entry point with no console window. Both frameworks are present on the target PC. The package contains no original account settings or device logs.

Sources: saved XP API pages in `analysis/site-reference/`. Read `TESTING.md` for validation coverage and outstanding physical-device checks.
