import django.db.models.deletion
from django.db import migrations, models


def initialize_legacy_operational_state(apps, schema_editor):
    Camera = apps.get_model("flood_camera_monitoring", "Camera")
    Snapshot = apps.get_model(
        "flood_camera_monitoring", "CameraOperationalSnapshot"
    )

    for camera in Camera.objects.all().iterator():
        was_offline = camera.status == 3
        if was_offline:
            # OFFLINE misturava disponibilidade da transmissão com a decisão
            # administrativa. Câmeras legadas continuam habilitadas, enquanto
            # a indisponibilidade passa a ser registrada no snapshot.
            Camera.objects.filter(pk=camera.pk).update(status=1)

        Snapshot.objects.get_or_create(
            camera_id=camera.pk,
            defaults={
                "stream_status": "UNAVAILABLE" if was_offline else "UNKNOWN",
                "analysis_status": "NOT_ANALYZED",
                "model_status": "UNKNOWN",
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("addressing", "0014_address_city_ref"),
        ("users", "0003_user_profile_picture_fk_and_url"),
        ("flood_camera_monitoring", "0016_remove_legacy_demo_camera"),
    ]

    operations = [
        migrations.AlterField(
            model_name="camera",
            name="status",
            field=models.IntegerField(
                choices=[(1, "ACTIVE"), (2, "INACTIVE"), (3, "OFFLINE")],
                default=2,
            ),
        ),
        migrations.AddField(
            model_name="camera",
            name="address",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cameras",
                to="addressing.address",
            ),
        ),
        migrations.AddField(
            model_name="camera",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="registered_cameras",
                to="users.user",
            ),
        ),
        migrations.CreateModel(
            name="CameraOperationalSnapshot",
            fields=[
                (
                    "camera",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="operational_snapshot",
                        serialize=False,
                        to="flood_camera_monitoring.camera",
                    ),
                ),
                (
                    "stream_status",
                    models.CharField(
                        choices=[
                            ("UNKNOWN", "UNKNOWN"),
                            ("CHECKING", "CHECKING"),
                            ("ONLINE", "ONLINE"),
                            ("UNAVAILABLE", "UNAVAILABLE"),
                        ],
                        db_index=True,
                        default="UNKNOWN",
                        max_length=20,
                    ),
                ),
                ("stream_checked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "analysis_status",
                    models.CharField(
                        choices=[
                            ("NOT_ANALYZED", "NOT_ANALYZED"),
                            ("RUNNING", "RUNNING"),
                            ("AVAILABLE", "AVAILABLE"),
                            ("STALE", "STALE"),
                            ("NO_FRAME", "NO_FRAME"),
                            ("MODEL_UNAVAILABLE", "MODEL_UNAVAILABLE"),
                            ("ERROR", "ERROR"),
                        ],
                        db_index=True,
                        default="NOT_ANALYZED",
                        max_length=24,
                    ),
                ),
                (
                    "classification",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("NO_INDICATION", "NO_INDICATION"),
                            (
                                "INTERMEDIATE_INDICATION",
                                "INTERMEDIATE_INDICATION",
                            ),
                            ("FLOOD_INDICATION", "FLOOD_INDICATION"),
                        ],
                        max_length=32,
                        null=True,
                    ),
                ),
                ("prob_normal", models.FloatField(blank=True, null=True)),
                ("prob_medium", models.FloatField(blank=True, null=True)),
                ("prob_flooded", models.FloatField(blank=True, null=True)),
                ("confidence", models.FloatField(blank=True, null=True)),
                ("frames", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "analysis_started_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                ("analyzed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "model_status",
                    models.CharField(
                        choices=[
                            ("UNKNOWN", "UNKNOWN"),
                            ("READY", "READY"),
                            ("UNAVAILABLE", "UNAVAILABLE"),
                            ("FALLBACK", "FALLBACK"),
                        ],
                        db_index=True,
                        default="UNKNOWN",
                        max_length=20,
                    ),
                ),
                (
                    "model_version",
                    models.CharField(blank=True, max_length=255, null=True),
                ),
                (
                    "error_code",
                    models.CharField(blank=True, max_length=100, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.RunPython(
            initialize_legacy_operational_state,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
