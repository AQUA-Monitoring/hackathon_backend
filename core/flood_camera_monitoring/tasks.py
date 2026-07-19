from celery import shared_task
import logging

from core.common.cache import cache_set_json
from django.conf import settings


@shared_task
def refresh_all_and_cache_task() -> int:
    """Atualiza snapshots, persiste indicações e publica a projeção no cache."""
    from core.flood_camera_monitoring.application.use_cases.analyze_all_cameras import (
        AnalyzeAllCamerasService,
    )

    logger = logging.getLogger(__name__)
    try:
        service = AnalyzeAllCamerasService()
        data, saved = service.run_and_collect()
        payload = {"data": data, "ts": int(__import__("time").time())}
        ttl = getattr(settings, "PREDICT_CACHE_TTL_SECONDS", 300)
        cache_set_json("flood:predict_all", payload, ex=int(ttl))
        logger.info(
            "Unified refresh done: cached=%d items, persisted=%d alerts",
            len(data),
            saved,
        )
        return len(data)
    except Exception:
        logger.exception("Unified refresh failed")
        return 0
