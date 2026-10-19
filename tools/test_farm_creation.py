"""Offline new-draft admission, visual checks and no-replay regressions."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

from PIL import Image,ImageDraw
from farm_creation_layout import source_match, selected_badges, caption_editor, control, empty_search, test_video_preview
from farm_carousel_inspection import InspectionStopped
from farm_creation_runs import CreationRuns, creation_config
from farm_draft_creation import CreationOwnership, CreationWorkflow
from farm_draft_transport import CreationKernel, StepKernel
from farm_draft_runs import API,source_content
from farm_drafts import CarouselDrafts,DraftConflict
from farm_draft_workflow import atomic_json
from farm_jobs import FarmJobs
from imouse_social_automation import LIVE_TEST_DEVICE_ID,KernelSafetyError

CONFIG=dict(version=1,api=API,kernelSha256='a'*64,expectedUid='test-only',
    mediaBind='192.168.50.2',mediaClient='192.168.50.3',mediaPort=9917)


def png(image):
    out=io.BytesIO();image.save(out,'PNG');return out.getvalue()


def word(label,x,y,w=80):
    return dict(text=label,words=[dict(text=label,x=x,y=y,width=w,height=18)])


class FixtureCreation(CreationRuns):
    executions=0
    def execute(self,folder,assets,caption,package_hash,cancelled):
        self.executions+=1
        result=dict(packageSha256=package_hash,state='review_required',source='offline_protocol_fixture',
            cleanup='confirmed',savedDraftVerified=False,evidenceExport='confirmed',
            actions=[dict(label='save-photo-1',state='outcome_unknown')],observations=[],error='Import reply lost.')
        atomic_json(folder/'record.json',result);return result


class CreationTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='farm-creation-test-');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.drafts=CarouselDrafts(self.root/'drafts.db',self.root/'stage')
        self.draft=self.drafts.create(str(uuid.uuid4()),'Fresh carousel test')
        self.assets=[]
        for i,color in enumerate(('#154b81','#208345','#8d2580'),1):
            image=Image.new('RGB',(1080,1350),color);draw=ImageDraw.Draw(image)
            draw.rectangle((90+i*90,300,400+i*90,900),fill='white')
            self.assets.append(png(image))
            self.draft=self.drafts.import_image(self.draft['id'],self.draft['revision'],str(i)+'.png',base64.b64encode(self.assets[-1]).decode())
        self.draft=self.drafts.save(self.draft['id'],self.draft['revision'],self.draft['title'],
            'New carousel draft\nFresh slides in order\nDraft only',self.draft['slideIds'])
        self.jobs=FarmJobs(journal_path=self.root/'jobs.db');self.addCleanup(self.jobs.close)
        self.service=FixtureCreation(self.root/'runs',self.drafts,self.jobs,CONFIG)
        self.spec=dict(id=str(uuid.uuid4()),draft_id=self.draft['id'],revision=self.draft['revision'],store_id=self.service.store_id)

    def wait(self):
        end=time.monotonic()+3
        while time.monotonic()<end:
            result=self.service.get(self.spec['id'])
            if result['terminal']: return result
            time.sleep(.01)
        self.fail('Fixture did not finish.')

    def test_creation_is_disabled_without_its_separate_configuration(self):
        service=CreationRuns(self.root/'disabled',self.drafts,self.jobs)
        self.assertFalse(service.capability()['enabled'])
        spec=dict(self.spec,store_id=service.store_id)
        with self.assertRaises(KernelSafetyError):service.start(spec)
        self.assertEqual([],service.list(self.draft['id']))

    def test_only_supported_revision_is_eligible_without_truncating_caption(self):
        self.assertTrue(self.service.eligibility(self.draft['id'],self.draft['revision'])['eligible'])
        draft=self.drafts.save(self.draft['id'],self.draft['revision'],self.draft['title'],'a'*51,self.draft['slideIds'])
        self.assertFalse(self.service.eligibility(draft['id'],draft['revision'])['eligible'])
        self.assertEqual('a'*51,self.drafts.get(draft['id'])['caption'])
        with self.assertRaises(DraftConflict):self.service.start(self.spec)

    def test_unknown_import_is_retained_and_same_id_or_restart_never_replays(self):
        self.service.start(self.spec);result=self.wait()
        self.assertFalse(result['savedDraftVerified']);self.assertEqual('review_required',result['state'])
        self.service.start(self.spec);self.assertEqual(1,self.service.executions)
        restarted=FixtureCreation(self.root/'runs',self.drafts,self.jobs,CONFIG)
        restarted.start(self.spec);self.assertEqual(0,restarted.executions)
        self.assertEqual('outcome_unknown',restarted.get(self.spec['id'])['workflow']['actions'][0]['state'])

    def test_a_new_id_cannot_duplicate_the_same_content_after_an_unknown_save(self):
        self.service.start(self.spec);self.wait()
        eligibility=self.service.eligibility(self.draft['id'],self.draft['revision'])
        self.assertFalse(eligibility['eligible']);self.assertEqual(self.spec['id'],eligibility['previousRunId'])
        with self.assertRaises(DraftConflict):self.service.start(dict(self.spec,id=str(uuid.uuid4())))
        self.assertEqual(1,self.service.executions)

    def test_request_cannot_override_account_phone_endpoint_or_action(self):
        for key,value in [('account','another'),('device_id','C241'),('api','http://127.0.0.1:9913/api'),('action','publish')]:
            with self.subTest(key=key),self.assertRaises(ValueError):self.service.start(dict(self.spec,**{key:value}))
        self.assertEqual(0,self.service.executions)

    def test_cancel_before_admission_never_imports(self):
        self.service.cancel(self.spec['id']);self.service.start(self.spec);result=self.wait()
        self.assertEqual(0,self.service.executions);self.assertFalse(result['savedDraftVerified'])

    def test_configuration_refuses_release_endpoints_shared_media_or_other_modes(self):
        path=self.root/'config.json'
        for changes,mode in [({'api':'http://127.0.0.1:9913/api'},'live'),({'mediaBind':'0.0.0.0'},'live'),
            ({'mediaPort':9916},'live'),({'mediaClient':CONFIG['mediaBind']},'live'),({},'simulate')]:
            path.write_text(json.dumps(dict(CONFIG,**changes)),encoding='utf-8')
            with self.subTest(changes=changes),self.assertRaises(ValueError):creation_config(path,mode)
        path.write_text(json.dumps(CONFIG),encoding='utf-8');self.assertEqual(CONFIG,creation_config(path,'live'))

    def test_creation_transport_cannot_send_spaces_large_chunks_or_other_targets(self):
        calls=[]
        def fake(*args):calls.append(args);return b'{}',{}
        client=CreationKernel(API,transport=fake)
        good=dict(id=LIVE_TEST_DEVICE_ID,token='fixture')
        for fun,data in [('/key/sendkey',dict(good,key='Hi there')),('/key/sendkey',dict(good,key='x'*13)),
                         ('/key/sendkey',dict(good,fn_key='AppSwitch')),('/key/sendkey',dict(good,fn_key='Home',key='x')),
                         ('/mouse/click',dict(good,id='C241',x=100,y=100)),('/input/stop',good)]:
            with self.subTest(fun=fun,data=data),self.assertRaises(KernelSafetyError):
                client._transport('POST',API+'/',dict(fun=fun,data=data),8)
        for data in (dict(good,key='Instagram'),dict(good,fn_key='Enter')):
            client._transport('POST',API+'/',dict(fun='/key/sendkey',data=data),8)
        self.assertEqual(2,len(calls))
        old=StepKernel(API,transport=fake)
        with self.assertRaises(KernelSafetyError):old._transport('POST',API+'/',dict(fun='/key/sendkey',data=dict(good,fn_key='Home')),8)

    def test_fixed_phase_and_total_budgets_cannot_be_extended_by_phase_change(self):
        now=[0.0];owner=CreationOwnership(None,'fixture',threading.Event(),lambda:now[0])
        owner.begin_phase('one');now[0]=121
        with self.assertRaises(InspectionStopped):owner.begin_phase('two')
        owner=CreationOwnership(None,'fixture',threading.Event(),lambda:now[0])
        for n in range(6):now[0]+=110;owner.begin_phase(str(n))
        now[0]+=61
        with self.assertRaises(InspectionStopped):owner.check_budget()

    def test_context_menu_image_comparison_rejects_wrong_image_and_crop(self):
        image=Image.new('RGB',(500,1080),'white')
        image.paste(Image.open(io.BytesIO(self.assets[0])).resize((450,563)),(25,111));raw=png(image)
        self.assertTrue(source_match(raw,self.assets[0],(25,111,475,674))['matched'])
        self.assertFalse(source_match(raw,self.assets[1],(25,111,475,674))['matched'])
        self.assertFalse(source_match(raw,self.assets[0],(25,11,475,574))['matched'])

    def test_caption_content_requires_every_exact_line_and_does_not_repair_ocr(self):
        text=dict(width=500,height=1080,lines=[word('Caption',215,76),word('OK',450,77,30),
            word('Poll',58,618,40),word('Prompt',150,618),word('Hi there',20,493)])
        caption_editor(text,'Hi there')
        for wrong in ('Hithere','Hi there\nMissing line','Hi there!'):
            with self.subTest(wrong=wrong),self.assertRaises(InspectionStopped):caption_editor(text,wrong)

    def test_known_selection_glyphs_reject_reordered_or_missing_badges(self):
        references=json.loads(Path(__file__).with_name('farm_creation_badges.json').read_text(encoding='utf-8'))
        image=Image.new('RGB',(500,1080),'black');cells={1:(0,3),2:(0,2),3:(0,1)}
        for number,(row,col) in cells.items():
            crop=Image.open(io.BytesIO(base64.b64decode(references[str(number)]['png'])))
            image.paste(crop,(col*125+93,691))
        raw=png(image);self.assertEqual({1:1,2:2,3:3},selected_badges(raw,{},cells,[1,2,3]))
        with self.assertRaises(InspectionStopped):selected_badges(raw,{},cells,[2,1,3])
        ImageDraw.Draw(image).rectangle((468,691,486,709),fill='black')
        with self.assertRaises(InspectionStopped):selected_badges(png(image),{},cells,[1,2,3])

    def test_bright_empty_selection_ring_is_not_an_extra_numbered_selection(self):
        references=json.loads(Path(__file__).with_name('farm_creation_badges.json').read_text(encoding='utf-8'))
        image=Image.new('RGB',(500,1080),'black');cells={1:(0,3),2:(0,2),3:(0,1)}
        image.paste(Image.open(io.BytesIO(base64.b64decode(references['1']['png']))),(468,691))
        ImageDraw.Draw(image).ellipse((217,690,237,710),fill=(162,149,181),outline='white')
        self.assertEqual({1:1},selected_badges(png(image),{},cells,[1]))
        ImageDraw.Draw(image).rectangle((224,695,228,706),fill='black')
        with self.assertRaises(InspectionStopped):selected_badges(png(image),{},cells,[1])

    def test_reference_control_is_independent_of_ambiguous_ocr_and_rejects_changes(self):
        row=json.loads(Path(__file__).with_name('farm_creation_controls.json').read_text(encoding='utf-8'))['ok']
        image=Image.new('RGB',(500,1080),'white');image.paste(Image.open(io.BytesIO(base64.b64decode(row['png']))),tuple(row['box'][:2]))
        self.assertEqual(row['box'],control(png(image),'ok'))
        ImageDraw.Draw(image).rectangle(row['box'],fill='red')
        with self.assertRaises(InspectionStopped):control(png(image),'ok')

    def test_lost_creation_click_answer_is_unknown_and_is_never_repeated(self):
        workflow=object.__new__(CreationWorkflow)
        workflow.record=dict(actions=[],commands=[]);workflow.save=lambda:None
        workflow.observe=lambda *args:({'id':'fixture'},b'fixture')
        calls=[]
        def lost(fun,**data):
            calls.append(fun);workflow.record['commands'].append(dict(state='outcome_unknown'))
            raise TimeoutError('Click was delivered but reply was lost.')
        workflow.command=lost
        with self.assertRaises(TimeoutError):workflow.step('save-photo-1','photo_save_menu',point=(180,778))
        self.assertEqual(['/mouse/click'],calls)
        self.assertEqual('outcome_unknown',workflow.record['actions'][0]['state'])
        with self.assertRaises(InspectionStopped):workflow.step('save-photo-1','photo_save_menu',point=(180,778))
        self.assertEqual(1,len(calls))

    def test_only_confirmed_preimport_failure_can_offer_an_explicit_new_attempt(self):
        value=dict(terminal=True,state='review_required',workflow=dict(state='review_required',
            source='candidate_phone_workflow',cleanup='confirmed',evidenceExport='confirmed',
            commands=[dict(purpose='home-from-profile',state='answered')],
            actions=[dict(label='home-from-profile',state='answered')]))
        self.assertTrue(CreationRuns.before_import_retry(value))
        for purpose,state in [('save-photo-1','answered'),('save-photo-1','outcome_unknown'),
                              ('home-from-profile','outcome_unknown'),('paste-exact-caption','answered'),('open-new-carousel-editor','answered')]:
            changed=copy.deepcopy(value);changed['workflow']['commands'].append(dict(purpose=purpose,state=state))
            with self.subTest(purpose=purpose,state=state):self.assertFalse(CreationRuns.before_import_retry(changed))
        changed=copy.deepcopy(value);changed['workflow']['cleanup']='unconfirmed'
        self.assertFalse(CreationRuns.before_import_retry(changed))

    def test_feed_navigation_proof_never_establishes_an_account_and_rejects_overlay_pixels(self):
        rows=json.loads(Path(__file__).with_name('farm_creation_controls.json').read_text(encoding='utf-8'))
        image=Image.new('RGB',(500,1080),'white')
        for name in ('instagram_logo','feed_home','feed_reels','feed_search'):
            row=rows[name];image.paste(Image.open(io.BytesIO(base64.b64decode(row['png']))),tuple(row['box'][:2]))
        workflow=object.__new__(CreationWorkflow)
        text=dict(width=500,height=1080,lines=[])
        result=workflow.verify_screen('instagram_navigation',dict(text=text,result={}),png(image))
        self.assertFalse(result['accountVerified'])
        ImageDraw.Draw(image).rectangle(rows['feed_search']['box'],fill='gray')
        with self.assertRaises(InspectionStopped):workflow.verify_screen('instagram_navigation',dict(text=text,result={}),png(image))

    def test_empty_ios_search_uses_exact_word_and_does_not_repair_a_query(self):
        row=dict(text='Q Search',words=[dict(text='Q',x=42,y=995,width=20,height=18),dict(text='Search',x=75,y=995,width=75,height=18)])
        text=dict(width=500,height=1080,lines=[word('Siri Suggestions',20,80,180),row])
        self.assertTrue(empty_search(text))
        changed=copy.deepcopy(text);changed['lines'][-1]['words'][-1]['text']='Safari'
        with self.assertRaises(InspectionStopped):empty_search(changed)

    def test_caret_exclusion_never_ignores_a_typed_query(self):
        row=json.loads(Path(__file__).with_name('farm_creation_controls.json').read_text(encoding='utf-8'))['empty_ios_search']
        im=Image.new('RGB',(500,1080),'white');im.paste(Image.open(io.BytesIO(base64.b64decode(row['png']))),tuple(row['box'][:2]))
        text=dict(width=500,height=1080,lines=[word('Siri Suggestions',20,80,180)])
        self.assertTrue(empty_search(text,png(im)))
        ImageDraw.Draw(im).rectangle((78,992,81,1021),fill='white');self.assertTrue(empty_search(text,png(im)))
        ImageDraw.Draw(im).rectangle((90,992,160,1021),fill='black')
        with self.assertRaises(InspectionStopped):empty_search(text,png(im))

    def test_zero_command_admission_failure_can_be_retried_but_unknown_cleanup_cannot(self):
        value=dict(terminal=True,state='review_required',workflow=dict(state='review_required',
            source='candidate_phone_workflow',cleanup='not_needed',evidenceExport='confirmed',commands=[],actions=[],observations=[]))
        self.assertTrue(CreationRuns.before_import_retry(value))
        value['workflow']['cleanup']='unconfirmed';self.assertFalse(CreationRuns.before_import_retry(value))

    def test_only_known_readonly_test_preview_has_a_done_navigation_target(self):
        text=dict(width=500,height=1080,lines=[word('imouse-draft',172,76,125),word('Done',425,76,50),
            word('Open in VLC',130,1004,130),word('END OF TEST VIDEO',57,308,240)])
        self.assertFalse(test_video_preview(text)['accountVerified'])
        changed=copy.deepcopy(text);changed['lines'][0]['text']='Unrelated document'
        with self.assertRaises(InspectionStopped):test_video_preview(changed)

    def test_app_navigation_reuses_a_matching_restored_query_without_typing(self):
        labels=['Instagram','TikTok','YouTube','Bluesky','Gmail','Zoho Mail','Expo Go','Proton VPN']
        first=dict(width=500,height=1080,lines=[word(label,20+(i%4)*115,170+(i//4)*127,90) for i,label in enumerate(labels)]+[word('Search',235,893,48)])
        second=dict(width=500,height=1080,lines=[word('Top Hit',20,80),word('Safari',130,180)])
        frames=iter([({'text':first},None),({'text':second},None)])
        workflow=object.__new__(CreationWorkflow);workflow.observe=lambda *args:next(frames)
        calls=[];workflow.step=lambda label,role,**data:calls.append((label,role,data))
        workflow.open_app('Safari','transfer')
        self.assertEqual(['transfer-search-Safari','transfer-open-Safari'],[c[0] for c in calls])
        self.assertFalse(any('text' in c[2] for c in calls))

    def test_a_different_restored_query_is_cleared_before_new_app_text(self):
        labels=['Safari','Mail','Notes','Camera','Settings','Photos','Music']
        first=dict(width=500,height=1080,lines=[word(label,20,170+i*70,90) for i,label in enumerate(labels)]+[word('Search',235,893,48)])
        second=dict(width=500,height=1080,lines=[word('Top Hit',20,80),word('Safari',130,180)])
        frames=iter([({'text':first},None),({'text':second},None)])
        workflow=object.__new__(CreationWorkflow);workflow.observe=lambda *args:next(frames)
        calls=[];workflow.step=lambda label,role,**data:calls.append((label,role,data))
        workflow.open_app('Instagram','initial')
        self.assertEqual(['initial-search-Instagram','initial-clear-restored-search','initial-query-Instagram','initial-open-Instagram'],[c[0] for c in calls])
        self.assertEqual('Instagram',calls[2][2]['text'])

    def test_image_hold_settles_before_press_and_does_not_repeat_a_press(self):
        workflow=object.__new__(CreationWorkflow);workflow.record=dict(actions=[],commands=[]);workflow.save=lambda:None
        workflow.observe=lambda *args:({'id':'fixture'},b'fixture')
        events=[]
        def command(fun,**data):
            events.append(fun);workflow.record['commands'].append(dict(state='answered'))
        workflow.command=command;workflow.pause=lambda seconds:events.append(seconds)
        workflow.step('image-menu-1','transfer_slide',point=(245,480),hold=True)
        self.assertEqual(['/mouse/move',.6,'/mouse/down',1.1,'/mouse/up'],events[:5])
        self.assertEqual(1,events.count('/mouse/down'));self.assertEqual(1,events.count('/mouse/up'))

    def test_picker_highlight_is_fixed_and_cannot_weaken_full_size_image_checks(self):
        im=Image.open(io.BytesIO(self.assets[0])).convert('RGB').crop((0,135,1080,1215)).resize((125,125))
        tinted=Image.blend(im,Image.new('RGB',im.size,'white'),.6)
        screen=Image.new('RGB',(500,1080),'white');screen.paste(tinted,(125,677));raw=png(screen)
        self.assertTrue(source_match(raw,self.assets[0],(125,677,250,802),square=True,badge=True)['matched'])
        self.assertFalse(source_match(raw,self.assets[1],(125,677,250,802),square=True,badge=True)['matched'])
        self.assertFalse(source_match(raw,self.assets[0],(125,677,250,802),square=True)['matched'])
        selected=Image.blend(im,Image.new('RGB',im.size,'black'),.5)
        selected_preview=Image.blend(selected,Image.new('RGB',im.size,'white'),.6)
        screen.paste(selected_preview,(125,677))
        self.assertTrue(source_match(png(screen),self.assets[0],(125,677,250,802),square=True,badge=True)['matched'])
        self.assertFalse(source_match(png(screen),self.assets[1],(125,677,250,802),square=True,badge=True)['matched'])
        screen.paste(Image.new('RGB',(125,125),'white'),(125,677))
        self.assertFalse(source_match(png(screen),self.assets[0],(125,677,250,802),square=True,badge=True)['matched'])

    def imported_value(self):
        return dict(terminal=True,state='review_required',request=self.spec,
            workflow=dict(state='review_required',source='candidate_phone_workflow',account='xs.halle.xo',
                cleanup='confirmed',evidenceExport='confirmed',mediaDelivery=dict(stopped=True),
                commands=[dict(purpose='save-photo-'+str(i),state='answered') for i in (1,2,3)],
                actions=[dict(label='save-photo-'+str(i),state='answered') for i in (1,2,3)],
                observations=[dict(state='observed',observation=dict(receiverPid=321,frameEvidence=dict(session='fixture-stream')))],
                finalInput=dict(generation=8,owned=False,active=False,stopped=False,releasing=False,release_failed=False)))

    def test_imported_checkpoint_never_continues_unknown_imports_editor_or_save(self):
        value=self.imported_value();self.assertTrue(CreationRuns.imported_checkpoint(value))
        for purpose,state in [('save-photo-4','answered'),('open-new-carousel-editor','answered'),
                              ('paste-exact-caption','answered'),('prepared-save-once','outcome_unknown'),('pointer','outcome_unknown')]:
            changed=copy.deepcopy(value);changed['workflow']['commands'].append(dict(purpose=purpose,state=state))
            with self.subTest(purpose=purpose,state=state):
                self.assertFalse(CreationRuns.imported_checkpoint(changed))
        changed=copy.deepcopy(value);changed['workflow']['commands'].pop();self.assertFalse(CreationRuns.imported_checkpoint(changed))
        changed=copy.deepcopy(value);changed['workflow']['cleanup']='unconfirmed';self.assertFalse(CreationRuns.imported_checkpoint(changed))

    def test_explicit_import_continuation_is_idempotent_and_cannot_fork_or_reimport(self):
        self.service.start(self.spec);original=self.wait();value=self.imported_value()
        value.update(id=self.spec['id'],packageSha256=original['packageSha256'])
        original_get=self.service.get
        def get(key):return value if key==self.spec['id'] else original_get(key)
        with patch.object(self.service,'get',side_effect=get):
            eligible=self.service.eligibility(self.draft['id'],self.draft['revision'])
            self.assertTrue(eligible['eligible']);self.assertEqual(self.spec['id'],eligible['continueImportedFrom'])
            with self.assertRaises(DraftConflict):self.service.start(dict(self.spec,id=str(uuid.uuid4())))
            continuation=dict(self.spec,id=str(uuid.uuid4()),continue_imported_from=self.spec['id'])
            self.service.start(continuation)
            self.service.start(continuation)
            with self.assertRaises(DraftConflict):self.service.start(dict(continuation,id=str(uuid.uuid4())))
            self.assertEqual(2,len(self.service.list(self.draft['id'])))
            with self.assertRaises(DraftConflict):self.service.imported_proof(self.spec['id'],'b'*64)
        self.assertFalse(CreationRuns.before_import_retry(dict(value,request=continuation)))

    def test_import_continuity_rejects_a_new_owner_or_receiver_before_any_input(self):
        workflow=object.__new__(CreationWorkflow);workflow.imported_media=dict(generation=8,receiverPid=321,frameSession='fixture-stream')
        receiver=dict(receiver_pid=321,frame_session='fixture-stream')
        class Kernel:
            def kernel_status(self):return dict(receivers=[receiver])
        workflow.kernel=Kernel();state=self.imported_value()['workflow']['finalInput']
        workflow.check_import_continuity(state)
        for changed in (dict(state,generation=10),dict(state,owned=True)):
            with self.assertRaises(InspectionStopped):workflow.check_import_continuity(changed)
        receiver['frame_session']='new-stream'
        with self.assertRaises(InspectionStopped):workflow.check_import_continuity(state)

    def test_continuation_acquisition_failure_without_phone_commands_keeps_imports_not_reimport_permission(self):
        value=self.imported_value();value['request']=dict(self.spec,continue_imported_from=str(uuid.uuid4()))
        value['workflow'].update(commands=[],actions=[],observations=[],importedMedia=dict(priorRunId=value['request']['continue_imported_from']))
        self.assertTrue(CreationRuns.imported_checkpoint(value))
        self.assertFalse(CreationRuns.before_import_retry(value))
        value['workflow']['commands']=[dict(purpose='pointer',state='outcome_unknown')]
        self.assertFalse(CreationRuns.imported_checkpoint(value))

    def test_running_verifier_reports_its_own_cleanup_instead_of_completed_import_cleanup(self):
        self.service.start(self.spec);value=self.wait()
        folder=self.service.folder/self.spec['id']/'verification';folder.mkdir()
        atomic_json(folder/'record.json',dict(packageSha256=value['packageSha256'],cleanup='unconfirmed',actions=[]))
        with patch.object(self.jobs,'get',return_value=dict(status='running',terminal=False,result=None,error=None)):
            current=self.service.get(self.spec['id'])
        self.assertFalse(current['terminal']);self.assertEqual('unconfirmed',current['cleanup'])
        self.assertEqual('unconfirmed',current['workflow']['cleanup']);self.assertFalse(current['savedDraftVerified'])

    def test_closing_caption_editor_makes_no_text_claim_and_details_still_refuse_mismatch(self):
        row=json.loads(Path(__file__).with_name('farm_creation_controls.json').read_text(encoding='utf-8'))['ok']
        image=Image.new('RGB',(500,1080),'white');image.paste(Image.open(io.BytesIO(base64.b64decode(row['png']))),tuple(row['box'][:2]))
        workflow=object.__new__(CreationWorkflow);workflow.caption='Hi there';workflow.assets=self.assets
        text=dict(width=500,height=1080,lines=[word('Caption',215,76),word('Poll',58,618,40),
            word('Prompt',150,618),word('Hithere',20,493)])
        value=dict(text=text,result=dict(layout='carousel_details'))
        checked=workflow.verify_screen('caption_pasted_editor',value,png(image))
        self.assertFalse(checked['captionExact']);self.assertTrue(checked['requiresExactDetailsBeforeSave'])
        for wrong in ('Hithere','Hi there!','Hi there\nextra'):
            value['text']['lines']=[word(wrong,20,493)]
            with self.subTest(wrong=wrong),self.assertRaises(InspectionStopped):workflow.verify_screen('details',value,png(image))

    def execution_fixture(self,creator_state='review_required',images=('01.jpg','02.jpg','03.jpg')):
        self.service.start(self.spec);value=self.wait()
        _,package,digest=self.service.row(self.spec['id']);assets,caption,_=source_content(package)
        class Server:
            instance=None
            def __init__(inner,*args,**kwargs):
                Server.instance=inner;inner.clock=time.monotonic;inner.deadline=inner.clock()+5
                inner.url='http://192.168.50.2:9917/fixture';inner.served_images=set(images)
                inner.closed=inner.clients_closed=False
            def handle_request(inner):time.sleep(.001)
            def close_clients(inner):inner.clients_closed=True
            def server_close(inner):inner.closed=True
        class Creator:
            def __init__(inner,*args,**kwargs):pass
            def run(inner):return dict(packageSha256=digest,state=creator_state,source='offline_protocol_fixture',
                cleanup='confirmed',evidenceExport='confirmed',savedDraftVerified=False,actions=[],observations=[],
                error='Import reply lost.' if creator_state=='review_required' else None)
        return Server,Creator,(self.service.folder/self.spec['id'],assets,caption,digest,threading.Event())

    def test_lost_import_reply_stops_verification_even_if_all_images_were_served(self):
        server,creator,args=self.execution_fixture()
        with patch('farm_creation_runs.MediaTransferServer',server),patch('farm_creation_runs.CreationWorkflow',creator),\
                patch('farm_creation_runs.Workflow',side_effect=AssertionError('Never verify uncertain creation')):
            result=CreationRuns.execute(self.service,*args)
        self.assertEqual('review_required',result['state']);self.assertFalse(result['savedDraftVerified'])
        self.assertTrue(server.instance.closed and server.instance.clients_closed and result['mediaDelivery']['stopped'])

    def test_creation_setup_exception_still_closes_media_clients_and_listener(self):
        server,_,args=self.execution_fixture()
        with patch('farm_creation_runs.MediaTransferServer',server),\
                patch('farm_creation_runs.CreationWorkflow',side_effect=RuntimeError('Fixture setup failed')):
            with self.assertRaises(RuntimeError):CreationRuns.execute(self.service,*args)
        self.assertTrue(server.instance.closed and server.instance.clients_closed)

    def test_incomplete_media_delivery_never_starts_saved_draft_verification(self):
        server,creator,args=self.execution_fixture('created_unverified',('01.jpg','02.jpg'))
        with patch('farm_creation_runs.MediaTransferServer',server),patch('farm_creation_runs.CreationWorkflow',creator),\
                patch('farm_creation_runs.Workflow',side_effect=AssertionError('Missing image must stop')):
            result=CreationRuns.execute(self.service,*args)
        self.assertEqual('review_required',result['state']);self.assertFalse(result['savedDraftVerified'])

    def test_failed_independent_verifier_cannot_claim_a_created_draft(self):
        server,creator,args=self.execution_fixture('created_unverified')
        class Verifier:
            def __init__(inner,*args,**kwargs):pass
            def run(inner):return dict(state='review_required',savedDraftVerified=False,source='offline_protocol_fixture',
                cleanup='confirmed',evidenceExport='confirmed',actions=[],observations=[],error='Wrong reopened caption.')
        with patch('farm_creation_runs.MediaTransferServer',server),patch('farm_creation_runs.CreationWorkflow',creator),\
                patch('farm_creation_runs.Workflow',Verifier):
            result=CreationRuns.execute(self.service,*args)
        self.assertFalse(result['createdDraftVerified']);self.assertFalse(result['savedDraftVerified'])
        self.assertEqual('Wrong reopened caption.',result['error'])


if __name__=='__main__':unittest.main()
