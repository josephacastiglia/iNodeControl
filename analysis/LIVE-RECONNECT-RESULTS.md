# Live reconnect check — 14 September 2026

After the user manually selected iMouse2-C24C, the port 9913 API reported
live:true with increasing frames. Receiver PID was 38772. The test script
verified phone 86:1D:4A:04:2F:F6 bound to C24C / C24CBFBD.

`tools/live-c24c-check.ps1` completed reset, Home, and exactly one Search click.
Visual inspection of `live-click-search.bmp` confirmed Search opened. This is
one successful live trial of the revised click timing, not a reliability claim.

Sending ASCII `Test 123!` through `/key/sendkey` still produced `Test123!` in the
visible Search field. Evidence: `live-typing-space.bmp`. The longer space hold
and inter-key gap have not resolved the missing-space issue.

All screenshots came directly from the independent port 9913 BMP endpoint.
No other phone was controlled. No vendor service was stopped. GUI rendering,
canned swipe, and broader reconnect/reliability tests remain unverified here.
