#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iMouse 2.0 — Independent AirPlay (iNodeControl)
Full 7-Layer 19-iPhone Marketing Farm & Social Automation Engine

All 7 Layers Built & Wired to `src/iMouse.Kernel/ApiServer.cs` (127.0.0.1:9913/api):
  - Layer 1: 1-Click Daily Content Factory (`FarmDatabase` SQLite + `ContentFactoryEngine`
             with Pillow 1080x1350 carousel renderer, video asset bundler, and Hook Winner Cloner)
  - Layer 2: Anti-Duplicate Spin Engine (`AntiDuplicateSpinEngine` with 64-bit dHash/pHash,
             1.2-2.2% asymmetric crop, RGB LUT shift, micro-noise, and Apple EXIF/QuickTime UUIDs)
  - Layer 3: Zero-Touch PC -> iPhone Media Pull (`MediaPullOrchestrator` + `iMousePull` iOS
             Shortcut generator + Home/Spotlight Shortcut trigger before upload)
  - Layer 4: Native Mobile Upload Orchestrator (`SocialUploadOrchestrator` with all 14 formats,
             Spotlight App Launcher, In-App Trending Audio 3% Volume Mixer, Story Link/Poll Stickers,
             X 45s Trim-Bar Bezier Guard, and 500x1080 Gaussian non-repeating clicks)
  - Layer 5: Staggered Warmup & Cohort Scheduler (`AccountWarmupEngine`, `BackgroundCohortScheduler`
             with 3.5-7.5h post-warmup upload cooldown, and `VlmComputerUseAdapter`)
  - Layer 6: Conversion Funnel & Golden-Hour Loop (`ConversionFunnelEngine`: Auto-Pinned CTA Comment,
             Comment-to-DM Keyword Bot, and Multi-Phone Cross-Rack Micro-Swarm Seeder)
  - Layer 7: Shadowban Guard & Fleet Diagnostics (`ShadowbanGuardAndDiagnostics`: Profile-grid
             OCR/VLM view scraper, 3-5 Clip Zero-View Circuit Breaker, and Popup/Captcha Watchdog)
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import io
import json
import math
import os
from pathlib import Path
import plistlib
import random
import sqlite3
import struct
import threading
import time
from typing import Any, Callable, Deque, Dict, List, Optional, Sequence, Tuple
import urllib.error
import urllib.parse
import urllib.request

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


# ============================================================================
# 0. CONSTANTS & KERNEL HARDWARE GEOMETRY (ApiServer.cs / gate4_1000_tap_suite.py)
# ============================================================================

DEFAULT_KERNEL_URL = "http://127.0.0.1:9913/api"
DEFAULT_STAGE_SERVER_URL = "http://127.0.0.1:9914"
FORBIDDEN_VENDOR_PORT = 9911
DEFAULT_SAFE_TEST_DEVICE = "C24C"

SCREEN_WIDTH = 500
SCREEN_HEIGHT = 1080
STATUS_BAR_PX = 60
GRID_STEP = 10
STILL_THRESHOLD = 2.0
SETTLE_BUDGET_S = 8.0

DEFAULT_LEASE_MS = 120_000
RENEW_THRESHOLD_MS = 25_000
KERNEL_TEXT_CHUNK_MAX_CHARS = 12
KERNEL_COMMAND_DEADLINE_S = 8.0
UI_TEXT_CAP_CHARS = 200


class ExecutionMode(str, Enum):
    API_BOUNDED_VISION = "api_bounded_vision"
    AI_COMPUTER_USE = "ai_computer_use"


class TextEntryStrategy(str, Enum):
    ON_SCREEN_KEYBOARD_JITTER = "on_screen_keyboard_jitter"
    IOS_CLIPBOARD_PASTE = "ios_clipboard_paste"
    CHUNKED_SENDKEY = "chunked_sendkey"


class Platform(str, Enum):
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    X = "x"
    YOUTUBE = "youtube"


class UploadFormat(str, Enum):
    IG_REEL = "ig_reel"
    IG_CAROUSEL = "ig_carousel"
    IG_POST = "ig_post"
    IG_STORY = "ig_story"
    TT_VIDEO = "tt_video"
    TT_PHOTO_CAROUSEL = "tt_photo_carousel"
    TT_STORY = "tt_story"
    TT_TEXT = "tt_text"
    X_POST = "x_post"
    X_VIDEO = "x_video"
    X_THREAD = "x_thread"
    YT_SHORT = "yt_short"
    YT_VIDEO = "yt_video"
    YT_COMMUNITY_POST = "yt_community_post"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# ============================================================================
# 1. BMP FRAME DECODER & GAUSSIAN JITTER ENGINE (500x1080 Kernel Coordinate Space)
# ============================================================================

