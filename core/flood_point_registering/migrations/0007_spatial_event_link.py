import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("flood_impact", "0003_legacy_impact_evidence"),
        ("flood_point_registering", "0006_spatial_resolution"),
    ]

    operations = [
        migrations.AddField(
            model_name="flood_point_register",
            name="spatial_event",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="legacy_flood_points", to="flood_impact.floodspatialevent",
            ),
        ),
    ]
