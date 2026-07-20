"""Apresentação das capacidades HLS locais legadas."""

from pathlib import Path
import time

from django.conf import settings
from django.http import Http404
from rest_framework.response import Response
from rest_framework.views import APIView

from core.flood_camera_monitoring.infra.hls import (
    ensure_hls_live_loop,
    media_loop_url,
    next_skip_count,
)
from core.flood_camera_monitoring.presentation.utils import build_prediction_payload

class HlsLoopInfoView(APIView):
    """Return the HLS live loop URL and ensure the stream is running."""

    def get(self, request, *args, **kwargs):
        ok, playlist_path, err = ensure_hls_live_loop()
        if not ok or not playlist_path:
            return Response({"ok": False, "error": err or "unknown"}, status=503)
        # Build public URL under MEDIA_URL
        rel = Path(playlist_path).relative_to(Path(settings.MEDIA_ROOT)).as_posix()
        hls_url = request.build_absolute_uri(
            (str(settings.MEDIA_URL).rstrip("/") + "/" + rel)
        )
        return Response({"ok": True, "hls_url": hls_url})


## Removed MJPEG and MP4 demo endpoints to simplify


class HlsPredictView(APIView):
    """Return a snapshot prediction for the demo HLS loop source (from media files)."""

    def get(self, request, *args, **kwargs):
        from core.flood_camera_monitoring.infra.opencv_stream import (
            OpenCVVideoStream,
        )
        from core.flood_camera_monitoring.services.stream_prediction import (
            predict_snapshot,
        )
        from core.flood_camera_monitoring.infra.torch_flood_classifier import (
            build_default_classifier,
        )

        # Use the same source as HLS (loop of media files)
        loop_url = media_loop_url()
        if not loop_url:
            raise Http404("No .mp4 files found in MEDIA_ROOT")

        clf = build_default_classifier()
        stream = OpenCVVideoStream(loop_url)
        # Advance a few frames to avoid sampling always the very first frame
        try:
            to_skip = next_skip_count()
            for _ in range(max(0, to_skip)):
                _ = stream.grab()
                time.sleep(0.005)
        except Exception:
            pass
        try:
            res = predict_snapshot(
                classifier=clf,
                stream=stream,
                timeout_seconds=float(request.query_params.get("timeout", 5.0)),
                meta={
                    "skipped_frames": int(to_skip) if "to_skip" in locals() else 0,
                    "source": loop_url,
                    "model_fallback": bool(getattr(clf, "_fallback", False)),
                    "checkpoint": str(getattr(clf, "checkpoint_path", "")),
                },
            )
        except TimeoutError:
            return Response({"detail": "Could not capture frame"}, status=504)

        return Response(build_prediction_payload(res))
