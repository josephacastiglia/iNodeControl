# Receiver selection follow-up

14 October 2026, during the coordinated navigation test window.

The operator reports that the original vendor app has a button that opens the
phone's Screen Mirroring menu using gestures and selects a receiver. This has
not been reproduced or validated in our implementation. The retained C24C frame
shows Bedroom TV above iMouse2-C24C, with iMouse2-C24C selected.

Our API currently returns code 41 for /device/airplay/connect and
/device/airplay/disconnect (src/iMouse.Kernel/ApiServer.cs). This means this
implementation does not perform selection; it does not establish that phone UI
automation is impossible. A future reconnect workflow must positively identify
the intended receiver and its phone, rather than select the first row. It must
keep lease/Stop safeguards and distinguish sending gestures from verified video.
Recovery without a live phone image will need its own supported observation and
selection method. No reconnect automation is implemented or tested in this window.

Current window: no phone input sent as of the read-only retained-frame check.
The operator has been asked to dismiss Screen Mirroring and return to the FKA
page unchanged. The stale-frame preflight remains enforced pending that check.

## Existing helper found during offline inspection

`tools/force_recast.py` already implements a leased ControlBar/click sequence.
It selects fixed coordinates rather than reading receiver names: C24C is assigned
(250, 472). In today's captured 500x1080 chooser this is the Bedroom TV row,
while iMouse2-C24C occupies the next row. The helper also sends Home repeatedly
and may reselect automatically after a disconnect. It was not run or changed.
Thus the earlier broad claim that recasting must always be manual was too
strong. The repository contains an automation attempt, but it does not satisfy
the user's explicit receiver-selection requirement in the current layout.
Next work should reuse its lease transport only after adding a verified target
selection method and removing blind retries; receiver discovery and UI selection
are different problems. This does not expand today's authorized live window.
