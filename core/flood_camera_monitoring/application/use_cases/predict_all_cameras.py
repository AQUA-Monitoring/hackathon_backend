from dataclasses import dataclass
from typing import Any

from core.flood_camera_monitoring.application.operational_snapshot import (
    snapshot_prediction_payload,
)
from core.flood_camera_monitoring.infra.models import (
    Camera,
    CameraOperationalSnapshot,
)


@dataclass
class PredictAllCamerasService:
    """Lê os últimos snapshots das câmeras ativas.

    A leitura nunca abre streams, carrega modelos ou inicia inferência. A
    atualização dos snapshots pertence à tarefa operacional assíncrona.
    """

    def run(self) -> list[dict[str, Any]]:
        cameras = Camera.objects.filter(
            status=Camera.CameraStatus.ACTIVE
        ).select_related("operational_snapshot")
        results: list[dict[str, Any]] = []
        for camera in cameras.iterator():
            try:
                snapshot = camera.operational_snapshot
            except CameraOperationalSnapshot.DoesNotExist:
                snapshot = None
            results.append(snapshot_prediction_payload(camera, snapshot))
        return results
