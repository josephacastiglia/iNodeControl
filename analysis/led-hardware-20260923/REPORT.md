# Rack LED feasibility — live read-only inspection, 23 September 2026

## Result

There is a concrete lead for hub indicators, but no verified way yet to switch all photographed lights off from iMouse while preserving phone operation. Do not ship an enabled Rack lights toggle based on this inspection alone.

## Live evidence

- PnP enumeration found 19 USB control boards with VID 720A, each Started. C24C and C241 are present. This confirms USB enumeration, not phone attachment or live mirroring.
- Four VID 1A40 / PID 0201 hubs are present: one upstream hub and three downstream hubs serving the boards.
- Read-only IOCTL_USB_GET_NODE_INFORMATION succeeded for all four. Each reports seven ports and wHubCharacteristics = 0x0088. Bit 0x0080 advertises port-indicator support.
- All 19 boards opened for HID capability queries. Each reports vendor usage page FF00, usage 0000, 17-byte input, 9-byte output, no feature report, one vendor-defined output field. These capabilities do not describe a lighting command. Absence of feature reports does not exclude an undocumented LED command in the output protocol.
- The raw HID report-descriptor IOCTL returned error 1; report sizes and usage data came from Windows HID preparsed capabilities.
- Prior review of the decoded protocol, vendor translations, and saved vendor API documentation found no board-LED On/Off command. Phone brightness is a separate function.

## What this does and does not establish

The hub descriptor is positive evidence of advertised hub-indicator support. It does not identify the wiring between hub indicator pins and the photographed front-panel LEDs. It does not establish control of the red/blue/green LEDs on each phone board, the power-supply light, or every other rack light. An advertised capability must still be tested on a known indicator before UI implementation.

The normal Windows/libusb path is another unresolved part: libusb's Windows documentation says hub control used by uhubctl is not supported by its Windows backends. Reading hub descriptors successfully does not establish permission or an API to issue hub class SET_FEATURE requests. No driver replacement or filter installation was attempted.

## Next engineering gate

1. Establish a supported Windows transport for port-indicator requests that preserves the existing hub driver and connections, or obtain the manufacturer's LED-control API.
2. If such a transport is available, target one positively identified hub port. Observe which physical LED changes; test Off and restoration to automatic operation. Record board presence, phone input, and video before/after. Do not substitute PORT_POWER or port disable for LED control.
3. Only expose controls for the lights actually verified. A hub-only control must not claim to turn off the phone-board LEDs.
4. Board LEDs require their own documented/observed firmware command or circuit evidence. Do not guess undocumented output packets across the rack.

## Artifacts

- rack-pnp.txt: rack-filtered connected-device inventory and parent/child relationships.
- hid-caps.txt: current board HID capability results.
- hub-indicators.json: raw hub descriptors and parsed indicator flag.
- Read-HubIndicators.ps1: reproducible read-only hub query; restricts opening to VID 1A40/PID 0201; sends only GET_NODE_INFORMATION.

No hardware output reports, LED-setting requests, port power changes, port resets, service restarts, driver changes, or app changes were made. The existing kernel executable was invoked only with --hid-caps and a separate diagnostic data directory; it exited before input/receiver/server startup.

## References

- Microsoft USB hub descriptor: https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/usbspec/ns-usbspec-_usb_hub_descriptor
- Microsoft USBView read-only enumeration: https://github.com/microsoft/Windows-driver-samples/blob/main/usb/usbview/enum.c
- Linux USB hub definitions: HUB_CHAR_PORTIND = 0x0080; HUB_LED_OFF = 3, distinct from power control: https://github.com/torvalds/linux/blob/master/include/uapi/linux/usb/ch11.h
- libusb Windows hub limitations: https://github.com/libusb/libusb/wiki/Windows
