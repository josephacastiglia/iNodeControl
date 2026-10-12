# Receiver logging: bounded retention and recoverable file failures

12 October 2026. Offline candidate work; no receiver, rack connection or screen control.

## Change

The receiver's stdout/stderr callback previously called `File.AppendAllText` directly. Logs had no retention bound, and an ordinary file error could escape a background callback. The candidate now uses a serialized `ReceiverLog` writer:

- Current log plus one `.1` generation, at most 4 MiB each for new output. Lines are bounded before UTF-8 encoding; unusually long lines are marked truncated.
- A pre-existing oversized log is preserved for one generation, until the next rotation. This avoids silently truncating historical evidence on the first candidate start. It means the initial retained total can exceed 8 MiB.
- File/permission errors do not escape the callback. Per-phone `receiver_message` exposes the logging warning while the receiver remains running. A later successful line clears it. Missing output is not represented as successfully logged.
- Failed rotation leaves the active file intact and does not append beyond its budget. Concurrent stdout/stderr writes are serialized. No unbounded queue is introduced.

Phone input, pacing, receiver arguments and restart policy are unchanged. The installed kernel/receiver are untouched. Log rotation is a candidate behavior change and must be included in later live acceptance; tools that follow file offsets must account for rotation. Keep raw evidence archives separately rather than using a rotating runtime log as permanent evidence.

## Validation

| Check | Result |
|---|---|
| Recovery/logging suite | 20/20 pass, including eight new cases |
| Kernel self-tests | 111 pass, including warning propagation into per-phone status |
| Release kernel build | Zero warnings/errors |

The focused suite uses fake process handles and disposable files. It covers Unicode truncation, simultaneous callbacks, size/retention bounds, failed writes and recovery, rotation failure and recovery, EOF and one oversized historical generation. The kernel suite uses fake HID and private synthetic frame pipes. No live receiver was started.

The Windows sandbox refused file renames in the disposable log folder, so three rotation cases initially failed with access denied (17/20). Those logs are retained. The same built suite passed 20/20 under approved unrestricted execution. The kernel suite likewise used approved execution for private pipes. Neither exception authorized real phone access.

## Scope

This fixes known file-handling behavior. It does not establish full-disk host recovery, process cleanup on real hardware, iOS recasting, or endurance acceptance. Runtime prerequisites and physical gates remain open. The earlier combined package stays immutable; a newer review package and source/build manifest record this kernel separately.
