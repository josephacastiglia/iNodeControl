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

Input actions run in order. A following tap, key or text send waits for a drag's
button release to finish. **Stop input** can interrupt that work; it does not
wait behind the queued actions. Resume discards cancelled work rather than
replaying it.

Board assignments are view-only on the current independent connection. Settings
shows the saved assignment, but **Bind board**, **Unbind** and **Auto-bind** are
disabled. A missing assignment needs a verified phone/board/receiver setup update
during maintenance. It is not proof of a bad cable, and the console does not try
other boards automatically. Physical identification of the remaining rack is
still required before those phones can be enabled.

The current connection also disables **Cast**, **Disc**, **Start casting**,
**Stop casting**, and **Restart board**, with an explanation beside the settings
or in the button tooltip. Start or stop mirroring on the phone itself. Board
restart is not implemented in this version; export diagnostics if control stops.

## If the app will not start

If the candidate launcher cannot start the service, its error explains the
reported refusal and points to that attempt's file under `launch-logs/`. For
example, a missing receiver plugin is listed by name. Each attempt has a separate
file; an earlier error is not reused. The dialog shows at most the last 8 KiB,
while the full error file is kept for diagnosis. `launch-error.txt` contains the
latest launch failure. These are local records; inspect them before sharing.

A readiness timeout does not stop or restart the service. The message includes
its process ID and says it may still be running. Do not repeatedly relaunch to
try to clear it. If the process exits without reporting a reason, or Windows
cannot return its exit code, the message says so. This launcher change is in the
candidate source only; the installed shortcut has not been changed.

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

The combined candidate waits for input cleanup before disconnecting, reconnecting
or finishing a normal close. Cleanup has a 15-second limit per retired connection;
independent phones release together. An unanswered release remains unconfirmed.
The console retains its own release information so explicit Resume or normal
close can finish that cleanup. It does not replay the interrupted click or key.
Repeated requests for the same release wait for its result; selecting that phone
again cannot bypass an unanswered release. A later successful Stop takes priority
over an older failed reply.
On disconnect, read the status and Activity. On a normal close, an unresolved
release or failure to save its record produces a warning before the window exits.
Inspect the affected phones before taking further control; closing a window is
not proof that a physical button was released.

The active data folder holds `last-input-cleanup.json`. If any release was
unconfirmed, `last-input-cleanup-warning.json` preserves that historical warning
even after a later clean close. These bounded records contain service addresses,
phone IDs and confirmation states, without lease tokens or raw service-error
bodies. The candidate's diagnostic export includes both records from its active
data folder automatically, including while disconnected. Each is labelled as
historical; an earlier confirmation is not proof of current control or button
state. Missing, unreadable or invalid records are identified explicitly.
Isolated candidates write only to their isolated folder. Automated window tests
copy the records into `qa` before deleting their temporary profile. Forced process
termination, a crash or OS shutdown can bypass normal awaited cleanup.

## If something stops working

| What you see | What to check |
|---|---|
| Board missing / no phone on board | The intended board and its USB/phone cables. Confirm the phone's identity before changing a binding. |
| Input paused | Read the reason, inspect the phone, then use Resume input when ready. |
| Preview may be old / not updating | Look at the physical phone before acting on the image. A still screen can also produce few bitmap updates. |
| Screenshot transfers busy | Let pending requests finish and close duplicate viewers if it persists. This is temporary image-transfer congestion; restarting a phone or its receiver is not the remedy. |
| Not mirroring | Reopen the phone's Screen Mirroring list and select its assigned receiver. |
| Receiver failed | Export diagnostics, including its restart count. Do not repeatedly restart services to erase the failure. |
| Taps land off target | Confirm the right phone and current preview, then use Reset pointer on that phone before retrying. |

Receiver discovery can be delayed after a restart. A cable replug restored it in
one recorded trial, but that is not a confirmed cause or a dependable recovery
procedure. Record a missing receiver and use the agreed recovery window.

Preferences are saved when connecting or changing the theme. If Activity says
preferences could not be saved, the choice still applies to the current session;
the previous saved file remains in place. If it instead says preferences were
saved but the launcher settings copy could not be updated, the main preferences
file succeeded and the separate launcher copy remains older. Resolve the file or
folder access problem before relying on that copy for startup. Isolated candidates
save only to their own data folder.

## Export a problem report

1. Open **Settings → Export diagnostics**.
2. Choose where to save the JSON report. Collection takes at most about five
   seconds for collection; writing the file can take longer on slow storage.
3. Read Activity for the result. A partial report is still useful: unavailable
   sections are marked, while the local console snapshot is preserved.

The candidate report includes build identities, phone/board/receiver mapping,
current console preferences, calibration and movement settings when the kernel
supports them, video delivery information, restart counts, input state, resource
use, recent activity and the active profile's saved cleanup history. It works
while disconnected, with service requests marked skipped and local history still
available. A new profile with no cleanup history is reported as missing, not as
a successful release. The report does not acquire control or send phone input.

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
