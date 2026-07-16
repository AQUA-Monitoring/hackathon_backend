from unittest import skipUnless
from unittest.mock import Mock, patch

import requests
from django.conf import settings
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

    @skipUnless(
        settings.FLOOD_CAMERA_API_MODE == "proxy",
        "URL resolution is specific to the lightweight proxy mode",
    )
    def test_public_flood_url_resolves_to_proxy_in_lightweight_mode(self):
        match = resolve("/api/flood_monitoring/predict/all/")

        self.assertEqual(match.view_name, "flood-camera-proxy")
        self.assertEqual(match.kwargs["path"], "predict/all/")

    @patch("core.flood_camera_monitoring.presentation.proxy.requests.request")
    def test_forwards_method_path_query_body_and_headers(self, request_mock):
        request_mock.return_value = Mock(
            content=b'{"saved": 1}',
            status_code=202,
            headers={"Content-Type": "application/json", "X-Upstream": "flood"},
        )
        request = self.factory.post(
            "/api/flood_monitoring/analyze/all?refresh=1",
            data=b'{"force": true}',
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer token",
        )

        response = proxy_flood_camera(request, path="analyze/all")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.content, b'{"saved": 1}')
        self.assertEqual(response["X-Upstream"], "flood")
        call = request_mock.call_args.kwargs
        self.assertEqual(call["method"], "POST")
        self.assertEqual(
            call["url"],
            "http://flood-api:8091/api/flood_monitoring/analyze/all?refresh=1",
        )
        self.assertEqual(call["data"], b'{"force": true}')
        self.assertEqual(call["headers"]["Authorization"], "Bearer token")
        self.assertEqual(call["timeout"], (2.0, 120.0))

    @patch(
        "core.flood_camera_monitoring.presentation.proxy.requests.request",
        side_effect=requests.ConnectionError,
    )
    def test_returns_stable_503_when_flood_service_is_unavailable(self, _request):
        response = proxy_flood_camera(
            self.factory.get("/api/flood_monitoring/predict/all/"),
            path="predict/all/",
        )

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
    def test_returns_504_when_flood_service_times_out(self, _request):
        response = proxy_flood_camera(
            self.factory.get("/api/flood_monitoring/predict/all/"),
            path="predict/all/",
        )

        self.assertEqual(response.status_code, 504)
        self.assertJSONEqual(
            response.content,
            {
                "detail": "Flood camera monitoring timed out",
                "code": "flood_camera_timeout",
            },
        )
