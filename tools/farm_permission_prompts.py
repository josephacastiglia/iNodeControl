"""iOS permission prompts: recognition, an answer policy and validated input methods. No input.

A workflow that meets a prompt asks `plan()` what to do. The answer is the
least-privilege choice that still lets that run continue. An input method is
used only after it has been validated for that prompt family on a phone. Until
then the run stops with a precise one-time request, and nothing clicks through a
prompt blindly. Evidence so far: on 17 Oct (C24C) YouTube's local-network prompt
highlighted under the pointer, but ignored the pointer click and Escape. The
operator chose Don't Allow by hand.

A method becomes validated only through WINDOW_EVIDENCE: results that
tools/farm_prompt_validation.py recorded in a C24C validation window, each with
the operator's confirmation of the safe answer. Nothing is validated by default.
Evidence is per phone: on 20 Oct the same move-then-click answered a prompt on one
rack phone and was ignored on another.
"""
import re
import uuid

# Answer per prompt family. None means the run must stop and ask.
POLICY = {
    'local_network': "Don't Allow",
    'notifications': "Don't Allow",
    'tracking': 'Ask App Not to Track',
    'camera': "Don't Allow",
    'microphone': "Don't Allow",
    'location': "Don't Allow",
    'contacts': "Don't Allow",
    'bluetooth': "Don't Allow",
    # Needed only by the app whose own media picker the run is about to use.
    'photos': 'Allow Full Access',
    # Needed only directly after the run's own Paste.
    'paste': 'Allow Paste',
    # iOS's reminder about full photo-library access the app already has. Allow Full Access
    # keeps the current setting; Limit Access would change it and open the photo selection.
    'photos_reminder': 'Allow Full Access',
    'unknown_permission': None,
}
# The safe answer of each family: the only button a validation window ever targets. It grants
# nothing the app does not already have: the declining button, or for the full-access
# reminder, keeping the current setting.
SAFE_ANSWER = {
    'local_network': "Don't Allow", 'notifications': "Don't Allow", 'tracking': 'Ask App Not to Track',
    'camera': "Don't Allow", 'microphone': "Don't Allow", 'location': "Don't Allow", 'contacts': "Don't Allow",
    'bluetooth': "Don't Allow", 'photos': "Don't Allow", 'paste': "Don't Allow Paste", 'photos_reminder': 'Allow Full Access',
}
# Answers an alert's cancel action gives. Escape reaches only that action, so it is used only for these.
CANCEL_ANSWERS = ("Don't Allow", 'Ask App Not to Track', "Don't Allow Paste")
# Families whose policy answer changes nothing, so it is answered even for another app.
ALWAYS_SAFE = ('local_network', 'notifications', 'tracking', 'photos_reminder')

# Input methods, in the order a validation window tries them. Each records its
# evidence per prompt family. Only 'validated' entries are ever used by a run.
METHODS = ('pointer_tap', 'keyboard_escape', 'absolute_tap', 'keyboard_focus', 'long_press')
# What the shared run answer path (ReelCreationWorkflow.answer_prompt, used by the Reel,
# TikTok and X runs) can send. Escape only reaches an alert's cancel action, so it may
# only decline. A method validated in a window but missing here stops the run with its
# one-time request; it is added here together with its run implementation.
RUN_METHODS = ('pointer_tap', 'keyboard_escape', 'long_press')
EVIDENCE = {
    ('local_network', 'pointer_tap'): ('ignored', '17 Oct C24C steps 133-134: button highlighted under the pointer; click ignored'),
    ('local_network', 'keyboard_escape'): ('ignored', '17 Oct C24C step 135: Escape ignored'),
}
# Validation-window results, one record per (family, method), added only by a reviewed
# commit of the `promote` output of tools/farm_prompt_validation.py. An entry counts only
# when window_problems() finds its evidence complete.
WINDOW_EVIDENCE = ()
WINDOW_SOURCE = 'c24c_prompt_validation_window'
WINDOW_RECORD = 'analysis/farm-prompt-validation-20261020/window/'
_SHA256 = re.compile(r'[0-9a-f]{64}')

