# Keyboard specification

Author: Grok 4.7. Sources: `src/iMouse.Kernel/HidProtocol.cs` (`Ascii`, `Key`), `src/iMouse.Kernel/InputRouter.cs` (`/key/sendkey`, `Stroke`), `src/iMouse.Kernel/InputSessions.cs` (`ExecuteAsync`), `src/iMouse.Console/MainWindow.xaml` / `MainWindow.xaml.cs` (`SendText_Click`, `MaxSendText`), `src/iMouse.Console/ApiClient.cs` (`TextChunk`, `SendTextAsync`), `src/iMouse.Console/InputLeaseClient.cs` (`SequenceAsync`).

This is the Gate 5 character-set and keyboard-settings record from [FINISH-CRITERIA.md](FINISH-CRITERIA.md). It does not sign off Gate 5. A code-0 sendkey means the HID writes finished. It does not mean iOS inserted the text.

## Supported character set

`HidProtocol.Ascii` maps one character to `(modifier, usage)` on USB HID Usage Page `0x07` (Keyboard/Keypad). The map is US QWERTY. Every code point from 32 through 126 is accepted. Nothing else is, except the five controls below.

Lowercase `a`–`z`: modifier `0`, usage `4 + (c - 'a')` (`a` = 4 … `z` = 29). Uppercase `A`–`Z`: modifier `2` (Left Shift), same usage (`A` = 4 … `Z` = 29).

| Char | Mod | Usage | Char | Mod | Usage | Char | Mod | Usage |
|---|---:|---:|---|---:|---:|---|---:|---:|
| a / A | 0 / 2 | 4 | j / J | 0 / 2 | 13 | s / S | 0 / 2 | 22 |
| b / B | 0 / 2 | 5 | k / K | 0 / 2 | 14 | t / T | 0 / 2 | 23 |
| c / C | 0 / 2 | 6 | l / L | 0 / 2 | 15 | u / U | 0 / 2 | 24 |
| d / D | 0 / 2 | 7 | m / M | 0 / 2 | 16 | v / V | 0 / 2 | 25 |
| e / E | 0 / 2 | 8 | n / N | 0 / 2 | 17 | w / W | 0 / 2 | 26 |
| f / F | 0 / 2 | 9 | o / O | 0 / 2 | 18 | x / X | 0 / 2 | 27 |
| g / G | 0 / 2 | 10 | p / P | 0 / 2 | 19 | y / Y | 0 / 2 | 28 |
| h / H | 0 / 2 | 11 | q / Q | 0 / 2 | 20 | z / Z | 0 / 2 | 29 |
| i / I | 0 / 2 | 12 | r / R | 0 / 2 | 21 | | | |

Digits are unshifted. The same usage with Left Shift is the US shifted symbol.

| Digit | Mod | Usage | Shifted | Mod | Usage |
|---|---:|---:|---|---:|---:|
| 1 | 0 | 30 | ! | 2 | 30 |
| 2 | 0 | 31 | @ | 2 | 31 |
| 3 | 0 | 32 | # | 2 | 32 |
| 4 | 0 | 33 | $ | 2 | 33 |
| 5 | 0 | 34 | % | 2 | 34 |
| 6 | 0 | 35 | ^ | 2 | 35 |
| 7 | 0 | 36 | & | 2 | 36 |
| 8 | 0 | 37 | * | 2 | 37 |
| 9 | 0 | 38 | ( | 2 | 38 |
| 0 | 0 | 39 | ) | 2 | 39 |

Plain punctuation is unshifted. Its pair is the same usage with Left Shift.

| Plain | Mod | Usage | Shifted | Mod | Usage | HID name |
|---|---:|---:|---|---:|---:|---|
| space (32) | 0 | 44 | | | | Spacebar |
| - | 0 | 45 | _ | 2 | 45 | - and _ |
| = | 0 | 46 | + | 2 | 46 | = and + |
| [ | 0 | 47 | { | 2 | 47 | [ and { |
| ] | 0 | 48 | } | 2 | 48 | ] and } |
| \ | 0 | 49 | pipe | 2 | 49 | backslash and pipe |
| ; | 0 | 51 | : | 2 | 51 | ; and : |
| ' | 0 | 52 | " | 2 | 52 | ' and " |
| ` | 0 | 53 | ~ | 2 | 53 | Grave and tilde |
| , | 0 | 54 | < | 2 | 54 | , and < |
| . | 0 | 55 | > | 2 | 55 | . and > |
| / | 0 | 56 | ? | 2 | 56 | / and ? |

Usage 50 (Non-US `#`) is not used.

