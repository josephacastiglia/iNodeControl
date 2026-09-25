# Single-port LED test: original preparation

Update: the test has been executed and concluded at the user's request. Automatic mode is restored. See LIVE-INDICATOR-TEST.md for the actual outcome and limitations. The following is the original preparation, not the final status.

The user authorized testing LED control while preserving phone operation. Transport preflight is complete; actual switching awaits a usable transport and physical observation.

## Preflight evidence

See test-preflight.json. All 19 boards remain Started. All four hubs return valid descriptors with port indicators advertised. Live PnP confirms C24C is attached to USB\VID_1A40&PID_0201\9&fe3f543&2&4 at port 1. The hub stack is Microsoft USBHUB3, with no Bus Hound filter. A libusb0 service exists on the PC, but the connected-device stack listing did not show it attached to these hubs.

Downloaded the official Bus Hound free installer from https://www.perisoft.net/cgi-bin/bhfree.cgi without executing it. The response is an MSI database; it is saved with the correct .msi extension. Authenticode is Valid, signed by Perisoft LLC. SHA256: 3387FDB6B6CF8E1E62986D6A5675D42A1213DCC0E3E1E8712C8376299BD3D758. Read-only MSI inspection identifies version 8.0, dinstall.exe and bhound10.sys. Generic MSI prerequisite strings do not establish actual prerequisites. Installation adds a system driver and may require disruption/restart; no installation or reboot has been performed.

## Candidate transport

Infineon documents using Bus Hound to issue the USB-standard PORT_INDICATOR command on its HX2VL hub: https://community.infineon.com/t5/Knowledge-Base-Articles/Manual-Control-of-a-USB-HUB-Port/ta-p/250727

That is evidence of a Windows testing method, not proof that this different hub model will respond or that all photographed lights are wired to hub indicator pins. Bus Hound is not currently installed. Its vendor supports Windows 10/11: https://www.perisoft.net/bushound/

The built-in legacy USBUSER_SET_ROOTPORT_FEATURE is explicitly discouraged by Microsoft and targets root ports rather than these external hub ports. It was not called: https://learn.microsoft.com/en-us/windows/win32/api/usbuser/ni-usbuser-ioctl_usb_user_request

## Bounded live procedure after transport setup

1. Re-enumerate and revalidate the C24C parent hub/port; saved device paths can change. Confirm the observer is watching the rack. Capture device and live input/video baseline from the current app before any change.
2. Open only the identified downstream hub in the test tool. First use GET_STATUS on port 1. If a manual indicator mode is already active or status cannot be read, do not change it: the prior selector cannot be reconstructed from the indicator bit alone.
3. For a port initially in automatic mode, send PORT_INDICATOR Off for at most five seconds. Have the observer identify which light, if any, changes. Restore Automatic even if the observation/test fails. Verify the request results and fresh port status.
4. Verify board presence and the same phone's input/video. Stop on any disconnect. Do not broaden to another port or all lights on the basis of command success alone.
5. Only add an app control after transport, visible effect, restoration, and continued phone operation are verified. Investigate a distributable/supported app transport separately from the diagnostic tool.

## USB setup packets for the identified hub's port 1

These are USB hub control transfers, NOT the boards' 8-byte HID reports. Never pass them to --hid-send.

| Operation | bmRequestType | bRequest | wValue | wIndex | wLength | Little-endian setup bytes |
| --- | --- | --- | --- | --- | --- | --- |
| Read port status | A3 | 00 | 0000 | 0001 | 0004 | A3 00 00 00 01 00 04 00 |
| Indicator Off | 23 | 03 | 0016 | 0301 | 0000 | 23 03 16 00 01 03 00 00 |
| Restore Automatic | 23 | 03 | 0016 | 0001 | 0000 | 23 03 16 00 01 00 00 00 |

Indicator mode definitions: https://github.com/torvalds/linux/blob/master/include/uapi/linux/usb/ch11.h

No PORT_POWER, PORT_RESET, port disable, guessed firmware command, or driver replacement is part of this test.
