from django.contrib.gis.geos import LineString, MultiLineString, MultiPolygon, Point, Polygon
from django.test import TestCase
from django.utils import timezone

from core.addressing.models import City, GeodataDataset, RoadAxisSegment, Street
from core.flood_impact.models import FloodSpatialEvent, FloodSpatialEventRevision, RoadFloodImpact
from core.flood_impact.services import PostGISRoadImpactService


class RoadImpactServiceTests(TestCase):
    def setUp(self):
        self.city = City.objects.create(name="Cidade Impacto", geometry=MultiPolygon(Polygon(((-2, -2), (3, -2), (3, 3), (-2, 3), (-2, -2))), srid=4326))
        self.dataset = GeodataDataset.objects.create(city=self.city, kind="street", authority="Teste", title="Eixos", source_url="https://example.test", license_name="Teste", source_version="1", retrieved_at=timezone.now(), sha256="a" * 64, source_crs="EPSG:4326", status="active")
        street = Street.objects.create(city=self.city, dataset=self.dataset, source_record_id="street-1", name="Rua Um", normalized_name="rua um", geometry=MultiLineString(LineString((-1, .5), (2, .5)), srid=4326))
        self.segment = RoadAxisSegment.objects.create(city=self.city, street=street, dataset=self.dataset, source_record_id="segment-1", geometry=street.geometry)
        self.event = FloodSpatialEvent.objects.create(city=self.city, evidence_kind="FORECAST", source_type="test", source_id="forecast-1")

    def revision(self, footprint):
        revision = FloodSpatialEventRevision.objects.create(event=self.event, revision=1, status="ACTIVE", footprint=footprint, valid_from=timezone.now(), geometry_method="PROVIDED", justification="teste", source_revision="1")
        self.event.current_revision = revision
        self.event.save(update_fields=["current_revision"])
        return revision

    def test_intersection_is_linear_and_idempotent(self):
        footprint = MultiPolygon(Polygon(((0, 0), (1, 0), (1, 1), (0, 1), (0, 0))), srid=4326)
        revision = self.revision(footprint)
        first = PostGISRoadImpactService().calculate(revision=revision, road_dataset=self.dataset)
        second = PostGISRoadImpactService().calculate(revision=revision, road_dataset=self.dataset)
        impact = RoadFloodImpact.objects.get()
        self.assertGreater(impact.length_m, 0)
        self.assertEqual(impact.intersection.geom_type, "MultiLineString")
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(RoadFloodImpact.objects.count(), 1)

    def test_event_without_footprint_does_not_impact_roads(self):
        result = PostGISRoadImpactService().calculate(revision=self.revision(None), road_dataset=self.dataset)
        self.assertEqual(result.run.report["reason"], "footprint_required")
        self.assertEqual(RoadFloodImpact.objects.count(), 0)

    def test_point_touch_is_reported_but_not_an_affected_length(self):
        footprint = MultiPolygon(Polygon(((2, .5), (2.5, .5), (2.5, 1), (2, 1), (2, .5))), srid=4326)
        result = PostGISRoadImpactService().calculate(revision=self.revision(footprint), road_dataset=self.dataset)
        self.assertEqual(result.run.report["touches"], 1)
        self.assertEqual(RoadFloodImpact.objects.count(), 0)
