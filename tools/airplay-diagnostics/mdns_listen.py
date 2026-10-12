"""Passive mDNS listener: records AirPlay-related queries and answers seen on one interface.

Sends nothing. For each packet mentioning _airplay/_raop (or an iMouse2 receiver), prints the
time, sender, whether it is a query or a response, the QU (unicast-reply) bit on questions,
and the names involved. Use it to see whether a given phone asks for AirPlay receivers and
whether the receivers' host answers it. Usage: python mdns_listen.py 192.168.4.26 SECONDS [logfile]
"""
import socket, struct, sys, time

iface, seconds = sys.argv[1], float(sys.argv[2])
log = open(sys.argv[3], "a", encoding="utf-8") if len(sys.argv) > 3 else None
GROUP, PORT = "224.0.0.251", 5353


def read_name(data, off, depth=0):
    labels = []
    while off < len(data) and depth < 20:
        n = data[off]
        if n == 0:
            return ".".join(labels), off + 1
        if n & 0xC0 == 0xC0:
            name, _ = read_name(data, ((n & 0x3F) << 8) | data[off + 1], depth + 1)
            return ".".join(labels + [name]) if name else ".".join(labels), off + 2
        labels.append(data[off + 1: off + 1 + n].decode("utf-8", "replace"))
        off += 1 + n
    return ".".join(labels), off


def parse(data):
    flags, qd, an, ns, ar = struct.unpack("!HHHHH", data[2:12])
    off, questions, answers = 12, [], []
    for _ in range(qd):
        name, off = read_name(data, off)
        qtype, qclass = struct.unpack("!HH", data[off: off + 4])
        off += 4
        questions.append((name, qtype, bool(qclass & 0x8000)))
    for _ in range(an + ns + ar):
        name, off = read_name(data, off)
        rtype, _, ttl, rdlen = struct.unpack("!HHIH", data[off: off + 10])
        off += 10
        value = read_name(data, off)[0] if rtype == 12 else ""
        answers.append((name, rtype, value, ttl))
        off += rdlen
    return bool(flags & 0x8000), questions, answers


def relevant(text):
    return "_airplay" in text or "_raop" in text or "iMouse2" in text


def out(line):
    print(line, flush=True)
    if log:
        log.write(line + "\n"); log.flush()


sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("", PORT))
sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(GROUP) + socket.inet_aton(iface))
sock.settimeout(0.5)
start = time.time()
out(f"{time.strftime('%H:%M:%S')} listening on {iface} for {seconds:.0f} s (sends nothing)")
while time.time() - start < seconds:
    try:
        data, (src, sport) = sock.recvfrom(9000)
    except socket.timeout:
        continue
    try:
        is_response, questions, answers = parse(data)
    except Exception:
        continue
    now = time.strftime("%H:%M:%S")
    if not is_response:
        asked = [f"{n}{' QU' if qu else ''}" for n, t, qu in questions if relevant(n)]
        if asked:
            out(f"{now} QUERY    from {src}:{sport}  {', '.join(asked)}  (+{sum(1 for a in answers if relevant(a[0]) or relevant(a[2]))} known answers)")
    else:
        rel = [a for a in answers if a[1] == 12 and (relevant(a[0]) or relevant(a[2]))]
        if rel:
            kind = "GOODBYE " if all(a[3] == 0 for a in rel) else "RESPONSE"   # TTL 0 withdraws the records
            names = sorted({f"{a[2] or a[0]} ttl={a[3]}" for a in rel})
            out(f"{now} {kind} from {src}:{sport}  {', '.join(names)}")
out(f"{time.strftime('%H:%M:%S')} done")
