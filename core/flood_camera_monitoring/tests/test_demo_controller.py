import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from core.flood_camera_monitoring.demo.controller import DemoStreamController
from core.flood_camera_monitoring.demo.manifest import load_scenario


class DemoControllerTests(TestCase):
    def test_every_state_change_creates_a_new_session(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "normal.mp4").touch()
            (root / "flooded.mp4").touch()
            manifest = root / "scenario.json"
            manifest.write_text(
                json.dumps(
                    {
                        "scenario_id": "controller-test",
                        "segment_seconds": 2,
                        "phases": [
                            {
                                "name": "normal",
                                "file": "normal.mp4",
                                "label": "normal",
                                "duration_seconds": 2,
                            },
                            {
                                "name": "flooded",
                                "file": "flooded.mp4",
                                "label": "flooded",
                                "duration_seconds": 2,
                            },
                        ],
                    }
                )
            )
            controller = DemoStreamController(
                load_scenario(manifest),
                root / "work",
                public_hls_url="http://public/hls/playlist.m3u8",
                internal_base_url="http://internal",
            )
            controller.hls_dir.mkdir(parents=True)

            with (
                patch.object(controller, "_stop_process"),
                patch.object(controller, "_build_source", return_value=root / "source"),
                patch.object(controller, "_clear_hls"),
                patch.object(controller, "_start_hls"),
            ):
                first = controller.set_state("normal")
                second = controller.set_state("normal")

            self.assertNotEqual(first["session_id"], second["session_id"])
            self.assertEqual(second["demo_state"], "normal")
