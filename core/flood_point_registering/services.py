"""Serviços simples do cadastro legado de pontos de alagamento."""

from django.utils import timezone
from django.db import transaction

from core.flood_point_registering.infra.models import Flood_Point_Register
from core.flood_impact.models import FloodSpatialEvent, FloodSpatialEventRevision


def active_flood_points(*, at=None):
    return Flood_Point_Register.objects.active(at or timezone.now()).order_by("-created_at")


@transaction.atomic
def sync_legacy_spatial_event(flood_point, *, author=None):
    """Cria uma revisão canônica sem alterar a semântica do registro legado."""
    event, _ = FloodSpatialEvent.objects.select_for_update().get_or_create(
        source_type="legacy_flood_point",
        source_id=str(flood_point.pk),
        defaults={
            "city": flood_point.city,
            "evidence_kind": FloodSpatialEvent.EvidenceKind.LEGACY_UNCLASSIFIED,
        },
    )
    if event.city_id != flood_point.city_id:
        event.city = flood_point.city
    event.evidence_kind = FloodSpatialEvent.EvidenceKind.LEGACY_UNCLASSIFIED
    revision_number = (event.revisions.order_by("-revision").values_list("revision", flat=True).first() or 0) + 1
    revision = FloodSpatialEventRevision.objects.create(
        event=event,
        revision=revision_number,
        status=FloodSpatialEventRevision.Status.DRAFT,
        location=flood_point.location,
        footprint=flood_point.footprint,
        confidence=flood_point.possibility,
        valid_from=flood_point.created_at,
        valid_until=flood_point.finished_at,
        geometry_method=(
            FloodSpatialEventRevision.GeometryMethod.PROVIDED
            if flood_point.location or flood_point.footprint
            else FloodSpatialEventRevision.GeometryMethod.DERIVED
        ),
        source_version="legacy-adapter-v1",
        properties={
            "legacy_props": flood_point.props,
            "territory_resolution": flood_point.territory_resolution,
            "neighborhood_id": str(flood_point.neighborhood_id),
        },
        author=author if getattr(author, "is_authenticated", False) else None,
        justification="Snapshot criado pelo adaptador do cadastro legado.",
        source_revision=str(revision_number),
    )
    event.current_revision = revision
    event.save(update_fields=["city", "evidence_kind", "current_revision", "updated_at"])
    if flood_point.spatial_event_id != event.id:
        Flood_Point_Register.objects.filter(pk=flood_point.pk).update(spatial_event=event)
        flood_point.spatial_event = event
    return event
