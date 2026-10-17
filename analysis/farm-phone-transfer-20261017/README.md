# C24C carousel transfer and Instagram draft — 17 October 2026

**Result: passed for one supervised test.** Three numbered test slides and the exact caption were saved in Instagram and verified after reopening. Nothing was published. The user explicitly designated the signed-in account; its handle and phone frames are retained only in the local evidence archive.

## Delivered

- `tools/farm_media_transfer.py`: short-lived, read-only media delivery of a local carousel review ZIP. Validates image checksums, dimensions, order and caption before listening. The package is held in memory, so later source edits cannot change an in-flight transfer.
- Explicit private bind address and client IP; secret URL; 1–60 minute lifetime; bounded reads; no farm API, directory browsing, uploads or publication operations. Host checks and no-referrer/no-store headers reduce unintended exposure. The temporary LAN transfer uses HTTP, not an authenticated Instagram API; IP restriction is not cryptographic phone identity.
- Phone page with numbered slides, Save to Photos instructions, exact-caption copy and clear draft-only wording. A served image is not automatically marked as saved in Photos or Instagram.
- Thirteen offline acceptance checks. The existing HTTP suite and the new transfer suite share one test-only ephemeral-loopback allowlist. Real kernel and external connections remain forbidden by the test guard.

## Live procedure and evidence

The WPF candidate stayed unchanged at build `4c1a4949`. This run used the existing release kernel's leased API, a separate transfer process, and per-step phone frames inspected by the agent. It did not control the PC or invoke the old unvalidated autonomous upload route.

Local draft ID: `eeb59816-5805-4169-aa1c-d91fe1e2c14f`, revision **5**, in the candidate's simulation draft database. The database's mode describes its isolated storage; actual phone observations are recorded separately here.

Review ZIP SHA-256: `7f910284d9c7dc26d3c443183fdda33c78bdd4553036dabc75e38d158f48b616`.

| Check | Evidence | Result |
|---|---|---|
| Correct phone and account | C24C canonical identity, free lease, live frame; profile observed and operator confirmed account | Passed |
| Transfer page reachable | `11-load-transfer`; server logged its request | Passed |
| Images saved to Photos | `27-photos` shows three distinct numbered images | Passed |
| Instagram selection order | `34`–`36` selection badges show blue 1, green 2, purple 3 | Passed |
| Caption transfer | `25-copy-caption`; `42-paste-caption` shows “Instagram pasted from Safari” and complete caption | Passed |
| Saved in Instagram | `45-draft-exit-menu`, `46-save-instagram-draft`, `47-open-drafts-library` | Passed |
| Reopened content persists | `48`–`50`: all three slide thumbnails; third image inspected; full caption retained | Passed |
| Safe ending | `54-final-drafts-library`: one test draft remains; final lease free and media server closed | Passed |

Caption, preserved exactly as visually checked (three lines):

```text
iMouse carousel draft test.
Three numbered slides in order: 1, 2, 3.
DRAFT ONLY - do not publish.
```

The camera roll contains three new JPEGs. The phone clipboard contains this caption. The draft remains in Instagram; no test image or existing media was deleted. Safari retains the now-expired transfer tab/history. No permission, FKA, account or network setting was changed.

## Observed limits

- A bottom-edge swipe did not return Home. The normal release Home command subsequently worked from a non-editing screen; it is still unsuitable inside a text field because it includes Tab.
- The first image long press selected nearby text. A 600 ms pause after pointer movement was added to the **test helper**, and the next attempt opened the correct image menu. One later long press produced no menu; the image was re-observed before another attempt. These are observations, not proof of a general timing fix.
- Instagram initially opened the Reel composer; the agent explicitly selected Post after inspecting the screen. The final editor's Next button occupies a similar location to Share on the following screen. Every action was separated by screenshot inspection; no blind coordinate sequence was enabled.
- Caption paste preserved spaces in this trial. The HID missing-space defect, Unicode/long-caption phone acceptance, other Instagram versions and unattended execution remain unvalidated.
- The transfer server's historical `savedInPhotos:false` / `savedInInstagram:false` state means it never claimed app confirmation. The independent phone evidence above supplies that confirmation; HTTP GETs alone cannot.
- Native WPF transfer launch/stop and automated screen recognition are not implemented in this pass. The export is a reusable input to the transfer CLI.

## Final rack state

Kernel PID **6108**, C24C receiver **6700**, C241 receiver **37088**, installed console **34016** remained the same processes. Neither receiver restarted. C24C was mirroring and free, generation 78. C241 remained free at generation 0 and offline as it was at preflight; it received no input. The media-only server PID 62972 exited, and port 9916 was no longer listening. No release binaries, shortcut or operator settings were written by this work.

## Verification and preservation

The standalone transfer suite initially passed 12 checks. The full suite exposed an existing process-wide test network guard that did not know the new suite's ephemeral port. After extracting a shared allowlist and adding its own guard regression, **all 119 Python tests passed** in 10.619 seconds. The intermediate failure is retained separately. The first full-suite launch was delayed by an automatic permission-review timeout; the permitted retry executed successfully. No C# change required a new native build.

Raw frames, step records, test content, final runtime records, source copies and test logs are archived under the sibling `iMouseXP-2.0-evidence-archive/20261017-farm-phone-transfer/` with SHA-256 checksums. These include private screen content and remain off Git. `phone_step.py` is an evidence helper, not an unattended product flow: C24C only, explicit observed actions, free-lease preflight, before/after captures, cleanup in `finally`, no replay on failure.

## Repeat from an exported local draft

First coordinate the phone/account, verify C24C identity and its current LAN address from its established receiver connection, and inspect the reviewed slides/caption. Do not assume today's address is permanent. With unused state-file names, run:

```text
python tools/farm_media_transfer.py --package <review.zip> --bind <PC-LAN-IPv4> --allow-client <C24C-LAN-IPv4> --minutes 20 --ready-file <ready.json> --events-file <events.jsonl> --stop-file <stop-marker>
```

Use the secret URL in the readiness file on that phone. Save images in numerical order; copy and verify the caption; confirm the Instagram account; select Post, images in order, then Save draft. Reopen from Drafts to verify before claiming success. Creating the stop-marker ends the server; expiry also closes it. Do not expose the farm control server, disable the firewall, publish, switch accounts or delete existing drafts as a shortcut.
