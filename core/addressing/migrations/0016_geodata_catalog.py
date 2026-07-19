import django.contrib.gis.db.models.fields
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("addressing", "0015_territory_geojson")]
    operations = [
        migrations.CreateModel(name="GeodataDataset", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("kind", models.CharField(choices=[("city_boundary", "Limite municipal"), ("region_boundary", "Limite regional"), ("neighborhood_boundary", "Limite de bairro"), ("street", "Logradouro"), ("address_point", "Ponto de endereço")], max_length=32)),
            ("authority", models.CharField(max_length=255)), ("title", models.CharField(max_length=255)),
            ("source_url", models.URLField(max_length=1000)), ("license_name", models.CharField(max_length=255)),
            ("license_url", models.URLField(blank=True, max_length=1000)), ("source_version", models.CharField(max_length=120)),
            ("published_at", models.DateField(blank=True, null=True)), ("retrieved_at", models.DateTimeField()),
            ("sha256", models.CharField(max_length=64)), ("source_crs", models.CharField(max_length=32)),
            ("status", models.CharField(choices=[("staged", "Preparado"), ("active", "Ativo"), ("superseded", "Substituído"), ("failed", "Falhou")], default="staged", max_length=16)),
            ("metadata", models.JSONField(blank=True, default=dict)),
            ("city", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="datasets", to="addressing.city")),
        ]),
        migrations.CreateModel(name="Street", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("source_record_id", models.CharField(max_length=255)), ("name", models.CharField(max_length=255)),
            ("normalized_name", models.CharField(db_index=True, max_length=255)), ("street_type", models.CharField(blank=True, max_length=80)),
            ("zipcode_from", models.CharField(blank=True, max_length=32)), ("zipcode_to", models.CharField(blank=True, max_length=32)),
            ("geometry", django.contrib.gis.db.models.fields.MultiLineStringField(blank=True, null=True, srid=4326)),
            ("properties", models.JSONField(blank=True, default=dict)), ("is_active", models.BooleanField(db_index=True, default=True)),
            ("city", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="streets", to="addressing.city")),
            ("dataset", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="streets", to="addressing.geodatadataset")),
        ]),
        migrations.CreateModel(name="AddressReference", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("source_record_id", models.CharField(max_length=255)), ("street_name", models.CharField(max_length=255)),
            ("number", models.CharField(blank=True, max_length=50)), ("zipcode", models.CharField(blank=True, max_length=32)),
            ("complement", models.CharField(blank=True, max_length=255)), ("location", django.contrib.gis.db.models.fields.PointField(srid=4326)),
            ("properties", models.JSONField(blank=True, default=dict)), ("is_active", models.BooleanField(db_index=True, default=True)),
            ("city", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="address_references", to="addressing.city")),
            ("dataset", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="address_references", to="addressing.geodatadataset")),
            ("neighborhood", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="address_references", to="addressing.neighborhood")),
            ("street", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="address_references", to="addressing.street")),
        ]),
        migrations.CreateModel(name="StreetNeighborhood", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("neighborhood", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="street_links", to="addressing.neighborhood")),
            ("street", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="neighborhood_links", to="addressing.street")),
        ]),
        migrations.AddField(model_name="address", name="dataset", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="legacy_addresses", to="addressing.geodatadataset")),
        migrations.AddField(model_name="address", name="source_record_id", field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name="address", name="street_ref", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="legacy_addresses", to="addressing.street")),
        migrations.AddField(model_name="city", name="source_record_id", field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name="city", name="geometry_dataset", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="cities", to="addressing.geodatadataset")),
        migrations.AddField(model_name="region", name="dataset", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="regions", to="addressing.geodatadataset")),
        migrations.AddField(model_name="region", name="source_record_id", field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name="region", name="is_active", field=models.BooleanField(db_index=True, default=True)),
        migrations.AddField(model_name="neighborhood", name="dataset", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="neighborhoods", to="addressing.geodatadataset")),
        migrations.AddField(model_name="neighborhood", name="source_record_id", field=models.CharField(blank=True, max_length=255)),
        migrations.AddField(model_name="neighborhood", name="is_active", field=models.BooleanField(db_index=True, default=True)),
        migrations.AddConstraint(model_name="geodatadataset", constraint=models.UniqueConstraint(fields=("city", "kind", "sha256"), name="uniq_geodata_city_kind_sha")),
        migrations.AddConstraint(model_name="geodatadataset", constraint=models.UniqueConstraint(condition=models.Q(("status", "active")), fields=("city", "kind"), name="uniq_active_geodata_kind")),
        migrations.AddConstraint(model_name="street", constraint=models.UniqueConstraint(fields=("dataset", "source_record_id"), name="uniq_street_dataset_source")),
        migrations.AddConstraint(model_name="addressreference", constraint=models.UniqueConstraint(fields=("dataset", "source_record_id"), name="uniq_addressref_dataset_source")),
        migrations.AddConstraint(model_name="streetneighborhood", constraint=models.UniqueConstraint(fields=("street", "neighborhood"), name="uniq_street_neighborhood")),
        migrations.AddIndex(model_name="geodatadataset", index=models.Index(fields=["city", "kind", "status"], name="addressing__city_id_d2c44d_idx")),
        migrations.AddIndex(model_name="street", index=models.Index(fields=["city", "normalized_name", "is_active"], name="addressing__city_id_6de0b5_idx")),
        migrations.AddIndex(model_name="addressreference", index=models.Index(fields=["city", "street_name", "number"], name="addressing__city_id_1cfe06_idx")),
    ]
