# Open iMouse 2.0

Use the desktop shortcut **iMouse 2.0 - Independent AirPlay**.

For the product goal, acceptance checklist, and release sign-off, see
[Completion criteria](FINISH-CRITERIA.md).

This is our Windows iPhone-control app, with our own AirPlay receivers. Keep using
this one shortcut as we update the app; internal build-folder names are for development.

To recognize it once open:

- Settings shows `http://127.0.0.1:9913`.
- The footer shows `Cast iMouse2-C24C / iMouse2-C241`.
- On each iPhone, choose its matching `iMouse2-C24C` or `iMouse2-C241` receiver.

The window currently still says **iMouse 2.0 — iPhone Console**; old builds use
that same title, so the shortcut and receiver names are the reliable identifiers.
**iMouseXP International Edition Console** is the original vendor application.

The shortcut opens `Open iMouse 2.0.ps1` in this folder. It checks the saved
connection, starts our service if needed, and opens the exact current console.
It reuses an already-running two-phone service and does not stop vendor services
or send phone input. If this console is already open, use its taskbar window.

There are seven historical console builds under `release/`; they are retained.
The former `iMOUSE 2.exe - Shortcut` pointed to the old `release/iMouse2/iMouse2.exe`.
Its original shortcut is backed up in `analysis/app-identification/`.

For development: the current console path is
`release/iMouse2-two-phone-candidate/iMouse2.exe`. Update the single launcher
when changing the active build; keep the desktop shortcut name unchanged.
