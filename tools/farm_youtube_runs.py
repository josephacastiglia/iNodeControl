"""Explicit candidate admission: a saved YouTube Short copy -> verified YouTube draft on the signed-in channel.

Same durable rules as the Reel, TikTok and X routes: GET never connects to the
phone, a request ID only retrieves its journal, and a new request for the same
video and title is refused once any earlier attempt could have imported media
or saved a draft. Nothing resumes. There is no fixed YouTube channel: creation
binds the channel shown on Add details and the verifier must find the same one
(the operator's rule of 20 Oct for every platform). There is no default phone
either: the route drives only the phone named by the configuration's 'phone'
block (board, device ID, receiver; box slot 16 for YouTube), and stays disabled
while the shared transport cannot drive that phone.
"""
import functools

from farm_reel_runs import ReelCreationRuns, reel_content, MAX_SECONDS
from farm_tiktok_layout import TikTokReference
from farm_youtube_creation import (YouTubeCreationWorkflow, YouTubeVerification, COMMITTING, phone_from_config,
                                   transport_drives)
from farm_youtube_layout import caption_supported
from imouse_social_automation import DEFAULT_SAFE_TEST_DEVICE


class YouTubeCreationRuns(ReelCreationRuns):
    action_name = 'create-youtube-draft'
    FORMAT, LABEL = 'yt_short', 'YouTube'
    PINNED_ACCOUNT = False
    workflow, verifier, reference, committing = YouTubeCreationWorkflow, YouTubeVerification, TikTokReference, COMMITTING
    caption_supported = staticmethod(caption_supported)
    ENABLED_REASON = ('Saves one prepared YouTube Short as a draft on the channel signed in on the configured phone. Safari '
                      'downloads it and Files saves it to Photos; YouTube selects that exact video without trimming, reads the '
                      'channel on Add details, the exact one-line title is pasted and Save draft is pressed once. A separate check '
                      'on the same channel reopens the draft, sees it play, keeps it and finds it once in Drafts. Start on the '
                      'YouTube home feed. The video stays in Photos and Safari Downloads, and the phone clipboard is replaced.')
    DISABLED_REASON = 'YouTube draft creation is disabled. Prepare the isolated candidate for the YouTube phone first.'
    NO_PHONE_REASON = ('YouTube draft creation is disabled: the candidate configuration names no YouTube phone '
                       '(board, device ID and receiver).')
    SUPPORTED_REASON = 'This saved YouTube Short copy fits the candidate.'
    UNSUPPORTED_REASON = ('The YouTube candidate needs a saved YouTube Short copy for the configured phone, 2-15 seconds long, with '
                          'one ASCII title line of up to 24 characters and no leading, trailing or double spaces. Nothing is '
                          'trimmed or truncated.')
    HELD_REASON = ('This exact video and title already have a YouTube request. '
                   'Select its saved result; an uncertain import or Save draft is never repeated.')
    RUNNING_REASON = 'Creating a YouTube Short draft from the saved video and exact title. No upload or messaging.'
    VERIFIED_REASON = 'The YouTube Short draft was saved, reopened on the same channel, played and kept in Drafts. Nothing was uploaded.'
    MEANING = ('Package video imported to Photos, selected untrimmed, the exact title pasted and the YouTube draft saved on the bound '
               'channel, then independently reopened on the same channel, played, kept and found once in Drafts. '
               'No upload or app-restart claim.')

    def __init__(self, folder, videos, jobs, config=None):
        # A malformed phone block stops the backend at start; an absent or undrivable one only disables this route.
        self.phone = phone_from_config(config)
        self.phone_reason = None
        if config is not None and self.phone is None:
            self.phone_reason = self.NO_PHONE_REASON
        elif config is not None and not transport_drives(self.phone):
            self.phone_reason = ('YouTube draft creation is disabled: its phone ' + self.phone['board'] + ' (' + self.phone['receiver']
                                 + ') needs the multi-phone farm; this backend\'s shared phone transport drives only '
                                 + DEFAULT_SAFE_TEST_DEVICE + '.')
        super().__init__(folder, videos, jobs, config if self.phone_reason is None else None)
        if self.config is not None:
            self.workflow = functools.partial(YouTubeCreationWorkflow, phone=self.phone)
            self.verifier = functools.partial(YouTubeVerification, phone=self.phone)

    def capability(self):
        value = super().capability()
        value.update(device=self.phone['board'] if self.phone else None,
                     phone={k: v for k, v in self.phone.items() if k != 'deviceId'} if self.phone else None)
        if self.phone_reason: value['reason'] = self.phone_reason
        return value

    def supports(self, package):
        """A saved Short for the configured phone; no copy is supported while no phone is configured."""
        manifest, caption, _ = reel_content(package)
        video = manifest.get('video') or {}
        seconds = video.get('seconds')
        return (self.phone is not None and manifest.get('format') == self.FORMAT and manifest.get('deviceId') == self.phone['board']
                and self.caption_supported(caption) and (video.get('width'), video.get('height')) == (720, 1280)
                and type(seconds) in (int, float) and 2 <= seconds <= MAX_SECONDS)
