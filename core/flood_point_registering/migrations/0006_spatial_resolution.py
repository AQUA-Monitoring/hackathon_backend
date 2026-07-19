from django.contrib.gis.db import models
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("flood_point_registering", "0005_add_city_fk_backfill_and_cleanup"),
    ]

    operations = [
        migrations.AddField(
            model_name="flood_point_register",
            name="location",
            field=models.PointField(blank=True, null=True, srid=4326),
        ),
        migrations.AddField(
            model_name="flood_point_register",
            name="footprint",
            field=models.MultiPolygonField(blank=True, null=True, srid=4326),
        ),
        migrations.AddField(
            model_name="flood_point_register",
            name="territory_resolution",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
