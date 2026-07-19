from uuid import uuid4

from rest_framework import status
from rest_framework.test import APITestCase

from core.addressing.infra.models import Address, City
from core.flood_camera_monitoring.infra.models import Camera


class NearbyCamerasApiTests(APITestCase):
    def setUp(self):
        self.city = City.objects.create(name="Cidade Câmeras Próximas")
        # A randomized test area keeps --keepdb runs isolated from data left by
        # a previously interrupted test process.
        self.origin_latitude = -20 - (uuid4().int % 500_000) / 100_000
        self.origin_longitude = -40 - (uuid4().int % 500_000) / 100_000

    def address(self, *, latitude, longitude, street="Rua de teste"):
        return Address.objects.create(
            street=street,
            city=self.city.name,
            city_ref=self.city,
            latitude=latitude,
            longitude=longitude,
        )

    def camera(
        self,
        description,
        *,
        camera_status=Camera.CameraStatus.ACTIVE,
        address=None,
        latitude=None,
        longitude=None,
        video_hls="https://cameras.example/stream.m3u8",
        video_embed="https://cameras.example/embed",
    ):
        return Camera.objects.create(
            description=description,
            status=camera_status,
            address=address,
            latitude=latitude,
            longitude=longitude,
            video_hls=video_hls,
            video_embed=video_embed,
        )

    def test_public_nearby_uses_canonical_coordinates_and_safe_summary(self):
        origin = self.camera(
            "Origem",
            address=self.address(
                latitude=self.origin_latitude, longitude=self.origin_longitude
            ),
        )
        nearest = self.camera(
            "A mais próxima",
            address=self.address(
                latitude=self.origin_latitude + 0.0005,
                longitude=self.origin_longitude,
            ),
        )
        legacy_offline = self.camera(
            "B offline legado",
            camera_status=Camera.CameraStatus.OFFLINE,
            latitude=self.origin_latitude + 0.0015,
            longitude=self.origin_longitude,
        )
        self.camera(
            "Inativa",
            camera_status=Camera.CameraStatus.INACTIVE,
            address=self.address(
                latitude=self.origin_latitude + 0.001,
                longitude=self.origin_longitude,
            ),
        )
        self.camera(
            "Endereço incompleto não usa legado",
            address=self.address(latitude=None, longitude=None),
            latitude=self.origin_latitude + 0.001,
            longitude=self.origin_longitude,
        )
        self.camera(
            "Endereço distante vence legado",
            address=self.address(
                latitude=self.origin_latitude - 1,
                longitude=self.origin_longitude,
            ),
            latitude=self.origin_latitude + 0.001,
            longitude=self.origin_longitude,
        )

        response = self.client.get(
            f"/api/flood_monitoring/cameras/{origin.id}/nearby/",
            {"radius_m": 1000},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["ordering"], "distance")
        self.assertEqual(response.data["radius_m"], 1000)
        self.assertEqual(
            [item["id"] for item in response.data["results"]],
            [str(nearest.id), str(legacy_offline.id)],
        )
        self.assertLess(
            response.data["results"][0]["distance_m"],
            response.data["results"][1]["distance_m"],
        )
        offline_item = response.data["results"][1]
        self.assertEqual(offline_item["administrative_status"], "ACTIVE")
        self.assertEqual(offline_item["status"], "OFFLINE")
        for item in response.data["results"]:
            self.assertNotIn("video_hls", item)
            self.assertNotIn("video_embed", item)
            self.assertNotIn("created_by", item)

    def test_defaults_to_six_items_and_has_deterministic_pagination(self):
        origin = self.camera(
            "Origem",
            address=self.address(
                latitude=self.origin_latitude, longitude=self.origin_longitude
            ),
        )
        for index in range(7):
            self.camera(
                f"Câmera {index}",
                address=self.address(
                    latitude=self.origin_latitude,
                    longitude=self.origin_longitude + 0.0001 + index * 0.00001,
                    street=f"Rua {index}",
                ),
            )

        first_page = self.client.get(
            f"/api/flood_monitoring/cameras/{origin.id}/nearby/"
        )
        second_page = self.client.get(
            f"/api/flood_monitoring/cameras/{origin.id}/nearby/", {"page": 2}
        )

        self.assertEqual(first_page.status_code, status.HTTP_200_OK)
        self.assertEqual(first_page.data["count"], 7)
        self.assertEqual(first_page.data["ordering"], "distance")
        self.assertEqual(first_page.data["radius_m"], 5000)
        self.assertEqual(len(first_page.data["results"]), 6)
        self.assertEqual(second_page.status_code, status.HTTP_200_OK)
        self.assertEqual(len(second_page.data["results"]), 1)

    def test_rejects_invalid_parameters_and_missing_pages(self):
        origin = self.camera(
            "Origem",
            address=self.address(
                latitude=self.origin_latitude, longitude=self.origin_longitude
            ),
        )
        route = f"/api/flood_monitoring/cameras/{origin.id}/nearby/"

        for params in (
            {"radius_m": 99},
            {"radius_m": 20_001},
            {"radius_m": "invalid"},
            {"page": 0},
            {"page_size": 21},
        ):
            with self.subTest(params=params):
                response = self.client.get(route, params)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        missing_page = self.client.get(route, {"page": 2})
        self.assertEqual(missing_page.status_code, status.HTTP_404_NOT_FOUND)

    def test_returns_not_found_and_unprocessable_origin(self):
        missing = self.client.get(
            "/api/flood_monitoring/cameras/00000000-0000-0000-0000-000000000000/nearby/"
        )
        self.assertEqual(missing.status_code, status.HTTP_404_NOT_FOUND)

        incomplete_origin = self.camera(
            "Origem sem coordenadas",
            address=self.address(latitude=None, longitude=None),
            latitude=self.origin_latitude,
            longitude=self.origin_longitude,
        )
        unprocessable = self.client.get(
            f"/api/flood_monitoring/cameras/{incomplete_origin.id}/nearby/"
        )
        self.assertEqual(
            unprocessable.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        self.assertEqual(unprocessable.data["code"], "camera_location_unavailable")
