from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Address:
    """Address aggregate root (value-object style).

    Other contexts should reference Address by its ID only (string/UUID),
    avoiding direct coupling between bounded contexts.
    """

    id: str
    street: str
    number: Optional[str]
    neighborhood: Optional[str]
    city: str
    state: Optional[str]
    country: str
    zipcode: Optional[str]
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    neighborhood_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.street or not self.city or not self.country:
            raise ValueError("street, city and country are required")
        if self.latitude is not None and not (-90.0 <= self.latitude <= 90.0):
            raise ValueError("latitude must be between -90 and 90")
        if self.longitude is not None and not (-180.0 <= self.longitude <= 180.0):
            raise ValueError("longitude must be between -180 and 180")


@dataclass(frozen=True)
class Region:
    id: str
    name: str
    city: str
    props: dict | None = None
    geometry: dict | None = None  # GeoJSON Polygon/MultiPolygon
    bbox_min_lon: float | None = None
    bbox_min_lat: float | None = None
    bbox_max_lon: float | None = None
    bbox_max_lat: float | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.city:
            raise ValueError("name and city are required")


@dataclass(frozen=True)
class Neighborhood:
    id: str
    name: str
    city: str
    region_id: str
    props: dict | None = None
    geometry: dict | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.city:
            raise ValueError("name and city are required")
