from django.db import migrations, models


def backfill_affected_territory(apps, schema_editor):
    """Preenche snapshots apenas quando a geometria e a cobertura existem.

    O backfill usa exclusivamente o estado histórico das tabelas locais. Rodar
    novamente produz o mesmo resultado para a mesma base territorial ativa.
    """
    Revision = apps.get_model("flood_impact", "FloodSpatialEventRevision")
    Region = apps.get_model("addressing", "Region")
    Street = apps.get_model("addressing", "Street")
    RoadAxisSegment = apps.get_model("addressing", "RoadAxisSegment")

    for revision in Revision.objects.exclude(location=None, footprint=None).iterator():
        geometry = revision.footprint if revision.footprint is not None else revision.location
        city_id = revision.event.city_id
        regions = Region.objects.filter(
            city_ref_id=city_id, is_active=True, geometry__intersects=geometry,
        ).order_by("name", "id")
        street_ids = set(Street.objects.filter(
            city_id=city_id, is_active=True, geometry__intersects=geometry,
        ).values_list("id", flat=True))
        street_ids.update(RoadAxisSegment.objects.filter(
            city_id=city_id, is_active=True, geometry__intersects=geometry,
            street_id__isnull=False,
        ).values_list("street_id", flat=True))
        streets = Street.objects.filter(id__in=street_ids, is_active=True).order_by("name", "id")
        revision.affected_regions = [{"id": str(region.id), "name": region.name} for region in regions]
        revision.affected_streets = [{"id": str(street.id), "name": street.name} for street in streets]
        revision.save(update_fields=["affected_regions", "affected_streets"])


class Migration(migrations.Migration):
    dependencies = [("flood_impact", "0003_legacy_impact_evidence")]

    operations = [
        migrations.AddField(
            model_name="floodspatialeventrevision",
            name="affected_regions",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="floodspatialeventrevision",
            name="affected_streets",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(backfill_affected_territory, migrations.RunPython.noop),
    ]
