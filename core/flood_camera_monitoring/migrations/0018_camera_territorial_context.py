import django.db.models.deletion
from django.db import migrations, models


def backfill_from_address(apps, schema_editor):
    Camera = apps.get_model("flood_camera_monitoring", "Camera")
    for camera in Camera.objects.select_related("address", "neighborhood").all().iterator():
        address = camera.address
        updates = {
            "city_id": address.city_ref_id if address else None,
            "region_id": camera.neighborhood.region_id if camera.neighborhood_id else None,
            "street_id": address.street_ref_id if address else None,
            "address_reference_id": address.address_reference_id if address else None,
            "territory_resolution": {"method": "LEGACY_ADDRESS", "resolved": False},
        }
        Camera.objects.filter(pk=camera.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [
        ("addressing", "0021_address_reference_autocomplete_indexes"),
        ("flood_camera_monitoring", "0017_camera_registration_and_operational_snapshot"),
    ]

    operations = [
        migrations.AddField(model_name="camera", name="city", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="territorial_cameras", to="addressing.city")),
        migrations.AddField(model_name="camera", name="region", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="territorial_cameras", to="addressing.region")),
        migrations.AddField(model_name="camera", name="street", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="territorial_cameras", to="addressing.street")),
        migrations.AddField(model_name="camera", name="road_segment", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="territorial_cameras", to="addressing.roadaxissegment")),
        migrations.AddField(model_name="camera", name="address_reference", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="territorial_cameras", to="addressing.addressreference")),
        migrations.AddField(model_name="camera", name="territory_resolution", field=models.JSONField(blank=True, default=dict)),
        migrations.RunPython(backfill_from_address, reverse_code=migrations.RunPython.noop),
    ]
