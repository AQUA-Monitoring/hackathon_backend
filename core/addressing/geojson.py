"""Validação e operações GeoJSON territoriais sem dependência de PostGIS."""
from __future__ import annotations

import json
from typing import Any

from shapely.geometry import Point, shape
from shapely.validation import explain_validity


def validate_territory_geometry(value: Any) -> dict:
    if not isinstance(value, dict) or value.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("A geometria territorial deve ser Polygon ou MultiPolygon")
    if "coordinates" not in value:
        raise ValueError("Geometria territorial sem coordenadas")
    try:
        geom = shape(value)
    except Exception as exc:
        raise ValueError("Coordenadas GeoJSON inválidas") from exc
    if geom.is_empty or not geom.is_valid:
        raise ValueError(f"Geometria territorial inválida: {explain_validity(geom)}")
    if geom.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("Tipo geométrico territorial não suportado")
    return value


def point_inside_geometry(longitude: float, latitude: float, geometry: dict | None) -> bool | None:
    if geometry is None:
        return None
    # GeoDjango entrega GEOSGeometry diretamente nas views; normalize para o
    # mesmo GeoJSON usado pelos endpoints e pela validação Shapely.
    if hasattr(geometry, "geojson"):
        geometry = json.loads(geometry.geojson)
    validate_territory_geometry(geometry)
    return bool(shape(geometry).covers(Point(float(longitude), float(latitude))))


def feature_collection(objects, *, kind: str) -> dict:
    features = []
    for obj in objects:
        geometry = getattr(obj, "geometry", None)
        if geometry is None:
            continue
        raw_geometry = json.loads(geometry.geojson) if hasattr(geometry, "geojson") else geometry
        city = getattr(obj, "city", None)
        city_name = city.name if hasattr(city, "name") else city
        city_id = getattr(obj, "city_ref_id", None)
        if kind == "city":
            city_id = obj.id
        dataset = getattr(obj, "geometry_dataset", None) if kind == "city" else getattr(obj, "dataset", None)
        features.append({
            "type": "Feature",
            "geometry": raw_geometry,
            "properties": {
                "id": str(obj.id),
                "name": obj.name,
                "type": kind,
                "city": city_name,
                "city_id": str(city_id) if city_id else None,
                "region_id": str(getattr(obj, "region_id", None)) if getattr(obj, "region_id", None) else None,
                "source_record_id": getattr(obj, "source_record_id", ""),
                "provenance": ({
                    "dataset_id": str(dataset.id),
                    "authority": dataset.authority,
                    "source_version": dataset.source_version,
                    "source_url": dataset.source_url,
                    "license": {"name": dataset.license_name, "url": dataset.license_url},
                } if dataset else None),
            },
        })
    return {"type": "FeatureCollection", "features": features}
