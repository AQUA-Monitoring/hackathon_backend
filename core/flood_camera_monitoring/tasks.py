from celery import shared_task
import logging

from core.common.cache import cache_set_json, now_ts
from django.conf import settings


@shared_task(name="core.flood_camera_monitoring.tasks.refresh_all_and_cache_task")
def refresh_all_and_cache_task() -> int:
    """Atualiza snapshots, persiste indicações e publica a projeção no cache."""
    from core.flood_camera_monitoring.services.analyze import (
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


@shared_task(name="core.flood_camera_monitoring.infra.tasks.analyze_all_cameras_task")
def analyze_all_cameras_task() -> int:
    """Nome Celery legado; implementação canônica neste módulo."""
    from core.flood_camera_monitoring.services.analyze import AnalyzeAllCamerasService

    saved = AnalyzeAllCamerasService().run()
    logging.getLogger(__name__).info(
        "AnalyzeAllCamerasTask finished: saved=%s", saved
    )
    return saved


@shared_task(
    name="core.flood_camera_monitoring.infra.tasks.refresh_predict_all_cache_task"
)
def refresh_predict_all_cache_task() -> int:
    """Nome Celery legado para atualização do cache a partir dos snapshots."""
    from core.flood_camera_monitoring.services.predict import PredictAllCamerasService

    data = PredictAllCamerasService().run()
    try:
        ttl = int(getattr(settings, "PREDICT_CACHE_TTL_SECONDS", 300))
        cache_set_json("flood:predict_all", {"data": data, "ts": now_ts()}, ex=ttl)
    except Exception:
        logging.getLogger(__name__).warning(
            "Failed to set predict_all cache", exc_info=True
        )
    return len(data)
