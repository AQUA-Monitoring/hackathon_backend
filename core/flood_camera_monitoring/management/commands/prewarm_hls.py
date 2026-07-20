from django.core.management.base import BaseCommand
from core.flood_camera_monitoring.infra.hls import ensure_hls_live_loop


class Command(BaseCommand):
    help = (
        "Ensure the HLS live loop is running (generates playlist/segments if needed)."
    )

    def handle(self, *args, **options):
        ok, playlist, err = ensure_hls_live_loop()
        if ok:
            self.stdout.write(self.style.SUCCESS(f"HLS ready: {playlist}"))
        else:
            self.stderr.write(self.style.ERROR(f"HLS error: {err}"))
