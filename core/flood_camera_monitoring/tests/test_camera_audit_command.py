import json
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from core.flood_camera_monitoring.infra.models import Camera


class CameraRegistrationAuditCommandTests(TestCase):
    def test_reports_legacy_gaps_without_stream_urls_or_mutation(self):
        camera = Camera.objects.create(
            description="Câmera legada",
            video_hls="https://private.example/stream.m3u8?token=secret",
        )
        output = StringIO()

        call_command("audit_camera_registration_gaps", stdout=output)

        report = json.loads(output.getvalue())
        item = next(
            entry
            for entry in report["pending"]
            if entry["camera_id"] == str(camera.id)
        )
        self.assertEqual(item["missing"], ["address", "created_by"])
        self.assertFalse(item["legacy_location_available"])
        self.assertNotIn("video_hls", output.getvalue())
        self.assertNotIn("private.example", output.getvalue())
        camera.refresh_from_db()
        self.assertIsNone(camera.address_id)
        self.assertIsNone(camera.created_by_id)
