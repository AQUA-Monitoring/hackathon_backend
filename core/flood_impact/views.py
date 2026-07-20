import json
import uuid
from collections import defaultdict

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.db import transaction
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from core.addressing.models import City, GeodataDataset
from core.flood_impact.models import FloodSpatialEvent, FloodSpatialEventRevision, RoadFloodImpact, RoadFloodImpactRun, RoadImpactHotspot
from core.flood_impact.services import PostGISRoadImpactService, affected_territory_snapshot
from core.flood_camera_monitoring.services.nearby import (
    camera_coordinates,
    haversine_distance_m,
)
from core.flood_camera_monitoring.infra.models import Camera


def _is_admin(user):
    return bool(user and user.is_authenticated and (getattr(user, "is_staff", False) or getattr(user, "type", None) == "admin"))


def _geometry(raw, expected):
    if raw is None:
        return None
    value = GEOSGeometry(json.dumps(raw) if isinstance(raw, dict) else raw, srid=4326)
    if value.geom_type == "Polygon" and expected == "MultiPolygon":
        value = MultiPolygon(value, srid=4326)
    if value.geom_type != expected:
        raise ValueError(f"geometry must be {expected}")
    if not value.valid:
        raise ValueError("geometry must be valid")
    return value


class FloodImpactPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = "page_size"
    max_page_size = 500


