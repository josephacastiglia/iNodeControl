# Permission prompts without constant human help

Operator request (20 Oct): *"We need to develop solutions for permission prompts so
humans don't have to constantly step in."* This record covers what is built
offline, what the evidence says about input, and the validation window that would
let the farm answer prompts itself. It used no phone input, service, desktop
control, publishing or messaging.

## 1. Evidence

- **One retained prompt.** The only system permission prompt in the retained
  C24C frames is YouTube's local-network prompt: *Allow "YouTube" to find devices
  on local networks?* with **Don't Allow / Allow** (17 Oct steps 132–135).
- **The pointer was ignored.** The iMouse pointer **hovered** *Don't Allow* (the
  button highlighted), but the **click was ignored** (step 133). **Escape was
  ignored** too (step 135). The operator then tapped *Don't Allow* physically
  (step 136).
- **Interpretation.** iOS privacy alerts accept the pointer's hover but not its
  clicks, and not the keyboard either. A pointer- or keyboard-only farm cannot
  assume it can answer them.
- **Private OCR.** The YouTube frames (steps 46–66 and 131–151) were re-read with
  the production OCR into a private archive outside Git
  (`iMouseXP-2.0-evidence-archive/20261020-farm-youtube-offline`, 117 files,
  manifest `f763e5a860f66b7d4b67c50f0b27a2b92eb5625742c10669242ca3d3a8a9d33c`).

## 2. What is built (offline)

`tools/farm_permission_prompts.py` (tested by `tools/test_farm_permission_prompts.py`):

- **Recognition** from OCR. It reads the alert families by their iOS wording:
  local network, photos, notifications, tracking, paste, camera, microphone,
  location, contacts and Bluetooth. A generic *Don't Allow* button covers the
  rest. It also reads the app name and each button's position.
  - Across **432 retained frames** from the Reel, TikTok, X and YouTube routes,
    it detects only the 11 YouTube frames that show the prompt.
  - With the pointer over a button, OCR loses that button's label. The run then
    stops; it never guesses.
- **Policy**, the least privilege that still lets the run continue:

  | Family | Answer |
  |---|---|
  | local network | Don't Allow |
  | notifications | Don't Allow |
  | camera, microphone, location, contacts, Bluetooth | Don't Allow |
  | tracking | Ask App Not to Track |
  | photos | Allow Full Access, only for the app whose own media picker the run is opening; otherwise stop |
  | paste | Allow Paste, only directly after the run's own Paste |
  | photos reminder ("has been able to access your entire photo library", 20 Oct) | Allow Full Access, which keeps the current setting |
  | unknown | stop |

  A prompt for a different app than the one being driven is not answered. The
  exceptions are local network, notifications and tracking, where declining is
  always safe.
- **Input methods with evidence.** Each family records each method as `ignored`,
  unvalidated or `validated`. A run uses only `validated` methods; none exist yet.
- **Workflow integration (Reel, TikTok and X):**
  - Every screen check first looks for a prompt over the screen and records it
    with its decision.
  - **Without a validated method the run stops with a precise one-time request.**
    For example: *Choose "Don't Allow" on "YouTube"'s local network prompt on the
    phone. iOS keeps this answer, so it is a one-time step per phone and app.*
  - With a validated method, the run answers once as its own journaled action
    (`answer-<family>-prompt-N`), re-observes the same screen and continues. It
    answers at most two prompts per observation.
  - Pointer tap, long press and Escape are implemented. Absolute tap and keyboard
    focus raise "not implemented" until validated.
  - The TikTok fixture proves both paths with a first-time Photos prompt over the
    camera (synthetic composite):
    - by default the run stops before the picker;
    - with a validated method it answers *Allow Full Access* and saves the draft.
  - The X fixture stops on an unrecognized *Allow / Don't Allow* alert over the
    media composer before Save to drafts. X adds media through the iOS system
    photo picker, which needs no Photos permission.

## 3. Ways to stop needing a human

In order of promise:

1. **Absolute-coordinate input.**
   - The vendor library has a second report family, `A0` (buttons plus absolute
     X/Y scaled to 0–32767). The kernel already contains a guarded **move-only**
     probe (`--absolute-probe-pid C24C`, commit `373dd58`) that has never been
     sent to a phone.
   - If iOS treats the absolute device differently from the relative pointer,
     for example closer to a touch, privacy alerts may accept it.
   - Sequence: run the existing move-only probe in a window and confirm
     positioning. Only then add a guarded absolute press/release, and try it once
     on a reproducible prompt (step 4).
2. **Keyboard focus.** C24C reportedly has Full Keyboard Access on (never changed
   by the farm). Tab to move focus to the button, then Space or Return, may work
   even though Escape did not. It is untested and needs a Space key path in the
   workflow step (today's step refuses spaces in text).
3. **Long press** on the button (down about 1.1 s, then up). Untested; cheap to
   try.
4. **A reproducible test prompt.** The YouTube prompt never reappears once
   answered. Validation therefore needs a prompt that can be raised on demand.
   None is confirmed yet:
   - **Not the farm's transfer page.** An earlier draft of this record proposed
     a location request from that page. Browsers expose location only on HTTPS
     pages, and the transfer link is plain HTTP. A website prompt is also drawn
     by Safari itself, not by the system alert that ignored the pointer, so it
     would not validate the same alert class.
   - **To check on the phone:** an iOS privacy setting that asks every time.
     The candidate is an app's *Paste from Other Apps* set to *Ask*, together
     with an action that reads the clipboard. Whether that alert is the same
     class as the YouTube one is part of the check.
   - Deleting and reinstalling an app, or resetting all privacy settings, would
     also raise prompts. Both are too disruptive for a farm phone.
   - Validation always answers with the declining button.
5. **Prevention, the fallback that already works.**
   - iOS keeps every answer per app.
   - A **setup sweep** per new phone (operator present once) opens each app the
     farm uses, lets the farm name each first-run prompt, and records it as
     cleared.
   - Later runs meet no prompts on that phone. With 19 phones this turns
     "constantly" into once per phone and app.
   - Device management can preconfigure some prompts (for example notifications)
     on supervised phones. Local network and photos generally cannot, so the
     sweep is still needed.

## 4. What a validation window needs

An agreed time with C24C mirroring connected and the operator present. Then, in
this order, stopping at the first unexpected result:

1. The existing move-only absolute probe.
2. Find a reproducible system prompt (section 3, item 4). Without one, each
   method below gets a single try on the next real first-run prompt.
3. Long press on the declining button.
4. Keyboard focus.
5. A guarded absolute tap, once built, after (1) passes.

Each method that dismisses the prompt with the intended answer becomes
`validated` for that family, with its evidence, and only then can runs use it.
No method is ever tried on *Allow* buttons during validation.

The window is prepared offline in
[the prompt-validation record](../farm-prompt-validation-20261020/README.md)
(branch `local/prompt-validation-20261020`): scripts, steps, candidate prompts,
stop conditions and how a result becomes `validated`.
