from django.db import migrations


DEMO_DESCRIPTION = "Camera Demo Alagamento (Loop)"


def remove_legacy_demo_camera(apps, schema_editor):
    Camera = apps.get_model("flood_camera_monitoring", "Camera")
    Camera.objects.filter(description=DEMO_DESCRIPTION).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("flood_camera_monitoring", "0015_seed_demo_camera"),
    ]

    operations = [
        migrations.RunPython(remove_legacy_demo_camera, migrations.RunPython.noop),
    ]