class FloodImpactEventViewSet(viewsets.ViewSet):
    pagination_class = FloodImpactPagination

    def get_permissions(self):
        return [permissions.IsAuthenticated()]

    def _error(self, code, detail, http_status=status.HTTP_400_BAD_REQUEST):
        return Response({"error": {"code": code, "detail": detail, "fields": {}}}, status=http_status)

    def _paginate(self, request, queryset, mapper):
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        return paginator.get_paginated_response([mapper(item) for item in page])

    @staticmethod
    def _event_payload(event):
        revision = event.current_revision
        payload = {
            "id": str(event.id), "city_id": str(event.city_id),
            "city": str(event.city_id), "city_name": event.city.name,
            "neighborhoods": [],
            "evidence_kind": event.evidence_kind,
            "source": {"type": event.source_type, "id": event.source_id},
            "revision": ({
                "id": str(revision.id), "number": revision.revision, "status": revision.status,
                "confidence": revision.confidence, "geometry_method": revision.geometry_method,
                "valid_from": revision.valid_from.isoformat(),
                "valid_until": revision.valid_until.isoformat() if revision.valid_until else None,
                "location": json.loads(revision.location.geojson) if revision.location else None,
                "footprint": json.loads(revision.footprint.geojson) if revision.footprint else None,
                "affected_regions": revision.affected_regions,
                "affected_streets": revision.affected_streets,
            } if revision else None),
        }
        if revision:
            payload.update({
                "status": revision.status,
                "location": json.loads(revision.location.geojson) if revision.location else None,
                "footprint": json.loads(revision.footprint.geojson) if revision.footprint else None,
                "geometry_method": revision.geometry_method,
                "confidence": revision.confidence,
                "valid_from": revision.valid_from.isoformat(),
                "valid_until": revision.valid_until.isoformat() if revision.valid_until else None,
                "current_revision": revision.revision,
                "metadata": revision.properties,
                "affected_regions": revision.affected_regions,
                "affected_streets": revision.affected_streets,
            })
        return payload

    def list(self, request):
        qs = FloodSpatialEvent.objects.select_related("city", "current_revision").order_by("-created_at")
        if request.query_params.get("city_id"):
            qs = qs.filter(city_id=request.query_params["city_id"])
        if request.query_params.get("evidence_kind"):
            value = request.query_params["evidence_kind"]
            if value not in FloodSpatialEvent.EvidenceKind.values:
                return self._error("invalid_filter", "evidence_kind inválido.")
            qs = qs.filter(evidence_kind=value)
        if request.query_params.get("status"):
            value = request.query_params["status"]
            if value not in FloodSpatialEventRevision.Status.values:
                return self._error("invalid_filter", "status inválido.")
            qs = qs.filter(current_revision__status=value)
        if request.query_params.get("valid_at"):
            instant = parse_datetime(request.query_params["valid_at"])
            if instant is None:
                return self._error("invalid_filter", "valid_at deve ser ISO-8601.")
            qs = qs.filter(current_revision__valid_from__lte=instant).filter(Q(current_revision__valid_until__isnull=True) | Q(current_revision__valid_until__gt=instant))
        if request.query_params.get("bbox"):
            try:
                west, south, east, north = [float(item) for item in request.query_params["bbox"].split(",")]
                from django.contrib.gis.geos import Polygon
                bbox = Polygon.from_bbox((west, south, east, north))
            except (TypeError, ValueError):
                return self._error("invalid_filter", "bbox deve ser west,south,east,north.")
            qs = qs.filter(Q(current_revision__footprint__intersects=bbox) | Q(current_revision__location__intersects=bbox))
        return self._paginate(request, qs, self._event_payload)

    def retrieve(self, request, pk=None):
        event = FloodSpatialEvent.objects.select_related("city", "current_revision").filter(pk=pk).first()
        return Response(self._event_payload(event)) if event else self._error("not_found", "Evento não encontrado.", status.HTTP_404_NOT_FOUND)

    @transaction.atomic
    def create(self, request):
        if not _is_admin(request.user):
            return self._error("forbidden", "Acesso administrativo obrigatório.", status.HTTP_403_FORBIDDEN)
        try:
            city = City.objects.get(pk=request.data.get("city_id") or request.data.get("city"))
            evidence_kind = request.data["evidence_kind"]
            if evidence_kind not in FloodSpatialEvent.EvidenceKind.values:
                raise ValueError("evidence_kind invalid")
            source = request.data.get("source")
            if not isinstance(source, dict):
                source = {"type": str(source or "manual"), "id": str(request.data.get("source_id") or uuid.uuid4())}
            revision_data = request.data.get("revision") or request.data
            valid_from = parse_datetime(revision_data["valid_from"])
            if valid_from is None:
                raise ValueError("valid_from invalid")
            valid_until = parse_datetime(revision_data.get("valid_until")) if revision_data.get("valid_until") else None
            if valid_until and valid_until <= valid_from:
                raise ValueError("valid_until invalid")
            confidence = revision_data.get("confidence")
            if confidence is not None and not 0 <= float(confidence) <= 1:
                raise ValueError("confidence invalid")
            location = _geometry(revision_data.get("location"), "Point")
            footprint = _geometry(revision_data.get("footprint"), "MultiPolygon")
            if footprint and city.geometry and not city.geometry.covers(footprint):
                raise ValueError("footprint outside city")
            method = revision_data["geometry_method"]
            if method not in FloodSpatialEventRevision.GeometryMethod.values:
                raise ValueError("geometry_method invalid")
            justification = str(revision_data.get("justification") or "Criação manual da mancha operacional.")
            source_revision = str(revision_data.get("source_revision") or "1")
        except (KeyError, TypeError, ValueError, City.DoesNotExist) as exc:
            return self._error("invalid_input", str(exc))
        event = FloodSpatialEvent.objects.create(city=city, evidence_kind=evidence_kind, source_type=str(source["type"]), source_id=str(source["id"]))
        affected_territory = affected_territory_snapshot(city=city, location=location, footprint=footprint)
        revision = FloodSpatialEventRevision.objects.create(
            event=event, revision=1, status=FloodSpatialEventRevision.Status.DRAFT,
            location=location, footprint=footprint, confidence=confidence, valid_from=valid_from, valid_until=valid_until,
            geometry_method=method, source_version=revision_data.get("source_version", ""),
            properties=revision_data.get("properties", revision_data.get("metadata", {})),
            affected_regions=affected_territory["affected_regions"],
            affected_streets=affected_territory["affected_streets"],
            author=request.user, justification=justification, source_revision=source_revision,
        )
        event.current_revision = revision
        event.save(update_fields=["current_revision", "updated_at"])
        return Response(self._event_payload(event), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="revisions")
    @transaction.atomic
    def revisions(self, request, pk=None):
        if not _is_admin(request.user):
            return self._error("forbidden", "Acesso administrativo obrigatório.", status.HTTP_403_FORBIDDEN)
        event = FloodSpatialEvent.objects.select_for_update().filter(pk=pk).first()
        if event is None:
            return self._error("not_found", "Evento não encontrado.", status.HTTP_404_NOT_FOUND)
        payload = request.data
        try:
            current = event.current_revision
            valid_from_raw = payload.get("valid_from") or (current.valid_from.isoformat() if current else None)
            valid_from = parse_datetime(valid_from_raw) if valid_from_raw else None
            if valid_from is None: raise ValueError("valid_from invalid")
            valid_until_raw = payload.get("valid_until") or (current.valid_until.isoformat() if current and current.valid_until else None)
            valid_until = parse_datetime(valid_until_raw) if valid_until_raw else None
            footprint = _geometry(payload.get("footprint"), "MultiPolygon")
            if footprint and event.city.geometry and not event.city.geometry.covers(footprint): raise ValueError("footprint outside city")
            location = _geometry(payload.get("location"), "Point") if "location" in payload else (current.location if current else None)
            method = payload.get("geometry_method") or (current.geometry_method if current else None)
            if method not in FloodSpatialEventRevision.GeometryMethod.values: raise ValueError("geometry_method invalid")
            justification = str(payload["justification"])
            source_revision = str(payload.get("source_revision") or (current.revision if current else "1"))
        except (KeyError, TypeError, ValueError) as exc:
            return self._error("invalid_input", str(exc))
        number = (event.revisions.order_by("-revision").values_list("revision", flat=True).first() or 0) + 1
        if event.current_revision and event.current_revision.status == FloodSpatialEventRevision.Status.ACTIVE:
            event.current_revision.status = FloodSpatialEventRevision.Status.SUPERSEDED
            event.current_revision.save(update_fields=["status", "updated_at"])
        affected_territory = affected_territory_snapshot(city=event.city, location=location, footprint=footprint)
        revision = FloodSpatialEventRevision.objects.create(
            event=event, revision=number, status=FloodSpatialEventRevision.Status.DRAFT, location=location, footprint=footprint,
            confidence=payload.get("confidence", current.confidence if current else None), valid_from=valid_from, valid_until=valid_until,
            geometry_method=method, source_version=payload.get("source_version", current.source_version if current else ""),
            properties=payload.get("properties", current.properties if current else {}),
            affected_regions=affected_territory["affected_regions"],
            affected_streets=affected_territory["affected_streets"],
            author=request.user, justification=justification, source_revision=source_revision,
        )
        event.current_revision = revision
        event.save(update_fields=["current_revision", "updated_at"])
        return Response(self._event_payload(event), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="recalculate")
    def recalculate(self, request, pk=None):
        if not _is_admin(request.user):
            return self._error("forbidden", "Acesso administrativo obrigatório.", status.HTTP_403_FORBIDDEN)
        event = FloodSpatialEvent.objects.select_related("current_revision").filter(pk=pk).first()
        if not event or not event.current_revision:
            return self._error("not_found", "Evento ou revisão não encontrado.", status.HTTP_404_NOT_FOUND)
        if event.city.geometry is None:
            return self._error("territory_unresolved", "A cidade não possui limite territorial validado.", status.HTTP_409_CONFLICT)
        if event.current_revision.footprint is None or not event.city.geometry.covers(event.current_revision.footprint):
            return self._error("invalid_geometry", "A mancha deve estar integralmente dentro do município.", status.HTTP_422_UNPROCESSABLE_ENTITY)
        datasets = GeodataDataset.objects.filter(kind=GeodataDataset.Kind.STREET, city=event.city)
        dataset_id = request.data.get("road_dataset_id")
        dataset = datasets.filter(pk=dataset_id).first() if dataset_id else datasets.filter(status=GeodataDataset.Status.ACTIVE).order_by("-retrieved_at").first()
        if dataset is None:
            return self._error("invalid_input", "road_dataset_id deve identificar uma malha viária.")
        result = PostGISRoadImpactService().calculate(revision=event.current_revision, road_dataset=dataset)
        return Response({"run_id": str(result.run.id), "status": result.run.status, "reused": result.reused, "report": result.run.report})

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        if not _is_admin(request.user): return self._error("forbidden", "Acesso administrativo obrigatório.", status.HTTP_403_FORBIDDEN)
        event = FloodSpatialEvent.objects.select_related("current_revision").filter(pk=pk).first()
        if not event or not event.current_revision: return self._error("not_found", "Evento não encontrado.", status.HTTP_404_NOT_FOUND)
        if event.city.geometry is None:
            return self._error("territory_unresolved", "A cidade não possui limite territorial validado.", status.HTTP_409_CONFLICT)
        if event.current_revision.footprint is None or not event.city.geometry.covers(event.current_revision.footprint):
            return self._error("invalid_geometry", "A mancha deve estar integralmente dentro do município.", status.HTTP_422_UNPROCESSABLE_ENTITY)
        event.current_revision.status = FloodSpatialEventRevision.Status.ACTIVE
        event.current_revision.save(update_fields=["status", "updated_at"])
        return Response(self._event_payload(event))

    @action(detail=True, methods=["post"], url_path="revoke")
    def revoke(self, request, pk=None):
        if not _is_admin(request.user): return self._error("forbidden", "Acesso administrativo obrigatório.", status.HTTP_403_FORBIDDEN)
        event = FloodSpatialEvent.objects.select_related("current_revision").filter(pk=pk).first()
        if not event or not event.current_revision: return self._error("not_found", "Evento não encontrado.", status.HTTP_404_NOT_FOUND)
        event.current_revision.status = FloodSpatialEventRevision.Status.REVOKED
        event.current_revision.save(update_fields=["status", "updated_at"])
        return Response(self._event_payload(event))

    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, pk=None):
        event = FloodSpatialEvent.objects.filter(pk=pk).first()
        if event is None: return self._error("not_found", "Evento não encontrado.", status.HTTP_404_NOT_FOUND)
        revisions = event.revisions.prefetch_related("impact_runs").order_by("revision")
        return Response({"event_id": str(event.id), "revisions": [{
            "id": str(revision.id), "number": revision.revision, "status": revision.status,
            "author_id": str(revision.author_id) if revision.author_id else None,
            "justification": revision.justification, "source_revision": revision.source_revision,
            "affected_regions": revision.affected_regions,
            "affected_streets": revision.affected_streets,
            "runs": [{"id": str(run.id), "status": run.status, "input_hash": run.input_hash, "algorithm_version": run.algorithm_version} for run in revision.impact_runs.all()],
        } for revision in revisions]})

    def _completed_run(self, event):
        if event.current_revision_id is None: return None
        return RoadFloodImpactRun.objects.filter(revision_id=event.current_revision_id, status=RoadFloodImpactRun.Status.COMPLETED).order_by("-finished_at").first()

    @action(detail=True, methods=["get"], url_path="roads")
    def roads(self, request, pk=None):
        event = FloodSpatialEvent.objects.select_related("current_revision").filter(pk=pk).first()
        if event is None: return self._error("not_found", "Evento não encontrado.", status.HTTP_404_NOT_FOUND)
        run = self._completed_run(event)
        qs = run.impacts.select_related("segment", "segment__street").order_by("-length_m") if run else RoadFloodImpact.objects.none()
        try: minimum = float(request.query_params.get("min_length_m", 0))
        except ValueError: return self._error("invalid_filter", "min_length_m inválido.")
        if run: qs = qs.filter(length_m__gte=minimum)
        return self._paginate(request, qs, lambda impact: {
            "id": str(impact.id), "run_id": str(impact.run_id), "segment_id": str(impact.segment_id),
            "road_axis_segment": str(impact.segment_id),
            "street": ({"id": str(impact.segment.street_id), "name": impact.segment.street.name} if impact.segment.street_id else None),
            "street_id": str(impact.segment.street_id) if impact.segment.street_id else None,
            "street_name": impact.segment.street.name if impact.segment.street_id else None,
            "intersection": json.loads(impact.intersection.geojson), "length_m": impact.length_m,
            "affected_length_m": impact.length_m,
            "segment_fraction": impact.segment_fraction, "relation": impact.relation,
            "evidence_kind": impact.evidence_kind, "evidence_status": impact.evidence_status,
        })

    @action(detail=True, methods=["get"], url_path="hotspots")
    def hotspots(self, request, pk=None):
        event = FloodSpatialEvent.objects.select_related("current_revision").filter(pk=pk).first()
        if event is None: return self._error("not_found", "Evento não encontrado.", status.HTTP_404_NOT_FOUND)
        run = self._completed_run(event)
        qs = run.hotspots.order_by("rank") if run else RoadImpactHotspot.objects.none()
        return self._paginate(request, qs, lambda hotspot: {
            "id": str(hotspot.id), "run_id": str(hotspot.run_id), "rank": hotspot.rank,
            "location": json.loads(hotspot.location.geojson), "impacted_length_m": hotspot.impacted_length_m,
            "segment_count": hotspot.segment_count, "dimension": hotspot.dimension,
            "dimension_key": hotspot.dimension_key, "label": hotspot.label,
        })


class RoadImpactHotspotViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        qs = RoadImpactHotspot.objects.select_related("run__revision__event").filter(
            run__status=RoadFloodImpactRun.Status.COMPLETED,
            run__revision__status=FloodSpatialEventRevision.Status.ACTIVE,
        ).order_by("-run__revision__valid_from", "rank")
        if request.query_params.get("city_id"): qs = qs.filter(run__revision__event__city_id=request.query_params["city_id"])
        if request.query_params.get("dimension"): qs = qs.filter(dimension=request.query_params["dimension"])
        period_start = request.query_params.get("period_start") or request.query_params.get("from")
        period_end = request.query_params.get("period_end") or request.query_params.get("until")
        if period_start: qs = qs.filter(run__revision__valid_from__gte=period_start)
        if period_end: qs = qs.filter(run__revision__valid_from__lt=period_end)
        evidence_kind = request.query_params.get("evidence_kind") or FloodSpatialEvent.EvidenceKind.CONFIRMED_OCCURRENCE
        qs = qs.filter(run__revision__event__evidence_kind=evidence_kind)
        if request.query_params.get("bbox"):
            try:
                from django.contrib.gis.geos import Polygon
                values = [float(value) for value in request.query_params["bbox"].split(",")]
                qs = qs.filter(location__intersects=Polygon.from_bbox(values))
            except (TypeError, ValueError):
                return Response({"error": {"code": "invalid_filter", "detail": "bbox inválido.", "fields": {}}}, status=400)
        groups = defaultdict(lambda: {"items": [], "events": set(), "length": 0.0, "duration": 0})
        for item in qs:
            group = groups[(item.dimension, item.dimension_key)]
            group["items"].append(item)
            group["events"].add(item.run.revision.event_id)
            group["length"] += item.impacted_length_m
            revision = item.run.revision
            group["duration"] += max(0, int(((revision.valid_until or revision.valid_from) - revision.valid_from).total_seconds()))
        results = []
        cameras = list(Camera.objects.exclude(status=Camera.CameraStatus.INACTIVE).select_related("address"))
        for group in groups.values():
            item = group["items"][0]
            origin = (item.location.y, item.location.x)
            nearby = []
            for camera in cameras:
                coordinates = camera_coordinates(camera)
                if coordinates is None:
                    continue
                distance = haversine_distance_m(origin, coordinates)
                if distance <= 2000:
                    nearby.append({"id": str(camera.id), "description": camera.description, "latitude": coordinates[0], "longitude": coordinates[1], "distance_m": distance, "active": camera.status == Camera.CameraStatus.ACTIVE})
            nearby.sort(key=lambda value: value["distance_m"])
            event_count = len(group["events"])
            results.append({
                "id": str(item.id), "event_id": str(item.run.revision.event_id),
                "spatial_unit": item.dimension, "spatial_id": item.dimension_key, "name": item.label,
                "geometry": json.loads(item.location.geojson), "evidence_kind": evidence_kind,
                "period_start": min(value.run.revision.valid_from for value in group["items"]).isoformat(),
                "period_end": max(value.run.revision.valid_until or value.run.revision.valid_from for value in group["items"]).isoformat(),
                "event_count": event_count,
                "confirmed_event_count": event_count if evidence_kind == FloodSpatialEvent.EvidenceKind.CONFIRMED_OCCURRENCE else 0,
                "affected_length_m": group["length"], "affected_duration_seconds": group["duration"],
                "recurrence_score": event_count, "nearby_cameras": nearby[:5],
                "algorithm_version": item.run.algorithm_version,
            })
        results.sort(key=lambda value: (-value["recurrence_score"], -value["affected_length_m"], value["name"]))
        paginator = FloodImpactPagination()
        page = paginator.paginate_queryset(results, request)
        return paginator.get_paginated_response(page)

    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, pk=None):
        hotspot = RoadImpactHotspot.objects.select_related("run__revision__event").filter(pk=pk).first()
        if hotspot is None:
            return Response({"error": {"code": "not_found", "detail": "Hotspot não encontrado.", "fields": {}}}, status=404)
        qs = RoadImpactHotspot.objects.select_related("run__revision__event").filter(
            dimension=hotspot.dimension,
            dimension_key=hotspot.dimension_key,
            run__revision__event__city=hotspot.run.revision.event.city,
            run__status=RoadFloodImpactRun.Status.COMPLETED,
            run__revision__status=FloodSpatialEventRevision.Status.ACTIVE,
        ).order_by("-run__revision__valid_from")
        paginator = FloodImpactPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response([{
            "id": str(item.id),
            "event_id": str(item.run.revision.event_id),
            "evidence_kind": item.run.revision.event.evidence_kind,
            "status": item.run.revision.status,
            "valid_from": item.run.revision.valid_from.isoformat(),
            "valid_until": item.run.revision.valid_until.isoformat() if item.run.revision.valid_until else None,
            "affected_length_m": item.impacted_length_m,
            "affected_regions": item.run.revision.affected_regions,
            "affected_streets": item.run.revision.affected_streets,
        } for item in page])
