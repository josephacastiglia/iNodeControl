"""iOS permission prompts: recognition, an answer policy and validated input methods. No input.

A workflow that meets a prompt asks `plan()` what to do. The answer is the
least-privilege choice that still lets that run continue. An input method is
used only after it has been validated for that prompt family on a phone. Until
then the run stops with a precise one-time request, and nothing clicks through a
prompt blindly. Evidence so far: on 17 Oct (C24C) YouTube's local-network prompt
highlighted under the pointer, but ignored the pointer click and Escape. The
operator chose Don't Allow by hand.
"""
import re

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
    'unknown_permission': None,
}

# Input methods, in the order a validation window tries them. Each records its
# evidence per prompt family. Only 'validated' entries are ever used by a run.
METHODS = ('pointer_tap', 'keyboard_escape', 'absolute_tap', 'keyboard_focus', 'long_press')
EVIDENCE = {
    ('local_network', 'pointer_tap'): ('ignored', '17 Oct C24C steps 133-134: button highlighted under the pointer; click ignored'),
    ('local_network', 'keyboard_escape'): ('ignored', '17 Oct C24C step 135: Escape ignored'),
}

_QUOTE = '["“”‘’\']'
FAMILIES = (
    ('local_network', re.compile(r'devices on (your )?local networks?', re.I)),
    ('tracking', re.compile(r'track your activity', re.I)),
    ('notifications', re.compile(r'send you notifications', re.I)),
    ('paste', re.compile(r'would like to paste from|wants to paste from', re.I)),
    ('photos', re.compile(r'access (to )?your (photos|photo library)', re.I)),
    ('camera', re.compile(r'access (to )?(the|your) camera', re.I)),
    ('microphone', re.compile(r'access (to )?(the|your) microphone', re.I)),
    ('location', re.compile(r'use your (current |precise )?location|access your location', re.I)),
    ('contacts', re.compile(r'access (to )?your contacts', re.I)),
    ('bluetooth', re.compile(r'use bluetooth|find and connect to bluetooth', re.I)),
)
BUTTONS = ("Don't Allow", 'Allow', 'Allow Full Access', 'Limit Access...', 'Ask App Not to Track', 'Allow Paste',
           "Don't Allow Paste", 'Allow Once', 'Allow While Using App', 'OK')
APP = re.compile(r'(?:allow\s+' + _QUOTE + r'(?P<a>[^"“”‘’\']{1,40})' + _QUOTE + r'|'
                 + _QUOTE + r'(?P<b>[^"“”‘’\']{1,40})' + _QUOTE + r'\s+(?:would like|wants))', re.I)


def _norm(value):
    return ' '.join(str(value).replace('’', "'").replace('‘', "'").split())


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
    app = (match.group('a') or match.group('b')).strip() if match else None
    return dict(kind=kind, app=app, buttons=buttons, ambiguous=False, joined=joined)


def plan(prompt, *, app_expected=None, needs_media_picker=False, after_own_paste=False, validated=None):
    """What a run may do. Never 'tap' unless the method is validated for this family.

    validated: {(family, method): ...} entries proven on a phone; defaults to EVIDENCE's
    'validated' items (none yet). Returns action 'answer' with a method and target, or
    'stop' with an operator request that names the prompt, the answer and why.
    """
    kind, app = prompt['kind'], prompt.get('app')
    answer = POLICY.get(kind)
    if kind == 'photos' and not needs_media_picker: answer = None
    if kind == 'paste' and not after_own_paste: answer = None
    if app_expected and app and app.casefold() != app_expected.casefold() and kind not in ('local_network', 'notifications', 'tracking'):
        answer = None   # A prompt for another app during this run is not ours to answer.
    reason = None
    if prompt.get('ambiguous'): answer, reason = None, 'Two identical buttons were read.'
    if answer is not None and answer not in prompt['buttons']:
        answer, reason = None, 'The policy answer is not visible on this prompt.'
    proven = {key: value for key, value in (validated if validated is not None else EVIDENCE).items() if value[0] == 'validated'}
    method = next((m for m in METHODS if (kind, m) in proven), None)
    if answer is not None and method is not None:
        return dict(action='answer', kind=kind, app=app, answer=answer, method=method, target=prompt['buttons'][answer],
                    evidence=proven[(kind, method)][1])
    who = f'"{app}"' if app else 'this app'
    request = (f'Choose "{answer}" on {who}\'s {kind.replace("_", " ")} prompt on the phone. iOS keeps this answer, '
               'so it is a one-time step per phone and app.' if answer else
               f'Review {who}\'s {kind.replace("_", " ")} prompt on the phone; the farm has no safe automatic answer for it.')
    tried = sorted(m for (k, m), (state, _) in EVIDENCE.items() if k == kind and state == 'ignored')
    return dict(action='stop', kind=kind, app=app, answer=answer, method=None, request=request,
                reason=reason or ('No input method is validated for this prompt yet.' if answer else 'No automatic answer applies.'),
                ignoredMethods=tried)
