from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("addressing", "0022_street_official_catalog")]
    operations = [
        migrations.AddIndex(
            model_name="street",
            index=models.Index(fields=("official_code",), name="addressing_street_official_idx"),
        ),
        migrations.AddConstraint(
            model_name="street",
            constraint=models.UniqueConstraint(
                condition=Q(is_active=True) & ~Q(official_code=""),
                fields=("city", "dataset", "official_code"),
                name="uniq_street_city_dataset_official",
            ),
        ),
    ]
