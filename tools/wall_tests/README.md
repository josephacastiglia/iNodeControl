# Offline phone-wall checks

Run `dotnet run --project tools/wall_tests/WallTests.csproj -c Release`.

22 cases link the actual tile lifetime registry, screenshot limiter, freshness tracker, rate meter and API client. Injected HTTP handlers accept only screenshot GETs; there is no socket fallback or active input client. No WPF window, phone or operator settings are used.

Coverage: independent delivery states for 19 simulated phones; at most three in-flight fetches; one held peer while the other 18 finish; timeout versus caller cancellation; cancellation while queued and active; recovery of every occupied slot after failure; cancelled, replaced and removed streams; and a late response from a delegate that ignores cancellation. Six console self-tests additionally cover tile binding notifications, identity text, update-rate wording and unchanged input readiness.

The limiter bounds requests, not UI work. A slot is released before decode, presentation or retry delay. HTTP supplies its normal timeout; a delegate that ignores cancellation can occupy its slot until it finishes. These tests do not measure real rack throughput, WPF rendering, network latency or physical frame delivery.
