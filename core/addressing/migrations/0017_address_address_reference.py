import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("addressing", "0016_geodata_catalog")]

    operations = [
        migrations.AddField(
            model_name="address",
            name="address_reference",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="operational_addresses",
                to="addressing.addressreference",
            ),
        ),
    ]
