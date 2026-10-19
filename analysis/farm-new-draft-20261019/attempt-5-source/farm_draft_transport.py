"""Restricted C24C draft transport; no release endpoint or publishing command."""
import json
import urllib.request
from farm_live_verification import ReadOnlyKernel, NoRedirect
from farm_carousel_inspection import InspectionStopped
from farm_screen_layout import picker_controls, editor_controls, next_label, NEXT_BOX, words_at
from farm_draft_rehearsal import save_prompt
from imouse_social_automation import IMouseKernel, LIVE_TEST_DEVICE_ID, KernelSafetyError

def allowed_tap(text, x, y, intent, frame=None):
    if not (10 <= x <= 490 and 65 <= y <= 1035):
        raise InspectionStopped('Tap is outside the reviewed app area.')
    for line in text.get('lines', []):
        words = line.get('words', [])
        if not words: continue
        left=min(w['x'] for w in words); right=max(w['x']+w['width'] for w in words)
        top=min(w['y'] for w in words); bottom=max(w['y']+w['height'] for w in words)
        if left-45 <= x <= right+45 and top-25 <= y <= bottom+25:
            if any(word in line['text'].casefold().split() for word in ('share','publish','send','post','discard','delete','follow')):
                # Selecting the explicit Post format in the create menu is preparation,
                # not the final Post/Share action. It needs an independent visual review.
                labels={row['text'].casefold() for row in text.get('lines',[])}
                # The current Create sheet also has an Edits row. OCR sometimes
                # omits Reel entirely; recognize independent, exact positioned
                # labels rather than repairing it or bypassing the Post guard.
                edits_menu = all(words_at(text,label,box) for label,box in (
                    ('create',(205,505,290,540)),('edits',(60,612,130,650)),
                    ('post',(60,665,130,700)),('story',(60,720,140,755)),
                    ('instants',(60,770,155,810))))
                if not (intent == 'choose_post_format' and line['text'].casefold() == 'post'
                        and ({'create','reel','story'} <= labels or edits_menu) and .30 < y/1080 < .92):
                    raise InspectionStopped('Target overlaps a prohibited or ambiguous action label.')
    if intent == 'details':
        left, top, right, bottom = NEXT_BOX
        if (frame is None or not editor_controls(frame, text) or not next_label(frame, text)
                or not left + 8 <= x <= right - 8 or not top + 8 <= y <= bottom - 8):
            raise InspectionStopped('The exact Next label and its editor target are not verified.')
    if intent == 'save_draft' and (not save_prompt(text) or not .83 <= y / 1080 <= .89):
        raise InspectionStopped('Save draft sheet/target is not recognized.')
    if intent == 'open_drafts':
        if frame is None or not picker_controls(frame, text):
            raise InspectionStopped('The production picker recognizer did not verify this frame.')
        rows=text.get('lines',[])
        header=any(row['text'].casefold()=='new post' and min(w['y'] for w in row['words'])<130 for row in rows if row['words'])
        targets=[w for row in rows for w in row['words'] if w['text'].casefold()=='drafts' and 610<w['y']<680
                 and w['x']-15<=x<=w['x']+w['width']+15 and w['y']-15<=y<=w['y']+w['height']+15]
        target=len(targets)==1
        if not header or not target: raise InspectionStopped('Drafts control is not located in the reviewed post picker.')
    if intent == 'leave_picker':
        rows=text.get('lines',[])
        labels={row['text'].casefold() for row in rows if row.get('words')
                and min(w['y'] for w in row['words'])<130}
        if not ({'new post','drafts'} & labels) or not (20<=x<=55 and 70<=y<=100):
            raise InspectionStopped('Only the reviewed picker/library close control may be used.')


class StepKernel(IMouseKernel):
    def __init__(self, url, transport=None, *, _creation=False):
        reader=ReadOnlyKernel(url,transport=transport)
        super().__init__(url)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        def limited(method,target,body,timeout):
            if method == 'GET' or body == {'fun':'/input/status','data':{}}:
                return reader._transport(method,target,body,timeout)
            if method != 'POST' or target != self.url+'/':
                raise KernelSafetyError('Unsupported probe transport.')
            if not isinstance(body,dict) or not isinstance(body.get('data'),dict):
                raise KernelSafetyError('Malformed probe request.')
            fun=body.get('fun'); data=body['data']
            allowed=('/input/acquire','/input/renew','/input/release','/mouse/reset','/mouse/move','/mouse/click','/mouse/swipe')
            if _creation: allowed += ('/mouse/down','/mouse/up','/key/sendkey')
            if fun not in allowed:
                raise KernelSafetyError('This probe cannot send that command.')
            if data.get('id') != LIVE_TEST_DEVICE_ID:
                raise KernelSafetyError('Only C24C is accepted.')
            if fun == '/key/sendkey':
                key=data.get('key')
                fields=set(data)-{'id','token'}
                if not ((fields=={'fn_key'} and data['fn_key'] in ('Home','Enter','Escape')) or
                        (fields=={'key'} and isinstance(key,str) and 1<=len(key)<=12 and
                         all(33<=ord(c)<=126 for c in key))):
                    raise KernelSafetyError('Creation permits only bounded URL/app text, Home, Enter or Escape; captions use Paste.')
            if transport is not None: return transport(method,target,body,timeout)
            request=urllib.request.Request(target,data=json.dumps(body).encode('utf-8'),method=method,
                headers={'Content-Type':'application/json'})
            with opener.open(request,timeout=min(timeout,8)) as response:
                raw=response.read(1024*1024+1)
                if len(raw)>1024*1024: raise KernelSafetyError('Candidate response exceeds the evidence limit.')
                return raw,dict(response.headers)
        self._transport=limited
        self.devices=reader.devices


class CreationKernel(StepKernel):
    """Separate internal transport for the creation state machine, never HTTP commands."""
    def __init__(self,url,transport=None):
        super().__init__(url,transport,_creation=True)
