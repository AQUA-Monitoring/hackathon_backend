from django.urls import re_path

from core.flood_camera_monitoring.presentation.proxy import proxy_flood_camera


urlpatterns = [
    re_path(r"^(?P<path>.*)$", proxy_flood_camera, name="flood-camera-proxy"),
]
