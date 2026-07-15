"""Flood URL subset that is safe in the lightweight development gateway."""

from django.urls import path

from core.flood_camera_monitoring.presentation.demo_control_views import (
    DemoStateView,
    DemoStatusView,
)


urlpatterns = [
    path("demo", DemoStatusView.as_view(), name="demo-status"),
    path("demo/state", DemoStateView.as_view(), name="demo-state"),
]
