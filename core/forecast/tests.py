from django.test import TestCase
from rest_framework.test import APIClient

from core.forecast.infra.models import Forecast


class ForecastOrderingTests(TestCase):
    def test_paginated_forecasts_have_deterministic_order(self):
        older = Forecast.objects.create(
            latitude=-26.3,
            longitude=-48.8,
            date="2026-07-18",
            flood=0.1,
            probability=0.2,
        )
        newer = Forecast.objects.create(
            latitude=-26.2,
            longitude=-48.9,
            date="2026-07-19",
            flood=0.3,
            probability=0.4,
        )

        response = APIClient().get("/api/forecast/foresee/", {"page_size": 1})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["date"], str(newer.date))
        self.assertNotEqual(older.date, newer.date)
