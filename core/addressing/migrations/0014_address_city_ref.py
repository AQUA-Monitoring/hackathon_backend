import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("addressing", "0013_seed_joinville_araquari_and_backfill_refs"),
    ]

    operations = [
        migrations.AddField(
            model_name="address",
            name="city_ref",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="addresses",
                to="addressing.city",
            ),
        ),
    ]
