from __future__ import annotations

import hashlib
import logging
from typing import Any

from django.conf import settings
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.common.cache import cache_get_json, cache_set_json
from core.flood_camera_monitoring.services.evaluation import (
    EvalConfig,
    aggregate_predictions,
    capture_frames,
    operational_confidence,
    operational_state,
)
from core.flood_camera_monitoring.infra.demo_stream_client import (
    DemoStreamClient,
    DemoStreamUnavailable,
)
from core.flood_camera_monitoring.infra.torch_flood_classifier import (
    get_default_classifier,
)
from core.flood_camera_monitoring.infra.utils import resolve_checkpoint_path
from core.flood_camera_monitoring.presentation.demo_control_views import (
    DemoStateView as BaseDemoStateView,
    DemoStatusView as BaseDemoStatusView,
)


logger = logging.getLogger(__name__)


def _enabled() -> bool:
    return bool(settings.DEMO_ENABLED)


def _client() -> DemoStreamClient:
    return DemoStreamClient()


def _public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    output = dict(payload)
    segment = output.get("segment")
    if isinstance(segment, dict):
        output["segment"] = {
            key: value for key, value in segment.items() if key != "internal_url"
        }
    return output


def _model_version() -> str:
    checkpoint = resolve_checkpoint_path()
    try:
        stat = checkpoint.stat()
        value = f"{checkpoint.name}:{stat.st_size}:{stat.st_mtime_ns}"
    except OSError:
        value = f"{checkpoint.name}:missing"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _cached(key: str) -> dict[str, Any] | None:
    try:
        value = cache_get_json(key)
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _store_cache(key: str, payload: dict[str, Any]) -> None:
    try:
        cache_set_json(key, payload, ex=int(settings.DEMO_PREDICTION_CACHE_SECONDS))
    except Exception:
        logger.warning("Could not cache demo prediction", exc_info=True)


class DemoStatusView(BaseDemoStatusView):
    """Full-service status preserving the DEMO_ENABLED contract."""

    require_enabled = True


class DemoStateView(BaseDemoStateView):
    """Full-service control preserving the DEMO_ENABLED contract."""

    require_enabled = True


class DemoPredictView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        if not _enabled():
            return Response(
                {"detail": "Demo stream is disabled"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            stream_state = _client().get_state()
        except DemoStreamUnavailable as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        segment = stream_state.get("segment")
        if not isinstance(segment, dict) or not segment.get("internal_url"):
            return Response(
                {"detail": "No complete demo segment is available yet"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        version = _model_version()
        cache_key = (
            f"flood:demo:{stream_state.get('session_id')}:"
            f"{segment.get('sequence')}:{version}"
        )
        cached = _cached(cache_key)
        if cached is not None:
            return Response(cached)

        classifier = get_default_classifier()
        fallback = bool(getattr(classifier, "_fallback", False))
        if fallback:
            return Response(
                {
                    "detail": "The real flood model is not available",
                    "model": {"ready": False, "fallback": True, "version": version},
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        cfg = EvalConfig(sample_frames=3)
        try:
            frames = capture_frames(str(segment["internal_url"]), cfg)
        except Exception as exc:
            logger.exception("Could not capture demo segment")
            return Response(
                {"detail": f"Could not capture demo segment: {exc}"},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )
        if not frames:
            return Response(
                {"detail": "Could not capture frames from demo segment"},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )

        summary, _ = aggregate_predictions(frames, classifier, cfg)
        actual = operational_state(summary)
        raw_expected = segment.get("expected_state")
        expected = raw_expected if isinstance(raw_expected, str) else None
        public_segment = {
            key: value for key, value in segment.items() if key != "internal_url"
        }
        payload = {
            "session_id": stream_state.get("session_id"),
            "demo_state": stream_state.get("demo_state"),
            "segment": public_segment,
            "prediction": {
                "state": actual,
                "confidence": operational_confidence(summary, actual),
                "probabilities": {
                    "normal": float(summary["mean_normal"]),
                    "medium": float(summary["mean_medium"]),
                    "flooded": float(summary["mean_flooded"]),
                },
                "frames": int(summary["frames_count"]),
            },
            "validation": {
                "expected": expected,
                "actual": actual,
                "match": expected == actual if expected is not None else None,
            },
            "model": {"ready": True, "fallback": False, "version": version},
        }
        _store_cache(cache_key, payload)
        return Response(payload)
