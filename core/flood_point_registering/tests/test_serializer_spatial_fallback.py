from django.test import TestCase

from core.addressing.infra.models import City, Neighborhood

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
