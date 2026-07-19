from __future__ import annotations

import hashlib
import csv
import json
import unicodedata
from datetime import date
from pathlib import Path

from django.contrib.gis.geos import GEOSGeometry, MultiLineString, MultiPolygon, Point
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.validation import explain_validity, make_valid
from shapely.ops import transform

from core.addressing.infra.models import (
    AddressReference, City, GeodataDataset, Neighborhood, Region, RoadAxisSegment,
    RoadAxisSegmentNeighborhood, Street, StreetNeighborhood,
)


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold().split())


def geos_geometry(raw, source_crs: str, expected: set[str], *, repair=False):
    try:
        geom = shape(raw)
    except Exception as exc:
        raise CommandError("Geometria inválida: GeoJSON ilegível") from exc
    repair_audit = None
    if geom.is_empty:
        raise CommandError("Geometria inválida: geometria vazia")
    if not geom.is_valid:
        reason = explain_validity(geom)
        if not repair:
            raise CommandError(f"Geometria inválida: {reason}")
        original_type = geom.geom_type
        geom = make_valid(geom)
        repair_audit = {"reason": reason, "original_type": original_type, "result_type": geom.geom_type}
    if geom.geom_type not in expected:
        raise CommandError(f"Geometria inválida ou tipo inesperado: {geom.geom_type}")
    if source_crs.upper() != "EPSG:4326":
        transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
        geom = transform(transformer.transform, geom)
    if geom.is_empty or not geom.is_valid:
        raise CommandError(f"Geometria inválida após reprojeção: {explain_validity(geom)}")
    value = GEOSGeometry(json.dumps(mapping(geom)), srid=4326)
    if value.geom_type == "Polygon":
        value = MultiPolygon(value, srid=4326)
    elif value.geom_type == "LineString":
        value = MultiLineString(value, srid=4326)
    return value, repair_audit


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def iter_source_features(path: Path, options: dict):
    """Yield source features lazily; CSV rows are never accumulated in memory."""
    if path.suffix.casefold() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                try:
                    longitude = float(row[options["longitude_prop"]].replace(",", "."))
                    latitude = float(row[options["latitude_prop"]].replace(",", "."))
                except (KeyError, TypeError, ValueError) as exc:
                    raise CommandError("CSV sem coordenadas válidas") from exc
                yield row, {"type": "Point", "coordinates": [longitude, latitude]}
        return
    try:
        with path.open("r", encoding="utf-8") as source:
            data = json.load(source)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CommandError("GeoJSON ilegível") from exc
    if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise CommandError("Esperado GeoJSON FeatureCollection")
    for feature in data["features"]:
        yield feature.get("properties") or {}, feature.get("geometry")


def chunked(iterator, size: int):
    chunk = []
    for item in iterator:
        chunk.append(item)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


