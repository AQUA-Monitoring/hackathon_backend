import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("flood_impact", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="floodspatialevent",
            name="derived_from_event",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="derived_events", to="flood_impact.floodspatialevent",
            ),
        ),
        migrations.AlterField(
            model_name="floodspatialevent",
            name="evidence_kind",
            field=models.CharField(
                choices=[
                    ("FORECAST", "Previsão"),
                    ("CAMERA_OBSERVATION", "Observação por câmera"),
                    ("USER_REPORT", "Relato"),
                    ("CONFIRMED_OCCURRENCE", "Ocorrência confirmada"),
                    ("LEGACY_UNCLASSIFIED", "Legado não classificado"),
                ],
                db_index=True, max_length=32,
            ),
        ),
    ]
