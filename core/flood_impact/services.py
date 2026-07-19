from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
import hashlib

from django.contrib.gis.geos import LineString, MultiLineString
from django.db import transaction
from django.utils import timezone

from core.addressing.infra.models import GeodataDataset, RoadAxisSegment
from core.flood_impact.models import (
    FloodSpatialEventRevision,
    RoadFloodImpact,
    RoadFloodImpactRun,
    RoadImpactHotspot,
)


def _line_parts(geometry):
    if geometry.empty:
        return []
    if geometry.geom_type == "LineString":
        return [geometry]
    if geometry.geom_type == "MultiLineString":
        return list(geometry)
    if geometry.geom_type == "GeometryCollection":
        parts = []
        for child in geometry:
            parts.extend(_line_parts(child))
        return parts
    return []


def _length_m(geometry) -> float:
    projected = geometry.clone()
    projected.transform(31982)
    return float(projected.length)


@dataclass(frozen=True)
class ImpactCalculationResult:
    run: RoadFloodImpactRun
    reused: bool


class PostGISRoadImpactService:
    """Idempotently derives road impacts from an explicit polygon footprint."""

    algorithm_version = "road-intersection-v1"

    @transaction.atomic
    def calculate(self, *, revision: FloodSpatialEventRevision, road_dataset: GeodataDataset) -> ImpactCalculationResult:
        input_hash = hashlib.sha256(
            b"|".join([
                bytes(revision.footprint.ewkb) if revision.footprint else b"no-footprint",
                str(revision.id).encode(), road_dataset.sha256.encode(), self.algorithm_version.encode(),
            ])
        ).hexdigest()
        run, created = RoadFloodImpactRun.objects.select_for_update().get_or_create(
            revision=revision,
            road_dataset=road_dataset,
            algorithm_version=self.algorithm_version,
            defaults={"status": RoadFloodImpactRun.Status.RUNNING, "started_at": timezone.now(), "input_hash": input_hash},
        )
        if not created and run.status == RoadFloodImpactRun.Status.COMPLETED:
            return ImpactCalculationResult(run=run, reused=True)

        run.impacts.all().delete()
        run.hotspots.all().delete()
        run.status = RoadFloodImpactRun.Status.RUNNING
        run.started_at = timezone.now()
        run.finished_at = None
        run.report = {}
        run.input_hash = input_hash
        run.save(update_fields=["status", "started_at", "finished_at", "report", "input_hash", "updated_at"])

        if revision.footprint is None:
            run.status = RoadFloodImpactRun.Status.COMPLETED
            run.finished_at = timezone.now()
            run.report = {"candidate_segments": 0, "impacted_segments": 0, "touches": 0, "reason": "footprint_required"}
            run.save(update_fields=["status", "finished_at", "report", "updated_at"])
            return ImpactCalculationResult(run=run, reused=False)

        candidates = RoadAxisSegment.objects.filter(
            dataset=road_dataset,
            city=revision.event.city,
            is_active=True,
            geometry__intersects=revision.footprint,
        ).select_related("street")
        impacts = []
        touches = 0
        total_length = 0.0
        for segment in candidates.iterator():
            intersection = segment.geometry.intersection(revision.footprint)
            parts = _line_parts(intersection)
            if not parts:
                touches += 1
                continue
            lines = [LineString(part.coords, srid=4326) for part in parts if len(part.coords) >= 2]
            if not lines:
                touches += 1
                continue
            linear = MultiLineString(*lines, srid=4326)
            length_m = _length_m(linear)
            segment_length_m = _length_m(segment.geometry)
            if length_m <= 0 or segment_length_m <= 0:
                continue
            total_length += length_m
            impacts.append(RoadFloodImpact(
                run=run,
                segment=segment,
                intersection=linear,
                length_m=length_m,
                segment_fraction=min(1.0, length_m / segment_length_m),
                relation=(RoadFloodImpact.Relation.WITHIN if revision.footprint.covers(segment.geometry) else RoadFloodImpact.Relation.CROSSES),
                evidence_kind=revision.event.evidence_kind,
                evidence_status=revision.status,
            ))
        RoadFloodImpact.objects.bulk_create(impacts, batch_size=1000)
        aggregates = defaultdict(lambda: {"length": 0.0, "segments": set(), "geometries": [], "label": ""})
        for impact in impacts:
            centroid = impact.intersection.centroid
            keys = [(RoadImpactHotspot.Dimension.ROAD_SEGMENT, str(impact.segment_id), impact.segment.street.name if impact.segment.street_id else "")]
            if impact.segment.street_id:
                keys.append((RoadImpactHotspot.Dimension.STREET, str(impact.segment.street_id), impact.segment.street.name))
            grid_key = f"{round(centroid.x, 3):.3f},{round(centroid.y, 3):.3f}"
            keys.append((RoadImpactHotspot.Dimension.GRID_CELL, grid_key, grid_key))
            for link in impact.segment.neighborhood_links.select_related("neighborhood").all():
                keys.append((RoadImpactHotspot.Dimension.NEIGHBORHOOD, str(link.neighborhood_id), link.neighborhood.name))
            for dimension, key, label in keys:
                value = aggregates[(dimension, key)]
                value["length"] += impact.length_m
                value["segments"].add(impact.segment_id)
                value["geometries"].append(impact.intersection)
                value["label"] = label
        hotspots = []
        for rank, ((dimension, key), value) in enumerate(sorted(aggregates.items(), key=lambda item: -item[1]["length"]), 1):
            merged = value["geometries"][0]
            for geometry in value["geometries"][1:]:
                merged = merged.union(geometry)
            hotspots.append(RoadImpactHotspot(
                run=run, location=merged.centroid, impacted_length_m=value["length"],
                segment_count=len(value["segments"]), rank=rank, dimension=dimension,
                dimension_key=key, label=value["label"],
            ))
        RoadImpactHotspot.objects.bulk_create(hotspots, batch_size=1000)
        run.status = RoadFloodImpactRun.Status.COMPLETED
        run.finished_at = timezone.now()
        run.report = {
            "candidate_segments": len(impacts) + touches,
            "impacted_segments": len(impacts),
            "touches": touches,
            "impacted_length_m": total_length,
        }
        run.save(update_fields=["status", "finished_at", "report", "updated_at"])
        return ImpactCalculationResult(run=run, reused=False)
