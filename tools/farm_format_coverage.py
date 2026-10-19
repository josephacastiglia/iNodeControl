"""Per-format draft evidence, kept separate from simulated job success.

Every UploadFormat appears exactly once. A level is the strongest *recorded*
evidence for a verified draft, never a claim that publishing works. A format
without an observed draft-save mechanism stays unsupported: posting, sharing or
sending a story is never a substitute for saving a draft.
"""
from imouse_social_automation import UploadFormat

# Ordered from weakest to strongest recorded evidence.
LEVELS = ('unsupported_draft', 'simulation_only', 'supervised_phone', 'integrated_offline', 'integrated_live')

SIMULATION = 'tools/test_farm_feature_validation.py: mock transport only; ends at simulated publish targets, never a phone draft.'
SUPERVISED_17 = 'analysis/farm-platform-drafts-20261017/README.md'

_FORMATS = {
    UploadFormat.IG_CAROUSEL: dict(
        platform='instagram', name='Instagram carousel', level='integrated_live', draftMechanism='observed',
        supervised='Three numbered slides with an exact multiline caption (analysis/farm-phone-transfer-20261017/README.md).',
        offline='Native creation and saved-draft inspection; retained-layout fault matrix (analysis/farm-recovery-20261019/README.md).',
        live='Priority 1/2 on C24C @xs.halle.xo: three distinct slides, short visible ASCII caption, one layout '
             '(analysis/farm-new-draft-20261019/README.md, analysis/farm-recovery-live-20261019/README.md).',
        remaining='Other slide counts, wrapped or hidden captions, ambiguous media, other accounts and phones.'),
    UploadFormat.IG_REEL: dict(
        platform='instagram', name='Instagram Reel', level='integrated_offline', draftMechanism='observed',
        supervised='MP4 Reel saved, reopened from Reels drafts and played (17 Oct steps 152-168; caption typed as a '
                   'space-free label). ' + SUPERVISED_17,
        offline='Draft-only Reel candidate: video import, exact single-line caption by paste, Save draft, independent '
                'Reels drafts reopen and playback check. Disabled without its isolated configuration '
                '(analysis/farm-reel-draft-20261019/README.md).',
        live=None,
        remaining='Fresh integrated C24C acceptance; multiline captions, other accounts/layouts and repeated runs.'),
    UploadFormat.IG_POST: dict(
        platform='instagram', name='Instagram single-image post', level='simulation_only', draftMechanism='not_observed',
        supervised=None, offline=None, live=None,
        remaining='Observe a single-image draft save/reopen; the carousel route selects 2-10 images only.'),
    UploadFormat.IG_STORY: dict(
        platform='instagram', name='Instagram story', level='unsupported_draft', draftMechanism='not_observed',
        supervised=None, offline=None, live=None,
        remaining='No verified story draft mechanism. Sharing a story is publication and stays disabled.'),
    UploadFormat.TT_VIDEO: dict(
        platform='tiktok', name='TikTok video', level='integrated_offline', draftMechanism='observed',
        supervised='Transferred MP4 draft saved, reopened and played; a suggested sound was removed before resaving '
                   '(17 Oct steps 94-113). ' + SUPERVISED_17,
        offline='Draft-only TikTok candidate: video import, suggested-sound removal, exact single-line description by '
                'paste checked caret-free, Drafts once, independent drafts-list reopen that must be silent. Disabled '
                'without its isolated configuration (analysis/farm-tiktok-draft-20261019/README.md).',
        live=None,
        remaining='Fresh integrated C24C acceptance (Paste callout, settled selection and suggestion timing unobserved); '
                  'wrapped descriptions, other accounts and repeated runs.'),
    UploadFormat.TT_PHOTO_CAROUSEL: dict(
        platform='tiktok', name='TikTok photo carousel', level='supervised_phone', draftMechanism='observed',
        supervised='Three-photo draft saved and reopened with numbered slides; a suggested sound stayed attached. '
                   + SUPERVISED_17,
        offline=None, live=None,
        remaining='Integrated adapter; detect or remove automatic sounds; recovery checks.'),
    UploadFormat.TT_STORY: dict(
        platform='tiktok', name='TikTok story', level='unsupported_draft', draftMechanism='not_observed',
        supervised=None, offline=None, live=None,
        remaining='No verified story draft mechanism; posting a story is publication.'),
    UploadFormat.TT_TEXT: dict(
        platform='tiktok', name='TikTok text post', level='unsupported_draft', draftMechanism='not_observed',
        supervised=None, offline=None, live=None,
        remaining='No observed text-post draft save. Captions also need the validated paste route, not HID typing.'),
    UploadFormat.X_POST: dict(
        platform='x', name='X post', level='supervised_phone', draftMechanism='observed',
        supervised='One-image draft saved and reopened with its exact label. ' + SUPERVISED_17,
        offline=None, live=None,
        remaining='Integrated adapter, account recognition, drafts-list identity and recovery checks.'),
    UploadFormat.X_VIDEO: dict(
        platform='x', name='X video', level='supervised_phone', draftMechanism='observed',
        supervised='Transferred MP4 draft saved and reopened; the blank preview played after Play. ' + SUPERVISED_17,
        offline=None, live=None,
        remaining='Integrated adapter with playback evidence and recovery checks.'),
    UploadFormat.X_THREAD: dict(
        platform='x', name='X thread', level='unsupported_draft', draftMechanism='not_observed',
        supervised=None, offline=None, live=None,
        remaining='No observed multi-post thread draft save.'),
    UploadFormat.YT_SHORT: dict(
        platform='youtube', name='YouTube Short', level='supervised_phone', draftMechanism='observed',
        supervised='Photo-derived and transferred MP4 Shorts saved and reopened with exact titles; a permission prompt '
                   'needed a physical tap. ' + SUPERVISED_17,
        offline=None, live=None,
        remaining='Integrated adapter; the permission prompt prevents an unattended claim.'),
    UploadFormat.YT_VIDEO: dict(
        platform='youtube', name='YouTube long video', level='unsupported_draft', draftMechanism='not_observed',
        supervised=None, offline=None, live=None,
        remaining='No observed long-video draft save on C24C.'),
    UploadFormat.YT_COMMUNITY_POST: dict(
        platform='youtube', name='YouTube community post', level='unsupported_draft', draftMechanism='not_observed',
        supervised=None, offline=None, live=None,
        remaining='No observed community-post draft mechanism.'),
}


# Only these routes can drive C24C at all, and only when the backend was started
# with their explicit isolated configuration. Everything else has no live route.
CANDIDATE_ROUTES = {UploadFormat.IG_CAROUSEL: '/api/farm/draft-creations', UploadFormat.IG_REEL: '/api/farm/reel-creations',
                    UploadFormat.TT_VIDEO: '/api/farm/tiktok-creations'}


def coverage():
    """One row per UploadFormat, in enum order. Review data only; never enables input."""
    rows = []
    for member in UploadFormat:
        route = CANDIDATE_ROUTES.get(member)
        rows.append(dict(id=member.value, simulation=SIMULATION, publishingEnabled=False,
                         liveRoute='explicit_isolated_candidate' if route else 'none', candidateEndpoint=route,
                         **_FORMATS[member]))
    return rows
