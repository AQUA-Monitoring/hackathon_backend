import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

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
