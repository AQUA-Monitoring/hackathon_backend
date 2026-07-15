"""Full Flood Monitoring API; imported only by flood/full images."""

from django.urls import path

from core.flood_camera_monitoring.presentation.demo_views import (
    DemoPredictView,
    DemoStateView,
    DemoStatusView,
)
from core.flood_camera_monitoring.presentation.viewsets import (
    FloodMonitoringViewSet,
    HealthcheckView,
)


urlpatterns = [
    path(
        "stream/snapshot",
        FloodMonitoringViewSet.as_view({"post": "predict_snapshot"}),
        name="stream-snapshot-detect",
    ),
    path(
        "predict/all/",
        FloodMonitoringViewSet.as_view({"get": "predict_all"}),
        name="predict-all-cameras",
    ),
    path(
        "cameras/",
        FloodMonitoringViewSet.as_view({"get": "cameras"}),
        name="cameras-list",
    ),
    path("health/", HealthcheckView.as_view(), name="flood-health"),
    path("demo", DemoStatusView.as_view(), name="demo-status"),
    path("demo/state", DemoStateView.as_view(), name="demo-state"),
    path("demo/predict", DemoPredictView.as_view(), name="demo-predict"),
]
