from django.contrib import admin

from .models import PushDelivery, PushSubscription, RegionSubscription


@admin.register(RegionSubscription)
class RegionSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "region", "created_at")
    search_fields = ("user__email", "region__name", "region__city")


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "is_active", "created_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("user__email",)
    exclude = ("endpoint", "p256dh", "auth")


@admin.register(PushDelivery)
class PushDeliveryAdmin(admin.ModelAdmin):
    list_display = ("operational_alert", "kind", "status", "attempts", "created_at")
    list_filter = ("kind", "status")
    readonly_fields = ("operational_alert", "subscription", "kind", "attempts", "last_error")