### Whitespace and control

These are accepted by `Ascii` on the API `key` string. The console text box rejects every code below 32, so the UI sends them only as `fn_key` (Space is the exception: it is ASCII 32 and goes in `key`).

| Input | Code | Mod | Usage | HID name |
|---|---:|---:|---:|---|
| Space | 32 | 0 | 44 | Spacebar |
| Enter `\r` or `\n` | 13 or 10 | 0 | 40 | Return (Enter) |
| Escape `\u001b` | 27 | 0 | 41 | Escape |
| Backspace `\b` | 8 | 0 | 42 | Delete (Backspace) |
| Tab `\t` | 9 | 0 | 43 | Tab |

`\r` and `\n` are the same report.

### Rejection

Anything `Ascii` does not list throws `ArgumentException` with `Unsupported character U+XXXX` (four hex digits). The API returns that as code 36. Unicode, emoji, and DEL (127) are rejected. There is no truncation and no IME path in this kernel. Unicode needs the original console's shortcut / clipboard tools, which this kernel does not implement.

The console blocks before the API when any character is `< 32` or `> 126`, and logs: `Keyboard typing supports English letters, numbers and punctuation. Use the original console's shortcut tools for Unicode text.` An empty box logs `Enter text to send first.` and sends nothing. Text over the temporary 200-character cap logs `Send text takes at most 200 characters at a time; this is N. Nothing was sent.` and sends nothing. The box has no `MaxLength`, because WPF would truncate pasted text to it silently and the shortened text would then send. Instead a counter under the box reads `N / 200` and turns red with `too long to send` above the cap.

## USB-HID report

`Key(modifier, usage)` is eight data bytes:

```text
A2  modifier  usage  00  00  00  00  00
```

`HidConnection` requires those eight bytes and prefixes HID report ID `0` on the wire (nine bytes). Bytes 3–6 are zero on every verified character stroke. Byte 7 is zero on character strokes. It is `02` only in the ControlBar / AppSwitch chord below.

Modifier byte (USB HID keyboard modifier bits):

| Value | Bit | Name | Emitted by verified paths |
|---:|---:|---|---|
| 0 | | None | lowercase, digits, plain punctuation, Enter, Backspace, Tab, Escape |
| 1 | 0 | Left Ctrl | not set. ControlBar / AppSwitch do not use this bit |
| 2 | 1 | Left Shift | `A`–`Z` and shifted symbols |
| 8 | 3 | Left GUI (Command) | Home's `H` |

Left Alt (4) and the right-side modifier bits are not emitted.

### Usage Page 0x07 codes this kernel emits

| Usage | Name | Produced by |
|---:|---|---|
| 4–29 | a/A … z/Z | letters |
| 6 | c and C | ControlBar chord (not the letter `c` path when byte 7 is `02`) |
| 11 | h and H | Home, with modifier 8 |
| 30–39 | 1/! … 0/) | digits and `!@#$%^&*()` |
| 40 | Return (Enter) | Enter, `\r`, `\n` |
| 41 | Escape | Escape, `\u001b` |
| 42 | Delete (Backspace) | Backspace, `\b` |
| 43 | Tab | Tab, `\t`, and the prefix of Home / ControlBar / AppSwitch |
| 44 | Spacebar | space. Hold is 90 ms, not 60 |
| 45–49, 51–56 | punctuation pairs in the table above | plain and shifted symbols |
| 82 (`0x52`) | Up Arrow | AppSwitch chord |

## Function keys

`POST /key/sendkey` with `fn_key` set. Any other name throws `ArgumentException`: `Function key has not been verified`. If `fn_key` is set, the `key` string is validated and then not typed.

| `fn_key` | Aliases | What is sent | Pointer |
|---|---|---|---|
| Home | | Stroke Tab (usage 43), then Stroke Left GUI+H (modifier 8, usage 11). Reports `A2 00 2B 00 00 00 00 00` and `A2 08 0B 00 00 00 00 00` | `Known = false` |
| ControlBar | | Opens Control Center. Not Left Ctrl + M (that would be modifier 1, usage 16). Stroke Tab, then vendor chord: `A2 00 00 00 00 00 00 02` for 45 ms, `A2 00 06 00 00 00 00 02` for 60 ms, then keyboard release. Usage 6 with byte 7 = `02` | `Known = false` |
| AppSwitch | | Opens the App Switcher. Same Tab and byte-7 prefix as ControlBar. Second report is `A2 00 52 00 00 00 00 02` (Up Arrow, usage 82) for 60 ms, then release | `Known = false` |
| Enter | `ENTER` | Stroke usage 40, modifier 0 | unchanged |
| Backspace | `BACKSPACE` | Stroke usage 42, modifier 0 | unchanged |
| Tab | | Stroke usage 43, modifier 0 | unchanged |
| Escape | | Stroke usage 41, modifier 0 | unchanged |

