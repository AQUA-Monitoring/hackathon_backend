import shutil
import tempfile
from pathlib import Path

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from core.flood_camera_monitoring.demo.assets import UploadedVideoResolver
from core.uploader.models import Video


class UploadedVideoResolverTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.work_dir = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)
        shutil.rmtree(self.work_dir, ignore_errors=True)

    def test_materializes_a_video_from_django_storage(self):
        video = Video.objects.create(
            file=SimpleUploadedFile("demo.mp4", b"demo-video"),
            description="Demo",
        )

        resolved = UploadedVideoResolver(self.work_dir)(str(video.attachment_key))

        self.assertTrue(resolved.is_file())
        self.assertEqual(resolved.read_bytes(), b"demo-video")
        self.assertEqual(resolved.parent, Path(self.work_dir) / "uploaded-videos")
