# Using iMouse 2.0

This guide describes the combined candidate. It has not replaced the installed app;
final phone and release acceptance is still open. Keep using your existing shortcut
until a candidate has been approved for installation.

## Start and identify a phone

1. Open **iMouse 2.0 - Independent AirPlay** using the existing desktop shortcut.
2. On each phone, open Control Center → Screen Mirroring and select its assigned
   receiver, such as **iMouse2-C24C**. Match the phone label to the receiver name.
3. Select the intended phone in the console. Check both its control status and
   video status before entering input. A live picture does not prove its control
   board is connected; a connected board does not prove its picture is current.
4. For work on one phone, clear the other phone checkboxes. **Mirror to all** and
   checked followers can send the selected phone's actions to multiple phones.

**Move phone pointer with mouse** can take control and move the phone pointer when
you hover over the preview. Turn it off in Controls when you only want to observe.

## Control and stop

Use the phone preview to click, drag or hold. Controls also contains **Send text**
and **Reset pointer**. Select an editable field on the phone before sending text.
The current text limit is 200 characters; an over-limit paste is refused without
silently shortening it. Check the text on the phone after sending.

Press **Stop input** to interrupt this console's input. After a failure or timeout,
inspect the phone before choosing **Resume input**. A timeout means the action's
result may be unknown; it may already have happened. Resume does not replay it.
If the panel says a held-button release was not confirmed, treat that as unresolved
and preserve a diagnostic report.

Only one controller can own a phone's input at a time. Before another session
uses it, finish the current work and use **Settings → Disconnect**, or close the
console normally. Disconnect affects this console's phones; it does not stop the
separate kernel or mirroring receivers.

## If something stops working

| What you see | What to check |
|---|---|
| Board missing / no phone on board | The intended board and its USB/phone cables. Confirm the phone's identity before changing a binding. |
| Input paused | Read the reason, inspect the phone, then use Resume input when ready. |
| Preview may be old / not updating | Look at the physical phone before acting on the image. A still screen can also produce few bitmap updates. |
| Not mirroring | Reopen the phone's Screen Mirroring list and select its assigned receiver. |
| Receiver failed | Export diagnostics, including its restart count. Do not repeatedly restart services to erase the failure. |
| Taps land off target | Confirm the right phone and current preview, then use Reset pointer on that phone before retrying. |

Receiver discovery can be delayed after a restart. A cable replug restored it in
one recorded trial, but that is not a confirmed cause or a dependable recovery
procedure. Record a missing receiver and use the agreed recovery window.

## Export a problem report

1. Open **Settings → Export diagnostics**.
2. Choose where to save the JSON report. Collection takes at most about five
   seconds for service requests; writing the file can take longer on slow storage.
3. Read Activity for the result. A partial report is still useful: unavailable
   sections are marked, while the local console snapshot is preserved.

The candidate report includes build identities, phone/board/receiver mapping,
current console preferences, calibration and movement settings when the kernel
supports them, video delivery information, restart counts, input state, resource
use and recent activity. It works while disconnected, with service sections
marked unavailable. It does not acquire control or send phone input.

Review it before sharing: phone identifiers, names, the service address and recent
activity are included. Screen images and the Send text box contents are not
collected. Older kernels omit fields they cannot report; missing values are not
proof of good health. Timing values do not measure physical iPhone display latency.

## Current limits

- The first space can disappear in fresh text fields with Full Keyboard Access
  On. That investigation is deferred; exact typing is not universally validated.
- The current Home sequence can insert a Tab into an active text field. Use the
  phone's physical Home gesture when the text must stay unchanged.
- App Switcher has failed in the tested Full Keyboard Access Off condition.
- Full-rack accuracy, recovery and endurance acceptance remains incomplete.

## Updates and returning to the working version

An update needs an agreed window and a verified copy of the working app and its
configuration. Keep the old shortcut and files until the new version passes its
checks. Returning to the working version means closing the candidate normally,
restoring any changed files from that verified copy, and using the original
shortcut again. Mirroring may need to be selected again on the phones.

The developer's exact checks are in [RELEASE-STAGING.md](RELEASE-STAGING.md).
Nothing in this guide authorizes an automatic update or service restart.
