from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID

from core.flood_camera_monitoring.demo.manifest import DemoManifestError
from core.uploader.models import Video


class UploadedVideoResolver:
    """Materialize uploader-backed videos for FFmpeg, regardless of storage backend."""

    def __init__(self, work_dir: str | Path) -> None:
        self.asset_dir = Path(work_dir) / "uploaded-videos"

    def __call__(self, attachment_key: str) -> Path:
        try:
            parsed_key = UUID(attachment_key)
        except (ValueError, AttributeError) as exc:
            raise DemoManifestError("Invalid video attachment key") from exc

        try:
            video = Video.objects.get(attachment_key=parsed_key)  # type: ignore[attr-defined]
        except Video.DoesNotExist as exc:
            raise DemoManifestError(
                f"Uploader video not found: {attachment_key}"
            ) from exc

        if not video.file.name:
            raise DemoManifestError(
                f"Uploader video has no stored file: {attachment_key}"
            )

        suffix = Path(video.file.name).suffix.lower() or ".video"
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        destination = self.asset_dir / f"{video.public_id}{suffix}"
        temporary = destination.with_suffix(f"{destination.suffix}.part")

        try:
            with video.file.open("rb") as source, temporary.open("wb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
            temporary.replace(destination)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise DemoManifestError(
                f"Could not read uploader video: {attachment_key}"
            ) from exc

        return destination
