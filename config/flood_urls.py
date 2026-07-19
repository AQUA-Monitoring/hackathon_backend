"""Restricted URL configuration used by the optional flood API service."""

from django.urls import include, path

from config.core_health import health


urlpatterns = [
    path("health/", health, name="flood-service-health"),
    path("api/addressing/", include("core.addressing.presentation.urls")),
    path(
        "api/flood_monitoring/",
        include("core.flood_camera_monitoring.presentation.flood_urls"),
    ),
]
