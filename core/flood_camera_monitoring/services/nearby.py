from dataclasses import dataclass
from math import asin, cos, degrees, radians, sin, sqrt

from django.db.models import Case, F, FloatField, Q, When

from core.flood_camera_monitoring.infra.models import Camera


EARTH_RADIUS_M = 6_371_008.8


class MissingCameraCoordinates(ValueError):
    pass


@dataclass(frozen=True)
class NearbyCameraResult:
    camera: Camera
    distance_m: float


def camera_coordinates(camera: Camera) -> tuple[float, float] | None:
    """Return canonical coordinates without masking incomplete addresses."""

    if camera.address is not None:
        latitude = camera.address.latitude
        longitude = camera.address.longitude
    else:
        latitude = camera.latitude
        longitude = camera.longitude
    if latitude is None or longitude is None:
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return float(latitude), float(longitude)


def haversine_distance_m(origin, destination) -> float:
    origin_latitude, origin_longitude = map(radians, origin)
    destination_latitude, destination_longitude = map(radians, destination)
    latitude_delta = destination_latitude - origin_latitude
    longitude_delta = destination_longitude - origin_longitude
    value = (
        sin(latitude_delta / 2) ** 2
        + cos(origin_latitude)
        * cos(destination_latitude)
        * sin(longitude_delta / 2) ** 2
    )
    return EARTH_RADIUS_M * 2 * asin(min(1.0, sqrt(value)))


def find_nearby_cameras(*, origin, candidates, radius_m) -> list[NearbyCameraResult]:
    origin_coordinates = camera_coordinates(origin)
    if origin_coordinates is None:
        raise MissingCameraCoordinates

    latitude, longitude = origin_coordinates
    angular_radius = radius_m / EARTH_RADIUS_M
    latitude_delta = degrees(angular_radius)
    longitude_delta = degrees(
        angular_radius / max(abs(cos(radians(latitude))), 1e-12)
    )

    candidates = candidates.exclude(pk=origin.pk).exclude(
        status=Camera.CameraStatus.INACTIVE
    ).annotate(
        _nearby_latitude=Case(
            When(address__isnull=False, then=F("address__latitude")),
            default=F("latitude"),
            output_field=FloatField(),
        ),
        _nearby_longitude=Case(
            When(address__isnull=False, then=F("address__longitude")),
            default=F("longitude"),
            output_field=FloatField(),
        ),
    ).filter(
        _nearby_latitude__gte=latitude - latitude_delta,
        _nearby_latitude__lte=latitude + latitude_delta,
    )

    if longitude_delta < 180:
        minimum_longitude = longitude - longitude_delta
        maximum_longitude = longitude + longitude_delta
        if minimum_longitude < -180:
            candidates = candidates.filter(
                Q(_nearby_longitude__gte=minimum_longitude + 360)
                | Q(_nearby_longitude__lte=maximum_longitude)
            )
        elif maximum_longitude > 180:
            candidates = candidates.filter(
                Q(_nearby_longitude__gte=minimum_longitude)
                | Q(_nearby_longitude__lte=maximum_longitude - 360)
            )
        else:
            candidates = candidates.filter(
                _nearby_longitude__gte=minimum_longitude,
                _nearby_longitude__lte=maximum_longitude,
            )

    results = []
    for candidate in candidates:
        coordinates = camera_coordinates(candidate)
        if coordinates is None:
            continue
        distance_m = haversine_distance_m(origin_coordinates, coordinates)
        if distance_m <= radius_m:
            results.append(NearbyCameraResult(candidate, distance_m))
    results.sort(
        key=lambda result: (
            result.distance_m,
            (result.camera.description or "").casefold(),
            str(result.camera.pk),
        )
    )
    return results
