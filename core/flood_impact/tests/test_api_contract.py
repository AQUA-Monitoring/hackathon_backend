from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.addressing.infra.models import City
from core.users.infra.models import User


class FloodImpactApiContractTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create(
            name="Admin territorial", email="territorial@example.test", type=User.UserType.ADMIN
        )
        self.client.force_authenticate(self.admin)
        self.city = City.objects.create(
            name="Cidade API Impacto",
            geometry=MultiPolygon(
                Polygon(((-50, -27), (-48, -27), (-48, -25), (-50, -25), (-50, -27))),
                srid=4326,
            ),
        )
        self.footprint = {
            "type": "MultiPolygon",
            "coordinates": [[[[-49.1, -26.4], [-49.0, -26.4], [-49.0, -26.3], [-49.1, -26.3], [-49.1, -26.4]]]],
        }

    def test_flat_frontend_contract_creates_and_revises_event(self):
        response = self.client.post(
            "/api/flood-impact/events/",
            {
                "city": str(self.city.id),
                "evidence_kind": "USER_REPORT",
                "geometry_method": "MANUAL",
                "footprint": self.footprint,
                "valid_from": timezone.now().isoformat(),
                "confidence": 0.75,
                "source_version": "operador-v1",
                "metadata": {"turno": "noite"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "DRAFT")
        self.assertEqual(response.data["current_revision"], 1)
        self.assertEqual(response.data["footprint"]["type"], "MultiPolygon")

        revised = self.client.post(
            f'/api/flood-impact/events/{response.data["id"]}/revisions/',
            {"footprint": self.footprint, "justification": "Ajuste operacional", "source_revision": 1},
            format="json",
        )
        self.assertEqual(revised.status_code, 201, revised.data)
        self.assertEqual(revised.data["current_revision"], 2)
        event = self.city.flood_spatial_events.get(pk=response.data["id"])
        self.assertEqual(event.current_revision.confidence, 0.75)
        self.assertEqual(event.current_revision.source_version, "operador-v1")
        self.assertEqual(event.current_revision.properties, {"turno": "noite"})

        activated = self.client.post(f'/api/flood-impact/events/{response.data["id"]}/activate/')
        self.assertEqual(activated.status_code, 200, activated.data)
        self.assertEqual(activated.data["status"], "ACTIVE")

    def test_non_admin_cannot_create_event(self):
        user = User.objects.create(name="Operador", email="operator@example.test")
        self.client.force_authenticate(user)
        response = self.client.post("/api/flood-impact/events/", {}, format="json")
        self.assertEqual(response.status_code, 403)
