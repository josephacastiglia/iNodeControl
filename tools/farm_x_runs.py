"""Explicit candidate admission: a saved X video copy -> verified X draft on the signed-in account.

Same durable rules as the Reel and TikTok routes: GET never connects to the
phone, a request ID only retrieves its journal, and a new request for the same
video and text is refused once any earlier attempt could have imported media or
saved a draft. Nothing resumes. There is no fixed X account: creation binds the
account signed in first and the verifier must find the same one.
"""
from farm_reel_runs import ReelCreationRuns
from farm_tiktok_layout import TikTokReference
from farm_x_creation import XCreationWorkflow, XVerification, COMMITTING
from farm_x_layout import caption_supported


class XCreationRuns(ReelCreationRuns):
    action_name = 'create-x-draft'
    FORMAT, LABEL = 'x_video', 'X'
    PINNED_ACCOUNT = False
    workflow, verifier, reference, committing = XCreationWorkflow, XVerification, TikTokReference, COMMITTING
    caption_supported = staticmethod(caption_supported)
    ENABLED_REASON = ('Saves one prepared X video as a draft on the X account signed in first. Safari downloads it and Files '
                      'saves it to Photos; X reads the signed-in handle from its menu, the exact one-line text is pasted, the one '
                      'matching video is added and Save to drafts is pressed once. A separate check on the same account reopens '
                      'the draft, plays it and keeps it. Start on the X home timeline. The video stays in Photos and Safari '
                      'Downloads, and the phone clipboard is replaced.')
    DISABLED_REASON = 'X draft creation is disabled. Prepare the isolated C24C candidate first.'
    SUPPORTED_REASON = 'This saved X copy fits the candidate.'
    UNSUPPORTED_REASON = ('The X candidate needs a saved C24C X video copy of 2-15 seconds and one ASCII text line of up to '
                          '32 characters, with no leading, trailing or double spaces. Nothing is trimmed or truncated.')
    HELD_REASON = ('This exact video and text already have an X request. '
                   'Select its saved result; an uncertain import or Save to drafts is never repeated.')
    RUNNING_REASON = 'Creating a C24C X draft from the saved video and exact text. No posting or messaging.'
    VERIFIED_REASON = 'The X draft was saved, reopened on the same account, played and kept in Drafts. Nothing was posted.'
    MEANING = ('Package video imported to Photos, exact text pasted, the matching video added and the X draft saved on the '
               'bound account, then independently reopened on the same account, played and kept. No post or app-restart claim.')
