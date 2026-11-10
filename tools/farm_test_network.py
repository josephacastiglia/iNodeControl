"""Shared test-only allowlist: ephemeral loopback servers, never the real rack."""
import sys

allowed_ports = set()
# Every connection the guard refused, in order. A test that must reach no kernel compares its slice of this.
refused = []


def network_guard(event, args):
    if event == 'socket.connect':
        address = args[1]
        if not isinstance(address, tuple) or address[0] != '127.0.0.1' or address[1] not in allowed_ports:
            refused.append(address)
            raise AssertionError('HTTP tests may connect only to their own ephemeral server.')


sys.addaudithook(network_guard)


def mark():
    """A position in `refused`. since(mark()) lists what the guard refused after that point."""
    return len(refused)


def since(position):
    return refused[position:]
