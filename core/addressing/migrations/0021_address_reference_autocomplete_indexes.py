from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("addressing", "0020_road_axis_segments")]

    operations = [
        migrations.AddIndex(
            model_name="addressreference",
            index=models.Index(
                fields=["city", "street", "is_active", "street_name"],
                name="addrref_street_lookup_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="addressreference",
            index=models.Index(
                fields=["city", "neighborhood", "is_active"],
                name="addrref_neigh_lookup_idx",
            ),
        ),
    ]
