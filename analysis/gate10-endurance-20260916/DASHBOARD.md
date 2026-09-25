# Gate 10 endurance dashboard

Analyzer: Grok 4.7. Generated 2026-09-24T04:34:31+00:00. Read-only; soak was not touched.

- As of: 2026-09-24T04:04:10.206+00:00 (elapsed 5:17:45, remaining 0:00:14)
- Started: 2026-09-23T22:46:24.338+00:00
- Running: False
- Fleet: kernel 4376 / console 11224 / match True
- Rows: 2025 parsed (0 incomplete), live samples 1272, live interactions 64
- Prior sessions excluded: kernel 34032 (656 samples, 33 interactions)

## Gates

| check | value | result |
| --- | --- | --- |
| receiver restarts | 0 | PASS |
| stream freezes >2s | 0 | PASS |
| stuck keys/buttons | 0 | PASS |
| processes alive | yes | PASS |
| memory drift | WS +89.9 MB/h, private +92.8 MB/h | RISING/RISING |

FLAT means |slope| < 5 MB/h. Full-session slope is not a warmup artifact: last 30m WS +54.9 MB/h, private +56.9 MB/h.

## Phones

| phone | received | counter | avg fps | fps 60s | min fps | max fps | restarts | freezes | state | live | pid |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C24C | 290,995 | 299,070 | 15.26 | 14.39 | 8.05 | 20.83 | 0 | 0 | mirroring | yes | 3420 |
| C241 | 289,980 | 297,825 | 15.21 | 16.06 | 7.33 | 20.94 | 0 | 0 | mirroring | yes | 8868 |
| C214 | 380,918 | 388,367 | 19.98 | 20.16 | 13.42 | 21.87 | 0 | 0 | mirroring | yes | 10496 |
| 724E | 381,650 | 382,938 | 20.02 | 20.14 | 16.22 | 21.30 | 0 | 0 | mirroring | yes | 12148 |
| Phone 5 | 388,233 | 395,185 | 20.36 | 20.26 | 18.61 | 21.34 | 0 | 0 | mirroring | yes | 21952 |

Received is frames gained this session. FPS uses inter-sample deltas; a zero-frame gap over 2s is a freeze, not a low FPS.

## Memory

10-minute window: 41 samples. Aggregate WS 707.9 -> 855.1 -> 1133.2 MB. Private 625.5 -> 777.8 -> 1064.4 MB.

| process | pid | name | ws MB | private MB | 10m ws med | 10m ws peak | 10m priv med | 10m priv peak | ws MB/h | priv MB/h |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| kernel | 4376 | iMouse2.Kernel.exe | 88.4 | 50.4 | 88.4 | 88.4 | 50.4 | 50.4 | +0.0 | +0.0 |
| console | 11224 | iMouse2.exe | 213.1 | 263.4 | 213.1 | 213.1 | 263.4 | 263.4 | -0.1 | -0.1 |
| receiver C24C | 3420 | uxplay.exe | 165.5 | 149.3 | 164.6 | 165.5 | 148.4 | 149.3 | +17.7 | +18.3 |
| receiver C241 | 8868 | uxplay.exe | 168.9 | 152.6 | 167.9 | 168.9 | 151.6 | 152.6 | +18.7 | +19.3 |
| receiver C214 | 10496 | uxplay.exe | 166.6 | 150.4 | 165.7 | 166.6 | 149.5 | 150.4 | +18.0 | +18.5 |
| receiver 724E | 12148 | uxplay.exe | 165.4 | 149.2 | 164.3 | 165.4 | 148.1 | 149.2 | +17.9 | +18.5 |
| receiver Phone 5 | 21952 | uxplay.exe | 165.4 | 149.2 | 164.5 | 165.4 | 148.2 | 149.2 | +17.6 | +18.2 |
| aggregate | - | 1272 samples | 1133.2 | 1064.4 | 1128.6 | 1133.2 | 1059.5 | 1064.4 | +89.9 | +92.8 |

## Interactions

- Executed: 64
- Search click success: 0% (0/64)
- Dispatch latency p50: n/a (0 dispatched)
- Group Home response: n/a (0 dispatched)
- Stuck keys/buttons: 0
- Acquire codes: 409:64
- Errors: 64x A target is owned, stopped, or recovering. No leases acquired.

| phone | attempts | search success | dispatch p50 ms | group home |
| --- | --- | --- | --- | --- |
| C24C | 13 | 0% (0/13) | n/a | n/a |
| C241 | 13 | 0% (0/13) | n/a | n/a |
| C214 | 13 | 0% (0/13) | n/a | n/a |
| 724E | 13 | 0% (0/13) | n/a | n/a |
| Phone 5 | 12 | 0% (0/12) | n/a | n/a |

