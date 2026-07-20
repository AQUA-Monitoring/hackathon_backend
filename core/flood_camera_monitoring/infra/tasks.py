"""Compatibilidade para imports e nomes Celery históricos.

As implementações canônicas vivem em :mod:`core.flood_camera_monitoring.tasks`.
"""

from core.flood_camera_monitoring.tasks import (
    analyze_all_cameras_task,
    refresh_all_and_cache_task,
    refresh_predict_all_cache_task,
)

__all__ = [
    "analyze_all_cameras_task",
    "refresh_all_and_cache_task",
    "refresh_predict_all_cache_task",
]
