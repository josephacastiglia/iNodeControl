"""Explicit candidate admission: a saved TikTok video copy -> verified TikTok draft.

Same durable rules as the Reel route: GET never connects to the phone, a request
ID only retrieves its journal, and a new request for the same video and
description is refused once any earlier attempt could have imported media or
saved a draft. Nothing resumes.
"""
from farm_reel_runs import ReelCreationRuns
from farm_tiktok_creation import TikTokCreationWorkflow, TikTokVerification, COMMITTING
from farm_tiktok_layout import TikTokReference, caption_supported


class TikTokCreationRuns(ReelCreationRuns):
    action_name = 'create-tiktok-draft'
    FORMAT, LABEL = 'tt_video', 'TikTok'
    workflow, verifier, reference, committing = TikTokCreationWorkflow, TikTokVerification, TikTokReference, COMMITTING
    caption_supported = staticmethod(caption_supported)
    ENABLED_REASON = ('Saves one prepared TikTok video as a draft: Safari downloads it, Files saves it to Photos, any suggested '
                      'sound is removed, the exact one-line description is pasted, Drafts is pressed once, then a separate check '
                      "reopens it silent and keeps it. Start on @{account}'s TikTok profile. The video stays in Photos and Safari "
                      'Downloads, and the phone clipboard is replaced.')
    DISABLED_REASON = 'TikTok draft creation is disabled. Prepare the isolated C24C candidate first.'
    SUPPORTED_REASON = 'This saved TikTok copy fits the candidate.'
    UNSUPPORTED_REASON = ('The TikTok candidate needs a saved C24C TikTok video copy of 2-15 seconds and one ASCII description '
                          'line of up to 24 characters, with no leading, trailing or double spaces. Nothing is trimmed or truncated.')
    HELD_REASON = ('This exact video and description already have a TikTok request. '
                   'Select its saved result; an uncertain import or Drafts press is never repeated.')
    RUNNING_REASON = 'Creating a C24C TikTok draft from the saved video and exact description. No publishing or messaging.'
    VERIFIED_REASON = 'The TikTok draft was saved, reopened without a sound and kept in Drafts. Nothing was published.'
    MEANING = ('Package video imported to Photos, selected, suggested sound removed, exact description pasted, TikTok draft saved, '
               'then independently reopened silent with the exact description and kept. No publication or app-restart persistence claim.')
