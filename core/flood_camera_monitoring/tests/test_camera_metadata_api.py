from datetime import timedelta
from types import ModuleType
from unittest.mock import Mock, patch

from django.db.models.deletion import ProtectedError
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core.addressing.infra.models import City, Neighborhood, Region
from core.flood_camera_monitoring.infra.models import (
    Camera,
    CameraOperationalSnapshot,
)
from core.users.infra.models import User


class CameraMetadataApiTests(APITestCase):
    def setUp(self):
        self.initial_camera_count = Camera.objects.count()
        self.city = City.objects.create(name="Cidade Câmera Teste")
        self.region = Region.objects.create(
            name="Centro",
            city=self.city.name,
            city_ref=self.city,
        )
        self.neighborhood = Neighborhood.objects.create(
            name="América",
            city=self.city.name,
            city_ref=self.city,
            region=self.region,
        )
        self.admin = User.objects.create(
            name="Admin",
            email="admin-cameras@example.test",
            type=User.UserType.ADMIN,
        )
        self.standard = User.objects.create(
            name="Standard",
            email="standard-cameras@example.test",
            type=User.UserType.STANDARD,
        )

    def camera_payload(self, *, hls="https://cameras.example/stream.m3u8"):
        return {
            "description": "Câmera América",
            "video_hls": hls,
            "video_embed": None,
            "address": {
                "city_id": str(self.city.id),
                "neighborhood_id": str(self.neighborhood.id),
                "street": "Rua Blumenau",
                "number": "100",
                "state": "SC",
                "country": "Brazil",
                "zipcode": "89204-250",
                "latitude": -26.285,
                "longitude": -48.853,
            },
        }

    def create_camera_as_admin(self, **kwargs):
        self.client.force_authenticate(self.admin)
        return self.client.post(
            "/api/flood_monitoring/cameras/",
            self.camera_payload(**kwargs),
            format="json",
        )

    def test_admin_creates_camera_address_author_and_default_snapshot(self):
        response = self.create_camera_as_admin(
            hls=" HTTPS://CAMERAS.EXAMPLE/stream.m3u8/ "
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        camera = Camera.objects.select_related("address", "created_by").get(
            pk=response.data["id"]
        )
        self.assertEqual(camera.status, Camera.CameraStatus.INACTIVE)
        self.assertEqual(camera.video_hls, "https://cameras.example/stream.m3u8")
        self.assertEqual(camera.created_by, self.admin)
        self.assertEqual(camera.address.city_ref, self.city)
        self.assertEqual(camera.address.neighborhood, self.neighborhood)
        self.assertEqual(camera.latitude, camera.address.latitude)
        snapshot = camera.operational_snapshot
        self.assertEqual(snapshot.stream_status, snapshot.StreamStatus.UNKNOWN)
        self.assertEqual(snapshot.analysis_status, snapshot.AnalysisStatus.NOT_ANALYZED)
        self.assertEqual(snapshot.model_status, snapshot.ModelStatus.UNKNOWN)
        self.assertEqual(response.data["created_by"], {"id": str(self.admin.id)})

    def test_creation_requires_admin_and_rejects_client_audit_fields(self):
        response = self.client.post(
            "/api/flood_monitoring/cameras/", self.camera_payload(), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(self.standard)
        response = self.client.post(
            "/api/flood_monitoring/cameras/", self.camera_payload(), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.admin)
        payload = self.camera_payload()
        payload["status"] = "ACTIVE"
        payload["created_by"] = str(self.standard.id)
        response = self.client.post(
            "/api/flood_monitoring/cameras/", payload, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)
        self.assertIn("created_by", response.data)
        self.assertEqual(Camera.objects.count(), self.initial_camera_count)

    def test_duplicate_normalized_hls_returns_conflict(self):
        first = self.create_camera_as_admin(
            hls="https://CAMERAS.example/stream.m3u8/"
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second_payload = self.camera_payload(
            hls="https://cameras.example/stream.m3u8"
        )
        second_payload["description"] = "Outra câmera"
        second = self.client.post(
            "/api/flood_monitoring/cameras/", second_payload, format="json"
        )
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("video_hls", second.data)
        self.assertEqual(Camera.objects.count(), self.initial_camera_count + 1)

    def test_referenced_address_and_author_are_protected(self):
        created = self.create_camera_as_admin()
        camera = Camera.objects.select_related("address", "created_by").get(
            pk=created.data["id"]
        )

        with self.assertRaises(ProtectedError):
            camera.address.delete()
        with self.assertRaises(ProtectedError):
            self.admin.delete()

    def test_snapshot_failure_rolls_back_camera_and_address(self):
        self.client.force_authenticate(self.admin)
        address_count = self.city.addresses.count()
        camera_count = Camera.objects.count()

        with patch.object(
            CameraOperationalSnapshot.objects,
            "create",
            side_effect=RuntimeError("snapshot failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "snapshot failure"):
                self.client.post(
                    "/api/flood_monitoring/cameras/",
                    self.camera_payload(),
                    format="json",
                )

        self.assertEqual(Camera.objects.count(), camera_count)
        self.assertEqual(self.city.addresses.count(), address_count)

    def test_metadata_routes_do_not_call_inference_or_stream_adapters(self):
        classifier_factory = Mock(side_effect=AssertionError("classifier called"))
        stream_factory = Mock(side_effect=AssertionError("stream called"))
        classifier_module = ModuleType(
            "core.flood_camera_monitoring.infra.torch_flood_classifier"
        )
        classifier_module.build_default_classifier = classifier_factory
        stream_module = ModuleType(
            "core.flood_camera_monitoring.adapters.gateways.opencv_stream_adapter"
        )
        stream_module.OpenCVVideoStream = stream_factory

        with patch.dict(
            "sys.modules",
            {
                classifier_module.__name__: classifier_module,
                stream_module.__name__: stream_module,
            },
        ):
            created = self.create_camera_as_admin(
                hls="https://cameras.example/no-inference.m3u8"
            )
            self.assertEqual(created.status_code, status.HTTP_201_CREATED)
            camera = Camera.objects.get(pk=created.data["id"])
            camera.status = Camera.CameraStatus.ACTIVE
            camera.save(update_fields=["status"])

            self.client.force_authenticate(user=None)
            self.assertEqual(
                self.client.get("/api/flood_monitoring/cameras/").status_code,
                status.HTTP_200_OK,
            )
            self.assertEqual(
                self.client.get(
                    f"/api/flood_monitoring/cameras/{camera.id}/"
                ).status_code,
                status.HTTP_200_OK,
            )
            self.assertEqual(
                self.client.get("/api/flood_monitoring/predict/all/").status_code,
                status.HTTP_200_OK,
            )

        classifier_factory.assert_not_called()
        stream_factory.assert_not_called()

    def test_public_list_omits_reproduction_and_author_and_detail_is_progressive(self):
        created = self.create_camera_as_admin()
        camera_id = created.data["id"]
        self.client.force_authenticate(user=None)

        listing = self.client.get("/api/flood_monitoring/cameras/")
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertTrue(
            all("created_by" not in camera for camera in listing.data["results"])
        )
        self.assertTrue(
            all("video_hls" not in camera for camera in listing.data["results"])
        )
        self.assertTrue(
            all("video_embed" not in camera for camera in listing.data["results"])
        )

        public_detail = self.client.get(
            f"/api/flood_monitoring/cameras/{camera_id}/"
        )
        self.assertNotIn("created_by", public_detail.data)
        self.assertIsNone(public_detail.data["video_hls"])
        self.assertIsNone(public_detail.data["video_embed"])

        self.client.force_authenticate(self.standard)
        standard_detail = self.client.get(
            f"/api/flood_monitoring/cameras/{camera_id}/"
        )
        self.assertIsNone(standard_detail.data["video_hls"])
        self.assertIsNone(standard_detail.data["video_embed"])

        self.client.force_authenticate(self.admin)
        admin_detail = self.client.get(
            f"/api/flood_monitoring/cameras/{camera_id}/"
        )
        self.assertEqual(
            admin_detail.data["created_by"], {"id": str(self.admin.id)}
        )
        self.assertEqual(
            admin_detail.data["video_hls"],
            "https://cameras.example/stream.m3u8",
        )

    def test_active_unavailable_camera_keeps_source_for_explicit_public_retry(self):
        created = self.create_camera_as_admin()
        camera = Camera.objects.get(pk=created.data["id"])
        camera.status = Camera.CameraStatus.ACTIVE
        camera.save(update_fields=["status"])
        snapshot = camera.operational_snapshot
        snapshot.stream_status = snapshot.StreamStatus.UNAVAILABLE
        snapshot.save(update_fields=["stream_status"])

        self.client.force_authenticate(user=None)
        detail = self.client.get(f"/api/flood_monitoring/cameras/{camera.id}/")

        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(
            detail.data["video_hls"], "https://cameras.example/stream.m3u8"
        )
        self.assertEqual(
            detail.data["operational"]["stream"]["status"], "UNAVAILABLE"
        )

    @override_settings(FLOOD_ANALYSIS_STALE_SECONDS=600)
    def test_stale_preserves_valid_result_but_fallback_nulls_it(self):
        created = self.create_camera_as_admin()
        camera = Camera.objects.get(pk=created.data["id"])
        snapshot = camera.operational_snapshot
        snapshot.analysis_status = snapshot.AnalysisStatus.AVAILABLE
        snapshot.classification = snapshot.CameraClassification.FLOOD_INDICATION
        snapshot.prob_normal = 10.0
        snapshot.prob_medium = 20.0
        snapshot.prob_flooded = 70.0
        snapshot.confidence = 70.0
        snapshot.frames = 3
        snapshot.analysis_started_at = timezone.now() - timedelta(seconds=611)
        snapshot.analyzed_at = timezone.now() - timedelta(seconds=601)
        snapshot.model_status = snapshot.ModelStatus.READY
        snapshot.model_version = "camera-model-v1"
        snapshot.save()

        detail = self.client.get(f"/api/flood_monitoring/cameras/{camera.id}/")
        analysis = detail.data["operational"]["analysis"]
        self.assertEqual(analysis["status"], "STALE")
        self.assertEqual(analysis["classification"], "FLOOD_INDICATION")
        self.assertEqual(analysis["probabilities"]["flooded"], 70.0)
        self.assertEqual(analysis["frames"], 3)

        snapshot.model_status = snapshot.ModelStatus.FALLBACK
        snapshot.save()
        detail = self.client.get(f"/api/flood_monitoring/cameras/{camera.id}/")
        analysis = detail.data["operational"]["analysis"]
        self.assertIsNone(analysis["classification"])
        self.assertIsNone(analysis["probabilities"])
        self.assertIsNone(analysis["confidence"])
        self.assertIsNone(analysis["frames"])

    def test_predict_all_reads_snapshot_and_nulls_unavailable_result(self):
        created = self.create_camera_as_admin()
        camera = Camera.objects.get(pk=created.data["id"])
        camera.status = Camera.CameraStatus.ACTIVE
        camera.save(update_fields=["status"])
        snapshot = camera.operational_snapshot
        snapshot.analysis_status = snapshot.AnalysisStatus.NO_FRAME
        snapshot.frames = 0
        snapshot.model_status = snapshot.ModelStatus.READY
        snapshot.model_version = "camera-model-v1"
        snapshot.save()

        response = self.client.get("/api/flood_monitoring/predict/all/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = next(
            item
            for item in response.data["results"]
            if item["camera"]["id"] == str(camera.id)
        )
        self.assertIsNone(item["is_flooded"])
        self.assertIsNone(item["confidence"])
        self.assertIsNone(item["medium"])
        self.assertEqual(
            item["probabilities"],
            {"normal": None, "medium": None, "flooded": None},
        )
        self.assertEqual(item["meta"]["status"], "NO_FRAME")

    def test_list_supports_search_filters_and_operational_priority_before_paging(self):
        normal_response = self.create_camera_as_admin(
            hls="https://cameras.example/normal.m3u8"
        )
        normal = Camera.objects.get(pk=normal_response.data["id"])
        normal.status = Camera.CameraStatus.ACTIVE
        normal.save(update_fields=["status"])
        normal_snapshot = normal.operational_snapshot
        normal_snapshot.analysis_status = normal_snapshot.AnalysisStatus.AVAILABLE
        normal_snapshot.classification = (
            normal_snapshot.CameraClassification.NO_INDICATION
        )
        normal_snapshot.prob_normal = 90.0
        normal_snapshot.prob_medium = 5.0
        normal_snapshot.prob_flooded = 5.0
        normal_snapshot.confidence = 90.0
        normal_snapshot.frames = 2
        normal_snapshot.analyzed_at = timezone.now()
        normal_snapshot.model_status = normal_snapshot.ModelStatus.READY
        normal_snapshot.model_version = "camera-model-v1"
        normal_snapshot.save()

        flood_payload = self.camera_payload(
            hls="https://cameras.example/flood.m3u8"
        )
        flood_payload["description"] = "Câmera prioritária"
        flood_response = self.client.post(
            "/api/flood_monitoring/cameras/", flood_payload, format="json"
        )
        flood = Camera.objects.get(pk=flood_response.data["id"])
        flood.status = Camera.CameraStatus.ACTIVE
        flood.save(update_fields=["status"])
        flood_snapshot = flood.operational_snapshot
        flood_snapshot.analysis_status = flood_snapshot.AnalysisStatus.AVAILABLE
        flood_snapshot.classification = (
            flood_snapshot.CameraClassification.FLOOD_INDICATION
        )
        flood_snapshot.prob_normal = 5.0
        flood_snapshot.prob_medium = 5.0
        flood_snapshot.prob_flooded = 90.0
        flood_snapshot.confidence = 90.0
        flood_snapshot.frames = 2
        flood_snapshot.analyzed_at = timezone.now()
        flood_snapshot.model_status = flood_snapshot.ModelStatus.READY
        flood_snapshot.model_version = "camera-model-v1"
        flood_snapshot.save()

        first_page = self.client.get(
            "/api/flood_monitoring/cameras/?page_size=1"
        )
        self.assertEqual(first_page.data["results"][0]["id"], str(flood.id))

        filtered = self.client.get(
            "/api/flood_monitoring/cameras/",
            {
                "classification": "FLOOD_INDICATION",
                "region_id": str(self.region.id),
                "search": "prioritária",
            },
        )
        self.assertEqual(filtered.data["count"], 1)
        self.assertEqual(filtered.data["results"][0]["id"], str(flood.id))


class AddressingLookupApiTests(APITestCase):
    def test_cities_and_city_id_region_lookup_have_additive_contract(self):
        initial_city_count = City.objects.count()
        city = City.objects.create(name="Cidade Lookup Teste")
        region = Region.objects.create(
            name="Centro", city=city.name, city_ref=city
        )
        neighborhood = Neighborhood.objects.create(
            name="América",
            city=city.name,
            city_ref=city,
            region=region,
        )

        cities = self.client.get("/api/addressing/cities/")
        self.assertEqual(cities.status_code, status.HTTP_200_OK)
        self.assertEqual(cities.data["count"], initial_city_count + 1)
        self.assertIn(
            {"id": str(city.id), "name": city.name}, cities.data["results"]
        )

        regions = self.client.get(
            "/api/addressing/regions-neighborhoods/", {"city_id": str(city.id)}
        )
        self.assertEqual(regions.status_code, status.HTTP_200_OK)
        self.assertEqual(regions.data["city"], city.name)
        self.assertEqual(regions.data["city_id"], str(city.id))
        self.assertEqual(regions.data["regions"][0]["city_id"], str(city.id))
        self.assertEqual(
            regions.data["regions"][0]["neighborhoods"][0]["id"],
            str(neighborhood.id),
        )

        invalid = self.client.get(
            "/api/addressing/regions-neighborhoods/",
            {"city": city.name, "city_id": str(city.id)},
        )
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(invalid.data["code"], "invalid_filter")
