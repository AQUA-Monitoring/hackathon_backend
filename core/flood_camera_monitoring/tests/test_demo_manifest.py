import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from core.flood_camera_monitoring.demo.manifest import (
    DemoManifestError,
    load_scenario,
)


class DemoManifestTests(TestCase):
    def _write_scenario(self, root: Path, **updates) -> Path:
        (root / "normal.mp4").touch()
        (root / "flooded.mp4").touch()
        payload = {
            "scenario_id": "test-scenario",
            "segment_seconds": 2,
            "phases": [
                {
                    "name": "normal phase",
                    "file": "normal.mp4",
                    "label": "normal",
                    "duration_seconds": 4,
                },
                {
                    "name": "flood phase",
                    "file": "flooded.mp4",
                    "label": "flooded",
                    "duration_seconds": 4,
                },
            ],
        }
        payload.update(updates)
        path = root / "scenario.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_maps_auto_and_forced_states_to_expected_phases(self):
        with TemporaryDirectory() as directory:
            scenario = load_scenario(self._write_scenario(Path(directory)))

            self.assertEqual(scenario.phase_for_sequence("auto", 0).label, "normal")
            self.assertEqual(scenario.phase_for_sequence("auto", 1).label, "normal")
            self.assertEqual(scenario.phase_for_sequence("auto", 2).label, "flooded")
            self.assertEqual(scenario.phase_for_sequence("auto", 4).label, "normal")
            self.assertEqual(
                scenario.phase_for_sequence("flooded", 999).label, "flooded"
            )

    def test_rejects_duration_that_cannot_align_with_hls_segments(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._write_scenario(root)
            payload = json.loads(path.read_text())
            payload["phases"][0]["duration_seconds"] = 3
            path.write_text(json.dumps(payload))

            with self.assertRaisesRegex(DemoManifestError, "divisible"):
                load_scenario(path)

    def test_rejects_missing_video_and_path_traversal(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._write_scenario(root)
            payload = json.loads(path.read_text())
            payload["phases"][0]["file"] = "../outside.mp4"
            path.write_text(json.dumps(payload))

            with self.assertRaises(DemoManifestError):
                load_scenario(path)

    def test_supports_a_temporary_flooded_only_scenario(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._write_scenario(root)
            payload = json.loads(path.read_text())
            payload["phases"] = payload["phases"][1:]
            path.write_text(json.dumps(payload))

            scenario = load_scenario(path)

            self.assertEqual(scenario.available_states, ("auto", "flooded"))
            self.assertEqual(scenario.phase_for_sequence("auto", 0).label, "flooded")

    def test_resolves_an_uploader_video_from_an_environment_key(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._write_scenario(root)
            payload = json.loads(path.read_text())
            payload["phases"] = payload["phases"][1:]
            payload["phases"][0].pop("file")
            payload["phases"][0]["video_attachment_key_env"] = (
                "DEMO_VIDEO_ATTACHMENT_KEY"
            )
            path.write_text(json.dumps(payload))
            resolved_video = root / "materialized.mp4"
            resolved_video.touch()
            resolver = Mock(return_value=resolved_video)

            with patch.dict(
                "os.environ",
                {"DEMO_VIDEO_ATTACHMENT_KEY": "a9417b87-8b8b-4278-a154-f3f4333e5797"},
            ):
                scenario = load_scenario(path, video_resolver=resolver)

            resolver.assert_called_once_with(
                "a9417b87-8b8b-4278-a154-f3f4333e5797"
            )
            self.assertEqual(scenario.phases[0].file_path, resolved_video)

    def test_requires_the_configured_uploader_environment_key(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._write_scenario(root)
            payload = json.loads(path.read_text())
            payload["phases"] = payload["phases"][1:]
            payload["phases"][0].pop("file")
            payload["phases"][0]["video_attachment_key_env"] = (
                "DEMO_VIDEO_ATTACHMENT_KEY"
            )
            path.write_text(json.dumps(payload))

            with (
                patch.dict("os.environ", {}, clear=True),
                self.assertRaisesRegex(DemoManifestError, "is not configured"),
            ):
                load_scenario(path, video_resolver=Mock())

    def test_operational_manifest_rejects_local_files(self):
        with TemporaryDirectory() as directory:
            path = self._write_scenario(Path(directory))
            with self.assertRaisesRegex(DemoManifestError, "somente vídeos do uploader"):
                load_scenario(path, require_uploader=True)