_QUOTE = '["“”‘’\']'
FAMILIES = (
    ('local_network', re.compile(r'devices on (your )?local networks?', re.I)),
    ('tracking', re.compile(r'track your activity', re.I)),
    ('notifications', re.compile(r'send you notifications', re.I)),
    ('paste', re.compile(r'would like to paste from|wants to paste from', re.I)),
    # Before 'photos': the reminder about existing full access, never a first request.
    ('photos_reminder', re.compile(r'has been able to access your entire photo library|continue to allow full access', re.I)),
    ('photos', re.compile(r'access (to )?your (photos|photo library)', re.I)),
    ('camera', re.compile(r'access (to )?(the|your) camera', re.I)),
    ('microphone', re.compile(r'access (to )?(the|your) microphone', re.I)),
    ('location', re.compile(r'use your (current |precise )?location|access your location', re.I)),
    ('contacts', re.compile(r'access (to )?your contacts', re.I)),
    ('bluetooth', re.compile(r'use bluetooth|find and connect to bluetooth', re.I)),
)
BUTTONS = ("Don't Allow", 'Allow', 'Allow Full Access', 'Limit Access...', 'Limit Access', 'Ask App Not to Track', 'Allow Paste',
           "Don't Allow Paste", 'Allow Once', 'Allow While Using App', 'OK')
APP = re.compile(r'(?:allow\s+' + _QUOTE + r'(?P<a>[^"“”‘’\']{1,40})' + _QUOTE + r'|'
                 + _QUOTE + r'(?P<b>[^"“”‘’\']{1,40})' + _QUOTE + r'\s+(?:would like|wants)|'
                 + _QUOTE + r'(?P<c>[^"“”‘’\']{1,40})' + _QUOTE + r'\s+has been able)', re.I)


def _norm(value):
    return ' '.join(str(value).replace('’', "'").replace('‘', "'").replace('…', '...').split())


def _rows(text):
    rows = []
    for line in text.get('lines', []):
        words = line.get('words') or []
        if not words: continue
        rows.append(dict(text=_norm(line.get('text', '')), left=min(w['x'] for w in words), top=min(w['y'] for w in words),
                         right=max(w['x']+w['width'] for w in words), bottom=max(w['y']+w['height'] for w in words)))
    return rows


def detect(text):
    """A recognized permission prompt, or None. OCR only; geometry decides the buttons."""
    rows = _rows(text)
    joined = ' '.join(r['text'] for r in sorted(rows, key=lambda r: (r['top'], r['left'])))
    buttons = {}
    for r in rows:
        label = r['text']
        if label.casefold() in {b.casefold() for b in BUTTONS}:
            canonical = next(b for b in BUTTONS if b.casefold() == label.casefold())
            if canonical in buttons: return dict(kind='unknown_permission', app=None, ambiguous=True, buttons={}, joined=joined)
            buttons[canonical] = (round((r['left']+r['right'])/2), round((r['top']+r['bottom'])/2))
    kind = next((name for name, pattern in FAMILIES if pattern.search(joined)), None)
    permission_like = "Don't Allow" in buttons or 'Ask App Not to Track' in buttons or "Don't Allow Paste" in buttons
    if kind is None and not permission_like: return None
    if kind is None: kind = 'unknown_permission'
    match = APP.search(joined)
    app = (match.group('a') or match.group('b') or match.group('c')).strip() if match else None
    return dict(kind=kind, app=app, buttons=buttons, ambiguous=False, joined=joined)


