"""Restricted URL configuration for the optional flood camera API service."""

from django.http import JsonResponse
from django.urls import include, path


def health(_request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("health/", health, name="flood-service-health"),
    path(
        "api/flood_monitoring/",
        include("core.flood_camera_monitoring.presentation.urls"),
    ),
]
