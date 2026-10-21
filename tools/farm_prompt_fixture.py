"""Offline C24C stand-in for prompt-validation tests and the window dry run. No socket or phone.

It draws a phone screen with an iOS-style alert, keeps the pointer, a Full Keyboard Access
focus highlight and the prompt's state, and answers the kernel calls a validation step makes.
Synthetic throughout: it tests the protocol and the guards, not how iOS treats any input.
"""
import copy
import hashlib
import io
import uuid

from PIL import Image, ImageDraw

from imouse_social_automation import LIVE_TEST_DEVICE_ID

START = 1792454400.0          # 2026-10-20 00:00 UTC

PROMPTS = {
    'local_network': dict(app='YouTube', box=(88, 263, 412, 835),
                          lines=('Allow "YouTube" to find', 'devices on local networks?'), top=300,
                          buttons=(("Don't Allow", (88, 782, 250, 835)), ('Allow', (250, 782, 412, 835)))),
    'paste': dict(app='TikTok', box=(88, 420, 412, 640),
                  lines=('"TikTok" would like to paste from', '"Notes"', 'Do you want to allow this?'), top=455,
                  buttons=(("Don't Allow Paste", (88, 588, 250, 640)), ('Allow Paste', (250, 588, 412, 640)))),
    # iOS's reminder about full photo-library access the app already has (wording from 20 Oct).
    'photos_reminder': dict(app='Instagram', box=(88, 380, 412, 800),
                            lines=('"Instagram" has been able to access', 'your entire photo library.', 'Do you want to continue to',
                                   'allow full access?'), top=415,
                            buttons=(('Limit Access', (88, 694, 412, 747)), ('Allow Full Access', (88, 747, 412, 800)))),
    'location': dict(app='Maps', box=(88, 360, 412, 840),
                     lines=('Allow "Maps" to use your', 'location?'), top=395, extras=(('Precise: On', (165, 470)),),
                     buttons=(('Allow Once', (88, 680, 412, 733)), ('Allow While Using App', (88, 733, 412, 786)),
                              ("Don't Allow", (88, 786, 412, 840)))),
}


def line(text, x, y, width=None, height=18):
    words, cursor = [], x
    for part in text.split(' '):
        w = max(8, round((width or len(text)*9) * len(part)/max(1, len(text))))
        words.append(dict(text=part, x=cursor, y=y, width=w, height=height)); cursor += w + 6
    return dict(text=text, words=words)


def centred(text, cx, cy):
    return line(text, round(cx - len(text)*4.5), round(cy - 9))


class FixtureOcr:
    def __init__(self, phone): self.phone = phone

    def read(self, raw):
        digest = hashlib.sha256(raw).hexdigest()
        text = copy.deepcopy(self.phone.texts[digest]); text['frameSha256'] = digest
        return text


