from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("flood_impact", "0002_event_lineage")]

    operations = [
        migrations.AlterField(
            model_name="roadfloodimpact",
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
