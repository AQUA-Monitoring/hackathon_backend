import mimetypes
import uuid
from pathlib import Path

from django.db import models


def image_file_path(image, _) -> str:
    content_type = getattr(image.file, "content_type", None)
    extension: str | None = mimetypes.guess_extension(content_type or "")
    if not extension and getattr(image.file, "name", None):
        extension = Path(image.file.name).suffix
    if extension == ".jpe":
        extension = ".jpg"
    return f"images/{image.public_id}{extension or ''}"


class Image(models.Model):
    attachment_key = models.UUIDField(
        max_length=255,
        default=uuid.uuid4,
        unique=True,
        help_text=("Used to attach the image to another object. " "Cannot be used to retrieve the image file."),
    )
    public_id = models.UUIDField(
        max_length=255,
        default=uuid.uuid4,
        unique=True,
        help_text=(
            "Used to retrieve the image itself. "
            "Should not be readable until the image is attached to another object."
        ),
    )
    file = models.ImageField(upload_to=image_file_path)
    description = models.CharField(max_length=255, blank=True)
    uploaded_on = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.description} - {self.attachment_key}"

    @property
    def url(self) -> str:
        return self.file.url  # pylint: disable=no-member