class Command(BaseCommand):
    help = "Importa uma edição oficial/licenciada de geodados de endereçamento."

    def add_arguments(self, parser):
        parser.add_argument("geojson_path")
        parser.add_argument("--city")
        parser.add_argument("--city-code")
        parser.add_argument("--kind", required=True, choices=[v for v, _ in GeodataDataset.Kind.choices])
        parser.add_argument("--authority", required=True)
        parser.add_argument("--title", required=True)
        parser.add_argument("--source-url", required=True)
        parser.add_argument("--license-name", required=True)
        parser.add_argument("--license-url", default="")
        parser.add_argument("--source-version", required=True)
        parser.add_argument("--published-at")
        parser.add_argument("--crs")
        parser.add_argument("--source-crs")
        parser.add_argument("--id-prop", default="id")
        parser.add_argument("--name-prop", default="name")
        parser.add_argument("--region-prop", default="region")
        parser.add_argument("--street-prop", default="street")
        parser.add_argument("--number-prop", default="number")
        parser.add_argument("--zipcode-prop", default="zipcode")
        parser.add_argument("--official-code-prop", default="official_code")
        parser.add_argument("--modifier-prop", default="modifier")
        parser.add_argument("--address-type-prop", default="address_type")
        parser.add_argument("--species-prop", default="species")
        parser.add_argument("--complement-prop", default="complement")
        parser.add_argument("--longitude-prop", default="longitude")
        parser.add_argument("--latitude-prop", default="latitude")
        parser.add_argument("--road-class-prop", default="road_class")
        parser.add_argument("--surface-prop", default="surface")
        parser.add_argument("--direction-prop", default="direction")
        parser.add_argument("--repair-geometries", action="store_true")
        parser.add_argument("--chunk-size", type=int, default=1000)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **o):
        path = Path(o["geojson_path"]).expanduser().resolve()
        if not path.is_file():
            raise CommandError("Arquivo GeoJSON/CSV não encontrado")
        if o["chunk_size"] <= 0 or o["chunk_size"] > 10000:
            raise CommandError("--chunk-size deve estar entre 1 e 10000")
        if not o.get("city_code") and not o.get("city"):
            raise CommandError("Informe --city-code (canônico) ou --city (compatibilidade)")
        if o.get("city_code"):
            city = City.objects.filter(official_code=o["city_code"].strip()).first()
        else:
            city = City.objects.filter(name__iexact=o["city"].strip()).first()
        if city is None:
            raise CommandError("Cidade deve existir antes da importação")
        source_crs = o.get("crs") or o.get("source_crs") or "EPSG:4326"
        digest = file_sha256(path)
        seen = set()
        expected = {
            GeodataDataset.Kind.CITY: {"Polygon", "MultiPolygon"}, GeodataDataset.Kind.REGION: {"Polygon", "MultiPolygon"},
            GeodataDataset.Kind.NEIGHBORHOOD: {"Polygon", "MultiPolygon"}, GeodataDataset.Kind.STREET: {"LineString", "MultiLineString"},
            GeodataDataset.Kind.ADDRESS: {"Point"},
        }[o["kind"]]
        report = {"validated": 0, "created": 0, "updated": 0, "inactivated": 0, "skipped": 0, "duplicates": 0, "errors": 0, "conflicts": 0, "spatial_links": 0, "unmatched": 0, "chunks": 0, "repairs": []}

        def parsed_features():
            for idx, (props, raw_geometry) in enumerate(iter_source_features(path, o), 1):
                source_id = str(props.get(o["id_prop"]) or "").strip()
                if not source_id or source_id in seen:
                    report["duplicates"] += 1
                    raise CommandError(f"Feature {idx}: ID oficial ausente ou duplicado")
                seen.add(source_id)
                geom, repair_audit = geos_geometry(raw_geometry, source_crs, expected, repair=o["repair_geometries"])
                if repair_audit:
                    report["repairs"].append({"feature": idx, "source_record_id": source_id, **repair_audit})
                if city.geometry and o["kind"] == GeodataDataset.Kind.ADDRESS and not city.geometry.covers(geom):
                    report["conflicts"] += 1
                    raise CommandError(f"Feature {idx}: ponto fora do limite municipal")
                report["validated"] += 1
                yield source_id, props, geom

        summary = {"sha256": digest, "dry_run": o["dry_run"], "report": report}
        if o["dry_run"]:
            for batch in chunked(parsed_features(), o["chunk_size"]):
                report["chunks"] += 1
            self.stdout.write(json.dumps(summary, ensure_ascii=False))
            return
        existing = GeodataDataset.objects.filter(city=city, kind=o["kind"], authority=o["authority"], sha256=digest).first()
        if existing and existing.status != GeodataDataset.Status.FAILED:
            report["skipped"] = existing.metadata.get("report", {}).get("validated", 0)
            self.stdout.write(json.dumps({**summary, "dataset_id": str(existing.id), "idempotent": True}))
            return
        dataset_values = {
            "city": city, "kind": o["kind"], "authority": o["authority"], "title": o["title"], "source_url": o["source_url"],
            "license_name": o["license_name"], "license_url": o["license_url"], "source_version": o["source_version"],
            "published_at": date.fromisoformat(o["published_at"]) if o["published_at"] else None,
            "retrieved_at": timezone.now(), "sha256": digest, "source_crs": source_crs, "status": GeodataDataset.Status.STAGED,
            "metadata": {"report": report},
        }
        if existing:
            for field, value in dataset_values.items():
                setattr(existing, field, value)
            existing.save()
            dataset = existing
        else:
            dataset = GeodataDataset.objects.create(**dataset_values)
        try:
            with transaction.atomic():
                previous = GeodataDataset.objects.select_for_update().filter(city=city, kind=o["kind"], authority=o["authority"], status="active")
                previous_ids = list(previous.values_list("id", flat=True))
                previous.update(status="superseded")
                if o["kind"] == GeodataDataset.Kind.REGION:
                    report["inactivated"] = Region.objects.filter(city_ref=city, dataset__authority=o["authority"], is_active=True).update(is_active=False)
                elif o["kind"] == GeodataDataset.Kind.NEIGHBORHOOD:
                    report["inactivated"] = Neighborhood.objects.filter(city_ref=city, dataset__authority=o["authority"], is_active=True).update(is_active=False)
                elif o["kind"] == GeodataDataset.Kind.STREET:
                    report["inactivated"] = Street.objects.filter(city=city, dataset__authority=o["authority"], is_active=True).update(is_active=False)
                    RoadAxisSegment.objects.filter(city=city, dataset__authority=o["authority"], is_active=True).update(is_active=False)
                elif o["kind"] == GeodataDataset.Kind.ADDRESS:
                    report["inactivated"] = AddressReference.objects.filter(city=city, dataset__authority=o["authority"], is_active=True).update(is_active=False)
                regions = {normalized(region.name): region for region in Region.objects.filter(city_ref=city, is_active=True)}
                neighborhoods = list(Neighborhood.objects.filter(city_ref=city, is_active=True).exclude(geometry=None))
                streets = {street.normalized_name: street for street in Street.objects.filter(city=city, is_active=True)}
                for batch in chunked(parsed_features(), o["chunk_size"]):
                    report["chunks"] += 1
                    if o["kind"] == GeodataDataset.Kind.CITY:
                        for source_id, props, geom in batch:
                            city.geometry, city.source_record_id, city.geometry_dataset = geom, source_id, dataset
                            city.official_code = city.official_code or str(props.get(o["official_code_prop"]) or "").strip()
                            city.normalized_name = normalized(city.name)
                            city.save(update_fields=["geometry", "source_record_id", "geometry_dataset", "official_code", "normalized_name"])
                    elif o["kind"] == GeodataDataset.Kind.REGION:
                        objects = [Region(city=city.name, city_ref=city, dataset=dataset, source_record_id=source_id, official_code=str(props.get(o["official_code_prop"]) or "").strip(), name=(name := str(props.get(o["name_prop"]) or "").strip()), normalized_name=normalized(name), geometry=geom, props=props) for source_id, props, geom in batch]
                        Region.objects.bulk_create(objects, batch_size=o["chunk_size"])
                    elif o["kind"] == GeodataDataset.Kind.NEIGHBORHOOD:
                        objects = []
                        for source_id, props, geom in batch:
                            name = str(props.get(o["name_prop"]) or "").strip()
                            region = regions.get(normalized(str(props.get(o["region_prop"]) or "")))
                            objects.append(Neighborhood(city=city.name, city_ref=city, dataset=dataset, source_record_id=source_id, official_code=str(props.get(o["official_code_prop"]) or "").strip(), name=name, normalized_name=normalized(name), region=region, geometry=geom, props=props))
                        Neighborhood.objects.bulk_create(objects, batch_size=o["chunk_size"])
                    elif o["kind"] == GeodataDataset.Kind.STREET:
                        objects = [Street(city=city, dataset=dataset, source_record_id=source_id, name=(name := str(props.get(o["name_prop"]) or props.get(o["street_prop"]) or "").strip()), normalized_name=normalized(name), geometry=geom, properties=props) for source_id, props, geom in batch]
                        Street.objects.bulk_create(objects, batch_size=o["chunk_size"])
                        links = [StreetNeighborhood(street=street, neighborhood=neighborhood) for street in objects for neighborhood in neighborhoods if neighborhood.geometry.intersects(street.geometry)]
                        StreetNeighborhood.objects.bulk_create(links, batch_size=o["chunk_size"], ignore_conflicts=True)
                        segments = [RoadAxisSegment(
                            city=city, street=street, dataset=dataset,
                            source_record_id=street.source_record_id, geometry=street.geometry,
                            road_class=str(street.properties.get(o["road_class_prop"]) or ""),
                            surface=str(street.properties.get(o["surface_prop"]) or ""),
                            direction=str(street.properties.get(o["direction_prop"]) or ""),
                            properties=street.properties,
                        ) for street in objects]
                        RoadAxisSegment.objects.bulk_create(segments, batch_size=o["chunk_size"])
                        segment_links = [RoadAxisSegmentNeighborhood(segment=segment, neighborhood=neighborhood) for segment in segments for neighborhood in neighborhoods if neighborhood.geometry.intersects(segment.geometry)]
                        RoadAxisSegmentNeighborhood.objects.bulk_create(segment_links, batch_size=o["chunk_size"], ignore_conflicts=True)
                        report["spatial_links"] += len(links) + len(segment_links)
                    else:
                        objects = []
                        for source_id, props, point in batch:
                            street_name = str(props.get(o["street_prop"]) or "").strip()
                            neighborhood = next((item for item in neighborhoods if item.geometry.covers(point)), None)
                            if neighborhood is None:
                                report["unmatched"] += 1
                            objects.append(AddressReference(city=city, neighborhood=neighborhood, dataset=dataset, source_record_id=source_id, street=streets.get(normalized(street_name)), street_name=street_name, number=str(props.get(o["number_prop"]) or ""), modifier=str(props.get(o["modifier_prop"]) or ""), address_type=str(props.get(o["address_type_prop"]) or ""), species=str(props.get(o["species_prop"]) or ""), complement=str(props.get(o["complement_prop"]) or ""), zipcode=str(props.get(o["zipcode_prop"]) or ""), location=point, properties=props))
                        AddressReference.objects.bulk_create(objects, batch_size=o["chunk_size"])
                    report["created"] += len(batch)
                dataset.status = GeodataDataset.Status.ACTIVE
                dataset.metadata = {"report": report, "superseded_dataset_ids": [str(value) for value in previous_ids]}
                dataset.save(update_fields=["status", "metadata", "updated_at"])
        except Exception:
            report["errors"] += 1
            dataset.status = GeodataDataset.Status.FAILED
            dataset.metadata = {"report": report}
            dataset.save(update_fields=["status", "metadata", "updated_at"])
            raise
        self.stdout.write(json.dumps({**summary, "dataset_id": str(dataset.id), "idempotent": False, "report": report}))
