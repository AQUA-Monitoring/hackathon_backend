from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.addressing.models import City, Region
from core.flood_camera_monitoring.infra.models import (
    Camera,
    FloodDetectionRecord,
    OperationalAlert,
)
from core.users.infra.models import User

from ..adapters import PushDeliveryError
from ..models import PushDelivery, PushSubscription, RegionSubscription
from ..services import deliver_push, fanout_alert


class NotificationFixture(TestCase):
    def setUp(self):
        self.city = City.objects.create(name="Joinville Notifica")
        self.region = Region.objects.create(
            name="Região Norte", city=self.city.name, city_ref=self.city
        )
        self.other_region = Region.objects.create(
            name="Região Sul", city=self.city.name, city_ref=self.city
        )
        self.admin = User.objects.create(
            name="Admin", email="notification-admin@example.test", type=User.UserType.ADMIN
        )
        self.user = User.objects.create(
            name="Morador", email="notification-user@example.test"
        )
        self.other_user = User.objects.create(
            name="Outro", email="notification-other@example.test"
        )
        self.camera = Camera.objects.create(
            status=Camera.CameraStatus.ACTIVE,
            description="Câmera Norte",
            region=self.region,
        )
        self.detection = FloodDetectionRecord.objects.create(
            camera=self.camera,
            is_flooded=True,
            confidence=0.94,
            prob_normal=0.02,
            prob_medium=0.04,
            prob_flooded=0.94,
        )
        self.alert = OperationalAlert.objects.create(
            camera=self.camera,
            region=self.region,
            initial_detection=self.detection,
            latest_detection=self.detection,
            first_detected_at=self.detection.created_at,
            last_detected_at=self.detection.created_at,
            evidence={
                "classification": "FLOOD_INDICATION",
                "confidence": 0.94,
                "probabilities": {"normal": 0.02, "medium": 0.04, "flooded": 0.94},
                "model_version": "test-model",
            },
        )


