from unittest.mock import Mock, patch

import requests
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve

from core.flood_camera_monitoring.presentation.proxy import proxy_flood_camera


@override_settings(
    FLOOD_CAMERA_SERVICE_URL="http://flood-api:8091",
    FLOOD_CAMERA_PROXY_CONNECT_TIMEOUT_SECONDS=2.0,
    FLOOD_CAMERA_PROXY_READ_TIMEOUT_SECONDS=120.0,
)
class FloodCameraProxyTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_public_url_resolves_to_proxy(self):
        match = resolve("/api/flood_monitoring/health/")

        self.assertEqual(match.view_name, "flood-camera-proxy")
        self.assertEqual(match.kwargs["path"], "health/")

    @patch("core.flood_camera_monitoring.presentation.proxy.requests.request")
    def test_forwards_method_path_query_body_and_headers(self, request_mock):
        request_mock.return_value = Mock(
            content=b'{"saved": 1}',
            status_code=202,
            headers={"Content-Type": "application/json", "X-Upstream": "flood"},
        )
        request = self.factory.post(
            "/api/flood_monitoring/analyze/all?refresh=1&camera=abc",
            data=b'{"force": true}',
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer token",
            HTTP_X_REQUEST_ID="request-123",
        )

        response = proxy_flood_camera(request, path="analyze/all")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.content, b'{"saved": 1}')
        self.assertEqual(response["X-Upstream"], "flood")
        call = request_mock.call_args.kwargs
        self.assertEqual(call["method"], "POST")
        self.assertEqual(
            call["url"],
            "http://flood-api:8091/api/flood_monitoring/"
            "analyze/all?refresh=1&camera=abc",
        )
        self.assertEqual(call["data"], b'{"force": true}')
        self.assertEqual(call["headers"]["Authorization"], "Bearer token")
        self.assertEqual(call["headers"]["X-Request-Id"], "request-123")
        self.assertEqual(call["timeout"], (2.0, 120.0))
        self.assertFalse(call["allow_redirects"])

    @patch("core.flood_camera_monitoring.presentation.proxy.requests.request")
    def test_preserves_get_response_and_does_not_forward_host(self, request_mock):
        request_mock.return_value = Mock(
            content=b'{"results": []}',
            status_code=200,
            headers={"Content-Type": "application/json", "Content-Length": "999"},
        )
        request = self.factory.get(
            "/api/flood_monitoring/predict/all/",
            HTTP_HOST="public.example",
        )

        response = proxy_flood_camera(request, path="predict/all/")

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"results": []})
        headers = request_mock.call_args.kwargs["headers"]
        self.assertNotIn("Host", headers)
        self.assertNotEqual(response.get("Content-Length"), "999")

    @patch(
        "core.flood_camera_monitoring.presentation.proxy.requests.request",
        side_effect=requests.ConnectionError,
    )
    def test_returns_stable_503_when_service_is_unavailable(self, request_mock):
        request = self.factory.get("/api/flood_monitoring/health/")

        response = proxy_flood_camera(request, path="health/")

        self.assertEqual(response.status_code, 503)
        self.assertJSONEqual(
            response.content,
            {
                "detail": "Flood camera monitoring is unavailable",
                "code": "flood_camera_unavailable",
            },
        )

    @patch(
        "core.flood_camera_monitoring.presentation.proxy.requests.request",
        side_effect=requests.Timeout,
    )
    def test_returns_504_when_service_times_out(self, request_mock):
        request = self.factory.get("/api/flood_monitoring/predict/all/")

        response = proxy_flood_camera(request, path="predict/all/")

        self.assertEqual(response.status_code, 504)
        self.assertJSONEqual(
            response.content,
            {
                "detail": "Flood camera monitoring timed out",
                "code": "flood_camera_timeout",
            },
        )