Console buttons that send unverified names (`WIN+v` Paste, `TAB+b`, `TAB+l`, `OPENKeyboard`, `SwitchIme`) hit the rejection above. They must not be treated as success.

## Timing and limits

Each `Stroke` (every character, and Enter / Backspace / Tab / Escape / the Tab and GUI+H of Home):

1. Clear: `A2 00 00 00 00 00 00 00`, then 45 ms.
2. Down: `A2 modifier usage 00 00 00 00 00`, held 60 ms, or 90 ms when usage is 44 (Space).
3. Release in `finally`: the same clear report.
4. Settle 35 ms.

Delays are `Task.Delay` on the command token. They are scheduled intervals, not a measured HID clock. A cancelled stroke still sends the release. Failure also releases mouse and keyboard and drops the handle.

The ControlBar / AppSwitch chord is not a `Stroke`: 45 ms on the byte-7 prefix, 60 ms on the usage report, release, no 35 ms settle.

### The 8-second command deadline

`InputSessions.ExecuteAsync` cancels every input command 8 s after it starts (`deadline.CancelAfter(TimeSpan.FromSeconds(8))`). The cancelled stroke still sends its release. The phone's result is code 499 (`Input cancelled`) inside a code-33 answer. Any non-zero result calls `BeginClose(slot, true, …)`: the lease is revoked and the phone stays stopped until an explicit Resume. The console's `HttpClient.Timeout` (`ApiClient`) is also 8 s.

At 140 ms a character (170 ms for a space), plus HID write time, one `key` string longer than roughly 50 characters (about 47 if every character is a space) cannot finish in 8 s. It is cut off partway: the start is typed, the rest is not, and input is stopped. `rack-agent/test/conformance.test.mjs` reproduces this with one 64-character sendkey against the kernel source with a fake HID ("one 64-character sendkey exceeds the 8 s command deadline").

### Text chunking

Send text never puts more than 32 characters (`ApiClient.TextChunk`) in one `/key/sendkey`. That is at most 5.44 s of stroke timing (32 spaces) and 4.48 s with no spaces, which leaves at least 2.5 s of the deadline for HID writes and the round trip. The rack agent uses the same size (`rack-agent/src/actions.js`, `TEXT_CHUNK`).

`ApiClient.SendTextAsync` splits the text into consecutive 32-character chunks (the last may be shorter) and sends them through `InputLeaseClient.SequenceAsync`:

- **One lease.** Every chunk carries the same token map. The console holds the phones' input gates for the whole text, so no other input from this console lands between chunks. Other input waits, and Stop input cancels it. The lease is renewed in the background as usual (every 10 s, 30 s lease).
- **Strictly sequential.** A chunk leaves only after the kernel answered code 0 for the one before it.
- **Stop at the first problem, never retry.** The first chunk that fails, times out, or is cut short by Stop ends the text. That chunk is never resent, because its outcome is unknown and it may be partly typed. No later chunk is sent. A failure or timeout pauses input like any failed command (the kernel also stops the phone on its own failures), so Resume is required before more input. Either one raises the lease client's pause notice, so the panel reads Input paused and Resume is enabled. For a timeout the notice reads `Input paused: request timed out; the outcome is unknown. Check the phone, then choose Resume input.` Single taps, keys and drags behave the same way. A Stop raises no notice.
- **Report how far it got.** The activity log gives confirmed characters out of the total, then which chunk may be partly typed and which chunks were not sent. For example: `Send text failed: 64 of 200 characters confirmed. Chunk 3 of 7 may be partly typed and was not retried. Chunks 4–7 were not sent.` Confirmed means the kernel answered code 0 for that chunk. As above, that means the HID writes finished, not that iOS inserted the text. When the send ends before a chunk leaves (for example, Stop before the first chunk), no chunk is reported as partly typed.
- **Stopped, timed out and failed are reported separately.** The lease client decides which by checking whether one of its own cancellation sources fired (Stop, a selection change, disconnect, the caller). It does not go by the exception type. A cancellation that none of them requested is the HTTP timeout.
- **Stop input takes the first click while a drawer is open.** Send text lives in the Controls drawer. The drawer's dimming overlay used to cover the top bar too, so on the rack the first click on Stop input only closed the drawer and the 200-character send ran to completion. The drawer now starts below the top bar. Live on C24C, a single Stop click during chunk 3 left `64 of 200 characters confirmed. Chunk 3 of 7 may be partly typed and was not retried. Chunks 4–7 were not sent.`, matching the phone: 64 characters plus 12 of chunk 3, and nothing afterwards.
- **Timeout recovery covers every input path.** Text chunks, taps, keys and drags all raise the pause notice above and wait for Resume input. Input queued behind a failed command is not sent and is logged as `Not sent: …`. A drag that fails or times out while its button may be down is released at once with `/input/release` and the console's own token. The panel then says whether the kernel confirmed the release. See `analysis/input-timeout-candidate-20260925/`.

