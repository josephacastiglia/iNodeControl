"""Offline decoder for saved WCH/iMouse HID bytes; never opens a device.

Interpretations come from MouseKeyItem.dll's static analysis and the September
captures. A board completion signal is not an iOS action acknowledgement.
See analysis/vendor-protocol-rea-20261014/REPORT.md for provenance and limits.
"""
import argparse
import json


def decode_report(report: bytes, *, direction: str, framing: str) -> dict:
    if direction not in ('in', 'out'):
        raise ValueError('direction must be in or out')
    if framing not in ('usb', 'windows'):
        raise ValueError('framing must be usb or windows; it is never guessed')
    payload_size = 16 if direction == 'in' else 8
    expected_size = payload_size + (framing == 'windows')
    if len(report) != expected_size:
        raise ValueError(f'Expected {expected_size} bytes, got {len(report)}')
    if framing == 'windows':
        if report[0] != 0:
            raise ValueError('Only the observed Windows report ID zero is supported')
        payload = report[1:]
    else:
        payload = report
    family = payload[0]
    result = {'direction': direction, 'framing': framing,
              'payload_hex': payload.hex(' '), 'family': f'{family:02x}',
              'kind': 'unknown', 'ios_outcome': 'not established by this report'}
    if direction == 'in':
        if family in (0xA0, 0xA1):
            result.update(kind='vendor_movement_completion_signal',
                          unknown_tail_hex=payload[1:].hex(' '),
                          correlation='No sequence ID decoded; do not match to a command by timing alone')
        elif family == 0xA5:
            result.update(kind='vendor_identifier_reply', identifier_hex=payload[1:7].hex(),
                          unknown_tail_hex=payload[7:].hex(' '),
                          identity_scope='Six-byte vendor identifier; not proven equivalent to DeviceStore UID')
        elif family in (0xA6, 0xAF):
            result.update(kind='vendor_status_event', unknown_tail_hex=payload[1:].hex(' '),
                          meaning='Host handler changes recovery/pacing state; physical cause unverified')
    elif family == 0xA1:
        result.update(kind='relative_mouse', buttons=payload[1],
                      dx=int.from_bytes(payload[2:3], 'little', signed=True),
                      dy=int.from_bytes(payload[3:4], 'little', signed=True),
                      unknown_tail_hex=payload[4:].hex(' '))
    elif family == 0xA2:
        result.update(kind='keyboard', modifier=payload[1], usages=list(payload[2:6]),
                      unassigned_byte6=payload[6], extended_byte7=payload[7],
                      vendor_fn=True if payload[7] == 2 else False if payload[7] == 0 else None,
                      unknown_extended_value=payload[7] if payload[7] not in (0, 2) else None)
    elif family == 0xA0:
        result.update(kind='absolute_mouse_candidate', buttons=payload[1],
                      x_raw=int.from_bytes(payload[2:4], 'little'),
                      y_raw=int.from_bytes(payload[4:6], 'little'),
                      unknown_tail_hex=payload[6:].hex(' '),
                      support='Static vendor mode only; not validated on this rack')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--direction', required=True, choices=['in', 'out'])
    parser.add_argument('--framing', required=True, choices=['usb', 'windows'])
    parser.add_argument('--hex', required=True, dest='hex_bytes', help='Saved bytes in hexadecimal')
    args = parser.parse_args()
    try:
        result = decode_report(bytes.fromhex(args.hex_bytes), direction=args.direction, framing=args.framing)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
