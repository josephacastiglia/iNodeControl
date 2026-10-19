# First-space comparison — 10–11 October 2026

**Completed: the extra field click did not preserve the first space.** All six fresh Notes trials on C24C visibly produced `Hithere` after submitting `Hi there`. The cause remains unresolved, and Gate 5 exact typing remains open.

| Condition | Trials | Exact text | First space lost |
|---|---|---|---|
| A: no extra field click | A1, A2, A3 | 0/3 | 3/3 |
| B: one field click at (250, 520) | B1, B2, B3 | 0/3 | 3/3 |

## Method and limits

- Order: A1, B1, B2, A2, A3, B3. The operator performed physical Home before each fresh note.
- Full Keyboard Access was visually verified On before testing and left unchanged.
- Original unpromoted candidate `b0708e3`, using its actual Send text button, an isolated data directory, hover tracking Off, group targeting Off and an unarmed logging proxy. Candidate DLL SHA-256: `E5A51FC6204566FA3B48C650FC239A42B158217D8045D2712850173980303AC3`.
- Existing lease-aware phone-preparation runner reused. An adapter replaced PowerShell UI Automation with supported Computer Use. No direct key API send or automatic retry was used.
- Each trial submitted eight characters in one chunk; all six kernel responses returned code 0. Phone frames, captured before navigation, showed seven characters. Command completion therefore did not establish exact insertion.
- Visual checkpoints made the preparation-to-send wait longer than planned. Recorded release-to-click-invocation delays were 163,371 / 171,445 / 168,447 / 165,302 / 178,713 / 175,258 ms. These are not exactly matched delays or HID latency measurements.
- Each B click opened Paste / AutoFill / Add Link. That menu was left present before typing. Results apply to this focus procedure, not every possible field-focus method.
- A3 logged an extra "Still typing the previous text" warning despite one requested Computer Use Send text click. Its proxy record contains exactly one text command. The source of the warning was not investigated here.
- One phone, one app and one short string. No new FKA-Off comparison or full character-set acceptance was performed.

## Evidence and restoration

Local evidence: `C:\Users\joey_\Desktop\Claude Code\iMouseXP-2.0-evidence-archive\20261010-typing-mode-ab\`. It contains the full report, prepared source snapshot, adapter, exact binaries, phone frames, raw console/proxy records and restoration checks. `SHA256SUMS.txt` records file hashes. Preserve this folder; it is outside the Git repository.

The candidate closed normally and released C24C; all six runners exited 0 and the proxy stopped. The installed console was restored from `release/iMouse2-two-phone-candidate` as PID 29160. Final read-only checks found both phones unowned, inactive and not stopped. C24C was generation 14 and mirroring; C241 remained generation 0, with its receiver running but its video already offline before these trials.

Kernel PID 43928 and receiver PIDs 2360 / 18176 stayed unchanged, with zero receiver restarts. Release hashes and operator settings content matched the initial record. No phone setting was changed. Six new test notes remain, with the final note open; none was deleted. No product change, merge, promotion, deployment or push occurred.

## Next work

Review the first-space HID reports and FKA focus/key routing offline before proposing another bounded live diagnostic. Keep the missing-space mechanism unresolved. Do not repeat this six-note comparison as pending work, or add compensating spaces as a fix.
