from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .adapters import PushDeliveryError, WebPushAdapter
from .models import PushDelivery, PushSubscription


def _alert_region_id(alert):
    return getattr(alert, "region_id", None)


def fanout_alert(alert, kind: str) -> int:
    """Persist one delivery per active device subscribed to the alert region."""
    region_id = _alert_region_id(alert)
    if not region_id:
        return 0
    subscriptions = PushSubscription.objects.filter(
        is_active=True,
        user__region_subscriptions__region_id=region_id,
    ).distinct()
    pending_ids = []
    for subscription in subscriptions:
        delivery, created = PushDelivery.objects.get_or_create(
            operational_alert=alert,
            subscription=subscription,
            kind=kind,
        )
        if created:
            pending_ids.append(delivery.id)
    if pending_ids:
        from .tasks import deliver_push_batch_task

        transaction.on_commit(lambda: deliver_push_batch_task.delay([str(i) for i in pending_ids]))
    return len(pending_ids)


def schedule_confirmed_alert(alert) -> int:
    return fanout_alert(alert, PushDelivery.Kind.CONFIRMED)


def schedule_resolved_alert(alert) -> int:
    return fanout_alert(alert, PushDelivery.Kind.RESOLVED)


def schedule_publication_push(publication, event_kind: str) -> int:
    kind = (
        PushDelivery.Kind.CONFIRMED
        if event_kind == "CONFIRMED"
        else PushDelivery.Kind.RESOLVED
    )
    return fanout_alert(publication.alert, kind)


def _payload(delivery: PushDelivery) -> dict:
    alert = delivery.operational_alert
    confirmed = delivery.kind == PushDelivery.Kind.CONFIRMED
    camera_id = getattr(alert, "camera_id", None)
    region = getattr(alert, "region", None)
    region_name = getattr(region, "name", "região monitorada")
    return {
        "title": (
            "Alagamento confirmado por administrador"
            if confirmed
            else "Alerta de alagamento encerrado"
        ),
        "body": (
            f"Há um alagamento confirmado em {region_name}."
            if confirmed
            else f"O alerta de alagamento em {region_name} foi encerrado."
        ),
        "url": f"/cameras/{camera_id}" if camera_id else f"/regioes/{alert.region_id}",
        "alert_id": str(alert.pk),
        "kind": delivery.kind,
    }


def deliver_push(delivery_id, *, adapter=None) -> str:
    adapter = adapter or WebPushAdapter()
    with transaction.atomic():
        delivery = (
            PushDelivery.objects.select_for_update(of=("self",))
            .select_related("subscription", "operational_alert__region")
            .get(pk=delivery_id)
        )
        if delivery.status in {PushDelivery.Status.SENT, PushDelivery.Status.EXPIRED}:
            return delivery.status
        delivery.attempts += 1
        subscription = delivery.subscription
        try:
            adapter.send(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                payload=_payload(delivery),
            )
        except PushDeliveryError as exc:
            if exc.status_code in {404, 410}:
                subscription.is_active = False
                subscription.expired_at = timezone.now()
                subscription.save(update_fields=["is_active", "expired_at", "updated_at"])
                delivery.status = PushDelivery.Status.EXPIRED
            else:
                delivery.status = PushDelivery.Status.FAILED
            delivery.last_error = str(exc)[:255]
            delivery.save(update_fields=["attempts", "status", "last_error", "updated_at"])
            return delivery.status
        delivery.status = PushDelivery.Status.SENT
        delivery.sent_at = timezone.now()
        delivery.last_error = ""
        delivery.save(
            update_fields=["attempts", "status", "sent_at", "last_error", "updated_at"]
        )
        return delivery.status


def recover_failed_deliveries() -> int:
    ids = list(
        PushDelivery.objects.filter(
            status=PushDelivery.Status.FAILED,
            attempts__lt=settings.WEB_PUSH_MAX_ATTEMPTS,
            subscription__is_active=True,
        ).values_list("id", flat=True)[: settings.WEB_PUSH_RECOVERY_BATCH_SIZE]
    )
    if ids:
        PushDelivery.objects.filter(id__in=ids).update(status=PushDelivery.Status.PENDING)
        from .tasks import deliver_push_batch_task

        deliver_push_batch_task.delay([str(item) for item in ids])
    return len(ids)
