"""The one phone a live farm window may drive.

A window used to be locked to C24C by constants. With several phones on one kernel, each window
is given exactly one PhoneIdentity (from its prepared creation config) and every gate compares
against it: the kernel client refuses any other target, and the window reads only its own
receiver's frames. There is no default in the live path; LEGACY_C24C exists for the single-phone
tools and tests written before the rack had more than one phone.
"""
from dataclasses import dataclass
import re


class PhoneIdentityError(ValueError):
    pass


@dataclass(frozen=True)
class PhoneIdentity:
    board: str          # Board PID, four hex digits, e.g. 'C24C'.
    device_id: str      # The phone's AirPlay device ID, which the kernel uses as its input target.
    receiver: str       # Its receiver's AirPlay name, e.g. 'iMouse2-18'.
    slot: int = 0       # Box slot (1 = far left); 0 for the pre-rack C24C setup.

    def __post_init__(self):
        if not isinstance(self.board, str) or not re.fullmatch(r'[0-9A-F]{4}', self.board):
            raise PhoneIdentityError('Board must be four upper-case hexadecimal digits.')
        if not isinstance(self.device_id, str) or not re.fullmatch(r'([0-9A-F]{2}:){5}[0-9A-F]{2}', self.device_id):
            raise PhoneIdentityError('Device ID must be an upper-case MAC-style identifier.')
        if type(self.slot) is not int or not 0 <= self.slot <= 20:
            raise PhoneIdentityError('Slot must be 0 to 20.')
        expected = f'iMouse2-{self.slot}' if self.slot else 'iMouse2-' + self.board
        if self.receiver != expected:
            raise PhoneIdentityError(f'Receiver must be {expected} for this phone.')

    def targets(self, value):
        """True when a kernel target string names this phone (board PID or device ID)."""
        return isinstance(value, str) and value.upper() in (self.board, self.device_id)

    @classmethod
    def from_config(cls, value):
        if not isinstance(value, dict) or set(value) != {'board', 'deviceId', 'receiver', 'slot'}:
            raise PhoneIdentityError('Phone config needs exactly board, deviceId, receiver and slot.')
        return cls(board=value['board'], device_id=value['deviceId'], receiver=value['receiver'], slot=value['slot'])

    def as_config(self):
        return dict(board=self.board, deviceId=self.device_id, receiver=self.receiver, slot=self.slot)


LEGACY_C24C = PhoneIdentity(board='C24C', device_id='86:1D:4A:04:2F:F6', receiver='iMouse2-C24C')


def own_receiver(status, phone):
    """This phone's receiver row from /kernel/status. Never another phone's, never a guess."""
    rows = [r for r in (status or {}).get('receivers') or [] if isinstance(r, dict) and r.get('deviceid') == phone.device_id]
    if len(rows) != 1 or rows[0].get('name') != phone.receiver:
        raise PhoneIdentityError(f'Kernel does not report exactly one receiver {phone.receiver} for {phone.board}.')
    return rows[0]
