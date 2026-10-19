"""Offline local-draft acceptance: persistence, ordering, image integrity and no input."""
import base64
import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid
import zipfile
from email.message import Message

from PIL import Image

from farm_drafts import CarouselDrafts, DraftConflict, MAX_IMAGE_BYTES, prepare_image
import imouse_farm_server as server


def picture(color, size=(100, 125), fmt="PNG"):
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, fmt)
    return output.getvalue()


class CarouselDraftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="imouse-drafts-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = CarouselDrafts(self.root / "drafts.db", self.root / "stage")
        self.draft = self.store.create(str(uuid.uuid4()))

    def add(self, color="red", raw=None, name="image.png"):
        self.draft = self.store.import_image(self.draft["id"], self.draft["revision"], name, base64.b64encode(raw or picture(color)).decode())
        return self.draft

    def save(self, **changes):
        values = dict(title=self.draft["title"], caption=self.draft["caption"], slide_ids=self.draft["slideIds"])
        values.update(changes)
        self.draft = self.store.save(self.draft["id"], self.draft["revision"], **values)
        return self.draft

    def test_reopen_persists_order_caption_and_images_without_originals(self):
        self.add("red"); self.add("blue")
        self.save(title="My launch", caption="Line one\nFull Unicode: café 🎉", slide_ids=self.draft["slideIds"][::-1])
        reopened = CarouselDrafts(self.root / "drafts.db", self.root / "different-stage")
        self.assertEqual(self.draft, reopened.get(self.draft["id"]))
        self.assertEqual("ready_local", self.draft["status"])
        self.assertFalse(self.draft["savedInInstagram"])
        self.assertIn("current phone typing path", " ".join(self.draft["validation"]["warnings"]))

    def test_empty_or_one_slide_is_saved_but_export_refused(self):
        for count in range(2):
            with self.assertRaisesRegex(ValueError, "2–10"):
                self.store.export(self.draft["id"], self.draft["revision"])
            if count == 0: self.add()

    def test_existing_create_id_recovers_saved_result_without_regeneration(self):
        self.add()
        self.assertEqual(self.draft, self.store.create(self.draft["id"]))
        with self.assertRaises(DraftConflict):
            self.store.create(self.draft["id"], "Different title")

    def test_stale_revision_cannot_overwrite_a_newer_save_or_export(self):
        stale = self.draft["revision"]
        self.save(title="New title")
        with self.assertRaises(DraftConflict):
            self.store.save(self.draft["id"], stale, "Old title", "", [])
        with self.assertRaises(DraftConflict):
            self.store.export(self.draft["id"], stale)
        self.assertEqual("New title", self.store.get(self.draft["id"])["title"])

    def test_two_store_instances_cannot_lose_a_simultaneous_edit(self):
        other = CarouselDrafts(self.root / "drafts.db", self.root / "stage")
        gate = threading.Barrier(2)
        results = []
        def save(store, title):
            gate.wait()
            try:
                store.save(self.draft["id"], 1, title, "", [])
                results.append("saved")
            except DraftConflict: results.append("conflict")
        workers = [threading.Thread(target=save, args=(store, name)) for store, name in ((self.store, "A"), (other, "B"))]
        for worker in workers: worker.start()
        for worker in workers: worker.join(3)
        self.assertCountEqual(["saved", "conflict"], results)

    def test_images_fit_without_crop_and_export_order_is_selected_order(self):
        self.add(raw=picture("red", (400, 100)), name='<img src="x">.png')
        self.add("blue")
        self.save(caption='<script>alert("x")</script>\nPreserved space', slide_ids=self.draft["slideIds"][::-1])
        with zipfile.ZipFile(io.BytesIO(self.store.export(self.draft["id"], self.draft["revision"]))) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertFalse(manifest["published"])
            self.assertFalse(manifest["savedInInstagram"])
            self.assertEqual(self.draft["caption"], archive.read("caption.txt").decode())
            for number, slide in enumerate(self.draft["slides"], 1):
                raw = archive.read(f"{number:02}.jpg")
                self.assertEqual(slide["sha256"], hashlib.sha256(raw).hexdigest())
                with Image.open(io.BytesIO(raw)) as image:
                    self.assertEqual((1080, 1350), image.size)
                    if number == 2:
                        self.assertGreater(min(image.getpixel((0, 0))), 240)
                        self.assertGreater(image.getpixel((540, 675))[0], 240)
            review = archive.read("review.html").decode()
            self.assertNotIn('<script>', review)
            self.assertNotIn('<img src="x">', review)
            for line in archive.read("SHA256SUMS.txt").decode().splitlines():
                digest, name = line.split("  ")
                self.assertEqual(digest, hashlib.sha256(archive.read(name)).hexdigest())

    def test_invalid_image_rejects_without_changing_draft(self):
        before = self.draft
        for raw in (b"bad image", picture("red")[:20], picture("red", fmt="GIF"), b"x" * (MAX_IMAGE_BYTES + 1)):
            with self.subTest(length=len(raw)), self.assertRaises(ValueError): self.add(raw=raw)
        self.assertEqual(before, self.store.get(before["id"]))

    def test_invalid_payload_types_and_caption_are_not_silently_truncated(self):
        for text in ("x" * 2201, "bad\x00text", 123, ["caption"]):
            with self.assertRaises((ValueError, UnicodeError)): self.save(caption=text)
        self.save(caption="x" * 2200)
        self.assertEqual(2200, len(self.draft["caption"]))
        for content in (None, "not base64", 123):
            with self.assertRaises(ValueError): self.store.import_image(self.draft["id"], self.draft["revision"], "test.png", content)

    def test_duplicate_and_foreign_images_are_refused(self):
        self.add()
        with self.assertRaisesRegex(ValueError, "already"): self.add()
        other = self.store.create(str(uuid.uuid4()))
        with self.assertRaisesRegex(ValueError, "belong"):
            self.store.save(other["id"], 1, "other", "", self.draft["slideIds"])
        with self.assertRaisesRegex(ValueError, "unique"):
            self.save(slide_ids=self.draft["slideIds"] * 2)

    def test_removed_images_remain_in_old_exports(self):
        self.add("red"); self.add("blue"); self.add("green")
        exported = self.store.export(self.draft["id"], self.draft["revision"])
        self.save(slide_ids=self.draft["slideIds"][1:])
        with zipfile.ZipFile(io.BytesIO(exported)) as archive:
            self.assertEqual(3, len(json.loads(archive.read("manifest.json"))["assets"]))
        self.assertEqual(2, len(self.store.get(self.draft["id"])["slides"]))

    def test_max_slides_and_oversized_pixels_are_rejected(self):
        for index in range(10): self.add(color=(index * 20, 0, 0))
        with self.assertRaisesRegex(ValueError, "10 slides"): self.add("green")
        with patch("farm_drafts.MAX_PIXELS", 20):
            with self.assertRaisesRegex(ValueError, "megapixel"): prepare_image(picture("red"), "test.png")

    def test_corrupt_saved_blob_blocks_export(self):
        self.add("red"); self.add("blue")
        with self.store.connection() as db:
            db.execute("UPDATE carousel_assets SET image=? WHERE draft_id=? AND id=?", (b"broken", self.draft["id"], self.draft["slideIds"][0]))
        with self.assertRaisesRegex(ValueError, "damaged"):
            self.store.export(self.draft["id"], self.draft["revision"])

    def generated(self, *, bad_hash=False, bad_path=False):
        folder = self.root / "stage/C24C"
        folder.mkdir(parents=True, exist_ok=True)
        raw = picture("green")
        (folder / "slide.png").write_bytes(raw)
        manifest = {"caption": "Generated caption", "generation": "generation-1", "assets": [
            {"url": "/stage/C24C/../secret.png" if bad_path else "/stage/C24C/slide.png", "sha256": "bad" if bad_hash else hashlib.sha256(raw).hexdigest()}]}
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return folder

    def test_generated_content_is_snapshotted_and_survives_source_changes(self):
        folder = self.generated()
        draft = self.store.create(str(uuid.uuid4()), from_generated=True)
        (folder / "slide.png").write_bytes(b"now broken")
        (folder / "manifest.json").write_text("{}", encoding="utf-8")
        self.assertEqual(draft, self.store.get(draft["id"]))
        self.assertEqual("generation-1", draft["sourceGeneration"])

    def test_bad_generated_source_rolls_back_whole_draft(self):
        for options in ({"bad_hash": True}, {"bad_path": True}):
            self.generated(**options)
            new_id = str(uuid.uuid4())
            with self.assertRaises(ValueError): self.store.create(new_id, from_generated=True)
            with self.assertRaises(KeyError): self.store.get(new_id)
        self.assertEqual(1, len(self.store.list()))

    def test_exif_orientation_is_applied_and_original_is_not_changed(self):
        image = Image.new("RGB", (400, 100), "red")
        exif = image.getexif(); exif[274] = 6
        buffer = io.BytesIO(); image.save(buffer, "JPEG", exif=exif)
        raw = buffer.getvalue()
        metadata, converted = prepare_image(raw, "rotated.jpg")
        self.assertEqual((100, 400), (metadata["originalWidth"], metadata["originalHeight"]))
        self.assertEqual(raw, buffer.getvalue())
        with Image.open(io.BytesIO(converted)) as output: self.assertEqual({}, output.getexif())


class CarouselRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="farm-draft-routes-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.runtime = server.FarmBackendRuntime(root / "farm.db", root / "stage")
        self.addCleanup(patch.stopall)
        patch.object(server, "RUNTIME", self.runtime).start()

    def request(self, path, data=None):
        handler = object.__new__(server.FarmRequestHandler)
        handler.path = path
        handler.headers = Message()
        raw = json.dumps(data).encode() if data is not None else b""
        handler.headers["Content-Length"] = str(len(raw))
        handler.rfile = io.BytesIO(raw)
        from unittest.mock import Mock
        handler._send_bytes = Mock()
        (handler.do_POST if data is not None else handler.do_GET)()
        code, _, response = handler._send_bytes.call_args.args
        return code, json.loads(response)

    def test_draft_routes_are_local_even_in_live_mode(self):
        self.runtime.execution_mode = "live"
        with patch.object(self.runtime, "get_kernel", side_effect=AssertionError("No kernel needed")):
            draft_id = str(uuid.uuid4())
            self.assertEqual(200, self.request("/api/farm/drafts", {"id": draft_id})[0])
            revision = 1
            for color in ("red", "blue"):
                code, result = self.request(f"/api/farm/drafts/{draft_id}/import", {"revision": revision, "name": "slide.png", "content": base64.b64encode(picture(color)).decode()})
                self.assertEqual(200, code, result); revision = result["draft"]["revision"]
            code, result = self.request(f"/api/farm/drafts/{draft_id}/export", {"revision": revision})
            self.assertEqual(200, code, result)
            self.assertFalse(result["published"])
            self.assertFalse(result["savedInInstagram"])
            self.assertEqual(1, len(self.request("/api/farm/drafts")[1]["drafts"]))
        self.assertEqual([], self.runtime.mock_kernel.commands_dispatched)

    def test_conflict_status_and_unknown_id(self):
        draft_id = str(uuid.uuid4())
        self.request("/api/farm/drafts", {"id": draft_id})
        self.assertEqual(409, self.request(f"/api/farm/drafts/{draft_id}/save", {"revision": 0, "title": "name", "caption": "", "slide_ids": []})[0])
        self.assertEqual(404, self.request("/api/farm/drafts/../../settings.json")[0])
        self.assertEqual(400, self.request("/api/farm/drafts", {"id": draft_id, "from_generated": "true"})[0])


if __name__ == "__main__": unittest.main()
