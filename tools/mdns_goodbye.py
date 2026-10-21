"""Withdraws AirPlay names that a stopped receiver left behind on the network.

The kernel ends a UxPlay receiver by killing it, so the receiver's built-in mDNS responder never
sends its goodbye. Every phone then keeps listing the dead receiver for the record lifetime
(MDNSD_TTL_SERVICE, 4500 s). This sends that goodbye on the receiver's behalf: the two service
PTR records (_airplay._tcp and _raop._tcp) with TTL 0, which RFC 6762 section 10.1 says listeners
must drop within one second.

Refuses any receiver whose kernel reports it running (receiver PID above zero), so a live
receiver is never withdrawn. Sends no phone input and starts nothing.

  python tools/mdns_goodbye.py --receivers <receivers.json> --board C214 [--board 724E] [--status-url URL]
"""
import argparse
import json
import socket
import time
import urllib.request
from pathlib import Path

GROUP, PORT = '224.0.0.251', 5353


def name_bytes(name):
    out = b''
    for label in name.rstrip('.').split('.'):
        raw = label.encode('utf-8')
        if not 0 < len(raw) < 64: raise ValueError(f'Bad DNS label in {name!r}')
        out += bytes([len(raw)]) + raw
    return out + b'\0'


def ptr(owner, target):
    rdata = name_bytes(target)
    # type PTR (12), class IN (1, no cache-flush bit on shared records), TTL 0 = goodbye.
    return name_bytes(owner) + (12).to_bytes(2, 'big') + (1).to_bytes(2, 'big') + (0).to_bytes(4, 'big') + len(rdata).to_bytes(2, 'big') + rdata


def goodbye_packet(receiver):
    mac = receiver['Mac'].replace(':', '').upper()
    records = [ptr('_airplay._tcp.local', f"{receiver['Name']}._airplay._tcp.local"),
               ptr('_raop._tcp.local', f"{mac}@{receiver['Name']}._raop._tcp.local")]
    # Response header: id 0, flags 0x8400 (authoritative answer), no questions, N answers.
    return (0).to_bytes(2, 'big') + (0x8400).to_bytes(2, 'big') + (0).to_bytes(2, 'big') + len(records).to_bytes(2, 'big') + bytes(4) + b''.join(records)


def running(status_url):
    try:
        with urllib.request.urlopen(status_url, timeout=3) as response:
            rows = json.load(response)['data']['receivers']
    except OSError:
        return set()   # No kernel answering: nothing is running under it.
    return {r['name'] for r in rows if r.get('receiver_pid', 0) > 0}


def addresses():
    # Every IPv4 interface, as the receiver announced on each; link-local ones are skipped.
    found = {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    return sorted(a for a in found if not a.startswith(('127.', '169.254.')))


def send(packets, repeats=3):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        # Listeners ignore mDNS responses not sent from port 5353 (RFC 6762 section 11).
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('', PORT))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        for attempt in range(repeats):
            for address in addresses():
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(address))
                for packet in packets: sock.sendto(packet, (GROUP, PORT))
            if attempt + 1 < repeats: time.sleep(1)
    finally:
        sock.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--receivers', required=True)
    parser.add_argument('--board', action='append', required=True)
    parser.add_argument('--status-url', default='http://127.0.0.1:9916/api/kernel/status')
    args = parser.parse_args()
    configured = {r['BoardPid'].upper(): r for r in json.loads(Path(args.receivers).read_text(encoding='utf-8-sig'))}
    chosen = []
    for board in args.board:
        if board.upper() not in configured: raise SystemExit(f'No receiver is configured for board {board}.')
        chosen.append(configured[board.upper()])
    live = running(args.status_url) & {r['Name'] for r in chosen}
    if live: raise SystemExit('Refused: running receivers must not be withdrawn: ' + ', '.join(sorted(live)))
    send([goodbye_packet(r) for r in chosen])
    print(json.dumps({'withdrawn': [r['Name'] for r in chosen], 'interfaces': addresses()}))


if __name__ == '__main__':
    main()
