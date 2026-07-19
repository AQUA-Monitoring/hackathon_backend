from django.db import migrations


def backfill_spatial_events(apps, schema_editor):
    FloodPoint = apps.get_model("flood_point_registering", "Flood_Point_Register")
    Event = apps.get_model("flood_impact", "FloodSpatialEvent")
    Revision = apps.get_model("flood_impact", "FloodSpatialEventRevision")

    for flood_point in FloodPoint.objects.filter(spatial_event__isnull=True).iterator():
        event, _ = Event.objects.get_or_create(
            source_type="legacy_flood_point",
            source_id=str(flood_point.pk),
            defaults={
                "city_id": flood_point.city_id,
                "evidence_kind": "LEGACY_UNCLASSIFIED",
            },
        )
        revision, _ = Revision.objects.get_or_create(
            event=event,
            revision=1,
            defaults={
                "status": "DRAFT",
                "location": flood_point.location,
                "footprint": flood_point.footprint,
                "confidence": flood_point.possibility,
                "valid_from": flood_point.created_at,
                "valid_until": flood_point.finished_at,
                "geometry_method": "DERIVED",
                "source_version": "legacy-backfill-v1",
                "properties": {
                    "legacy_props": flood_point.props,
                    "territory_resolution": flood_point.territory_resolution,
                    "neighborhood_id": str(flood_point.neighborhood_id),
                    "backfill_uses_current_territory": True,
                },
                "justification": "Backfill auditável do cadastro legado, sem geometria inventada.",
                "source_revision": "1",
            },
        )
        if event.current_revision_id is None:
            event.current_revision_id = revision.pk
            event.save(update_fields=["current_revision"])
        FloodPoint.objects.filter(pk=flood_point.pk).update(spatial_event_id=event.pk)


class Migration(migrations.Migration):
    dependencies = [
        ("flood_point_registering", "0007_spatial_event_link"),
    ]

    operations = [
        migrations.RunPython(backfill_spatial_events, migrations.RunPython.noop),
    ]
