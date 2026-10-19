"""Bounded creation of a new C24C carousel, followed by the existing verifier.

Only reviewed navigation, Photos saves, paste and Save draft are available.
Unknown outcomes stop. Long operations have fixed phase and total budgets.
"""
import hashlib
import json
import base64
import io
import threading
from pathlib import Path
import numpy as np
from PIL import Image

from farm_carousel_inspection import OwnedCaptureRun, InspectionStopped
from farm_creation_layout import (require, exact, source_match, picker_grid,
    selected_badges, caption_editor, home, app_target, control, empty_search, test_video_preview, restored_app_search)
from farm_draft_workflow import Workflow, atomic_json, centre, icon_matches
from farm_draft_verification import caption_comparison
from farm_live_verification import idle
from farm_observations import classify
from farm_screen_layout import pixels, words_at, line_at, overlay_present
from imouse_social_automation import LIVE_TEST_DEVICE_ID


class CreationOwnership(OwnedCaptureRun):
    TOTAL_SECONDS = 720
    PHASE_SECONDS = 120

    def __init__(self, *args, **kwargs):
        super().__init__(*args, budget_seconds=120, **kwargs)
        self.started = self.monotonic()
        self.phase_started = self.started
        self.phase = None

    def check_budget(self):
        if self.cancelled.is_set(): raise InspectionStopped('Creation cancelled; no action will be replayed.')
        now=self.monotonic()
        if now-self.started>=self.TOTAL_SECONDS or now-self.phase_started>=self.PHASE_SECONDS:
            raise InspectionStopped('Creation reached its fixed total or phase time limit.')

    def begin_phase(self, name):
        self.check_budget()  # An expired phase cannot grant itself more time.
        self.phase, self.phase_started = name, self.monotonic()


