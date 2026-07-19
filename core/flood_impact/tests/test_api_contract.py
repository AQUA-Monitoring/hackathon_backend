from django.contrib.gis.geos import LineString, MultiLineString, MultiPolygon, Polygon
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from core.addressing.models import City, GeodataDataset, Region, Street
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
        Region.objects.create(name="Região API", city=self.city.name, city_ref=self.city, geometry=self.city.geometry)
        dataset = GeodataDataset.objects.create(
            city=self.city, kind="street", authority="Teste", title="Ruas", source_url="https://example.test/ruas",
            license_name="Teste", source_version="1", retrieved_at=timezone.now(), sha256="c" * 64,
            source_crs="EPSG:4326", status="active",
        )
        Street.objects.create(
            city=self.city, dataset=dataset, source_record_id="street-api", name="Rua API", normalized_name="rua api",
            geometry=MultiLineString(LineString((-49.1, -26.35), (-49.0, -26.35)), srid=4326),
        )

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
        self.assertEqual(response.data["affected_regions"][0]["name"], "Região API")
        self.assertEqual(response.data["affected_streets"][0]["name"], "Rua API")

        revised = self.client.post(
            f'/api/flood-impact/events/{response.data["id"]}/revisions/',
            {"footprint": self.footprint, "justification": "Ajuste operacional", "source_revision": 1},
            format="json",
        )
        self.assertEqual(revised.status_code, 201, revised.data)
        self.assertEqual(revised.data["current_revision"], 2)
        history = self.client.get(f'/api/flood-impact/events/{response.data["id"]}/history/')
        self.assertEqual(history.status_code, 200, history.data)
        self.assertEqual(history.data["revisions"][-1]["affected_streets"][0]["name"], "Rua API")
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
