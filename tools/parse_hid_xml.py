"""Summarise the USB ETW XML dump: VID 720A devices, endpoints, OUT/IN sizes over time.

tracerpt does not emit transfer payloads (only buffer pointers), so this cannot
decode the 8-byte report. It can tell us whether interrupt OUT traffic happened.
"""
from __future__ import annotations

import collections
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}
XML = Path(__file__).resolve().parents[1] / "analysis" / "hid-captures" / "vid720a-20260913-234351.xml"


def text(el, path, default=""):
    n = el.find(path, NS)
    return (n.text or default) if n is not None else default


def data_map(event):
    out = {}
    ed = event.find("e:EventData", NS)
    if ed is None:
        return out
    for d in ed.iter():
        name = d.attrib.get("Name")
        if name and d.text:
            out[name] = d.text.strip()
    return out


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else XML
    devices = {}  # UsbDevice handle -> (vid, pid)
    endpoints = collections.defaultdict(list)
    xfers = []
    n = 0
    for _, ev in ET.iterparse(path, events=("end",)):
        if not ev.tag.endswith("Event"):
            continue
        n += 1
        if n % 50000 == 0:
            print(f"... {n} events", file=sys.stderr)
        fields = data_map(ev)
        task = text(ev, "e:RenderingInfo/e:Task")
        msg = text(ev, "e:RenderingInfo/e:Message")
        time = text(ev, "e:System/e:TimeCreated")
        if not time:
            tcel = ev.find("e:System/e:TimeCreated", NS)
            if tcel is not None:
                time = tcel.attrib.get("SystemTime", "")
        vid = fields.get("fid_idVendor", "")
        if vid.lower() == "0x720a":
            handle = fields.get("fid_UsbDevice", "")
            pid = fields.get("fid_idProduct", "")
            if handle:
                devices[handle] = (vid, pid)
        addr = fields.get("fid_bEndpointAddress")
        if addr and fields.get("fid_UsbDevice") in devices:
            endpoints[fields["fid_UsbDevice"]].append(
                (addr, fields.get("fid_bmAttributes"), fields.get("fid_wMaxPacketSize"))
            )
        if "BULK_OR_INTERRUPT" in task and "Complete" in msg:
            dev = fields.get("fid_UsbDevice") or fields.get("fid_URB_Hdr_UsbdDeviceHandle")
            if dev in devices:
                xfers.append(
                    (
                        time,
                        devices[dev][1],
                        fields.get("fid_URB_TransferFlags"),
                        fields.get("fid_URB_TransferBufferLength"),
                    )
                )
        ev.clear()

    print(f"events scanned: {n}")
    print(f"VID_720A devices: {len(devices)}")
    for h, (vid, pid) in sorted(devices.items(), key=lambda kv: kv[1][1]):
        eps = sorted(set(endpoints.get(h, [])))
        print(f"  {pid}  handle={h}  endpoints={eps}")

    print(f"interrupt completes on those devices: {len(xfers)}")
    counts = collections.Counter((flags, length) for _, _, flags, length in xfers)
    print("flags,length -> count")
    for k, c in counts.most_common(20):
        print(f"  {k}  {c}")

    # 1-second buckets of OUT (flags 0x2) vs IN (flags 0x3)
    buckets = collections.Counter()
    for time, pid, flags, length in xfers:
        sec = time[:19] if time else "?"
        direction = "OUT" if flags == "0x2" else "IN" if flags == "0x3" else flags
        buckets[(sec, direction, length)] += 1
    print("time  dir  length  count  (first 40 non-empty seconds)")
    shown = 0
    for (sec, direction, length), c in sorted(buckets.items()):
        print(f"  {sec}  {direction}  {length}  {c}")
        shown += 1
        if shown >= 40:
            break


if __name__ == "__main__":
    main()
