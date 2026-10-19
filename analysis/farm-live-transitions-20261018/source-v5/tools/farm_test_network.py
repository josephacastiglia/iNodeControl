"""Shared test-only allowlist: ephemeral loopback servers, never the real rack."""
import sys

allowed_ports = set()


def network_guard(event, args):
    if event == 'socket.connect':
        address = args[1]
        if not isinstance(address, tuple) or address[0] != '127.0.0.1' or address[1] not in allowed_ports:
            raise AssertionError('HTTP tests may connect only to their own ephemeral server.')


sys.addaudithook(network_guard)