class CreationWorkflow(Workflow):
    def __init__(self, *args, transfer_url, transfer_title, imported_media=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.owned=CreationOwnership(self.kernel,self.owned.run_id,self.cancelled,self.monotonic)
        self.url,self.title=transfer_url,transfer_title
        self.imported_media=imported_media
        self.cells={}; self.selection=[]
        self.record.update(mode='create_new_draft',budgetSeconds=720,phaseBudgetSeconds=120,
            phases=[],createdDraftVerified=False,captionMethod='verified_safari_copy_and_instagram_paste')
        if imported_media: self.record['importedMedia']=imported_media

    def check_import_continuity(self,state):
        if not self.imported_media:return
        receiver=self.kernel.kernel_status()['receivers'][0]
        require(idle(state) and state['generation']==self.imported_media['generation']
            and receiver.get('receiver_pid')==self.imported_media['receiverPid']
            and receiver.get('frame_session')==self.imported_media['frameSession'],
            'Phone ownership or receiver changed after import. Review the imported media without replaying it.')

    def import_picker_close(self,value,frame):
        icon_matches(frame,self.templates['picker_saved'],(19,66,58,105))
        return 39,84

    def phase(self,name):
        self.owned.begin_phase(name)
        self.record['phases'].append(dict(name=name,started=self.monotonic()))
        self.save()

    def verify_screen(self,role,value,frame,index=None,require_next=False):
        text=value['text']
        if role=='account_entry' and value['result'].get('screen')=='profile':
            return super().verify_screen('profile',value,frame)
        if role in ('profile','create','editor','picker','library','details','save_prompt'):
            return super().verify_screen(role,value,frame,index,require_next)
        if role=='selected_images':
            # Cancel is the explicitly recognized multi-selection control here,
            # not permission to ignore another modal over the picker.
            checked={**text,'lines':[r for r in text.get('lines',[]) if not (r.get('text','').casefold() in ('cancel','o cancel')
                and r.get('words') and 620<min(w['y'] for w in r['words'])<670)]}
        else: checked=text
        require(not overlay_present(checked), 'An unexpected overlay interrupts creation.')
        if role in ('instagram_navigation','account_entry'):
            for name in ('instagram_logo','feed_home','feed_reels','feed_search'):control(frame,name)
            return dict(navigation='instagram_feed',accountVerified=False)
        if role=='media_preview':return test_video_preview(text)
        if role=='safari_entry':
            try:return self.verify_screen('safari',value,frame)
            except InspectionStopped:return test_video_preview(text)
        if role=='home': return home(text,frame)
        if role=='search':
            empty_search(text,frame); return dict(field='empty_app_search',proof='same_frame_placeholder_glyphs_with_fixed_caret_exclusion')
        if role=='restored_search':return restored_app_search(text)
        if role=='app_result':return dict(target=app_target(text,self.search_app,frame))
        if role=='app_search_entry':
            try:return dict(empty=empty_search(text,frame))
            except InspectionStopped:
                control(frame,'search_clear')
                return restored_app_search(text)
        if role=='search_after_escape':
            try:return dict(home=home(text,frame))
            except InspectionStopped:return dict(emptySearch=empty_search(text,frame))
        if role=='safari':
            # Browser chrome, independent of web content. Read-only navigation.
            image=pixels(frame,exact=True)
            rows=json.loads(Path(__file__).with_name('farm_creation_browser.json').read_text(encoding='utf-8'))
            for row in rows:
                raw=base64.b64decode(row['png'],validate=True)
                require(hashlib.sha256(raw).hexdigest()==row['sha256'], 'Browser reference is damaged.')
                left,top,right,bottom=row['box']
                with Image.open(io.BytesIO(raw)) as reference:
                    delta=np.abs(image[top:bottom,left:right].astype(float)-np.asarray(reference.convert('RGB')).astype(float))/255
                require(delta.mean()<.025, 'Safari navigation chrome changed.')
            return dict(browser='safari')
        if role=='address_selected':
            image=pixels(frame,exact=True)
            selected=image[940:972,30:385].astype(int)
            require(((selected[:,:,2]-selected[:,:,0]>15)&(selected[:,:,2]>200)).mean()>.15,
                    'Safari address is not visibly selected; existing text will not be overwritten blindly.')
            require((image[1066:1069,170:330].max(axis=2)<90).mean()>.85, 'Address field geometry changed.')
            return dict(addressSelected=True)
        if role=='transfer_home':
            exact(text,self.title,(10,65,490,170))
            exact(text,'Open slide 1 of 3',(60,210,440,370))
            exact(text,'Open slide 2 of 3',(60,310,440,445))
            exact(text,'Open slide 3 of 3',(60,390,440,520))
            return dict(packageSha256=self.package_hash)
        if role=='transfer_slide':
            exact(text,'Slide %d of 3'%index,(10,65,490,140))
            comparison=source_match(frame,self.assets[index-1],(23,248,477,819))
            require(comparison['matched'], 'Transfer image does not match this saved slide.')
            return comparison
        if role=='photo_save_menu':
            exact(text,'Save to Photos',(100,745,405,810))
            exact(text,'Copy',(100,805,405,865))
            comparison=source_match(frame,self.assets[index-1],(25,111,475,674))
            require(comparison['matched'], 'The Photos context menu belongs to a different image.')
            return comparison
        if role in ('transfer_caption','caption_copied'):
            exact(text,'Copy caption',(15,450,485,850))
            if role=='caption_copied':
                rows=' '.join(r['text'] for r in text.get('lines',[]) if r.get('words')
                              and 500<min(w['y'] for w in r['words'])<925)
                require('Caption copied. Verify the pasted text in Instagram.' in rows,
                        'The transfer page did not confirm copying. No paste is permitted.')
            return dict(packageSha256=self.package_hash)
        if role=='transfer_return':
            if line_at(text,'copy caption',(15,450,485,850)):
                return self.verify_screen('transfer_caption',value,frame)
            return self.verify_screen('transfer_home',value,frame)
        if role in ('select_images','selected_images'):
            self.cells=picker_grid(frame,text,self.assets,self.selection)
            return dict(cells=self.cells,selected=selected_badges(frame,text,self.cells,self.selection) if self.selection else {})
        if role=='details_blank':
            require(value['result'].get('layout')=='carousel_details', 'New post details are not recognized.')
            control(frame,'details_empty_caption')
            require(source_match(frame,self.assets[0],(20,126,260,426))['matched'], 'Details show different media.')
            return dict(emptyCaption=True)
        if role in ('caption_blank','paste_menu','caption_filled'):
            caption_editor(text,self.caption if role=='caption_filled' else None,frame)
            if role!='caption_filled': control(frame,'empty_caption')
            if role=='paste_menu': exact(text,'Paste',(20,420,115,475))
            return dict(captionExact=role=='caption_filled')
        raise InspectionStopped('Unsupported creation screen: '+role)

    def step(self,label,role,*,index=None,point=None,hold=False,key=None,text=None,swipe=None):
        require(not any(a['label']==label for a in self.record['actions']), 'Creation action cannot be replayed.')
        value,frame=self.observe(role,index)
        if callable(point): point=point(value,frame)
        row=dict(label=label,kind=role,observationId=value['id'],state='not_sent')
        self.record['actions'].append(row);self.save()
        start=len(self.record['commands'])
        try:
            if point:
                x,y=point
                require(10<=x<=490 and 65<=y<=1035, 'Creation target leaves the reviewed phone area.')
                if hold:
                    self.command('/mouse/move',basis=value,purpose=label+'-position',x=x,y=y)
                    # A press follows the same recognized image/empty caption,
                    # with no unrelated phone command in between.
                    self.pause(.6)
                    self.command('/mouse/down',purpose=label+'-press',button=1)
                    self.pause(1.1)
                    self.command('/mouse/up',purpose=label+'-release',button=1)
                else: self.command('/mouse/click',basis=value,purpose=label,x=x,y=y,button=1)
            elif key:
                self.command('/key/sendkey',basis=value,purpose=label,fn_key=key)
            elif text is not None:
                require(text and all(33<=ord(c)<=126 for c in text) and len(text)<=120,
                        'Only bounded URL/app search text without spaces is permitted. Captions use Paste.')
                # One bounded, contiguous input sequence, never retried. The
                # first dispatch is bound to the recognized selected/empty field.
                for offset in range(0,len(text),12):
                    self.command('/key/sendkey',basis=value if offset==0 else None,
                        purpose=label+'-'+str(offset),key=text[offset:offset+12])
            elif swipe:
                self.command('/mouse/swipe',basis=value,purpose=label,**swipe)
            else: raise InspectionStopped('Creation action has no reviewed implementation.')
            row['state']='answered';self.save()
            self.command('/mouse/move',purpose='park_after_answered_action',x=480,y=300)
            self.pause(.7)
        except BaseException as error:
            sent=self.record['commands'][start:]
            row.update(state=sent[-1]['state'] if sent else 'not_sent',reason=str(error));self.save();raise

    def open_app(self,name,visit):
        self.search_app=name
        value,frame=self.observe('home')
        try: point=app_target(value['text'],name,frame)
        except InspectionStopped: point=None
        if point:
            self.step(visit+'-open-'+name,'home',point=lambda v,f:app_target(v['text'],name,f));return
        self.step(visit+'-search-'+name,'home',point=lambda v,f:centre(control(f,'home_search')))
        value,frame=self.observe('app_search_entry')
        try:app_target(value['text'],name,frame);desired=True
        except InspectionStopped:desired=False
        if not desired:
            try:empty_search(value['text'],frame);empty=True
            except InspectionStopped:empty=False
            if not empty:
                self.step(visit+'-clear-restored-search','restored_search',point=lambda v,f:centre(control(f,'search_clear')))
            self.step(visit+'-query-'+name,'search',text=name)
        self.step(visit+'-open-'+name,'app_result',point=lambda v,f:app_target(v['text'],name,f))

    def account_profile(self,label):
        value,_=self.observe('account_entry')
        if value['result'].get('screen')!='profile':
            self.step(label,'instagram_navigation',point=(447,1008))
        self.observe('profile')

    def run(self):
        try:
            self.identity=self.runtime()
            state=self.kernel.input_status().get(LIVE_TEST_DEVICE_ID)
            require(idle(state), 'C24C is not free.')
            self.check_import_continuity(state)
            raw,_=self.kernel.shot('C24C');initial_text=self.store.ocr.read(raw);initial=classify(initial_text,
                dict(platform='instagram',account=self.account,caption=self.caption),raw)
            initial_profile=initial['screen']=='profile' and initial['accountStatus']=='exact_text_match'
            initial_home=initial_search=initial_results=initial_media=False
            initial_picker=False
            initial_transfer=0
            if self.imported_media:
                # Only close a recognized, unedited picker. No editor, account
                # switch, permission dialog or uncertain Save can be resumed.
                self.selection=list(self.imported_media.get('selection',[]))
                cells=picker_grid(raw,initial_text,self.assets,self.selection)
                if self.selection:selected_badges(raw,initial_text,cells,self.selection)
                initial_picker=True
            if not initial_profile and not initial_picker:
                try:home(initial_text,raw);initial_home=True
                except InspectionStopped:
                    try:
                        for name in ('instagram_logo','feed_home','feed_reels','feed_search'):control(raw,name)
                    except InspectionStopped:
                        try:empty_search(initial_text,raw);initial_search=True
                        except InspectionStopped:
                            try:restored_app_search(initial_text);initial_results=True
                            except InspectionStopped:
                                try:test_video_preview(initial_text);initial_media=True
                                except InspectionStopped:
                                    for number in (1,2,3):
                                        try:self.verify_screen('transfer_slide',dict(text=initial_text,result={}),raw,number);initial_transfer=number;break
                                        except InspectionStopped:pass
                                    require(initial_transfer,'Start on a supported read-only entry screen or the authorized profile.')
            self.record['cleanup']='unconfirmed';self.save();self.owned.acquire()
            if self.imported_media:
                # Acquisition retains the free slot's generation; release or
                # revocation advances it. Do not invent an acquire increment.
                require(self.owned.generation==self.imported_media['generation']
                    and self.owned.stream[1]==self.imported_media['receiverPid']
                    and self.owned.stream[3]==self.imported_media['frameSession'],
                    'The imported-media ownership checkpoint changed before acquisition.')
            self.command('/mouse/reset',purpose='initial_pointer_reset')
            self.phase('open-transfer')
            if initial_picker:
                self.step('close-unedited-import-picker','selected_images' if self.selection else 'select_images',point=self.import_picker_close)
                self.selection=[]
                self.observe('profile');initial_profile=True
            if not initial_profile:
                if initial_transfer:
                    self.step('home-from-retained-transfer-slide','transfer_slide',index=initial_transfer,key='Home')
                    initial_home=True
                if initial_results:
                    self.step('dismiss-restored-app-search','restored_search',key='Escape')
                    after,after_frame=self.observe('search_after_escape')
                    try:home(after['text'],after_frame);initial_home=True
                    except InspectionStopped:initial_search=True
                if initial_media:
                    self.step('home-from-readonly-test-preview','media_preview',key='Home')
                    initial_home=True
                if initial_search:
                    self.step('dismiss-empty-ios-search','search',key='Escape')
                    initial_home=True
                if initial_home:self.open_app('Instagram','initial')
                self.account_profile('verify-launch-account')
            self.step('home-from-profile','profile',key='Home')
            self.open_app('Safari','transfer')
            entry,_=self.observe('safari_entry')
            try:test_video_preview(entry['text']);preview=True
            except InspectionStopped:preview=False
            if preview:
                self.step('close-readonly-safari-test-preview','media_preview',point=lambda v,f:centre(exact(v['text'],'Done',(405,65,495,110))))
            self.step('focus-safari-address','safari',point=(245,953))
            self.step('enter-transfer-url','address_selected',text=self.url)
            # Field is no longer selected, but must still be the same Safari
            # address edit session before Enter. It is never sent as a caption.
            self.command('/key/sendkey',purpose='load-transfer-url',fn_key='Enter')
            self.pause(1)
            if not self.imported_media:
                self.step('open-slide-1','transfer_home',point=lambda v,f:centre(exact(v['text'],'Open slide 1 of 3',(60,210,440,370))))
                for number in range(1,4):
                    self.phase('save-slide-'+str(number))
                    self.step('focus-transfer-image-'+str(number),'transfer_slide',index=number,point=(245,480))
                    self.step('image-menu-'+str(number),'transfer_slide',index=number,point=(245,480),hold=True)
                    self.step('save-photo-'+str(number),'photo_save_menu',index=number,
                        point=lambda v,f:centre(exact(v['text'],'Save to Photos',(100,745,405,810))))
                    label='Back to caption' if number==3 else 'Next slide'
                    self.step('next-transfer-'+str(number),'transfer_slide',index=number,
                        point=lambda v,f:centre(exact(v['text'],label,(30,825,470,920))))
            self.phase('copy-caption-and-open-instagram')
            # The caption route returns near the copy button on the observed
            # page. If it is off screen, a single read-only scroll is allowed.
            value,_=self.capture('transfer_return')
            if not line_at(value['text'],'copy caption',(15,450,485,850)):
                self.step('scroll-transfer-caption','transfer_home',swipe=dict(x1=480,y1=830,x2=480,y2=430,duration=400))
            self.step('copy-caption','transfer_caption',point=lambda v,f:centre(exact(v['text'],'Copy caption',(15,450,485,850))))
            self.step('home-from-readonly-transfer','caption_copied',key='Home')
            self.open_app('Instagram','return')
            self.account_profile('verify-returned-account')
            self.phase('select-new-media')
            self.action('open-create','profile_create','profile')
            self.action('choose-post-format','choose_post_format','create')
            self.step('preview-first-slide','select_images',point=lambda v,f:(self.cells[1][1]*125+62,677+self.cells[1][0]*125+62))
            self.step('enable-multiple-selection','select_images',point=lambda v,f:centre(control(f,'select')))
            self.selection=[1];self.observe('selected_images')
            for number in (2,3):
                self.step('select-slide-'+str(number),'selected_images',point=lambda v,f,n=number:(self.cells[n][1]*125+62,677+self.cells[n][0]*125+62))
                self.selection.append(number);self.observe('selected_images')
            self.step('open-new-carousel-editor','selected_images',point=lambda v,f:centre(exact(v['text'],'Next',(420,65,495,110))))
            self.phase('paste-and-save-new-draft')
            for index in (1,2): self.action('prepared-slide-'+str(index+1),'next_slide','editor',index)
            self.action('prepared-details','details','editor',3)
            self.step('focus-empty-caption','details_blank',point=lambda v,f:centre(control(f,'details_empty_caption')))
            self.step('open-paste-menu','caption_blank',point=(50,502),hold=True)
            self.step('paste-exact-caption','paste_menu',point=lambda v,f:centre(exact(v['text'],'Paste',(20,420,115,475))))
            self.pause(2)  # Let the OS paste toast leave the Caption header; no action is repeated.
            self.step('confirm-pasted-caption','caption_filled',point=lambda v,f:centre(control(f,'ok')))
            self.observe('details')
            self.action('prepared-back','back_to_editor','details')
            self.action('prepared-exit-sheet','request_save','editor',3)
            self.action('prepared-save-once','save_draft','save_prompt')
            self.action('return-profile','leave_picker','picker');self.observe('profile')
            self.record.update(state='created_unverified',meaning='New media selected and caption pasted; saved candidate requires independent reopen verification.')
        except BaseException as error:
            self.record.update(state='review_required',error=type(error).__name__+': '+str(error))
        finally: self.finish()
        return self.record