class SubscriptionApiTests(NotificationFixture):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_authentication_is_required(self):
        self.assertEqual(self.client.get("/api/region-subscriptions/").status_code, 401)
        self.assertEqual(self.client.post("/api/push-subscriptions/", {}, format="json").status_code, 401)

    def test_region_subscription_is_idempotent_and_can_be_deleted(self):
        self.client.force_authenticate(self.user)
        payload = {"region_id": str(self.region.id)}
        created = self.client.post("/api/region-subscriptions/", payload, format="json")
        repeated = self.client.post("/api/region-subscriptions/", payload, format="json")
        self.assertEqual(created.status_code, 201)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(RegionSubscription.objects.count(), 1)
        listed = self.client.get("/api/region-subscriptions/")
        self.assertEqual(listed.data["results"][0]["region"]["name"], "Região Norte")
        self.assertEqual(
            listed.data["results"][0]["region"]["city"],
            {"id": str(self.city.id), "name": self.city.name},
        )
        deleted = self.client.delete(
            f"/api/region-subscriptions/?region_id={self.region.id}"
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(
            self.client.delete(f"/api/region-subscriptions/?region_id={self.region.id}").status_code,
            204,
        )

    def test_push_subscription_is_upserted_without_exposing_keys(self):
        self.client.force_authenticate(self.user)
        payload = {
            "endpoint": "https://push.example.test/device-1",
            "keys": {"p256dh": "public-device-key", "auth": "auth-secret"},
        }
        response = self.client.post("/api/push-subscriptions/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("endpoint", response.data)
        self.assertNotIn("keys", response.data)
        subscription = PushSubscription.objects.get()
        self.assertEqual(subscription.user, self.user)
        self.assertEqual(subscription.p256dh, "public-device-key")
        renewed = self.client.post("/api/push-subscriptions/", payload, format="json")
        self.assertEqual(renewed.status_code, 200)
        deleted = self.client.delete(
            "/api/push-subscriptions/?endpoint=https%3A%2F%2Fpush.example.test%2Fdevice-1"
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(
            self.client.delete(
                "/api/push-subscriptions/?endpoint=https%3A%2F%2Fpush.example.test%2Fdevice-1"
            ).status_code,
            204,
        )

    @override_settings(WEB_PUSH_ENABLED=False, WEB_PUSH_VAPID_PUBLIC_KEY="not-public")
    def test_config_does_not_expose_key_while_disabled(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/push-subscriptions/config/")
        self.assertEqual(
            response.data,
            {"enabled": False, "public_key": "", "application_server_key": ""},
        )


class PushDeliveryServiceTests(NotificationFixture):
    def setUp(self):
        super().setUp()
        RegionSubscription.objects.create(user=self.user, region=self.region)
        RegionSubscription.objects.create(user=self.other_user, region=self.other_region)
        self.subscription = PushSubscription.objects.create(
            user=self.user,
            endpoint="https://push.example.test/device-1",
            p256dh="key",
            auth="auth",
        )
        PushSubscription.objects.create(
            user=self.other_user,
            endpoint="https://push.example.test/device-2",
            p256dh="key-2",
            auth="auth-2",
        )

    @patch("core.notifications.tasks.deliver_push_batch_task.delay")
    def test_fanout_targets_region_and_is_idempotent(self, delay):
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(fanout_alert(self.alert, PushDelivery.Kind.CONFIRMED), 1)
            self.assertEqual(fanout_alert(self.alert, PushDelivery.Kind.CONFIRMED), 0)
        self.assertEqual(PushDelivery.objects.count(), 1)
        self.assertEqual(PushDelivery.objects.get().subscription, self.subscription)
        delay.assert_called_once()

    def test_successful_delivery_records_sent_without_private_data_in_payload(self):
        delivery = PushDelivery.objects.create(
            operational_alert=self.alert,
            subscription=self.subscription,
            kind=PushDelivery.Kind.CONFIRMED,
        )

        class Adapter:
            def send(inner_self, *, subscription_info, payload):
                self.assertEqual(subscription_info["endpoint"], self.subscription.endpoint)
                self.assertNotIn("endpoint", payload)
                self.assertNotIn("p256dh", str(payload))

        self.assertEqual(deliver_push(delivery.id, adapter=Adapter()), PushDelivery.Status.SENT)
        delivery.refresh_from_db()
        self.assertEqual(delivery.attempts, 1)
        self.assertIsNotNone(delivery.sent_at)

    def test_gone_subscription_is_expired_and_deactivated(self):
        delivery = PushDelivery.objects.create(
            operational_alert=self.alert,
            subscription=self.subscription,
            kind=PushDelivery.Kind.CONFIRMED,
        )

        class GoneAdapter:
            def send(self, **kwargs):
                raise PushDeliveryError("endpoint expirado", status_code=410)

        self.assertEqual(deliver_push(delivery.id, adapter=GoneAdapter()), PushDelivery.Status.EXPIRED)
        delivery.refresh_from_db()
        self.subscription.refresh_from_db()
        self.assertFalse(self.subscription.is_active)
        self.assertEqual(delivery.last_error, "endpoint expirado")

    def test_failure_is_sanitized_and_marked_for_retry(self):
        delivery = PushDelivery.objects.create(
            operational_alert=self.alert,
            subscription=self.subscription,
            kind=PushDelivery.Kind.CONFIRMED,
        )

        class FailedAdapter:
            def send(self, **kwargs):
                raise PushDeliveryError("falha temporária")

        self.assertEqual(
            deliver_push(delivery.id, adapter=FailedAdapter()),
            PushDelivery.Status.FAILED,
        )
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, PushDelivery.Status.FAILED)
        self.assertEqual(delivery.last_error, "falha temporária")


class OperationalAlertApiTests(NotificationFixture):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_standard_user_cannot_access_admin_feed(self):
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/operational-alerts/").status_code, 403)
        self.assertEqual(
            self.client.post(f"/api/operational-alerts/{self.alert.id}/confirm/", {}).status_code,
            403,
        )

    def test_admin_feed_is_paginated_and_does_not_expose_stream_urls(self):
        self.camera.video_hls = "https://private.example.test/stream.m3u8"
        self.camera.save(update_fields=["video_hls"])
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/operational-alerts/?status=OPEN_INDICATION")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        alert = response.data["results"][0]
        self.assertNotIn("video_hls", alert["camera"])
        self.assertEqual(alert["camera"]["administrative_status"], "ACTIVE")
        self.assertEqual(alert["camera"]["detail_path"], f"/cameras/{self.camera.id}")
        self.assertEqual(alert["region"]["city"]["id"], str(self.city.id))
        self.assertEqual(alert["evidence"]["initial_detection_id"], str(self.detection.id))
        self.assertEqual(alert["evidence"]["latest_detection_id"], str(self.detection.id))
        self.assertIsNone(alert["evidence"]["image_url"])

    @patch("core.notifications.tasks.deliver_push_batch_task.delay")
    def test_confirmation_is_unique_and_second_request_conflicts(self, delay):
        RegionSubscription.objects.create(user=self.user, region=self.region)
        PushSubscription.objects.create(
            user=self.user,
            endpoint="https://push.example.test/device-confirm",
            p256dh="key",
            auth="auth",
        )
        self.client.force_authenticate(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                f"/api/operational-alerts/{self.alert.id}/confirm/", {}, format="json"
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "CONFIRMED")
        self.assertEqual(PushDelivery.objects.count(), 1)
        repeated = self.client.post(
            f"/api/operational-alerts/{self.alert.id}/confirm/", {}, format="json"
        )
        self.assertEqual(repeated.status_code, 409)
        self.assertEqual(PushDelivery.objects.count(), 1)
