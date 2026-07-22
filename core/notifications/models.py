import uuid

from django.db import models


class RegionSubscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="region_subscriptions"
    )
    region = models.ForeignKey(
        "addressing.Region", on_delete=models.CASCADE, related_name="subscriptions"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["region__city", "region__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "region"], name="uniq_notification_user_region"
            )
        ]


class PushSubscription(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="push_subscriptions"
    )
    endpoint = models.URLField(max_length=2048, unique=True)
    p256dh = models.CharField(max_length=512)
    auth = models.CharField(max_length=512)
    user_agent = models.CharField(max_length=512, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["user", "is_active"])]


class PushDelivery(models.Model):
    class Kind(models.TextChoices):
        CONFIRMED = "confirmed", "Alagamento confirmado"
        RESOLVED = "resolved", "Alerta encerrado"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        SENT = "sent", "Enviada"
        FAILED = "failed", "Falhou"
        EXPIRED = "expired", "Assinatura expirada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operational_alert = models.ForeignKey(
        "flood_camera_monitoring.OperationalAlert",
        on_delete=models.CASCADE,
        related_name="push_deliveries",
    )
    subscription = models.ForeignKey(
        PushSubscription, on_delete=models.CASCADE, related_name="deliveries"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["operational_alert", "subscription", "kind"],
                name="uniq_push_alert_subscription_kind",
            )
        ]
        indexes = [models.Index(fields=["status", "created_at"])]
