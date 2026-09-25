# Priority 2 Live Acceptance Run Report — 17 September 2026

## Configuration
- **Kernel**: `release/iMouse2-kernel-ownership/iMouse2.Kernel.exe` (PID 9340, port 9913)
- **Console**: `release/iMouse2-ownership-console/iMouse2.exe` (PID 27056)
- **Phones**:
  - `86:1D:4A:04:2F:F6` (C24C, board `C24CBFBD`, receiver `iMouse2-C24C`)
  - `FE:A9:BC:D7:A0:44` (C241, board `C241BFBD`, receiver `iMouse2-C241`)
- **Baseline Snapshot**: Verified both phones mirroring with 0 receiver restarts.
  - C24C: 13,637 frames received (`00-baseline-c24c.bmp`)
  - C241: 21,004 frames received (`00-baseline-c241.bmp`)

## Measurement Methodology
- **A2 Latency Method**: Console-side measurement: Activity log entry at Stop click (`HH:mm:ss.fff  Input stopped: <ids>`) versus timestamp of the first incoming mirror frame showing the button released.
- **A7 Renewal Verification**: Verified via kernel lease state and `/input/renew` dispatch count every 10 seconds.
- **A10 Active Hover Method**: 10 continuous minutes with cursor active over the phone picture, maintaining steady `/mouse/move` traffic over USB HID link, counting transient failures tripping the pause latch.

## Results Matrix
| # | Test | Status | Evidence / Notes |
|---|---|---|---|
| A1 | Tap, drag, long press, Home on each phone | Pending | |
| A2 | Stop mid-drag (held press, Stop click) | Pending | |
| A3 | Stop, then try to tap | Pending | |
| A4 | Resume, then tap | Pending | |
| A5 | Stop with video offline | Pending | |
| A6 | Unplug C241 cable during held press, Stop | Pending | |
| A7 | Idle for 40s with phone selected | Passed | 170+ renewals recorded since 01:35 EDT, every 10s on 30s lease, 0 pauses |
| A8 | Selection change C24C to C241 | Pending | |
| A9 | Disconnect from Settings | Pending | |
| A10 | 10-minute active hover move stability | Pending | |
