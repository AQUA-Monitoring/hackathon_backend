from celery import shared_task
import logging
from django.conf import settings
from core.common.cache import cache_set_json, now_ts


@shared_task
def analyze_all_cameras_task() -> int:
    """Atualiza snapshots operacionais e persiste indicações válidas."""
    from core.flood_camera_monitoring.application.use_cases.analyze_all_cameras import (
        AnalyzeAllCamerasService,
    )

    logger = logging.getLogger(__name__)
    service = AnalyzeAllCamerasService()
    saved = service.run()
    logger.info("AnalyzeAllCamerasTask finished: saved=%s", saved)
    return saved


@shared_task
def refresh_predict_all_cache_task() -> int:
    """Lê snapshots persistidos e atualiza o cache compartilhado.

    Stores under key 'flood:predict_all' a JSON payload {"data": [...], "ts": <unix>}.
    Returns the number of camera entries computed.
    """
    from core.flood_camera_monitoring.application.use_cases.predict_all_cameras import (
        PredictAllCamerasService,
    )

    logger = logging.getLogger(__name__)
    service = PredictAllCamerasService()
    data = service.run()
    try:
        ttl = int(getattr(settings, "PREDICT_CACHE_TTL_SECONDS", 300))
        cache_set_json("flood:predict_all", {"data": data, "ts": now_ts()}, ex=ttl)
        logger.info("Refreshed predict_all cache with %s entries", len(data))
    except Exception as e:
        logger.warning("Failed to set predict_all cache: %s", e)
    return len(data)
