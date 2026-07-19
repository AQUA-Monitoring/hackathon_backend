from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import MultiLineString, MultiPolygon, Point, Polygon, LineString
from django.test import TestCase
from django.db import IntegrityError
from django.utils import timezone
from rest_framework.test import APIClient

from core.addressing.infra.models import AddressReference, City, GeodataDataset, Neighborhood, Street, StreetNeighborhood


class GeodataApiTests(TestCase):
    def setUp(self):
        self.city = City.objects.create(name="Cidade Geo")
        self.dataset = GeodataDataset.objects.create(city=self.city, kind="street", authority="Prefeitura", title="Ruas", source_url="https://example.test/ruas", license_name="Licença oficial", source_version="1", retrieved_at=timezone.now(), sha256="a" * 64, source_crs="EPSG:4326", status="active")
        self.street = Street.objects.create(city=self.city, dataset=self.dataset, source_record_id="r1", name="Rua A", normalized_name="rua a", geometry=MultiLineString(LineString((0, 0), (1, 1)), srid=4326))
        self.client = APIClient()

    def test_public_streets_and_protected_address_references(self):
        self.assertEqual(self.client.get("/api/addressing/streets/").status_code, 200)
        self.assertIn(self.client.get("/api/addressing/address-references/").status_code, (401, 403))

    def test_resolve_returns_covering_neighborhood(self):
        neighborhood_dataset = GeodataDataset.objects.create(city=self.city, kind="neighborhood_boundary", authority="Prefeitura", title="Bairros", source_url="https://example.test/bairros", license_name="Licença oficial", source_version="1", retrieved_at=timezone.now(), sha256="b" * 64, source_crs="EPSG:4326", status="active")
        Neighborhood.objects.create(name="Centro", city=self.city.name, city_ref=self.city, dataset=neighborhood_dataset, source_record_id="b1", geometry=MultiPolygon(Polygon(((0, 0), (1, 0), (1, 1), (0, 1), (0, 0))), srid=4326))
        user = get_user_model().objects.create_user(username="geo-user", email="geo@example.test", password="secret-test")
        self.client.force_authenticate(user)
        response = self.client.get("/api/addressing/resolve/", {"longitude": .5, "latitude": .5})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["neighborhood"]["name"], "Centro")

    def test_streets_filters_and_geometry_is_opt_in(self):
        neighborhood_dataset = GeodataDataset.objects.create(city=self.city, kind="neighborhood_boundary", authority="Prefeitura", title="Bairros", source_url="https://example.test/bairros", license_name="Licença oficial", source_version="1", retrieved_at=timezone.now(), sha256="c" * 64, source_crs="EPSG:4326", status="active")
        neighborhood = Neighborhood.objects.create(name="Centro", city=self.city.name, city_ref=self.city, dataset=neighborhood_dataset, source_record_id="b1", geometry=MultiPolygon(Polygon(((0, 0), (1, 0), (1, 1), (0, 1), (0, 0))), srid=4326))
        StreetNeighborhood.objects.create(street=self.street, neighborhood=neighborhood)
        response = self.client.get("/api/addressing/streets/", {"city_id": self.city.id, "neighborhood_id": neighborhood.id, "search": "Rua", "bbox": "0,0,2,2"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertNotIn("geometry", response.data["results"][0])
        response = self.client.get("/api/addressing/streets/", {"include_geometry": "true"})
        self.assertIn("geometry", response.data["results"][0])

    def test_territories_validates_filters_and_returns_provenance(self):
        self.assertEqual(self.client.get("/api/addressing/territories/", {"city_id": "bad"}).status_code, 400)
        self.assertEqual(self.client.get("/api/addressing/territories/", {"type": "district"}).status_code, 400)
        self.city.geometry = MultiPolygon(Polygon(((0, 0), (1, 0), (1, 1), (0, 1), (0, 0))), srid=4326)
        self.city.geometry_dataset = self.dataset
        self.city.source_record_id = "municipio-1"
        self.city.save()
        response = self.client.get("/api/addressing/territories/", {"type": "city", "dataset_version": "1", "bbox": "0,0,2,2"})
        properties = response.data["features"][0]["properties"]
        self.assertEqual(properties["city_id"], str(self.city.id))
        self.assertEqual(properties["source_record_id"], "municipio-1")
        self.assertEqual(properties["provenance"]["authority"], "Prefeitura")

    def test_resolve_uses_aliases_and_restricts_nearest_address_to_city(self):
        city_dataset = GeodataDataset.objects.create(city=self.city, kind="city_boundary", authority="Prefeitura", title="Município", source_url="https://example.test/cidade", license_name="Licença oficial", source_version="1", retrieved_at=timezone.now(), sha256="d" * 64, source_crs="EPSG:4326", status="active")
        self.city.geometry = MultiPolygon(Polygon(((0, 0), (2, 0), (2, 2), (0, 2), (0, 0))), srid=4326)
        self.city.geometry_dataset = city_dataset
        self.city.save()
        AddressReference.objects.create(city=self.city, dataset=self.dataset, source_record_id="a1", street=self.street, street_name="Rua A", location=Point(.5005, .5005, srid=4326))
        other_city = City.objects.create(name="Outra Cidade")
        other_dataset = GeodataDataset.objects.create(city=other_city, kind="address_point", authority="IBGE", title="Endereços", source_url="https://example.test/enderecos", license_name="Licença oficial", source_version="1", retrieved_at=timezone.now(), sha256="e" * 64, source_crs="EPSG:4326", status="active")
        AddressReference.objects.create(city=other_city, dataset=other_dataset, source_record_id="a2", street_name="Rua Errada", location=Point(.5, .5, srid=4326))
        user = get_user_model().objects.create_user(username="geo-alias", email="alias@example.test", password="secret-test")
        self.client.force_authenticate(user)
        response = self.client.get("/api/addressing/resolve/", {"lon": .5, "lat": .5})
        self.assertEqual(response.data["nearest_address"]["street"], "Rua A")
        self.assertEqual(response.data["nearest_address"]["match_type"], "nearest")
        self.assertIn("distance", response.data["nearest_address"])

    def test_address_references_require_staff_and_resolve_applies_radius(self):
        user = get_user_model().objects.create_user(username="regular", email="regular@example.test", password="secret-test")
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get("/api/addressing/address-references/").status_code, 403)
        self.assertEqual(self.client.get("/api/addressing/resolve/", {"lat": 0, "lon": 0, "radius_m": 5000}).status_code, 400)

    def test_admin_import_endpoint_permissions_and_errors(self):
        from unittest.mock import patch
        from django.test import override_settings
        from django.core.management.base import CommandError
        with TemporaryDirectory() as directory:
            path = Path(directory) / "input.geojson"
            path.write_text("{}", encoding="utf-8")
            user = get_user_model().objects.create_user(username="regular-import", email="ri@example.test", password="secret-test")
            self.client.force_authenticate(user)
            with override_settings(GEODATA_IMPORT_ROOT=Path(directory)):
                self.assertEqual(self.client.post("/api/addressing/import-dataset/", {"path": "input.geojson"}, format="json").status_code, 403)
                admin = get_user_model().objects.create_superuser(username="admin-import", email="ai@example.test", password="secret-test")
                self.client.force_authenticate(admin)
                with patch("core.addressing.presentation.viewsets.call_command", side_effect=CommandError("Geometria inválida: teste")):
                    response = self.client.post("/api/addressing/import-dataset/", {"path": "input.geojson"}, format="json")
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.data["error"]["code"], "invalid_geometry")
                with patch("core.addressing.presentation.viewsets.call_command", side_effect=IntegrityError("conflict")):
                    response = self.client.post("/api/addressing/import-dataset/", {"path": "input.geojson"}, format="json")
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(response.data["error"]["code"], "dataset_conflict")
