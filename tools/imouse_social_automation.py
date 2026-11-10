#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
iMouse 2.0 farm engine: local content preparation and the kernel client.

Two things live here, and nothing that publishes, messages or engages:
  - Content preparation: `FarmDatabase` (the content profiles and the prepared slates),
    `ContentFactoryEngine` with its renderers (`LlmCodeAnimationEngine`, `AntiDuplicateSpinEngine`).
    It renders review media into the stage folder from local templates. No phone, no kernel.
  - `IMouseKernel` and `KernelSafetyError`: the kernel client every draft workflow builds on. It
    refuses any target but its own phone before a request leaves this process.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
import hashlib
import html
import io
import json
import math
import os
from pathlib import Path
import random
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
import urllib.error
import urllib.parse
import urllib.request
import uuid
from farm_phone_identity import LEGACY_C24C, PhoneIdentity, PhoneIdentityError, own_receiver

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
# CONSTANTS
# ============================================================================

# The pre-rack single phone. Live draft windows take their phone from their prepared config.
DEFAULT_KERNEL_URL = "http://127.0.0.1:9913/api"
FORBIDDEN_VENDOR_PORT = 9911
DEFAULT_SAFE_TEST_DEVICE = LEGACY_C24C.board
LIVE_TEST_DEVICE_ID = LEGACY_C24C.device_id


def persona_device_id(value: str) -> str:
    """Map the verified console ID to its stored persona, without guessing bindings."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Select a device.")
    value = value.strip()
    return "C24C" if value.upper() in (LIVE_TEST_DEVICE_ID, "C24C") else value


DEFAULT_LEASE_MS = 120_000
RENEW_THRESHOLD_MS = 25_000
KERNEL_COMMAND_DEADLINE_S = 8.0


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
# CONTENT PREPARATION: the profile and slate store
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
    Thread-safe SQLite store for content preparation:
      - personas: the content profile per phone (niche, voice, CTA keyword, offer URL) the factory writes for
      - content_slates: every prepared item with its staged files and checksums
    The tables keep the columns earlier versions created (cohort, warmup and view counters, upload_logs),
    so an existing farm.db opens unchanged; nothing reads or writes those any more.
    """

    def __init__(self, db_path: Path = Path("output/farm-data/imouse_farm.db")) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

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
                    default_views = -1  # Unknown until supplied by a verified observation.
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

    def get_persona(self, device_id: str) -> Dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM personas WHERE device_id = ?", (device_id,)).fetchone()
            if not row:
                raise KeyError(f"Unknown persona device_id: {device_id}")
            return dict(row)

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


# ============================================================================
# CONTENT PREPARATION: per-phone variants, fonts, the video renderer and the factory
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
            if not writer.isOpened():
                writer.release()
                raise RuntimeError("The video encoder could not start; no video was generated.")
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
            raise RuntimeError("Video generation requires Pillow and OpenCV. Install the farm dependencies first.")

        mp4_bytes = out_mp4_path.read_bytes()
        phash_hex = AntiDuplicateSpinEngine.compute_dhash_hex(first_frame_bytes or mp4_bytes)
        sha256_hex = hashlib.sha256(mp4_bytes).hexdigest()
        return out_mp4_path, phash_hex, sha256_hex


