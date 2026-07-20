"""Persistência do contexto territorial de metadados de uma câmera.

Este serviço não acessa stream, OpenCV ou modelo de inferência.
"""

from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.contrib.gis.db.models.functions import Distance

from core.addressing.services import TerritoryResolver
from core.addressing.models import AddressReference, RoadAxisSegment


def apply_camera_territorial_context(camera, *, latitude: float, longitude: float):
    point = Point(float(longitude), float(latitude), srid=4326)
    resolution = TerritoryResolver().resolve_point(point)
    address_reference = AddressReference.objects.filter(
        city=resolution.city, is_active=True, location__distance_lte=(point, D(m=200))
    ).annotate(_distance=Distance("location", point)).order_by("_distance", "id").first()
    road_segment = RoadAxisSegment.objects.filter(
        city=resolution.city, is_active=True, geometry__distance_lte=(point, D(m=200))
    ).annotate(_distance=Distance("geometry", point)).order_by("_distance", "id").first()
    camera.city = resolution.city
    camera.region = resolution.region
    camera.neighborhood = resolution.neighborhood or camera.neighborhood
    camera.street = address_reference.street if address_reference and address_reference.street_id else (road_segment.street if road_segment else None)
    camera.road_segment = road_segment
    camera.address_reference = address_reference
    camera.territory_resolution = {
        "method": resolution.method,
        "point": {"type": "Point", "coordinates": [point.x, point.y]},
        "city_id": str(resolution.city_id) if hasattr(resolution, "city_id") else str(resolution.city.id),
        "region_id": str(resolution.region.id) if resolution.region else None,
        "neighborhood_id": str(resolution.neighborhood.id) if resolution.neighborhood else None,
        "max_distance_m": 200,
    }
    return camera