def button_boxes(text):
    """{button: (left, top, right, bottom)} for exactly read alert buttons; None if a label repeats."""
    boxes = {}
    for r in _rows(text):
        canonical = next((b for b in BUTTONS if b.casefold() == r['text'].casefold()), None)
        if canonical is None: continue
        if canonical in boxes: return None
        boxes[canonical] = (r['left'], r['top'], r['right'], r['bottom'])
    return boxes


# Fallback for a correctly placed click that was ignored (tools/farm_prompt_press.py): one settled press held on the
# policy answer. Only these families; on any other screen a hold this long is a long press. Shortest hold first:
# 800 ms answered A12's reminder (5 Nov, one trial), 80 and 300 ms did nothing, 400 and 600 ms are not yet known.
SLOW_PRESS = ('photos_reminder',)
SLOW_PRESS_HOLDS_MS = (400, 600, 800)
# Any of these in a row means the alert is still on the screen. The pointer's dot can hide the answer's own label
# ("Allow F' Access", A12, 5 Nov), so that label's absence proves nothing.
ALERT_ROWS = {'photos_reminder': ('has been able to', 'access your entire photo', 'continue to allow full', 'limit access', 'allow f')}


def slow_press_plan(prompt, *, click_ignored=False):
    """Whether this alert may take the held press, and on what. Needs a click already ignored and the policy answer read."""
    kind = prompt['kind']
    answer = POLICY.get(kind)
    reason = None
    if kind not in SLOW_PRESS: reason = 'This prompt has no slow-press fallback.'
    elif not click_ignored: reason = 'A correctly placed click comes first.'
    elif prompt.get('ambiguous'): reason = 'Two identical buttons were read.'
    elif answer not in prompt['buttons']: reason = 'The policy answer is not visible on this prompt.'
    elif "Don't Allow" in prompt['buttons']: reason = "A full-access reminder has no Don't Allow; this alert needs review."
    if reason: return dict(action='stop', kind=kind, reason=reason)
    return dict(action='press', kind=kind, answer=answer, target=prompt['buttons'][answer], holdsMs=SLOW_PRESS_HOLDS_MS)


def alert_reads(text, kind):
    """Whether any row of this family's alert still reads."""
    rows = [r['text'].casefold() for r in _rows(text)]
    return any(fragment in row for row in rows for fragment in ALERT_ROWS.get(kind, ()))


def window_problems(entry):
    """Why a validation-window entry cannot count as evidence. An empty list means it is complete."""
    if not isinstance(entry, dict): return ['A window entry must be a record.']
    problems = []
    family, method, state = entry.get('family'), entry.get('method'), entry.get('state')
    if family not in SAFE_ANSWER: problems.append('The prompt family is unknown or has no safe answer.')
    if method not in METHODS: problems.append('The input method is unknown.')
    if state not in ('validated', 'ignored'): problems.append('A window result is either validated or ignored.')
    if entry.get('source') != WINDOW_SOURCE or entry.get('phone') != 'C24C': problems.append('This is not C24C validation-window evidence.')
    if family in SAFE_ANSWER and entry.get('answer') != SAFE_ANSWER[family]:
        problems.append('Validation only ever targets the safe answer.')
    if not re.fullmatch(r'2\d{3}-\d{2}-\d{2}', str(entry.get('date'))): problems.append('The window date is missing.')
    try: uuid.UUID(str(entry.get('trial')))
    except ValueError: problems.append('The trial identity is missing.')
    summary = entry.get('summary')
    if not (isinstance(summary, str) and summary.startswith(WINDOW_RECORD) and summary.endswith('.json')
            and '..' not in summary and '\\' not in summary):
        problems.append('The trial summary is not in the validation record.')
    for key in ('summarySha256', 'beforeFrameSha256', 'afterFrameSha256'):
        if not _SHA256.fullmatch(str(entry.get(key))): problems.append(key + ' is missing.')
    if entry.get('commandsAnswered') is not True: problems.append('A trial command has no answered reply.')
    if entry.get('outcome') != {'validated': 'dismissed', 'ignored': 'ignored'}.get(state):
        problems.append('The recorded outcome does not support this state.')
    if state == 'validated' and (entry.get('safeAnswerConfirmed') is not True or not str(entry.get('confirmation') or '').strip()):
        problems.append("The operator's confirmation of the safe answer is missing.")
    return problems


