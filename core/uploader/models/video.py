import mimetypes
import uuid
from pathlib import Path

from django.db import models

from core.uploader.helpers.files import get_content_type


def video_file_path(video, filename: str) -> str:
    content_type = get_content_type(video.file)
    extension = mimetypes.guess_extension(content_type or "")
    if not extension:
        extension = Path(filename or getattr(video.file, "name", "")).suffix
    return f"videos/{video.public_id}{extension or ''}"


class Video(models.Model):
    attachment_key = models.UUIDField(
        max_length=255,
        default=uuid.uuid4,
        unique=True,
        help_text=(
            "Used to attach the video to another object. "
            "Cannot be used to retrieve the video file."
        ),
    )
    public_id = models.UUIDField(
        max_length=255,
        default=uuid.uuid4,
        unique=True,
        help_text=(
            "Used to retrieve the video file itself. "
            "Should not be readable until the video is attached to another object."
        ),
    )
    file = models.FileField(upload_to=video_file_path)
    description = models.CharField(max_length=255, blank=True)
    uploaded_on = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.description} - {self.attachment_key}"

    @property
    def url(self) -> str:
        return self.file.url  # pylint: disable=no-member
