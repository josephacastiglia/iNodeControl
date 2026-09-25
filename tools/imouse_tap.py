"""Randomised tapping for the iMouse XP kernel.

Every coordinate action picks a random point INSIDE the target area instead of its exact
centre, so repeated taps on the same control never land on the identical pixel.

Why not just tap the centre: a script that taps an icon a thousand times sends the exact
same pixel a thousand times. A finger never does that. This draws from a clamped Gaussian
centred on the target, so most taps land mid-control with a natural spread and none ever
fall outside the usable area - the tap varies, but it cannot miss.

Coordinates are in the phone's MIRROR-IMAGE space (500 x 1080 on the XR rack), which is
what /mouse/click, /mouse/move and /pic/screenshot all use. NOT iOS logical points
(414 x 896); using those would put every tap in the wrong place.

Usage
-----
    from imouse_tap import Phone

    p = Phone("86:1D:4A:04:2F:F6")
    p.reset()                                  # clears the silent stuck-click state
    p.tap(423, 122, 96, 104)                   # random point inside the Grindr icon
    p.hold(423, 122, 96, 104, ms=900)          # long press, random point, for context menus
    p.screenshot("now.png")

Self-check (no phone needed):
    python imouse_tap.py --check
Live demo against the rack:
    python imouse_tap.py --demo <device-id>
"""
from __future__ import annotations

import json
import random
import sys
import time
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:9911/api"

# Fraction of the target actually used. 0.80 keeps taps off the outer rim, so they still
# land on the control even when the size estimate is a little loose.
INSET = 0.80
# 0.0 spreads evenly across the inset area; 1.0 clusters tight at the centre.
# 0.40 reads like a finger: clustered in the middle, with real variation.
BIAS = 0.40


def jitter(cx, cy, w, h, *, inset=INSET, bias=BIAS, rng=random):
    """Return a random (x, y) inside a target of size w x h centred on (cx, cy)."""
    hw, hh = (w * inset) / 2.0, (h * inset) / 2.0
    sx, sy = max(hw * (1.0 - bias), 0.5), max(hh * (1.0 - bias), 0.5)
    while True:  # reject the tail rather than clamping, or points pile up on the edge
        dx, dy = rng.gauss(0, sx), rng.gauss(0, sy)
        if abs(dx) <= hw and abs(dy) <= hh:
            return int(round(cx + dx)), int(round(cy + dy))


def jitter_rect(x0, y0, x1, y1, **kw):
    """Same as jitter(), but from a bounding box (top-left, bottom-right)."""
    return jitter((x0 + x1) / 2.0, (y0 + y1) / 2.0, abs(x1 - x0), abs(y1 - y0), **kw)


def human_pause(lo=0.25, hi=0.75, rng=random):
    """A short irregular wait, so a sequence of taps isn't metronomic either."""
    time.sleep(rng.uniform(lo, hi))


class Phone:
    """Thin client for one phone on the kernel. Every tap is randomised by default."""

    def __init__(self, device_id, base=BASE, rng=None, timeout=8):
        self.id = device_id
        self.base = base
        self.rng = rng or random.Random()
        self.timeout = timeout
        self.last_point = None

    # --- transport ---
    def _call(self, path, **params):
        params["id"] = self.id
        url = f"{self.base}{path}?{urllib.parse.urlencode(params)}"
        body = urllib.request.urlopen(url, timeout=self.timeout).read()
        return json.loads(body)["data"]["code"]

    def screenshot(self, path=None):
        """Fetch a live frame. Returns raw BMP bytes, or saves a PNG if a path is given."""
        url = f"{self.base}/pic/screenshot?id={urllib.parse.quote(self.id)}&binary=true"
        raw = urllib.request.urlopen(url, timeout=self.timeout).read()
        if path:
            import io
            from PIL import Image
            Image.open(io.BytesIO(raw)).convert("RGB").save(path)
        return raw

    # --- primitives ---
    def reset(self):
        """Clear the pointer. A phone can silently ignore clicks - notably right after an
        iOS sheet animation - until this is sent. Cheap; send it liberally."""
        return self._call("/mouse/reset")

    def move(self, x, y):
        return self._call("/mouse/move", x=x, y=y)

    def home(self):
        return self._call("/key/sendkey", fn_key="Home")

    # --- randomised actions ---
    def tap(self, cx, cy, w, h, *, settle=0.0, **kw):
        """Tap a random point inside the target. Returns (x, y, code)."""
        x, y = jitter(cx, cy, w, h, rng=self.rng, **kw)
        self.last_point = (x, y)
        self.move(x, y)
        time.sleep(0.15)
        code = self._call("/mouse/click", x=x, y=y, button=1)
        if settle:
            time.sleep(settle)
        return x, y, code

    def hold(self, cx, cy, w, h, *, ms=900, settle=0.0, **kw):
        """Long press at a random point: button down, hold, up. Returns (x, y, code)."""
        x, y = jitter(cx, cy, w, h, rng=self.rng, **kw)
        self.last_point = (x, y)
        self.move(x, y)
        time.sleep(0.15)
        self._call("/mouse/down", button=1)
        time.sleep(ms / 1000.0)
        code = self._call("/mouse/up", button=1)
        if settle:
            time.sleep(settle)
        return x, y, code

    def tap_rect(self, x0, y0, x1, y1, **kw):
        return self.tap((x0 + x1) / 2.0, (y0 + y1) / 2.0, abs(x1 - x0), abs(y1 - y0), **kw)


def _check():
    """Statistical self-check. No phone required."""
    import statistics as st
    rng = random.Random(7)
    cases = [("icon 96x104", 423, 122, 96, 104), ("pill 150x44", 250, 898, 150, 44)]
    ok = True
    for name, cx, cy, w, h in cases:
        pts = [jitter(cx, cy, w, h, rng=rng) for _ in range(2000)]
        hw, hh = w * INSET / 2, h * INSET / 2
        inside = all(abs(x - cx) <= hw + 0.5 and abs(y - cy) <= hh + 0.5 for x, y in pts)
        centre = sum(1 for x, y in pts if (x, y) == (cx, cy))
        uniq = len(set(pts))
        ok &= inside and centre < 20 and uniq > 500
        print(f"{name}: all inside target {inside} | distinct {uniq}/2000 | exact-centre hits {centre} "
              f"| sd x {st.pstdev([p[0] for p in pts]):.1f}px y {st.pstdev([p[1] for p in pts]):.1f}px")
    print("SELF-CHECK", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def _demo(device_id):
    """Three randomised taps on the Search pill, each dismissed with Home."""
    p = Phone(device_id)
    p.reset(); time.sleep(0.4); p.home(); time.sleep(1.2)
    for i in range(3):
        p.reset(); time.sleep(0.4)
        x, y, code = p.tap(250, 898, 150, 44, settle=1.4)
        print(f"tap {i + 1}: ({x},{y}) offset ({x - 250:+d},{y - 898:+d}) code {code}")
        p.home(); time.sleep(1.2)
    return 0


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(_check())
    if "--demo" in sys.argv:
        sys.exit(_demo(sys.argv[sys.argv.index("--demo") + 1]))
    print(__doc__)