class ContentFactoryEngine:
    """
    Prepares one batch of review media for a phone's content profile:
      - Niche hooks & captions tailored to the profile's `niche`, `brand_voice`, and `cta_keyword`
      - Real `1080x1350` / `540x675` (4:5 locked aspect ratio) multi-slide JPEG carousels rendered via Pillow
      - Real MP4/synthetic vertical video container staged per device
    """

    HOOK_TEMPLATES: List[str] = [
        "A practical checklist for {niche}",
        "Plan your next {niche} project",
        "Four questions to ask before starting {niche}",
        "A starting point for your {niche} workflow",
        "Review and improve your {niche} process",
    ]

    def __init__(
        self,
        db: FarmDatabase,
        spinner: AntiDuplicateSpinEngine,
        stage_root: Path = Path("output/media-stage"),
        rng: Optional[random.Random] = None,
        code_animator: Optional[LlmCodeAnimationEngine] = None,
    ) -> None:
        self.db = db
        self.spinner = spinner
        self.stage_root = stage_root
        self.rng = rng or random.Random()
        self.code_animator = code_animator or LlmCodeAnimationEngine()

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

        raise RuntimeError("Carousel rendering requires Pillow; no image was generated.")

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

        # Old slates retain their files. A failed render must not invalidate the
        # current manifest or an export that is already downloading.
        generation = uuid.uuid4().hex

        hook_base = self.rng.choice(self.HOOK_TEMPLATES).format(niche=niche)
        caption = (
            f"{hook_base}. Explore {offer_url} #{kw.lower()}"
        )

        slides_copy = [
            f"Slide 1: {hook_base}",
            f"Slide 2: Define the audience and outcome for {niche}",
            f"Slide 3: Choose one useful action and measure its result",
            f"Slide 4: Learn more at {offer_url}",
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
            fname = f"slide_{generation}_{idx:02d}_{phash[:8]}.jpg"
            (dev_stage_dir / fname).write_bytes(spun_jpg)
            staged_filenames.append(fname)
            last_phash, last_sha256 = phash, sha256

        # Compile the 9:16 `.mp4` video animation.
        anim_spec = self.code_animator.generate_animation_code_spec(
            device_id=device_id,
            niche=niche,
            brand_voice=persona["brand_voice"],
            cta_keyword=kw,
            rng=self.rng,
        )
        mp4_temp_name = f"render_{generation}.mp4"
        mp4_path, mp4_phash, _ = self.code_animator.compile_code_spec_to_mp4(
            spec=anim_spec,
            out_mp4_path=dev_stage_dir / mp4_temp_name,
            device_id=device_id,
        )
        spun_mp4_bytes, _, mp4_sha256 = self.spinner.spin_video_mp4_for_device(
            mp4_path.read_bytes(),
            device_id=device_id,
        )
        mp4_path.unlink(missing_ok=True)
        mp4_final_name = f"video_{generation}_{mp4_phash[:8]}.mp4"
        final_mp4_path = dev_stage_dir / mp4_final_name
        final_mp4_path.write_bytes(spun_mp4_bytes)
        staged_filenames.insert(0, mp4_final_name)
        last_phash, last_sha256 = mp4_phash, mp4_sha256

        # The batch's manifest: what was rendered, with a checksum per file.
        manifest = {
            "deviceId": device_id,
            "niche": niche,
            "ctaKeyword": kw,
            "offerUrl": offer_url,
            "caption": caption,
            "generatedAt": utc_now(),
            "phashHex": last_phash,
            "sha256Hex": last_sha256,
            "generation": generation,
            "contentSource": "local_templates",
            "reviewRequired": True,
            "files": [f"/stage/{device_id}/{fn}" for fn in staged_filenames],
            "assets": [{"url": f"/stage/{device_id}/{fn}", "sha256": hashlib.sha256((dev_stage_dir / fn).read_bytes()).hexdigest(),
                        "bytes": (dev_stage_dir / fn).stat().st_size} for fn in staged_filenames],
        }
        manifest_tmp = dev_stage_dir / f"manifest_{generation}.tmp"
        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
        manifest_tmp.write_bytes(manifest_bytes)
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()

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
                    "generation": generation,
                    "manifest": f"/stage/{device_id}/manifest_{generation}.json",
                    "manifestSha256": manifest_sha256,
                }
            )
        # Publish only after every asset and slate row exists. Existing assets are
        # immutable, so a reviewer can keep an older preview open while rendering.
        # Keep the exact manifest for each run. The latest pointer is convenient
        # for manual review, but cannot identify an older scheduled batch.
        manifest_tmp.replace(dev_stage_dir / f"manifest_{generation}.json")
        manifest_tmp.write_bytes(manifest_bytes)
        manifest_tmp.replace(dev_stage_dir / "manifest.json")
        media_html = []
        for name in staged_filenames:
            safe_name = html.escape(name, quote=True)
            preview = (f'<video controls preload="metadata" src="{safe_name}"></video>' if name.endswith(".mp4")
                       else f'<img loading="lazy" src="{safe_name}" alt="Carousel draft">')
            media_html.append(f'<article>{preview}<a download href="{safe_name}">Download asset</a></article>')
        review = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                  '<title>iMouse content review</title><style>body{font:16px system-ui;background:#f5f7fb;color:#18243a;margin:32px auto;padding:0 24px;max-width:1100px}'
                  'h1{font-size:28px}header,p{max-width:800px;line-height:1.6}section{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:18px}'
                  'article,pre{background:white;border:1px solid #dbe2ed;border-radius:12px;padding:16px}img,video{width:100%;max-height:440px;object-fit:contain}'
                  'a{display:block;color:#165cc7;margin-top:12px}pre{white-space:pre-wrap;font:inherit}</style>'
                  f'<header><h1>{html.escape(niche)}</h1><p>Draft for {html.escape(device_id)}. Generated from local templates. Review the copy and media before use. Nothing has been published or sent.</p></header>'
                  f'<h2>Caption</h2><pre>{html.escape(caption)}</pre><h2>Media</h2><section>{"".join(media_html)}</section>'
                  '<a href="manifest.json">Manifest and checksums</a></html>')
        review_tmp = dev_stage_dir / f"review_{generation}.tmp"
        review_tmp.write_text(review, encoding="utf-8")
        review_tmp.replace(dev_stage_dir / "review.html")
        return created_items


