"""Local carousel drafts. No network, phone transport, or publication capability.

Limits are this candidate's supported editing contract, not a claim about the
maximum accepted by every Instagram version. Original images stay untouched.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import html
import io
import json
import re
from pathlib import Path
import sqlite3
import threading
import uuid
import warnings
import zipfile
from datetime import datetime, timezone

from PIL import Image, ImageOps

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_SLIDES = 10
MAX_CAPTION = 2200


class DraftConflict(ValueError):
    pass


def identifier(value):
    if not isinstance(value, str):
        raise ValueError("Draft ID must be a UUID.")
    return str(uuid.UUID(value))


def checked_text(value, label, maximum, *, required=False):
    if (not isinstance(value, str) or len(value) > maximum or
            any(ord(c) < 32 and c not in "\n\t" for c in value)):
        raise ValueError(f"{label} must be text with at most {maximum} characters and no control codes.")
    value.encode("utf-8", errors="strict")
    if required and not value.strip():
        raise ValueError(f"{label} cannot be empty.")
    return value


def generated_manifest(stage_root, generation=None, checksum=None):
    """Read either the latest batch or a checksum-pinned historical batch."""
    pinned = generation is not None or checksum is not None
    if pinned and (not isinstance(generation, str) or not re.fullmatch(r'[0-9a-f]{32}', generation) or
                   not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-f]{64}', checksum)):
        raise ValueError('A generated batch needs its exact generation and manifest checksum.')
    folder = (Path(stage_root) / 'C24C').resolve()
    path = folder / (f'manifest_{generation}.json' if pinned else 'manifest.json')
    if not path.is_file(): raise ValueError('Generated batch is missing. No newer batch was substituted.')
    if not path.resolve().is_relative_to(folder) or path.stat().st_size > 128 * 1024:
        raise ValueError('Generated manifest is outside the media folder or too large.')
    raw = path.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    if pinned and digest != checksum: raise ValueError('Generated manifest checksum changed; this batch cannot be reviewed.')
    document = json.loads(raw)
    if not isinstance(document, dict) or not isinstance(document.get('assets'), list): raise ValueError('Invalid generated manifest.')
    if pinned and (document.get('generation') != generation or document.get('deviceId') != 'C24C'):
        raise ValueError('Generated manifest does not belong to this C24C batch.')
    return document, digest


def prepare_image(raw, name):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_IMAGE_BYTES:
        raise ValueError("Each image must be nonempty and at most 8 MiB.")
    name = checked_text(name, "Image name", 200, required=True)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ("JPEG", "PNG") or getattr(source, "n_frames", 1) != 1:
                    raise ValueError("Choose a static JPEG or PNG image.")
                if source.width * source.height > MAX_PIXELS:
                    raise ValueError("Image exceeds the 40 megapixel editing limit.")
                source.load()  # A header alone does not establish a valid image.
                oriented = ImageOps.exif_transpose(source).convert("RGBA")
                width, height = oriented.size
                # Fit the whole image. Do not crop meaningful content off a slide.
                fitted = ImageOps.contain(oriented, (1080, 1350), Image.Resampling.LANCZOS)
                canvas = Image.new("RGB", (1080, 1350), "white")
                canvas.paste(fitted, ((1080 - fitted.width) // 2, (1350 - fitted.height) // 2), fitted)
                output = io.BytesIO()
                canvas.save(output, "JPEG", quality=94)
                thumbnail = canvas.copy()
                thumbnail.thumbnail((240, 300))
                preview = io.BytesIO()
                thumbnail.save(preview, "JPEG", quality=85)
    except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ValueError("Image exceeds safe decoding limits.") from exc
    except (OSError, SyntaxError) as exc:
        raise ValueError("Image could not be decoded as a complete JPEG or PNG.") from exc
    encoded = output.getvalue()
    digest = hashlib.sha256(encoded).hexdigest()
    return {"id": digest, "name": name, "width": 1080, "height": 1350,
            "originalWidth": width, "originalHeight": height,
            "fitted": width * 5 != height * 4,
            "upscaled": width < 1080 or height < 1350,
            "bytes": len(encoded), "sha256": digest,
            "preview": base64.b64encode(preview.getvalue()).decode("ascii")}, encoded


class CarouselDrafts:
    def __init__(self, database: Path, stage_root: Path):
        self.database = Path(database)
        self.stage_root = Path(stage_root)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS carousel_drafts
                  (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS carousel_assets
                  (draft_id TEXT NOT NULL, id TEXT NOT NULL, metadata TEXT NOT NULL, image BLOB NOT NULL,
                   PRIMARY KEY(draft_id, id));
            """)

    @contextmanager
    def connection(self):
        with self._lock:
            db = sqlite3.connect(self.database, timeout=10)
            try:
                with db:
                    yield db
            finally:
                db.close()

    @staticmethod
    def _read(db, draft_id):
        row = db.execute("SELECT document FROM carousel_drafts WHERE id=?", (identifier(draft_id),)).fetchone()
        if not row:
            raise KeyError("Draft not found.")
        return json.loads(row[0])

    @staticmethod
    def _write(db, document):
        document["revision"] += 1
        document["updatedAt"] = datetime.now(timezone.utc).isoformat()
        db.execute("UPDATE carousel_drafts SET document=? WHERE id=?", (json.dumps(document), document["id"]))

    @staticmethod
    def _revision(document, revision):
        if type(revision) is not int or revision != document["revision"]:
            raise DraftConflict("This draft changed. Reopen it before saving; your edits were not overwritten.")

    def _public(self, db, document):
        result = dict(document)
        slides = []
        errors = []
        if not 2 <= len(document["slideIds"]) <= MAX_SLIDES:
            errors.append("Choose 2–10 slides for this carousel candidate.")
        for asset_id in document["slideIds"]:
            row = db.execute("SELECT metadata, image FROM carousel_assets WHERE draft_id=? AND id=?", (document["id"], asset_id)).fetchone()
            if not row or hashlib.sha256(row[1]).hexdigest() != asset_id:
                errors.append("A saved slide is missing or damaged. Reimport it before exporting.")
                continue
            slides.append(json.loads(row[0]))
        warnings_list = []
        if any(s["fitted"] for s in slides):
            warnings_list.append("Non-4:5 images have white margins so the entire image remains visible.")
        if any(s["upscaled"] for s in slides):
            warnings_list.append("Some source images are small; check sharpness in the preview.")
        if len(document["caption"]) > 200 or any(ord(c) > 126 for c in document["caption"]):
            warnings_list.append("Caption preserved in full. The current phone typing path cannot send this caption; use the transfer page's copy button and verify the pasted text in Instagram.")
        else:
            warnings_list.append("Phone typing, including first-space handling, still requires live validation.")
        result.update(slides=slides, validation={"errors": errors, "warnings": warnings_list},
                      status="ready_local" if not errors else "editing", savedInInstagram=False)
        return result

    def list(self):
        with self.connection() as db:
            records = [json.loads(row[0]) for row in db.execute("SELECT document FROM carousel_drafts")]
        return [{k: d[k] for k in ("id", "title", "updatedAt", "revision")} for d in sorted(records, key=lambda d: d["updatedAt"], reverse=True)]

    def get(self, draft_id):
        with self.connection() as db:
            return self._public(db, self._read(db, draft_id))

    def create(self, draft_id, title="Instagram carousel", from_generated=False, *, source_generation=None, manifest_sha256=None):
        draft_id = identifier(draft_id)
        title = checked_text(title, "Title", 120, required=True)
        if type(from_generated) is not bool:
            raise ValueError("from_generated must be a boolean.")
        fingerprint = json.dumps([title, from_generated])
        pinned = source_generation is not None or manifest_sha256 is not None
        if pinned:
            if (from_generated is not True or not isinstance(source_generation, str) or
                    not re.fullmatch(r'[0-9a-f]{32}', source_generation) or
                    not isinstance(manifest_sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', manifest_sha256)):
                raise ValueError('A generated batch needs its exact generation and manifest checksum.')
            fingerprint = json.dumps([title, from_generated, source_generation, manifest_sha256])
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT fingerprint FROM carousel_drafts WHERE id=?", (draft_id,)).fetchone()
            if old:
                if old[0] != fingerprint:
                    raise DraftConflict("This draft ID was already used for a different draft.")
                return self._public(db, self._read(db, draft_id))
            document = {"id": draft_id, "title": title, "caption": "", "slideIds": [], "revision": 1,
                        "platform": "instagram", "format": "ig_carousel", "deviceId": "C24C",
                        "updatedAt": datetime.now(timezone.utc).isoformat(), "sourceGeneration": None}
            if from_generated:
                folder = (self.stage_root / "C24C").resolve()
                manifest, source_hash = generated_manifest(self.stage_root, source_generation, manifest_sha256)
                document["caption"] = checked_text(manifest.get("caption"), "Caption", MAX_CAPTION)
                document["sourceGeneration"] = manifest.get("generation")
                document['sourceManifestSha256'] = source_hash
                for asset in manifest.get("assets", []):
                    url = asset.get("url", "")
                    if not url.startswith("/stage/C24C/"):
                        raise ValueError("Generated asset has an unexpected source.")
                    name = url[len("/stage/C24C/"):]
                    if not name or any(c in name for c in "/\\:%\x00") or name in (".", ".."):
                        raise ValueError("Invalid generated asset name.")
                    if Path(name).suffix.lower() not in (".jpg", ".jpeg", ".png"):
                        continue
                    path = (folder / name).resolve()
                    if not path.is_relative_to(folder) or path.stat().st_size > MAX_IMAGE_BYTES:
                        raise ValueError("Generated asset is outside the media folder or too large.")
                    raw = path.read_bytes()
                    if hashlib.sha256(raw).hexdigest() != asset.get("sha256"):
                        raise ValueError("Generated image checksum changed. Regenerate or import it explicitly.")
                    if pinned and (type(asset.get('bytes')) is not int or asset['bytes'] != len(raw)):
                        raise ValueError('Generated image size does not match its batch manifest.')
                    metadata, image = prepare_image(raw, name)
                    if metadata["id"] in document["slideIds"]:
                        if pinned: raise ValueError('Generated batch contains duplicate slides; review its source.')
                        continue
                    if len(document["slideIds"]) >= MAX_SLIDES:
                        raise ValueError("Generated content exceeds the 10-slide editing limit.")
                    self._insert_asset(db, draft_id, metadata, image)
                    document["slideIds"].append(metadata["id"])
                if not document["slideIds"]:
                    raise ValueError("The generated manifest contains no carousel images.")
                if pinned and len(document['slideIds']) < 2:
                    raise ValueError('A generated carousel batch needs at least two distinct slides.')
            db.execute("INSERT INTO carousel_drafts VALUES (?, ?, ?)", (draft_id, fingerprint, json.dumps(document)))
            return self._public(db, document)

    @staticmethod
    def _insert_asset(db, draft_id, metadata, image):
        db.execute("INSERT OR IGNORE INTO carousel_assets VALUES (?, ?, ?, ?)", (draft_id, metadata["id"], json.dumps(metadata), image))

    def import_image(self, draft_id, revision, name, content):
        if not isinstance(content, str) or len(content) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
            raise ValueError("Image payload exceeds 8 MiB.")
        try:
            raw = base64.b64decode(content, validate=True)
        except ValueError as exc:
            raise ValueError("Invalid image encoding.") from exc
        metadata, image = prepare_image(raw, name)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            document = self._read(db, draft_id)
            self._revision(document, revision)
            if metadata["id"] in document["slideIds"]:
                raise ValueError("That image is already in this draft.")
            if len(document["slideIds"]) >= MAX_SLIDES:
                raise ValueError("This candidate supports at most 10 slides.")
            self._insert_asset(db, document["id"], metadata, image)
            document["slideIds"].append(metadata["id"])
            self._write(db, document)
            return self._public(db, document)

    def save(self, draft_id, revision, title, caption, slide_ids):
        title = checked_text(title, "Title", 120, required=True)
        caption = checked_text(caption, "Caption", MAX_CAPTION)
        if (not isinstance(slide_ids, list) or len(slide_ids) > MAX_SLIDES or
                any(not isinstance(s, str) for s in slide_ids) or len(set(slide_ids)) != len(slide_ids)):
            raise ValueError("Slide order must contain unique image IDs, at most 10.")
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            document = self._read(db, draft_id)
            self._revision(document, revision)
            for asset_id in slide_ids:
                if not db.execute("SELECT 1 FROM carousel_assets WHERE draft_id=? AND id=?", (document["id"], asset_id)).fetchone():
                    raise ValueError("A selected image does not belong to this draft.")
            document.update(title=title, caption=caption, slideIds=slide_ids)
            self._write(db, document)
            return self._public(db, document)

    def export(self, draft_id, revision):
        with self.connection() as db:
            document = self._read(db, draft_id)
            self._revision(document, revision)
            public = self._public(db, document)
            if public["validation"]["errors"]:
                raise ValueError(" ".join(public["validation"]["errors"]))
            files = {"caption.txt": document["caption"].encode("utf-8")}
            assets = []
            images = []
            for number, slide in enumerate(public["slides"], 1):
                name = f"{number:02}.jpg"
                raw = db.execute("SELECT image FROM carousel_assets WHERE draft_id=? AND id=?", (document["id"], slide["id"])).fetchone()[0]
                files[name] = raw
                assets.append({"file": name, "sha256": slide["sha256"], "bytes": len(raw)})
                images.append(f'<figure><img src="{name}" alt="Slide {number}"><figcaption>{number}. {html.escape(slide["name"])}</figcaption></figure>')
            manifest = {**document, "assets": assets, "status": "local_export", "savedInInstagram": False, "published": False,
                        "warnings": public["validation"]["warnings"]}
            files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            files["README.txt"] = b"Local Instagram carousel draft. Not uploaded, saved in Instagram, or published.\nReview slides in numeric order and caption.txt. Phone import and caption transfer require validation.\nImages are fitted within 1080x1350 with white margins; original files are unchanged.\n"
            files["review.html"] = ('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
                '<title>Carousel draft review</title><style>body{font:16px system-ui;max-width:1100px;margin:32px auto;padding:16px}section{display:flex;flex-wrap:wrap}figure{width:240px;margin:12px}img{width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
                f'<h1>{html.escape(document["title"])}</h1><p>Local draft · not saved in Instagram or published.</p><pre>{html.escape(document["caption"])}</pre><section>{"".join(images)}</section>').encode("utf-8")
            files["SHA256SUMS.txt"] = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in files.items()).encode()
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, data in files.items():
                    # The same saved revision must have the same package hash,
                    # including when reviewed again on another day.
                    entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    entry.external_attr = 0o600 << 16
                    archive.writestr(entry, data, compress_type=zipfile.ZIP_DEFLATED)
            return output.getvalue()
