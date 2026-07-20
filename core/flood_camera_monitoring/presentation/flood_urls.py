"""Full Flood Monitoring API; imported only by flood/full images."""

from django.urls import path

from core.flood_camera_monitoring.presentation.demo_views import (
    DemoPredictView,
    DemoStateView,
    DemoStatusView,
)
from core.flood_camera_monitoring.presentation.camera_views import CameraMetadataViewSet
from core.flood_camera_monitoring.presentation.health_views import HealthcheckView
from core.flood_camera_monitoring.presentation.monitoring_views import FloodMonitoringViewSet


urlpatterns = [
    path(
        "stream/snapshot",
        FloodMonitoringViewSet.as_view({"post": "predict_snapshot"}),
        name="stream-snapshot-detect",
    ),
    path(
        "predict/all/",
        CameraMetadataViewSet.as_view({"get": "predict_all"}),
        name="predict-all-cameras",
    ),
    path(
        "cameras/",
        CameraMetadataViewSet.as_view({"get": "list", "post": "create"}),
        name="cameras-list",
    ),
    path(
        "cameras/<uuid:pk>/",
        CameraMetadataViewSet.as_view({"get": "retrieve"}),
        name="cameras-detail",
    ),
    path(
        "cameras/<uuid:pk>/nearby/",
        CameraMetadataViewSet.as_view({"get": "nearby"}),
        name="cameras-nearby",
    ),
    path("health/", HealthcheckView.as_view(), name="flood-health"),
    path("demo", DemoStatusView.as_view(), name="demo-status"),
    path("demo/state", DemoStateView.as_view(), name="demo-state"),
    path("demo/predict", DemoPredictView.as_view(), name="demo-predict"),
]