The chunking is in the console, not the kernel. Another API client that sends a long `key` in one command still hits the deadline.

**The 200-character cap is temporary.** Chunking does not require it: every chunk fits the deadline whatever the text length. The cap bounds how long one send holds the phones and blocks other input from this console. 200 characters is seven chunks, about 28 s of typing with no spaces and up to about 34 s with many spaces, plus round trips. Revisit it once Stop and recovery during long sends have more rack time.

Limits:

| Bound | Value | Where |
|---|---|---|
| Kernel command deadline | 8 s per command; then code 499, lease revoked, Stop latched until Resume | `InputSessions.ExecuteAsync` |
| Console request timeout | 8 s per HTTP request | `ApiClient` (`HttpClient.Timeout`) |
| Kernel `key` length | 1–1000 characters | `InputRouter`. Longer, or empty `key` with empty `fn_key`: `Provide a key or 1–1000 ASCII characters.` Anything over roughly 50 characters in one command can outlast the deadline |
| Console chunk | 32 characters per `/key/sendkey` | `ApiClient.TextChunk` |
| Send text cap (temporary) | 200 characters (seven chunks) | `MainWindow.MaxSendText`, checked in `SendText_Click`. Longer text stays whole in the box, the counter turns red, and nothing is sent. There is no `MaxLength` on the box, so nothing is truncated |
| UI alphabet | codes 32–126 only | `SendText_Click`. `AcceptsReturn` is false |

## Required iOS settings

The phone sees a hardware keyboard. Settings the API cannot read still decide whether a usage becomes the expected glyph.

**Hardware keyboard layout: English (US).** The tables above are US QWERTY (`Shift+2` = `@`, `Shift+3` = `#`, `Shift+6` = `^`). Another hardware layout changes the glyph for the same usage. This layout was not captured as a Settings screenshot in the cited runs. Exact-text checks require it.

**Full Keyboard Access.** Vendor setup turns it on (Accessibility → Keyboards → Full Keyboard Access, auto-hide 1 s). While it is on, character keys are accessibility commands until Typing Mode. A UIKit insertion cursor is not Typing Mode. Space with the blue ring on AssistiveTouch opens that menu instead of inserting a space.

- C24C (no FKA ring in the Gate 5 Control Center shot) inserted `iMouse2026` into Spotlight directly.
- C241 (FKA on) did not insert `iMouse2026` into an empty Spotlight field. API code was 0. Later, `hello2026` inserted after the field already held selected text, and after a Typing Mode entry (Tab until the blue ring is on the field, then Space).
- To type with FKA on, the text field must be focused and Typing Mode must be on. The on-screen exit hint is Control+Tab. This kernel has no verified Control+Tab `fn_key`. Escape cleared the Typing Mode banner once.
- Turning FKA off matches the C24C direct-typing path. Toggling it off and back on left it on. AirPlay reconnect does not change that.

**Smart Punctuation.** iOS can rewrite ASCII `'` and `"` (usages 52) into curly quotes after delivery, and can rewrite `--` or `...`. Exact expected text requires Smart Punctuation off. The cited alphanumeric captures did not contain quotes, so they do not prove it was off.

**Auto-Capitalization and autocorrect.** The kernel sends Shift itself for `A`–`Z`. Auto-Capitalization can still capitalize an unshifted first letter. Autocorrect can replace a word. Exact expected text requires both off, or a field that does not apply them. Spotlight kept the sent case in `iMouse2026` and `hello2026`. That does not prove Notes will.

Spotlight consumes spaces. Usage 44 is still a space in Notes (`A B Test 123!` on C24C). Do not score spaces in Spotlight.

