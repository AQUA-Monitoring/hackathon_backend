import shutil
import tempfile
from pathlib import Path

from django.http import Http404
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse

from config.media import serve_media


class MediaServingTests(SimpleTestCase):
    def setUp(self):
        self.work_dir = Path(tempfile.mkdtemp())
        self.media_root = self.work_dir / "media"
        self.media_root.mkdir()
        self.settings_override = override_settings(
            DEBUG=False,
            MEDIA_ROOT=self.media_root,
        )
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.work_dir, ignore_errors=True)

    def test_serves_existing_upload_with_debug_disabled(self):
        image = self.media_root / "images" / "example.png"
        image.parent.mkdir()
        image.write_bytes(b"png-content")

        response = self.client.get(
            reverse("media-file", kwargs={"path": "images/example.png"})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"png-content")
        self.assertEqual(response["Content-Type"], "image/png")

    def test_returns_404_for_missing_upload(self):
        response = self.client.get(
            reverse("media-file", kwargs={"path": "images/missing.png"})
        )

        self.assertEqual(response.status_code, 404)

    def test_rejects_path_traversal_and_symlink_escape(self):
        outside = self.work_dir / "secret.txt"
        outside.write_text("secret", encoding="utf-8")
        link = self.media_root / "outside.txt"
        link.symlink_to(outside)
        request = RequestFactory().get("/media/outside.txt")

        with self.assertRaises(Http404):
            serve_media(request, "../secret.txt")
        with self.assertRaises(Http404):
            serve_media(request, "outside.txt")