class PromptPhone:
    """Kernel-shaped fixture. answers: methods that activate the button they reach."""
    _is_live_http = False

    def __init__(self, prompt='local_network', *, answers=(), fka=True, focus_order=('Allow', "Don't Allow"), focus_style='fill',
                 probe=False, probe_mode='positioned', screen=None, busy=False, kernel_hash='a'*64, uid='fixture-uid',
                 lose_reply=None, stale_after_tab=False, receiver_change_after=None, pointer=None, focus_auto_hide=1.0):
        self.now = START
        self.prompt = PROMPTS[prompt] if prompt else None
        self.visible = prompt is not None
        self.answers, self.fka, self.focus_order, self.focus_style = set(answers), fka, tuple(focus_order), focus_style
        self.probe, self.probe_mode = probe, probe_mode
        self.screen = screen or ('blank' if probe else 'app')
        self.owned, self.generation = busy, 7
        self.kernel_hash, self.uid = kernel_hash, uid
        self.lose_reply, self.stale_after_tab, self.receiver_change_after = lose_reply, stale_after_tab, receiver_change_after
        self.sequence, self.changed_at, self.session = 100, START, uuid.uuid4().hex
        self.pointer, self.pressed, self.focus, self.tabs = pointer, None, None, 0
        # C24C's Full Keyboard Access hides its focus highlight 1 s after the last key (Auto-Hide 1s,
        # 11 Oct); the focus itself stays. None keeps the highlight showing.
        self.focus_auto_hide, self.focus_key_at, self.focus_shown = focus_auto_hide, None, False
        self.answered, self.calls, self.unexpected, self.texts = None, [], [], {}
        self.replies, self.sends, self.last_tab = 0, 0, False

    # -- clock -------------------------------------------------------------------------------
    def clock(self): self.now += .001; return self.now
    def pause(self, seconds): self.now += seconds

    def change(self):
        self.sequence += 1; self.changed_at = self.now

    def hide_focus(self):
        if self.focus_shown and self.focus_auto_hide is not None and self.now - self.focus_key_at >= self.focus_auto_hide:
            self.focus_shown = False; self.sequence += 1; self.changed_at = self.focus_key_at + self.focus_auto_hide

    # -- kernel surface ------------------------------------------------------------------------
    def resolve_device_id(self, phone):
        if phone != 'C24C': raise AssertionError('Another phone was addressed.')
        return LIVE_TEST_DEVICE_ID

    def receiver(self):
        self.hide_focus()
        return dict(deviceid=LIVE_TEST_DEVICE_ID, name='iMouse2-C24C', receiver_pid=321, receiver_restarts=0, live=True,
                    frames=self.sequence, frame_session=self.session)

    def kernel_status(self):
        boards = [dict(pid='C24C', observation=dict(State='receiving', Reports=self.replies))] if self.probe else []
        return dict(code=0, build_identity=dict(sha256=self.kernel_hash), input_leases_required=True, allowed=['C24C'],
                    process=dict(pid=4321, started_utc='2026-10-20T10:00:00.0000000Z'), receivers=[self.receiver()],
                    input_configuration=dict(absolute_probe_board='C24C' if self.probe else None,
                                             hid_reply_boards=['C24C'] if self.probe else []),
                    hid_replies=dict(boards=boards))

    def devices(self): return [dict(deviceid=LIVE_TEST_DEVICE_ID, pid='C24C', uid=self.uid)]

    def input_status(self):
        return {LIVE_TEST_DEVICE_ID: dict(id=LIVE_TEST_DEVICE_ID, generation=self.generation, owned=self.owned, active=False,
                                          stopped=False, releasing=False, release_failed=False, lease_remaining_ms=30000)}

    def preflight_phone(self, phone):
        if self.owned: raise AssertionError('Takeover of an owned phone.')
        return dict(resolved_id=self.resolve_device_id(phone), receiver=self.receiver())

    def acquire(self, phones, lease_ms):
        assert phones == ['C24C'] and not self.owned
        self.owned = True; return {'C24C': 'fixture-token'}

    def renew_if_needed(self, tokens, min_remaining_ms): assert tokens == {'C24C': 'fixture-token'} and self.owned

    def release(self, tokens):
        assert tokens == {'C24C': 'fixture-token'}
        self.owned = False; self.generation += 1; self.calls.append('release')

    def shot(self, phone):
        self.resolve_device_id(phone); self.hide_focus()
        image, text = self.render()
        out = io.BytesIO(); image.save(out, 'PNG'); raw = out.getvalue()
        self.texts[hashlib.sha256(raw).hexdigest()] = dict(text, width=500, height=1080)
        age = 2000 if self.stale_after_tab and self.last_tab else round((self.now - self.changed_at)*1000)
        return raw, {'X-iMouse-Frame-Session': self.session, 'X-iMouse-Frame-Sequence': str(self.sequence),
                     'X-iMouse-Frame-Age-Ms': str(age), 'X-iMouse-Frame-Delivery': 'flowing'}

    def send(self, phone, token, fun, **data):
        assert phone == 'C24C' and token == 'fixture-token' and self.owned, 'Input without the lease.'
        self.calls.append((fun, dict(data)))
        self.sends += 1
        self.last_tab = fun == '/key/sendkey' and data.get('fn_key') == 'Tab'
        if self.probe: self.absolute(fun, data)
        else: self.relative(fun, data)
        if self.receiver_change_after is not None and self.sends >= self.receiver_change_after: self.session = uuid.uuid4().hex
        if self.lose_reply and self.lose_reply(fun, data): raise TimeoutError('Fixture: the action happened; its answer was lost.')
        return dict(code=0, results=[dict(id=LIVE_TEST_DEVICE_ID, code=0, message='ok')])

    # -- behaviour ---------------------------------------------------------------------------
    def button_at(self, x, y):
        if not self.visible: return None
        return next((label for label, (l, t, r, b) in self.prompt['buttons'] if l <= x < r and t <= y < b), None)

    def dismiss(self, label):
        self.answered, self.visible, self.focus, self.focus_shown = label, False, None, False
        self.change()

    def move(self, point):
        if point != self.pointer: self.pointer = point; self.change()

    def relative(self, fun, data):
        if fun == '/mouse/reset': self.move((14, 14))
        elif fun == '/mouse/move': self.move((data['x'], data['y']))
        elif fun == '/mouse/click':
            self.move((data['x'], data['y']))
            hit = self.button_at(*self.pointer)
            if hit is None: self.flag(fun, data)
            elif 'pointer_tap' in self.answers: self.dismiss(hit)
        elif fun == '/mouse/down': self.pressed = self.button_at(*self.pointer) if self.pointer else None
        elif fun == '/mouse/up':
            if self.pressed and 'long_press' in self.answers: self.dismiss(self.pressed)
            self.pressed = None
        elif fun == '/key/sendkey' and data == {'fn_key': 'Escape'}:
            if self.visible and 'keyboard_escape' in self.answers: self.dismiss(self.cancel_answer())
        elif fun == '/key/sendkey' and data == {'fn_key': 'Tab'}:
            if self.visible and self.fka:
                self.focus = self.focus_order[self.tabs % len(self.focus_order)]; self.tabs += 1
                self.focus_key_at, self.focus_shown = self.now, True; self.change()
        elif fun == '/key/sendkey' and data == {'key': ' '}:
            if self.visible and self.fka and self.focus not in (None, 'body') and 'keyboard_focus' in self.answers:
                self.dismiss(self.focus)
        else: self.flag(fun, data)

    def cancel_answer(self):
        labels = [label for label, _ in self.prompt['buttons']]
        return next(label for label in ("Don't Allow Paste", "Don't Allow", 'Ask App Not to Track') if label in labels)

    def absolute(self, fun, data):
        if fun != '/mouse/move': self.flag(fun, data); return
        self.replies += 1
        x, y = data['x'], data['y']
        if self.probe_mode == 'positioned': self.move((x, y))
        elif self.probe_mode == 'offset': self.move((round(x*.8 + 20), round(y*.8 + 30)))
        elif self.probe_mode == 'tap': self.screen = 'navigated'; self.move((x, y))

    def flag(self, fun, data):
        self.unexpected.append((fun, dict(data)))
        raise AssertionError(f'Unexpected {fun} {data} on the fixture phone.')

    # -- drawing -----------------------------------------------------------------------------
    def render(self):
        image = Image.new('RGB', (500, 1080), 'white'); draw = ImageDraw.Draw(image)
        lines = [line('9:41', 40, 18, 36, 16)]
        draw.text((40, 20), '9:41', fill='black')
        if self.screen == 'app':
            draw.text((210, 80), 'Phone app', fill='black'); lines.append(line('Phone app', 210, 78))
            for top in (140, 330, 520, 710, 900):
                draw.rectangle((20, top, 480, top + 160), fill=(205, 214, 228))
        elif self.screen == 'navigated':
            draw.rectangle((0, 70, 500, 1080), fill=(30, 30, 60)); draw.text((200, 500), 'Search', fill='white')
            lines.append(line('Search', 200, 498))
        else:   # Safari about:blank: a white page above the bottom bar.
            draw.rectangle((0, 935, 500, 1080), fill=(240, 240, 240)); draw.text((210, 960), 'about:blank', fill='black')
            lines.append(line('about:blank', 210, 958))
        if self.visible and self.prompt:
            image = Image.eval(image, lambda v: round(v*.6)); draw = ImageDraw.Draw(image)
            l, t, r, b = self.prompt['box']
            draw.rounded_rectangle(self.prompt['box'], 14, fill=(242, 242, 242))
            for index, text in enumerate(self.prompt['lines']):
                y = self.prompt['top'] + 24*index
                lines.append(centred(text, 250, y)); draw.text((round(250 - len(text)*3), y - 6), text, fill='black')
            for label, (cx, cy) in self.prompt.get('extras', ()):   # A control that is not an answer.
                box = centred(label, cx, cy); lines.append(box)
                draw.text((round(cx - len(label)*3), round(cy - 6)), label, fill='black')
                if self.focus == label and self.focus_shown:
                    words = box['words']
                    draw.rectangle((words[0]['x'], words[0]['y'], words[-1]['x'] + words[-1]['width'], words[0]['y'] + 18),
                                   outline=(10, 132, 255), width=3)
            for label, (bl, bt, br, bb) in self.prompt['buttons']:
                draw.line((bl, bt, br, bt), fill=(200, 200, 200), width=1)
                hovered = self.pointer is not None and bl <= self.pointer[0] < br and bt <= self.pointer[1] < bb
                if hovered: draw.rectangle((bl + 1, bt + 1, br - 1, bb - 1), fill=(222, 222, 222))
                if self.focus == label and self.focus_shown and self.focus_style == 'fill':
                    draw.rectangle((bl + 2, bt + 2, br - 3, bb - 3), fill=(224, 236, 255), outline=(10, 132, 255), width=3)
                elif self.focus == label and self.focus_shown:   # A ring alone, drawn just outside the answer.
                    draw.rectangle((bl - 2, bt - 2, br + 2, bb + 2), outline=(10, 132, 255), width=3)
                cx, cy = (bl + br)/2, (bt + bb)/2
                draw.text((round(cx - len(label)*3), round(cy - 6)), label, fill=(0, 122, 255))
                if not hovered: lines.append(centred(label, cx, cy))   # OCR loses a hovered label (17 Oct).
            if len(self.prompt['buttons']) == 2:
                draw.line((250, self.prompt['buttons'][0][1][1], 250, b), fill=(200, 200, 200), width=1)
            if self.focus == 'body' and self.focus_shown:
                draw.rectangle((l + 10, self.prompt['top'] - 14, r - 10, self.prompt['top'] + 24*len(self.prompt['lines'])),
                               outline=(10, 132, 255), width=3)
        if self.pointer is not None:
            x, y = self.pointer
            draw.ellipse((x - 10, y - 10, x + 10, y + 10), fill=(128, 128, 128))
        return image, dict(lines=lines)
