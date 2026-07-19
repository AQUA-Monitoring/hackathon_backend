from django.test import SimpleTestCase

from core.addressing.geojson import point_inside_geometry, validate_territory_geometry


class GeoJSONTerritoryTests(SimpleTestCase):
    geometry = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
    }

    def test_accepts_valid_polygon_and_covers_boundary(self):
        self.assertEqual(validate_territory_geometry(self.geometry), self.geometry)
        self.assertTrue(point_inside_geometry(0.5, 0.5, self.geometry))
        self.assertTrue(point_inside_geometry(0, 0, self.geometry))
        self.assertFalse(point_inside_geometry(2, 2, self.geometry))

    def test_rejects_unsupported_geometry(self):
        with self.assertRaises(ValueError):
            validate_territory_geometry({"type": "Point", "coordinates": [0, 0]})

    def test_missing_geometry_is_unknown(self):
        self.assertIsNone(point_inside_geometry(0, 0, None))
