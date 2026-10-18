"""One agent-reviewed C24C draft step. Not an unattended product adapter.

An explicit move-only challenge requests a new receiver frame on a quiet page.
It does not bypass freshness for taps. Each action has a durable, non-replayable
directory, a reviewed baseline, fresh OCR/frame evidence and one scoped lease.
No keyboard, Home, publication, messaging, settings or other-phone API exists.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import threading
import time
import urllib.request
import uuid
import zipfile

from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[2]
RUN = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools'))
from farm_carousel_inspection import OwnedCaptureRun, InspectionStopped
from farm_live_verification import ReadOnlyKernel, NoRedirect, validate_runtime, idle
from farm_frame_evidence import capture_settled
from farm_observations import ObservationStore, WindowsOcr
from farm_screen_layout import picker_controls, picker_stability, editor_controls, next_label, NEXT_BOX
from farm_draft_rehearsal import save_prompt
from farm_draft_media import media_comparison
from imouse_social_automation import IMouseKernel, LIVE_TEST_DEVICE_ID, KernelSafetyError


def same_reviewed_page(before, after, mean_limit=.008, change_limit=.015,
                       before_text=None, after_text=None):
    # The production picker recognizer is the only way to exclude autoplay pixels.
    # This comparison alone never establishes frame freshness or grants input.
    if (before_text is not None and after_text is not None
            and picker_controls(before, before_text) and picker_controls(after, after_text)):
        result = picker_stability(before, before_text, after, after_text)
        if not result['controlsStable']:
            raise InspectionStopped(result['reason'])
        return result
    with Image.open(io.BytesIO(before)) as a, Image.open(io.BytesIO(after)) as b:
        if a.size != b.size or a.size != (500,1080):
            raise InspectionStopped('Review frame dimensions changed.')
        # Exclude only the clock/status bar. Pointer movements remain in the comparison.
        difference = ImageChops.difference(a.convert('RGB'), b.convert('RGB'))
        difference = difference.crop((0,65,500,1050))
        mean = sum(ImageStat.Stat(difference).mean) / (3 * 255)
        changed = sum(1 for r,g,b in difference.getdata() if max(r,g,b) > 35) / (500 * 985)
    if mean > mean_limit or changed > change_limit:
        raise InspectionStopped('Page changed since visual review; inspect the retained fresh frame before another explicit step.')
    return dict(meanError=mean, changedFraction=changed)


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
                if not (intent == 'choose_post_format' and line['text'].casefold() == 'post'
                        and {'create','reel','story'} <= labels and .30 < y/1080 < .92):
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


def fresh_pair(before, first, after, second):
    """Both observations were fresh when captured, under this same lease/stream.

    The latest observation is re-aged again immediately before any command. An
    earlier image is never made fresh by obtaining another image or moving a dot.
    """
    for value in (before, after):
        if (value.get('freshness') != 'recent' or value.get('stable') is not True
                or value.get('inputSettled') is not True
                or value.get('frameEvidence', {}).get('pairedMetadata') is not True
                or not capture_settled(value)):
            raise InspectionStopped('Both comparison frames need recent, authenticated delivery evidence.')
    def context(value):
        return (value.get('receiverPid'), value['frameEvidence'].get('session'),
                value.get('inputGeneration'), value['ownershipEvidence'].get('runId'))
    if (any(item is None for item in context(before)) or context(before) != context(after)
            or type(before['frameEvidence'].get('sequence')) is not int
            or type(after['frameEvidence'].get('sequence')) is not int
            or after['frameEvidence']['sequence'] <= before['frameEvidence']['sequence']):
        raise InspectionStopped('Comparison frames changed lease/stream or did not advance.')
    result = same_reviewed_page(first, second, mean_limit=.002, change_limit=.005,
                                before_text=before['text'], after_text=after['text'])
    return {**result, 'beforeObservationId': before['id'], 'afterObservationId': after['id'],
            'freshAtEachCapture': True, 'automaticInputAllowed': False}


def verified_slide(frame, observation):
    if observation.get('result', {}).get('layout') != 'carousel_editor':
        raise InspectionStopped('The production recognizer did not identify a carousel editor.')
    package=ROOT/'analysis/farm-phone-transfer-20261017/test-carousel.zip'
    if hashlib.sha256(package.read_bytes()).hexdigest()!='7f910284d9c7dc26d3c443183fdda33c78bdd4553036dabc75e38d158f48b616':
        raise InspectionStopped('Reviewed test package changed.')
    with zipfile.ZipFile(package) as files:
        manifest=json.loads(files.read('manifest.json')); assets=[files.read(a['file']) for a in manifest['assets']]
    matched=media_comparison(frame,assets,'carousel_editor')
    if (matched.get('status')!='visual_match' or matched.get('matchedIndex') is None
            or matched.get('position',{}).get('index')!=matched['matchedIndex']
            or matched['position'].get('count')!=len(assets)):
        raise InspectionStopped('Source image, page order or count did not match the test carousel.')
    return matched


class StepKernel(IMouseKernel):
    def __init__(self, url, transport=None):
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
            if fun not in ('/input/acquire','/input/renew','/input/release','/mouse/reset','/mouse/move','/mouse/click','/mouse/swipe'):
                raise KernelSafetyError('This probe cannot send that command.')
            if data.get('id') != LIVE_TEST_DEVICE_ID:
                raise KernelSafetyError('Only C24C is accepted.')
            if transport is not None: return transport(method,target,body,timeout)
            request=urllib.request.Request(target,data=json.dumps(body).encode('utf-8'),method=method,
                headers={'Content-Type':'application/json'})
            with opener.open(request,timeout=min(timeout,8)) as response:
                raw=response.read(1024*1024+1)
                if len(raw)>1024*1024: raise KernelSafetyError('Candidate response exceeds the evidence limit.')
                return raw,dict(response.headers)
        self._transport=limited
        self.devices=reader.devices


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('label')
    p.add_argument('--review',type=Path,required=True)
    p.add_argument('--action',choices=('refresh','tap','next_slide','previous_slide'),required=True)
    p.add_argument('--intent',required=True,choices=('frame_challenge','profile_create','choose_post_format','open_drafts',
        'open_test_draft','details','back_to_editor','request_save','save_draft','leave_picker','view_profile','inspect_slide'))
    p.add_argument('--point',type=int,nargs=2)
    args=p.parse_args()
    if not args.label.replace('-','').isalnum(): p.error('Use a unique simple label.')
    if args.action=='tap' and args.point is None: p.error('A reviewed tap needs a point.')
    preparation=json.loads((RUN/'preparation.json').read_text(encoding='utf-8'))
    expected=preparation['validation']['build']['sha256']
    assert hashlib.sha256(Path(preparation['kernel']).with_suffix('.dll').read_bytes()).hexdigest()==expected
    baseline=args.review.read_bytes()
    baseline_text=WindowsOcr().read(baseline)
    folder=RUN/args.label
    folder.mkdir(exist_ok=False)
    (folder/'reviewed.png').write_bytes(baseline)
    record=dict(source='agent_supervised_phone',action=args.action,intent=args.intent,point=args.point,
        commands=[],captures=[],cleanup='not_needed',state='not_sent',savedDraftVerified=False,
        automaticInputAllowed=False,reviewFrameSha256=hashlib.sha256(baseline).hexdigest())
    def save(): (folder/'record.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    kernel=StepKernel(preparation['arguments'][0].rstrip('/'))
    store=ObservationStore(folder/'observations.sqlite3')
    owned=OwnedCaptureRun(kernel,str(uuid.uuid4()),threading.Event())
    def runtime():
        return validate_runtime(kernel.kernel_status(),kernel.devices(),expected,preparation['expectedUid'])
    def command(fun,*,basis=None,**data):
        owned.check(kernel)
        if runtime()!=identity: raise InspectionStopped('Kernel identity changed.')
        if basis is not None and store.get(basis)['freshness']!='recent':
            raise InspectionStopped('Decision frame expired at the final dispatch check.')
        item=dict(fun=fun,data=data,state='outcome_unknown');record['commands'].append(item);save()
        item['response']=kernel.send('C24C',owned.tokens['C24C'],fun,**data)
        item['state']='answered';save()
    def capture(name):
        request=dict(id=str(uuid.uuid4()),device_id='C24C',platform='instagram',account='xs.halle.xo')
        store.capture(request,kernel,owned_run=owned)
        value,frame=store.evidence(request['id']);(folder/(name+'.png')).write_bytes(frame)
        current=store.get(request['id'])
        record['captures'].append(dict(name=name,observation=current));save()
        if (current['freshness']!='recent' or not current.get('stable') or not current.get('inputSettled')
            or not current.get('frameEvidence',{}).get('pairedMetadata')):
            raise InspectionStopped('No recent settled paired frame after the pointer challenge.')
        if current.get('result',{}).get('screen') in ('permission_prompt','share_sheet','sharing_dialog'):
            if not (current['result']['screen']=='sharing_dialog' and args.intent=='save_draft' and save_prompt(current['text'])):
                raise InspectionStopped('A dialog requires a separate review.')
        return current,frame
    def second_frame(first, image, name):
        # Move only inside the fixed preview to provoke a new delivery on quiet
        # screens. Freshness and each OCR result still have to pass independently.
        command('/mouse/move',x=450,y=300)
        time.sleep(.12)
        second, raw=capture(name)
        result=fresh_pair(first,image,second,raw)
        record.setdefault('framePairs',[]).append(result);save()
        return second,raw
    try:
        identity=runtime()
        state=kernel.input_status().get(LIVE_TEST_DEVICE_ID)
        if not idle(state): raise InspectionStopped('Another controller or paused state prevents this step.')
        raw,headers=kernel.shot('C24C')
        # Quiet source permitted ONLY for a move-only challenge, never a click.
        with Image.open(io.BytesIO(raw)) as image:
            image.save(folder/'before.png')
        record['preflightReview']=same_reviewed_page(baseline,raw,
            before_text=baseline_text,after_text=WindowsOcr().read(raw))
        before=kernel.kernel_status()['receivers'][0]
        if (before.get('frame_pipe_connected') is not True or before.get('frame_delivery') not in ('flowing','quiet')
                or not before.get('frame_session') or headers.get('X-iMouse-Frame-Session')!=before['frame_session']):
            raise InspectionStopped('No consistent connected stream for the move-only challenge.')
        record['cleanup']='unconfirmed';save();owned.acquire()
        command('/mouse/reset')
        command('/mouse/move',x=480,y=300)
        time.sleep(.12)
        fresh,frame=capture('fresh')
        if fresh['frameEvidence']['sequence']<=before['frames']:
            raise InspectionStopped('Pointer challenge produced no new receiver frame.')
        record['freshReview']=same_reviewed_page(baseline,frame,
            before_text=baseline_text,after_text=fresh['text'])
        if args.action=='refresh':
            command('/mouse/move',x=450,y=300)
            time.sleep(.12)
            current,_=capture('after')
            time.sleep(1.7)
            aged=store.get(current['id'])
            record['retainedExpiry']=dict(freshness=aged['freshness'],frameEvidence=aged['frameEvidence'],recaptured=False)
            if aged['freshness']=='recent': raise InspectionStopped('Retained frame failed to expire.')
        else:
            if fresh['result'].get('layout')=='post_media_picker':
                fresh,frame=second_frame(fresh,frame,'picker-decision')
            if args.action=='tap': allowed_tap(fresh['text'],*args.point,args.intent,frame=frame)
            else:
                record['sourceSlideEvidence']=verified_slide(frame,fresh);save()
            owned.check(kernel)
            if store.get(fresh['id'])['freshness']!='recent': raise InspectionStopped('Decision frame expired before dispatch.')
            record['state']='outcome_unknown';save()
            if args.action=='tap': command('/mouse/click',basis=fresh['id'],x=args.point[0],y=args.point[1],button=1)
            else:
                x1,x2=(400,100) if args.action=='next_slide' else (100,400)
                command('/mouse/swipe',basis=fresh['id'],x1=x1,y1=480,x2=x2,y2=480,duration=350)
            record['state']='answered';save()
            time.sleep(.65)
            command('/mouse/move',x=480,y=300)
            time.sleep(.12)
            current,image=capture('after-first')
            second_frame(current,image,'after')
        record['state']='observed'
    except Exception as exc:
        record.update(error=str(exc),state='review_required')
    finally:
        try:
            if owned.tokens: owned.release();record['cleanup']='confirmed'
            record['finalInput']=kernel.input_status().get(LIVE_TEST_DEVICE_ID)
        except Exception as exc: record.update(cleanup='unconfirmed',cleanupError=str(exc))
        save()
    print(json.dumps(dict(state=record['state'],error=record.get('error'),cleanup=record['cleanup'],folder=str(folder))))
    return 0 if record['state']=='observed' and record['cleanup']=='confirmed' else 2


if __name__=='__main__': raise SystemExit(main())
