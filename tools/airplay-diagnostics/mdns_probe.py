"""Read-only mDNS probe (optional 3rd argument: comma-separated PTR names to ask for): asks one interface's LAN who offers AirPlay, and lists who answers.

Sends a standard mDNS PTR query for _airplay._tcp.local and _raop._tcp.local (what an iPhone
sends when Screen Mirroring opens) out of the interface with the given IPv4 address, then
listens on 224.0.0.251:5353 for a few seconds and prints every responder and the service
names it announced. Changes no setting.
Usage: python mdns_probe.py 192.168.4.26 [seconds] [name1,name2]
"""
import os, socket, struct, sys, time

iface = sys.argv[1]
seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 6.0
GROUP, PORT = "224.0.0.251", 5353


def qname(name):
    return b"".join(bytes([len(p)]) + p.encode() for p in name.split(".") if p) + b"\0"


def query(names):
    header = struct.pack("!HHHHHH", 0, 0, len(names), 0, 0, 0)
    qclass = 0x8001 if os.environ.get("MDNS_QU") else 1   # QU bit asks for a unicast reply, as an iPhone's first query does
    return header + b"".join(qname(n) + struct.pack("!HH", 12, qclass) for n in names)   # PTR, IN


def read_name(data, off, depth=0):
    labels = []
    while off < len(data) and depth < 20:
        n = data[off]
        if n == 0:
            return ".".join(labels), off + 1
        if n & 0xC0 == 0xC0:
            ptr = ((n & 0x3F) << 8) | data[off + 1]
            name, _ = read_name(data, ptr, depth + 1)
            return ".".join(labels + [name]) if name else ".".join(labels), off + 2
        labels.append(data[off + 1: off + 1 + n].decode("utf-8", "replace"))
        off += 1 + n
    return ".".join(labels), off


def records(data):
    qd, an, ns, ar = struct.unpack("!HHHH", data[4:12])
    off = 12
    for _ in range(qd):
        _, off = read_name(data, off)
        off += 4
    out = []
    for _ in range(an + ns + ar):
        name, off = read_name(data, off)
        rtype, _, ttl, rdlen = struct.unpack("!HHIH", data[off: off + 10])
        off += 10
        rdata = data[off: off + rdlen]
        value = ""
        if rtype == 12:
            value, _ = read_name(data, off)
        elif rtype == 1 and rdlen == 4:
            value = socket.inet_ntoa(rdata)
        elif rtype == 33:
            target, _ = read_name(data, off + 6)
            value = f"{target}:{struct.unpack('!H', rdata[4:6])[0]}"
        out.append((rtype, name, value, ttl))
        off += rdlen
    return out


sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("", PORT))
sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(GROUP) + socket.inet_aton(iface))
sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(iface))
sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
sock.settimeout(0.5)
sent = time.time()
names = sys.argv[3].split(",") if len(sys.argv) > 3 else ["_airplay._tcp.local", "_raop._tcp.local"]
sock.sendto(query(names), (GROUP, PORT))
print(f"{time.strftime('%H:%M:%S')} query sent from {iface}; listening {seconds:.0f} s")
seen = {}
while time.time() - sent < seconds:
    try:
        data, (src, _) = sock.recvfrom(9000)
    except socket.timeout:
        continue
    if struct.unpack("!H", data[2:4])[0] & 0x8000 == 0:
        continue   # a query, not a response
    try:
        recs = records(data)
    except Exception:
        continue
    for rtype, name, value, ttl in recs:
        if rtype in (12, 33, 1):
            key = (src, rtype, name, value)
            if key not in seen:
                seen[key] = ttl
                kind = {12: "PTR", 33: "SRV", 1: "A"}[rtype]
                print(f"  from {src:15} {kind:3} {name} -> {value} ttl={ttl}")
print(f"{time.strftime('%H:%M:%S')} done; responders: {sorted({k[0] for k in seen})}")