def evidence(entries=None):
    """EVIDENCE plus complete window entries, as {(family, method): (state, note)}.

    Contradicting results for one pair become 'conflicting', which no run uses: a method
    seen both answering and ignored needs review first.
    """
    known = dict(EVIDENCE)
    for entry in WINDOW_EVIDENCE if entries is None else entries:
        if window_problems(entry): continue
        key = (entry['family'], entry['method'])
        note = f"{entry['date']} C24C window trial {entry['trial']}: {entry.get('note') or entry['outcome']}"
        if key not in known: known[key] = (entry['state'], note)
        elif known[key][0] != entry['state']: known[key] = ('conflicting', known[key][1] + ' | ' + note)
    return known


def plan(prompt, *, app_expected=None, needs_media_picker=False, after_own_paste=False, validated=None):
    """What a run may do. Never 'tap' unless the method is validated for this family.

    validated: {(family, method): (state, note)} entries proven on a phone; defaults to
    evidence(), which is EVIDENCE plus complete window results (none validated yet).
    Returns action 'answer' with a method the run can send and its target, or 'stop' with
    an operator request that names the prompt, the answer and why.
    """
    kind, app = prompt['kind'], prompt.get('app')
    answer = POLICY.get(kind)
    if kind == 'photos' and not needs_media_picker: answer = None
    if kind == 'paste' and not after_own_paste: answer = None
    if app_expected and app and app.casefold() != app_expected.casefold() and kind not in ALWAYS_SAFE:
        answer = None   # A prompt for another app during this run is not ours to answer.
    reason = None
    if kind == 'photos_reminder' and "Don't Allow" in prompt['buttons']:
        answer, reason = None, "A full-access reminder has no Don't Allow; this alert needs review."
    if prompt.get('ambiguous'): answer, reason = None, 'Two identical buttons were read.'
    if answer is not None and answer not in prompt['buttons']:
        answer, reason = None, 'The policy answer is not visible on this prompt.'
    known = evidence()
    proven = {key: value for key, value in (validated if validated is not None else known).items() if value[0] == 'validated'}
    runnable = [m for m in METHODS if (kind, m) in proven and m in RUN_METHODS
                and (m != 'keyboard_escape' or (answer in CANCEL_ANSWERS and answer == SAFE_ANSWER.get(kind)))]
    if answer is not None and runnable:
        method = runnable[0]
        return dict(action='answer', kind=kind, app=app, answer=answer, method=method, target=prompt['buttons'][answer],
                    evidence=proven[(kind, method)][1])
    waiting = [m for m in METHODS if (kind, m) in proven and m not in runnable]
    if answer and waiting and reason is None:
        reason = 'Validated but not usable for this answer in a run: ' + ', '.join(waiting) + '.'
    who = f'"{app}"' if app else 'this app'
    keeps = ('That keeps the current setting; iOS repeats this reminder from time to time.' if kind == 'photos_reminder'
             else 'iOS keeps this answer, so it is a one-time step per phone and app.')
    request = (f'Choose "{answer}" on {who}\'s {kind.replace("_", " ")} prompt on the phone. {keeps}' if answer else
               f'Review {who}\'s {kind.replace("_", " ")} prompt on the phone; the farm has no safe automatic answer for it.')
    tried = sorted(m for (k, m), (state, _) in known.items() if k == kind and state == 'ignored')
    return dict(action='stop', kind=kind, app=app, answer=answer, method=None, request=request,
                reason=reason or ('No input method is validated for this prompt yet.' if answer else 'No automatic answer applies.'),
                ignoredMethods=tried)
