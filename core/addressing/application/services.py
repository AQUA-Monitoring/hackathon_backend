from typing import Iterable, Optional

from core.addressing.domain.repository import NeighborhoodRepository
from core.addressing.domain.entities import Neighborhood as DNeighborhood


def _neighborhood_to_feature(n: DNeighborhood) -> dict:
    geom = None
    props = {
        "id": n.id,
        "name": n.name,
        "city": n.city,
    }
    # A geometria canônica não é misturada com metadados legados.
    geom = getattr(n, "geometry", None)
    if hasattr(geom, "geojson"):
        import json
        geom = json.loads(geom.geojson)
    if geom is None and isinstance(n.props, dict):
        geom = n.props.get("geometry")
        # Merge remaining props, without overriding core fields
        for k, v in n.props.items():
            if k not in props:
                props[k] = v
    return {"type": "Feature", "geometry": geom, "properties": props}


def build_neighborhoods_feature_collection(
    repo: NeighborhoodRepository,
    *,
    all_flag: Optional[bool] = None,
    city: Optional[str] = None,
    region: Optional[str] = None,
) -> dict:
    # Select neighborhoods via repository
    neighborhoods: Iterable[DNeighborhood]
    if all_flag is True:
        # type: ignore[attr-defined]
        neighborhoods = repo.list_all()  # provided by our Django impl
    elif city and region:
        # type: ignore[attr-defined]
        neighborhoods = repo.list_by_city_and_region(
            city, region
        )  # provided by our Django impl
    elif city:
        neighborhoods = repo.list_by_city(city)
    else:
        # Default to list_all if no filters provided
        # type: ignore[attr-defined]
        neighborhoods = repo.list_all()

    features = [_neighborhood_to_feature(n) for n in neighborhoods]
    return {"type": "FeatureCollection", "features": features}
