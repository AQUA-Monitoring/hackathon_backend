import django.contrib.gis.db.models.fields
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("addressing", "0020_road_axis_segments"), ("users", "0003_user_profile_picture_fk_and_url")]

    operations = [
        migrations.CreateModel(name="FloodSpatialEvent", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("evidence_kind", models.CharField(choices=[("FORECAST", "Previsão"), ("CAMERA_OBSERVATION", "Observação por câmera"), ("USER_REPORT", "Relato"), ("CONFIRMED_OCCURRENCE", "Ocorrência confirmada")], db_index=True, max_length=32)),
            ("source_type", models.CharField(max_length=120)), ("source_id", models.CharField(max_length=255)),
            ("city", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="flood_spatial_events", to="addressing.city")),
        ]),
        migrations.CreateModel(name="FloodSpatialEventRevision", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("revision", models.PositiveIntegerField()),
            ("status", models.CharField(choices=[("DRAFT", "Rascunho"), ("ACTIVE", "Ativo"), ("SUPERSEDED", "Substituído"), ("REVOKED", "Revogado")], db_index=True, default="DRAFT", max_length=16)),
            ("location", django.contrib.gis.db.models.fields.PointField(blank=True, null=True, srid=4326)),
            ("footprint", django.contrib.gis.db.models.fields.MultiPolygonField(blank=True, null=True, srid=4326)),
            ("confidence", models.FloatField(blank=True, null=True)), ("valid_from", models.DateTimeField()),
            ("valid_until", models.DateTimeField(blank=True, null=True)),
            ("geometry_method", models.CharField(choices=[("PROVIDED", "Fornecida"), ("DERIVED", "Derivada"), ("MANUAL", "Manual")], max_length=16)),
            ("source_version", models.CharField(blank=True, max_length=120)), ("properties", models.JSONField(blank=True, default=dict)),
            ("justification", models.TextField()), ("source_revision", models.CharField(max_length=255)),
            ("author", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="flood_event_revisions", to="users.user")),
            ("event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="revisions", to="flood_impact.floodspatialevent")),
        ]),
        migrations.AddField(model_name="floodspatialevent", name="current_revision", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="current_for_events", to="flood_impact.floodspatialeventrevision")),
        migrations.CreateModel(name="RoadFloodImpactRun", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("algorithm_version", models.CharField(max_length=40)),
            ("status", models.CharField(choices=[("RUNNING", "Executando"), ("COMPLETED", "Concluído"), ("FAILED", "Falhou")], db_index=True, default="RUNNING", max_length=16)),
            ("started_at", models.DateTimeField()), ("finished_at", models.DateTimeField(blank=True, null=True)),
            ("report", models.JSONField(blank=True, default=dict)),
            ("input_hash", models.CharField(db_index=True, max_length=64)),
            ("revision", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="impact_runs", to="flood_impact.floodspatialeventrevision")),
            ("road_dataset", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="flood_impact_runs", to="addressing.geodatadataset")),
        ]),
        migrations.CreateModel(name="RoadFloodImpact", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("intersection", django.contrib.gis.db.models.fields.MultiLineStringField(srid=4326)),
            ("length_m", models.FloatField()), ("segment_fraction", models.FloatField()),
            ("relation", models.CharField(choices=[("CROSSES", "Cruza"), ("WITHIN", "Contido")], max_length=16)),
            ("evidence_kind", models.CharField(choices=[("FORECAST", "Previsão"), ("CAMERA_OBSERVATION", "Observação por câmera"), ("USER_REPORT", "Relato"), ("CONFIRMED_OCCURRENCE", "Ocorrência confirmada")], db_index=True, max_length=32)),
            ("evidence_status", models.CharField(choices=[("DRAFT", "Rascunho"), ("ACTIVE", "Ativo"), ("SUPERSEDED", "Substituído"), ("REVOKED", "Revogado")], db_index=True, max_length=16)),
            ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="impacts", to="flood_impact.roadfloodimpactrun")),
            ("segment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="flood_impacts", to="addressing.roadaxissegment")),
        ]),
        migrations.CreateModel(name="RoadImpactHotspot", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("location", django.contrib.gis.db.models.fields.PointField(srid=4326)),
            ("impacted_length_m", models.FloatField()), ("segment_count", models.PositiveIntegerField()), ("rank", models.PositiveIntegerField(default=1)),
            ("dimension", models.CharField(choices=[("ROAD_SEGMENT", "Trecho viário"), ("GRID_CELL", "Célula de grade"), ("STREET", "Logradouro"), ("NEIGHBORHOOD", "Bairro")], max_length=20)),
            ("dimension_key", models.CharField(max_length=255)), ("label", models.CharField(blank=True, max_length=255)),
            ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="hotspots", to="flood_impact.roadfloodimpactrun")),
        ]),
        migrations.AddConstraint(model_name="floodspatialevent", constraint=models.UniqueConstraint(fields=("source_type", "source_id"), name="uniq_flood_event_source")),
        migrations.AddIndex(model_name="floodspatialevent", index=models.Index(fields=["city", "evidence_kind"], name="flood_impac_city_ev_idx")),
        migrations.AddConstraint(model_name="floodspatialeventrevision", constraint=models.UniqueConstraint(fields=("event", "revision"), name="uniq_flood_event_revision")),
        migrations.AddConstraint(model_name="floodspatialeventrevision", constraint=models.CheckConstraint(condition=models.Q(("confidence__isnull", True), models.Q(("confidence__gte", 0), ("confidence__lte", 1)), _connector="OR"), name="flood_revision_confidence_0_1")),
        migrations.AddConstraint(model_name="floodspatialeventrevision", constraint=models.CheckConstraint(condition=models.Q(("valid_until__isnull", True), ("valid_until__gt", models.F("valid_from")), _connector="OR"), name="flood_revision_valid_window")),
        migrations.AddIndex(model_name="floodspatialeventrevision", index=models.Index(fields=["status", "valid_from", "valid_until"], name="flood_impac_status_valid_idx")),
        migrations.AddConstraint(model_name="roadfloodimpactrun", constraint=models.UniqueConstraint(fields=("revision", "road_dataset", "algorithm_version"), name="uniq_road_impact_run")),
        migrations.AddConstraint(model_name="roadfloodimpact", constraint=models.UniqueConstraint(fields=("run", "segment"), name="uniq_run_impacted_segment")),
        migrations.AddConstraint(model_name="roadfloodimpact", constraint=models.CheckConstraint(condition=models.Q(("length_m__gte", 0)), name="road_impact_length_nonnegative")),
        migrations.AddConstraint(model_name="roadfloodimpact", constraint=models.CheckConstraint(condition=models.Q(("segment_fraction__gte", 0), ("segment_fraction__lte", 1)), name="road_impact_fraction_0_1")),
        migrations.AddConstraint(model_name="roadimpacthotspot", constraint=models.UniqueConstraint(fields=("run", "dimension", "dimension_key"), name="uniq_road_hotspot_dimension")),
    ]
