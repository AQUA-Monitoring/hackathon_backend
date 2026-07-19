import json
from django.contrib.gis.db import models
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.db import migrations


def move_legacy_geometry(apps, schema_editor):
    for model_name in ("City", "Region", "Neighborhood"):
        model = apps.get_model("addressing", model_name)
        for obj in model.objects.all().iterator():
            props = obj.props if hasattr(obj, "props") and isinstance(obj.props, dict) else {}
            geometry = props.get("geometry")
            if geometry and not getattr(obj, "geometry", None):
                parsed = GEOSGeometry(json.dumps(geometry), srid=4326)
                obj.geometry = MultiPolygon(parsed, srid=4326) if parsed.geom_type == "Polygon" else parsed
                obj.geometry_metadata = {"source": "legacy_props_geometry", "migrated": True}
                obj.save(update_fields=["geometry", "geometry_metadata"])


class Migration(migrations.Migration):
    dependencies = [("addressing", "0014_address_city_ref")]
    operations = [
        migrations.RunSQL("CREATE EXTENSION IF NOT EXISTS postgis", reverse_sql=migrations.RunSQL.noop),
        migrations.AddField(model_name="city", name="geometry", field=models.MultiPolygonField(blank=True, null=True, srid=4326)),
        migrations.AddField(model_name="city", name="geometry_metadata", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="region", name="geometry", field=models.MultiPolygonField(blank=True, null=True, srid=4326)),
        migrations.AddField(model_name="region", name="geometry_metadata", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="neighborhood", name="geometry", field=models.MultiPolygonField(blank=True, null=True, srid=4326)),
        migrations.AddField(model_name="neighborhood", name="geometry_metadata", field=models.JSONField(blank=True, default=dict)),
        migrations.RunPython(move_legacy_geometry, migrations.RunPython.noop),
    ]
