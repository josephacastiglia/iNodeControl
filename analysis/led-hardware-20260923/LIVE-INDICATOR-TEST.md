# LED test concluded — 23 September 2026

The user requested restoration and conclusion. No further tests are pending.

After the user's reboot, the Bus Hound driver was running. Fresh mapping and Bus Hound's device properties confirmed C24C on port 1 of hub USB\VID_1A40&PID_0201\9&fe3f543&2&4 (Bus Hound device 49, child 110 showing VID_720A/PID_C24C).

## Results

| Request | USB setup bytes | Result |
| --- | --- | --- |
| Initial port status | A3 00 00 00 01 00 04 00 | complete; 03 01 00 00 |
| Indicator Off, port 1 only | 23 03 16 00 01 03 00 00 | complete |
| Restore Automatic, port 1 only | 23 03 16 00 01 00 00 00 | complete |
| Final port status | A3 00 00 00 01 00 04 00 | complete; 03 01 00 00 |

The user watched the rack and reported **no visible change**. Command completion does not prove control of any visible light. No working lights button was added.

The final status matches the original: connected, enabled, powered, indicator manual-mode bit clear, no port change bits. All 19 control boards reported PnP Status OK after the test. Before/after enumeration does not exclude a transient interruption. Independent iMouse/UxPlay were not running after reboot; live phone input/video during Off was not validated.

The measured interval between initiating Off and completion of the Automatic UI action was 14,423 ms, longer than the prepared five-second target. Separate UI actions incurred this delay. Automatic restoration succeeded. No PORT_POWER, reset, disable, hot-plug simulation or proprietary HID command was sent.

At the user's request, command-editor fields were also restored to their original defaults: type 80, request 06, value 0301, index 0409, length 0040. These editor defaults were **not executed**. They are request fields, not persistent hardware configuration.

Hardware support for the photographed LEDs remains unverified. Further work would require manufacturer documentation or schematic evidence identifying how those LEDs are controlled. Do not infer support from the hub descriptor or command success alone.
