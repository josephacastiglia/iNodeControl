"""Explicit candidate admission: a saved TikTok photo package (tt_photo) -> verified TikTok draft.

The image runs base (farm_reel_runs.ImageCreationRuns) keeps the durable rules: GET never connects
to the phone, a request ID only retrieves its journal, and a new request for the same slides and
description is refused once any earlier attempt could have saved a photo or a draft. Nothing resumes.
"""
from farm_reel_runs import ImageCreationRuns
from farm_tiktok_photo_creation import TikTokPhotoCreationWorkflow, TikTokPhotoVerification, COMMITTING
from farm_tiktok_photo_layout import caption_supported


class TikTokPhotoCreationRuns(ImageCreationRuns):
    action_name = 'create-tiktok-photo-draft'
    FORMAT, LABEL = 'tt_photo', 'TikTok photo'
    workflow, verifier, committing = TikTokPhotoCreationWorkflow, TikTokPhotoVerification, COMMITTING
    caption_supported = staticmethod(caption_supported)
    PINNED_ACCOUNT = True
    ENABLED_REASON = ('Saves one prepared TikTok photo post (2-10 slides) as a draft: Safari saves each slide to Photos, '
                      'TikTok selects exactly those photos in slide order, keeps the sound it suggests, the exact one-line '
                      'description is pasted, Drafts is pressed once, then a separate check finds the draft once in Drafts by '
                      "its first slide, without reopening it. Start on @{account}'s TikTok profile. The slides stay in Photos, "
                      'and the phone clipboard is replaced.')
    DISABLED_REASON = 'TikTok photo draft creation is disabled. Prepare the tiktok-photo window for its phone first.'
    SUPPORTED_REASON = 'This saved TikTok photo package fits the candidate.'
    UNSUPPORTED_REASON = ('The TikTok photo candidate needs a saved tt_photo package of 2-10 slides (1080x1920) for this '
                          'phone and one ASCII description line of up to 24 characters, with no leading, trailing or double '
                          'spaces. Nothing is cropped, trimmed or truncated.')
    HELD_REASON = ('These exact slides and description already have a TikTok photo request. '
                   'Select its saved result; an uncertain Photos save or Drafts press is never repeated.')
    RUNNING_REASON = 'Creating a TikTok photo draft from the saved slides and exact description. No posting or messaging.'
    VERIFIED_REASON = ('The TikTok photo draft was saved and found once in Drafts with the package\'s first slide as its '
                       'cover. Nothing was posted.')
    MEANING = ('Package slides saved to Photos from the transfer page, selected in slide order, the suggested sound kept, '
               'exact description pasted and the draft saved once, then independently found once in Drafts by its first '
               'slide (not reopened). No post or app-restart claim.')