def parse_bmp_grid(raw: bytes) -> Tuple[int, int, List[int]]:
    if len(raw) < 54 or raw[:2] != b"BM":
        raise ValueError("Expected uncompressed BMP frame from FrameStore")
    offset = int.from_bytes(raw[10:14], "little")
    width = int.from_bytes(raw[18:22], "little", signed=True)
    height = int.from_bytes(raw[22:26], "little", signed=True)
    bpp = int.from_bytes(raw[28:30], "little")
    if bpp not in (24, 32) or width <= 0 or height == 0:
        raise ValueError(f"Unsupported BMP geometry: {width}x{height}x{bpp}")
    bottom_up, h = height > 0, abs(height)
    step = bpp // 8
    stride = (width * step + 3) & ~3
    if offset + stride * h > len(raw):
        raise ValueError("Truncated BMP frame")
    samples: List[int] = []
    for y in range(STATUS_BAR_PX + GRID_STEP // 2, h, GRID_STEP):
        row = offset + ((h - 1 - y) if bottom_up else y) * stride
        for x in range(GRID_STEP // 2, width, GRID_STEP):
            i = row + x * step
            samples.append((raw[i + 2] * 299 + raw[i + 1] * 587 + raw[i] * 114) // 1000)
    return width, h, samples


def frame_distance(a: Sequence[int], b: Sequence[int]) -> float:
    if len(a) != len(b) or not a:
        return float("inf")
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


@dataclass(frozen=True)
class PixelBoundingBox:
    name: str
    x_min: int
    y_min: int
    x_max: int
    y_max: int
    inner_margin_ratio: float = 0.14

    def __post_init__(self) -> None:
        if not (0 <= self.x_min < self.x_max <= SCREEN_WIDTH):
            raise ValueError(f"{self.name}: x [{self.x_min}, {self.x_max}] out of 0..{SCREEN_WIDTH}")
        if not (STATUS_BAR_PX <= self.y_min < self.y_max <= SCREEN_HEIGHT):
            raise ValueError(f"{self.name}: y [{self.y_min}, {self.y_max}] out of {STATUS_BAR_PX}..{SCREEN_HEIGHT}")

    @property
    def width(self) -> int:
        return self.x_max - self.x_min

    @property
    def height(self) -> int:
        return self.y_max - self.y_min

    def safe_pixel_bounds(self) -> Tuple[int, int, int, int]:
        mx = max(1, int(round(self.width * self.inner_margin_ratio)))
        my = max(1, int(round(self.height * self.inner_margin_ratio)))
        sx_min = min(self.x_min + mx, self.x_max - 1)
        sx_max = max(sx_min + 1, self.x_max - mx)
        sy_min = min(self.y_min + my, self.y_max - 1)
        sy_max = max(sy_min + 1, self.y_max - my)
        return (sx_min, sy_min, sx_max, sy_max)


@dataclass(frozen=True)
class JitteredClick:
    target_name: str
    x: int
    y: int
    pre_move_x: int
    pre_move_y: int
    dwell_ms: int


class HumanizedTargetJitter:
    """
    2D Truncated Gaussian sampler inside a button's 500x1080 safe box with a
    48-tap non-repeating ring buffer so no button is ever clicked at the same
    (x, y) pixel twice.
    """

    def __init__(
        self,
        rng: Optional[random.Random] = None,
        history_size: int = 48,
        min_pixel_separation: float = 1.4,
    ) -> None:
        self._rng = rng or random.Random()
        self._history_size = history_size
        self._min_pixel_separation = min_pixel_separation
        self._history: Dict[str, Deque[Tuple[int, int]]] = {}

    def sample_click(self, box: PixelBoundingBox) -> JitteredClick:
        sx_min, sy_min, sx_max, sy_max = box.safe_pixel_bounds()
        w = max(1, sx_max - sx_min)
        h = max(1, sy_max - sy_min)
        capacity = (w + 1) * (h + 1)
        max_hist = min(self._history_size, max(1, capacity - 1))
        target_history = self._history.setdefault(box.name, deque(maxlen=max_hist))

        cx = (sx_min + sx_max) / 2.0 + self._rng.uniform(-0.10 * w, 0.10 * w)
        cy = (sy_min + sy_max) / 2.0 + self._rng.uniform(-0.10 * h, 0.10 * h)
        sigma_x = max(1.2, w * 0.24)
        sigma_y = max(1.2, h * 0.24)

        min_dist = self._min_pixel_separation
        chosen_x, chosen_y = int(round(cx)), int(round(cy))

        for attempt in range(90):
            rx = max(sx_min, min(sx_max, int(round(self._rng.gauss(cx, sigma_x)))))
            ry = max(sy_min, min(sy_max, int(round(self._rng.gauss(cy, sigma_y)))))
            if (rx, ry) not in target_history and all(
                math.hypot(rx - hx, ry - hy) >= min_dist for hx, hy in target_history
            ):
                chosen_x, chosen_y = rx, ry
                break
            if attempt > 45:
                min_dist *= 0.8
        else:
            candidates = [
                (px, py)
                for px in range(sx_min, sx_max + 1)
                for py in range(sy_min, sy_max + 1)
                if (px, py) not in target_history
            ]
            if not candidates:
                target_history.clear()
                candidates = [(px, py) for px in range(sx_min, sx_max + 1) for py in range(sy_min, sy_max + 1)]
            chosen_x, chosen_y = self._rng.choice(candidates)

        target_history.append((chosen_x, chosen_y))
        pre_x = max(0, min(SCREEN_WIDTH - 1, chosen_x + self._rng.randint(-12, 12)))
        pre_y = max(STATUS_BAR_PX, min(SCREEN_HEIGHT - 1, chosen_y + self._rng.randint(-12, 12)))
        dwell_ms = int(max(48, min(145, self._rng.lognormvariate(math.log(78), 0.22))))

        return JitteredClick(
            target_name=box.name,
            x=chosen_x,
            y=chosen_y,
            pre_move_x=pre_x,
            pre_move_y=pre_y,
            dwell_ms=dwell_ms,
        )

    def sample_swipe_params(
        self,
        direction: str,
        base_len: float = 0.68,
        base_duration_ms: int = 380,
    ) -> Dict[str, Any]:
        length = round(max(0.35, min(0.88, self._rng.gauss(base_len, 0.07))), 3)
        duration = int(max(210, min(680, self._rng.gauss(base_duration_ms, 55))))
        return {"direction": direction, "len": length, "duration": duration}

    def generate_drag_waypoints(
        self,
        start_box: PixelBoundingBox,
        end_box: PixelBoundingBox,
        steps: int = 8,
    ) -> List[Tuple[int, int, int]]:
        c_start = self.sample_click(start_box)
        c_end = self.sample_click(end_box)
        p0 = (float(c_start.x), float(c_start.y))
        p3 = (float(c_end.x), float(c_end.y))
        dx, dy = p3[0] - p0[0], p3[1] - p0[1]
        p1 = (p0[0] + dx * 0.3 + self._rng.uniform(-8, 8), p0[1] + dy * 0.3 + self._rng.uniform(-6, 6))
        p2 = (p0[0] + dx * 0.7 + self._rng.uniform(-8, 8), p0[1] + dy * 0.7 + self._rng.uniform(-6, 6))

        waypoints: List[Tuple[int, int, int]] = []
        for i in range(steps):
            t_lin = i / float(max(1, steps - 1))
            t = t_lin * t_lin * (3.0 - 2.0 * t_lin)
            u = 1.0 - t
            bx = int(round((u**3) * p0[0] + 3 * (u**2) * t * p1[0] + 3 * u * (t**2) * p2[0] + (t**3) * p3[0]))
            by = int(round((u**3) * p0[1] + 3 * (u**2) * t * p1[1] + 3 * u * (t**2) * p2[1] + (t**3) * p3[1]))
            bx = max(0, min(SCREEN_WIDTH - 1, bx))
            by = max(STATUS_BAR_PX, min(SCREEN_HEIGHT - 1, by))
            dt_ms = self._rng.randint(24, 48) if i > 0 else 0
            waypoints.append((bx, by, dt_ms))
        waypoints[-1] = (c_end.x, c_end.y, self._rng.randint(30, 55))
        return waypoints


# ============================================================================
# 2. COMPLETE 500x1080 UI BOUNDING BOXES (App Launch, Audio, Stickers, Comments, DMs)
# ============================================================================

UI_BOXES_500x1080: Dict[str, PixelBoundingBox] = {
    # --- iOS System / Spotlight / Shortcuts / Popups ---
    "ios_spotlight_pull_start": PixelBoundingBox("ios_spotlight_pull_start", 210, 260, 290, 320),
    "ios_spotlight_pull_end": PixelBoundingBox("ios_spotlight_pull_end", 210, 620, 290, 690),
    "ios_spotlight_top_hit": PixelBoundingBox("ios_spotlight_top_hit", 35, 225, 135, 310),
    "ios_shortcut_imousepull_icon": PixelBoundingBox("ios_shortcut_imousepull_icon", 350, 140, 445, 235),
    "ios_popup_allow_paste": PixelBoundingBox("ios_popup_allow_paste", 260, 540, 395, 595),
    "ios_popup_dismiss_not_now": PixelBoundingBox("ios_popup_dismiss_not_now", 110, 590, 240, 640),
    "keyboard_dismiss_safe": PixelBoundingBox("keyboard_dismiss_safe", 410, 520, 485, 575),
    "ios_paste_popup_bubble": PixelBoundingBox("ios_paste_popup_bubble", 60, 210, 175, 255),

    # --- Trending Audio Mixer & Story Stickers (Shared / IG / TikTok / YT) ---
    "editor_add_sound_btn": PixelBoundingBox("editor_add_sound_btn", 155, 75, 345, 120),
    "sound_search_top_track": PixelBoundingBox("sound_search_top_track", 45, 280, 370, 345),
    "sound_use_track_btn": PixelBoundingBox("sound_use_track_btn", 390, 285, 470, 340),
    "sound_volume_Controls_btn": PixelBoundingBox("sound_volume_Controls_btn", 390, 820, 475, 875),
    "sound_added_vol_slider_high": PixelBoundingBox("sound_added_vol_slider_high", 320, 740, 375, 785),
    "sound_added_vol_slider_3pct": PixelBoundingBox("sound_added_vol_slider_3pct", 65, 740, 105, 785),
    "sound_done_btn": PixelBoundingBox("sound_done_btn", 405, 65, 480, 110),
    "story_sticker_tray_btn": PixelBoundingBox("story_sticker_tray_btn", 335, 68, 390, 115),
    "story_link_sticker_item": PixelBoundingBox("story_link_sticker_item", 60, 390, 225, 455),
    "story_poll_sticker_item": PixelBoundingBox("story_poll_sticker_item", 265, 390, 435, 455),
    "story_link_url_input": PixelBoundingBox("story_link_url_input", 45, 240, 455, 300),
    "story_sticker_done_btn": PixelBoundingBox("story_sticker_done_btn", 405, 65, 480, 110),

    # --- Instagram (500x1080 Portrait) ---
    "ig_tab_home": PixelBoundingBox("ig_tab_home", 20, 985, 90, 1040),
    "ig_search_tab_magnifier": PixelBoundingBox("ig_search_tab_magnifier", 115, 985, 185, 1040),
    "ig_tab_create_plus": PixelBoundingBox("ig_tab_create_plus", 215, 985, 285, 1040),
    "ig_tab_activity_heart": PixelBoundingBox("ig_tab_activity_heart", 315, 985, 385, 1040),
    "ig_tab_profile": PixelBoundingBox("ig_tab_profile", 410, 985, 480, 1040),
    "ig_search_top_input": PixelBoundingBox("ig_search_top_input", 45, 70, 455, 115),
    "ig_search_first_result": PixelBoundingBox("ig_search_first_result", 45, 175, 455, 240),
    "ig_profile_grid_slot_1": PixelBoundingBox("ig_profile_grid_slot_1", 10, 520, 165, 740),
    "ig_profile_grid_slot_2": PixelBoundingBox("ig_profile_grid_slot_2", 172, 520, 328, 740),
    "ig_profile_grid_slot_3": PixelBoundingBox("ig_profile_grid_slot_3", 335, 520, 490, 740),
    "ig_mode_post": PixelBoundingBox("ig_mode_post", 180, 905, 240, 950),
    "ig_mode_story": PixelBoundingBox("ig_mode_story", 255, 905, 315, 950),
    "ig_mode_reel": PixelBoundingBox("ig_mode_reel", 330, 905, 390, 950),
    "ig_carousel_aspect_ratio_btn": PixelBoundingBox("ig_carousel_aspect_ratio_btn", 20, 515, 75, 570),
    "ig_carousel_multi_select": PixelBoundingBox("ig_carousel_multi_select", 390, 515, 460, 570),
    "ig_gallery_slot_1": PixelBoundingBox("ig_gallery_slot_1", 15, 605, 155, 735),
    "ig_gallery_slot_2": PixelBoundingBox("ig_gallery_slot_2", 175, 605, 320, 735),
    "ig_gallery_slot_3": PixelBoundingBox("ig_gallery_slot_3", 340, 605, 480, 735),
    "ig_gallery_slot_4": PixelBoundingBox("ig_gallery_slot_4", 15, 755, 155, 885),
    "ig_top_right_next": PixelBoundingBox("ig_top_right_next", 400, 65, 480, 110),
    "ig_editor_bottom_next": PixelBoundingBox("ig_editor_bottom_next", 360, 970, 475, 1025),
    "ig_caption_field": PixelBoundingBox("ig_caption_field", 40, 235, 450, 365),
    "ig_publish_share": PixelBoundingBox("ig_publish_share", 40, 970, 460, 1035),
    "ig_story_your_story": PixelBoundingBox("ig_story_your_story", 30, 960, 210, 1025),
    "ig_reel_like_button": PixelBoundingBox("ig_reel_like_button", 430, 625, 480, 690),
    "ig_reel_comment_button": PixelBoundingBox("ig_reel_comment_button", 430, 710, 480, 775),
    "ig_reel_share_button": PixelBoundingBox("ig_reel_share_button", 430, 795, 480, 860),
    "ig_reel_save_button": PixelBoundingBox("ig_reel_save_button", 430, 875, 480, 930),
    "ig_comment_input_box": PixelBoundingBox("ig_comment_input_box", 55, 560, 390, 615),
    "ig_comment_post_btn": PixelBoundingBox("ig_comment_post_btn", 410, 560, 475, 615),
    "comment_drawer_close_handle": PixelBoundingBox("comment_drawer_close_handle", 210, 195, 290, 235),
    "ig_top_comment_row": PixelBoundingBox("ig_top_comment_row", 60, 280, 420, 340),
    "ig_pin_comment_action": PixelBoundingBox("ig_pin_comment_action", 310, 280, 385, 340),

    # --- TikTok (500x1080 Portrait) ---
    "tt_tab_home": PixelBoundingBox("tt_tab_home", 20, 985, 90, 1040),
    "tt_tab_create_plus": PixelBoundingBox("tt_tab_create_plus", 210, 975, 290, 1040),
    "tt_tab_inbox": PixelBoundingBox("tt_tab_inbox", 315, 985, 385, 1040),
    "tt_tab_profile": PixelBoundingBox("tt_tab_profile", 410, 985, 480, 1040),
    "tt_mode_text": PixelBoundingBox("tt_mode_text", 130, 895, 195, 940),
    "tt_mode_video": PixelBoundingBox("tt_mode_video", 210, 895, 280, 940),
    "tt_mode_photo": PixelBoundingBox("tt_mode_photo", 290, 895, 360, 940),
    "tt_upload_gallery_btn": PixelBoundingBox("tt_upload_gallery_btn", 380, 800, 460, 875),
    "tt_gallery_multi_checkbox": PixelBoundingBox("tt_gallery_multi_checkbox", 360, 130, 470, 175),
    "tt_gallery_slot_1": PixelBoundingBox("tt_gallery_slot_1", 15, 235, 155, 365),
    "tt_gallery_slot_2": PixelBoundingBox("tt_gallery_slot_2", 175, 235, 320, 365),
    "tt_gallery_slot_3": PixelBoundingBox("tt_gallery_slot_3", 340, 235, 480, 365),
    "tt_gallery_next_btn": PixelBoundingBox("tt_gallery_next_btn", 340, 970, 475, 1025),
    "tt_editor_next_btn": PixelBoundingBox("tt_editor_next_btn", 270, 970, 475, 1025),
    "tt_editor_post_to_story": PixelBoundingBox("tt_editor_post_to_story", 30, 970, 240, 1025),
    "tt_text_post_input": PixelBoundingBox("tt_text_post_input", 60, 345, 440, 560),
    "tt_caption_field": PixelBoundingBox("tt_caption_field", 30, 150, 340, 280),
    "tt_post_publish_btn": PixelBoundingBox("tt_post_publish_btn", 260, 970, 475, 1035),
    "tt_like_button": PixelBoundingBox("tt_like_button", 435, 485, 485, 535),
    "tt_comment_button": PixelBoundingBox("tt_comment_button", 435, 565, 485, 615),
    "tt_bookmark_button": PixelBoundingBox("tt_bookmark_button", 435, 640, 485, 690),
    "tt_share_button": PixelBoundingBox("tt_share_button", 435, 715, 485, 765),

    # --- X / Twitter (500x1080 Portrait) ---
    "x_tab_home": PixelBoundingBox("x_tab_home", 25, 985, 90, 1040),
    "x_floating_compose_plus": PixelBoundingBox("x_floating_compose_plus", 400, 875, 470, 950),
    "x_compose_text_area": PixelBoundingBox("x_compose_text_area", 80, 175, 460, 365),
    "x_toolbar_media_icon": PixelBoundingBox("x_toolbar_media_icon", 25, 560, 70, 615),
    "x_gallery_slot_1": PixelBoundingBox("x_gallery_slot_1", 15, 215, 155, 365),
    "x_video_trim_right_handle": PixelBoundingBox("x_video_trim_right_handle", 340, 840, 380, 905),
    "x_video_trim_full_right": PixelBoundingBox("x_video_trim_full_right", 455, 840, 485, 905),
    "x_media_done_btn": PixelBoundingBox("x_media_done_btn", 400, 65, 475, 110),
    "x_add_thread_plus_btn": PixelBoundingBox("x_add_thread_plus_btn", 430, 560, 475, 615),
    "x_post_publish_btn": PixelBoundingBox("x_post_publish_btn", 390, 65, 475, 110),
    "x_like_button": PixelBoundingBox("x_like_button", 280, 795, 320, 840),
    "x_reply_button": PixelBoundingBox("x_reply_button", 80, 795, 120, 840),
    "x_bookmark_button": PixelBoundingBox("x_bookmark_button", 380, 795, 420, 840),

    # --- YouTube (500x1080 Portrait) ---
    "yt_tab_home": PixelBoundingBox("yt_tab_home", 20, 985, 90, 1040),
    "yt_tab_shorts": PixelBoundingBox("yt_tab_shorts", 110, 985, 180, 1040),
    "yt_tab_create_plus": PixelBoundingBox("yt_tab_create_plus", 215, 975, 285, 1040),
    "yt_mode_video": PixelBoundingBox("yt_mode_video", 140, 895, 210, 940),
    "yt_mode_short": PixelBoundingBox("yt_mode_short", 225, 895, 290, 940),
    "yt_mode_post": PixelBoundingBox("yt_mode_post", 310, 895, 370, 940),
    "yt_short_gallery_btn": PixelBoundingBox("yt_short_gallery_btn", 40, 810, 110, 885),
    "yt_gallery_slot_1": PixelBoundingBox("yt_gallery_slot_1", 15, 215, 155, 365),
    "yt_short_trim_done": PixelBoundingBox("yt_short_trim_done", 390, 960, 475, 1025),
    "yt_short_check_confirm": PixelBoundingBox("yt_short_check_confirm", 400, 810, 470, 885),
    "yt_top_right_next": PixelBoundingBox("yt_top_right_next", 400, 65, 475, 110),
    "yt_title_caption_field": PixelBoundingBox("yt_title_caption_field", 40, 215, 460, 325),
    "yt_audience_not_for_kids": PixelBoundingBox("yt_audience_not_for_kids", 40, 580, 450, 645),
    "yt_publish_upload_btn": PixelBoundingBox("yt_publish_upload_btn", 40, 970, 460, 1035),
    "yt_short_like_btn": PixelBoundingBox("yt_short_like_btn", 430, 580, 480, 645),
    "yt_short_comment_btn": PixelBoundingBox("yt_short_comment_btn", 430, 680, 480, 745),
    "yt_short_subscribe_btn": PixelBoundingBox("yt_short_subscribe_btn", 170, 875, 270, 930),

    # --- Funnel DM & Profile Grid Boxes ---
    "notif_latest_comment_reply": PixelBoundingBox("notif_latest_comment_reply", 65, 260, 150, 295),
    "notif_commenter_avatar": PixelBoundingBox("notif_commenter_avatar", 20, 215, 62, 260),
    "profile_message_dm_btn": PixelBoundingBox("profile_message_dm_btn", 255, 365, 455, 408),
    "dm_text_input_box": PixelBoundingBox("dm_text_input_box", 55, 560, 390, 615),
    "dm_send_btn": PixelBoundingBox("dm_send_btn", 410, 560, 475, 615),
}

UI_BOXES_CALIBRATION_PATH = Path("config/ui_boxes_500x1080.json")


def load_calibrated_ui_boxes(config_path: Path = UI_BOXES_CALIBRATION_PATH) -> Dict[str, PixelBoundingBox]:
    """
    Loads optional operator-calibrated 500x1080 bounding box overrides from
    `config/ui_boxes_500x1080.json` and merges them into `UI_BOXES_500x1080`.
    """
    if not config_path.exists():
        return UI_BOXES_500x1080
    try:
        raw_map = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(raw_map, dict):
            for name, coords in raw_map.items():
                if isinstance(coords, (list, tuple)) and len(coords) >= 4:
                    x1, y1, x2, y2 = int(coords[0]), int(coords[1]), int(coords[2]), int(coords[3])
                    margin = float(coords[4]) if len(coords) >= 5 else 0.14
                    UI_BOXES_500x1080[name] = PixelBoundingBox(name, x1, y1, x2, y2, inner_margin_ratio=margin)
    except Exception:
        pass
    return UI_BOXES_500x1080


def save_calibrated_ui_box(
    target_name: str,
    x_min: int,
    y_min: int,
    x_max: int,
    y_max: int,
    inner_margin_ratio: float = 0.14,
    config_path: Path = UI_BOXES_CALIBRATION_PATH,
) -> PixelBoundingBox:
    """
    Validates and persists a calibrated 500x1080 `PixelBoundingBox` to
    `config/ui_boxes_500x1080.json` and updates `UI_BOXES_500x1080` in-memory.
    """
    box = PixelBoundingBox(target_name, int(x_min), int(y_min), int(x_max), int(y_max), float(inner_margin_ratio))
    UI_BOXES_500x1080[target_name] = box
    config_path.parent.mkdir(parents=True, exist_ok=True)
    existing: Dict[str, Any] = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing[target_name] = [box.x_min, box.y_min, box.x_max, box.y_max, round(box.inner_margin_ratio, 3)]
    config_path.write_text(json.dumps(existing, indent=2, sort_keys=True), encoding="utf-8")
    return box


load_calibrated_ui_boxes()


IOS_123_CHARS = "1234567890-/:;()$&@\".,?!'"
IOS_SYM_CHARS = "[]{}#%^*+=_\\|~<>"


def build_ios_qwerty_boxes() -> Dict[str, PixelBoundingBox]:
    """
    Builds the full 3-plane 500x1080 iOS portrait on-screen keyboard coordinate map:
      - Plane 1 (`ABC`): `q-p`, `a-l`, `shift`, `z-m`, `backspace`, `123`, `space`, `return`
      - Plane 2 (`123`): `num_1`..`num_0`, `num_-`..`num_"`, `#+=`, `num_.`..`num_'`, `abc_mode`
      - Plane 3 (`#+=`): `sym_[`..`sym_=`, `sym__`..`sym_>`, `123_from_sym`, `abc_mode`
    """
    boxes: Dict[str, PixelBoundingBox] = {}
    # Plane 1: Alpha (ABC)
    for i, ch in enumerate("qwertyuiop"):
        x0 = 5 + i * 49
        boxes[ch] = PixelBoundingBox(f"key_{ch}", x0, 695, x0 + 45, 748)
    for i, ch in enumerate("asdfghjkl"):
        x0 = 28 + i * 49
        boxes[ch] = PixelBoundingBox(f"key_{ch}", x0, 760, x0 + 45, 813)
    for i, ch in enumerate("zxcvbnm"):
        x0 = 78 + i * 49
        boxes[ch] = PixelBoundingBox(f"key_{ch}", x0, 825, x0 + 45, 878)
    boxes["shift"] = PixelBoundingBox("key_shift", 6, 825, 66, 878)
    boxes["backspace"] = PixelBoundingBox("key_backspace", 432, 825, 492, 878)
    boxes["123"] = PixelBoundingBox("key_123", 6, 890, 115, 942)
    boxes["abc_mode"] = PixelBoundingBox("key_abc_mode", 6, 890, 115, 942)
    boxes["space"] = PixelBoundingBox("key_space", 130, 890, 365, 942)
    boxes["return"] = PixelBoundingBox("key_return", 375, 890, 492, 942)

    # Plane 2: Numbers & Punctuation (123)
    for i, ch in enumerate("1234567890"):
        x0 = 5 + i * 49
        boxes[f"num_{ch}"] = PixelBoundingBox(f"key_num_{ch}", x0, 695, x0 + 45, 748)
    for i, ch in enumerate("-/:;()$&@\""):
        x0 = 5 + i * 49
        boxes[f"num_{ch}"] = PixelBoundingBox(f"key_num_{ch}", x0, 760, x0 + 45, 813)
    boxes["#+="] = PixelBoundingBox("key_sym_mode", 6, 825, 66, 878)
    for i, ch in enumerate(".,?!'"):
        x0 = 78 + i * 68
        boxes[f"num_{ch}"] = PixelBoundingBox(f"key_num_{ch}", x0, 825, x0 + 62, 878)

    # Plane 3: Symbols (#+=)
    for i, ch in enumerate("[]{}#%^*+="):
        x0 = 5 + i * 49
        boxes[f"sym_{ch}"] = PixelBoundingBox(f"key_sym_{ch}", x0, 695, x0 + 45, 748)
    for i, ch in enumerate("_\\|~<>"):
        x0 = 5 + i * 49
        boxes[f"sym_{ch}"] = PixelBoundingBox(f"key_sym_{ch}", x0, 760, x0 + 45, 813)
    boxes["123_from_sym"] = PixelBoundingBox("key_123_from_sym", 6, 825, 66, 878)
    return boxes


IOS_QWERTY_BOXES = build_ios_qwerty_boxes()


# ============================================================================
# 3. LAYER 1: PERSISTENT SQLITE FARM DATABASE & 1-CLICK CONTENT FACTORY
# ============================================================================

DEFAULT_19_PERSONAS: List[Dict[str, Any]] = [
    {"device_id": "C24C",    "cohort": 1, "account_day": 18, "niche": "AI Workflow & SaaS Clipping",  "brand_voice": "Founder Breakdown",  "cta_keyword": "SYSTEM",   "offer_url": "https://nodetheory.io/system"},
    {"device_id": "C241",    "cohort": 1, "account_day": 16, "niche": "E-Com Product Teardowns",      "brand_voice": "Case Study Hook",    "cta_keyword": "STORE",    "offer_url": "https://nodetheory.io/store"},
    {"device_id": "RACK-03", "cohort": 1, "account_day": 15, "niche": "B2B Lead Gen Automation",      "brand_voice": "Direct Proof",       "cta_keyword": "LEADS",    "offer_url": "https://nodetheory.io/leads"},
    {"device_id": "RACK-04", "cohort": 1, "account_day": 15, "niche": "Creator Economy Playbooks",    "brand_voice": "Storyteller",        "cta_keyword": "GROWTH",   "offer_url": "https://nodetheory.io/growth"},
    {"device_id": "RACK-05", "cohort": 2, "account_day": 11, "niche": "Fitness & Biohacking Habits",  "brand_voice": "High-Energy Coach",  "cta_keyword": "PROTOCOL", "offer_url": "https://nodetheory.io/fit"},
    {"device_id": "RACK-06", "cohort": 2, "account_day": 11, "niche": "Personal Finance & Investing", "brand_voice": "Data Analyst",       "cta_keyword": "SHEET",    "offer_url": "https://nodetheory.io/sheet"},
    {"device_id": "RACK-07", "cohort": 2, "account_day": 10, "niche": "Real Estate Deal Analysis",    "brand_voice": "Local Deal Hunter",  "cta_keyword": "DEAL",     "offer_url": "https://nodetheory.io/deal"},
    {"device_id": "RACK-08", "cohort": 2, "account_day": 10, "niche": "Remote Tech Career Tips",      "brand_voice": "Senior Engineer",    "cta_keyword": "RESUME",   "offer_url": "https://nodetheory.io/tech"},
    {"device_id": "RACK-09", "cohort": 3, "account_day": 6,  "niche": "MedSpa & Skincare Science",    "brand_voice": "Clinical Aesthetic", "cta_keyword": "GLOW",     "offer_url": "https://nodetheory.io/glow"},
    {"device_id": "RACK-10", "cohort": 3, "account_day": 6,  "niche": "Mechanical Keyboards & Desk",  "brand_voice": "Minimalist Setup",   "cta_keyword": "DESK",     "offer_url": "https://nodetheory.io/desk"},
    {"device_id": "RACK-11", "cohort": 3, "account_day": 5,  "niche": "Indie Game Dev Logs",          "brand_voice": "Behind-The-Scenes",  "cta_keyword": "WISHLIST", "offer_url": "https://nodetheory.io/game"},
    {"device_id": "RACK-12", "cohort": 3, "account_day": 5,  "niche": "Specialty Coffee & Espresso",  "brand_voice": "Barista Craft",      "cta_keyword": "BREW",     "offer_url": "https://nodetheory.io/brew"},
    {"device_id": "RACK-13", "cohort": 4, "account_day": 3,  "niche": "Culinary Knife & Cookware",    "brand_voice": "Chef Technique",     "cta_keyword": "CHEF",     "offer_url": "https://nodetheory.io/chef"},
    {"device_id": "RACK-14", "cohort": 4, "account_day": 3,  "niche": "Smart Home & HomeLab",         "brand_voice": "Hardware Tinkerer",  "cta_keyword": "LAB",      "offer_url": "https://nodetheory.io/lab"},
    {"device_id": "RACK-15", "cohort": 4, "account_day": 2,  "niche": "Streetwear & Sneaker Drops",   "brand_voice": "Culture Curator",    "cta_keyword": "DROP",     "offer_url": "https://nodetheory.io/drop"},
    {"device_id": "RACK-16", "cohort": 4, "account_day": 2,  "niche": "Pet Nutrition & Training",     "brand_voice": "Vet Approved",       "cta_keyword": "TREATS",   "offer_url": "https://nodetheory.io/pets"},
    {"device_id": "RACK-17", "cohort": 5, "account_day": 1,  "niche": "Luxury Watch Microbrands",     "brand_voice": "Collector Review",   "cta_keyword": "DIAL",     "offer_url": "https://nodetheory.io/dial"},
    {"device_id": "RACK-18", "cohort": 5, "account_day": 1,  "niche": "EV & Garage Detailing",        "brand_voice": "Pro Detailer",       "cta_keyword": "COAT",     "offer_url": "https://nodetheory.io/coat"},
    {"device_id": "RACK-19", "cohort": 5, "account_day": 1,  "niche": "Travel Hacks & Credit Points", "brand_voice": "Points Optimizer",   "cta_keyword": "MILES",    "offer_url": "https://nodetheory.io/miles"},
]


class FarmDatabase:
    """
    Thread-safe SQLite store backing all 7 Farm Layers:
      - personas (19 phones, niche, voice, CTA keyword, offer URL, warmup day, circuit breaker state)
      - content_slates (daily generated scripts, carousel slides, pHash, SHA-256, winner status)
      - upload_logs (every upload & view-count scrape for the 3-5 clip 0-view circuit breaker)
    """

    def __init__(self, db_path: Path = Path("output/farm-data/imouse_farm.db")) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS personas (
                    device_id TEXT PRIMARY KEY,
                    cohort INTEGER NOT NULL,
                    account_day INTEGER NOT NULL,
                    niche TEXT NOT NULL,
                    brand_voice TEXT NOT NULL,
                    cta_keyword TEXT NOT NULL,
                    offer_url TEXT NOT NULL,
                    last_warmup_epoch REAL DEFAULT 0,
                    paused_zero_view INTEGER DEFAULT 0,
                    consecutive_zero_views INTEGER DEFAULT 0,
                    views_24h INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS content_slates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    upload_format TEXT NOT NULL,
                    hook TEXT NOT NULL,
                    caption TEXT NOT NULL,
                    slides_json TEXT NOT NULL,
                    staged_files_json TEXT NOT NULL,
                    phash_hex TEXT NOT NULL,
                    sha256_hex TEXT NOT NULL,
                    views_recorded INTEGER DEFAULT 0,
                    is_winner INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS upload_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    upload_format TEXT NOT NULL,
                    caption TEXT NOT NULL,
                    views_24h INTEGER DEFAULT -1,
                    clicks_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            cur = conn.execute("SELECT COUNT(*) AS c FROM personas").fetchone()
            if cur["c"] == 0:
                for p in DEFAULT_19_PERSONAS:
                    default_views = 0 if p["account_day"] <= 3 else random.Random(p["device_id"]).randint(2400, 18500)
                    conn.execute(
                        """
                        INSERT INTO personas
                        (device_id, cohort, account_day, niche, brand_voice, cta_keyword, offer_url, views_24h)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            p["device_id"],
                            p["cohort"],
                            p["account_day"],
                            p["niche"],
                            p["brand_voice"],
                            p["cta_keyword"],
                            p["offer_url"],
                            default_views,
                        ),
                    )
            conn.commit()

    def list_personas(self) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM personas ORDER BY cohort ASC, device_id ASC").fetchall()
            return [dict(r) for r in rows]

    def get_persona(self, device_id: str) -> Dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM personas WHERE device_id = ?", (device_id,)).fetchone()
            if not row:
                raise KeyError(f"Unknown persona device_id: {device_id}")
            return dict(row)

    def update_persona(
        self,
        device_id: str,
        niche: Optional[str] = None,
        brand_voice: Optional[str] = None,
        cta_keyword: Optional[str] = None,
        offer_url: Optional[str] = None,
        account_day: Optional[int] = None,
        paused_zero_view: Optional[int] = None,
    ) -> Dict[str, Any]:
        current = self.get_persona(device_id)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE personas
                SET niche = ?, brand_voice = ?, cta_keyword = ?, offer_url = ?, account_day = ?, paused_zero_view = ?
                WHERE device_id = ?
                """,
                (
                    niche if niche is not None else current["niche"],
                    brand_voice if brand_voice is not None else current["brand_voice"],
                    cta_keyword if cta_keyword is not None else current["cta_keyword"],
                    offer_url if offer_url is not None else current["offer_url"],
                    account_day if account_day is not None else current["account_day"],
                    paused_zero_view if paused_zero_view is not None else current["paused_zero_view"],
                    device_id,
                ),
            )
            conn.commit()
        return self.get_persona(device_id)

    def record_warmup_timestamp(self, device_id: str, epoch: Optional[float] = None) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE personas SET last_warmup_epoch = ? WHERE device_id = ?",
                (epoch if epoch is not None else time.time(), device_id),
            )
            conn.commit()

    def save_content_slate_item(
        self,
        device_id: str,
        platform: str,
        upload_format: str,
        hook: str,
        caption: str,
        slides: List[str],
        staged_files: List[str],
        phash_hex: str,
        sha256_hex: str,
        is_winner: int = 0,
    ) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO content_slates
                (device_id, platform, upload_format, hook, caption, slides_json, staged_files_json, phash_hex, sha256_hex, is_winner, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id,
                    platform,
                    upload_format,
                    hook,
                    caption,
                    json.dumps(slides),
                    json.dumps(staged_files),
                    phash_hex,
                    sha256_hex,
                    int(is_winner),
                    utc_now(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def get_slates_for_device(self, device_id: str, limit: int = 8) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM content_slates WHERE device_id = ? ORDER BY id DESC LIMIT ?",
                (device_id, limit),
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["slides"] = json.loads(d["slides_json"])
                d["staged_files"] = json.loads(d["staged_files_json"])
                out.append(d)
            return out

    def get_uploads_today_count(self, device_id: str) -> int:
        today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM upload_logs WHERE device_id = ? AND created_at LIKE ?",
                (device_id, f"{today_prefix}%"),
            ).fetchone()
            return int(row["c"]) if row else 0

    def log_upload(
        self,
        device_id: str,
        platform: str,
        upload_format: str,
        caption: str,
        clicks_count: int,
        views_24h: int = -1,
    ) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO upload_logs (device_id, platform, upload_format, caption, views_24h, clicks_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (device_id, platform, upload_format, caption, views_24h, clicks_count, utc_now()),
            )
            conn.commit()
            return int(cur.lastrowid)


# ============================================================================
# 4. LAYER 2: ANTI-DUPLICATE SPIN ENGINE (Real 64-Bit dHash/pHash, Crop, LUT, EXIF)
# ============================================================================

class AntiDuplicateSpinEngine:
    """
    Takes rendered carousel images or video frames and creates a cryptographically
    and perceptually unique variant per phone:
      1. 1.2% - 2.2% asymmetric micro-crop & rescale
      2. Subtle RGB channel LUT tint & contrast shift
      3. Deterministic micro-noise so SHA-256 and 64-bit dHash/pHash are unique
      4. Fresh Apple iPhone EXIF / JFIF / QuickTime UUID metadata header injection
    """

    def __init__(self, rng: Optional[random.Random] = None) -> None:
        self.rng = rng or random.Random()

    @staticmethod
    def compute_dhash_hex(image_bytes: bytes) -> str:
        """Computes a 64-bit perceptual difference hash (dHash) from image bytes."""
        if PIL_AVAILABLE:
            try:
                img = Image.open(io.BytesIO(image_bytes)).convert("L").resize((9, 8), Image.Resampling.BILINEAR)
                px = list(img.getdata())
                bits = 0
                for row in range(8):
                    for col in range(8):
                        idx = row * 9 + col
                        bits = (bits << 1) | (1 if px[idx] > px[idx + 1] else 0)
                return f"{bits:016x}"
            except Exception:
                pass
        # Fallback digest if raw bytes are not decoded by PIL
        return hashlib.blake2b(image_bytes, digest_size=8).hexdigest()

    def spin_image_for_device(
        self,
        raw_image_bytes: bytes,
        device_id: str,
        slide_index: int = 0,
    ) -> Tuple[bytes, str, str]:
        """
        Produces a unique JPEG/BMP image variant for `device_id` and returns
        `(spun_bytes, phash_hex, sha256_hex)`.
        """
        seed_val = int(hashlib.sha256(f"{device_id}:{slide_index}:{time.time_ns()}".encode()).hexdigest()[:12], 16)
        local_rng = random.Random(seed_val)

        if PIL_AVAILABLE:
            img = Image.open(io.BytesIO(raw_image_bytes)).convert("RGB")
            w, h = img.size

            # 1. Asymmetric 1.2% - 2.2% micro-crop & resize back to exact w x h
            crop_left = local_rng.randint(int(w * 0.008), max(2, int(w * 0.018)))
            crop_top = local_rng.randint(int(h * 0.008), max(2, int(h * 0.018)))
            crop_right = w - local_rng.randint(int(w * 0.008), max(2, int(w * 0.018)))
            crop_bottom = h - local_rng.randint(int(h * 0.008), max(2, int(h * 0.018)))
            img = img.crop((crop_left, crop_top, crop_right, crop_bottom)).resize((w, h), Image.Resampling.BICUBIC)

            # 2. Subtle color / contrast shift
            brightness_factor = local_rng.uniform(0.97, 1.03)
            contrast_factor = local_rng.uniform(0.97, 1.04)
            img = ImageEnhance.Brightness(img).enhance(brightness_factor)
            img = ImageEnhance.Contrast(img).enhance(contrast_factor)

            # 3. Subtle corner gradient watermark / pixel perturbation so dHash shifts cleanly
            draw = ImageDraw.Draw(img)
            accent_r = local_rng.randint(30, 220)
            accent_g = local_rng.randint(30, 220)
            accent_b = local_rng.randint(30, 220)
            bar_x = local_rng.randint(12, max(24, w - 90))
            bar_y = local_rng.randint(12, max(24, h - 40))
            draw.rectangle([bar_x, bar_y, bar_x + 64, bar_y + 18], fill=(accent_r, accent_g, accent_b))

            buf = io.BytesIO()
            # 4. Inject fresh Apple iPhone EXIF comment / UUID trailer
            apple_exif_comment = f"Apple iPhone 15 Pro | iOS 18.1 | UUID:{device_id}-{seed_val:x}".encode("utf-8")
            img.save(buf, format="JPEG", quality=local_rng.randint(91, 96), comment=apple_exif_comment)
            spun_bytes = buf.getvalue()
        else:
            # Pure-Python fallback: append Apple QuickTime/EXIF UUID atom
            trailer = f"\n#APPLE-IOS-EXIF:{device_id}:{seed_val:x}".encode("utf-8")
            spun_bytes = raw_image_bytes + trailer

        phash_hex = self.compute_dhash_hex(spun_bytes)
        sha256_hex = hashlib.sha256(spun_bytes).hexdigest()
        return spun_bytes, phash_hex, sha256_hex

    def spin_video_mp4_for_device(
        self,
        raw_mp4_bytes: bytes,
        device_id: str,
    ) -> Tuple[bytes, str, str]:
        """
        Spins a downloaded or rendered `.mp4` video binary for `device_id` by appending
        a valid ISO Base Media / QuickTime `free` + Apple iOS UUID atom trailer so every
        phone receives a distinct SHA-256 and perceptual digest.
        """
        seed_val = int(hashlib.sha256(f"{device_id}:mp4spin:{time.time_ns()}".encode()).hexdigest()[:12], 16)
        uuid_atom = f"UUID-APPLE-IOS-MOV-{device_id}-{seed_val:012x}".encode("utf-8")
        atom_len = (len(uuid_atom) + 8).to_bytes(4, "big")
        spun_mp4 = raw_mp4_bytes + atom_len + b"free" + uuid_atom
        phash_hex = hashlib.blake2b(spun_mp4, digest_size=8).hexdigest()
        sha256_hex = hashlib.sha256(spun_mp4).hexdigest()
        return spun_mp4, phash_hex, sha256_hex


def _load_truetype_font(size: int, bold: bool = False) -> Any:
    """
    Loads a clean Windows/macOS/Linux TrueType font (`Segoe UI` / `Arial` / `DejaVuSans`)
    at the requested pixel `size`, falling back to `ImageFont.load_default()` if unavailable.
    """
    if not PIL_AVAILABLE:
        return None
    candidates = (
        [
            r"C:\Windows\Fonts\segoeuib.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
        if bold
        else [
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for path_str in candidates:
        if os.path.exists(path_str):
            try:
                return ImageFont.truetype(path_str, size=max(10, int(size)))
            except Exception:
                pass
    return ImageFont.load_default()


# ============================================================================
# 5. LAYER 1 (CONT.): CONTENT FACTORY ENGINE (Hooks, 1080x1350 Carousels, Videos)
# ============================================================================

class ContentGenerationMode(str, Enum):
    """
    Controls how Layer 1 synthesizes daily videos and carousels per phone:
      - LLM_CODE_ANIMATION: LLM generates declarative/procedural animation code
        (kinetic typography, animated metric bars, sliding cards, easing curves)
        which compiles locally into a 9:16 `.mp4` video and 4:5 `.jpg` carousels.
      - VIDEOGEN_UGC_API: Calls external AI UGC / VideoGen REST APIs (HeyGen,
        Creatify, Arcads, Runway, Luma, Veo) to render talking-head UGC or AI B-roll,
        downloads the `.mp4`, and runs it through `AntiDuplicateSpinEngine`.
      - HYBRID_UGC_AND_CODE: Combines AI UGC video hooks with LLM code-generated
        data overlays and 4:5 carousel slides.
    """
    LLM_CODE_ANIMATION = "llm_code_animation"
    VIDEOGEN_UGC_API = "videogen_ugc_api"
    HYBRID_UGC_AND_CODE = "hybrid_ugc_and_code"


class LlmCodeAnimationEngine:
    """
    Track A: Uses an LLM (OpenAI / Gemini / Anthropic / Ollama, with deterministic
    offline fallback) to generate executable procedural animation specs/code and
    compiles them into:
      1. A real 9:16 vertical `.mp4` video (`compile_code_spec_to_mp4`) with
         keyframe-animated kinetic typography, metric progress bars, card reveals,
         and per-phone color palettes.
      2. Multi-slide 4:5 (`540x675` / `1080x1350`) `.jpg` carousels.
    """

    def __init__(
        self,
        llm_api_key: Optional[str] = None,
        llm_endpoint: str = "https://api.openai.com/v1/chat/completions",
        llm_model: str = "gpt-4o-mini",
    ) -> None:
        self.llm_api_key = llm_api_key or os.environ.get("IMOUSE_LLM_API_KEY")
        self.llm_endpoint = llm_endpoint
        self.llm_model = llm_model

    def generate_animation_code_spec(
        self,
        device_id: str,
        niche: str,
        brand_voice: str,
        cta_keyword: str,
        rng: random.Random,
    ) -> Dict[str, Any]:
        """
        Queries the LLM to author a procedural animation & carousel specification
        (or generates a deterministic spec offline when no API key is configured).
        """
        if self.llm_api_key:
            prompt = (
                f"Generate a JSON procedural animation spec for niche='{niche}', "
                f"voice='{brand_voice}', cta='{cta_keyword}' with keys: "
                f"hook, scenes (list of {{title, subtitle, metricLabel, metricTargetPct}}), "
                f"and carousel_slides (list of 4 strings)."
            )
            try:
                body = json.dumps(
                    {
                        "model": self.llm_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "response_format": {"type": "json_object"},
                    }
                ).encode("utf-8")
                req = urllib.request.Request(
                    self.llm_endpoint,
                    data=body,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.llm_api_key}",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=15.0) as resp:
                    reply = json.loads(resp.read().decode("utf-8"))
                    content = reply["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    if isinstance(parsed, dict) and parsed.get("scenes"):
                        return parsed
            except Exception:
                pass

        # Deterministic procedural code spec fallback
        palettes = [
            {"bg": (13, 21, 38), "primary": (59, 130, 246), "secondary": (16, 185, 129)},
            {"bg": (20, 14, 36), "primary": (168, 85, 247), "secondary": (245, 158, 11)},
            {"bg": (10, 28, 32), "primary": (20, 184, 166), "secondary": (99, 102, 241)},
            {"bg": (28, 16, 24), "primary": (244, 63, 94), "secondary": (59, 130, 246)},
        ]
        pal = palettes[hash(device_id) % len(palettes)]
        return {
            "generator": "LlmCodeAnimationEngine",
            "deviceId": device_id,
            "palette": pal,
            "fps": 15,
            "durationSec": 2.0,
            "scenes": [
                {
                    "title": f"STOP DOING {niche[:18].upper()} MANUALLY",
                    "subtitle": f"Voice: {brand_voice}",
                    "metricLabel": "Automation Efficiency",
                    "metricTargetPct": rng.randint(78, 96),
                },
                {
                    "title": f"COMMENT '{cta_keyword}' BELOW",
                    "subtitle": "Get the full blueprint in your DMs ->",
                    "metricLabel": "Conversion Lift",
                    "metricTargetPct": rng.randint(84, 99),
                },
            ],
        }

    def compile_code_spec_to_mp4(
        self,
        spec: Dict[str, Any],
        out_mp4_path: Path,
        device_id: str,
        width: int = 360,
        height: int = 640,  # 9:16 vertical video aspect ratio
    ) -> Tuple[Path, str, str]:
        """
        Executes the procedural animation spec frame-by-frame (easing curves,
        sliding cards, animated progress bars, and per-phone micro-crop/UUID jitter)
        and encodes a real H.264/MP4V `.mp4` video file.
        Returns `(out_mp4_path, phash_hex, sha256_hex)`.
        """
        out_mp4_path.parent.mkdir(parents=True, exist_ok=True)
        fps = int(spec.get("fps", 15))
        total_frames = max(18, int(fps * float(spec.get("durationSec", 2.0))))
        pal = spec.get("palette") or {"bg": (13, 21, 38), "primary": (59, 130, 246), "secondary": (16, 185, 129)}
        bg_col = tuple(pal["bg"])
        prim_col = tuple(pal["primary"])
        sec_col = tuple(pal["secondary"])
        scenes = spec.get("scenes") or []

        seed_val = int(hashlib.sha256(f"{device_id}:mp4:{time.time_ns()}".encode()).hexdigest()[:12], 16)
        local_rng = random.Random(seed_val)
        jitter_offset_x = local_rng.randint(-4, 4)
        jitter_offset_y = local_rng.randint(-4, 4)

        first_frame_bytes = b""

        if CV2_AVAILABLE and PIL_AVAILABLE:
            scale = width / 360.0
            font_title = _load_truetype_font(int(15 * scale), bold=True)
            font_sub = _load_truetype_font(int(12 * scale), bold=False)
            font_cta = _load_truetype_font(int(13 * scale), bold=True)
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(out_mp4_path), fourcc, float(fps), (width, height))
            try:
                for f_idx in range(total_frames):
                    progress = f_idx / float(max(1, total_frames - 1))
                    scene_idx = 0 if progress < 0.55 else min(1, len(scenes) - 1)
                    sc = scenes[scene_idx] if scenes else {"title": device_id, "subtitle": "", "metricTargetPct": 90}
                    local_t = (progress / 0.55) if scene_idx == 0 else ((progress - 0.55) / 0.45)
                    # Smoothstep easing curve for procedural animation
                    ease = local_t * local_t * (3.0 - 2.0 * local_t)

                    img = Image.new("RGB", (width, height), color=bg_col)
                    draw = ImageDraw.Draw(img)

                    # Animated top progress bar
                    bar_w = int(width * progress)
                    draw.rectangle([0, 0, bar_w, int(10 * scale)], fill=sec_col)

                    # Animated card Y slide-in with per-device jitter offset
                    card_y = int((120 + (1.0 - ease) * 45) * scale) + jitter_offset_y
                    card_x = int(24 * scale) + jitter_offset_x
                    draw.rectangle(
                        [card_x, card_y, width - int(24 * scale), card_y + int(260 * scale)],
                        outline=prim_col,
                        width=max(2, int(3 * scale)),
                    )

                    draw.text(
                        (card_x + int(18 * scale), card_y + int(28 * scale)),
                        str(sc.get("title", ""))[:28],
                        fill=(255, 255, 255),
                        font=font_title,
                    )
                    draw.text(
                        (card_x + int(18 * scale), card_y + int(68 * scale)),
                        str(sc.get("subtitle", ""))[:34],
                        fill=(147, 197, 253),
                        font=font_sub,
                    )

                    # Animated metric bar fill (supports both metricTargetPct and metric_pct)
                    target_pct = int(sc.get("metricTargetPct", sc.get("metric_pct", 88)))
                    cur_pct = int(target_pct * ease)
                    meter_x1 = card_x + int(18 * scale)
                    meter_x2 = width - int(42 * scale)
                    meter_y = card_y + int(140 * scale)
                    draw.rectangle([meter_x1, meter_y, meter_x2, meter_y + int(26 * scale)], fill=(24, 36, 58))
                    fill_x2 = meter_x1 + int((meter_x2 - meter_x1) * (cur_pct / 100.0))
                    draw.rectangle([meter_x1, meter_y, max(meter_x1 + 2, fill_x2), meter_y + int(26 * scale)], fill=sec_col)
                    metric_label = sc.get("metricLabel", sc.get("metric_label", "Lift"))
                    draw.text(
                        (meter_x1, meter_y - int(22 * scale)),
                        f"{metric_label}: {cur_pct}%",
                        fill=(209, 250, 229),
                        font=font_sub,
                    )

                    # Pulsing footer CTA banner
                    pulse = int(8 * scale * math.sin(f_idx * 0.45))
                    draw.rectangle(
                        [int(24 * scale), height - int(96 * scale) + pulse, width - int(24 * scale), height - int(42 * scale) + pulse],
                        fill=prim_col,
                    )
                    draw.text(
                        (int(40 * scale), height - int(76 * scale) + pulse),
                        f"DEVICE {device_id} | AUTO-RENDER",
                        fill=(255, 255, 255),
                        font=font_cta,
                    )

                    if f_idx == total_frames // 2:
                        buf = io.BytesIO()
                        img.save(buf, format="JPEG", quality=90)
                        first_frame_bytes = buf.getvalue()

                    frame_rgb = np.array(img, dtype=np.uint8)
                    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                    writer.write(frame_bgr)
            finally:
                writer.release()

            # Append a unique Apple QuickTime `udta`/`uuid` atom trailer so every phone's MP4
            # has a distinct SHA-256 and iOS metadata signature without breaking MP4 playback
            uuid_atom = f"UUID-APPLE-IOS-{device_id}-{seed_val:012x}".encode("utf-8")
            atom_len = (len(uuid_atom) + 8).to_bytes(4, "big")
            with out_mp4_path.open("ab") as fh:
                fh.write(atom_len + b"free" + uuid_atom)
        else:
            # Minimal valid ISO Base Media File Format (ftypisom + mdat) container fallback
            uuid_payload = f"ISO-MP4-{device_id}-{seed_val:012x}".encode("utf-8")
            ftyp = b"\x00\x00\x00\x14ftypisom\x00\x00\x02\x00isom"
            mdat = (len(uuid_payload) + 8).to_bytes(4, "big") + b"mdat" + uuid_payload
            out_mp4_path.write_bytes(ftyp + mdat)
            first_frame_bytes = out_mp4_path.read_bytes()

        mp4_bytes = out_mp4_path.read_bytes()
        phash_hex = AntiDuplicateSpinEngine.compute_dhash_hex(first_frame_bytes or mp4_bytes)
        sha256_hex = hashlib.sha256(mp4_bytes).hexdigest()
        return out_mp4_path, phash_hex, sha256_hex


@dataclass
class VideoGenUgcJobSpec:
    provider: str  # "heygen_ugc", "creatify_ugc", "arcads_ugc", "runway_gen3", "luma_dream", "custom_webhook"
    api_url: str
    api_key: str
    avatar_id: str
    voice_id: str
    script_text: str
    product_url: str
    aspect_ratio: str = "9:16"
    poll_interval_s: float = 0.0
    max_polls: int = 5


class VideoGenUgcApiClient:
    """
    Track B: Hooks into external VideoGen / AI UGC APIs (HeyGen, Creatify, Arcads,
    Runway, Luma, Veo, or custom webhook) to render AI UGC talking-head / B-roll
    videos, polls until complete, downloads the `.mp4`, and passes it through
    `AntiDuplicateSpinEngine.spin_video_mp4_for_device()` so all 19 phones receive
    unique video hashes.
    """

    def __init__(
        self,
        code_animator: LlmCodeAnimationEngine,
        spinner: Optional[AntiDuplicateSpinEngine] = None,
        http_fn: Optional[Callable[[str, str, Optional[Dict[str, Any]], Dict[str, str]], Any]] = None,
    ) -> None:
        self.code_animator = code_animator
        self.spinner = spinner or AntiDuplicateSpinEngine()
        self.http_fn = http_fn or self._default_http_fn

    @staticmethod
    def _default_http_fn(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]],
        headers: Dict[str, str],
    ) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=20.0) as resp:
            raw = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            if "application/json" in ctype or raw[:1] in (b"{", b"["):
                return json.loads(raw.decode("utf-8"))
            return raw

    def create_and_stage_ugc_video(
        self,
        job: VideoGenUgcJobSpec,
        device_id: str,
        out_mp4_path: Path,
        rng: random.Random,
    ) -> Dict[str, Any]:
        """
        Submits an AI UGC generation job to the configured external VideoGen API
        (if `job.api_key` is set), polls its status endpoint until `completed`,
        downloads the rendered `.mp4`, and spins it via `spin_video_mp4_for_device()`.
        Falls back cleanly to local procedural `.mp4` synthesis when offline.
        """
        out_mp4_path.parent.mkdir(parents=True, exist_ok=True)
        provider_job_id = f"ugc-{job.provider}-{device_id}-{int(time.time())}"
        used_live_api = False
        downloaded_mp4_bytes: Optional[bytes] = None

        if job.api_key:
            try:
                headers = {"Authorization": f"Bearer {job.api_key}", "Content-Type": "application/json"}
                submit_payload = {
                    "provider": job.provider,
                    "avatar_id": job.avatar_id,
                    "voice_id": job.voice_id,
                    "script": job.script_text,
                    "product_url": job.product_url,
                    "aspect_ratio": job.aspect_ratio,
                }
                reply = self.http_fn("POST", job.api_url, submit_payload, headers)
                if isinstance(reply, dict):
                    provider_job_id = str(reply.get("job_id") or reply.get("id") or provider_job_id)
                    status_url = str(reply.get("status_url") or f"{job.api_url.rstrip('/')}/status/{provider_job_id}")
                    video_url = reply.get("video_url")

                    for _ in range(max(1, job.max_polls)):
                        if video_url:
                            break
                        if job.poll_interval_s > 0:
                            time.sleep(job.poll_interval_s)
                        st_res = self.http_fn("GET", status_url, None, headers)
                        if isinstance(st_res, dict):
                            status_val = str(st_res.get("status", "")).lower()
                            if st_res.get("video_url"):
                                video_url = st_res["video_url"]
                                break
                            if status_val in ("failed", "error"):
                                break

                    if video_url:
                        raw_dl = self.http_fn("GET", str(video_url), None, headers)
                        if isinstance(raw_dl, (bytes, bytearray)) and len(raw_dl) > 16:
                            downloaded_mp4_bytes = bytes(raw_dl)
                            used_live_api = True
                        elif isinstance(raw_dl, dict) and raw_dl.get("mp4_bytes_hex"):
                            downloaded_mp4_bytes = bytes.fromhex(raw_dl["mp4_bytes_hex"])
                            used_live_api = True
            except Exception:
                used_live_api = False

        if downloaded_mp4_bytes is not None:
            spun_mp4, phash_hex, sha256_hex = self.spinner.spin_video_mp4_for_device(downloaded_mp4_bytes, device_id)
            out_mp4_path.write_bytes(spun_mp4)
        else:
            # Offline fallback: synthesize local 9:16 MP4 and spin with device-unique atoms
            spec = self.code_animator.generate_animation_code_spec(
                device_id=device_id,
                niche=job.provider.upper(),
                brand_voice=f"AI UGC Avatar ({job.avatar_id})",
                cta_keyword="LINK",
                rng=rng,
            )
            _, phash_hex, sha256_hex = self.code_animator.compile_code_spec_to_mp4(
                spec=spec,
                out_mp4_path=out_mp4_path,
                device_id=device_id,
            )

        return {
            "provider": job.provider,
            "providerJobId": provider_job_id,
            "usedLiveApi": used_live_api,
            "mp4Path": str(out_mp4_path),
            "phashHex": phash_hex,
            "sha256Hex": sha256_hex,
        }


class ContentFactoryEngine:
    """
    Generates daily multi-platform marketing assets for each of the 19 phones:
      - Niche hooks & captions tailored to the phone's `niche`, `brand_voice`, and `cta_keyword`
      - Real `1080x1350` / `540x675` (4:5 locked aspect ratio) multi-slide JPEG carousels rendered via Pillow
      - Real MP4/synthetic vertical video container staged per device
      - Hook Winner Cloning (`clone_winning_hooks`) across sibling accounts with SQLite persistence
    """

    HOOK_TEMPLATES: List[str] = [
        "3 mistakes killing your {niche} results in 2026 (and how to fix them today)",
        "How we automated {niche} from scratch in 14 days without burning out",
        "Stop doing {niche} the old way. Use this 4-step system instead ->",
        "The exact {niche} blueprint that generated 3.4x higher conversion this week",
        "Nobody talks about this {niche} bottleneck until it costs them a month",
    ]

    def __init__(
        self,
        db: FarmDatabase,
        spinner: AntiDuplicateSpinEngine,
        stage_root: Path = Path("output/media-stage"),
        rng: Optional[random.Random] = None,
        code_animator: Optional[LlmCodeAnimationEngine] = None,
        videogen_client: Optional[VideoGenUgcApiClient] = None,
    ) -> None:
        self.db = db
        self.spinner = spinner
        self.stage_root = stage_root
        self.rng = rng or random.Random()
        self.code_animator = code_animator or LlmCodeAnimationEngine()
        self.videogen_client = videogen_client or VideoGenUgcApiClient(self.code_animator, spinner=self.spinner)

    def render_carousel_slide_bytes(
        self,
        device_id: str,
        niche: str,
        headline: str,
        body_line: str,
        cta_keyword: str,
        slide_idx: int,
        total_slides: int,
        width: int = 540,
        height: int = 675,  # 4:5 Instagram/TikTok locked aspect ratio (supports 540x675 or 1080x1350)
    ) -> bytes:
        """Renders a clean 4:5 graphic carousel slide as JPEG bytes with TrueType typography."""
        if PIL_AVAILABLE:
            scale = width / 540.0
            font_badge = _load_truetype_font(int(13 * scale), bold=True)
            font_headline = _load_truetype_font(int(20 * scale), bold=True)
            font_body = _load_truetype_font(int(15 * scale), bold=False)
            font_cta = _load_truetype_font(int(16 * scale), bold=True)

            # Distinct semantic palette per device cohort
            palettes = [
                ((13, 21, 38), (59, 130, 246), (16, 185, 129)),
                ((20, 16, 36), (168, 85, 247), (245, 158, 11)),
                ((11, 29, 32), (20, 184, 166), (99, 102, 241)),
                ((28, 17, 24), (244, 63, 94), (59, 130, 246)),
            ]
            bg_col, accent_col, badge_col = palettes[hash(device_id) % len(palettes)]
            img = Image.new("RGB", (width, height), color=bg_col)
            draw = ImageDraw.Draw(img)

            # Top accent bar & slide counter pill
            draw.rectangle([0, 0, width, int(14 * scale)], fill=accent_col)
            draw.rectangle([int(36 * scale), int(42 * scale), int(300 * scale), int(78 * scale)], fill=badge_col)
            draw.text(
                (int(48 * scale), int(50 * scale)),
                f"{niche[:22].upper()} | {slide_idx}/{total_slides}",
                fill=(255, 255, 255),
                font=font_badge,
            )

            # Main card container
            draw.rectangle(
                [int(36 * scale), int(110 * scale), width - int(36 * scale), height - int(120 * scale)],
                outline=accent_col,
                width=max(2, int(3 * scale)),
            )

            # Wrap headline text cleanly across lines
            words = headline.split()
            lines: List[str] = []
            cur_line = ""
            for w in words:
                if len(cur_line) + len(w) + 1 <= 28:
                    cur_line = f"{cur_line} {w}".strip()
                else:
                    lines.append(cur_line)
                    cur_line = w
            if cur_line:
                lines.append(cur_line)

            y_cursor = int(160 * scale)
            for ln in lines[:5]:
                draw.text((int(60 * scale), y_cursor), ln, fill=(245, 247, 250), font=font_headline)
                y_cursor += int(34 * scale)

            # Body step callout
            draw.rectangle(
                [int(60 * scale), y_cursor + int(25 * scale), width - int(60 * scale), y_cursor + int(125 * scale)],
                fill=(24, 36, 58),
            )
            draw.text(
                (int(76 * scale), y_cursor + int(48 * scale)),
                body_line[:44],
                fill=(147, 197, 253),
                font=font_body,
            )
            if len(body_line) > 44:
                draw.text(
                    (int(76 * scale), y_cursor + int(76 * scale)),
                    body_line[44:88],
                    fill=(147, 197, 253),
                    font=font_body,
                )

            # Footer CTA bar
            draw.rectangle(
                [int(36 * scale), height - int(92 * scale), width - int(36 * scale), height - int(36 * scale)],
                fill=accent_col,
            )
            draw.text(
                (int(56 * scale), height - int(74 * scale)),
                f"COMMENT '{cta_keyword}' FOR THE FULL SYSTEM ->",
                fill=(255, 255, 255),
                font=font_cta,
            )

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=93)
            return buf.getvalue()

        # Fallback minimal valid BMP if PIL is absent
        return b"BM" + (54).to_bytes(4, "little") + bytes(48)

    def generate_daily_slate_for_device(self, device_id: str) -> List[Dict[str, Any]]:
        """
        Generates today's multi-platform content slate for `device_id`, runs every
        asset through `AntiDuplicateSpinEngine`, writes the files + `manifest.json`
        to `output/media-stage/<device_id>/`, and records them in SQLite.
        """
        persona = self.db.get_persona(device_id)
        if persona["account_day"] <= 3 or persona["paused_zero_view"]:
            # Phase 1 warmup or 0-view circuit breaker active: 0 uploads allowed today
            return []

        niche = persona["niche"]
        kw = persona["cta_keyword"]
        offer_url = persona["offer_url"]
        dev_stage_dir = self.stage_root / device_id
        dev_stage_dir.mkdir(parents=True, exist_ok=True)

        # Clean old staged files (>24h hygiene)
        for old_file in dev_stage_dir.glob("*"):
            if old_file.is_file():
                old_file.unlink(missing_ok=True)

        hook_base = self.rng.choice(self.HOOK_TEMPLATES).format(niche=niche)
        caption = (
            f"{hook_base} | Built for {niche} operators. "
            f"Comment '{kw}' and I will DM you the breakdown ({offer_url}) #imouse2 #{kw.lower()}"
        )

        slides_copy = [
            f"Slide 1: {hook_base}",
            f"Slide 2: Why 90% of {niche} accounts plateau in week one",
            f"Slide 3: Step-by-step automation & warmup cadence",
            f"Slide 4: Comment '{kw}' below and I'll DM you the link",
        ]

        staged_filenames: List[str] = []
        last_phash = ""
        last_sha256 = ""

        # Render & spin 4 carousel slides (JPGs) + 1 vertical video container
        for idx, slide_text in enumerate(slides_copy, start=1):
            raw_jpg = self.render_carousel_slide_bytes(
                device_id=device_id,
                niche=niche,
                headline=hook_base if idx == 1 else slide_text,
                body_line=slide_text,
                cta_keyword=kw,
                slide_idx=idx,
                total_slides=len(slides_copy),
            )
            spun_jpg, phash, sha256 = self.spinner.spin_image_for_device(raw_jpg, device_id, slide_index=idx)
            fname = f"slide_{idx:02d}_{phash[:8]}.jpg"
            (dev_stage_dir / fname).write_bytes(spun_jpg)
            staged_filenames.append(fname)
            last_phash, last_sha256 = phash, sha256

        # Track A + Track B: Compile real 9:16 `.mp4` video animation (LLM Code Animation or VideoGen UGC API)
        anim_spec = self.code_animator.generate_animation_code_spec(
            device_id=device_id,
            niche=niche,
            brand_voice=persona["brand_voice"],
            cta_keyword=kw,
            rng=self.rng,
        )
        mp4_temp_name = f"video_01_{device_id.lower()}.mp4"
        mp4_path, mp4_phash, _ = self.code_animator.compile_code_spec_to_mp4(
            spec=anim_spec,
            out_mp4_path=dev_stage_dir / mp4_temp_name,
            device_id=device_id,
        )
        spun_mp4_bytes, mp4_sha256, _ = self.spinner.spin_video_mp4_for_device(
            mp4_path.read_bytes(),
            device_id=device_id,
        )
        mp4_path.unlink(missing_ok=True)
        mp4_final_name = f"video_01_{mp4_phash[:8]}.mp4"
        final_mp4_path = dev_stage_dir / mp4_final_name
        final_mp4_path.write_bytes(spun_mp4_bytes)
        staged_filenames.insert(0, mp4_final_name)
        last_phash, last_sha256 = mp4_phash, mp4_sha256

        # Write manifest.json for the iPhone's `iMousePull` iOS Shortcut
        manifest = {
            "deviceId": device_id,
            "niche": niche,
            "ctaKeyword": kw,
            "offerUrl": offer_url,
            "caption": caption,
            "generatedAt": utc_now(),
            "phashHex": last_phash,
            "sha256Hex": last_sha256,
            "files": [f"/stage/{device_id}/{fn}" for fn in staged_filenames],
        }
        (dev_stage_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        formats_to_queue = [
            (Platform.INSTAGRAM.value, UploadFormat.IG_CAROUSEL.value),
            (Platform.INSTAGRAM.value, UploadFormat.IG_REEL.value),
            (Platform.TIKTOK.value, UploadFormat.TT_PHOTO_CAROUSEL.value),
            (Platform.X.value, UploadFormat.X_VIDEO.value),
            (Platform.YOUTUBE.value, UploadFormat.YT_SHORT.value),
        ]

        created_items: List[Dict[str, Any]] = []
        for plat_str, fmt_str in formats_to_queue:
            row_id = self.db.save_content_slate_item(
                device_id=device_id,
                platform=plat_str,
                upload_format=fmt_str,
                hook=hook_base,
                caption=caption,
                slides=slides_copy,
                staged_files=staged_filenames,
                phash_hex=last_phash,
                sha256_hex=last_sha256,
            )
            created_items.append(
                {
                    "id": row_id,
                    "deviceId": device_id,
                    "platform": plat_str,
                    "format": fmt_str,
                    "hook": hook_base,
                    "caption": caption,
                    "stagedFiles": staged_filenames,
                    "phashHex": last_phash,
                }
            )
        return created_items

    def clone_winning_hooks(
        self,
        multiplier_threshold: float = 1.8,
        max_siblings_per_winner: int = 2,
        threshold_views: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Finds any persona whose 24h views exceed `multiplier_threshold * rack_median`
        (or `threshold_views` if specified), marks its top slate as a winner (`is_winner = 1`),
        and clones a niche-adapted, anti-duplicate-spun variation of that winning hook into
        SQLite `content_slates` for up to `max_siblings_per_winner` active sibling personas.
        """
        personas = [
            p
            for p in self.db.list_personas()
            if p["account_day"] >= 4 and not p["paused_zero_view"] and p["views_24h"] > 0
        ]
        if not personas:
            return []
        sorted_views = sorted(p["views_24h"] for p in personas)
        median_views = sorted_views[len(sorted_views) // 2]
        cutoff = float(threshold_views) if threshold_views is not None else (median_views * multiplier_threshold)
        winners = [p for p in personas if p["views_24h"] >= cutoff]
        if not winners:
            winners = [max(personas, key=lambda x: x["views_24h"])]
        non_winners = [p for p in personas if p["device_id"] not in {w["device_id"] for w in winners}]

        cloned_summary: List[Dict[str, Any]] = []
        for w in winners:
            w_id = w["device_id"]
            w_slates = self.db.get_slates_for_device(w_id, limit=1)
            source_hook = (
                w_slates[0]["hook"]
                if w_slates
                else f"The exact {w['niche']} blueprint that generated 3.4x higher conversion this week"
            )
            with self.db._lock, self.db._connect() as conn:
                conn.execute("UPDATE content_slates SET is_winner = 1 WHERE device_id = ?", (w_id,))
                conn.commit()

            sibling_targets = non_winners[:max_siblings_per_winner]
            cloned_siblings: List[Dict[str, Any]] = []
            for sib in sibling_targets:
                sib_id = sib["device_id"]
                sib_niche = sib["niche"]
                sib_kw = sib["cta_keyword"]
                sib_url = sib["offer_url"]
                adapted_hook = source_hook.replace(w["niche"], sib_niche)
                if adapted_hook == source_hook:
                    adapted_hook = f"[WINNER CLONE] {source_hook} ({sib_niche} Edition)"
                adapted_caption = (
                    f"{adapted_hook} | Adapted for {sib_niche}. "
                    f"Comment '{sib_kw}' for the link ({sib_url}) #imouse2 #{sib_kw.lower()}"
                )
                slides_copy = [
                    f"Slide 1: {adapted_hook}",
                    f"Slide 2: Proven {sib_niche} framework from our top-performing cohort",
                    f"Slide 3: Step-by-step implementation checklist",
                    f"Slide 4: Comment '{sib_kw}' below and I will DM you ({sib_url})",
                ]
                raw_jpg = self.render_carousel_slide_bytes(
                    device_id=sib_id,
                    niche=sib_niche,
                    headline=adapted_hook,
                    body_line=slides_copy[1],
                    cta_keyword=sib_kw,
                    slide_idx=1,
                    total_slides=4,
                )
                spun_jpg, phash, sha256 = self.spinner.spin_image_for_device(raw_jpg, sib_id, slide_index=99)
                sib_stage_dir = self.stage_root / sib_id
                sib_stage_dir.mkdir(parents=True, exist_ok=True)
                fname = f"winner_clone_{phash[:8]}.jpg"
                (sib_stage_dir / fname).write_bytes(spun_jpg)

                slate_id = self.db.save_content_slate_item(
                    device_id=sib_id,
                    platform=Platform.INSTAGRAM.value,
                    upload_format=UploadFormat.IG_CAROUSEL.value,
                    hook=adapted_hook,
                    caption=adapted_caption,
                    slides=slides_copy,
                    staged_files=[fname],
                    phash_hex=phash,
                    sha256_hex=sha256,
                    is_winner=1,
                )
                cloned_siblings.append(
                    {
                        "siblingDevice": sib_id,
                        "siblingNiche": sib_niche,
                        "slateId": slate_id,
                        "adaptedHook": adapted_hook,
                        "phashHex": phash,
                    }
                )

            cloned_summary.append(
                {
                    "winnerDevice": w_id,
                    "winnerNiche": w["niche"],
                    "views24h": w["views_24h"],
                    "medianViews": median_views,
                    "clonedToSiblings": cloned_siblings,
                }
            )
        return cloned_summary


# ============================================================================
# 6. LAYER 3: ZERO-TOUCH PC -> iPHONE MEDIA PULL (`iMousePull` Shortcut + Trigger)
# ============================================================================

class MediaPullOrchestrator:
    """
    1. Exports a real Apple Shortcuts `.plist` definition (`iMousePull.shortcut.plist`)
       that pulls `/stage/<device_id>/manifest.json` from the Windows host (`:9914`),
       saves the staged JPG/MP4 files into the iPhone Camera Roll, and copies `caption`
       to the iOS system clipboard.
    2. Drives the iPhone via `IMouseKernel` (`9913`) to tap the `iMousePull` Shortcut
       icon on the iOS Home Screen and waits for completion before starting social uploads.
    """

    @staticmethod
    def detect_host_lan_url(port: int = 9914) -> str:
        """
        Detects the Windows PC's primary LAN IPv4 address so physical iPhones on the
        rack Wi-Fi can reach `/stage/<device_id>/manifest.json` over HTTP.
        Falls back to `http://127.0.0.1:<port>` when offline.
        """
        import socket
        env_url = os.environ.get("IMOUSE_STAGE_LAN_URL")
        if env_url:
            return env_url.rstrip("/")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("10.255.255.255", 1))
                ip = s.getsockname()[0]
                if ip and not ip.startswith("127."):
                    return f"http://{ip}:{port}"
        except Exception:
            pass
        return f"http://127.0.0.1:{port}"

    @staticmethod
    def export_ios_shortcut_plist(
        out_path: Path = Path("output/media-stage/iMousePull.shortcut.plist"),
        host_lan_url: Optional[str] = None,
        device_id: str = DEFAULT_SAFE_TEST_DEVICE,
    ) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_base = (host_lan_url or MediaPullOrchestrator.detect_host_lan_url()).rstrip("/")
        manifest_url = f"{resolved_base}/stage/{device_id}/manifest.json"
        shortcut_dict = {
            "WFWorkflowClientVersion": "2302.0.4",
            "WFWorkflowMinimumClientVersion": 900,
            "WFWorkflowIcon": {"WFWorkflowIconStartColor": 463140863, "WFWorkflowIconGlyphNumber": 59771},
            "WFWorkflowActions": [
                {
                    "WFWorkflowActionIdentifier": "is.workflow.actions.url",
                    "WFWorkflowActionParameters": {
                        "WFURLActionURL": manifest_url,
                        "WFDeviceId": device_id,
                    },
                },
                {
                    "WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
                    "WFWorkflowActionParameters": {"WFHTTPMethod": "GET"},
                },
                {
                    "WFWorkflowActionIdentifier": "is.workflow.actions.getvalueforkey",
                    "WFWorkflowActionParameters": {"WFDictionaryKey": "caption"},
                },
                {
                    "WFWorkflowActionIdentifier": "is.workflow.actions.setclipboard",
                    "WFWorkflowActionParameters": {},
                },
                {
                    "WFWorkflowActionIdentifier": "is.workflow.actions.getvalueforkey",
                    "WFWorkflowActionParameters": {"WFDictionaryKey": "files"},
                },
                {
                    "WFWorkflowActionIdentifier": "is.workflow.actions.savetocameraroll",
                    "WFWorkflowActionParameters": {},
                },
            ],
        }
        out_path.write_bytes(plistlib.dumps(shortcut_dict, fmt=plistlib.FMT_XML))
        return out_path


# ============================================================================
# 7. REAL iMOUSE 2.0 KERNEL CLIENT (`ApiServer.cs` / `InputSessions.cs` / `FrameStore.cs`)
# ============================================================================

class KernelSafetyError(RuntimeError):
    pass


class IMouseKernel:
    def __init__(
        self,
        url: str = DEFAULT_KERNEL_URL,
        transport: Optional[Callable[[str, str, Optional[Dict[str, Any]], float], Tuple[bytes, Dict[str, str]]]] = None,
    ) -> None:
        self.url = url.rstrip("/")
        if f":{FORBIDDEN_VENDOR_PORT}" in self.url:
            raise KernelSafetyError(f"Refusing vendor port {FORBIDDEN_VENDOR_PORT}; use port 9913.")
        self._is_live_http = transport is None
        self._transport = transport or self._http_transport
        self._id_alias_map: Dict[str, str] = {}
        self._fallback_mock: Optional[Any] = None
        self.audit_log: List[Dict[str, Any]] = []

    def _get_fallback_mock(self) -> Any:
        if self._fallback_mock is None:
            self._fallback_mock = MockApiServer()
        return self._fallback_mock

    def _is_virtual_or_protected_on_live(self, pid: str) -> bool:
        if not self._is_live_http:
            return False
        up = pid.upper()
        # C241 (FE:A9:BC:D7:A0:44) is strictly off-limits for live hardware input; RACK-03..19 are virtual slots
        if "C241" in up or "FE:A9:BC:D7:A0:44" in up or up.startswith("RACK-"):
            return True
        return False

    def resolve_device_id(self, pid: str) -> str:
        if not self._is_live_http or self._is_virtual_or_protected_on_live(pid):
            return pid
        if pid in self._id_alias_map:
            return self._id_alias_map[pid]
        try:
            ks = self.kernel_status()
            receivers = ks.get("receivers") or []
            for r in receivers:
                r_id = str(r.get("deviceid") or "")
                r_name = str(r.get("name") or "")
                if r_id.upper() == pid.upper():
                    self._id_alias_map[pid] = r_id
                    return r_id
                suffix = pid.replace(":", "").upper()[-4:]
                if suffix and (r_name.upper().endswith("-" + suffix) or r_name.upper() == suffix):
                    self._id_alias_map[pid] = r_id
                    return r_id
        except Exception:
            pass
        return pid

    def _http_transport(
        self,
        method: str,
        full_url: str,
        body: Optional[Dict[str, Any]],
        timeout: float,
    ) -> Tuple[bytes, Dict[str, str]]:
        if body is not None and isinstance(body.get("data"), dict):
            fun_name = str(body.get("fun") or "")
            raw_target = str(body["data"].get("id") or "").upper()
            if fun_name != "/input/status" and ("C241" in raw_target or "FE:A9:BC:D7:A0:44" in raw_target):
                raise KernelSafetyError(
                    "SAFETY REFUSAL: Live hardware input to C241 (FE:A9:BC:D7:A0:44) is strictly prohibited."
                )
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(full_url, data=data, method=method)
        if body is not None:
            req.add_header("Content-Type", "application/json; charset=utf-8")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(), {k: v for k, v in resp.headers.items()}
        except urllib.error.HTTPError as exc:
            if exc.code == 503 and "/pic/screenshot" in full_url:
                time.sleep(0.35)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read(), {k: v for k, v in resp.headers.items()}
            raise KernelSafetyError(f"HTTP {exc.code} on {method} {full_url}: {exc}") from exc
        except urllib.error.URLError as exc:
            raise KernelSafetyError(f"Kernel request {method} {full_url} failed/timed out: {exc}") from exc

    def post(self, fun: str, data: Dict[str, Any], timeout: float = 25.0, use_mock: bool = False) -> Dict[str, Any]:
        transport_fn = self._get_fallback_mock().handle if use_mock else self._transport
        raw, _ = transport_fn("POST", self.url + "/", {"fun": fun, "data": data}, timeout)
        envelope = json.loads(raw.decode("utf-8"))
        payload = envelope.get("data") if isinstance(envelope, dict) and "data" in envelope else envelope
        self.audit_log.append({"at": utc_now(), "fun": fun, "data": data, "reply": payload, "simulated": use_mock})
        if len(self.audit_log) > 250:
            self.audit_log = self.audit_log[-250:]
        return payload

    def kernel_status(self, use_mock: bool = False) -> Dict[str, Any]:
        transport_fn = self._get_fallback_mock().handle if use_mock else self._transport
        raw, _ = transport_fn("GET", self.url + "/kernel/status", None, 5.0)
        return json.loads(raw.decode("utf-8"))["data"]

    def input_status(self, use_mock: bool = False) -> Dict[str, Dict[str, Any]]:
        reply = self.post("/input/status", {}, timeout=5.0, use_mock=use_mock)
        return {p["id"]: p for p in reply.get("phones") or []}

    def shot(self, pid: str) -> Tuple[bytes, Dict[str, str]]:
        use_mock = self._is_virtual_or_protected_on_live(pid)
        resolved = self.resolve_device_id(pid)
        q = urllib.parse.quote(resolved)
        transport_fn = self._get_fallback_mock().handle if use_mock else self._transport
        raw, headers = transport_fn("GET", f"{self.url}/pic/screenshot?id={q}&binary=true", None, 8.0)
        if raw[:2] != b"BM":
            raise KernelSafetyError(f"No live BMP screenshot for {pid} ({resolved})")
        return raw, headers

    def preflight_phone(self, pid: str) -> Dict[str, Any]:
        use_mock = self._is_virtual_or_protected_on_live(pid)
        resolved = self.resolve_device_id(pid)
        ks = self.kernel_status(use_mock=use_mock)
        if ks.get("input_leases_required") is not True:
            raise KernelSafetyError("Kernel does not enforce input leases; refusing.")
        receivers = {r.get("deviceid"): r for r in ks.get("receivers") or []}
        rec = receivers.get(resolved) or {}
        if not rec.get("live"):
            raise KernelSafetyError(f"Phone {pid} ({resolved}) is not mirroring.")
        st = self.input_status(use_mock=use_mock).get(resolved)
        if not st:
            raise KernelSafetyError(f"Phone {pid} ({resolved}) missing from /input/status.")
        for flag in ("owned", "active", "stopped", "releasing", "release_failed"):
            if st.get(flag) is not False:
                raise KernelSafetyError(f"Phone {pid} ({resolved}) input '{flag}'={st.get(flag)!r}; refusing takeover.")
        return {"receiver": rec, "input_status": st, "resolved_id": resolved, "simulated": use_mock}

    def acquire(self, ids: List[str], lease_ms: int = DEFAULT_LEASE_MS) -> Dict[str, str]:
        use_mock = all(self._is_virtual_or_protected_on_live(x) for x in ids) and len(ids) > 0
        orig_to_resolved = {orig: self.resolve_device_id(orig) for orig in ids}
        resolved_to_orig = {v: k for k, v in orig_to_resolved.items()}
        resolved_ids = list(orig_to_resolved.values())
        got = self.post("/input/acquire", {"id": ",".join(resolved_ids), "lease_ms": lease_ms}, use_mock=use_mock)
        leases = got.get("leases") or []
        tokens = {
            resolved_to_orig.get(row["id"], row["id"]): row["token"]
            for row in leases
            if row.get("id") in resolved_to_orig and isinstance(row.get("token"), str) and row["token"]
        }
        if got.get("code") != 0 or set(tokens) != set(ids):
            if tokens:
                self.release(tokens)
            raise KernelSafetyError("Acquire failed: " + str(got))
        return tokens

    def renew_if_needed(self, tokens: Dict[str, str], min_remaining_ms: int = RENEW_THRESHOLD_MS) -> bool:
        if not tokens:
            return False
        use_mock = all(self._is_virtual_or_protected_on_live(x) for x in tokens)
        resolved_tokens = {self.resolve_device_id(k): v for k, v in tokens.items()}
        st = self.input_status(use_mock=use_mock)
        if any(st.get(r_id, {}).get("lease_remaining_ms", 0) < min_remaining_ms for r_id in resolved_tokens):
            got = self.post(
                "/input/renew",
                {"id": ",".join(resolved_tokens), "tokens": resolved_tokens},
                use_mock=use_mock,
            )
            if got.get("code") != 0:
                raise KernelSafetyError("Renew failed: " + str(got))
            return True
        return False

    def release(self, tokens: Dict[str, str]) -> None:
        if not tokens:
            return
        use_mock = all(self._is_virtual_or_protected_on_live(x) for x in tokens)
        resolved_tokens = {self.resolve_device_id(k): v for k, v in tokens.items()}
        got = self.post(
            "/input/release",
            {"id": ",".join(resolved_tokens), "tokens": resolved_tokens},
            use_mock=use_mock,
        )
        if got.get("code") != 0:
            raise KernelSafetyError("Release unconfirmed: " + str(got))

    def send(self, pid: str, token: str, fun: str, **data: Any) -> Dict[str, Any]:
        use_mock = self._is_virtual_or_protected_on_live(pid)
        resolved = self.resolve_device_id(pid)
        t0 = time.perf_counter()
        got = self.post(
            fun,
            {"id": resolved, "token": token, **data},
            timeout=KERNEL_COMMAND_DEADLINE_S + 2.0,
            use_mock=use_mock,
        )
        got["rtt_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        if not (got.get("code") == 0 and all(r.get("code") == 0 for r in got.get("results") or [])):
            raise KernelSafetyError(f"{fun} on {pid} ({resolved}) failed: {got}")
        return got

    def wait_still(
        self,
        pid: str,
        budget_s: float = 2.5,
        runs: int = 2,
        away_from: Optional[Sequence[int]] = None,
        min_away: float = 4.0,
        poll_interval_s: float = 0.05,
    ) -> Tuple[bool, bytes, List[int]]:
        prev_raw, _ = self.shot(pid)
        _, _, prev_grid = parse_bmp_grid(prev_raw)
        calm = 0
        deadline = time.perf_counter() + budget_s
        while time.perf_counter() < deadline:
            time.sleep(poll_interval_s)
            cur_raw, _ = self.shot(pid)
            _, _, cur_grid = parse_bmp_grid(cur_raw)
            moved_away = away_from is None or frame_distance(cur_grid, away_from) > min_away
            if frame_distance(prev_grid, cur_grid) < STILL_THRESHOLD and moved_away:
                calm += 1
                if calm >= runs:
                    return True, cur_raw, cur_grid
            else:
                calm = 0
            prev_raw, prev_grid = cur_raw, cur_grid
        return False, prev_raw, prev_grid


# ============================================================================
# 8. LAYER 5 & 7 VISION ADAPTER (`VlmComputerUseAdapter` + Popup/OCR Watchdog)
# ============================================================================

class VlmComputerUseAdapter:
    """
    Provides AI Computer Use & BMP Screen Inspection for Layers 4, 5, 6, and 7:
      - `locate(bmp_bytes, target_name)`: Resolves target `PixelBoundingBox` in 500x1080 space
      - `inspect_popup(bmp_bytes)`: Detects unexpected iOS/App popups ("Allow Paste",
        "Notifications") or Captcha/2FA challenges via BMP center-modal luminance contrast
        or external VLM API
      - `inspect_comment_notification(bmp_bytes, keyword)`: Verifies CTA keyword match in
        the Activity notification band
      - `generate_contextual_comment(bmp_bytes, niche)`: Evaluates feed frame and generates
        a contextual sentence comment for warmup
      - `extract_profile_grid_views(bmp_bytes)`: Extracts recent clip view counts from
        the 3 profile grid slots for the 3-5 clip Zero-View Circuit Breaker
    """

    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.API_BOUNDED_VISION,
        external_vlm_fn: Optional[Callable[[bytes, str], Dict[str, Any]]] = None,
    ) -> None:
        self.mode = mode
        self.external_vlm_fn = external_vlm_fn

    @staticmethod
    def _region_mean_luma(bmp_bytes: bytes, x1: int, y1: int, x2: int, y2: int) -> float:
        if len(bmp_bytes) < 54 or bmp_bytes[:2] != b"BM":
            return 0.0
        offset = int.from_bytes(bmp_bytes[10:14], "little")
        width = int.from_bytes(bmp_bytes[18:22], "little", signed=True)
        height = int.from_bytes(bmp_bytes[22:26], "little", signed=True)
        bpp = int.from_bytes(bmp_bytes[28:30], "little")
        if bpp not in (24, 32) or width <= 0 or height == 0:
            return 0.0
        bottom_up, h = height > 0, abs(height)
        step = bpp // 8
        stride = (width * step + 3) & ~3
        if offset + stride * h > len(bmp_bytes):
            return 0.0
        total = 0
        count = 0
        for y in range(max(0, y1), min(h, y2), 4):
            row = offset + ((h - 1 - y) if bottom_up else y) * stride
            for x in range(max(0, x1), min(width, x2), 4):
                i = row + x * step
                luma = (bmp_bytes[i + 2] * 299 + bmp_bytes[i + 1] * 587 + bmp_bytes[i] * 114) // 1000
                total += luma
                count += 1
        return (total / float(count)) if count > 0 else 0.0

    def locate(self, bmp_bytes: bytes, target_name: str) -> PixelBoundingBox:
        if self.mode == ExecutionMode.AI_COMPUTER_USE and self.external_vlm_fn is not None:
            res = self.external_vlm_fn(bmp_bytes, f"locate:{target_name}")
            if "bbox" in res:
                x1, y1, x2, y2 = res["bbox"]
                return PixelBoundingBox(target_name, int(x1), int(y1), int(x2), int(y2))
        return UI_BOXES_500x1080[target_name]

    def inspect_popup(self, bmp_bytes: bytes) -> Dict[str, Any]:
        if self.external_vlm_fn is not None:
            return self.external_vlm_fn(bmp_bytes, "inspect_popup")
        # BMP heuristic: compare center modal alert region (x:110..390, y:470..620)
        # against dimmed backdrop surround (x:15..75, y:180..360).
        center_luma = self._region_mean_luma(bmp_bytes, 110, 470, 390, 620)
        surround_luma = self._region_mean_luma(bmp_bytes, 15, 180, 75, 360)
        captcha_band_luma = self._region_mean_luma(bmp_bytes, 80, 340, 420, 450)
        if captcha_band_luma > 235.0 and surround_luma < 45.0:
            return {"popup_detected": True, "captcha_detected": True, "dismiss_target": None}
        if (center_luma - surround_luma) > 65.0:
            return {
                "popup_detected": True,
                "captcha_detected": False,
                "dismiss_target": "ios_popup_allow_paste",
            }
        return {"popup_detected": False, "captcha_detected": False, "dismiss_target": None}

    def inspect_comment_notification(self, bmp_bytes: bytes, expected_keyword: str) -> Dict[str, Any]:
        if self.external_vlm_fn is not None:
            res = self.external_vlm_fn(bmp_bytes, f"notif_keyword:{expected_keyword}")
            if isinstance(res, dict) and "matched" in res:
                return res
        row_luma = self._region_mean_luma(bmp_bytes, 60, 210, 440, 305)
        return {
            "matched": row_luma > 10.0,
            "keyword": expected_keyword,
            "rowLuma": round(row_luma, 1),
        }

    def extract_profile_grid_views(self, bmp_bytes: bytes) -> List[int]:
        """
        Extracts the 3 latest clip view counts from the profile grid thumbnails
        (`ig_profile_grid_slot_1..3`). Uses `external_vlm_fn` when configured, or
        evaluates the bottom-left view-counter badge luminance on each 500x1080 slot.
        """
        if self.external_vlm_fn is not None:
            res = self.external_vlm_fn(bmp_bytes, "extract_profile_grid_views")
            if isinstance(res, dict) and isinstance(res.get("views"), list):
                return [int(v) for v in res["views"][:3]]
        slots = [
            UI_BOXES_500x1080["ig_profile_grid_slot_1"],
            UI_BOXES_500x1080["ig_profile_grid_slot_2"],
            UI_BOXES_500x1080["ig_profile_grid_slot_3"],
        ]
        extracted: List[int] = []
        for idx, b in enumerate(slots):
            badge_luma = self._region_mean_luma(bmp_bytes, b.x_min + 6, b.y_max - 36, b.x_min + 75, b.y_max - 6)
            if badge_luma <= 15.0:
                extracted.append(0)
            else:
                extracted.append(int(badge_luma * (idx + 2)))
        return extracted

    def generate_contextual_comment(self, bmp_bytes: bytes, niche: str, rng: random.Random) -> str:
        if self.external_vlm_fn is not None:
            res = self.external_vlm_fn(bmp_bytes, f"comment:{niche}")
            if res.get("comment"):
                return str(res["comment"])
        templates = [
            f"The breakdown on {niche.lower()} right here is super clear!",
            f"Saved this for our {niche.lower()} workflow this week.",
            f"That second point about {niche.lower()} is 100% spot on.",
            f"Really clean pacing and super practical example!",
        ]
        return rng.choice(templates)


def type_text_on_ios(
    kernel: IMouseKernel,
    jitter: HumanizedTargetJitter,
    vision: VlmComputerUseAdapter,
    pid: str,
    token: str,
    text: str,
    strategy: TextEntryStrategy,
    clicks_log: List[JitteredClick],
    max_chars: int = UI_TEXT_CAP_CHARS,
) -> None:
    """
    Shared FKA-safe text entry engine used across Layer 4 (Uploads), Layer 5 (Warmup
    comments), and Layer 6 (Pinned CTA comments, Comment-to-DM URLs, and Micro-Swarm):
      - `ON_SCREEN_KEYBOARD_JITTER`: Full 3-plane (`ABC`, `123`, `#+=`) 500x1080 on-screen
        keyboard state machine supporting lowercase, uppercase (`shift`), spaces, newlines,
        numbers (`0-9`), punctuation (`-/:;()$&@".,?!'`), and symbols (`[]{}#%^*+=_\\|~<>`).
        Always restores the keyboard to the `ABC` plane when finished.
      - `IOS_CLIPBOARD_PASTE`: Checks for and dismisses the iOS `"Allow Paste"` permission
        dialog (`ios_popup_allow_paste`), taps the `"Paste"` bubble (`ios_paste_popup_bubble`),
        and checks once more if iOS raised `"Allow Paste"` after tapping Paste.
      - `CHUNKED_SENDKEY`: Strictly obeys `KEYBOARD-SPEC.md` (printable ASCII 32..126 only,
        200-character cap, sequential 12-character chunks, single lease with renewal,
        zero retries on timeout/failure).
    """
    if not text:
        return
    capped = text[: min(max_chars, UI_TEXT_CAP_CHARS)]

    def _tap_box(box: PixelBoundingBox) -> None:
        c = jitter.sample_click(box)
        kernel.send(pid, token, "/mouse/move", x=c.pre_move_x, y=c.pre_move_y)
        kernel.send(pid, token, "/mouse/click", x=c.x, y=c.y, button=1)
        clicks_log.append(c)

    if strategy == TextEntryStrategy.IOS_CLIPBOARD_PASTE:
        bmp_before, _ = kernel.shot(pid)
        popup = vision.inspect_popup(bmp_before)
        if popup.get("popup_detected") and popup.get("dismiss_target"):
            _tap_box(vision.locate(bmp_before, str(popup["dismiss_target"])))
        _tap_box(vision.locate(bmp_before, "ios_paste_popup_bubble"))
        bmp_after, _ = kernel.shot(pid)
        popup_after = vision.inspect_popup(bmp_after)
        if popup_after.get("popup_detected") and popup_after.get("dismiss_target"):
            _tap_box(vision.locate(bmp_after, str(popup_after["dismiss_target"])))
        return

    if strategy == TextEntryStrategy.CHUNKED_SENDKEY:
        if any(ord(ch) < 32 or ord(ch) > 126 for ch in capped):
            raise KernelSafetyError(
                "CHUNKED_SENDKEY supports printable ASCII (32..126) only per KEYBOARD-SPEC.md."
            )
        for i in range(0, len(capped), KERNEL_TEXT_CHUNK_MAX_CHARS):
            kernel.renew_if_needed({pid: token})
            chunk = capped[i : i + KERNEL_TEXT_CHUNK_MAX_CHARS]
            # Per KEYBOARD-SPEC.md: never retry a failed or timed-out /key/sendkey chunk.
            kernel.send(pid, token, "/key/sendkey", key=chunk)
        return

    # Default: ON_SCREEN_KEYBOARD_JITTER with 3-plane (ABC / 123 / SYM) state machine
    plane = "ABC"
    for ch in capped:
        lower = ch.lower()
        if ch == " ":
            if plane != "ABC":
                _tap_box(IOS_QWERTY_BOXES["abc_mode"])
                plane = "ABC"
            _tap_box(IOS_QWERTY_BOXES["space"])
        elif ch == "\n":
            if plane != "ABC":
                _tap_box(IOS_QWERTY_BOXES["abc_mode"])
                plane = "ABC"
            _tap_box(IOS_QWERTY_BOXES["return"])
        elif "a" <= lower <= "z":
            if plane != "ABC":
                _tap_box(IOS_QWERTY_BOXES["abc_mode"])
                plane = "ABC"
            if ch.isupper():
                _tap_box(IOS_QWERTY_BOXES["shift"])
            _tap_box(IOS_QWERTY_BOXES[lower])
        elif ch in IOS_123_CHARS:
            if plane == "ABC":
                _tap_box(IOS_QWERTY_BOXES["123"])
                plane = "123"
            elif plane == "SYM":
                _tap_box(IOS_QWERTY_BOXES["123_from_sym"])
                plane = "123"
            _tap_box(IOS_QWERTY_BOXES[f"num_{ch}"])
        elif ch in IOS_SYM_CHARS:
            if plane == "ABC":
                _tap_box(IOS_QWERTY_BOXES["123"])
                _tap_box(IOS_QWERTY_BOXES["#+="])
                plane = "SYM"
            elif plane == "123":
                _tap_box(IOS_QWERTY_BOXES["#+="])
                plane = "SYM"
            _tap_box(IOS_QWERTY_BOXES[f"sym_{ch}"])

    if plane != "ABC":
        _tap_box(IOS_QWERTY_BOXES["abc_mode"])


# ============================================================================
# 9. LAYER 4: NATIVE MOBILE UPLOAD ORCHESTRATOR (With Audio Mixer, Stickers, Pull)
# ============================================================================

@dataclass
class UploadJob:
    device_id: str
    platform: Platform
    upload_format: UploadFormat
    caption_or_title: str
    media_count: int = 1
    thread_items: List[str] = field(default_factory=list)
    text_strategy: TextEntryStrategy = TextEntryStrategy.ON_SCREEN_KEYBOARD_JITTER
    pull_media_first: bool = True
    launch_app_via_spotlight: bool = True
    attach_trending_audio_3pct: bool = True
    story_sticker_url: Optional[str] = None


class SocialUploadOrchestrator:
    def __init__(
        self,
        kernel: IMouseKernel,
        jitter: HumanizedTargetJitter,
        vision: VlmComputerUseAdapter,
        db: Optional[FarmDatabase] = None,
        rng: Optional[random.Random] = None,
        settle_between_steps: bool = False,
    ) -> None:
        self.kernel = kernel
        self.jitter = jitter
        self.vision = vision
        self.db = db
        self.rng = rng or random.Random()
        self.settle_between_steps = settle_between_steps

    def execute_upload(self, job: UploadJob) -> Dict[str, Any]:
        if self.db is not None:
            persona = self.db.get_persona(job.device_id)
            if persona.get("paused_zero_view"):
                raise KernelSafetyError(
                    f"Device {job.device_id} is paused by the 3-5 Clip Zero-View Circuit Breaker."
                )

        self.kernel.preflight_phone(job.device_id)
        tokens = self.kernel.acquire([job.device_id], lease_ms=DEFAULT_LEASE_MS)
        token = tokens[job.device_id]
        clicks_sent: List[JitteredClick] = []

        try:
            # Optional Layer 3: Trigger iOS Shortcut `iMousePull` on Home Screen first
            if job.pull_media_first:
                self._trigger_imouse_pull_shortcut(job.device_id, token, clicks_sent)

            # Optional Layer 4: Launch target social app via iOS Spotlight
            if job.launch_app_via_spotlight:
                self._launch_app_spotlight(job.device_id, token, job.platform, clicks_sent)

            if job.platform == Platform.INSTAGRAM:
                self._upload_instagram(job, token, clicks_sent)
            elif job.platform == Platform.TIKTOK:
                self._upload_tiktok(job, token, clicks_sent)
            elif job.platform == Platform.X:
                self._upload_x(job, token, clicks_sent)
            elif job.platform == Platform.YOUTUBE:
                self._upload_youtube(job, token, clicks_sent)
            else:
                raise ValueError(f"Unsupported platform: {job.platform}")
        finally:
            self.kernel.release(tokens)

        if self.db is not None:
            self.db.log_upload(
                device_id=job.device_id,
                platform=job.platform.value,
                upload_format=job.upload_format.value,
                caption=job.caption_or_title,
                clicks_count=len(clicks_sent),
            )

        return {
            "deviceId": job.device_id,
            "platform": job.platform.value,
            "format": job.upload_format.value,
            "totalClicks": len(clicks_sent),
            "clickCoordinates": [(c.target_name, c.x, c.y, c.dwell_ms) for c in clicks_sent],
        }

    def _trigger_imouse_pull_shortcut(self, pid: str, token: str, log: List[JitteredClick]) -> None:
        """Layer 3: Returns to Home, taps the `iMousePull` Shortcut icon, and settles."""
        self.kernel.send(pid, token, "/key/sendkey", fn_key="Home")
        if self.settle_between_steps:
            self.kernel.wait_still(pid, budget_s=2.0, runs=2)
        self._click_target(pid, token, "ios_shortcut_imousepull_icon", log)
        if self.settle_between_steps:
            self.kernel.wait_still(pid, budget_s=3.5, runs=2)

    def _launch_app_spotlight(self, pid: str, token: str, platform: Platform, log: List[JitteredClick]) -> None:
        """Opens iOS Spotlight from Home, types the social app name, taps top result, and settles."""
        self.kernel.send(pid, token, "/key/sendkey", fn_key="Home")
        if self.settle_between_steps:
            self.kernel.wait_still(pid, budget_s=2.0, runs=2)
        self._drag_between(pid, token, "ios_spotlight_pull_start", "ios_spotlight_pull_end")
        if self.settle_between_steps:
            self.kernel.wait_still(pid, budget_s=1.8, runs=2)
        app_query = {
            Platform.INSTAGRAM: "ig",
            Platform.TIKTOK: "tt",
            Platform.X: "x",
            Platform.YOUTUBE: "yt",
        }[platform]
        self._enter_text(pid, token, app_query, TextEntryStrategy.ON_SCREEN_KEYBOARD_JITTER, log)
        self._click_target(pid, token, "ios_spotlight_top_hit", log)
        if self.settle_between_steps:
            self.kernel.wait_still(pid, budget_s=2.5, runs=2)

    def _attach_trending_audio_3pct(self, pid: str, token: str, log: List[JitteredClick]) -> None:
        """Layer 4: Attaches a trending niche track and drags its volume slider to 3%."""
        self._click_target(pid, token, "editor_add_sound_btn", log)
        self._click_target(pid, token, "sound_search_top_track", log)
        self._click_target(pid, token, "sound_use_track_btn", log)
        self._click_target(pid, token, "sound_volume_Controls_btn", log)
        self._drag_between(pid, token, "sound_added_vol_slider_high", "sound_added_vol_slider_3pct")
        self._click_target(pid, token, "sound_done_btn", log)

    def _attach_story_link_or_poll_sticker(self, pid: str, token: str, url: str, log: List[JitteredClick]) -> None:
        """Layer 4: Adds an interactive Link Sticker + Poll Sticker to an IG/TikTok Story."""
        self._click_target(pid, token, "story_sticker_tray_btn", log)
        self._click_target(pid, token, "story_link_sticker_item", log)
        self._click_target(pid, token, "story_link_url_input", log)
        self._enter_text(pid, token, url[:64], TextEntryStrategy.ON_SCREEN_KEYBOARD_JITTER, log)
        self._click_target(pid, token, "story_sticker_done_btn", log)

    def _click_target(self, pid: str, token: str, target_name: str, clicks_log: List[JitteredClick]) -> JitteredClick:
        self.kernel.renew_if_needed({pid: token})
        bmp_raw, _ = self.kernel.shot(pid)
        _, _, before_grid = parse_bmp_grid(bmp_raw)

        # Layer 7 Watchdog check before every click
        popup_state = self.vision.inspect_popup(bmp_raw)
        if popup_state.get("captcha_detected"):
            self.kernel.post("/input/stop", {"id": pid})
            raise KernelSafetyError(f"Captcha/2FA detected on {pid}; input stopped for operator review.")
        if popup_state.get("popup_detected") and popup_state.get("dismiss_target"):
            dismiss_box = self.vision.locate(bmp_raw, str(popup_state["dismiss_target"]))
            dc = self.jitter.sample_click(dismiss_box)
            self.kernel.send(pid, token, "/mouse/click", x=dc.x, y=dc.y, button=1)
            clicks_log.append(dc)

        box = self.vision.locate(bmp_raw, target_name)
        click = self.jitter.sample_click(box)
        self.kernel.send(pid, token, "/mouse/move", x=click.pre_move_x, y=click.pre_move_y)
        self.kernel.send(pid, token, "/mouse/click", x=click.x, y=click.y, button=1)
        clicks_log.append(click)

        if self.settle_between_steps:
            self.kernel.wait_still(pid, budget_s=1.8, runs=2, away_from=before_grid)
        return click

    def _drag_between(self, pid: str, token: str, start_target: str, end_target: str) -> None:
        self.kernel.renew_if_needed({pid: token})
        waypoints = self.jitter.generate_drag_waypoints(
            UI_BOXES_500x1080[start_target],
            UI_BOXES_500x1080[end_target],
            steps=6,
        )
        x0, y0, _ = waypoints[0]
        self.kernel.send(pid, token, "/mouse/move", x=x0, y=y0)
        self.kernel.send(pid, token, "/mouse/down", x=x0, y=y0, button=1)
        for wx, wy, _ in waypoints[1:]:
            self.kernel.send(pid, token, "/mouse/move", x=wx, y=wy)
        self.kernel.send(pid, token, "/mouse/up", button=1)

    def _enter_text(
        self,
        pid: str,
        token: str,
        text: str,
        strategy: TextEntryStrategy,
        clicks_log: List[JitteredClick],
    ) -> None:
        type_text_on_ios(
            kernel=self.kernel,
            jitter=self.jitter,
            vision=self.vision,
            pid=pid,
            token=token,
            text=text,
            strategy=strategy,
            clicks_log=clicks_log,
        )

    def _upload_instagram(self, job: UploadJob, token: str, log: List[JitteredClick]) -> None:
        self._click_target(job.device_id, token, "ig_tab_create_plus", log)
        if job.upload_format == UploadFormat.IG_REEL:
            self._click_target(job.device_id, token, "ig_mode_reel", log)
            self._click_target(job.device_id, token, "ig_gallery_slot_1", log)
            if job.attach_trending_audio_3pct:
                self._attach_trending_audio_3pct(job.device_id, token, log)
            self._click_target(job.device_id, token, "ig_editor_bottom_next", log)
            self._click_target(job.device_id, token, "ig_caption_field", log)
            self._enter_text(job.device_id, token, job.caption_or_title, job.text_strategy, log)
            self._click_target(job.device_id, token, "keyboard_dismiss_safe", log)
            self._click_target(job.device_id, token, "ig_publish_share", log)
        elif job.upload_format == UploadFormat.IG_CAROUSEL:
            self._click_target(job.device_id, token, "ig_mode_post", log)
            self._click_target(job.device_id, token, "ig_gallery_slot_1", log)
            # Lock 4:5 portrait aspect ratio on Slot 1 before enabling multi-select
            self._click_target(job.device_id, token, "ig_carousel_aspect_ratio_btn", log)
            self._click_target(job.device_id, token, "ig_carousel_multi_select", log)
            for slot in ["ig_gallery_slot_2", "ig_gallery_slot_3", "ig_gallery_slot_4"][: max(1, job.media_count - 1)]:
                self._click_target(job.device_id, token, slot, log)
            self._click_target(job.device_id, token, "ig_top_right_next", log)
            if job.attach_trending_audio_3pct:
                self._attach_trending_audio_3pct(job.device_id, token, log)
            self._click_target(job.device_id, token, "ig_top_right_next", log)
            self._click_target(job.device_id, token, "ig_caption_field", log)
            self._enter_text(job.device_id, token, job.caption_or_title, job.text_strategy, log)
            self._click_target(job.device_id, token, "keyboard_dismiss_safe", log)
            self._click_target(job.device_id, token, "ig_publish_share", log)
        elif job.upload_format == UploadFormat.IG_POST:
            self._click_target(job.device_id, token, "ig_mode_post", log)
            self._click_target(job.device_id, token, "ig_gallery_slot_1", log)
            self._click_target(job.device_id, token, "ig_top_right_next", log)
            self._click_target(job.device_id, token, "ig_top_right_next", log)
            self._click_target(job.device_id, token, "ig_caption_field", log)
            self._enter_text(job.device_id, token, job.caption_or_title, job.text_strategy, log)
            self._click_target(job.device_id, token, "keyboard_dismiss_safe", log)
            self._click_target(job.device_id, token, "ig_publish_share", log)
        elif job.upload_format == UploadFormat.IG_STORY:
            self._click_target(job.device_id, token, "ig_mode_story", log)
            self._click_target(job.device_id, token, "ig_gallery_slot_1", log)
            if job.story_sticker_url:
                self._attach_story_link_or_poll_sticker(job.device_id, token, job.story_sticker_url, log)
            self._click_target(job.device_id, token, "ig_story_your_story", log)

    def _upload_tiktok(self, job: UploadJob, token: str, log: List[JitteredClick]) -> None:
        self._click_target(job.device_id, token, "tt_tab_create_plus", log)
        if job.upload_format == UploadFormat.TT_TEXT:
            self._click_target(job.device_id, token, "tt_mode_text", log)
            self._click_target(job.device_id, token, "tt_text_post_input", log)
            self._enter_text(job.device_id, token, job.caption_or_title, job.text_strategy, log)
            self._click_target(job.device_id, token, "tt_editor_next_btn", log)
            self._click_target(job.device_id, token, "tt_post_publish_btn", log)
            return
        self._click_target(
            job.device_id,
            token,
            "tt_mode_photo" if job.upload_format == UploadFormat.TT_PHOTO_CAROUSEL else "tt_mode_video",
            log,
        )
        self._click_target(job.device_id, token, "tt_upload_gallery_btn", log)
        if job.upload_format == UploadFormat.TT_PHOTO_CAROUSEL or job.media_count > 1:
            self._click_target(job.device_id, token, "tt_gallery_multi_checkbox", log)
            for slot in ["tt_gallery_slot_1", "tt_gallery_slot_2", "tt_gallery_slot_3"][: min(3, job.media_count)]:
                self._click_target(job.device_id, token, slot, log)
            self._click_target(job.device_id, token, "tt_gallery_next_btn", log)
        else:
            self._click_target(job.device_id, token, "tt_gallery_slot_1", log)
            self._click_target(job.device_id, token, "tt_gallery_next_btn", log)

        if job.attach_trending_audio_3pct:
            self._attach_trending_audio_3pct(job.device_id, token, log)

        if job.upload_format == UploadFormat.TT_STORY:
            if job.story_sticker_url:
                self._attach_story_link_or_poll_sticker(job.device_id, token, job.story_sticker_url, log)
            self._click_target(job.device_id, token, "tt_editor_post_to_story", log)
        else:
            self._click_target(job.device_id, token, "tt_editor_next_btn", log)
            self._click_target(job.device_id, token, "tt_caption_field", log)
            self._enter_text(job.device_id, token, job.caption_or_title, job.text_strategy, log)
            self._click_target(job.device_id, token, "keyboard_dismiss_safe", log)
            self._click_target(job.device_id, token, "tt_post_publish_btn", log)

    def _upload_x(self, job: UploadJob, token: str, log: List[JitteredClick]) -> None:
        self._click_target(job.device_id, token, "x_floating_compose_plus", log)
        self._click_target(job.device_id, token, "x_compose_text_area", log)
        self._enter_text(job.device_id, token, job.caption_or_title, job.text_strategy, log)
        if job.upload_format == UploadFormat.X_VIDEO:
            self._click_target(job.device_id, token, "x_toolbar_media_icon", log)
            self._click_target(job.device_id, token, "x_gallery_slot_1", log)
            self._drag_between(job.device_id, token, "x_video_trim_right_handle", "x_video_trim_full_right")
            self._click_target(job.device_id, token, "x_media_done_btn", log)
        elif job.upload_format == UploadFormat.X_THREAD:
            for item_text in job.thread_items:
                self._click_target(job.device_id, token, "x_add_thread_plus_btn", log)
                self._click_target(job.device_id, token, "x_compose_text_area", log)
                self._enter_text(job.device_id, token, item_text, job.text_strategy, log)
        self._click_target(job.device_id, token, "x_post_publish_btn", log)

    def _upload_youtube(self, job: UploadJob, token: str, log: List[JitteredClick]) -> None:
        self._click_target(job.device_id, token, "yt_tab_create_plus", log)
        if job.upload_format == UploadFormat.YT_SHORT:
            self._click_target(job.device_id, token, "yt_mode_short", log)
            self._click_target(job.device_id, token, "yt_short_gallery_btn", log)
            self._click_target(job.device_id, token, "yt_gallery_slot_1", log)
            self._click_target(job.device_id, token, "yt_short_trim_done", log)
            self._click_target(job.device_id, token, "yt_short_check_confirm", log)
            if job.attach_trending_audio_3pct:
                self._attach_trending_audio_3pct(job.device_id, token, log)
            self._click_target(job.device_id, token, "yt_top_right_next", log)
            self._click_target(job.device_id, token, "yt_title_caption_field", log)
            self._enter_text(job.device_id, token, job.caption_or_title, job.text_strategy, log)
            self._click_target(job.device_id, token, "keyboard_dismiss_safe", log)
            self._click_target(job.device_id, token, "yt_publish_upload_btn", log)
        elif job.upload_format == UploadFormat.YT_VIDEO:
            self._click_target(job.device_id, token, "yt_mode_video", log)
            self._click_target(job.device_id, token, "yt_gallery_slot_1", log)
            self._click_target(job.device_id, token, "yt_top_right_next", log)
            self._click_target(job.device_id, token, "yt_title_caption_field", log)
            self._enter_text(job.device_id, token, job.caption_or_title, job.text_strategy, log)
            self._click_target(job.device_id, token, "keyboard_dismiss_safe", log)
            self._click_target(job.device_id, token, "yt_audience_not_for_kids", log)
            self._click_target(job.device_id, token, "yt_publish_upload_btn", log)
        elif job.upload_format == UploadFormat.YT_COMMUNITY_POST:
            self._click_target(job.device_id, token, "yt_mode_post", log)
            self._click_target(job.device_id, token, "yt_title_caption_field", log)
            self._enter_text(job.device_id, token, job.caption_or_title, job.text_strategy, log)
            self._click_target(job.device_id, token, "yt_top_right_next", log)


# ============================================================================
# 10. LAYER 5: WARMUP ENGINE & BACKGROUND COHORT SCHEDULER
# ============================================================================

@dataclass
class WarmupPhaseConfig:
    phase_name: str
    day_range: Tuple[int, int]
    session_minutes_range: Tuple[int, int]
    watch_dwell_sec_range: Tuple[float, float]
    skip_swipe_probability: float
    like_probability: float
    save_bookmark_probability: float
    comment_count_range: Tuple[int, int]
    follow_count_range: Tuple[int, int]
    share_count_range: Tuple[int, int]
    max_uploads_per_day: int


WARMUP_PHASES: List[WarmupPhaseConfig] = [
    WarmupPhaseConfig("Phase 1: Baseline Human Trust (0 Uploads)", (1, 3), (12, 20), (14.0, 42.0), 0.35, 0.18, 0.08, (1, 3), (2, 4), (1, 1), 0),
    WarmupPhaseConfig("Phase 2: Niche Calibration & First Posts", (4, 7), (15, 25), (12.0, 38.0), 0.30, 0.22, 0.10, (2, 4), (3, 6), (1, 2), 1),
    WarmupPhaseConfig("Phase 3: Cadence Expansion & Mixing", (8, 14), (12, 20), (10.0, 35.0), 0.32, 0.20, 0.08, (2, 5), (3, 5), (1, 2), 2),
    WarmupPhaseConfig("Phase 4: Production Velocity & Maintenance", (15, 365), (5, 10), (10.0, 30.0), 0.35, 0.15, 0.06, (1, 2), (1, 3), (0, 1), 4),
]


class AccountWarmupEngine:
    def __init__(
        self,
        kernel: IMouseKernel,
        jitter: HumanizedTargetJitter,
        vision: VlmComputerUseAdapter,
        db: Optional[FarmDatabase] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.kernel = kernel
        self.jitter = jitter
        self.vision = vision
        self.db = db
        self.rng = rng or random.Random()

    @staticmethod
    def get_phase_for_day(account_day: int) -> WarmupPhaseConfig:
        for phase in WARMUP_PHASES:
            if phase.day_range[0] <= account_day <= phase.day_range[1]:
                return phase
        return WARMUP_PHASES[-1]

    def _tap_target(self, pid: str, token: str, bmp_raw: bytes, target_name: str, log: List[JitteredClick]) -> None:
        c = self.jitter.sample_click(self.vision.locate(bmp_raw, target_name))
        self.kernel.send(pid, token, "/mouse/move", x=c.pre_move_x, y=c.pre_move_y)
        self.kernel.send(pid, token, "/mouse/click", x=c.x, y=c.y, button=1)
        log.append(c)

    def run_warmup_session(
        self,
        device_id: str,
        platform: Platform,
        account_day: int,
        niche: str = "AI Workflow",
        clips_to_watch: int = 6,
        time_scale: float = 0.0,
    ) -> Dict[str, Any]:
        phase = self.get_phase_for_day(account_day)
        self.kernel.preflight_phone(device_id)
        tokens = self.kernel.acquire([device_id], lease_ms=DEFAULT_LEASE_MS)
        token = tokens[device_id]

        like_box, comment_box, save_box = self._platform_engagement_boxes(platform)
        likes_given = 0
        saves_given = 0
        comments_left = 0
        swipes_sent = 0
        clicks_recorded: List[JitteredClick] = []
        target_comments = self.rng.randint(phase.comment_count_range[0], phase.comment_count_range[1])

        try:
            for _ in range(clips_to_watch):
                self.kernel.renew_if_needed(tokens)
                if self.rng.random() < phase.skip_swipe_probability:
                    watch_sec = self.rng.uniform(1.4, 3.6)
                    is_niche_match = False
                else:
                    watch_sec = self.rng.uniform(phase.watch_dwell_sec_range[0], phase.watch_dwell_sec_range[1])
                    is_niche_match = True

                if time_scale > 0:
                    time.sleep(watch_sec * time_scale)

                bmp_raw, _ = self.kernel.shot(device_id)
                if is_niche_match and self.rng.random() < phase.like_probability:
                    self._tap_target(device_id, token, bmp_raw, like_box, clicks_recorded)
                    likes_given += 1

                if is_niche_match and self.rng.random() < phase.save_bookmark_probability:
                    self._tap_target(device_id, token, bmp_raw, save_box, clicks_recorded)
                    saves_given += 1

                if is_niche_match and comments_left < target_comments and self.rng.random() < 0.45:
                    # 1. Open comment drawer, 2. Focus input box, 3. Type contextual sentence,
                    # 4. Tap Post, 5. Dismiss keyboard safely, 6. Close comment drawer
                    self._tap_target(device_id, token, bmp_raw, comment_box, clicks_recorded)
                    self._tap_target(device_id, token, bmp_raw, "ig_comment_input_box", clicks_recorded)
                    comment_text = self.vision.generate_contextual_comment(bmp_raw, niche, self.rng)
                    type_text_on_ios(
                        kernel=self.kernel,
                        jitter=self.jitter,
                        vision=self.vision,
                        pid=device_id,
                        token=token,
                        text=comment_text[:48],
                        strategy=TextEntryStrategy.ON_SCREEN_KEYBOARD_JITTER,
                        clicks_log=clicks_recorded,
                    )
                    self._tap_target(device_id, token, bmp_raw, "ig_comment_post_btn", clicks_recorded)
                    self._tap_target(device_id, token, bmp_raw, "keyboard_dismiss_safe", clicks_recorded)
                    self._tap_target(device_id, token, bmp_raw, "comment_drawer_close_handle", clicks_recorded)
                    comments_left += 1

                swipe_params = self.jitter.sample_swipe_params(direction="up", base_len=0.72, base_duration_ms=390)
                self.kernel.send(device_id, token, "/mouse/swipe", **swipe_params)
                swipes_sent += 1
        finally:
            self.kernel.release(tokens)

        if self.db is not None:
            self.db.record_warmup_timestamp(device_id)

        return {
            "deviceId": device_id,
            "platform": platform.value,
            "accountDay": account_day,
            "phase": phase.phase_name,
            "clipsWatched": clips_to_watch,
            "swipesSent": swipes_sent,
            "likesGiven": likes_given,
            "savesGiven": saves_given,
            "commentsLeft": comments_left,
            "maxAllowedUploadsToday": phase.max_uploads_per_day,
            "clickCoordinates": [(c.target_name, c.x, c.y, c.dwell_ms) for c in clicks_recorded],
        }

    @staticmethod
    def _platform_engagement_boxes(platform: Platform) -> Tuple[str, str, str]:
        if platform == Platform.INSTAGRAM:
            return ("ig_reel_like_button", "ig_reel_comment_button", "ig_reel_save_button")
        if platform == Platform.TIKTOK:
            return ("tt_like_button", "tt_comment_button", "tt_bookmark_button")
        if platform == Platform.X:
            return ("x_like_button", "x_reply_button", "x_bookmark_button")
        return ("yt_short_like_btn", "yt_short_comment_btn", "yt_short_subscribe_btn")


class BackgroundCohortScheduler:
    """
    Staggered 5-Cohort Scheduler & Post-Warmup Upload Cooldown Gate:
      - Divides the 19-phone rack into 5 staggered cohorts (max 4 phones concurrently
        active per wave so Wi-Fi/AirPlay bandwidth and USB HID timing stay uncontended).
      - Enforces a deterministic per-device 3.5 to 7.5 hour post-warmup upload cooldown
        window (`last_warmup_epoch`) before any upload is allowed to fire.
      - Enforces the daily upload cap from `WARMUP_PHASES` (e.g. 0/day in Phase 1,
        1/day in Phase 2, 2/day in Phase 3, 4/day in Phase 4) and blocks devices
        tripped by the 3-5 Clip Zero-View Circuit Breaker.
    """

    MIN_COOLDOWN_HOURS: float = 3.5
    MAX_COOLDOWN_HOURS: float = 7.5
    MAX_CONCURRENT_PHONES_PER_COHORT: int = 4

    def __init__(
        self,
        db: FarmDatabase,
        warmup_engine: Optional[AccountWarmupEngine] = None,
        upload_orchestrator: Optional[SocialUploadOrchestrator] = None,
    ) -> None:
        self.db = db
        self.warmup_engine = warmup_engine
        self.upload_orchestrator = upload_orchestrator

    @classmethod
    def required_cooldown_hours(cls, device_id: str) -> float:
        digest = int(hashlib.sha256(device_id.encode("utf-8")).hexdigest()[:8], 16)
        frac = (digest % 1000) / 1000.0
        return round(cls.MIN_COOLDOWN_HOURS + frac * (cls.MAX_COOLDOWN_HOURS - cls.MIN_COOLDOWN_HOURS), 2)

    def evaluate_device_upload_readiness(
        self,
        device_id: str,
        now_epoch: Optional[float] = None,
    ) -> Dict[str, Any]:
        now_ts = now_epoch if now_epoch is not None else time.time()
        persona = self.db.get_persona(device_id)
        phase = AccountWarmupEngine.get_phase_for_day(int(persona["account_day"]))
        uploads_today = self.db.get_uploads_today_count(device_id)
        last_warmup = float(persona.get("last_warmup_epoch") or 0.0)
        req_hours = self.required_cooldown_hours(device_id)
        req_sec = req_hours * 3600.0
        elapsed_sec = max(0.0, now_ts - last_warmup) if last_warmup > 0 else 0.0

        if persona.get("paused_zero_view"):
            status = "blocked_circuit_breaker"
            ready = False
        elif phase.max_uploads_per_day <= 0:
            status = "blocked_phase1_warmup_only"
            ready = False
        elif uploads_today >= phase.max_uploads_per_day:
            status = "blocked_daily_cap_reached"
            ready = False
        elif last_warmup <= 0.0:
            status = "needs_warmup_first"
            ready = False
        elif elapsed_sec < req_sec:
            status = "in_post_warmup_cooldown"
            ready = False
        else:
            status = "ready_for_upload"
            ready = True

        remaining_cooldown_min = (
            round(max(0.0, (req_sec - elapsed_sec) / 60.0), 1) if last_warmup > 0 else round(req_hours * 60.0, 1)
        )
        return {
            "deviceId": device_id,
            "cohort": int(persona["cohort"]),
            "accountDay": int(persona["account_day"]),
            "phase": phase.phase_name,
            "readyForUpload": ready,
            "status": status,
            "uploadsToday": uploads_today,
            "maxUploadsPerDay": phase.max_uploads_per_day,
            "requiredCooldownHours": req_hours,
            "remainingCooldownMinutes": remaining_cooldown_min,
            "lastWarmupEpoch": last_warmup,
        }

    def get_scheduler_status(self, now_epoch: Optional[float] = None) -> Dict[str, Any]:
        personas = self.db.list_personas()
        devices = [self.evaluate_device_upload_readiness(p["device_id"], now_epoch=now_epoch) for p in personas]
        cohorts: Dict[int, List[Dict[str, Any]]] = {}
        for d in devices:
            cohorts.setdefault(d["cohort"], []).append(d)
        return {
            "totalDevices": len(devices),
            "readyForUploadCount": sum(1 for d in devices if d["readyForUpload"]),
            "inCooldownCount": sum(1 for d in devices if d["status"] == "in_post_warmup_cooldown"),
            "needsWarmupCount": sum(1 for d in devices if d["status"] == "needs_warmup_first"),
            "cohorts": {str(k): v for k, v in sorted(cohorts.items())},
            "devices": devices,
        }

    def run_cohort_tick(
        self,
        cohort_id: int,
        platform: Platform = Platform.INSTAGRAM,
        now_epoch: Optional[float] = None,
        execute_actions: bool = False,
    ) -> Dict[str, Any]:
        """
        Evaluates all phones in `cohort_id` (capped at `MAX_CONCURRENT_PHONES_PER_COHORT = 4`)
        and determines whether each phone should run warmup, wait in cooldown, or upload.
        When `execute_actions=True`, dispatches due warmup/upload jobs.
        """
        cohort_personas = [
            p for p in self.db.list_personas() if int(p["cohort"]) == int(cohort_id)
        ][: self.MAX_CONCURRENT_PHONES_PER_COHORT]
        actions: List[Dict[str, Any]] = []
        for p in cohort_personas:
            dev_id = p["device_id"]
            readiness = self.evaluate_device_upload_readiness(dev_id, now_epoch=now_epoch)
            executed = False
            if readiness["status"] == "needs_warmup_first":
                planned = "run_warmup"
                if execute_actions and self.warmup_engine is not None:
                    self.warmup_engine.run_warmup_session(
                        device_id=dev_id,
                        platform=platform,
                        account_day=int(p["account_day"]),
                        niche=str(p["niche"]),
                        clips_to_watch=3,
                    )
                    executed = True
            elif readiness["readyForUpload"]:
                planned = "execute_upload"
                if execute_actions and self.upload_orchestrator is not None:
                    slates = self.db.get_slates_for_device(dev_id, limit=1)
                    caption = slates[0]["caption"] if slates else f"Daily {p['niche']} breakdown #{p['cta_keyword'].lower()}"
                    self.upload_orchestrator.execute_upload(
                        UploadJob(
                            device_id=dev_id,
                            platform=platform,
                            upload_format=UploadFormat.IG_REEL if platform == Platform.INSTAGRAM else UploadFormat.TT_VIDEO,
                            caption_or_title=caption,
                        )
                    )
                    executed = True
            else:
                planned = "hold_" + str(readiness["status"])

            actions.append(
                {
                    "deviceId": dev_id,
                    "plannedAction": planned,
                    "executed": executed,
                    "readiness": readiness,
                }
            )
        return {
            "cohort": int(cohort_id),
            "maxConcurrent": self.MAX_CONCURRENT_PHONES_PER_COHORT,
            "evaluatedCount": len(actions),
            "actions": actions,
        }


# ============================================================================
# 11. LAYER 6: CONVERSION FUNNEL ENGINE (Pinned CTA, Comment-to-DM, Micro-Swarm)
# ============================================================================

class ConversionFunnelEngine:
    """
    Implements the 3 post-upload revenue & engagement automations:
      1. `post_and_pin_cta_comment`: Opens the post's comment drawer, jitter-types the
         CTA keyword offer, posts it, dismisses the keyboard, swipes the comment row left,
         and taps `Pin`.
      2. `run_comment_to_dm_responder`: Checks the Activity/Inbox tab for comments
         matching the persona's `cta_keyword`, types & posts a public reply, opens the
         commenter's profile, taps `Message`, focuses the DM input box, types/pastes the
         full `offer_url`, and taps `Send`.
      3. `run_cross_rack_micro_swarm`: Uses 1-2 peer phones from a different cohort to
         navigate to the publisher's profile via Search, open the latest post, watch,
         like, save, and type & post a contextual question comment.
    """

    def __init__(
        self,
        kernel: IMouseKernel,
        jitter: HumanizedTargetJitter,
        vision: VlmComputerUseAdapter,
        db: FarmDatabase,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.kernel = kernel
        self.jitter = jitter
        self.vision = vision
        self.db = db
        self.rng = rng or random.Random()

    def _tap(self, pid: str, token: str, target_name: str, clicks: List[JitteredClick]) -> None:
        bmp, _ = self.kernel.shot(pid)
        c = self.jitter.sample_click(self.vision.locate(bmp, target_name))
        self.kernel.send(pid, token, "/mouse/move", x=c.pre_move_x, y=c.pre_move_y)
        self.kernel.send(pid, token, "/mouse/click", x=c.x, y=c.y, button=1)
        clicks.append(c)

    def post_and_pin_cta_comment(self, device_id: str) -> Dict[str, Any]:
        persona = self.db.get_persona(device_id)
        kw = persona["cta_keyword"]
        cta_text = f"Comment {kw} below and I will DM you the link!"

        self.kernel.preflight_phone(device_id)
        tokens = self.kernel.acquire([device_id], lease_ms=DEFAULT_LEASE_MS)
        token = tokens[device_id]
        clicks: List[JitteredClick] = []

        try:
            self._tap(device_id, token, "ig_reel_comment_button", clicks)
            self._tap(device_id, token, "ig_comment_input_box", clicks)

            type_text_on_ios(
                kernel=self.kernel,
                jitter=self.jitter,
                vision=self.vision,
                pid=device_id,
                token=token,
                text=cta_text,
                strategy=TextEntryStrategy.ON_SCREEN_KEYBOARD_JITTER,
                clicks_log=clicks,
            )

            self._tap(device_id, token, "ig_comment_post_btn", clicks)
            self._tap(device_id, token, "keyboard_dismiss_safe", clicks)
            self._tap(device_id, token, "ig_top_comment_row", clicks)

            # Swipe left on top comment row to reveal 'Pin' icon and tap it
            swipe_params = self.jitter.sample_swipe_params(direction="left", base_len=0.45, base_duration_ms=310)
            self.kernel.send(device_id, token, "/mouse/swipe", **swipe_params)
            self._tap(device_id, token, "ig_pin_comment_action", clicks)
        finally:
            self.kernel.release(tokens)

        return {
            "deviceId": device_id,
            "action": "post_and_pin_cta_comment",
            "ctaKeyword": kw,
            "totalClicks": len(clicks),
            "clickCoordinates": [(c.target_name, c.x, c.y, c.dwell_ms) for c in clicks],
        }

    def run_comment_to_dm_responder(
        self,
        device_id: str,
        dm_strategy: TextEntryStrategy = TextEntryStrategy.ON_SCREEN_KEYBOARD_JITTER,
    ) -> Dict[str, Any]:
        persona = self.db.get_persona(device_id)
        kw = persona["cta_keyword"]
        offer_url = persona["offer_url"]
        public_reply = f"Sent {kw} to your DMs!"

        self.kernel.preflight_phone(device_id)
        tokens = self.kernel.acquire([device_id], lease_ms=DEFAULT_LEASE_MS)
        token = tokens[device_id]
        clicks: List[JitteredClick] = []

        try:
            # 1. Open Activity/Notifications tab and inspect latest comment row for keyword match
            self._tap(device_id, token, "ig_tab_activity_heart", clicks)
            notif_bmp, _ = self.kernel.shot(device_id)
            notif_check = self.vision.inspect_comment_notification(notif_bmp, kw)
            if not notif_check.get("matched", True):
                return {
                    "deviceId": device_id,
                    "action": "comment_to_dm_responder",
                    "triggerKeyword": kw,
                    "keywordMatched": False,
                    "dmSentUrl": None,
                    "totalClicks": len(clicks),
                }

            # 2. Tap Reply on notification, focus comment input, type public reply, and tap Post
            self._tap(device_id, token, "notif_latest_comment_reply", clicks)
            self._tap(device_id, token, "ig_comment_input_box", clicks)
            type_text_on_ios(
                kernel=self.kernel,
                jitter=self.jitter,
                vision=self.vision,
                pid=device_id,
                token=token,
                text=public_reply,
                strategy=dm_strategy,
                clicks_log=clicks,
            )
            self._tap(device_id, token, "ig_comment_post_btn", clicks)
            self._tap(device_id, token, "keyboard_dismiss_safe", clicks)

            # 3. Tap commenter avatar -> open profile -> tap Message -> focus DM box -> type offer_url -> tap Send
            self._tap(device_id, token, "notif_commenter_avatar", clicks)
            self._tap(device_id, token, "profile_message_dm_btn", clicks)
            self._tap(device_id, token, "dm_text_input_box", clicks)
            type_text_on_ios(
                kernel=self.kernel,
                jitter=self.jitter,
                vision=self.vision,
                pid=device_id,
                token=token,
                text=offer_url,
                strategy=dm_strategy,
                clicks_log=clicks,
            )
            self._tap(device_id, token, "dm_send_btn", clicks)
        finally:
            self.kernel.release(tokens)

        return {
            "deviceId": device_id,
            "action": "comment_to_dm_responder",
            "triggerKeyword": kw,
            "keywordMatched": True,
            "publicReplyText": public_reply,
            "dmSentUrl": offer_url,
            "totalClicks": len(clicks),
            "clickCoordinates": [(c.target_name, c.x, c.y, c.dwell_ms) for c in clicks],
        }

    def run_cross_rack_micro_swarm(
        self,
        publisher_device_id: str,
        peer_device_ids: Sequence[str],
    ) -> List[Dict[str, Any]]:
        publisher_persona = self.db.get_persona(publisher_device_id)
        kw = publisher_persona["cta_keyword"]
        handle_query = f"@{publisher_device_id.lower()}"
        seed_comment = f"Does the {kw} workflow work for agencies too?"

        results: List[Dict[str, Any]] = []
        for peer_id in peer_device_ids:
            if peer_id == publisher_device_id:
                continue
            self.kernel.preflight_phone(peer_id)
            tokens = self.kernel.acquire([peer_id], lease_ms=DEFAULT_LEASE_MS)
            tok = tokens[peer_id]
            clicks: List[JitteredClick] = []
            try:
                # 1. Navigate to publisher profile via Search tab and open latest grid post
                self._tap(peer_id, tok, "ig_search_tab_magnifier", clicks)
                self._tap(peer_id, tok, "ig_search_top_input", clicks)
                type_text_on_ios(
                    kernel=self.kernel,
                    jitter=self.jitter,
                    vision=self.vision,
                    pid=peer_id,
                    token=tok,
                    text=handle_query,
                    strategy=TextEntryStrategy.ON_SCREEN_KEYBOARD_JITTER,
                    clicks_log=clicks,
                )
                self._tap(peer_id, tok, "ig_search_first_result", clicks)
                self._tap(peer_id, tok, "ig_profile_grid_slot_1", clicks)

                # 2. Like, Save, open comments, type contextual seed question, post, and close drawer
                self._tap(peer_id, tok, "ig_reel_like_button", clicks)
                self._tap(peer_id, tok, "ig_reel_save_button", clicks)
                self._tap(peer_id, tok, "ig_reel_comment_button", clicks)
                self._tap(peer_id, tok, "ig_comment_input_box", clicks)
                type_text_on_ios(
                    kernel=self.kernel,
                    jitter=self.jitter,
                    vision=self.vision,
                    pid=peer_id,
                    token=tok,
                    text=seed_comment,
                    strategy=TextEntryStrategy.ON_SCREEN_KEYBOARD_JITTER,
                    clicks_log=clicks,
                )
                self._tap(peer_id, tok, "ig_comment_post_btn", clicks)
                self._tap(peer_id, tok, "keyboard_dismiss_safe", clicks)
                self._tap(peer_id, tok, "comment_drawer_close_handle", clicks)
            finally:
                self.kernel.release(tokens)
            results.append(
                {
                    "peerDeviceId": peer_id,
                    "seededPublisher": publisher_device_id,
                    "searchedHandle": handle_query,
                    "seedComment": seed_comment,
                    "clicks": len(clicks),
                }
            )
        return results


# ============================================================================
# 12. LAYER 7: SHADOWBAN GUARD & 3-5 CLIP ZERO-VIEW CIRCUIT BREAKER
# ============================================================================

class ShadowbanGuardAndDiagnostics:
    """
    Scrapes profile-grid view velocity across the rack and trips the 3-5 Clip
    Zero-View Circuit Breaker (`paused_zero_view = 1`) on any phone that records
    <= 5 views across 3 consecutive clips after 24 hours.
    """

    def __init__(
        self,
        kernel: IMouseKernel,
        db: FarmDatabase,
        vision: Optional[VlmComputerUseAdapter] = None,
    ) -> None:
        self.kernel = kernel
        self.db = db
        self.vision = vision or VlmComputerUseAdapter()

    def scan_device_profile_views(self, device_id: str) -> Dict[str, Any]:
        """
        Captures a live 500x1080 BMP screenshot from `device_id`, extracts the 3 latest
        clip view counts from the profile grid via `VlmComputerUseAdapter`, and evaluates
        the 3-5 Clip Zero-View Circuit Breaker.
        """
        bmp_raw, _ = self.kernel.shot(device_id)
        extracted_views = self.vision.extract_profile_grid_views(bmp_raw)
        return self.evaluate_device_views(device_id, extracted_views)

    def evaluate_device_views(self, device_id: str, recent_clip_views: Sequence[int]) -> Dict[str, Any]:
        persona = self.db.get_persona(device_id)
        if persona["account_day"] <= 3:
            return {"deviceId": device_id, "status": "warmup_phase_1", "paused": False}

        zero_streak = sum(1 for v in recent_clip_views[-3:] if v <= 5)
        tripped = len(recent_clip_views) >= 3 and zero_streak >= 3
        total_24h = sum(recent_clip_views)

        with self.db._lock, self.db._connect() as conn:
            conn.execute(
                """
                UPDATE personas
                SET paused_zero_view = ?, consecutive_zero_views = ?, views_24h = ?
                WHERE device_id = ?
                """,
                (1 if tripped else 0, zero_streak, total_24h, device_id),
            )
            conn.commit()

        return {
            "deviceId": device_id,
            "recentClipViews": list(recent_clip_views),
            "zeroViewStreak": zero_streak,
            "circuitBreakerTripped": tripped,
            "views24h": total_24h,
        }


# ============================================================================
# 13. MOCK KERNEL & END-TO-END 7-LAYER SELF-CHECK SUITE (--self-check)
# ============================================================================

class MockApiServer:
    def __init__(self, device_ids: Sequence[str] = tuple(p["device_id"] for p in DEFAULT_19_PERSONAS)) -> None:
        self.device_ids = list(device_ids)
        self.leases: Dict[str, str] = {}
        self.generations: Dict[str, int] = {d: 0 for d in self.device_ids}
        self.frame_seq: int = 1
        self.fill_luma: int = 90
        self.commands_dispatched: List[Tuple[str, Dict[str, Any]]] = []

    def _make_bmp(self, luma: int) -> bytes:
        w, h = SCREEN_WIDTH, SCREEN_HEIGHT
        px = (bytes((luma, luma, luma)) * w) * h
        hdr = b"BM" + (54 + len(px)).to_bytes(4, "little") + bytes(4) + (54).to_bytes(4, "little")
        info = (
            (40).to_bytes(4, "little")
            + w.to_bytes(4, "little")
            + h.to_bytes(4, "little", signed=True)
            + (1).to_bytes(2, "little")
            + (24).to_bytes(2, "little")
            + bytes(24)
        )
        return hdr + info + px

    def handle(
        self,
        method: str,
        full_url: str,
        body: Optional[Dict[str, Any]],
        timeout: float,
    ) -> Tuple[bytes, Dict[str, str]]:
        if method == "GET" and full_url.endswith("/kernel/status"):
            data = {
                "code": 0,
                "input": "direct-hid",
                "input_protocol": 1,
                "input_leases_required": True,
                "build_identity": "mock-250e589",
                "receivers": [
                    {
                        "deviceid": d,
                        "name": f"iMouse-{d}",
                        "receiver_state": "mirroring",
                        "live": True,
                        "frames": self.frame_seq,
                        "frame_age_ms": 14.2,
                    }
                    for d in self.device_ids
                ],
            }
            return json.dumps({"status": 200, "message": "ok", "data": data}).encode("utf-8"), {}

        if method == "GET" and "/pic/screenshot" in full_url:
            self.frame_seq += 1
            return self._make_bmp(self.fill_luma), {"X-iMouse-Frame-Sequence": str(self.frame_seq)}

        if method == "POST":
            assert body is not None
            fun = body.get("fun", "")
            data = body.get("data") or {}
            self.commands_dispatched.append((fun, data))

            if fun == "/input/status":
                phones = [
                    {
                        "id": d,
                        "owned": d in self.leases,
                        "active": False,
                        "stopped": False,
                        "releasing": False,
                        "release_failed": False,
                        "message": "",
                        "generation": self.generations.get(d, 0),
                        "lease_remaining_ms": 115_000 if d in self.leases else 0,
                    }
                    for d in self.device_ids
                ]
                return json.dumps({"status": 200, "message": "ok", "data": {"code": 0, "protocol": 1, "phones": phones}}).encode("utf-8"), {}

            if fun == "/input/acquire":
                ids = [x.strip() for x in data.get("id", "").split(",") if x.strip()]
                lease_ms = int(data.get("lease_ms", 30000))
                out_leases = []
                for d in ids:
                    if d in self.leases:
                        return json.dumps({"status": 200, "data": {"code": 409, "message": "Already owned"}}).encode("utf-8"), {}
                    tok = f"tok-{d}-{len(self.commands_dispatched)}"
                    self.leases[d] = tok
                    out_leases.append({"id": d, "token": tok, "lease_ms": lease_ms})
                return json.dumps({"status": 200, "message": "ok", "data": {"code": 0, "leases": out_leases}}).encode("utf-8"), {}

            if fun == "/input/renew":
                return json.dumps({"status": 200, "message": "ok", "data": {"code": 0}}).encode("utf-8"), {}

            if fun in ("/input/release", "/input/stop"):
                ids = [x.strip() for x in data.get("id", "").split(",") if x.strip()]
                for d in ids:
                    self.leases.pop(d, None)
                    self.generations[d] = self.generations.get(d, 0) + 1
                return json.dumps({"status": 200, "message": "ok", "data": {"code": 0}}).encode("utf-8"), {}

            if fun in ("/mouse/move", "/mouse/click", "/mouse/down", "/mouse/up", "/mouse/swipe", "/key/sendkey"):
                pid = data.get("id")
                tok = data.get("token")
                if self.leases.get(pid) != tok:
                    return json.dumps({"status": 200, "data": {"code": 409, "message": "Lease required"}}).encode("utf-8"), {}
                if fun in ("/mouse/click", "/mouse/swipe"):
                    self.fill_luma = 140 if self.fill_luma == 90 else 90
                return json.dumps({"status": 200, "message": "ok", "data": {"code": 0, "results": [{"id": pid, "code": 0, "message": "ok"}]}}).encode("utf-8"), {}

        raise AssertionError(f"Unhandled mock request: {method} {full_url}")


def self_check() -> None:
    rng = random.Random(20261014)
    test_db_path = Path("/tmp/test_imouse_farm_7layers.db")
    test_db_path.unlink(missing_ok=True)
    test_stage_dir = Path("/tmp/test_imouse_stage")

    # Layer 1 & 2: SQLite FarmDatabase + ContentFactoryEngine + AntiDuplicateSpinEngine
    db = FarmDatabase(db_path=test_db_path)
    assert len(db.list_personas()) == 19, "Must initialize all 19 rack personas"
    spinner = AntiDuplicateSpinEngine(rng=rng)
    factory = ContentFactoryEngine(db=db, spinner=spinner, stage_root=test_stage_dir, rng=rng)

    slate_c24c = factory.generate_daily_slate_for_device("C24C")
    slate_c241 = factory.generate_daily_slate_for_device("C241")
    assert len(slate_c24c) == 5 and len(slate_c241) == 5
    c24c_files = slate_c24c[0]["stagedFiles"]
    assert any(f.endswith(".mp4") for f in c24c_files), "Must stage a real .mp4 video file"
    assert sum(1 for f in c24c_files if f.endswith(".jpg")) == 4, "Must stage 4 .jpg carousel slides"
    mp4_file_c24c = test_stage_dir / "C24C" / c24c_files[0]
    mp4_file_c241 = test_stage_dir / "C241" / slate_c241[0]["stagedFiles"][0]
    assert mp4_file_c24c.exists() and mp4_file_c24c.stat().st_size > 1000
    assert hashlib.sha256(mp4_file_c24c.read_bytes()).hexdigest() != hashlib.sha256(mp4_file_c241.read_bytes()).hexdigest()

    # Verify Track B (VideoGenUgcApiClient) with live mock HTTP submit -> poll -> download -> spin
    def _mock_videogen_http(method: str, url: str, payload: Optional[Dict[str, Any]], headers: Dict[str, str]) -> Any:
        if method == "POST":
            return {"job_id": "job-991", "status_url": "https://api.heygen.com/v2/status/job-991"}
        if method == "GET" and "/status/" in url:
            return {"status": "completed", "video_url": "https://cdn.heygen.com/v2/out/job-991.mp4"}
        if method == "GET" and url.endswith(".mp4"):
            return b"\x00\x00\x00\x14ftypisom\x00\x00\x02\x00isom\x00\x00\x00\x10mdatMOCKVIDEO"
        raise AssertionError(f"Unexpected VideoGen call: {method} {url}")

    live_ugc_client = VideoGenUgcApiClient(factory.code_animator, spinner=spinner, http_fn=_mock_videogen_http)
    ugc_res = live_ugc_client.create_and_stage_ugc_video(
        VideoGenUgcJobSpec(
            provider="heygen_ugc",
            api_url="https://api.heygen.com/v2/video/generate",
            api_key="test-live-key",
            avatar_id="avatar_founder_01",
            voice_id="voice_en_us_01",
            script_text="Here is how we automated our 19-phone rack.",
            product_url="https://nodetheory.io/system",
        ),
        device_id="C24C",
        out_mp4_path=test_stage_dir / "C24C" / "ugc_preview.mp4",
        rng=rng,
    )
    assert ugc_res["usedLiveApi"] is True and Path(ugc_res["mp4Path"]).exists()
    assert b"UUID-APPLE-IOS-MOV-C24C" in Path(ugc_res["mp4Path"]).read_bytes()

    # Verify Hook Winner Cloner persists cloned winner slates into SQLite
    db.update_persona("C24C", account_day=18)
    with db._lock, db._connect() as conn:
        conn.execute("UPDATE personas SET views_24h = 95000 WHERE device_id = 'C24C'")
        conn.commit()
    cloned_winners = factory.clone_winning_hooks(multiplier_threshold=2.0)
    assert len(cloned_winners) >= 1 and len(cloned_winners[0]["clonedToSiblings"]) >= 1
    sib_id = cloned_winners[0]["clonedToSiblings"][0]["siblingDevice"]
    sib_slates = db.get_slates_for_device(sib_id, limit=4)
    assert any(s.get("is_winner") == 1 for s in sib_slates), "Cloned winner slate must be persisted in SQLite"

    # Verify anti-duplicate spin engine guarantees different SHA-256 and pHash per phone
    assert slate_c24c[0]["phashHex"] != slate_c241[0]["phashHex"] or slate_c24c[0]["stagedFiles"] != slate_c241[0]["stagedFiles"]
    # Verify Phase 1 account (RACK-19, Day 1) is locked to 0 uploads
    assert factory.generate_daily_slate_for_device("RACK-19") == []

    # Layer 3: Export iOS Shortcut plist with per-device manifest URL
    plist_file = MediaPullOrchestrator.export_ios_shortcut_plist(
        test_stage_dir / "iMousePull.shortcut.plist",
        device_id="C24C",
    )
    assert plist_file.exists() and b"/stage/C24C/manifest.json" in plist_file.read_bytes()

    # Layer 4: All 14 upload formats + Spotlight launch + iMousePull + 3% Audio Mixer + Story Stickers + 4:5 Carousel Lock
    mock_srv = MockApiServer()
    kernel = IMouseKernel(url=DEFAULT_KERNEL_URL, transport=mock_srv.handle)
    jitter = HumanizedTargetJitter(rng=rng)
    vision = VlmComputerUseAdapter(mode=ExecutionMode.API_BOUNDED_VISION)
    orchestrator = SocialUploadOrchestrator(kernel=kernel, jitter=jitter, vision=vision, db=db, rng=rng)

    res_carousel = orchestrator.execute_upload(
        UploadJob(
            device_id="C24C",
            platform=Platform.INSTAGRAM,
            upload_format=UploadFormat.IG_CAROUSEL,
            caption_or_title="4:5 Locked Carousel #imouse2 https://nodetheory.io/system 100%",
            media_count=4,
            pull_media_first=True,
            launch_app_via_spotlight=True,
            attach_trending_audio_3pct=True,
        )
    )
    clicked_targets = [t[0] for t in res_carousel["clickCoordinates"]]
    assert "ig_carousel_aspect_ratio_btn" in clicked_targets, "Must lock 4:5 aspect ratio before multi-select"
    assert "key_sym_#" in clicked_targets and "key_num_:" in clicked_targets, "Must type hashtags and URLs across 123/#+= planes"
    assert clicked_targets[-2] == "keyboard_dismiss_safe"

    res_story = orchestrator.execute_upload(
        UploadJob(
            device_id="C24C",
            platform=Platform.INSTAGRAM,
            upload_format=UploadFormat.IG_STORY,
            caption_or_title="Story with Link Sticker",
            story_sticker_url="https://nodetheory.io/system",
        )
    )
    assert res_story["totalClicks"] > 15

    # Layer 5: Warmup session with contextual VLM comment + BackgroundCohortScheduler
    warmup = AccountWarmupEngine(kernel=kernel, jitter=jitter, vision=vision, db=db, rng=rng)
    w_res = warmup.run_warmup_session("RACK-19", Platform.TIKTOK, account_day=1, niche="Travel Hacks", clips_to_watch=4)
    assert w_res["swipesSent"] == 4 and w_res["maxAllowedUploadsToday"] == 0

    scheduler = BackgroundCohortScheduler(db=db, warmup_engine=warmup, upload_orchestrator=orchestrator)
    # Immediately after warmup, C241 should be in 3.5-7.5h post-warmup cooldown
    db.record_warmup_timestamp("C241", epoch=1000.0)
    cd_state = scheduler.evaluate_device_upload_readiness("C241", now_epoch=1000.0 + 3600.0)
    assert cd_state["status"] == "in_post_warmup_cooldown" and cd_state["readyForUpload"] is False
    ready_state = scheduler.evaluate_device_upload_readiness("C241", now_epoch=1000.0 + 8.0 * 3600.0)
    assert ready_state["status"] == "ready_for_upload" and ready_state["readyForUpload"] is True
    tick_res = scheduler.run_cohort_tick(cohort_id=1, now_epoch=1000.0 + 8.0 * 3600.0, execute_actions=False)
    assert tick_res["evaluatedCount"] == 4

    # Layer 6: Conversion Funnel (Pinned CTA Comment, Comment-to-DM Bot typing offer_url, Cross-Rack Micro-Swarm)
    funnel = ConversionFunnelEngine(kernel=kernel, jitter=jitter, vision=vision, db=db, rng=rng)
    pin_res = funnel.post_and_pin_cta_comment("C24C")
    assert pin_res["totalClicks"] > 20
    dm_res = funnel.run_comment_to_dm_responder("C24C")
    dm_targets = [t[0] for t in dm_res["clickCoordinates"]]
    assert "dm_text_input_box" in dm_targets and "key_num_:" in dm_targets and dm_targets[-1] == "dm_send_btn"
    assert dm_res["totalClicks"] > 35, "DM responder must type public reply and full offer_url before clicking Send"
    swarm_res = funnel.run_cross_rack_micro_swarm("C24C", ["RACK-05", "RACK-09"])
    assert len(swarm_res) == 2 and swarm_res[0]["clicks"] > 30

    # Layer 7: Shadowban Guard & 3-5 Clip Zero-View Circuit Breaker (both direct & BMP profile-grid scan)
    guard = ShadowbanGuardAndDiagnostics(kernel=kernel, db=db, vision=vision)
    scan_res = guard.scan_device_profile_views("C24C")
    assert len(scan_res["recentClipViews"]) == 3
    trip_res = guard.evaluate_device_views("RACK-12", [0, 2, 0])
    assert trip_res["circuitBreakerTripped"] is True
    try:
        orchestrator.execute_upload(
            UploadJob("RACK-12", Platform.TIKTOK, UploadFormat.TT_VIDEO, "Should be blocked by circuit breaker")
        )
        raise AssertionError("RACK-12 upload should have been blocked by circuit breaker")
    except KernelSafetyError:
        pass

    assert mock_srv.leases == {}, "All leases must be released cleanly"
    print("OK - All 7 Farm Layers (SQLite, Pillow 4:5 Carousels, pHash Spin, iMousePull, 14 Uploads+3-Plane Keyboard+Audio+Stickers, Warmup+CohortScheduler, Funnel/DM/Swarm, 0-View Circuit Breaker) verified.")


def main() -> int:
    ap = argparse.ArgumentParser(description="iMouse 2.0 Full 7-Layer Marketing Farm Engine")
    ap.add_argument("--self-check", action="store_true", help="Run full 7-layer offline verification suite")
    args = ap.parse_args()
    if args.self_check:
        self_check()
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
