from pathlib import Path

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, Http404
from django.utils._os import safe_join


def serve_media(_request, path: str) -> FileResponse:
    """Serve uploaded media when Gunicorn is the public HTTP server."""
    try:
        media_root = Path(settings.MEDIA_ROOT).resolve(strict=True)
        file_path = Path(safe_join(media_root, path)).resolve(strict=True)
        file_path.relative_to(media_root)
        if not file_path.is_file():
            raise Http404
        media_file = file_path.open("rb")
    except (OSError, SuspiciousFileOperation, ValueError):
        raise Http404 from None

    return FileResponse(media_file)
