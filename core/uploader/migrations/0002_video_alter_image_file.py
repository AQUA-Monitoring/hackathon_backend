import core.uploader.models.image
import core.uploader.models.video
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("uploader", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="image",
            name="file",
            field=models.FileField(upload_to=core.uploader.models.image.image_file_path),
        ),
        migrations.CreateModel(
            name="Video",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "attachment_key",
                    models.UUIDField(
                        default=uuid.uuid4,
                        help_text="Used to attach the video to another object. Cannot be used to retrieve the video file.",
                        unique=True,
                    ),
                ),
                (
                    "public_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        help_text="Used to retrieve the video file itself. Should not be readable until the video is attached to another object.",
                        unique=True,
                    ),
                ),
                (
                    "file",
                    models.FileField(upload_to=core.uploader.models.video.video_file_path),
                ),
                ("description", models.CharField(blank=True, max_length=255)),
                ("uploaded_on", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
