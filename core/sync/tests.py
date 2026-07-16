import shutil
import tempfile
from unittest.mock import patch

from django.test import TestCase, override_settings

from core.sync.syncers import sync_images
from core.uploader.models import Image


class SyncImagesTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    @patch("core.sync.syncers.fetch_file", return_value=b"image-content")
    def test_imports_image_and_uses_attachment_key_as_identity(self, fetch_file):
        data = [
            {
                "attachment_key": "73f1a3d0-0f15-4c4d-ae2f-703e665808f7",
                "url": "/media/images/remote-image.png",
                "description": "Imagem remota",
            }
        ]

        created, updated = sync_images(data, "token")

        self.assertEqual((created, updated), (1, 0))
        image = Image.objects.get()
        self.assertEqual(str(image.attachment_key), data[0]["attachment_key"])
        self.assertEqual(image.description, "Imagem remota")
        self.assertTrue(image.file.name.endswith(".png"))
        fetch_file.assert_called_once_with(data[0]["url"], "token")

        created, updated = sync_images(data, "token")

        self.assertEqual((created, updated), (0, 0))
        fetch_file.assert_called_once()
