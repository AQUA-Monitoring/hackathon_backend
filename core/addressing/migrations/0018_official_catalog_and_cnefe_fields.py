import django.db.models
import unicodedata
from django.db import migrations, models


def seed_codes_and_names(apps, schema_editor):
    City = apps.get_model("addressing", "City")
    Region = apps.get_model("addressing", "Region")
    Neighborhood = apps.get_model("addressing", "Neighborhood")
    codes = {"joinville": "4209102", "araquari": "4201307"}
    def normalized(value):
        return " ".join(unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().casefold().split())

    for city in City.objects.all().iterator():
        normalized_value = normalized(city.name)
        city.normalized_name = normalized_value
        city.official_code = city.official_code or codes.get(normalized_value, "")
        city.save(update_fields=["normalized_name", "official_code"])
    for model in (Region, Neighborhood):
        for obj in model.objects.all().iterator():
            obj.normalized_name = normalized(obj.name)
            obj.save(update_fields=["normalized_name"])


class Migration(migrations.Migration):
    dependencies = [("addressing", "0017_address_address_reference")]
    operations = [
        migrations.AddField(model_name="city", name="official_code", field=models.CharField(blank=True, db_index=True, max_length=32)),
        migrations.AddField(model_name="city", name="normalized_name", field=models.CharField(blank=True, db_index=True, max_length=120)),
        migrations.AddField(model_name="city", name="is_active", field=models.BooleanField(db_index=True, default=True)),
        migrations.AddField(model_name="region", name="official_code", field=models.CharField(blank=True, max_length=64)),
        migrations.AddField(model_name="region", name="normalized_name", field=models.CharField(blank=True, db_index=True, max_length=255)),
        migrations.AddField(model_name="neighborhood", name="official_code", field=models.CharField(blank=True, max_length=64)),
        migrations.AddField(model_name="neighborhood", name="normalized_name", field=models.CharField(blank=True, db_index=True, max_length=255)),
        migrations.AddField(model_name="addressreference", name="modifier", field=models.CharField(blank=True, max_length=80)),
        migrations.AddField(model_name="addressreference", name="address_type", field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name="addressreference", name="species", field=models.CharField(blank=True, max_length=120)),
        migrations.RunPython(seed_codes_and_names, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="geodatadataset", name="uniq_geodata_city_kind_sha"),
        migrations.RemoveConstraint(model_name="geodatadataset", name="uniq_active_geodata_kind"),
        migrations.AddConstraint(model_name="geodatadataset", constraint=models.UniqueConstraint(fields=("city", "kind", "authority", "sha256"), name="uniq_geodata_source_sha")),
        migrations.AddConstraint(model_name="geodatadataset", constraint=models.UniqueConstraint(condition=django.db.models.Q(status="active"), fields=("city", "kind", "authority"), name="uniq_active_geodata_source")),
        migrations.AddConstraint(model_name="city", constraint=models.UniqueConstraint(condition=~django.db.models.Q(official_code=""), fields=("official_code",), name="uniq_city_official_code")),
        migrations.AddConstraint(model_name="region", constraint=models.UniqueConstraint(condition=~django.db.models.Q(official_code=""), fields=("city_ref", "official_code"), name="uniq_region_city_official")),
        migrations.AddConstraint(model_name="neighborhood", constraint=models.UniqueConstraint(condition=~django.db.models.Q(official_code=""), fields=("city_ref", "official_code"), name="uniq_neigh_city_official")),
    ]
