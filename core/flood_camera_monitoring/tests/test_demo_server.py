from unittest import TestCase
from unittest.mock import Mock

import requests

from core.flood_camera_monitoring.demo.server import DemoServers


class DemoServerTests(TestCase):
    def test_control_state_requires_the_internal_token(self):
        controller = Mock()
        controller.snapshot.return_value = {
            "ok": True,
            "status": "ready",
            "demo_state": "auto",
        }
        servers = DemoServers(
            controller,
            media_host="127.0.0.1",
            media_port=0,
            control_host="127.0.0.1",
            control_port=0,
            control_token="secret",
        )
        servers.start()
        port = servers.control_server.server_address[1]
        try:
            unauthorized = requests.get(f"http://127.0.0.1:{port}/state", timeout=2)
            authorized = requests.get(
                f"http://127.0.0.1:{port}/state",
                headers={"X-Demo-Control-Token": "secret"},
                timeout=2,
            )
        finally:
            servers.close()

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200)
        self.assertEqual(authorized.json()["demo_state"], "auto")
