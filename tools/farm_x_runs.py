"""Explicit candidate admission: a saved X video copy -> verified X draft on the signed-in account.

Same durable rules as the Reel and TikTok routes: GET never connects to the
phone, a request ID only retrieves its journal, and a new request for the same
video and text is refused once any earlier attempt could have imported media or
saved a draft. Nothing resumes. There is no fixed X account: creation binds the
account signed in first and the verifier must find the same one.

XImageCreationRuns (below) is the same admission for one saved x_image package: the image is saved to
Photos from the shared transfer page, added in X and checked read-only in Drafts.
"""
from farm_reel_runs import ReelCreationRuns, ImageCreationRuns
from farm_tiktok_layout import TikTokReference
from farm_x_creation import XCreationWorkflow, XVerification, COMMITTING
from farm_x_layout import caption_supported
from farm_x_image_creation import XImageCreationWorkflow, XImageVerification, COMMITTING as IMAGE_COMMITTING
from farm_x_image_layout import XImageReference


class XCreationRuns(ReelCreationRuns):
    action_name = 'create-x-draft'
    FORMAT, LABEL = 'x_video', 'X'
    PINNED_ACCOUNT = False
    workflow, verifier, reference, committing = XCreationWorkflow, XVerification, TikTokReference, COMMITTING
    caption_supported = staticmethod(caption_supported)
    ENABLED_REASON = ('Saves one prepared X video as a draft on the X account signed in first. Safari downloads it and Files '
                      'saves it to Photos; X reads the signed-in handle from its menu, the exact one-line text is pasted, the one '
                      'matching video is added and Save to drafts is pressed once. A separate check on the same account finds '
                      'it once in Drafts by its exact text and the video thumbnail, without reopening it. Start on the X home timeline. The video stays in Photos and Safari '
                      'Downloads, and the phone clipboard is replaced.')
    DISABLED_REASON = 'X draft creation is disabled. Prepare the isolated C24C candidate first.'
    SUPPORTED_REASON = 'This saved X copy fits the candidate.'
    UNSUPPORTED_REASON = ('The X candidate needs a saved C24C X video copy of 2-15 seconds and one ASCII text line of up to '
                          '32 characters, with no leading, trailing or double spaces. Nothing is trimmed or truncated.')
    HELD_REASON = ('This exact video and text already have an X request. '
                   'Select its saved result; an uncertain import or Save to drafts is never repeated.')
    RUNNING_REASON = 'Creating a C24C X draft from the saved video and exact text. No posting or messaging.'
    VERIFIED_REASON = ('The X draft was saved and found once in Drafts on the same account, with the exact text and the '
                       'package video thumbnail. Nothing was posted.')
    MEANING = ('Package video imported to Photos, exact text pasted, the matching video added and the X draft saved on the '
               'bound account, then independently found once in Drafts on the same account with the exact text and the '
               'package video thumbnail. Not reopened (saving a reopened X draft drops its video, 23 Oct), not played. '
               'No post or app-restart claim.')


class XImageCreationRuns(ImageCreationRuns):
    """One saved x_image package (exactly one 1080x1350 image) -> one X draft on the account signed in first."""
    action_name = 'create-x-image-draft'
    FORMAT, LABEL = 'x_image', 'X image'
    PINNED_ACCOUNT = False
    workflow, verifier, committing = XImageCreationWorkflow, XImageVerification, IMAGE_COMMITTING
    reference = XImageReference
    caption_supported = staticmethod(caption_supported)
    ENABLED_REASON = ('Saves one prepared image as an X draft on the X account signed in first. Safari opens the package page, '
                      'the image is saved to Photos with touch and hold, the caption is copied; X reads the signed-in handle from '
                      'its menu, the exact one-line text is pasted, the one matching image is added and Save to drafts is pressed '
                      'once. A separate check on the same account finds it once in Drafts by its exact text and the image '
                      'thumbnail, without reopening it. Start on the X home timeline. The image stays in Photos and the phone '
                      'clipboard is replaced.')
    DISABLED_REASON = 'X image draft creation is disabled. Prepare the x-image window for this phone first.'
    SUPPORTED_REASON = 'This saved X image fits the candidate.'
    UNSUPPORTED_REASON = ('The X image candidate needs one saved 1080x1350 image for this phone and one ASCII text line of up to '
                          '32 characters, with no leading, trailing or double spaces. Nothing is cropped or truncated.')
    HELD_REASON = ('This exact image and text already have an X image request. '
                   'Select its saved result; an uncertain Photos save or Save to drafts is never repeated.')
    RUNNING_REASON = 'Creating an X image draft from the saved image and exact text. No posting or messaging.'
    VERIFIED_REASON = ('The X image draft was saved and found once in Drafts on the same account, with the exact text and '
                       'the package image thumbnail. Nothing was posted.')
    MEANING = ('Package image saved to Photos, exact text pasted, the matching image added and the X draft saved on the bound '
               'account, then independently found once in Drafts on the same account with the exact text and the package '
               'image thumbnail. Not reopened (saving a reopened X draft drops its media, 23 Oct). No post or app-restart claim.')
