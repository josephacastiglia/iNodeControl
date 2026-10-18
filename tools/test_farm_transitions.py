import copy
import hashlib
import io
import unittest
import uuid

from PIL import Image, ImageDraw

from farm_carousel_inspection import InspectionStopped
from farm_observations import classify
from farm_screen_layout import create_menu_controls
from farm_transitions import wait_for_transition
from test_farm_screen_layout import screen, encoded, changed, crop_proof


def create_sheet():
    image=Image.new('RGB',(500,1080),'#555555')
    image.paste('white',(0,466,500,1080)); draw=ImageDraw.Draw(image)
    entries=[('Create',219,516,62),('Edits',70,621,41),('Post',70,675,37),
             ('Story',69,728,46),('Instants',70,781,67),('Highlights',70,833,86),
             ('Live',70,886,33),('Fundraiser',70,939,91)]
    rows=[]
    for label,x,y,width in entries:
        draw.text((x,y),label,fill='black')
        rows.append(dict(text=label,words=[dict(text=label,x=x,y=y,width=width,height=15)]))
    raw=encoded(image)
    return raw,dict(width=500,height=1080,lines=rows,frameSha256=hashlib.sha256(raw).hexdigest())


class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.now=0.; self.events=[]; self.captures=[]; self.cancelled=False
        self.expected=dict(device_id='C24C',platform='instagram',account='test.account',caption='Exact caption')
        self.assets=[]
        for colour in ('navy','teal','purple'):
            image=Image.new('RGB',(500,625),colour); draw=ImageDraw.Draw(image)
            draw.rectangle((50,70,400,150),fill='white'); draw.rectangle((100,250,180,550),fill='orange')
            self.assets.append(encoded(image))

    def editor(self, header=False):
        raw,text=screen('editor')
        with Image.open(io.BytesIO(raw)) as image, Image.open(io.BytesIO(self.assets[0])) as asset:
            image.paste(asset,(0,164))
            if header: ImageDraw.Draw(image).rounded_rectangle((123,65,376,132),radius=30,fill='#888888')
            raw=encoded(image)
        text['frameSha256']=hashlib.sha256(raw).hexdigest(); crop_proof(raw,text)
        return raw,text

    def observation(self, raw, text, sequence):
        return dict(id=str(uuid.uuid4()),state='observed',freshness='recent',expired=False,stable=True,inputSettled=True,
            expected=dict(self.expected),observerSession='observer',resolvedDeviceId='C24C',receiverPid=10,inputGeneration=3,
            source='simulation',ownershipEvidence=dict(runId='run',generation=3,authenticatedBeforeAndAfter=True,
                source='owned_capture_guard',continuousPhoneActivityKnown=False),
            frameEvidence=dict(pairedMetadata=True,session='stream',sequence=sequence),
            frameSha256=hashlib.sha256(raw).hexdigest(),reviewFrameSha256=hashlib.sha256(raw).hexdigest(),
            evidenceRecordSha256='immutable-'+str(sequence),text=text)

    def run_wait(self, frames, stage='picker', mutate=None, final=None, capture_delay=.1, pause=None, **kwargs):
        iterator=iter(frames); current={}
        def capture():
            self.now+=capture_delay
            raw,text=copy.deepcopy(next(iterator)); text['frameSha256']=hashlib.sha256(raw).hexdigest()
            value=self.observation(raw,text,len(self.captures)+1)
            if mutate: mutate(value,len(self.captures)+1)
            current[value['id']]=(value,raw); self.captures.append(value)
            return value,raw
        def check():
            if self.cancelled: raise InspectionStopped('Cancelled')
        def latest(key):
            value,raw=copy.deepcopy(current[key])
            if final: final(value)
            return value,raw
        def sleep(seconds):
            self.now+=seconds
            if pause: pause()
        return wait_for_transition(stage,capture,check,latest,assets=self.assets,index=1,
            journal=self.events.append,monotonic=lambda:self.now,pause=sleep,**kwargs)

    def test_create_sheet_takes_precedence_over_background_profile_and_account(self):
        raw,text=create_sheet()
        for label in ('Edit profile','Share profile','Posts','Following','test.account'):
            text['lines'].append(dict(text=label,words=[dict(text=label,x=20,y=200,width=100,height=14)]))
        result=classify(text,self.expected,raw)
        self.assertEqual('create_menu',result['screen']); self.assertEqual('not_visible',result['accountStatus'])
        value,_,result=self.run_wait([(raw,text)]*2,stage='create')
        self.assertEqual('ready',result['state']); self.assertFalse(result['automaticInputAllowed'])

    def test_create_needs_every_exact_positioned_anchor_and_light_sheet(self):
        raw,text=create_sheet()
        self.assertIsNotNone(create_menu_controls(raw,text))
        for index in range(len(text['lines'])):
            bad=copy.deepcopy(text); bad['lines'].pop(index)
            with self.subTest(missing=index): self.assertIsNone(create_menu_controls(raw,bad))
        bad=copy.deepcopy(text); bad['lines'][2]['words'][0]['y']=80
        self.assertIsNone(create_menu_controls(raw,bad))
        duplicate=copy.deepcopy(text); duplicate['lines'].append(duplicate['lines'][2])
        self.assertIsNone(create_menu_controls(raw,duplicate))
        self.assertIsNone(create_menu_controls(changed(raw,(200,600,300,900),'black'),text))

    def test_indicator_fade_waits_then_uses_new_stable_pair_without_ignoring_indicator(self):
        raw,text=screen(); bright=changed(raw,(161,1064,338,1070),'white')
        dim=changed(raw,(161,1064,338,1070),'#555555')
        value,_,result=self.run_wait([(bright,text),(dim,text),(dim,text)])
        self.assertEqual(3,len(self.captures)); self.assertEqual('ready',result['state'])
        self.assertEqual(value['id'],self.captures[-1]['id'])
        self.assertIn('fading',self.events[1]['reason'])
        self.assertTrue(result['controlsStable']); self.assertEqual(0,result['worstProtectedBlock'])

    def test_continuing_indicator_changes_hit_capture_bound(self):
        raw,text=screen(); bright=changed(raw,(161,1064,338,1070),'white')
        with self.assertRaisesRegex(InspectionStopped,'four captures'):
            self.run_wait([(raw,text),(bright,text)]*2)
        self.assertEqual(4,len(self.captures)); self.assertEqual('held',self.events[-1]['state'])

    def test_control_or_library_change_cannot_be_waited_away(self):
        raw,text=screen()
        for box in ((435,80,440,85),(140,700,180,740)):
            with self.subTest(box=box),self.assertRaisesRegex(InspectionStopped,'outside the indicator'):
                self.run_wait([(raw,text),(changed(raw,box,'white'),text),(raw,text)])

    def test_audio_header_loading_waits_for_strict_whole_editor_stability(self):
        empty=self.editor(); loaded=self.editor(True)
        value,_,result=self.run_wait([empty,loaded,loaded],stage='editor',require_next=True)
        self.assertEqual(3,len(self.captures)); self.assertEqual('ready',result['state'])
        self.assertIn('header',self.events[1]['reason']); self.assertEqual(0,result['mean'])

    def test_wrong_slide_or_page_count_stops_before_later_matching_frame(self):
        raw,text=self.editor()
        with Image.open(io.BytesIO(raw)) as image,Image.open(io.BytesIO(self.assets[1])) as wrong:
            image.paste(wrong,(0,164)); other=encoded(image)
        for bad in (other,changed(raw,(235,836,241,842),'#555555')):
            with self.subTest(case=hashlib.sha256(bad).hexdigest()),self.assertRaises(InspectionStopped):
                self.run_wait([(raw,text),(bad,text),(raw,text)],stage='editor')

    def test_tiny_editor_action_change_is_not_diluted_by_full_screen_average(self):
        raw,text=self.editor()
        with self.assertRaisesRegex(InspectionStopped,'action controls'):
            self.run_wait([(raw,text),(changed(raw,(355,900,359,904),'white'),text)],stage='editor')

    def test_missing_or_old_next_proof_is_not_repaired_or_retried(self):
        raw,text=self.editor()
        missing=copy.deepcopy(text); missing.pop('controlOcr')
        old=copy.deepcopy(text); old['controlOcr']['next']['bounds']=[396,980,478,1032]
        for bad in (missing,old):
            with self.assertRaisesRegex(InspectionStopped,'Next label'):
                self.run_wait([(raw,bad)]*3,stage='editor',require_next=True)

    def test_dialog_or_missing_controls_stop_even_if_next_frame_would_match(self):
        for stage,fixture in (('picker',screen()),('editor',self.editor()),('create',create_sheet())):
            raw,text=fixture; bad=copy.deepcopy(text)
            bad['lines'].append(dict(text="Don't Allow",words=[dict(text="Don't Allow",x=100,y=600,width=90,height=16)]))
            with self.subTest(stage=stage),self.assertRaisesRegex(InspectionStopped,'dialog'):
                self.run_wait([(raw,text),(raw,bad),(raw,text)],stage=stage)

    def test_freshness_ownership_account_stream_or_duplicate_sequence_interrupts(self):
        for key,value in [('freshness','stale'),('inputSettled',False),('receiverPid',11),
                          ('inputGeneration',4),('observerSession','other'),('source','phone'),('resolvedDeviceId','C241')]:
            def mutate(v,n):
                if n%2==0: v[key]=value
            self.captures=[]
            with self.subTest(key=key),self.assertRaises(InspectionStopped):
                self.run_wait([screen()]*3,mutate=mutate)
        for field,key,value in [('expected','account','other.account'),('expected','device_id','C241'),
                                ('frameEvidence','session','new'),('frameEvidence','sequence',1),
                                ('ownershipEvidence','runId','other')]:
            self.captures=[]
            def mutate(v,n):
                if n==2: v[field][key]=value
            with self.subTest(field=field,key=key),self.assertRaises(InspectionStopped):
                self.run_wait([screen()]*3,mutate=mutate)

    def test_cancellation_and_capture_deadline_stop_without_retry(self):
        with self.assertRaisesRegex(InspectionStopped,'Cancelled'):
            self.run_wait([screen()]*3,pause=lambda:setattr(self,'cancelled',True))
        self.cancelled=False; self.captures=[]
        with self.assertRaisesRegex(InspectionStopped,'budget'):
            self.run_wait([screen()]*3,capture_delay=6.1)
        self.assertEqual(1,len(self.captures))

    def test_final_evidence_is_reaged_and_tampering_or_expiry_never_returns_ready(self):
        for field,value in [('freshness','stale'),('evidenceRecordSha256','changed'),('reviewFrameSha256','bad')]:
            with self.subTest(field=field),self.assertRaises(InspectionStopped):
                self.run_wait([screen()]*2,final=lambda v:v.update({field:value}))
        with self.assertRaisesRegex(InspectionStopped,'expired'):
            self.run_wait([screen()]*2,final=lambda v:setattr(self,'now',self.now+7))


if __name__=='__main__': unittest.main()
