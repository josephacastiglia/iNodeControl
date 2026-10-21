"""Reports mDNS questions for AirPlay receivers, by sender address. Listens only; sends nothing.

An iPhone asks for _airplay._tcp when its Screen Mirroring list opens, so a question from that
phone's address is network evidence that the list is on screen. Used as a library by the
auto-connect, or on its own:

  python tools/mdns_watch.py --seconds 20 [--source 192.168.4.57]
"""
import argparse
import socket
import struct
import time

GROUP, PORT = '224.0.0.251', 5353
SERVICES = ('_airplay._tcp.local', '_raop._tcp.local')


def read_name(packet, offset, depth=0):
    labels = []
    while True:
        if offset >= len(packet) or depth > 10: raise ValueError('bad name')
        length = packet[offset]
        if length == 0: return '.'.join(labels), offset + 1
        if length & 0xC0 == 0xC0:
            pointer = struct.unpack_from('>H', packet, offset)[0] & 0x3FFF
            name, _ = read_name(packet, pointer, depth + 1)
            return '.'.join(labels + [name]) if name else '.'.join(labels), offset + 2
        labels.append(packet[offset + 1:offset + 1 + length].decode('utf-8', 'replace'))
        offset += 1 + length


def questions(packet):
    """Question names of an mDNS query; empty for responses or malformed packets."""
    if len(packet) < 12: return []
    flags, count = struct.unpack_from('>H', packet, 2)[0], struct.unpack_from('>H', packet, 4)[0]
    if flags & 0x8000: return []
    names, offset = [], 12
    try:
        for _ in range(count):
            name, offset = read_name(packet, offset)
            names.append(name.lower()); offset += 4
    except (ValueError, struct.error, IndexError):
        return names
    return names


class Watcher:
    def __init__(self, interface):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('', PORT))
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(GROUP) + socket.inet_aton(interface))
        self.sock.settimeout(0.2)

    def airplay_queries(self, seconds, source=None):
        """Yields (time, sender) for each AirPlay question received within the window."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try: packet, (sender, _) = self.sock.recvfrom(9000)
            except socket.timeout: continue
            if source and sender != source: continue
            if any(q in SERVICES for q in questions(packet)): yield time.time(), sender

    def drain(self):
        self.sock.settimeout(0)
        try:
            while True: self.sock.recvfrom(9000)
        except (BlockingIOError, socket.timeout, OSError): pass
        finally: self.sock.settimeout(0.2)

    def close(self): self.sock.close()


def lan_address():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(('192.0.2.1', 9))   # Picks the default-route interface; sends nothing.
        return probe.getsockname()[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=float, default=20)
    parser.add_argument('--source')
    args = parser.parse_args()
    watcher = Watcher(lan_address())
    try:
        for when, sender in watcher.airplay_queries(args.seconds, args.source):
            print(f'{time.strftime("%H:%M:%S", time.localtime(when))} AirPlay query from {sender}', flush=True)
    finally:
        watcher.close()


if __name__ == '__main__':
    main()
