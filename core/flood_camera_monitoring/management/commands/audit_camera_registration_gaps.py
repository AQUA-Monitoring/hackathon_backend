import json

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.flood_camera_monitoring.infra.models import Camera


class Command(BaseCommand):
    help = (
        "Audita câmeras legadas sem endereço ou autoria e emite um relatório JSON "
        "sem expor URLs de transmissão."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fail-on-pending",
            action="store_true",
            help="Encerra com código diferente de zero quando houver pendências.",
        )

    def handle(self, *args, **options):
        cameras = Camera.objects.order_by("id")
        pending = []
        missing_address = 0
        missing_created_by = 0

        for camera in cameras.iterator():
            missing = []
            if camera.address_id is None:
                missing.append("address")
                missing_address += 1
            if camera.created_by_id is None:
                missing.append("created_by")
                missing_created_by += 1
            if not missing:
                continue

            pending.append(
                {
                    "camera_id": str(camera.id),
                    "administrative_status": (
                        "INACTIVE"
                        if camera.status == Camera.CameraStatus.INACTIVE
                        else "ACTIVE"
                    ),
                    "missing": missing,
                    "legacy_location_available": bool(
                        camera.neighborhood_id
                        and camera.latitude is not None
                        and camera.longitude is not None
                    ),
                }
            )

        report = {
            "generated_at": timezone.now().isoformat(),
            "summary": {
                "total_cameras": cameras.count(),
                "pending_cameras": len(pending),
                "missing_address": missing_address,
                "missing_created_by": missing_created_by,
            },
            "pending": pending,
            "backfill_policy": (
                "Forneça explicitamente o mapeamento de endereço e o usuário "
                "importador; o comando não inventa nem altera dados."
            ),
        }
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))

        if options["fail_on_pending"] and pending:
            raise SystemExit(2)
