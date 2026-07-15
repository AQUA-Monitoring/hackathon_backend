from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.urls import reverse


class HealthViewTests(SimpleTestCase):
    @patch("config.core_health.redis.from_url")
    @patch("config.core_health.connections")
    def test_reports_ok_when_database_and_redis_are_available(
        self, connections, redis_from_url
    ):
        cursor = MagicMock()
        cursor.fetchone.return_value = (1,)
        connections.__getitem__.return_value.cursor.return_value.__enter__.return_value = (
            cursor
        )
        redis_from_url.return_value.ping.return_value = True

        response = self.client.get(reverse("service-health"))

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content,
            {"status": "ok", "checks": {"database": True, "redis": True}},
        )

    @patch("config.core_health.redis.from_url", side_effect=ConnectionError)
    @patch("config.core_health.connections")
    def test_reports_degraded_without_exposing_errors(
        self, connections, redis_from_url
    ):
        connections.__getitem__.side_effect = RuntimeError("secret database error")

        response = self.client.get(reverse("service-health"))

        self.assertEqual(response.status_code, 503)
        self.assertJSONEqual(
            response.content,
            {
                "status": "degraded",
                "checks": {"database": False, "redis": False},
            },
        )
        self.assertNotContains(
            response, "secret database error", status_code=503
        )
