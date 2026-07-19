import django.contrib.gis.db.models.fields
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("addressing", "0019_reconcile_territory_postgis")]

    operations = [
        migrations.CreateModel(
            name="RoadAxisSegment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("source_record_id", models.CharField(max_length=255)),
                ("geometry", django.contrib.gis.db.models.fields.MultiLineStringField(srid=4326)),
                ("road_class", models.CharField(blank=True, max_length=80)),
                ("surface", models.CharField(blank=True, max_length=80)),
                ("direction", models.CharField(blank=True, max_length=40)),
                ("properties", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("city", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="road_axis_segments", to="addressing.city")),
                ("dataset", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="road_axis_segments", to="addressing.geodatadataset")),
                ("street", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="axis_segments", to="addressing.street")),
            ],
        ),
        migrations.CreateModel(
            name="RoadAxisSegmentNeighborhood",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("neighborhood", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="road_axis_segment_links", to="addressing.neighborhood")),
                ("segment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="neighborhood_links", to="addressing.roadaxissegment")),
            ],
        ),
        migrations.AddConstraint(model_name="roadaxissegment", constraint=models.UniqueConstraint(fields=("dataset", "source_record_id"), name="uniq_axis_segment_dataset_source")),
        migrations.AddIndex(model_name="roadaxissegment", index=models.Index(fields=["city", "street", "is_active"], name="addressing__city_id_axis_idx")),
        migrations.AddConstraint(model_name="roadaxissegmentneighborhood", constraint=models.UniqueConstraint(fields=("segment", "neighborhood"), name="uniq_axis_segment_neighborhood")),
    ]
