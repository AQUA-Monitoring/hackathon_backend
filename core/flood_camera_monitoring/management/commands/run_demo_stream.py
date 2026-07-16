from __future__ import annotations

import os
import threading

from django.core.management.base import BaseCommand, CommandError

from core.flood_camera_monitoring.demo.controller import (
    DemoStreamController,
    DemoStreamError,
)
from core.flood_camera_monitoring.demo.manifest import DemoManifestError, load_scenario
from core.flood_camera_monitoring.demo.server import DemoServers


class Command(BaseCommand):
    help = "Run the deterministic HLS demo stream and its internal control API"
    # The demo image intentionally excludes OpenCV and Torch. It only needs the
    # stream controller, so avoid Django's global URL checks, which load the
    # Flood Monitoring inference views.
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument(
            "--scenario",
            default=os.getenv("DEMO_SCENARIO_PATH", "/demo-assets/scenario.json"),
        )
        parser.add_argument(
            "--work-dir", default=os.getenv("DEMO_WORK_DIR", "/tmp/aqua-demo-stream")
        )
        parser.add_argument("--media-port", type=int, default=8088)
        parser.add_argument("--control-port", type=int, default=8089)

    def handle(self, *args, **options):
        token = os.getenv("DEMO_CONTROL_TOKEN", "")
        if not token:
            raise CommandError("DEMO_CONTROL_TOKEN must be configured")

        public_url = os.getenv(
            "DEMO_STREAM_PUBLIC_URL", "http://localhost:8088/hls/playlist.m3u8"
        )
        internal_url = os.getenv(
            "DEMO_STREAM_MEDIA_INTERNAL_BASE_URL", "http://demo-stream:8088"
        )
        try:
            scenario = load_scenario(options["scenario"])
            controller = DemoStreamController(
                scenario,
                options["work_dir"],
                public_hls_url=public_url,
                internal_base_url=internal_url,
            )
            controller.initialize()
        except (DemoManifestError, DemoStreamError) as exc:
            raise CommandError(str(exc)) from exc

        servers = DemoServers(
            controller,
            media_host="0.0.0.0",
            media_port=options["media_port"],
            control_host="0.0.0.0",
            control_port=options["control_port"],
            control_token=token,
        )
        servers.start()
        self.stdout.write(
            self.style.SUCCESS(
                f"Demo stream ready: media={options['media_port']} control={options['control_port']}"
            )
        )
        stop = threading.Event()
        try:
            stop.wait()
        except KeyboardInterrupt:
            pass
        finally:
            servers.close()
            controller.close()
