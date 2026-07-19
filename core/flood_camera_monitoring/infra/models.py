from django.db import models
import uuid

from core.common.models import TimestampedModel


class Camera(TimestampedModel):
    class CameraStatus(models.IntegerChoices):
        ACTIVE = 1, "ACTIVE"
        INACTIVE = 2, "INACTIVE"
        OFFLINE = 3, "OFFLINE"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.IntegerField(
        choices=CameraStatus.choices, default=CameraStatus.INACTIVE
    )
    video_hls = models.CharField(max_length=512, blank=True, null=True)
    video_embed = models.CharField(max_length=512, blank=True, null=True)
    description = models.CharField(max_length=255, blank=True)
    # Neighborhood is now a FK to Addressing.Neighborhood
    neighborhood = models.ForeignKey(
        "addressing.Neighborhood",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cameras",
    )
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    address = models.ForeignKey(
        "addressing.Address",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cameras",
    )
    created_by = models.ForeignKey(
        "users.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="registered_cameras",
    )

    def __str__(self) -> str:  # pragma: no cover
        return f"Camera {self.id} ({self.get_status_display()})"


class CameraOperationalSnapshot(TimestampedModel):
    class StreamStatus(models.TextChoices):
        UNKNOWN = "UNKNOWN", "UNKNOWN"
        CHECKING = "CHECKING", "CHECKING"
        ONLINE = "ONLINE", "ONLINE"
        UNAVAILABLE = "UNAVAILABLE", "UNAVAILABLE"

    class AnalysisStatus(models.TextChoices):
        NOT_ANALYZED = "NOT_ANALYZED", "NOT_ANALYZED"
        RUNNING = "RUNNING", "RUNNING"
        AVAILABLE = "AVAILABLE", "AVAILABLE"
        STALE = "STALE", "STALE"
        NO_FRAME = "NO_FRAME", "NO_FRAME"
        MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE", "MODEL_UNAVAILABLE"
        ERROR = "ERROR", "ERROR"

    class CameraClassification(models.TextChoices):
        NO_INDICATION = "NO_INDICATION", "NO_INDICATION"
        INTERMEDIATE_INDICATION = (
            "INTERMEDIATE_INDICATION",
            "INTERMEDIATE_INDICATION",
        )
        FLOOD_INDICATION = "FLOOD_INDICATION", "FLOOD_INDICATION"

    class ModelStatus(models.TextChoices):
        UNKNOWN = "UNKNOWN", "UNKNOWN"
        READY = "READY", "READY"
        UNAVAILABLE = "UNAVAILABLE", "UNAVAILABLE"
        FALLBACK = "FALLBACK", "FALLBACK"

    camera = models.OneToOneField(
        Camera,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="operational_snapshot",
    )
    stream_status = models.CharField(
        max_length=20,
        choices=StreamStatus.choices,
        default=StreamStatus.UNKNOWN,
        db_index=True,
    )
    stream_checked_at = models.DateTimeField(null=True, blank=True)
    analysis_status = models.CharField(
        max_length=24,
        choices=AnalysisStatus.choices,
        default=AnalysisStatus.NOT_ANALYZED,
        db_index=True,
    )
    classification = models.CharField(
        max_length=32,
        choices=CameraClassification.choices,
        null=True,
        blank=True,
    )
    prob_normal = models.FloatField(null=True, blank=True)
    prob_medium = models.FloatField(null=True, blank=True)
    prob_flooded = models.FloatField(null=True, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    frames = models.PositiveIntegerField(null=True, blank=True)
    analysis_started_at = models.DateTimeField(null=True, blank=True)
    analyzed_at = models.DateTimeField(null=True, blank=True)
    model_status = models.CharField(
        max_length=20,
        choices=ModelStatus.choices,
        default=ModelStatus.UNKNOWN,
        db_index=True,
    )
    model_version = models.CharField(max_length=255, null=True, blank=True)
    error_code = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self) -> str:  # pragma: no cover
        return f"Snapshot {self.camera_id}: {self.stream_status}/{self.analysis_status}"


class FloodDetectionRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    camera = models.ForeignKey(
        Camera, on_delete=models.CASCADE, related_name="detections"
    )
    is_flooded = models.BooleanField()
    confidence = models.FloatField()
    prob_normal = models.FloatField()
    prob_flooded = models.FloatField()
    prob_medium = models.FloatField(default=0.0)
    # Indica predição em zona intermediária/ambígua (ex.: perto de 50% ou fora do padrão)
    medium = models.BooleanField(default=False, db_index=True)
    image = models.ImageField(
        upload_to="flood_detections/%Y/%m/%d/", null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Flood detection record"
        verbose_name_plural = "Flood detection records"
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["confidence"]),
        ]