# ============================================================================
# KERNEL CLIENT (`ApiServer.cs` / `InputSessions.cs` / `FrameStore.cs`)
# ============================================================================

class KernelSafetyError(RuntimeError):
    pass


class IMouseKernel:
    def __init__(
        self,
        url: str = DEFAULT_KERNEL_URL,
        transport: Optional[Callable[[str, str, Optional[Dict[str, Any]], float], Tuple[bytes, Dict[str, str]]]] = None,
        phone: PhoneIdentity = LEGACY_C24C,
    ) -> None:
        if not isinstance(phone, PhoneIdentity):
            raise KernelSafetyError("A kernel client needs an explicit phone identity.")
        self.phone = phone
        self.url = url.rstrip("/")
        if f":{FORBIDDEN_VENDOR_PORT}" in self.url:
            raise KernelSafetyError(f"Refusing vendor port {FORBIDDEN_VENDOR_PORT}; use port 9913.")
        self._is_live_http = transport is None
        self._transport = transport or self._http_transport
        self._id_alias_map: Dict[str, str] = {}
        self.audit_log: List[Dict[str, Any]] = []

    def _require_live_target(self, pid: str) -> None:
        if self._is_live_http and not self.phone.targets(pid):
            raise KernelSafetyError(f"Live farm control is restricted to {self.phone.board}; target {pid!r} is not approved. Use explicit simulation for other phones.")

    def _validate_post_target(self, fun: str, data: Dict[str, Any]) -> None:
        if not self._is_live_http or fun == "/input/status":
            return
        raw = data.get("id")
        if not isinstance(raw, str) or not raw:
            raise KernelSafetyError(f"Live farm input requires an explicit {self.phone.board} target.")
        for pid in raw.split(","):
            self._require_live_target(pid)
        for field in ("tokens", "generations"):
            values = data.get(field)
            if values is not None:
                if not isinstance(values, dict):
                    raise KernelSafetyError(f"{field} must be a per-phone object.")
                for pid in values:
                    self._require_live_target(pid)

    def resolve_device_id(self, pid: str) -> str:
        self._require_live_target(pid)
        if not self._is_live_http:
            return pid
        if pid.upper() == self.phone.device_id:
            return self.phone.device_id
        if pid in self._id_alias_map:
            return self._id_alias_map[pid]
        # The board PID resolves only when the kernel reports this phone's own receiver, by
        # device ID and name; another phone's receiver can never stand in for it.
        try:
            own_receiver(self.kernel_status(), self.phone)
        except PhoneIdentityError as error:
            raise KernelSafetyError(f"The expected {self.phone.receiver} receiver identity is missing; refusing input.") from error
        self._id_alias_map[pid] = self.phone.device_id
        return self.phone.device_id

    def _http_transport(
        self,
        method: str,
        full_url: str,
        body: Optional[Dict[str, Any]],
        timeout: float,
    ) -> Tuple[bytes, Dict[str, str]]:
        if body is not None and isinstance(body.get("data"), dict):
            self._validate_post_target(str(body.get("fun") or ""), body["data"])
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

    def post(self, fun: str, data: Dict[str, Any], timeout: float = 25.0) -> Dict[str, Any]:
        self._validate_post_target(fun, data)
        raw, _ = self._transport("POST", self.url + "/", {"fun": fun, "data": data}, timeout)
        envelope = json.loads(raw.decode("utf-8"))
        payload = envelope.get("data") if isinstance(envelope, dict) and "data" in envelope else envelope
        self.audit_log.append({"at": utc_now(), "fun": fun, "data": data, "reply": payload, "simulated": not self._is_live_http})
        if len(self.audit_log) > 250:
            self.audit_log = self.audit_log[-250:]
        return payload

    def kernel_status(self) -> Dict[str, Any]:
        raw, _ = self._transport("GET", self.url + "/kernel/status", None, 5.0)
        return json.loads(raw.decode("utf-8"))["data"]

    def input_status(self) -> Dict[str, Dict[str, Any]]:
        reply = self.post("/input/status", {}, timeout=5.0)
        return {p["id"]: p for p in reply.get("phones") or []}

    def shot(self, pid: str) -> Tuple[bytes, Dict[str, str]]:
        resolved = self.resolve_device_id(pid)
        q = urllib.parse.quote(resolved)
        raw, headers = self._transport("GET", f"{self.url}/pic/screenshot?id={q}&binary=true", None, 8.0)
        if raw[:2] != b"BM":
            raise KernelSafetyError(f"No live BMP screenshot for {pid} ({resolved})")
        return raw, headers

    def preflight_phone(self, pid: str) -> Dict[str, Any]:
        resolved = self.resolve_device_id(pid)
        ks = self.kernel_status()
        if ks.get("input_leases_required") is not True:
            raise KernelSafetyError("Kernel does not enforce input leases; refusing.")
        receivers = {r.get("deviceid"): r for r in ks.get("receivers") or []}
        rec = receivers.get(resolved) or {}
        if not rec.get("live"):
            raise KernelSafetyError(f"Phone {pid} ({resolved}) is not mirroring.")
        st = self.input_status().get(resolved)
        if not st:
            raise KernelSafetyError(f"Phone {pid} ({resolved}) missing from /input/status.")
        for flag in ("owned", "active", "stopped", "releasing", "release_failed"):
            if st.get(flag) is not False:
                raise KernelSafetyError(f"Phone {pid} ({resolved}) input '{flag}'={st.get(flag)!r}; refusing takeover.")
        return {"receiver": rec, "input_status": st, "resolved_id": resolved, "simulated": not self._is_live_http}

    def acquire(self, ids: List[str], lease_ms: int = DEFAULT_LEASE_MS) -> Dict[str, str]:
        if not ids:
            raise KernelSafetyError("Select a phone before acquiring input.")
        for pid in ids:
            self._require_live_target(pid)
        orig_to_resolved = {orig: self.resolve_device_id(orig) for orig in ids}
        resolved_to_orig = {v: k for k, v in orig_to_resolved.items()}
        resolved_ids = list(orig_to_resolved.values())
        got = self.post("/input/acquire", {"id": ",".join(resolved_ids), "lease_ms": lease_ms})
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
        for pid in tokens:
            self._require_live_target(pid)
        resolved_tokens = {self.resolve_device_id(k): v for k, v in tokens.items()}
        st = self.input_status()
        if any(st.get(r_id, {}).get("lease_remaining_ms", 0) < min_remaining_ms for r_id in resolved_tokens):
            got = self.post(
                "/input/renew",
                {"id": ",".join(resolved_tokens), "tokens": resolved_tokens},
            )
            if got.get("code") != 0:
                raise KernelSafetyError("Renew failed: " + str(got))
            return True
        return False

    def release(self, tokens: Dict[str, str]) -> None:
        if not tokens:
            return
        for pid in tokens:
            self._require_live_target(pid)
        resolved_tokens = {self.resolve_device_id(k): v for k, v in tokens.items()}
        got = self.post(
            "/input/release",
            {"id": ",".join(resolved_tokens), "tokens": resolved_tokens},
        )
        if got.get("code") != 0:
            raise KernelSafetyError("Release unconfirmed: " + str(got))

    def send(self, pid: str, token: str, fun: str, **data: Any) -> Dict[str, Any]:
        if {"id", "token", "tokens"}.intersection(data):
            raise KernelSafetyError("Command data cannot override its target or lease.")
        resolved = self.resolve_device_id(pid)
        t0 = time.perf_counter()
        got = self.post(
            fun,
            {"id": resolved, "token": token, **data},
            timeout=KERNEL_COMMAND_DEADLINE_S + 2.0,
        )
        got["rtt_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        if not (got.get("code") == 0 and all(r.get("code") == 0 for r in got.get("results") or [])):
            raise KernelSafetyError(f"{fun} on {pid} ({resolved}) failed: {got}")
        return got
