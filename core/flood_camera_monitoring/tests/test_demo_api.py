from unittest.mock import ANY, Mock, patch

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from core.flood_camera_monitoring.infra.demo_stream_client import (
    DemoStreamUnavailable,
)
from core.flood_camera_monitoring.infra.models import FloodDetectionRecord
from core.users.infra.models import User


def stream_payload(*, state="auto", session_id="session-1", with_segment=True):
    payload = {
        "ok": True,
        "status": "ready",
        "session_id": session_id,
        "demo_state": state,
        "available_states": ["auto", "normal", "flooded"],
        "scenario": {"scenario_id": "test", "phases": []},
        "current_phase": "flood phase",
        "hls_url": "http://localhost:8088/hls/playlist.m3u8",
        "segment": None,
        "source": {
            "type": "uploader",
            "mode": state,
            "status": "ready",
            "attachment_key": "private-key",
            "version": "private-version",
        },
        "sources": {state: {"attachment_key": "private-key"}},
    }
    if with_segment:
        payload["segment"] = {
            "sequence": 2,
            "phase": "flood phase",
            "expected_state": "flooded",
            "internal_url": "http://demo-stream:8088/hls/seg_000000002.ts",
        }
    return payload


@override_settings(
    DEMO_ENABLED=True,
    DEMO_STREAM_INTERNAL_URL="http://demo-stream:8089",
    DEMO_CONTROL_TOKEN="test-token",
)
class DemoApiTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create(
            name="Admin",
            email="admin@example.com",
            type=User.UserType.ADMIN,
        )
        self.standard = User.objects.create(
            name="Standard",
            email="standard@example.com",
            type=User.UserType.STANDARD,
        )

    @patch("core.flood_camera_monitoring.presentation.demo_control_views._client")
    def test_status_is_public_and_hides_internal_segment_url(self, client_factory):
        client_factory.return_value.get_state.return_value = stream_payload()

        response = self.client.get("/api/flood_monitoring/demo")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["enabled"])
        self.assertNotIn("internal_url", response.data["segment"])
        self.assertNotIn("sources", response.data)
        self.assertEqual(
            response.data["source"],
            {"type": "uploader", "mode": "auto", "status": "ready"},
        )

    @override_settings(DEMO_ENABLED=False)
    @patch("core.flood_camera_monitoring.presentation.demo_control_views._client")
    def test_disabled_demo_status_does_not_call_sidecar(self, client_factory):
        response = self.client.get("/api/flood_monitoring/demo")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"enabled": False, "status": "disabled"})
        client_factory.assert_not_called()

    def test_anonymous_user_cannot_change_state(self):
        response = self.client.post(
            "/api/flood_monitoring/demo/state", {"state": "normal"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_standard_user_cannot_change_state(self):
        self.client.force_authenticate(self.standard)
        response = self.client.post(
            "/api/flood_monitoring/demo/state", {"state": "normal"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("core.flood_camera_monitoring.presentation.demo_control_views._client")
    def test_admin_changes_state_and_receives_new_session(self, client_factory):
        sidecar = client_factory.return_value
        sidecar.get_state.return_value = stream_payload(session_id="old-session")
        sidecar.set_state.return_value = stream_payload(
            state="normal", session_id="new-session"
        )
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            "/api/flood_monitoring/demo/state", {"state": "normal"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["session_id"], "new-session")
        self.assertEqual(response.data["demo_state"], "normal")
        sidecar.set_state.assert_called_once_with("normal")

    @override_settings(DEMO_ENABLED=False)
    @patch("core.flood_camera_monitoring.presentation.demo_control_views._client")
    def test_disabled_demo_rejects_admin_state_change(self, client_factory):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            "/api/flood_monitoring/demo/state", {"state": "normal"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["detail"], "Demo stream is disabled")
        client_factory.assert_not_called()

    @patch("core.flood_camera_monitoring.presentation.demo_control_views.logger")
    @patch("core.flood_camera_monitoring.presentation.demo_control_views._client")
    def test_admin_state_change_is_audited(self, client_factory, logger):
        sidecar = client_factory.return_value
        sidecar.get_state.return_value = stream_payload(session_id="old-session")
        sidecar.set_state.return_value = stream_payload(
            state="normal", session_id="new-session"
        )
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            "/api/flood_monitoring/demo/state", {"state": "normal"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        logger.info.assert_called_once()

    def test_invalid_state_is_rejected_before_sidecar_call(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            "/api/flood_monitoring/demo/state", {"state": "paused"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("core.flood_camera_monitoring.presentation.demo_control_views._client")
    def test_admin_cannot_select_a_phase_missing_from_scenario(self, client_factory):
        payload = stream_payload()
        payload["available_states"] = ["auto", "flooded"]
        client_factory.return_value.get_state.return_value = payload
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            "/api/flood_monitoring/demo/state", {"state": "normal"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        client_factory.return_value.set_state.assert_not_called()

    @patch("core.flood_camera_monitoring.presentation.demo_control_views._client")
    def test_sidecar_unavailable_returns_503(self, client_factory):
        client_factory.return_value.get_state.side_effect = DemoStreamUnavailable("down")

        response = self.client.get("/api/flood_monitoring/demo")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    @patch("core.flood_camera_monitoring.presentation.demo_views._store_cache")
    @patch("core.flood_camera_monitoring.presentation.demo_views._cached", return_value=None)
    @patch("core.flood_camera_monitoring.presentation.demo_views.aggregate_predictions")
    @patch("core.flood_camera_monitoring.presentation.demo_views.capture_frames")
    @patch("core.flood_camera_monitoring.presentation.demo_views.get_default_classifier")
    @patch("core.flood_camera_monitoring.presentation.demo_views._client")
    def test_prediction_is_public_compares_label_and_does_not_persist(
        self,
        client_factory,
        classifier_factory,
        capture,
        aggregate,
        cached,
        store_cache,
    ):
        client_factory.return_value.get_state.return_value = stream_payload()
        classifier_factory.return_value = Mock(_fallback=False)
        capture.return_value = [b"one", b"two", b"three"]
        aggregate.return_value = (
            {
                "strong": True,
                "medium_flag": False,
                "decision_flooded": 85.0,
                "mean_normal": 10.0,
                "mean_medium": 5.0,
                "mean_flooded": 85.0,
                "frames_count": 3,
            },
            [],
        )

        response = self.client.get("/api/flood_monitoring/demo/predict")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["validation"]["match"])
        self.assertEqual(response.data["prediction"]["state"], "flooded")
        self.assertEqual(FloodDetectionRecord.objects.count(), 0)
        store_cache.assert_called_once()

    @patch("core.flood_camera_monitoring.presentation.demo_views._cached", return_value=None)
    @patch("core.flood_camera_monitoring.presentation.demo_views.get_default_classifier")
    @patch("core.flood_camera_monitoring.presentation.demo_views._client")
    def test_fallback_model_is_not_accepted(
        self, client_factory, classifier_factory, cached
    ):
        client_factory.return_value.get_state.return_value = stream_payload()
        classifier_factory.return_value = Mock(_fallback=True)

        response = self.client.get("/api/flood_monitoring/demo/predict")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertTrue(response.data["model"]["fallback"])

    @patch("core.flood_camera_monitoring.presentation.demo_views._client")
    def test_predict_waits_for_a_complete_segment(self, client_factory):
        client_factory.return_value.get_state.return_value = stream_payload(
            with_segment=False
        )

        response = self.client.get("/api/flood_monitoring/demo/predict")

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    @patch("core.flood_camera_monitoring.presentation.demo_views._store_cache")
    @patch("core.flood_camera_monitoring.presentation.demo_views._cached", return_value=None)
    @patch("core.flood_camera_monitoring.presentation.demo_views.aggregate_predictions")
    @patch("core.flood_camera_monitoring.presentation.demo_views.capture_frames")
    @patch("core.flood_camera_monitoring.presentation.demo_views.get_default_classifier")
    @patch("core.flood_camera_monitoring.presentation.demo_views._client")
    def test_prediction_analyzes_the_exact_requested_segment(
        self,
        client_factory,
        classifier_factory,
        capture,
        aggregate,
        _cached,
        _store_cache,
    ):
        client_factory.return_value.get_state.return_value = stream_payload()
        classifier_factory.return_value = Mock(_fallback=False)
        capture.return_value = [b"one"]
        aggregate.return_value = (
            {
                "strong": False,
                "medium_flag": False,
                "decision_flooded": 5.0,
                "mean_normal": 90.0,
                "mean_medium": 5.0,
                "mean_flooded": 5.0,
                "frames_count": 1,
            },
            [],
        )

        response = self.client.get("/api/flood_monitoring/demo/predict?sequence=1")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["segment"]["sequence"], 1)
        capture.assert_called_once_with(
            "http://demo-stream:8088/hls/seg_000000001.ts",
            ANY,
        )

    @patch("core.flood_camera_monitoring.presentation.demo_views._client")
    def test_prediction_rejects_a_future_segment(self, client_factory):
        client_factory.return_value.get_state.return_value = stream_payload()

        response = self.client.get("/api/flood_monitoring/demo/predict?sequence=3")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
