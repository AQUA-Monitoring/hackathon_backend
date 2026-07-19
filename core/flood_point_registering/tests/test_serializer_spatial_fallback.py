from django.test import TestCase

from django.contrib.gis.geos import MultiPolygon, Polygon

from core.addressing.models import City, Neighborhood

from core.flood_point_registering.presentation.serializers.RegisterSerializer import (
    FloodPointRegisterSerializer,
)


class FloodPointSpatialFallbackTests(TestCase):
    def test_missing_props_does_not_invent_zero_coordinates(self):
        city = City.objects.create(name="Cidade fallback")
        neighborhood = Neighborhood.objects.create(
            name="Bairro fallback", city=city.name, city_ref=city
        )
        serializer = FloodPointRegisterSerializer()
        value = serializer.to_internal_value(
            {
                "city": str(city.pk),
                "neighborhood": str(neighborhood.pk),
                "possibility": 0.5,
                "finished_at": "2099-07-20T00:00:00Z",
            }
        )

        self.assertEqual(value["props"]["type"], "Feature")
        self.assertIsNone(value["props"]["geometry"])

    def test_frontend_payload_persists_and_resolves_spatial_evidence(self):
        city_geometry = MultiPolygon(Polygon((
            (-48.90, -26.40), (-48.70, -26.40), (-48.70, -26.20),
            (-48.90, -26.20), (-48.90, -26.40),
        ), srid=4326), srid=4326)
        city = City.objects.create(name="Cidade espacial", geometry=city_geometry)
        neighborhood = Neighborhood.objects.create(
            name="Bairro espacial", city=city.name, city_ref=city,
            geometry=city_geometry,
        )
        footprint = {
            "type": "MultiPolygon",
            "coordinates": [[[[-48.82, -26.32], [-48.78, -26.32],
                [-48.78, -26.28], [-48.82, -26.28], [-48.82, -26.32]]]],
        }
        serializer = FloodPointRegisterSerializer(data={
            "city": str(city.pk),
            "neighborhood": str(neighborhood.pk),
            "possibility": 0.5,
            "finished_at": "2099-07-20T00:00:00Z",
            "props": [{"type": "Feature", "geometry": footprint, "properties": {}}],
            "location": {"type": "Point", "coordinates": [-48.80, -26.30]},
            "footprint": footprint,
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        instance = serializer.save()
        self.assertIsNotNone(instance.location)
        self.assertIsNotNone(instance.footprint)
        self.assertEqual(instance.territory_resolution["city_id"], str(city.pk))
        self.assertIsNotNone(instance.spatial_event_id)
        self.assertEqual(instance.spatial_event.evidence_kind, "LEGACY_UNCLASSIFIED")
        self.assertEqual(instance.spatial_event.current_revision.footprint, instance.footprint)
