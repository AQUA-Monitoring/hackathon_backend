from celery import shared_task
import logging
from core.common.cache import cache_set_json, now_ts


@shared_task
def analyze_all_cameras_task() -> int:
    """Run analysis, persist alerts; return number of records saved."""
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
    """Compute predictions and refresh the shared cache.

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
        cache_set_json("flood:predict_all", {"data": data, "ts": now_ts()}, ex=300)
        logger.info("Refreshed predict_all cache with %s entries", len(data))
    except Exception as e:
        logger.warning("Failed to set predict_all cache: %s", e)
    return len(data)