**Open issue: the first space typed into a note goes missing (cause unresolved).** The controlled comparison is in [analysis/text-chunking-candidate-20260925/REPORT.md](analysis/text-chunking-candidate-20260925/REPORT.md).

*Findings* (C24C, Notes, 25 Sep 2026; sends through the console's `SendTextAsync` and the Send text button):

- 21 of 21 sends containing the first space typed into a note lost that space. In 7 later sends into such notes no space was lost. Examples: `Chunk check` became `Chunkcheck`, `Hi there` became `Hithere`, `A B C` became `AB C`.
- The kernel answered code 0 for every chunk.
- The loss did not depend on:
  - multi-chunk sending: one 11-character chunk lost it too;
  - where the space fell in the text: position 3, 6, 7 or 11;
  - first line versus body;
  - one lease versus a fresh lease per send;
  - whether the send began with Enter.
- Once a note had lost its first space, later sends into it arrived exactly, including after a 3 s pause. Every exact result in these runs was typed into such a note.

*Hypotheses:*

- iOS Inline Predictions. An "Inline Predictions — Press space to input predictive text" tip and grey predicted text appeared on screen during these runs, and one Enter accepted a pending prediction and inserted `he` that was never sent. **Tested with no change seen.** With authorization, Settings → General → Keyboard → Show Predictions Inline (originally ON) was turned OFF and then restored to ON. `Hi there` sent with the Send text button became `Hithere` in all nine fresh-note trials, three in each state. This does not definitively rule the setting out: no inline prediction was visible in either state, and Notes was not relaunched after the change.
- Full Keyboard Access (above). Untested. Testing it means changing that setting, which has not been authorized.

The kernel keeps no per-note state and sends the same reports for every space. That points at the phone, but it is not proven. The cause remains unresolved.

The older `A B Test 123!` capture kept its first space and is unexplained.

Also observed: iOS applied a pending autocorrection (`Hithere` → `Hi there`) when the note was left, so read typed text before navigating away.

## Evidence

| Run | What was visible | Files |
|---|---|---|
| C24C Gate 5, 21 Sep 2026 | Spotlight text exactly `iMouse2026`, then four Backspaces left `iMouse`. No stuck Shift. Isolation held | [analysis/gate5-everyday-controls-20260916/](analysis/gate5-everyday-controls-20260916/) `c24c-typed.png`, `c24c-backspace.png` |
| C241 Gate 5, same run | Spotlight stayed on placeholder `Search`. Code 0. Not a character-set failure | same folder, `c241-typed.png` |
| C241 clean typing, 22 Sep 2026 | Spotlight exactly `hello2026`, then four Backspaces left `hello` | [analysis/c241-clean-typing/](analysis/c241-clean-typing/) `c241-02-typed.png`, `c241-03-backspaced.png` |
| C24C Notes (older kernel) | Spaces, digits, and `!` visible as `A B Test 123!` | [INDEPENDENT-KERNEL.md](INDEPENDENT-KERNEL.md), `analysis/live-notes-space.bmp` |
| FKA diagnosis | Typing Mode required on C241; Escape cleared the banner | [analysis/c241-typing-diagnostic/findings.json](analysis/c241-typing-diagnostic/findings.json) |
| C24C text chunking, 25 Sep 2026 | `ApiClient.SendTextAsync` against the two-phone kernel. 100 characters in 4 chunks, about 15.4 s each run, every chunk confirmed, no Stop, lease released. Second-paragraph run exactly `Chunk check 2026 on C24C types 100 characters in four chunks of 32 with one lease (no Stop) #78 & OK`. Both new-note first-line runs arrived without the first space (open issue above). These runs used a test harness, not the Send text button |
| Text-chunking candidate, 25 Sep 2026 | 17 controlled sends on C24C, plus the candidate console's real Send text, Stop input, Resume input and Disconnect. Exact 100 characters through the button only in a note that had already lost its first space. Stop, recovery and release worked | [analysis/text-chunking-candidate-20260925/REPORT.md](analysis/text-chunking-candidate-20260925/REPORT.md), `trials/`, `ui/` | [analysis/c24c-text-chunking-20260925/](analysis/c24c-text-chunking-20260925/) `c24c-01-new-note.png`, `c24c-02-new-note-repeat.png`, `c24c-03-second-paragraph.png` |

Those captures do not include a live Enter newline, a live punctuation string on both phones, or a recorded Settings screenshot of English (US) / Smart Punctuation / Auto-Capitalization. Those remain open Gate 5 checks. This file only closes the documentation requirement.
